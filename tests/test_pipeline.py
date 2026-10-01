"""Tests for the cleaning steps, using tiny made-up files (no internet needed).

Run with:  uv run pytest
"""

from datetime import date

import duckdb
import pytest

from melbourne_foot_traffic import db, sources

OLD_FORMAT = """ID,Date_Time,Year,Month,Mdate,Day,Time,Sensor_ID,Sensor_Name,Hourly_Counts
1,"November 01, 2019 05:00:00 PM",2019,November,1,Friday,17,4,Town Hall (West),2500
2,"November 01, 2019 06:00:00 PM",2019,November,1,Friday,18,4,Town Hall (West),1800
3,"November 01, 2019 06:00:00 PM",2019,November,1,Friday,18,4,Town Hall (West),1800
4,"December 15, 2022 09:00:00 AM",2022,December,15,Thursday,9,4,Town Hall (West),900
5,"September 13, 2010 12:00:00 AM",2010,September,13,Monday,0,4,Town Hall (West),108
6,"September 13, 2010 12:00:00 AM",2010,September,13,Monday,0,4,Town Hall (West),2864
"""

NEW_FORMAT = """id,location_id,sensing_date,hourday,direction_1,direction_2,pedestriancount,sensor_name,location
a,4,2022-12-15,9,500,450,950,TownHallW,"-37.81, 144.96"
b,4,2022-12-15,10,0,0,0,TownHallW,"-37.81, 144.96"
c,6,2024-03-01,8,700,600,1300,FliS_T,"-37.82, 144.97"
"""


@pytest.fixture
def con():
    c = duckdb.connect(":memory:")
    c.execute(db.SCHEMA)
    return c


def write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text)
    return p


def test_old_format_parsed_and_deduplicated(con, tmp_path):
    p = write(tmp_path, "old.csv", OLD_FORMAT)
    n = db.load_counts(con, [p], "historic")
    assert n == 3  # exact duplicate 6pm row collapsed to one
    row = con.execute(
        "SELECT sensor_id, date, hour, count FROM counts ORDER BY date, hour LIMIT 1"
    ).fetchone()
    assert row == (4, date(2019, 11, 1), 17, 2500)


def test_conflicting_counts_are_dropped(con, tmp_path):
    # Two different counts for the same sensor-hour: neither can be trusted
    db.load_counts(con, [write(tmp_path, "old.csv", OLD_FORMAT)], "historic")
    n = con.execute("SELECT count(*) FROM counts WHERE date = '2010-09-13'").fetchone()[0]
    assert n == 0


def test_new_format_keeps_zeros(con, tmp_path):
    p = write(tmp_path, "new.csv", NEW_FORMAT)
    db.load_counts(con, [p], "live")
    zero = con.execute("SELECT count FROM counts WHERE hour = 10").fetchone()[0]
    assert zero == 0  # a real zero is kept, not treated as missing


def test_live_replaces_overlapping_archive(con, tmp_path):
    db.load_counts(con, [write(tmp_path, "old.csv", OLD_FORMAT)], "historic")
    db.load_counts(con, [write(tmp_path, "new.csv", NEW_FORMAT)], "live")
    db.reconcile_sources(con)
    rows = con.execute(
        "SELECT source, count FROM counts WHERE date = '2022-12-15' AND hour = 9"
    ).fetchall()
    assert rows == [("live", 950)]


def test_incremental_reload_does_not_duplicate(con, tmp_path):
    p = write(tmp_path, "new.csv", NEW_FORMAT)
    db.load_counts(con, [p], "live")
    db.load_counts(con, [p], "live")  # same file again, as on an overlapping rerun
    assert con.execute("SELECT count(*) FROM counts").fetchone()[0] == 3


def test_unknown_format_gives_clear_error(con, tmp_path):
    p = write(tmp_path, "bad.csv", "foo,bar\n1,2\n")
    with pytest.raises(ValueError, match="Unrecognised counts file format"):
        db.load_counts(con, [p], "live")


def test_weather_converted_to_local_time_across_dst():
    # Daylight saving ended at 3am on 7 April 2024 in Melbourne: 2am happens twice.
    # 15:00 and 16:00 UTC on 6 April are both 02:00 local on 7 April.
    payload = {
        "hourly": {
            "time": ["2024-04-06T15:00", "2024-04-06T16:00", "2024-04-06T17:00"],
            "temperature_2m": [12.0, 11.0, 10.0],
            "precipitation": [0.2, 0.3, 0.0],
        }
    }
    df = sources.weather_json_to_frame(payload)
    assert list(df["hour"]) == [2, 2, 3]
    assert set(df["date"]) == {date(2024, 4, 7)}


def test_weather_view_merges_repeated_dst_hour(con):
    payload = {
        "hourly": {
            "time": ["2024-04-06T15:00", "2024-04-06T16:00"],
            "temperature_2m": [12.0, 11.0],
            "precipitation": [0.2, 0.3],
        }
    }
    db.upsert_weather(con, sources.weather_json_to_frame(payload))
    db.create_views(con)
    temp, rain = con.execute(
        "SELECT temperature, precipitation_mm FROM weather WHERE hour = 2"
    ).fetchone()
    assert temp == pytest.approx(11.5)  # averaged
    assert rain == pytest.approx(0.5)  # summed
