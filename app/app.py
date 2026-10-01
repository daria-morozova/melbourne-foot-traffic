"""Melbourne CBD foot traffic dashboard.

Run locally:   uv run streamlit run app/app.py
Online:        Streamlit Community Cloud, pointing at this file.

Uses data/foot_traffic.duckdb if it exists (local), otherwise downloads the
latest database from the GitHub release that the monthly workflow updates.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))  # so the app runs without installing the package

from melbourne_foot_traffic import analysis, config, db, events, forecast, sources  # noqa: E402

REPO = "limpokaya/melbourne-foot-traffic"  # update if the GitHub username changes
DB_URL = f"https://github.com/{REPO}/releases/download/data-latest/foot_traffic.duckdb"
TRAIN_START = "2024-12-01"
MELBOURNE = ZoneInfo(config.LOCAL_TZ)

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK2, MUTED, GRID = "#52514e", "#898781", "#e1e0d9"

st.set_page_config(page_title="Melbourne CBD foot traffic", page_icon="🚶", layout="wide")


# --- Data and model (cached) -----------------------------------------------------


@st.cache_resource(ttl=timedelta(hours=24), show_spinner="Loading the database…")
def get_connection() -> duckdb.DuckDBPyConnection:
    """Open a private copy of the database, adding the calendar table if it's missing."""
    path = Path(tempfile.gettempdir()) / "foot_traffic_app.duckdb"
    if config.DB_PATH.exists():
        shutil.copy(config.DB_PATH, path)
    else:
        urllib.request.urlretrieve(DB_URL, path)
    con = duckdb.connect(str(path))
    tables = {r[0] for r in con.sql("SHOW TABLES").fetchall()}
    if "calendar" not in tables:
        today = datetime.now(MELBOURNE).date()
        db.load_calendar(con, events.build_calendar(datetime(2009, 1, 1).date(), today + timedelta(days=90)))
    db.create_views(con)
    return con


@st.cache_resource(ttl=timedelta(hours=24), show_spinner="Training the forecast model (about a minute)…")
def get_model():
    con = get_connection().cursor()
    last = con.sql("SELECT max(date) FROM counts").fetchone()[0]
    train = forecast.build_dataset(con, TRAIN_START, str(last))
    return forecast.fit(train), last


@st.cache_data(ttl=timedelta(hours=3), show_spinner=False)
def get_weather(day) -> tuple[pd.DataFrame, str]:
    try:
        hourly = sources.fetch_weather_forecast(days=3)
        wx = forecast.weather_for_model(hourly)
        wx = wx[wx.date == day]
        if len(wx) >= 20:
            return wx, "Open-Meteo forecast"
    except Exception:
        pass
    return forecast.typical_weather(get_connection().cursor(), [day]), "typical weather for this time of year (forecast unavailable)"


@st.cache_data(ttl=timedelta(hours=24), show_spinner=False)
def sensor_list() -> pd.DataFrame:
    con = get_connection().cursor()
    ids = ",".join(map(str, config.CBD_SENSORS))
    return con.sql(f"""
        SELECT location_id AS sensor_id, sensor_description AS name
        FROM sensors WHERE location_id IN ({ids}) ORDER BY name
    """).df()


@st.cache_data(ttl=timedelta(hours=24), show_spinner=False)
def daily_history(sensor_id: int) -> pd.DataFrame:
    con = get_connection().cursor()
    d = con.sql(f"""
        SELECT date, sum(count) AS people FROM counts
        WHERE sensor_id = {sensor_id} GROUP BY date HAVING count(*) = 24 ORDER BY date
    """).df()
    d["date"] = pd.to_datetime(d["date"])
    # weekly average, reindexed so gaps in the data stay gaps on the chart
    return d.set_index("date").people.resample("W").mean().to_frame()


@st.cache_data(ttl=timedelta(hours=24), show_spinner="Running the 2019 vs today comparison…")
def weekday_recovery() -> pd.DataFrame:
    con = get_connection().cursor()
    days = analysis.sensor_days(con)
    types = analysis.classify_sensors(days)
    office = types.index[types.type == "office"]
    out = []
    for label, d in [("Office district", days[days.sensor_id.isin(office)]),
                     ("Retail / leisure", days[~days.sensor_id.isin(office)])]:
        r = analysis.by_weekday(analysis.fit_recovery(d)).assign(group=label)
        out.append(r.rename_axis("day").reset_index())
    return pd.concat(out)


def style(fig: go.Figure, height: int = 360) -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=10, r=10, t=30, b=10),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color=INK2), hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    fig.update_xaxes(showgrid=False, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, rangemode="tozero")
    return fig


# --- Page ------------------------------------------------------------------------

st.title("Melbourne CBD foot traffic")
st.caption(
    "Hourly pedestrian counts from City of Melbourne sensors, a day-ahead forecast, "
    "and how the working week has changed since 2019."
)

