\# Melbourne Foot Traffic Forecaster



What drives foot traffic in Melbourne's CBD, and can it be predicted a day ahead?

This project uses the City of Melbourne's hourly pedestrian sensor counts (2009–present)

together with hourly weather from Open-Meteo to build three things: an automated pipeline

that keeps a local DuckDB database up to date, a day-ahead forecast of hourly counts per

sensor that has to beat a seasonal-naive baseline, and an analysis of one social question:

has the CBD recovered from COVID, and has hybrid work permanently changed the shape of the

working week? That last part compares Monday and Friday traffic with Tuesday–Thursday,

before and after 2020.



Phase 0 (setup) complete. Pipeline in progress.
\*\*Status:\*\*Data gap: hourly counts for Nov 2022 – Sep 2024 are not publicly available. The council's live table keeps a rolling two-year window, and the historic archive ends on 31 Oct 2022.

