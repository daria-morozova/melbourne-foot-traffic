# Melbourne's CBD has come back, but only on weekends

*What 17 years of pedestrian sensors say about hybrid work and the shape of the working week*

On a Saturday afternoon in 2026, Bourke Street Mall is as busy as it was in 2019.
On a Friday morning, the streets around Collins Place are not even close. Melbourne's
city centre hasn't had one recovery from COVID. It has had two, and the gap between
them says a lot about how office work has changed.

## The data

Since 2009 the City of Melbourne has counted people walking past sensors fixed under
awnings and on poles around the city, every hour, every day. The counts are public.
I combined the council's 2009–2022 archive with its current data, added hourly
weather, and compared all of 2019 with the two years from October 2024 to September
2026.

To keep the comparison fair, I used only the 18 CBD sensors that were counting in
both periods, in the same place. I left out public holidays and days when a sensor
was clearly broken. I then used a regression that compares each sensor with itself
and each month with the same month, so that a busy December or a quiet January
doesn't distort the picture.

## Weekends are back, weekdays are not

Across those 18 sensors, Saturday and Sunday traffic is now at **101% of 2019**.
Whatever people are doing in the city at the weekend, they are doing as much of it
as before the pandemic.

Weekdays tell a different story. They sit between **72% and 79% of 2019**. The CBD
has recovered as a place to spend leisure time, but not yet as a place to go to work.

## Two kinds of street

The CBD isn't one place. Some sensors sit among office towers: Collins Place, Queen
Street, the Spencer Street end of Collins Street. Others are in shopping and leisure
areas such as Bourke Street Mall, Chinatown and Melbourne Central. Rather than sort
them by hand, I let the 2019 data decide. If a sensor's weekday traffic was at least
30% higher than its weekend traffic, I classed it as office district. Eight sensors
qualified, and there was a clear break in the numbers between the two groups.

Split this way, the pattern is stark:

|Office district|Recent traffic as % of 2019|
|-|-|
|Monday|65%|
|Tuesday|72%|
|Wednesday|71%|
|Thursday|74%|
|**Friday**|**64%**|
|Saturday / Sunday|100–101%|

**Friday is still 36% below 2019 in the office district, while Wednesday is 29%
below.** Monday is almost as low as Friday. Shopping and leisure areas show a gentler
pattern, with Friday their *best*-recovered weekday at 85%.

## It's the commute

If this is hybrid work, the gap should show up when people travel to work and fade
when they don't. That's exactly what the data shows.

* **7–10am:** office-district Mondays and Fridays are 17% further below 2019 than
Tuesday to Thursday (95% interval: 15–19%).
* **After 7pm:** the difference all but disappears.

People still come into the city on Friday evenings; they just don't come in on Friday
mornings. The gap appears at 17 of the 18 sensors, so it isn't driven by one unusual
corner of the city.

## It isn't closing

The obvious objection is that this is a slow recovery still in progress. It doesn't
look like it. In the office district, traffic did rise between the two recent years:
weekends went from 98% to 104% of 2019. But the Monday/Friday morning gap stayed put:
18% in 2024–25 and 17% in 2025–26. The middle of the week is recovering. The edges of the
week are not catching up.

That points to a stable new arrangement rather than a lag. In sociological terms,
it looks like a new norm: workers and employers have settled on a mid-week office
rhythm, and Monday and Friday have become days for working from home. The
"Tuesday-to-Thursday office" isn't just something people say; it shows up in
millions of footsteps.

## What this means for the city

For businesses that depend on office workers, such as cafés, lunch spots and dry
cleaners in the office district, the city now has three busy weekdays, not five.
For transport, demand is concentrated mid-week. For the council, average weekday
figures hide two very different days. Planning for a typical weekday means planning
for a day that no longer exists.

For retail and leisure areas, the picture is more encouraging. Weekends are fully
back, and Friday evenings are healthy.

## Caveats

* The sensors count **people walking past**, not office workers or unique visitors.
* Some sensors were upgraded in 2023. Upgraded and non-upgraded sensors show the same
gap, so the hardware change doesn't explain it, but it can't rule out every change.
* The council hasn't published counts for November 2022 to September 2024, so I
can't say exactly *when* this pattern settled.
* A lot else has changed since 2019, including shops, transport and population. The
data shows a pattern that fits hybrid work very well; it can't prove that hybrid
work is the only cause.

## How I did it

Everything is open: the pipeline that collects the data each month, the forecasting
model, and the analysis are on GitHub, with a live dashboard where you can pick any
sensor and see its history and tomorrow's forecast.

* Code and notebooks: github.com/limpokaya/melbourne-foot-traffic

Dashboard: *notepad docs\\writeup.md*

*Data: City of Melbourne Pedestrian Counting System; weather from Open-Meteo.*

