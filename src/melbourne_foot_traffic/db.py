"""Load raw files into DuckDB as clean, typed tables.

Tables
------
counts          one row per sensor per local hour: sensor_id, date, hour, count, source
sensors         sensor locations as published (column names lower-cased)
weather_hourly  Open-Meteo weather per UTC hour, with local date and hour added

Views
-----
weather         weather per local (date, hour); handles the repeated hour when DST ends
hourly          counts joined to weather: the table the model and analysis start from

An hour with no row in `counts` means "no record" (sensor offline or not yet
installed), which is different from a row with count = 0 ("nobody walked past").
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS counts (
    sensor_id INTEGER NOT NULL,
    date      DATE    NOT NULL,
    hour      TINYINT NOT NULL,
    count     INTEGER NOT NULL,
    source    VARCHAR NOT NULL   -- 'historic' (2009-2022 ZIP) or 'live' (portal table)
);
CREATE TABLE IF NOT EXISTS weather_hourly (
    ts_utc               TIMESTAMP NOT NULL,
    date                 DATE      NOT NULL,
    hour                 TINYINT   NOT NULL,
    temperature_2m       DOUBLE,
    apparent_temperature DOUBLE,
    precipitation        DOUBLE,
    rain                 DOUBLE,
    relative_humidity_2m DOUBLE,
    cloud_cover          DOUBLE,
    wind_speed_10m       DOUBLE
);
"""

VIEWS = """
CREATE OR REPLACE VIEW weather AS
SELECT
    date, hour,
    avg(temperature_2m)       AS temperature,
    avg(apparent_temperature) AS apparent_temperature,
    sum(precipitation)        AS precipitation_mm,
    sum(rain)                 AS rain_mm,
    avg(relative_humidity_2m) AS humidity,
    avg(cloud_cover)          AS cloud_cover,
    avg(wind_speed_10m)       AS wind_speed
FROM weather_hourly
GROUP BY date, hour;

CREATE OR REPLACE VIEW hourly AS
SELECT c.sensor_id, c.date, c.hour, c.count, w.* EXCLUDE (date, hour)
FROM counts c
LEFT JOIN weather w USING (date, hour);
"""


def connect(path: Path | None = None) -> duckdb.DuckDBPyConnection:
    path = path or config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    con.execute(SCHEMA)
    return con


