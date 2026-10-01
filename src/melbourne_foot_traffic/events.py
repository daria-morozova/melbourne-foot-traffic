"""Calendar features: public holidays, school terms and major events, one row per day.

Public holidays come from the `holidays` package (Victoria). School terms and
events come from the hand-made CSVs in data/reference/, which list their sources.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import holidays
import pandas as pd

from . import config

REF_DIR = config.DATA_DIR / "reference"


def build_calendar(start: date, end: date, ref_dir: Path | None = None) -> pd.DataFrame:
    """One row per day with holiday, school-term and event flags.

    `school_term` is left empty (NA) for years not covered by school_terms.csv,
    so an unknown is never mistaken for "holidays".
    """
    ref_dir = ref_dir or REF_DIR
    days = pd.date_range(start, end, freq="D")
    cal = pd.DataFrame({"date": days.date})

    vic = holidays.Australia(subdiv="VIC", years=range(start.year, end.year + 1))
    cal["holiday_name"] = [vic.get(d) for d in cal["date"]]
    cal["is_holiday"] = cal["holiday_name"].notna()

    terms = pd.read_csv(ref_dir / "school_terms.csv", parse_dates=["start", "end"])
    in_term = pd.Series(False, index=days)
    for t in terms.itertuples():
        in_term |= (days >= t.start) & (days <= t.end)
    known_years = set(terms["year"])
    cal["school_term"] = pd.array(
        [bool(v) if d.year in known_years else pd.NA for d, v in zip(days, in_term)],
        dtype="boolean",
    )

    events = pd.read_csv(ref_dir / "events.csv", parse_dates=["start", "end"])
    for name, rows in events.groupby("event"):
        flag = pd.Series(False, index=days)
        for e in rows.itertuples():
            flag |= (days >= e.start) & (days <= e.end)
        cal[f"event_{name}"] = flag.values

    return cal
