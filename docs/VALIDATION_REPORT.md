# Naadi: validation report

All numbers come from files in `validation/results/` produced by the scripts named in each section. History for every method comes only from days before the test days. Nothing is fitted on test days.

## Summary

| Test | Data | Naadi | Best other | Official timetable |
| --- | --- | --- | --- | --- |
| Bus ETA, 1 to 30 stops ahead | 1.99 M predictions, 26 to 31 Oct | **134.7 s** mean error | 157.2 s (live only) | 273.6 s |
| Door to door, replayed on real buses | 3,595 journeys, 29 to 31 Oct | **18.0 min** (median 8.6) | — | 23.8 min (median 13.8) |
| Organisers' ETA Calculator, on its own answers | 88,620 answers, 15 to 16 Nov | **8.0 min** (median 1.7) | ETA Calculator 12.5 min (median 7.3) | — |
| Google Maps, bus only, replayed | 91 trips, 15 to 16 Nov | **12.3 min** | Google 36.5 min | — |
| 80% range coverage | 3,595 journeys | 78% | — | — |

---

## 1. Bus ETA on held-out days (`scripts/eval_eta.py`, `eta_oct.md`)

**Task:** a bus is at a stop now; predict when it reaches each stop 1 to 30 stops ahead.

**Truth:** interpolated crossing times of the same bus run.

**Data:**
- 1,987,389 predictions from 112,777 bus runs on 26 to 31 Oct.
- History from 1 to 24 Oct; LightGBM trained on 18 to 23 Oct.
- Nowcast settings tuned on 25 Oct.

| Method | MAE (s) | MAPE | P90 error (s) | within 2 min |
| --- | --- | --- | --- | --- |
| Official timetable (18.01 km/h template) | 273.6 | 33.5% | 687 | 50.9% |
| Bus's own recent speed (persistence) | 280.4 | 30.3% | 695 | 58.3% |
| City speed curve by hour | 235.1 | 27.3% | 588 | 56.8% |
| Historical average per link-hour | 173.1 | 17.4% | 435 | 68.4% |
| Empirical-Bayes history | 168.8 | 17.3% | 415 | 69.1% |
| Naadi history only (LightGBM) | 165.5 | 17.9% | 401 | 68.9% |
| Live only (last 30 min per link) | 157.2 | 18.2% | 383 | 68.7% |
| **Naadi (history + live nowcast)** | **134.7** | **15.5%** | **315** | **72.8%** |

**By distance ahead** (MAE in seconds):

| Method | 1-2 stops | 3-5 | 8-12 | 16-30 |
| --- | --- | --- | --- | --- |
| Timetable | 75 | 169 | 345 | 630 |
| Historical average | 45 | 102 | 215 | 412 |
| **Naadi** | **39** | **84** | **167** | **308** |

**Significance:** paired cluster bootstrap over bus runs (1,000 resamples). Naadi minus each baseline:

| Baseline | Difference (s) | 95% CI | One-sided p |
| --- | --- | --- | --- |
| Live only | −22.5 | [−23.0, −22.1] | < 0.001 |
| History only | −30.8 | [−31.4, −30.2] | < 0.001 |
| Historical average | −38.4 | [−39.2, −37.7] | < 0.001 |
| Timetable | −138.9 | [−140.2, −137.5] | < 0.001 |

The LightGBM history is also better than the historical average (−7.6 s, CI [−8.0, −7.2]).

All methods under-predict on average (bias −71 s for Naadi). Link traversals over 30 minutes are excluded from training, while the test truth includes every delay.

---

## 2. Door-to-door journeys replayed on real buses (`scripts/eval_journeys.py`, `scripts/build_summary.py`, `journeys_oct.md`)

### OD set (`validation/od_set.csv`)

Fixed before any results were seen, seed 20261117:
- 30 landmark trips, including the brief's Kashmere Gate ISBT → Nehru Place;
- 100 single-route stop pairs stratified by length (2 to 5, 5 to 10 and 10 to 20 km) across a 5 km grid;
- 60 random stop pairs 3 to 18 km apart.

Each is asked at 8 departure times (07:30, 08:30, 10:00, 13:00, 16:00, 18:00, 20:00, 22:30).

### Replay

Each planner's best journey is followed on the buses that actually ran that day:
1. walk as planned;
2. board the first bus of any of the leg's routes that really passed the stop afterwards;
3. ride it to the alighting stop;
4. repeat for any transfer.

This gives the true door-to-door time of the advice, including the wait. Cases are skipped when the boarding stop's GPS capture that day is under 60% of the route's typical stop, or no bus is seen within 3 hours.

### Splits

