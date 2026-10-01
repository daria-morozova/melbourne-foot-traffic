# Notes

* Phase 0 (setup): quick and easy, but the GitHub username limit was annoying.
* Phase 1 (pipeline): enjoyed … / dragged …
* Phase 2 (explore): enjoyed … / dragged …
* 
* \## Data notes
* 
* \### Sources
* Counts 2009 – Oct 2022: council archive ZIP (old format: Sensor\_ID, Date\_Time, Hourly\_Counts).
* Counts Oct 2024 onwards: council live table (new format: location\_id, sensing\_date, hourday, pedestriancount).
* Sensor IDs match across both formats (e.g. 4 = Town Hall (West) in both).
* Weather: Open-Meteo hourly, fetched in UTC and converted to Melbourne time.
* 
* \### Gaps and quality issues
* Nov 2022 – Sep 2024: not publicly available. The live table keeps a rolling
* &#x20; two-year window, and the archive ends on 31 Oct 2022 (despite its file name
* &#x20; saying 14 Dec). The DataVic copy is only a 99-row sample.
* &#x20; Because of the rolling window, the database is now the only copy of older live
* &#x20; data. Don't run --rebuild without a backup (the GitHub release holds one).
* &#x20; Sep 2010: every hour in the archive is stamped as midnight (24 conflicting rows
* &#x20; per sensor per day), so all 510 sensor-hours were dropped.
* &#x20; No row ≠ zero. A missing hour means no record; count = 0 means nobody passed.
* &#x20; Sensors 52 and 19 sometimes report whole days of zeros, likely faults.
* &#x20; Treat as missing.
* 
* \### Sensor selection (Phase 2)
* &#x20; 18 CBD sensors, each with ≥ 90% of hours present in 2019 and in Oct 2024 – Sep 2026:
* &#x20; 2, 3, 4, 5, 17, 18, 19, 20, 21, 23, 24, 30, 36, 40, 52, 53, 56, 58.
* &#x20; Excluded 6 (Flinders St underpass: several step changes and now described as
* &#x20; "Myki Barriers") and 47 (moved to 250 Elizabeth St).
* &#x20; Many sensors had a "Pushbox Upgrade" in Jul–Aug 2023, inside the data gap.
* &#x20; Upgraded and non-upgraded sensors recovered similarly (0.83 vs 0.84 of 2019),
* &#x20; so the upgrade probably didn't shift counts much.
* 
* \### Findings so far (data to Sep 2026)
* &#x20; CBD traffic is \~85% of 2019. It fell to 10–40% during the lockdowns.
* &#x20; Weekends are fully back (\~99%); weekdays are at 76–82%, lowest on
* &#x20; Monday (76%) and Friday (78%). The 8am commuter peak lost the most.
* &#x20; Rain: −4% for light rain, −18% for 3+ mm in an hour.
* &#x20; Heat: −8% at 30–35°C, −22% at 35°C+. Cold has little effect.
* 
* \### To do
* &#x20; Phase 3: build the holidays/events CSV in data/reference/
* &#x20; (public holidays, school terms, AFL Grand Final, Moomba, White Night).
* &#x20; Phase 4: robustness check on the 2023 upgrades.

