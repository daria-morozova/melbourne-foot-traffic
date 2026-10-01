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


# --- Model ---------------------------------------------------------------------

YEAR_LAG = 364  # same weekday a year earlier (52 weeks)
WEATHER_FEATURES = [
    "temperature", "apparent_temperature", "precipitation_mm", "rain_mm",
    "humidity", "cloud_cover", "wind_speed",
]
CALENDAR_FEATURES = [
    "is_holiday", "day_before_holiday", "day_after_holiday", "school_term",
    "event_australian_open", "event_grand_prix", "event_moomba",
    "event_lunar_new_year", "event_afl_grand_final", "event_new_years_eve",
]
TIME_FEATURES = ["hour", "dow", "month", "doy"]
COUNT_FEATURES = ["baseline", "lag_35", "lag_42", "lag_364"]
SEASON_FEATURES = ["season", "season_change"]
FEATURES = (
    ["sensor_id"] + TIME_FEATURES + CALENDAR_FEATURES + WEATHER_FEATURES
    + COUNT_FEATURES + SEASON_FEATURES
)
SEASON_YEARS = (2014, 2019)  # pre-COVID years used to learn the yearly rhythm


def seasonal_index(con: duckdb.DuckDBPyConnection, sensors: list[int] | None = None) -> pd.Series:
    """Typical traffic level for each day of the year, from 2014-2019.

    1.0 = an average day for that sensor and year; 1.10 = 10% busier. Averaged
    over sensors and years, then smoothed over 7 days so weekdays even out.
    Example: early January ~0.82-0.91 (holidays), mid-December ~1.10 (shopping).
    """
    sensors = sensors or config.CBD_SENSORS
    ids = ",".join(map(str, sensors))
    s = con.sql(f"""
        SELECT doy, avg(rel) AS season FROM (
            SELECT sensor_id, date, dayofyear(date) AS doy,
                   sum(count) / avg(sum(count)) OVER (PARTITION BY sensor_id, year(date)) AS rel
            FROM counts
            WHERE year(date) BETWEEN {SEASON_YEARS[0]} AND {SEASON_YEARS[1]}
              AND sensor_id IN ({ids})
            GROUP BY sensor_id, date HAVING count(*) = 24
        ) GROUP BY doy
    """).df().set_index("doy")["season"]
    s = s.reindex(range(1, 367)).interpolate()
    wrapped = pd.concat([s.iloc[-10:], s, s.iloc[:10]])  # year wraps around
    smooth = wrapped.rolling(7, center=True).mean().iloc[10:-10]
    return pd.Series(smooth.values, index=range(1, 367), name="season")


def add_season_features(df: pd.DataFrame, season: pd.Series) -> pd.DataFrame:
    """season: typical level for this day of year.
    season_change: typical level now vs. the baseline's weeks (5-8 weeks earlier).
    E.g. mid-December vs late October ~ +10%: the baseline is likely too low.
    """
    doy = df["doy"].to_numpy()
    now = season.reindex(doy).to_numpy()
    past = sum(
        season.reindex(((doy - lag - 1) % 365) + 1).to_numpy() for lag in BASELINE_LAGS
    ) / len(BASELINE_LAGS)
    return df.assign(season=now, season_change=now / past)


