"""Forecasting set-up shared by the baseline and the model.

Option A (chosen in Phase 3): the council publishes counts once a month, so when
forecasting tomorrow the newest count we could actually have is about 5 weeks
old. Every feature built from past counts must respect that, or the test scores
would be better than anything achievable in real use (leakage).
"""

from __future__ import annotations

import duckdb
import pandas as pd

from . import config

# The newest count usable for a forecast is this many days before the target day.
MIN_LAG_DAYS = 35
# Baseline: same sensor, same hour, same weekday, 5-8 weeks earlier, averaged.
BASELINE_LAGS = [35, 42, 49, 56]


def seasonal_baseline(
    con: duckdb.DuckDBPyConnection,
    start: str,
    end: str,
    sensors: list[int] | None = None,
) -> pd.DataFrame:
    """Actual counts between `start` and `end` with the seasonal-naive baseline.

    baseline = average count for the same sensor, weekday and hour, 5, 6, 7 and
    8 weeks before. Rows where none of those four weeks has data get NaN.
    """
    sensors = sensors or config.CBD_SENSORS
    assert min(BASELINE_LAGS) >= MIN_LAG_DAYS, "baseline would use counts not yet published"
    ids = ",".join(map(str, sensors))
    lags = ",".join(map(str, BASELINE_LAGS))
    return con.sql(f"""
        WITH target AS (
            SELECT sensor_id, date, hour, count
            FROM counts
            WHERE sensor_id IN ({ids}) AND date BETWEEN '{start}' AND '{end}'
        ),
        lagged AS (
            SELECT t.sensor_id, t.date, t.hour, past.count AS past_count
            FROM target t
            CROSS JOIN (SELECT unnest([{lags}]) AS lag) l
            JOIN counts past
              ON past.sensor_id = t.sensor_id
             AND past.hour = t.hour
             AND past.date = t.date - l.lag
        )
        SELECT t.*, avg(l.past_count) AS baseline, count(l.past_count) AS baseline_weeks
        FROM target t
        LEFT JOIN lagged l USING (sensor_id, date, hour)
        GROUP BY ALL
        ORDER BY t.sensor_id, t.date, t.hour
    """).df()


def score(df: pd.DataFrame, pred: str, by: str | list[str] | None = None) -> pd.DataFrame:
    """MAE (people per hour) and WAPE (MAE as a share of the average count).

    WAPE makes busy and quiet sensors comparable: 0.20 means the forecast is
    off by 20% of a typical hour's traffic.
    """
    d = df.dropna(subset=[pred, "count"]).assign(abs_err=lambda x: (x[pred] - x["count"]).abs())
    if by is None:
        return pd.DataFrame(
            {"MAE": [d.abs_err.mean()], "WAPE": [d.abs_err.sum() / d["count"].sum()], "hours": [len(d)]}
        )
    g = d.groupby(by)
    return pd.DataFrame(
        {"MAE": g.abs_err.mean(), "WAPE": g.abs_err.sum() / g["count"].sum(), "hours": g.size()}
    )
