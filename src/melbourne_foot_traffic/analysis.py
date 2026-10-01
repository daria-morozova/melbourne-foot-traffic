"""Phase 4: has the CBD recovered, and has the working week changed shape?

Compares 2019 with Oct 2024 - Sep 2026 (two full recent years), using the
same CBD sensors, whole days only, public holidays and faulty sensor-days
removed.

Model, per sensor-day:
    log(count) = sensor + month + weekday + period + weekday x period

Because the outcome is logged, exp(coefficient) is a ratio: "recent traffic
on Fridays is 0.75 x its 2019 level". Sensor and month terms make sure we
compare like with like (same sensors, same time of year). Standard errors are
clustered by week, since sensors on the same day (and days in the same week)
move together.
"""

from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats

from . import config

RECENT = ("2024-10-01", "2026-09-30")
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
WINDOWS = {  # hours (inclusive)
    "daily": (0, 23),
    "am_peak": (7, 9),
    "lunch": (12, 13),
    "pm_peak": (16, 18),
    "evening": (19, 23),
}
DAY_GROUPS = {
    "Mon + Fri": {"Mon": 0.5, "Fri": 0.5},
    "Tue–Thu": {"Tue": 1 / 3, "Wed": 1 / 3, "Thu": 1 / 3},
    "Weekend": {"Sat": 0.5, "Sun": 0.5},
}
# Sensors whose 2019 weekday traffic was 30%+ above weekend traffic are
# classed as office-district (commuter) sensors; the rest as retail/leisure.
OFFICE_THRESHOLD = 1.3


def sensor_days(con: duckdb.DuckDBPyConnection, sensors: list[int] | None = None) -> pd.DataFrame:
    """One row per sensor per day, with totals for each time window."""
    ids = ",".join(map(str, sensors or config.CBD_SENSORS))
    windows = ",\n".join(
        f"sum(c.count) FILTER (WHERE c.hour BETWEEN {a} AND {b}) AS {name}"
        for name, (a, b) in WINDOWS.items()
    )
    d = con.sql(f"""
        WITH faults AS (
            SELECT sensor_id, date FROM counts WHERE hour BETWEEN 8 AND 20
            GROUP BY ALL HAVING count(*) >= 10 AND max(count) = 0
        )
        SELECT c.sensor_id, c.date, {windows},
               CASE WHEN year(c.date) = 2019 THEN '2019' ELSE 'recent' END AS period
        FROM counts c
        ANTI JOIN faults f USING (sensor_id, date)
        JOIN calendar cal ON cal.date = c.date
        WHERE c.sensor_id IN ({ids})
          AND (year(c.date) = 2019 OR c.date BETWEEN '{RECENT[0]}' AND '{RECENT[1]}')
          AND NOT cal.is_holiday
        GROUP BY ALL
        HAVING count(*) = 24          -- whole days only
    """).df()
    d["date"] = pd.to_datetime(d["date"])
    d["dow"] = d["date"].dt.day_name().str[:3]
    d["month"] = d["date"].dt.month
    d["week"] = d["date"].dt.strftime("%G-%V")
    d["sensor"] = d["sensor_id"].astype(str)
    return d


def classify_sensors(days: pd.DataFrame) -> pd.DataFrame:
    """2019 weekday-to-weekend ratio per sensor, and its office/retail class."""
    d19 = days[days.period == "2019"].assign(weekend=lambda x: x.dow.isin(["Sat", "Sun"]))
    m = d19.groupby(["sensor_id", "weekend"])["daily"].mean().unstack()
    out = pd.DataFrame({"weekday_vs_weekend_2019": m[False] / m[True]})
    out["type"] = np.where(out.weekday_vs_weekend_2019 >= OFFICE_THRESHOLD, "office", "retail/leisure")
    return out.sort_values("weekday_vs_weekend_2019")


def fit_recovery(days: pd.DataFrame, window: str = "daily"):
    """Fit the log model for one time window. Returns a statsmodels result."""
    d = days[days[window] > 0]
    return smf.ols(
        f"np.log({window}) ~ C(sensor) + C(month) + C(dow, Treatment('Wed')) * C(period)", data=d
    ).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d["week"])[0]})


def _contrast(result, weights: dict[str, float]) -> tuple[float, float]:
    """Weighted sum of 'recent vs 2019' log-effects for the given weekdays, and its SE."""
    b, V = result.params, result.cov_params()
    vec = pd.Series(0.0, index=b.index)
    for day, w in weights.items():
        vec["C(period)[T.recent]"] += w
        if day != "Wed":
            vec[f"C(dow, Treatment('Wed'))[T.{day}]:C(period)[T.recent]"] += w
    return float(vec @ b), float(np.sqrt(vec @ V @ vec))


def recovery(result, weights: dict[str, float]) -> dict[str, float]:
    """Recent level as a share of 2019 (e.g. 0.75), with a 95% interval."""
    est, se = _contrast(result, weights)
    return {"ratio": np.exp(est), "low": np.exp(est - 1.96 * se), "high": np.exp(est + 1.96 * se)}


def by_weekday(result) -> pd.DataFrame:
    return pd.DataFrame({d: recovery(result, {d: 1.0}) for d in WEEKDAYS}).T


def monfri_gap(result) -> dict[str, float]:
    """How much further Mon+Fri are below 2019 than Tue-Thu (e.g. -0.11 = 11% further)."""
    w = {**DAY_GROUPS["Mon + Fri"], **{k: -v for k, v in DAY_GROUPS["Tue–Thu"].items()}}
    est, se = _contrast(result, w)
    return {
        "gap": np.exp(est) - 1,
        "low": np.exp(est - 1.96 * se) - 1,
        "high": np.exp(est + 1.96 * se) - 1,
        "p": float(2 * stats.norm.sf(abs(est / se))),
    }
