"""Tests for calendar features and the baseline. Run with: uv run pytest"""

from datetime import date, timedelta

import duckdb
import pandas as pd
import pytest

from melbourne_foot_traffic import db, events, forecast


@pytest.fixture
def ref_dir(tmp_path):
    (tmp_path / "school_terms.csv").write_text(
        "year,term,start,end,source\n2025,4,2025-10-06,2025-12-19,test\n"
    )
    (tmp_path / "events.csv").write_text(
        "event,start,end,note\nafl_grand_final,2025-09-27,2025-09-27,test\n"
    )
    return tmp_path


def test_calendar_flags(ref_dir):
    cal = events.build_calendar(date(2025, 9, 25), date(2025, 10, 7), ref_dir).set_index("date")
    assert cal.loc[date(2025, 9, 26), "is_holiday"]  # Grand Final eve public holiday
    assert cal.loc[date(2025, 9, 27), "event_afl_grand_final"]
    assert not cal.loc[date(2025, 10, 3), "school_term"]  # school holidays
    assert cal.loc[date(2025, 10, 6), "school_term"]  # term 4 starts


def test_school_term_unknown_outside_listed_years(ref_dir):
    cal = events.build_calendar(date(2024, 5, 1), date(2024, 5, 1), ref_dir)
    assert pd.isna(cal.loc[0, "school_term"])  # 2024 not in the test file: unknown, not False


def test_baseline_only_uses_counts_at_least_5_weeks_old():
    con = duckdb.connect(":memory:")
    con.execute(db.SCHEMA)
    target = date(2026, 3, 3)
    rows = [
        (4, target, 9, 1000),                       # the day we forecast
        (4, target - timedelta(days=7), 9, 9999),   # 1 week before: not yet published
        (4, target - timedelta(days=35), 9, 400),   # 5 weeks before: usable
        (4, target - timedelta(days=42), 9, 600),   # 6 weeks before: usable
    ]
    con.executemany("INSERT INTO counts VALUES (?, ?, ?, ?, 'live')", rows)
    out = forecast.seasonal_baseline(con, str(target), str(target), sensors=[4])
    assert out.loc[0, "baseline"] == 500  # mean of 400 and 600; the 9999 is ignored
    assert out.loc[0, "baseline_weeks"] == 2


def test_score_wape():
    df = pd.DataFrame({"count": [100, 300], "pred": [110, 270]})
    s = forecast.score(df, "pred")
    assert s.loc[0, "MAE"] == 20
    assert s.loc[0, "WAPE"] == pytest.approx(40 / 400)


def _tiny_db(days: int = 120):
    """A database with one sensor whose count on each day equals the day number."""
    con = duckdb.connect(":memory:")
    con.execute(db.SCHEMA)
    start = date(2025, 1, 1)
    rows = [(4, start + timedelta(days=d), 9, d) for d in range(days)]
    con.executemany("INSERT INTO counts VALUES (?, ?, ?, ?, 'live')", rows)
    cal = events.build_calendar(start, start + timedelta(days=days), events.REF_DIR)
    db.load_calendar(con, cal)
    db.create_views(con)
    return con, start


def test_features_only_look_back_35_days_or_more():
    con, start = _tiny_db()
    target = start + timedelta(days=100)  # count on this day = 100
    df = forecast.build_dataset(con, str(target), str(target), sensors=[4])
    row = df.iloc[0]
    assert row["count"] == 100
    assert row["lag_35"] == 65  # day 100 - 35
    assert row["lag_42"] == 58
    assert row["baseline"] == (65 + 58 + 51 + 44) / 4
    # nothing newer than 35 days can appear in any past-count feature
    assert max(row[c] for c in ["lag_35", "lag_42", "baseline"]) <= 100 - 35


def test_backtest_never_trains_on_the_test_month():
    con, start = _tiny_db(days=200)
    data = forecast.build_dataset(con, str(start), str(start + timedelta(days=199)), sensors=[4])
    seen = []
    original = forecast.fit_predict

    def spy(train, test, target="count"):
        seen.append((train.date.max(), test.date.min()))
        return pd.Series(0.0, index=test.index)

    forecast.fit_predict = spy
    try:
        forecast.rolling_backtest(data, "2025-05-01", "2025-06-30", train_start=str(start))
    finally:
        forecast.fit_predict = original
    assert seen and all(last_train < first_test for last_train, first_test in seen)
