# Naadi: proposal

**Transport Stack Hackathon 2026 · Problem 1: real-time bus traffic model and journey planner** · updated 23 Nov 2026

Live app: https://13-235-147-97.sslip.io/ · API: https://13-235-147-97.sslip.io/api/docs · Demo video: https://youtu.be/7jEKTCY2mV0

## The idea in one line

**Naadi is the measured travel-time layer for Delhi's buses:** an open API that says how long a bus trip really takes, and how sure that is, learned from the buses' own GPS, tested in public on days it never saw, and shaped to plug into the Transport Stack's own journey planner and ETA Calculator. The web app is its showcase.

## The problem

A Delhi commuter can't tell whether a bus trip will take 40 minutes or 90.
- **The timetable doesn't know the time of day.** Its stop-to-stop times are a constant 18 km/h template. Real weekday speeds run from 34.8 km/h at 02:00 to 16.3 km/h at 18:00.
- **Waits are unknown.** About 70% of live trips aren't in the timetable, so the scheduled minute means little, and in our replay waiting causes more error than riding.
- **The baselines the brief names inherit this.** Google Maps' Delhi bus answers for a Friday and a Tuesday at 08:30 were identical to the second; replayed on the buses that ran, they were 36.5 minutes off on average.

## What we built

1. **A travel-time model from the fleet.** 560 million GPS positions from 31 days of October 2026 are snapped to each route's own shape and turned into 38 million stop-to-stop bus traversals. A five-level history (link-hour, link, stop pair, road cell, city) with empirical-Bayes shrinkage feeds a LightGBM model of mean link time by hour and day type. A live nowcast corrects it with the stretches buses drove in the last 20 minutes, borrowing from the same road when a route has no recent bus.
2. **A door-to-door planner.** RAPTOR with measured waits and the way riders really travel: "take 405 or 402 or 411, whichever comes first". Each option has the walk (OpenStreetMap streets), boarding stop, routes, changes, fare (from October e-tickets), an 80% range, the next live buses, and the same trip at every hour of the day (the SamayChakra dial). Metro, Namo Bharat and shared autos appear as labelled timetable estimates, without changing the bus options.
3. **An open API and a web app.** 19 endpoints with OpenAPI docs, including `GET /journeys?from=…&to=…&depart=…` and an endpoint in the organisers' journey-planner format. The web app (Hindi and English, light and dark, installable) adds live buses in 3D, a live "Delhi right now" view, road speeds by hour, stop boards, route pages and an accuracy page.

## Evidence

All tests use held-out days and real buses; nothing is simulated.

| Test | Naadi | Baseline |
| --- | --- | --- |
| Bus arrival, 1 to 30 stops ahead (1,987,389 predictions) | 133.3 s | timetable 273.6 s; best of 8 other methods 157.2 s |
| Time on the bus, rides of 5 to 40 stops (2,876,808 rides) | 4.31 min on a 33-min ride; 90.4% within 10 min | — |
| Door to door, replayed on the buses that ran (3,598 journeys) | 15.5 min | timetable planner 22.9 min |
| Google Maps bus directions, both replayed (91 trips) | 12.3 min | 36.5 min |
| The organisers' ETA Calculator, same bus position (9,616 answers) | 7.38 min | 9.69 min |

Gains in the arrival test are significant at p < 0.001 under a paired bootstrap; the Google difference has a 95% interval of −31 to −18 minutes. The 80% ranges held the real time 78% of the time. Details and caveats: [validation report](VALIDATION_REPORT.md).

## What is new

- **Replay validation.** Each planner's advice is followed on the buses that really ran, which gives the true door-to-door time including waits. It is stricter than comparing segment arrival times, and it scores Naadi, a timetable planner and Google the same way.
- **Measured waits with common lines,** so riders get the realistic "whichever comes first" choice rather than a fictional timetable minute.
- **Honest uncertainty:** calibrated ranges with checked coverage, and a count of the past stop-to-stop runs behind every ride.
- **A live city view:** bus travel time against an ordinary day at the same hour, and the slowest stretches right now, from the whole fleet.
- **Fixes the Stack can reuse:** the feed's `trip_id` changes mid-run, which breaks naive trip grouping; a time-zone double shift in DuckDB moves day boundaries by 5.5 hours. Both are documented in the [technical note](TECHNICAL_NOTE.md).

## Who it helps

- **Commuters:** realistic times and ranges, the next real bus, the quieter hour, fares, in Hindi or English.
- **Operators and planners:** measured speeds by stretch and hour, and a replay framework that measures reliability (the midday gap around 13:00 is the hardest slot for every planner).
- **The Transport Stack:** open components on GTFS and GTFS-RT standards: the GPS-to-route matcher, the stop-crossing extractor, the travel-time grid, the journey API in the organisers' format and the replay evaluator. On the ETA Calculator's own questions, scored from the same position, Naadi's error is 7.4 minutes against 9.7, and fresher positions would improve the Calculator too.

## Why it's feasible

- **Running today** on one AWS t4g.small in Mumbai, at about US$0.4 a day under a US$20 budget; HTTPS, deploys with automatic rollback, per-address rate limits and a secret salt for public bus ids.
- **No database:** DuckDB over Parquet for the pipeline, arrays in memory for the API; a journey takes 0.3 to 0.6 s.
- **Reproducible:** the pipeline runs in about two hours on one laptop; 47 Python tests and browser tests on mocked and real data, including a request budget for every screen.

## Phase 2 plan

- **Problem 4, feeder routes:** our link times by hour are the "traffic conditions" input the brief asks for, with 500 m road-cell speeds across the network.
- **Problem 5, crowding:** e-ticket and AFC load as a third criterion in the router, which already trades time against changes.
- **Accuracy:** an out-of-time November test, the door-to-door replay with street walking, bias correction by distance ahead, a larger Google sample, and a forward-progress map match for loop routes.
- **Operators:** bunching, unreliable stretches and how realistic each route's timetable is, by hour.
- **Open components:** published model tables for one-command setup, and GTFS-RT TripUpdates output so any app, including Chartr, can use the predictions.

## Team and tools

- **Built with** Python (DuckDB, LightGBM, Numba, FastAPI) and TypeScript (React, MapLibre GL, deck.gl), with AI coding assistance (Kiro), which the rules allow.
- **Code licence:** MIT. **Data:** © Delhi Transport Stack and Delhi Open Transit Data; map data © OpenStreetMap contributors.
