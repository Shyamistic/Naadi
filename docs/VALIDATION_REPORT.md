# Naadi: validation report

Updated 23 Nov 2026. Every number comes from a file in `validation/results/`, produced by the script named in each section and gathered into `summary.json` by `scripts/build_summary.py`. History for every method comes only from days before the test days, and nothing is fitted on test days.

## Summary

| Test | Data | Naadi | Best other | Official timetable |
| --- | --- | --- | --- | --- |
| Bus arrival, 1 to 30 stops ahead | 1,987,389 predictions, 26 to 31 Oct | **133.3 s** mean error | 157.2 s (recent live buses only) | 273.6 s |
| Time on the bus, rides of 5 to 40 stops | 2,876,808 rides, 26 to 31 Oct | **4.31 min** on a 32.96-min ride (13.1%) | — | — |
| Door to door, replayed on real buses | 3,598 journeys, 29 to 31 Oct | **15.5 min** | — | 22.9 min (timetable planner) |
| The organisers' ETA Calculator, same bus position | 9,616 answers, 15 to 16 Nov | **7.38 min** | ETA Calculator 9.69 min | — |
| Google Maps bus directions, replayed | 91 trips, 15 to 16 Nov | **12.3 min** | Google 36.5 min | — |
| 80% range coverage | Door-to-door test journeys | 78% | — | — |

