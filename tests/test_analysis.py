"""Check the Phase 4 model recovers known ratios from made-up data. Run: uv run pytest"""

import numpy as np
import pandas as pd
import pytest

from melbourne_foot_traffic import analysis as A


@pytest.fixture
def fake_days():
    """Two sensors; recent traffic is 80% of 2019 on most days, 60% on Mon/Fri."""
    rng = np.random.default_rng(0)
    rows = []
    for period, dates in [("2019", pd.date_range("2019-01-01", "2019-12-31")),
                          ("recent", pd.date_range("2025-01-01", "2025-12-31"))]:
        for sensor, level in [(1, 1000), (2, 300)]:
            for d in dates:
                dow = d.day_name()[:3]
                factor = 1.0 if period == "2019" else (0.6 if dow in ("Mon", "Fri") else 0.8)
                rows.append({"sensor_id": sensor, "sensor": str(sensor), "date": d, "period": period,
                             "dow": dow, "month": d.month, "week": d.strftime("%G-%V"),
                             "daily": level * factor * rng.lognormal(0, 0.05)})
    return pd.DataFrame(rows)


def test_recovers_known_weekday_ratios(fake_days):
    r = A.by_weekday(A.fit_recovery(fake_days))
    assert r.loc["Wed", "ratio"] == pytest.approx(0.8, abs=0.02)
    assert r.loc["Fri", "ratio"] == pytest.approx(0.6, abs=0.02)
    assert (r.low <= r.ratio).all() and (r.ratio <= r.high).all()


def test_monfri_gap(fake_days):
    g = A.monfri_gap(A.fit_recovery(fake_days))
    assert g["gap"] == pytest.approx(0.6 / 0.8 - 1, abs=0.02)  # -25%
    assert g["high"] < 0 and g["p"] < 0.001
