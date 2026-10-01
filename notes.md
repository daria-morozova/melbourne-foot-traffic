# Notes

## Direction check (one line per phase)

- Phase 0 (setup): quick and easy, but the GitHub username limit was annoying.
- Phase 1 (pipeline): enjoyed … / dragged …
- Phase 2 (explore): enjoyed … / dragged …
- Phase 3 (forecast): enjoyed … / dragged …
- Phase 4 (analysis): enjoyed … / dragged …
- Phase 5 (communicate): enjoyed … / dragged …

## Results

- **Pipeline:** 6.2M hourly counts (2009–2026) + hourly weather in DuckDB, updated
  monthly by GitHub Actions; database published as the `data-latest` release.
- **Forecast:** LightGBM cuts error by 25% vs the seasonal baseline
  (WAPE 19.4% → 14.6%, Oct 2025 – Sep 2026 rolling monthly test). Better at all
  18 sensors; holidays 37% → 24%. Fails mostly on 41–43°C days and heavy rain
  (still over-predicts by ~30%).
- **Analysis:** office-district Friday traffic is 36% below 2019, Monday 35%,
  Wednesday 29%, Thursday 26%; weekends 100%. Mon/Fri morning commute (7–10am) a
  further 17% (95% CI 15–19%) below mid-week. Same in 2024–25 and 2025–26. Gap at
  17 of 18 sensors; same for upgraded and non-upgraded sensors. Retail/leisure:
  no whole-day Mon/Fri gap, Friday best-recovered weekday (85%).
- **Dashboard:** https://melbourne-foot-traffic.streamlit.app/

## Data notes

### Sources
- Counts 2009 – Oct 2022: council archive ZIP (old format: Sensor_ID, Date_Time, Hourly_Counts).
- Counts Oct 2024 onwards: council live table (new format: location_id, sensing_date, hourday, pedestriancount).
- Sensor IDs match across both formats (e.g. 4 = Town Hall (West) in both).
- Weather: Open-Meteo hourly, fetched in UTC and converted to Melbourne time.
- Calendar: Victorian public holidays (`holidays` package); school terms and events
  in data/reference/ (with sources).

### Gaps and quality issues
- Nov 2022 – Sep 2024: not publicly available. The live table keeps a rolling
  two-year window, and the archive ends on 31 Oct 2022 (despite its file name
  saying 14 Dec). The DataVic copy is only a 99-row sample.
- Because of the rolling window, the database is now the only copy of older live
  data. Don't run --rebuild without a backup (the GitHub release holds one).
- Sep 2010: every hour in the archive is stamped as midnight (24 conflicting rows
  per sensor per day), so all 510 sensor-hours were dropped.
- No row ≠ zero. A missing hour means no record; count = 0 means nobody passed.
- Sensors 52 and 19 sometimes report whole days of zeros, likely faults. Treated as missing.

### Sensor selection (Phase 2)
- 18 CBD sensors, each with ≥ 90% of hours present in 2019 and in Oct 2024 – Sep 2026:
  2, 3, 4, 5, 17, 18, 19, 20, 21, 23, 24, 30, 36, 40, 52, 53, 56, 58.
- Excluded 6 (Flinders St underpass: several step changes, now described as
  "Myki Barriers") and 47 (moved to 250 Elizabeth St).
- Office-district sensors (2019 weekday ≥ 1.3 × weekend): 17, 18, 23, 24, 36, 40, 53, 58.
- Many sensors had a "Pushbox Upgrade" in Jul–Aug 2023, inside the data gap.
  Upgraded and non-upgraded sensors show the same results, so the upgrade
  probably didn't shift counts much.

### Exploration findings (Phase 2)
- CBD traffic is ~85% of 2019. It fell to 10–40% during the lockdowns.
- Rain: −4% for light rain, −18% for 3+ mm in an hour.
- Heat: −8% at 30–35°C, −22% at 35°C+. Cold has little effect.

## Possible next steps
- Rewrite docs/writeup.md in my own voice and post it.
- Ask the council for Nov 2022 – Sep 2024 counts (contact form on the data portal).
- Forecast: a "heatwave" feature, or more summers of data, for the 41°C+ days.
- Option B: add the live "past hour" dataset for a true next-day forecast.
- University semester dates as a feature (students are a big part of CBD traffic).