The charts in the [README](../README.md#-accuracy) are drawn from the same file by `scripts/build_docs_figures.py`.

---

## 1. Bus arrival on held-out days (`scripts/eval_eta.py`, `eta_oct.md`)

**Task:** a bus is at a stop now; predict when it reaches each stop 1 to 30 stops ahead. **Truth:** the interpolated crossing times of the same bus run.

**Data:** 1,987,389 predictions from 112,777 bus runs on 26 to 31 Oct. History from 1 to 24 Oct; LightGBM trained on 18 to 23 Oct; nowcast tuned on 25 Oct (window 1,200 s, link strength 5, cell strength 1, fade τ = 9,600 s; tuning error 112.4 s).

| Method | MAE (s) | MAPE | P90 error (s) | Within 2 min | Bias (s) |
| --- | --- | --- | --- | --- | --- |
| Official timetable (18.01 km/h template) | 273.6 | 33.5% | 687 | 50.9% | −91.4 |
| The bus's own recent speed | 280.4 | 30.3% | 695 | 58.3% | −49.6 |
| City speed curve by hour | 235.1 | 27.3% | 588 | 56.8% | −121.1 |
| Historical average by link and hour | 173.1 | 17.4% | 435 | 68.4% | −125.5 |
| Empirical-Bayes history | 168.8 | 17.3% | 415 | 69.1% | −114.4 |
| Naadi history only (LightGBM) | 165.5 | 17.9% | 401 | 68.9% | −95.7 |
| Log-normal Kalman filter (published method) | 163.1 | 18.3% | 389 | 68.7% | −77.3 |
| Recent live buses only | 157.2 | 18.2% | 383 | 68.7% | −76.7 |
| **Naadi (history + live nowcast)** | **133.3** | **15.6%** | **309** | **72.9%** | −67.8 |

The log-normal Kalman filter is the published baseline of Achar et al. (arXiv:1904.03444) and Bhutani, Pachal & Achar (arXiv:2210.01655), with its noise settings tuned on 25 Oct only.

**By distance ahead** (MAE, s):

| Method | 1–2 stops | 3–5 | 8–12 | 16–30 |
| --- | --- | --- | --- | --- |
| Official timetable | 75 | 169 | 345 | 630 |
| Historical average | 45 | 102 | 215 | 412 |
| Recent live buses only | 46 | 98 | 195 | 361 |
| **Naadi** | **39** | **83** | **165** | **305** |

**By time of day** (MAE, s): Naadi 66 at night (00–06), 112 in the morning peak (07–10), 150 at midday (11–16), 196 in the evening peak (17–20) and 112 late (21–23); the timetable 264, 210, 288, 414 and 208.

**Significance:** paired cluster bootstrap over bus runs (1,000 resamples); Naadi minus each baseline:

| Baseline | Difference (s) | 95% CI | One-sided p |
| --- | --- | --- | --- |
| Recent live buses only | −23.9 | [−24.5, −23.4] | < 0.001 |
| Naadi history only | −32.2 | [−32.8, −31.6] | < 0.001 |
| Historical average | −39.8 | [−40.6, −39.1] | < 0.001 |
| Timetable | −140.3 | [−141.6, −138.9] | < 0.001 |

The LightGBM history is also better than the historical average (−7.6 s, CI [−8.0, −7.2]).

**Bias.** Every method predicts early on average. Naadi's bias grows with distance ahead, from −6.7 s at 1 stop to −251 s at 30. Link traversals over 30 minutes are excluded from training while the test truth includes every delay, and November buses ran about 12% faster than October's.

**Sensitivities:**
- With one calibration factor per distance ahead, fitted on 25 Oct for every method, Naadi reaches 130.2 s and the timetable 277.4 s. This isn't used in the live app.
- 26 Oct is a gazetted holiday inside the test window and is scored as a weekday. Scoring it as a weekend instead raises that day's error from 125.2 s to 152.8 s.
- Per test day, Naadi's error runs from 110.1 s (29 Oct) to 148.7 s (31 Oct).

---

## 2. Time on the bus, ride only (`scripts/eval_rides.py`, `rides_oct.md`)

This is the usual way bus travel-time models are reported, and how other entries report theirs: one bus over 5 to 40 consecutive stops on the same trip. History 1 to 24 Oct, nowcast tuned on 25 Oct, tested 26 to 31 Oct.

| Sample | Rides | Mean error | Mean ride | Within 5 min | Within 10 min | 5–9 stops | 10–20 | 21–40 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| All rides | 2,876,808 | **4.31 min** | 32.96 min | 76.4% | 90.4% | 2.20 | 3.86 | 6.73 |
| No gap over 10 min between stops | 966,316 | 2.65 min | 27.16 min | 85.1% | 97.2% | 1.60 | 2.63 | 4.07 |

Error as a share of ride time is 13.1% (9.8% without long gaps). Door to door with the wait for the bus, below, is the stricter test.

---

## 3. Door to door, replayed on real buses (`scripts/eval_journeys.py`, `journeys_oct_v2.md`)

### The origin–destination set (`validation/od_set.csv`)

Fixed before any results were seen (seed 20261117):
- 30 landmark trips, including the brief's Kashmere Gate ISBT → Nehru Place;
- 100 single-route stop pairs stratified by length (2 to 5, 5 to 10 and 10 to 20 km) across a 5 km grid;
- 60 random stop pairs 3 to 18 km apart.

Each is asked at 8 departure times: 07:30, 08:30, 10:00, 13:00, 16:00, 18:00, 20:00 and 22:30.

### The replay

Each planner's best journey is followed on the buses that actually ran that day: walk as planned; board the first bus of any of the leg's routes that really passed the stop afterwards; ride it to the alighting stop; repeat for any change. That gives the true door-to-door time of the advice, including the wait. Cases are skipped when the boarding stop's GPS capture that day is under 60% of the route's typical stop, or no bus is seen within 3 hours.

### Splits and results

Calibration factors fitted on 25 to 26 Oct; ranges calibrated on 27 to 28 Oct; reported on 29 to 31 Oct.

| Planner | Journeys | MAE raw (min) | MAE calibrated (min) |
| --- | --- | --- | --- |
| Timetable planner (same router, GTFS times, scheduled headways) | 3,366 | 26.5 | 22.9 |
| Naadi (history) | 3,613 | 19.6 | 17.9 |
| Naadi (history + live traffic) | 3,606 | 19.0 | 17.3 |
| **Naadi (history + live)** | 3,598 | 17.7 | **15.5** |

"Live" adds today's traffic on each stretch and, for the first bus, the bus actually approaching the stop.

| Ranges | Coverage of the 80% range | Median width |
| --- | --- | --- |
| Naadi (history) | 77.5% | 47.2 min |
| Naadi (history + live) | 78.1% | 40.0 min |

**Where the error comes from.** For Naadi with live data, the wait error is 12.6 min and the ride error 6.9 min (timetable planner: 18.0 and 9.8). Waits dominate: 10% of observed waits exceed 43 minutes. The 13:00 slot is the hardest for every planner, because midday service gaps make waits long and irregular.

**Walking.** This test was run when walking was straight-line distance × 1.35. The planner now uses OpenStreetMap street walking; the test will be re-run with it.

---

## 4. Head to head with the Transport Stack ETA Calculator (`scripts/score_eta_calculator.py`, `eta_calculator_nov.md`)

**Method.** We logged the organisers' ETA Calculator answers ("bus X will reach stop S in N minutes") on 15 and 16 Nov, and measured when the bus really crossed that stop from its GPS. Naadi answered the same question from the same bus position, using October history only.

**Fair scoring.** The actual crossing must belong to the same vehicle run (runs split after a gap over 1,200 s or a jump back over 1,000 m), and both methods are scored from the same GPS fix. An earlier scoring (12.5 against 8.0 min on 88,620 answers) didn't restrict the truth to the same run and was partly unfair to the Calculator, so it is withdrawn.

| Method | MAE (min) | Median error | Within 2 min | Bias | 0–5 min ahead | 10–20 | 20–40 | 40+ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ETA Calculator (Transport Stack) | 9.69 | 6.97 | 12.2% | +4.17 | 6.14 | 8.03 | 9.76 | 15.50 |
| Naadi history | 9.42 | 6.65 | 8.1% | +4.97 | 5.70 | 7.40 | 9.43 | 15.85 |
| **Naadi history + live** | **7.38** | **4.93** | **13.1%** | +2.58 | **5.02** | **5.68** | **6.75** | **12.81** |

9,616 same-run cases (a 3% sample, limited by laptop memory). Answering from the latest position at the time of the request, as the live app does, Naadi's error is 4.81 min. The Calculator's answers used positions a median of 266 s old (p10 to p90: 198 to 351 s), which explains much of its error, so fresher positions would improve it. Naadi is offered as a component the Stack can use alongside it.

---

## 5. Google Maps (`scripts/google_sampler.py`, `scripts/compare_google.py`, `google_nov.md`)

**Sampling.** Google Routes API, transit restricted to bus, for the origin–destination set on recorded days: about 100 calls a day (the demo key's limit), spent in a fixed priority order. Google's answers for Friday 13 and Tuesday 17 Nov at 08:30 were identical to the second, which suggests timetable-based times.

**Replay.** Google's recommended itinerary is replayed by matching each Google bus line to our route of the same name, with stops within 300 m of Google's boarding and alighting stops; the rider waits for that line, as Google instructs. Of 187 answers on 15 and 16 Nov, 97 Google itineraries matched and 91 could be replayed together with Naadi's.

| | Google Maps | Naadi |
| --- | --- | --- |
| Mean error of predicted door-to-door time | 36.5 min | **12.3 min** |
| Median error | 26.7 min | **7.2 min** |
| Bias (negative = too optimistic) | −36.4 min | −4.1 min |
| Predictions within 10 min | 22% | **63%** |
| Median actual time of the recommended trip | 59.6 min | **45.0 min** |

The difference in mean error is −24.3 min (bootstrap 95% CI −31.3 to −17.8), and Naadi's recommended trip was actually faster in 73% of cases. The sample is small and covers two unusual days: 15 Nov was Chhath Puja and 16 Nov had morning fog. The claim is narrow: "on the Delhi bus trips we replayed".

---

## 6. Deep-model ablation (`validation/results/eta_deep_oct.md`)

A spatio-temporal identity network (STID) was trained on a Kaggle GPU (107 s, 0.03 GPU-hours) from aggregated road-cell residuals only, under the same protocol (history 1 to 24 Oct, tuning 25 Oct, test 26 to 31 Oct).

| | Deep model | History alone | Nowcast |
| --- | --- | --- | --- |
| Road-cell residual forecast, 15 / 30 / 60 min ahead (MAE) | **0.208 / 0.211 / 0.216** | 0.225 / 0.225 / 0.225 | 0.222 / 0.230 / 0.239 |

It forecast residuals better, but bus arrival times didn't improve: 136.5 s alone and 135.1 s as a 0.6 blend, against 134.7 s for the nowcast it was compared with (paired bootstrap: no gain). The nowcast was later re-tuned to 133.3 s. The deep model therefore stays out of the API.

---

## 7. Calendar and weather

- Gazetted weekday holidays are scored as weekdays: 2 Oct, 20 Oct and 26 Oct (Maharishi Valmiki Jayanti, inside the arrival test window; see §1).
- 15 Nov was Chhath Puja; 16 Nov had morning fog (Safdarjung visibility about 400 m at 06:30 to 07:30).
- GRAP stage III ran from 7 to 17 Nov; the India International Trade Fair at Bharat Mandapam (14 to 27 Nov) congests roads around Pragati Maidan.

---

## 8. Reproduce

```text
python scripts/ingest_dtc_hist.py             # October archive -> cleaned positions
python scripts/match_routes.py                # positions -> distance along each route
python scripts/build_speed_tables.py          # stop crossings, link traversals
python scripts/rebuild_all.py --from-step 3   # tables, service levels, model, grids, networks, arrival evaluation
python scripts/eval_rides.py                  # ride-only test
python scripts/eval_journeys.py ...           # door-to-door replay (see the script's --help)
python scripts/run_test_days.py               # process recorded November days
python scripts/score_eta_calculator.py        # ETA Calculator head to head
python scripts/compare_google.py              # Google Maps replay
python scripts/build_summary.py               # validation/results/summary.json
python scripts/build_docs_figures.py          # charts for the README
```