def create_views(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(VIEWS)


# --- Counts --------------------------------------------------------------------


def _csv_source(paths: list[Path]) -> str:
    files = ", ".join(f"'{p.as_posix()}'" for p in paths)
    # Read everything as text and cast ourselves, so odd rows can't break sniffing
    return (
        f"read_csv([{files}], header=true, all_varchar=true, "
        f"normalize_names=true, union_by_name=true)"
    )


def counts_select_sql(con: duckdb.DuckDBPyConnection, paths: list[Path]) -> str:
    """SQL that turns either published format into (sensor_id, date, hour, count).

    New format (portal table, late 2022 onwards):
        location_id, sensing_date, hourday, pedestriancount
    Old format (2009-2022 archive):
        sensor_id, date_time ("November 01, 2019 05:00:00 PM"), hourly_counts
    """
    src = _csv_source(paths)
    cols = {row[0] for row in con.execute(f"DESCRIBE SELECT * FROM {src}").fetchall()}

    if {"location_id", "sensing_date", "hourday", "pedestriancount"} <= cols:
        return f"""
            SELECT
                TRY_CAST(location_id AS INTEGER)      AS sensor_id,
                TRY_CAST(sensing_date AS DATE)        AS date,
                TRY_CAST(hourday AS TINYINT)          AS hour,
                TRY_CAST(pedestriancount AS INTEGER)  AS count
            FROM {src}
        """

    if {"sensor_id", "hourly_counts", "date_time"} <= cols:
        # e.g. "November 01, 2019 05:00:00 PM" (other layouts listed as fallbacks)
        ts = (
            "try_strptime(date_time, ['%B %d, %Y %I:%M:%S %p', "
            "'%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%d/%m/%Y %I:%M:%S %p'])"
        )
        date_expr = f"CAST({ts} AS DATE)"
        hour_expr = f"CAST(hour({ts}) AS TINYINT)"
        return f"""
            SELECT
                TRY_CAST(sensor_id AS INTEGER)      AS sensor_id,
                {date_expr}                         AS date,
                {hour_expr}                         AS hour,
                TRY_CAST(hourly_counts AS INTEGER)  AS count
            FROM {src}
        """

    raise ValueError(
        "Unrecognised counts file format. Columns found:\n  "
        + ", ".join(sorted(cols))
        + f"\nFiles: {[p.name for p in paths]}"
    )


def load_counts(
    con: duckdb.DuckDBPyConnection, paths: list[Path], source: str
) -> int:
    """Clean, de-duplicate and insert counts, replacing any overlapping dates."""
    con.execute(
        f"CREATE OR REPLACE TEMP TABLE staged AS {counts_select_sql(con, paths)}"
    )
    total = con.execute("SELECT count(*) FROM staged").fetchone()[0]
    if total == 0:
        print(f"  no new {source} rows")
        return 0

    bad = con.execute(
        "SELECT count(*) FROM staged WHERE sensor_id IS NULL OR date IS NULL "
        "OR hour IS NULL OR count IS NULL OR hour NOT BETWEEN 0 AND 23 OR count < 0"
    ).fetchone()[0]
    if bad:
        print(f"  dropped {bad:,} unparseable rows of {total:,}")
        if bad / total > 0.01:
            sample = con.execute("SELECT * FROM staged WHERE date IS NULL LIMIT 5").df()
            raise ValueError(
                f"More than 1% of {source} rows failed to parse. Sample:\n{sample}"
            )

    # One row per sensor-hour. Exact repeats are collapsed to one row. If the
    # same sensor-hour has *different* counts we can't tell which is right, so
    # all of them are dropped. (Example: September 2010 in the archive stamps
    # every hour of the day as midnight.)
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE staged_clean AS
        SELECT sensor_id, date, hour, min(count) AS count
        FROM staged
        WHERE sensor_id IS NOT NULL AND date IS NOT NULL AND hour BETWEEN 0 AND 23
          AND count IS NOT NULL AND count >= 0
        GROUP BY sensor_id, date, hour
        HAVING count(DISTINCT count) = 1
        """
    )
    conflicts = con.execute(
        """
        SELECT count(*) AS keys, min(date) AS first, max(date) AS last
        FROM (
            SELECT sensor_id, date, hour FROM staged
            WHERE count IS NOT NULL
            GROUP BY ALL HAVING count(DISTINCT count) > 1
        )
        """
    ).fetchone()
    if conflicts[0]:
        print(
            f"  dropped {conflicts[0]:,} sensor-hours with conflicting counts "
            f"(between {conflicts[1]} and {conflicts[2]})"
        )
    kept = con.execute("SELECT count(*) FROM staged_clean").fetchone()[0]

    first = con.execute("SELECT min(date) FROM staged_clean").fetchone()[0]
    con.execute("DELETE FROM counts WHERE source = ? AND date >= ?", [source, first])
    con.execute(
        "INSERT INTO counts SELECT sensor_id, date, hour, count, ? FROM staged_clean",
        [source],
    )
    con.execute("DROP TABLE staged; DROP TABLE staged_clean;")
    print(f"  loaded {kept:,} {source} rows from {first}")
    return kept


def reconcile_sources(con: duckdb.DuckDBPyConnection) -> None:
    """Where the archive and the live table overlap, trust the live table."""
    live_start = last_or_first(con, "min", "live")
    if live_start is None:
        return
    n = con.execute(
        "SELECT count(*) FROM counts WHERE source = 'historic' AND date >= ?",
        [live_start],
    ).fetchone()[0]
    if n:
        con.execute(
            "DELETE FROM counts WHERE source = 'historic' AND date >= ?", [live_start]
        )
        print(f"  removed {n:,} archive rows that overlap the live table (from {live_start})")


def last_or_first(
    con: duckdb.DuckDBPyConnection, fn: str, source: str
) -> date | None:
    return con.execute(
        f"SELECT {fn}(date) FROM counts WHERE source = ?", [source]
    ).fetchone()[0]


# --- Sensors -------------------------------------------------------------------


def load_sensors(con: duckdb.DuckDBPyConnection, path: Path) -> int:
    con.execute(
        f"CREATE OR REPLACE TABLE sensors AS "
        f"SELECT * FROM read_csv('{path.as_posix()}', header=true, normalize_names=true)"
    )
    n = con.execute("SELECT count(*) FROM sensors").fetchone()[0]
    print(f"  loaded {n} sensors")
    return n


# --- Calendar ------------------------------------------------------------------


def load_calendar(con: duckdb.DuckDBPyConnection, cal: pd.DataFrame) -> int:
    """Replace the `calendar` table (one row per day: holidays, terms, events)."""
    con.register("calendar_df", cal)
    con.execute("CREATE OR REPLACE TABLE calendar AS SELECT * FROM calendar_df")
    con.unregister("calendar_df")
    print(f"  calendar: {len(cal):,} days, {int(cal['is_holiday'].sum())} public holidays")
    return len(cal)


# --- Weather -------------------------------------------------------------------


def last_weather_date(con: duckdb.DuckDBPyConnection) -> date | None:
    ts = con.execute("SELECT max(ts_utc) FROM weather_hourly").fetchone()[0]
    return ts.date() if ts is not None else None


def upsert_weather(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    cols = [c[0] for c in con.execute("DESCRIBE weather_hourly").fetchall()]
    df = df.reindex(columns=cols)  # same column order as the table
    first = df["ts_utc"].min()
    con.execute("DELETE FROM weather_hourly WHERE ts_utc >= ?", [first])
    con.register("weather_df", df)
    con.execute("INSERT INTO weather_hourly SELECT * FROM weather_df")
    con.unregister("weather_df")
    print(f"  loaded {len(df):,} weather hours from {first.date()}")
    return len(df)
