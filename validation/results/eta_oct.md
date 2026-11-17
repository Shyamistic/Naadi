# Bus ETA accuracy, held-out days 26 to 31 Oct 2026

Task: a bus is at a stop now; predict when it reaches a stop 1 to 30 stops ahead. 1,987,389 predictions from 112,777 bus trips. History from 1 to 24 Oct only; nowcast tuned on 25 Oct (window 1800 s, k_link 10, k_cell 3, tau 1000000000 s).

| Method | MAE (s) | MAPE | RMSE (s) | P90 error (s) | within 2 min | bias (s) |
|---|---|---|---|---|---|---|
| Official timetable | 273.6 | 33.5% | 531.4 | 687 | 50.9% | -91.4 |
| City speed curve | 235.1 | 27.3% | 489.3 | 588 | 56.8% | -121.1 |
| Historical average (link-hour) | 173.1 | 17.4% | 411.5 | 435 | 68.4% | -125.5 |
| Empirical-Bayes history | 168.8 | 17.3% | 406.0 | 415 | 69.1% | -114.4 |
| Naadi history (LightGBM) | 165.5 | 17.9% | 394.2 | 401 | 68.9% | -95.7 |
| Bus's own recent speed | 280.4 | 30.3% | 743.3 | 695 | 58.3% | -49.6 |
| Live only (last 30 min) | 157.2 | 18.2% | 366.4 | 383 | 68.7% | -76.7 |
| **Naadi (history + live nowcast)** | 134.7 | 15.5% | 331.9 | 315 | 72.8% | -70.7 |

MAE (s) by how far ahead:

| Method | 1-2 stops | 3-5 stops | 8-12 stops | 16-30 stops |
|---|---|---|---|---|
| Official timetable | 75 | 169 | 345 | 630 |
| City speed curve | 68 | 151 | 301 | 525 |
| Historical average (link-hour) | 45 | 102 | 215 | 412 |
| Empirical-Bayes history | 45 | 101 | 210 | 398 |
| Naadi history (LightGBM) | 46 | 101 | 206 | 384 |
| Bus's own recent speed | 65 | 155 | 349 | 692 |
| Live only (last 30 min) | 46 | 98 | 195 | 361 |
| **Naadi (history + live nowcast)** | 39 | 84 | 167 | 308 |

MAE (s) by time of day:

| Method | night 00-06 | morning peak 07-10 | midday 11-16 | evening peak 17-20 | late 21-23 |
|---|---|---|---|---|---|
| Official timetable | 264 | 210 | 288 | 414 | 208 |
| City speed curve | 97 | 190 | 280 | 357 | 174 |
| Historical average (link-hour) | 68 | 136 | 205 | 272 | 130 |
| Empirical-Bayes history | 68 | 132 | 200 | 267 | 127 |
| Naadi history (LightGBM) | 67 | 135 | 192 | 255 | 130 |
| Bus's own recent speed | 107 | 214 | 334 | 446 | 232 |
| Live only (last 30 min) | 74 | 131 | 177 | 235 | 134 |
| **Naadi (history + live nowcast)** | 66 | 113 | 152 | 199 | 112 |

With a per-horizon calibration factor fitted on 25 Oct for every method (fair to all):

| Method | MAE (s) | MAPE |
|---|---|---|
| Official timetable | 277.4 | 29.7% |
| City speed curve | 233.6 | 25.9% |
| Historical average (link-hour) | 164.2 | 17.0% |
| Empirical-Bayes history | 165.0 | 17.0% |
| Naadi history (LightGBM) | 166.0 | 17.5% |
| Bus's own recent speed | 284.2 | 29.7% |
| Live only (last 30 min) | 153.9 | 17.9% |
| **Naadi (history + live nowcast)** | 131.4 | 15.4% |

Paired cluster bootstrap over bus trips (1,000 resamples), MAE difference (negative = Naadi better):

- naadi_vs_live_only: -22.5 s, 95% CI [-23.0, -22.1], one-sided p = 0.000
- naadi_vs_gbm: -30.8 s, 95% CI [-31.4, -30.2], one-sided p = 0.000
- naadi_vs_ha: -38.4 s, 95% CI [-39.2, -37.7], one-sided p = 0.000
- naadi_vs_timetable: -138.9 s, 95% CI [-140.2, -137.5], one-sided p = 0.000
- gbm_vs_ha: -7.6 s, 95% CI [-8.0, -7.2], one-sided p = 0.000