def build_dataset(
    con: duckdb.DuckDBPyConnection,
    start: str,
    end: str,
    sensors: list[int] | None = None,
) -> pd.DataFrame:
    """One row per sensor-hour with every feature the model may use.

    Past-count features only look back 35 days or more (option A).
    Sensor-days that look like faults (zero for every daytime hour) are
    removed, both as targets and as history.
    """
    sensors = sensors or config.CBD_SENSORS
    ids = ",".join(map(str, sensors))
    lags = sorted(set(BASELINE_LAGS + [YEAR_LAG]))
    assert min(lags) >= MIN_LAG_DAYS
    base_lags = ",".join(map(str, BASELINE_LAGS))
    df = con.sql(f"""
        WITH faults AS (
            SELECT sensor_id, date FROM counts
            WHERE hour BETWEEN 8 AND 20
            GROUP BY ALL HAVING count(*) >= 10 AND max(count) = 0
        ),
        clean AS (
            SELECT c.sensor_id, c.date, c.hour, c.count
            FROM counts c ANTI JOIN faults f USING (sensor_id, date)
            WHERE c.sensor_id IN ({ids})
        ),
        target AS (SELECT * FROM clean WHERE date BETWEEN '{start}' AND '{end}'),
        lagged AS (
            SELECT t.sensor_id, t.date, t.hour, l.lag, p.count AS past
            FROM target t
            CROSS JOIN (SELECT unnest([{",".join(map(str, lags))}]) AS lag) l
            JOIN clean p ON p.sensor_id = t.sensor_id AND p.hour = t.hour
                        AND p.date = t.date - l.lag
        ),
        lag_features AS (
            SELECT sensor_id, date, hour,
                   avg(past) FILTER (WHERE lag IN ({base_lags})) AS baseline,
                   max(past) FILTER (WHERE lag = 35)  AS lag_35,
                   max(past) FILTER (WHERE lag = 42)  AS lag_42,
                   max(past) FILTER (WHERE lag = {YEAR_LAG}) AS lag_364
            FROM lagged GROUP BY ALL
        ),
        cal AS (
            SELECT *,
                   coalesce(lead(is_holiday) OVER (ORDER BY date), false) AS day_before_holiday,
                   coalesce(lag(is_holiday)  OVER (ORDER BY date), false) AS day_after_holiday
            FROM calendar
        )
        SELECT t.sensor_id, t.date, t.hour, t.count,
               dayofweek(t.date) AS dow, month(t.date) AS month, dayofyear(t.date) AS doy,
               {", ".join("cal." + c for c in CALENDAR_FEATURES)},
               {", ".join("w." + c for c in WEATHER_FEATURES)},
               lf.baseline, lf.lag_35, lf.lag_42, lf.lag_364
        FROM target t
        LEFT JOIN lag_features lf USING (sensor_id, date, hour)
        LEFT JOIN cal ON cal.date = t.date
        LEFT JOIN weather w ON w.date = t.date AND w.hour = t.hour
        ORDER BY t.date, t.sensor_id, t.hour
    """).df()
    df["date"] = pd.to_datetime(df["date"])
    df["sensor_id"] = pd.Categorical(df["sensor_id"], categories=sorted(sensors))
    for c in CALENDAR_FEATURES:
        df[c] = df[c].astype("float")  # booleans (with unknowns) -> 1/0/NaN
    return add_season_features(df, seasonal_index(con, sensors))


MODEL_PARAMS = dict(
    n_estimators=600, learning_rate=0.05, num_leaves=63, min_child_samples=50,
    subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1, random_state=42,
)


def fit_predict(train: pd.DataFrame, test: pd.DataFrame, target: str = "count") -> pd.Series:
    """Train LightGBM on `train` and return predicted counts for `test`.

    target="ratio":  learn count / baseline (how unusual the hour is), with each
                     row weighted by its baseline so the loss equals the error in
                     people. Falls back to the baseline where none exists.
    target="count":  learn the count directly (L1 loss = mean absolute error).
    """
    import lightgbm as lgb

    if target == "ratio":
        tr = train[train.baseline > 0]
        model = lgb.LGBMRegressor(objective="l1", **MODEL_PARAMS)
        model.fit(tr[FEATURES], tr["count"] / tr.baseline, sample_weight=tr.baseline)
        pred = model.predict(test[FEATURES]) * test.baseline
        pred = pd.Series(pred, index=test.index).where(test.baseline > 0, test.baseline)
    elif target == "count":
        model = lgb.LGBMRegressor(objective="l1", **MODEL_PARAMS)
        model.fit(train[FEATURES], train["count"])
        pred = pd.Series(model.predict(test[FEATURES]), index=test.index)
    else:
        raise ValueError(target)
    fit_predict.last_model = model  # kept for feature importance
    return pred.clip(lower=0)


def rolling_backtest(
    data: pd.DataFrame, test_start: str, test_end: str, train_start: str, target: str = "count"
) -> pd.DataFrame:
    """Re-train before each test month on everything up to that month, then predict it.

    Mirrors real use: the model for November has only seen data up to October.
    """
    out = []
    for month_start in pd.date_range(test_start, test_end, freq="MS"):
        month_end = month_start + pd.offsets.MonthEnd(0)
        train = data[(data.date >= train_start) & (data.date < month_start)]
        test = data[(data.date >= month_start) & (data.date <= month_end)].copy()
        if test.empty:
            continue
        test["model"] = fit_predict(train, test, target)
        test["train_rows"] = len(train)
        out.append(test)
    return pd.concat(out, ignore_index=True)