- Calibration factors fitted on 25 to 26 Oct.
- Conformal ranges calibrated on 27 to 28 Oct.
- Reported on 29 to 31 Oct.

| Planner | journeys | MAE raw (min) | median error | within 10 min | MAE calibrated | 80% range coverage |
| --- | --- | --- | --- | --- | --- | --- |
| Timetable planner (same router, GTFS times, scheduled headways) | 3,330 | 27.2 | 13.8 | 42% | 23.8 | 79% |
| Naadi (history) | 3,600 | 20.1 | 9.0 | 53% | 18.7 | 78% |
| **Naadi (history + live)** | 3,595 | 19.4 | 8.6 | 54% | **18.0** | 78% |

**MAE by departure time** (Naadi live, calibrated vs timetable, minutes):

| | 07:30 | 08:30 | 10:00 | 13:00 | 16:00 | 18:00 | 20:00 | 22:30 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Naadi | 14.5 | 12.9 | 13.0 | 26.1 | 19.1 | 23.6 | 20.8 | 12.9 |
| Timetable | 17.4 | 15.3 | 16.3 | 32.9 | 28.3 | 33.1 | 28.5 | 16.5 |

The 13:00 slot is the hardest for every planner: midday service gaps make waits long and irregular.

Most of the remaining error is waiting time. Splitting direct journeys on 27 Oct:
- **Rides:** within 6.0 min on average.
- **Waits:** the median wait was close to the prediction (7.7 vs 6.7 min). The tail is long: 10% of waits exceeded 43 minutes and 5% exceeded 80.

---

## 3. Head-to-head with the Transport Stack ETA Calculator (`scripts/score_eta_calculator.py`, `eta_calculator_nov.md`)

**Method:**
- We logged the organisers' `bus/etas` answers on 15 to 16 Nov: about 1 request a second, 30 random live buses per minute.
- For 88,620 answers we found when the bus actually crossed that stop, from its GPS along the route.
- Naadi predicted from the same bus position at the same moment, using October history only.

| Method | MAE (min) | median error | within 2 min | 0-5 min | 10-20 min | 20-40 min |
| --- | --- | --- | --- | --- | --- | --- |
| ETA Calculator | 12.50 | 7.26 | 12.4% | 6.12 | 7.95 | 9.70 |
| Naadi history | 8.99 | 2.53 | 43.8% | 1.20 | 3.57 | 5.85 |
| **Naadi history + live** | **8.01** | **1.65** | **55.3%** | **1.01** | **2.71** | **4.40** |

Both methods have large errors beyond 40 minutes ahead (about 24 min), where buses wait at terminals.

---

## 4. Google Maps (`scripts/google_sampler.py`, `scripts/compare_google.py`, `google_nov.md`)

**Sampling:**
- Google Routes API, transit restricted to bus, for the OD set on recorded days.
- About 100 calls a day (the demo key's limit), spent in a fixed priority order.

**Google's timetable-based times:** Google's answers for Friday 13 and Tuesday 17 Nov at 08:30 were identical to the second.

**Replay:**
- Google's recommended itinerary is replayed by matching each Google bus line to our route of the same name, with stops within 300 m of Google's boarding and alighting stops.
- The rider then waits for that line, as Google instructs.

**Coverage:** of 187 answers on 15 to 16 Nov, 97 Google itineraries matched and 91 could be replayed together with Naadi's.

| | Google Maps | Naadi |
| --- | --- | --- |
| Mean error of predicted door-to-door time | 36.5 min | **12.3 min** |
| Median error | 26.7 min | **7.2 min** |
| Bias (negative = too optimistic) | −36.4 min | −4.1 min |
| Predictions within 10 min | 22% | **63%** |
| Median actual time of the recommended trip | 59.6 min | **45.0 min** |

- **Difference in mean error:** −24.3 min (bootstrap 95% CI −31.3 to −17.8).
- **Faster in reality:** Naadi's recommended trip was actually faster in 73% of cases.
- **Size and scope:** the sample is small and covers one Sunday evening and one Monday. More days are added each day by `scripts/daily_refresh.py`.

---

## 5. Reproduce

```
python scripts/ingest_dtc_hist.py           # October archive -> L1
python scripts/match_routes.py              # L1 -> L2
python scripts/build_speed_tables.py        # stop passages, link traversals
python scripts/rebuild_all.py --from-step 3 # tables, service, model, grids, networks, ETA evaluation
python scripts/eval_journeys.py --network eval_oct --live --out journeys_oct --days 2026_10_25 ... 2026_10_31
python scripts/run_test_days.py             # recorded November days
python scripts/score_eta_calculator.py
python scripts/compare_google.py
python scripts/build_summary.py
```
