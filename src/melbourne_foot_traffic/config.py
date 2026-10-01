"""Settings shared by the whole pipeline: where files live and where data comes from."""

from pathlib import Path

# Project root = two folders up from this file (src/melbourne_foot_traffic/config.py)
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
DB_PATH = DATA_DIR / "foot_traffic.duckdb"

# City of Melbourne open data portal (Opendatasoft, API v2.1)
COM_API = "https://data.melbourne.vic.gov.au/api/explore/v2.1"
COUNTS_DATASET = "pedestrian-counting-system-monthly-counts-per-hour"
SENSORS_DATASET = "pedestrian-counting-system-sensor-locations"

# Older counts (May 2009 - 14 Dec 2022) are published as a ZIP attachment
# on the counts dataset rather than in the main table.
HISTORIC_ZIP_URL = (
    "https://data.melbourne.vic.gov.au/api/datasets/1.0/"
    "pedestrian-counting-system-monthly-counts-per-hour/attachments/"
    "pedestrian_counting_system_monthly_counts_per_hour_may_2009_to_14_dec_2022_csv_zip/"
)
HISTORIC_ZIP_PATH = RAW_DIR / "counts_2009_2022.zip"

# Open-Meteo historical weather (no API key needed)
WEATHER_API = "https://archive-api.open-meteo.com/v1/archive"
CBD_LAT, CBD_LON = -37.8136, 144.9631  # Melbourne CBD
WEATHER_VARS = [
    "temperature_2m",
    "apparent_temperature",
    "precipitation",
    "rain",
    "relative_humidity_2m",
    "cloud_cover",
    "wind_speed_10m",
]
WEATHER_START = "2009-05-01"  # first month of pedestrian counts
WEATHER_LAG_DAYS = 7  # the archive runs a few days behind real time

LOCAL_TZ = "Australia/Melbourne"

# CBD sensors chosen in notebooks/01_explore.ipynb: inside the CBD grid, >= 90% of
# hours present in 2019 and Oct 2024 - Sep 2026, not moved or changed.
CBD_SENSORS = [2, 3, 4, 5, 17, 18, 19, 20, 21, 23, 24, 30, 36, 40, 52, 53, 56, 58]

# When updating, re-fetch this many days before the last loaded date,
# in case the council corrected recent data.
OVERLAP_DAYS = 14