sensors = sensor_list()
default = int((sensors.name == "Town Hall (West)").idxmax())
choice = st.selectbox("Sensor", sensors.name, index=default)
sensor_id = int(sensors.loc[sensors.name == choice, "sensor_id"].iloc[0])

# --- Tomorrow's forecast
tomorrow = datetime.now(MELBOURNE).date() + timedelta(days=1)
model, last_data = get_model()
wx, wx_source = get_weather(tomorrow)
con = get_connection().cursor()
rows = forecast.build_dataset(con, str(tomorrow), str(tomorrow), sensors=[sensor_id], future=True, weather=wx)
rows["forecast"] = forecast.predict(model, rows)

st.subheader(f"Tomorrow: {tomorrow:%A %d %B %Y}")
total, typical = rows.forecast.sum(), rows.baseline.sum()
holiday = con.sql(f"SELECT holiday_name FROM calendar WHERE date = '{tomorrow}'").fetchone()
c1, c2, c3 = st.columns(3)
c1.metric("Forecast, whole day", f"{total:,.0f} people")
if typical > 0:
    c2.metric("vs. a typical recent " + f"{tomorrow:%A}", f"{total / typical - 1:+.0%}")
c3.metric("Weather", f"max {rows.temperature.max():.0f}°C, rain {rows.precipitation_mm.sum():.1f} mm")
if holiday and holiday[0]:
    st.info(f"Tomorrow is a public holiday: {holiday[0]}")

fig = go.Figure()
fig.add_scatter(x=rows.hour, y=rows.baseline, name=f"Typical {tomorrow:%A} (5–8 weeks ago)",
                line=dict(color=MUTED, width=2, dash="dot"), hovertemplate="%{y:,.0f}")
fig.add_scatter(x=rows.hour, y=rows.forecast, name="Forecast",
                line=dict(color=BLUE, width=2), hovertemplate="%{y:,.0f}")
fig.update_xaxes(title="Hour of day", tickvals=[0, 6, 12, 18, 23], ticktext=["0", "6am", "noon", "6pm", "23"])
fig.update_yaxes(title="People per hour")
st.plotly_chart(style(fig), width="stretch")
st.caption(
    f"Weather: {wx_source}. The model only uses counts at least 35 days old, because the council "
    f"publishes data monthly (latest data: {last_data:%d %b %Y}). Tested on Oct 2025 – Sep 2026, "
    "it is off by 14.6% of traffic on average, vs 19.4% for the 'typical day' rule."
)

# --- History
st.subheader("History")
hist = daily_history(sensor_id)
fig = go.Figure()
fig.add_scatter(x=hist.index, y=hist.people, line=dict(color=BLUE, width=1.5),
                name="Weekly average of daily totals", hovertemplate="%{y:,.0f}")
fig.add_vrect(x0="2020-03-30", x1="2021-10-22", fillcolor=GRID, opacity=0.5, line_width=0,
              annotation_text="lockdowns", annotation_position="top left")
fig.update_yaxes(title="People per day")
st.plotly_chart(style(fig, 320), width="stretch")
st.caption("Gaps: Sep 2010 (faulty timestamps), Nov 2022 – Sep 2024 (not published by the council).")

# --- The finding
st.subheader("Has the CBD recovered?")
st.markdown(
    "Weekends are back to 2019 levels. Weekdays are not, and in the **office district** "
    "Mondays and Fridays lag furthest behind: the pattern of hybrid work."
)
rec = weekday_recovery()
fig = go.Figure()
for group, colour in [("Office district", BLUE), ("Retail / leisure", AQUA)]:
    r = rec[rec.group == group]
    fig.add_scatter(
        x=r.day, y=r.ratio * 100, mode="markers+lines", name=group,
        line=dict(color=colour, width=2), marker=dict(size=9),
        error_y=dict(type="data", symmetric=False, array=(r.high - r.ratio) * 100,
                     arrayminus=(r.ratio - r.low) * 100, color=colour, thickness=1.5, width=0),
        hovertemplate="%{y:.0f}% of 2019",
    )
fig.add_hline(y=100, line=dict(color=MUTED, width=1, dash="dash"))
fig.update_yaxes(title="% of 2019 level", range=[50, 112])
st.plotly_chart(style(fig, 340), width="stretch")
st.caption(
    "Oct 2024 – Sep 2026 vs 2019, same 18 sensors, holidays excluded. Bars show 95% intervals "
    "from a regression with sensor and month controls. Office-district sensors are those where "
    "2019 weekday traffic was 30%+ above weekend traffic."
)

st.divider()
st.caption(
    f"Data: City of Melbourne Pedestrian Counting System; weather: Open-Meteo. "
    f"Code: github.com/{REPO}"
)
