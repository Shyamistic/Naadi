# Naadi: technical note

Problem 1, Transport Stack Hackathon 2026: a bus travel-time model and a journey planner for Delhi. Updated 23 Nov 2026 (web build `7bb8f44`).

Naadi (नाड़ी, "pulse") reads Delhi's traffic from its buses. It learns how long each stretch of each route takes at every hour from 31 days of bus GPS, corrects that with what buses are doing right now, measures waits from the gaps between the buses that really came, and plans door-to-door journeys on those times. This note covers the three topics the brief asks for (§2 to §4), then waiting and routing, uncertainty, the live city view, serving, and the limits. Results are in the [validation report](VALIDATION_REPORT.md).

---

## 1. Data

| Source | What we used |
| --- | --- |
| Historical GPS, October 2026 (organisers' archive `delhi-dtc-bus-gtfs-rt-2026-10.7z`, 16.1 GB packed, 124 GB unpacked) | 31 days, about 30 M raw positions a day. 36 to 39% are exact repeats and are dropped. 560 M positions after cleaning |
| Live GTFS-RT (OTD Delhi, `VehiclePositions.pb`) | Recorded every 10 s since 15 Nov 2026 on our server in Mumbai, with a backup recorder on a laptop. Feeds the live nowcast, the "Delhi right now" view and the November test days |
| Static bus GTFS v1-2 (DTC and DoT) | 6,812 stops, 2,554 routes, one shape per route. The organisers confirmed v1-2 is current. Its times are a constant-speed template (every hop at 18.01 km/h), so we use it only for stops, stop order and shapes |
| DMRC metro, NCRTC Namo Bharat and shared-mobility GTFS | Extra modes in the multimodal network, labelled as timetable estimates. The DMRC calendar ended on 31 Dec 2025 and has no Sunday trips |
| October 2026 e-tickets (`October-Delhi.csv`, about 2.56 M tickets) | Fares by route and stop pair. The vehicle-number column is dropped on load |
| OpenStreetMap (Geofabrik northern-zone extract) | Street walking times between places, stops and stations |
| Transport Stack ETA Calculator | Logged every minute for 30 random buses and stops, as a baseline |
| Google Maps Routes API (Maps demo key) | About 100 bus-only transit answers a day for a fixed origin–destination set, as a baseline |

Raw data stays private (Transport Stack Licence 1.0). Vehicle ids are licence plates: they are used only inside single-day queries, never written to any output, and the live API returns salted hashes (§8).

---

## 2. Linking GPS points to routes

1. **Clean** (`scripts/ingest_dtc_hist.py`, `scripts/ingest_live.py`): keep positions inside the Delhi NCR box; drop repeated (vehicle, timestamp) rows; drop null ids.
2. **Snap to the route's own shape** (`scripts/match_routes.py`):
   - Each `route_id` in GTFS v1-2 has exactly one shape, and direction is part of the route id (`425UP`, `425DOWN`).
   - So each point is projected onto the nearest segment of its own route's shape, in a local metric projection, and matched when it lies within 50 m. That gives distance along the route in metres.
   - Result: 78.1% of points matched, with a median offset of 7.4 m. The rest are buses off their mapped path (diversions, stale shapes), depot moves and GPS noise.
3. **Bus runs** (`scripts/build_speed_tables.py`): the feed's `trip_id` often changes in the middle of a run (found on route 425UP), so a run is one vehicle on one route until a 20-minute gap or a jump back of more than 1 km.
4. **Stop crossings:** for every stop on the shape, the crossing time is interpolated between the two consecutive matched points that bracket it. Both points must be 1 to 120 s apart, show forward progress and imply a speed under 108 km/h.
5. **Link traversals:** two consecutive stops crossed by the same run give one stop-to-stop travel time. We keep 5 to 1,800 s, 30 to 5,000 m and 0.5 to 80 km/h.
   - Result: 38.4 M traversals over 71,646 of the 83,413 stop-to-stop links (86%); 77% of links have 30 or more samples.

A bug we found and fixed: DuckDB sessions ran in the laptop's time zone (Asia/Calcutta), so `to_timestamp(t + 19800)` shifted IST a second time and put weekday/weekend and day boundaries 5.5 h off. Every step now runs in a UTC session and adds the IST offset explicitly, and a test guards it (`tests/test_core.py`).

---

## 3. Travel time on each stretch of road

**Unit:** one link is one stop-to-stop hop of one route, by IST hour (24) and day type (weekday or weekend).

**Historical model** (`scripts/model_tables.py`, `scripts/link_model.py`):
- **Levels of history**, so thin cells borrow strength from wider ones: link-hour; link over all hours, shifted by the city's hour-of-day curve; the same stop pair served by any route; a ~500 m road cell × 8 headings (all routes on that stretch of road); the city curve.
- **Empirical-Bayes estimate.** Each level is shrunk into the next with strength k (5 for link-hour, 20 for link, 10 for cell). A link with little data at 2 a.m. therefore falls back on the same road at that hour, not on a guess.
- **LightGBM.** Inputs are all these statistics (means, spreads, sample counts at each level, neighbouring hours) plus geometry. A gamma objective predicts the **mean** time: means add up along a ride and medians don't (sums of medians came out about 100 s short). Training uses history from 1 to 17 Oct and targets from 18 to 23 Oct, with early stopping on 24 Oct, so no day is both history and target.
- **Output:** a 4.0 M-row grid (link × hour × day type). Queries interpolate between hour centres, so 08:59 and 09:01 get nearly the same answer.

**Dwell and signals** are inside the stop-to-stop times, which run from stop centre to stop centre. With GPS updates about every 11 s, short dwells are often missed (median measured dwell 0 s), so we don't model dwell separately rather than report a number the data can't support.

**What the data shows:** on weekdays the median bus speed across road cells is 34.8 km/h at 02:00, 22.7 km/h at 08:00, 20.3 km/h at 12:00 and 16.3 km/h at 18:00. The template timetable's flat 18 km/h is wrong in both directions.

---

## 4. Combining live and historical data

`naadi/nowcast.py`, `naadi/live.py`:

1. **Live traversals.** Every live snapshot is projected onto routes in the same way. When a bus crosses consecutive stops, the traversal is compared with the model: residual r = ln(observed) − ln(model).
2. **Window and pooling.** Residuals from the last 20 minutes are pooled per link and per road cell:
   - road cell: r_cell = S_cell / (n_cell + 1);
   - link: r_link = (S_link + 5 · r_cell) / (n_link + 5).

   A link with no recent buses takes its road cell's signal. A road with no recent buses takes no correction, so the model falls back to history alone.
3. **Correction with a fade.** Each link's predicted time is multiplied by exp(r_link · e^(−Δt/τ)), where Δt is how far ahead the bus reaches the link and τ = 9,600 s. Today's anomaly mostly persists within a journey, and fades over a few hours.
4. **Tuning.** The window (1,200 s), the strengths (5 and 1) and τ were picked by grid search on a separate day (25 Oct, tuning error 112.4 s) and frozen before testing on 26 to 31 Oct.
5. **Next live bus.** For "leave now", the wait for the first bus is replaced by the predicted arrival of the next live bus on any of the leg's routes: the remaining model time from its current position, nowcast-corrected.

A deep spatio-temporal forecaster (STID, trained briefly on a Kaggle GPU from aggregated residuals only) beat the nowcast at forecasting road-cell residuals 15, 30 and 60 minutes ahead, but didn't improve held-out bus arrival times (136.5 s alone, 135.1 s blended, against 134.7 s for the nowcast it was compared with). It stays out of the API and is reported as an ablation (`validation/results/eta_deep_oct.md`).

---

## 5. Waiting and routing

- **Waits are measured, not scheduled.** About 70% of live trips are unscheduled (`ADDED`), so the timetable's departure minutes mean little.
  - For each route, stop, hour and day type, we measure the expected wait of a rider arriving at random from the gaps between buses that actually passed: E[W] = Σh² / (2 Σh). This keeps bunching and service gaps; gaps up to 2 h count.
  - Stop-level values are shrunk towards the route-hour level.
- **Common lines.** At a stop, Delhi riders take whichever useful bus comes first.
  - Every route serving the boarding stop and reaching the alighting stop (or a stop within 300 m) is a candidate.
  - Candidates are added in order of ride time while a candidate's ride beats the expected wait plus ride of the set so far (the optimal-strategy rule, Chriqui & Robillard 1975; Spiess & Florian 1989). The app says "take 405 or 402 or 411".
- **Router** (`naadi/router.py`, `naadi/strategy.py`): RAPTOR (Delling et al. 2014) adapted to measured waits.
  - Boarding a route costs its expected wait; riding costs the model's time at that hour. Round k finds the best arrival with at most k buses (k ≤ 3). Alternatives come from re-running with earlier options' routes banned. A query takes about 0.1 s once warm, using Numba.
  - **Walking** follows the OpenStreetMap street network (`naadi/walk.py`, `scripts/build_walk.py`) at 1.25 m/s, with straight-line distance × 1.35 as the fallback where no street path is known.
- **Other modes** (`naadi/multimodal.py`): metro, Namo Bharat and shared autos are added as separate platforms in a second network, with timetable or survey frequencies, and are labelled "timetable estimate". The bus network arrays stay byte-for-byte unchanged, and a test checks that the bus options are identical with and without the extra modes. Bus-only results are the scored ones.
- **Fares** (`naadi/fares.py`, `scripts/build_fares.py`): the October e-ticket amounts by route and stop pair, fitted on 1 to 24 Oct; on 25 to 31 Oct they matched the charged amount exactly 93.4% of the time where the table covers the route and stops. Elsewhere the official DTC slabs apply, labelled "fare estimated". Cash fares lead; One Delhi app prices (10% off) and the Pink Saheli rule are shown separately.
- **Time of day.** Every option is re-timed with the same buses at all 24 hours: the SamayChakra dial and the brief's "the same trip at a quieter hour". The same itinerary is also timed with the timetable planner, for contrast ("Timetable says 62 min").
- **Arrive by.** `arrive=` searches departures every 5 minutes over the three hours before the deadline and keeps the latest options that arrive in time.

---

## 6. Calibration and uncertainty

- **Calibration** (v2). On two held-out days (25 and 26 Oct), each planner's historical waits, live waits and rides get one factor each, minimising the mean absolute error of replayed door-to-door times. For Naadi with live data: historical wait × 1.40, live wait × 0.90, ride × 1.14. The same procedure is applied to the timetable baseline.
- **80% ranges** use grouped split-conformal prediction (Romano et al. 2019). On 27 and 28 Oct we take r = ln(actual / predicted) grouped by predicted time band and wait class, and use the finite-sample 10% and 90% quantiles. On the test days (29 to 31 Oct) the range contained the actual time for **78%** of journeys, with a median width of 40 min with live data.
- The ranges are wide because Delhi bus waits have a long tail: 10% of observed waits exceed 43 minutes. They are shown as "usually 59–109 min", not hidden.

---

## 7. Delhi right now

`GET /pulse` (`naadi/webapi.py`) summarises the last 20 minutes of live traversals:

- **Travel time against an ordinary day.** The median live residual is compared with ordinary October days at the same hour and day type (`scripts/build_pulse_baseline.py` → `pulse_baseline.json`). Comparing with zero would be wrong: the model predicts mean stretch times and stretch times are right-skewed, so the median residual is already about −0.05 on an ordinary day. Below 3% the app says "as usual".
- **Slowest stretches:** stretches with at least 3 traversals running at least 1.35 times their usual time, with the routes involved.
- **Where buses are:** a density grid (0.004° cells) for the home map's glow. The answer is cached for 15 s.

---

## 8. Serving, privacy and reliability

- **Serving.** FastAPI and Uvicorn on an AWS t4g.small (1.8 GB RAM) in Mumbai behind Caddy, which provides HTTPS on sslip.io. No database: the API holds the network, grid and tables as NumPy arrays in memory (about 480 MB after a burst of queries). A journey takes 0.3 to 0.6 s.
- **Privacy.** Public bus ids are SHA-256 of a secret salt plus the licence plate, cut to 10 hex characters. The salt is a random SecureString in AWS SSM, written to a root-only environment file on the server; a deploy fails and rolls back if it's missing. The web app has no accounts, tracking or analytics.
- **Rate limits.** 600 requests a minute per address and 60 for `/journeys`, answered with HTTP 429 and `Retry-After`. The web client shares identical requests in flight, throttles itself (a burst of 40, then 4 a second) and waits out a 429 with a visible notice. Browser tests count every screen's requests so a re-fetch loop can't ship again.
- **Deploys** (`infra/deploy_api.py`) upload code, artefacts and the web build to S3 and switch the server over SSM. The server snapshots the previous release first and restores it automatically if the new API doesn't report healthy within 120 s.

---

## 9. Limits

- The shape match uses the nearest segment without a direction check, so loop routes can snap to the wrong pass. 22% of points aren't matched, and some stops have poor capture; the replay skips those.
- The replay can only see buses whose GPS was matched, so a missed bus makes an observed wait look longer than it was.
- The door-to-door test was run when walking was straight-line distance × 1.35; the planner now uses street walking, and the test will be re-run.
- Every method predicts arrivals early, more so further ahead (Naadi: about 7 s at 1 stop, 251 s at 30). November buses ran about 12% faster than October's, which matters for an October-trained model; an out-of-time November test is planned.
- History covers October 2026 only: no monsoon, festival peaks such as Diwali (8 Nov), or winter fog.
- Metro times come from a timetable whose calendar ended in 2025; they are labelled as estimates.
- The Google comparison uses about 100 calls a day (the demo key's limit) and replays only Google bus legs whose route names match ours; the ETA Calculator comparison uses a 3% sample, limited by laptop memory.
