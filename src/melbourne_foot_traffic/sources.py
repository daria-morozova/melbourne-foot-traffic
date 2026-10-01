"""Download raw data from the City of Melbourne portal and Open-Meteo.

Every function here only fetches and saves; cleaning happens in db.py.
"""

from __future__ import annotations

import shutil
import time
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import config

# (connect, read) timeouts in seconds. Council exports can take minutes to
# start streaming; Open-Meteo normally answers in a second or two.
EXPORT_TIMEOUT = (30, 300)
WEATHER_TIMEOUT = (30, 90)


def _make_session() -> requests.Session:
    """A session that retries dropped connections and busy servers.

    Waits 2s, 4s, 8s, 16s, 32s between attempts, so a brief network hiccup
    or a '429 Too Many Requests' doesn't kill a whole run.
    """
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers["User-Agent"] = "melbourne-foot-traffic (portfolio project)"
    return session


SESSION = _make_session()


def _download(url: str, dest: Path, params: dict | None = None) -> Path:
    """Stream a URL to a file, so large exports never sit in memory."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with SESSION.get(url, params=params, stream=True, timeout=EXPORT_TIMEOUT) as r:
        if r.status_code != 200:
            raise RuntimeError(
                f"Download failed ({r.status_code}) for {r.url}\n{r.text[:500]}"
            )
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    tmp.replace(dest)
    print(f"  saved {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")
    return dest


# --- Pedestrian counts -------------------------------------------------------


def fetch_live_counts(since: date | None) -> Path:
    """Counts from the portal's main table, optionally only from `since` onwards."""
    url = f"{config.COM_API}/catalog/datasets/{config.COUNTS_DATASET}/exports/csv"
    params = {
        "delimiter": ",",
        "select": "location_id, sensing_date, hourday, pedestriancount",
    }
    if since is not None:
        params["where"] = f"sensing_date >= date'{since.isoformat()}'"
    label = since.isoformat() if since else "all"
    print(f"Fetching live counts (from {label})...")
    return _download(url, config.RAW_DIR / f"counts_live_{label}.csv", params)


def _is_data_csv(name: str) -> bool:
    """True for real CSVs; False for the hidden '._' files Macs add to ZIPs."""
    return (
        name.lower().endswith(".csv")
        and "__MACOSX" not in name
        and not Path(name).name.startswith("._")
    )


def fetch_historic_counts() -> list[Path]:
    """The 2009-2022 archive ZIP. Downloaded once, then reused from data/raw/."""
    zip_path = config.HISTORIC_ZIP_PATH
    if not zip_path.exists():
        print("Fetching historic counts ZIP (2009-2022, one-off)...")
        try:
            _download(config.HISTORIC_ZIP_URL, zip_path)
        except Exception as e:
            raise RuntimeError(
                f"{e}\n\nCould not download the historic ZIP automatically. "
                "Download it by hand from the 'Attachments' section of the "
                "'Pedestrian Counting System (counts per hour)' page on "
                "data.melbourne.vic.gov.au and save it as "
                f"{zip_path}"
            ) from e

    out_dir = config.RAW_DIR / "counts_historic"
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        for n in zf.namelist():
            if _is_data_csv(n):
                target = out_dir / Path(n).name
                if not target.exists():
                    with zf.open(n) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
    csvs = sorted(p for p in out_dir.glob("*.csv") if _is_data_csv(p.as_posix()))
    if not csvs:
        raise RuntimeError(f"No CSV files found inside {zip_path}")
    return csvs


def fetch_sensors() -> Path:
    """Sensor locations: small, so re-downloaded in full every run."""
    url = f"{config.COM_API}/catalog/datasets/{config.SENSORS_DATASET}/exports/csv"
    print("Fetching sensor locations...")
    return _download(url, config.RAW_DIR / "sensors.csv", {"delimiter": ","})


# --- Weather -------------------------------------------------------------------


def weather_json_to_frame(payload: dict) -> pd.DataFrame:
    """Turn an Open-Meteo response (requested in UTC) into a tidy table.

    Adds local Melbourne date and hour so it can be joined to the counts,
    which are recorded in local time.
    """
    hourly = payload["hourly"]
    df = pd.DataFrame(hourly)
    ts_utc = pd.to_datetime(df.pop("time"), utc=True)
    ts_local = ts_utc.dt.tz_convert(config.LOCAL_TZ)
    df.insert(0, "ts_utc", ts_utc.dt.tz_localize(None))
    df.insert(1, "date", ts_local.dt.date)
    df.insert(2, "hour", ts_local.dt.hour.astype("int8"))
    return df


def fetch_weather(start: date, end: date) -> pd.DataFrame:
    """Hourly CBD weather between two dates, one request per calendar year."""
    frames = []
    year_start = start
    while year_start <= end:
        year_end = min(date(year_start.year, 12, 31), end)
        print(f"Fetching weather {year_start} to {year_end}...")
        r = SESSION.get(
            config.WEATHER_API,
            params={
                "latitude": config.CBD_LAT,
                "longitude": config.CBD_LON,
                "start_date": year_start.isoformat(),
                "end_date": year_end.isoformat(),
                "hourly": ",".join(config.WEATHER_VARS),
                "timezone": "GMT",  # fetch in UTC, convert ourselves (DST-safe)
            },
            timeout=WEATHER_TIMEOUT,
        )
        if r.status_code != 200:
            raise RuntimeError(f"Open-Meteo error {r.status_code}: {r.text[:500]}")
        frames.append(weather_json_to_frame(r.json()))
        year_start = year_end + timedelta(days=1)
        time.sleep(1)  # be polite to a free service
    return pd.concat(frames, ignore_index=True)


WEATHER_FORECAST_API = "https://api.open-meteo.com/v1/forecast"


def fetch_weather_forecast(days: int = 3) -> pd.DataFrame:
    """Hourly CBD weather forecast for the next few days (same columns as fetch_weather)."""
    r = SESSION.get(
        WEATHER_FORECAST_API,
        params={
            "latitude": config.CBD_LAT,
            "longitude": config.CBD_LON,
            "hourly": ",".join(config.WEATHER_VARS),
            "timezone": "GMT",
            "forecast_days": days,
        },
        timeout=WEATHER_TIMEOUT,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Open-Meteo forecast error {r.status_code}: {r.text[:500]}")
    return weather_json_to_frame(r.json())
