"""Build or update the database in one command.

    uv run melbourne-foot-traffic            # update: fetch only what's new
    uv run melbourne-foot-traffic --rebuild  # delete the database and start over
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

from . import config, db, sources


def run(rebuild: bool = False) -> None:
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    if rebuild and config.DB_PATH.exists():
        print(f"Rebuilding: deleting {config.DB_PATH.name}")
        config.DB_PATH.unlink()

    con = db.connect()
    try:
        # 1. Historic archive (2009-2022): only needed once
        if db.last_or_first(con, "max", "historic") is None:
            db.load_counts(con, sources.fetch_historic_counts(), "historic")
        else:
            print("Historic counts already loaded, skipping")

        # 2. Live counts: everything the first time, then only recent dates
        last = db.last_or_first(con, "max", "live")
        since = last - timedelta(days=config.OVERLAP_DAYS) if last else None
        live_csv = sources.fetch_live_counts(since)
        db.load_counts(con, [live_csv], "live")
        live_csv.unlink()  # raw export no longer needed once loaded
        db.reconcile_sources(con)

        # 3. Sensor locations: small, refreshed every run
        db.load_sensors(con, sources.fetch_sensors())

        # 4. Weather up to a week ago (the archive lags real time)
        last_w = db.last_weather_date(con)
        start = (
            last_w - timedelta(days=2)
            if last_w
            else date.fromisoformat(config.WEATHER_START)
        )
        end = date.today() - timedelta(days=config.WEATHER_LAG_DAYS)
        if start <= end:
            db.upsert_weather(con, sources.fetch_weather(start, end))

        db.create_views(con)
        summarise(con)
    finally:
        con.close()


def summarise(con) -> None:
    print("\nDatabase summary")
    print(
        con.execute(
            """
            SELECT source, count(*) AS rows, count(DISTINCT sensor_id) AS sensors,
                   min(date) AS first_date, max(date) AS last_date
            FROM counts GROUP BY source ORDER BY first_date
            """
        ).df().to_string(index=False)
    )
    w = con.execute("SELECT count(*), min(date), max(date) FROM weather_hourly").fetchone()
    print(f"weather: {w[0]:,} hours, {w[1]} to {w[2]}")
    print(f"saved to {config.DB_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Update the foot traffic database.")
    parser.add_argument(
        "--rebuild", action="store_true", help="delete the database and rebuild it"
    )
    args = parser.parse_args()
    run(rebuild=args.rebuild)


if __name__ == "__main__":
    main()
