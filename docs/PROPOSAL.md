# Naadi: proposal

**Transport Stack Hackathon 2026 · Problem 1: real-time bus traffic model and journey planner**

## The problem

A Delhi commuter cannot tell whether a bus trip will take 30 minutes or 60. The published timetable runs every stop-to-stop hop at the same 18 km/h at every hour. Our October 2026 data shows real speeds from 35 km/h at 3 am to 16 km/h at 6 pm, and 70% of live trips are not in the timetable. The two baselines the brief names inherit this:
- **Google Maps:** it plans on timetables. Its Delhi bus answers for a Friday and a Tuesday at 08:30 were identical to the second.
- **The ETA Calculator:** on its own live answers, the organisers' tool was off by 12.5 minutes on average.

## What we built

Naadi uses the bus fleet as moving traffic sensors, as the brief proposes.

1. **Travel-time model.** 560 million GPS positions from 31 days are snapped to each route's own shape and turned into 38.4 million stop-to-stop bus traversals.
   - A hierarchy of histories (link-hour, link, stop pair, road cell, city) feeds a LightGBM model of mean link time by hour and day type.
   - A live nowcast corrects it with what buses on that link and road did in the last 30 minutes.
2. **Journey planner.** A RAPTOR router uses measured waits (bunching and gaps included) and the model's ride times.
   - It treats a stop the way riders do: take whichever useful bus comes first ("405 or 402 or 411").
   - It returns door-to-door options with walking, transfers, fares, an 80% range, the same trip at a quieter hour, and a 24-hour SamayChakra dial.
3. **Open API and app.**
   - `GET /journeys?from=…&to=…&depart=…`, plus stop departures with live ETAs, anonymised live buses and road speeds by hour.
   - A Hindi/English web app on a dark 2D/3D Delhi map.
   - Deployed on AWS (Mumbai) within a US$20 budget.

## Evidence

All tests use held-out days and real buses; nothing is simulated.

| Test | Naadi | Baseline |
| --- | --- | --- |
| Bus ETA, 1 to 30 stops ahead (1.99 M predictions) | 134.7 s | timetable 273.6 s; best other 157.2 s |
| Door to door, replayed on actual buses (3,595 journeys) | 18.0 min | timetable planner 23.8 min |
| Organisers' ETA Calculator, on 88,620 of its answers | 8.0 min | 12.5 min |
| Google Maps bus directions, replayed (91 trips) | 12.3 min | 36.5 min |

Every gain over a baseline is tested with a paired bootstrap; all are significant at p < 0.001 except the Google sample, whose 95% interval is −31 to −18 minutes. The 80% ranges contained the actual time for 78% of test journeys.

## What is new

- **Replay validation.** Each planner's advice is followed on the buses that really ran, which gives the true door-to-door time including waits. This is stricter than comparing segment ETAs, and it is how we scored both Google and the timetable.
- **Measured waits with common lines.** Riders get the realistic "whichever comes first" choice, not a fictional timetable minute.
- **Honest uncertainty:** calibrated ranges with checked coverage, and a sample count behind every ride time.
- **Fixes found on the way.** The feed's `trip_id` changes mid-run, which breaks naive trip grouping. A time-zone double shift in DuckDB moves day boundaries by 5.5 hours. Both are documented for other teams and for Transport Stack.

## Who it helps

- **Commuters:** realistic times, and the knowledge that 11 pm is not 9 am.
- **Operators and planners:**
  - the hourly road-speed layer shows where buses crawl;
  - the replay framework measures service reliability (for example the midday gap around 13:00).
- **Transport Stack:** reusable open components. These are the GPS-to-route matcher, the stop-crossing extractor, the travel-time grid, the journey API and the replay evaluator, all on GTFS and GTFS-RT standards.

## Phase 2 plan

- **Problem 5 (crowding):** add AFC-based load as a third criterion in the router, which is already multi-criteria by bus count.
- **Problem 4 (feeder routes):** our link times by hour are the "traffic conditions" input; 500 m road-cell speeds cover the network.
- **Model:**
  - a forward-progress (HMM) map match for loop routes;
  - a street-graph walking network;
  - multimodal legs once an updated DMRC timetable is available;
  - a graph neural network nowcast trained on GPU.
- **Product:** GTFS-RT TripUpdates output so any app, including Chartr's, can use the predictions.

## Team and tools

- **Built with:** Python (DuckDB, LightGBM, Numba, FastAPI) and React (MapLibre GL, deck.gl), with AI coding assistance, which the rules allow.
- **Code licence:** MIT.
- **Data:** © Delhi Transport Stack and Delhi Open Transit Data.
