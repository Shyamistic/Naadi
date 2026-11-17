# Naadi: technical note

Problem 1, Transport Stack Hackathon 2026: a bus travel-time model and a journey planner for Delhi.

Naadi (नाड़ी, "pulse") reads Delhi's traffic from its buses. It learns how long each stretch of each route takes at every hour from 31 days of bus GPS, corrects that with what buses are doing right now, and plans door-to-door bus journeys on those times. This note covers the three topics the brief asks for (§2 to §4), plus waiting, routing and uncertainty.

---

## 1. Data

| Source | What we used |
| --- | --- |
| Historical GPS, October 2026 (organisers' archive `delhi-dtc-bus-gtfs-rt-2026-10.7z`) | 31 days, about 30 M raw positions a day. 36 to 39% are exact repeats and are dropped. Total after cleaning: 560 M positions |
| Live GTFS-RT (OTD Delhi, `VehiclePositions.pb`) | Recorded every 10 s since 15 Nov 2026 on our server in Mumbai. Used for the live nowcast and as test data |
| Static GTFS v1-2 (DTC + DoT) | 6,812 stops, 2,554 routes, one shape per route. The organisers confirmed v1-2 is the current version. Its times are a constant-speed template (every hop at 18.01 km/h), so we use it only for stops, stop order and shapes |
| ETA Calculator for Buses (Transport Stack service) | Logged every minute for 30 random buses and 30 stops, as a baseline |
| Google Maps Routes API (Maps Demo Key) | About 100 bus-only transit answers a day for a fixed OD set, as a baseline |
| Fares | Delhi Tourism city-bus table (organisers' suggestion), shown as indicative |

Raw data stays private (Transport Stack Licence 1.0). Vehicle ids are licence plates: they are used only inside single-day queries as a hash, never written to any output, and the live API returns salted hashes.

---

## 2. Linking GPS points to routes

1. **Clean** (`scripts/ingest_dtc_hist.py`, `scripts/ingest_live.py`): keep positions inside the Delhi NCR box; drop repeated (vehicle, timestamp) rows; drop null ids.
2. **Snap to the route's own shape** (`scripts/match_routes.py`):
   - Each `route_id` in GTFS v1-2 has exactly one shape, and direction is part of the route id (`425UP`, `425DOWN`).
   - So each point is projected onto the nearest segment of its own route's shape, in a local metric projection.
   - A point is matched when it lies within 50 m. That gives distance along the route in metres.
   - Result: 78.1% of points matched, with a median offset of 7.4 m. The rest are buses off their mapped path (diversions, stale shapes), depot moves and GPS noise.
3. **Bus runs** (`scripts/build_speed_tables.py`):
   - The feed's `trip_id` often changes in the middle of a run; we found this on route 425UP.
   - So a run is one vehicle on one route until a 20-minute gap or a jump back of more than 1 km.
4. **Stop crossings:** for every stop on the shape, the crossing time is interpolated between the two consecutive matched points that bracket it. Both points must be 1 to 120 s apart, show forward progress and imply a speed under 108 km/h.
5. **Link traversals:** two consecutive stops crossed by the same run give one stop-to-stop travel time. We keep 5 to 1,800 s, 30 to 5,000 m and 0.5 to 80 km/h.
   - Result: 38.4 M traversals over 71,646 of the 83,413 stop-to-stop links (86%).
   - 77% of links have 30 or more samples.

A bug we found and fixed: DuckDB sessions ran in the laptop's time zone (Asia/Calcutta), so `to_timestamp(t + 19800)` shifted IST a second time. That put weekday/weekend and day boundaries 5.5 h off. Every step now runs in a UTC session and adds the IST offset explicitly, and a test guards it (`tests/test_core.py`).

---

## 3. Estimating travel time on each stretch of road

**Unit:** one link = one stop-to-stop hop of one route, by IST hour (24) and day type (weekday or weekend).

**Historical model** (`scripts/model_tables.py`, `scripts/link_model.py`):
- **Levels of history.** Tables at five levels, so thin cells borrow strength from wider ones:
  - link-hour;
  - link over all hours, shifted by the city's hour-of-day curve;
  - the same stop pair served by any route;
  - a ~500 m road cell × 8 headings (all routes on that stretch of road);
  - the city curve.
- **Empirical-Bayes estimate.** Each level is shrunk into the next with strength k (5 for link-hour, 20 for link, 10 for cell). A link with little data at 2 am therefore falls back on the same road at that hour, not on a guess.
- **LightGBM.**
  - Inputs: all these statistics (means, spreads, sample counts at each level, neighbouring hours) plus geometry.
  - Gamma objective, so it predicts the **mean** time. Means add up along a ride; medians do not, and sums of medians came out about 100 s short.
  - Training uses history from 1 to 17 Oct and targets from 18 to 23 Oct; early stopping on 24 Oct. No day is both history and target.
- **Output:** a 4.0 M-row grid (link × hour × day type). Queries interpolate between hour centres, so 08:59 and 09:01 get nearly the same answer.

**Waiting at stops and signals.** Stop-to-stop times run from stop centre to stop centre, so dwell and signal delay are inside them. With 11-second GPS updates, short dwells are often missed (median measured dwell 0 s). We decided not to model dwell separately rather than report a number the data cannot support.

What the data shows: on weekdays the median link speed is 35.5 km/h at 03:00, 20.5 km/h at 09:00, 16.2 km/h at 18:00 and 28.0 km/h at 23:00. The template timetable's flat 18 km/h is wrong in both directions.

---

## 4. Combining live and historical data

`naadi/nowcast.py`, `naadi/live.py`:

1. **Live traversals.** Every live snapshot is projected onto routes in the same way. When a bus crosses consecutive stops, the traversal is compared with the model: residual r = ln(observed) − ln(model).
2. **Window.** Residuals from the last 30 minutes are pooled per link and per road cell.
   - Road cell: r_cell = S_cell / (n_cell + 3).
   - Link: r_link = (S_link + 10 · r_cell) / (n_link + 10).

   A link with no recent buses takes its road cell's signal. A road with no recent buses takes no correction at all, so the model falls back to history alone.
3. **Correction.** Each link's predicted time is multiplied by exp(r_link). We let the correction decay with how far ahead the bus reaches the link (exp(−Δt / τ)). Tuning on 25 Oct chose τ = ∞: within a single journey (up to about 2 h), today's anomaly persists.
4. **Tuning.** The window (30 min) and the strengths (10 and 3) were picked by grid search on a separate day (25 Oct) and frozen before testing.
5. **Next live bus.** For "leave now" queries, the wait for the first bus is replaced by the predicted arrival of the next live bus on any of the leg's routes: remaining model time from its current position, nowcast-corrected.

---

## 5. Waiting and routing

- **Waits are measured, not scheduled.** About 70% of live trips are unscheduled (`ADDED`), so the timetable's departure minutes mean little.
  - For each route, stop, hour and day type, we measure the expected wait of a rider arriving at random from the gaps between buses that actually passed: E[W] = Σh² / (2 Σh).
  - This keeps bunching and service gaps; gaps up to 2 h count.
  - Stop-level values are shrunk towards the route-hour level.
- **Common lines.** At a stop, Delhi riders take whichever useful bus comes first.
  - Every route serving the boarding stop and reaching the alighting stop (or a stop within 300 m) is a candidate.
  - Candidates are added in order of ride time while a candidate's ride beats the expected wait plus ride of the set so far (the optimal-strategy rule, Chriqui & Robillard 1975; Spiess & Florian 1989).
  - The app says "take 405 or 402 or 411".
- **Router** (`naadi/router.py`): RAPTOR (Delling et al. 2014) adapted to measured waits.
  - Boarding a route costs its expected wait; riding costs the model's time at that hour.
  - Round k finds the best arrival with at most k buses (k ≤ 3). Walking is straight-line distance × 1.35 at 1.25 m/s, with a 1 km access radius and 450 m transfers.
  - Alternatives come from re-running with earlier options' routes banned.
  - A query takes about 0.1 s once warm, using Numba.
- **Time of day.**
  - Every option is re-timed at all 24 hours. This gives the SamayChakra dial and the brief's "the same trip at a quieter hour".
  - The same itinerary is also timed with the timetable planner, for contrast.

---

## 6. Calibration and uncertainty

- **Calibration.** On two held-out days (25 and 26 Oct), each planner's waits and rides get one factor each, minimising mean absolute error of replayed door-to-door times. For Naadi that is wait × 0.80 and ride × 1.19 in live mode. The same procedure is applied to the timetable baseline.
- **80% ranges** use split conformal prediction (Romano et al. 2019).
  - On 27 and 28 Oct we take r = ln(actual / predicted) by band of predicted time, and use the finite-sample 10% and 90% quantiles.
  - On the test days (29 to 31 Oct) the range contained the actual time for **78%** of 3,595 journeys.
  - The ranges are wide (for example 54 to 118 min for a 67-minute trip) because Delhi bus waits have a long tail: 10% of observed waits exceed 43 minutes.

---

## 7. Limits

- The shape match uses the nearest segment without a direction check, so loop routes can snap to the wrong pass. 22% of points are not matched, and some stops have poor capture; the replay skips those.
- The replay can only see buses whose GPS was matched, so a missed bus makes an observed wait look longer than it was.
- Walking uses straight lines × 1.35, not a street graph.
- The metro timetable from the organisers has no Sunday trips and expired in 2025, so Phase 1 plans bus journeys only.
- History covers October 2026 only: no monsoon, festival peaks such as Diwali (8 Nov), or winter fog.
- The Google comparison uses about 100 calls a day (the demo key's limit) and replays only Google's bus legs whose route names match ours.
