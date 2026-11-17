# Bus ETA accuracy, held-out days 26 to 31 Oct 2026

Task: a bus is at a stop now; predict when it reaches a stop 1 to 30 stops ahead. 1,369,867 predictions from 146,032 bus trips. History from 1 to 24 Oct only; nowcast tuned on 25 Oct (window 1800 s, k_link 10, k_cell 3, tau 9600 s).

| Method | MAE (s) | MAPE | RMSE (s) | P90 error (s) | within 2 min | bias (s) |
|---|---|---|---|---|---|---|
| Official timetable | 260.8 | 33.4% | 500.7 | 658 | 51.6% | -85.1 |
| City speed curve | 224.5 | 27.5% | 460.5 | 563 | 57.5% | -110.1 |
| Historical average (link-hour) | 163.7 | 17.4% | 385.4 | 410 | 69.2% | -114.7 |
| Empirical-Bayes history | 159.4 | 17.4% | 378.7 | 391 | 69.9% | -103.5 |
| Naadi history (LightGBM) | 154.7 | 18.0% | 361.5 | 375 | 69.5% | -79.0 |
| Bus's own recent speed | 301.4 | 35.0% | 764.1 | 748 | 55.3% | -19.0 |
| Live only (last 30 min) | 151.0 | 18.3% | 346.5 | 368 | 69.2% | -70.5 |
| **Naadi (history + live nowcast)** | 129.5 | 15.7% | 314.4 | 302 | 73.3% | -64.2 |

MAE (s) by how far ahead:

| Method | 1-2 stops | 3-5 stops | 8-12 stops | 16-30 stops |
|---|---|---|---|---|
| Official timetable | 75 | 166 | 338 | 606 |
| City speed curve | 68 | 149 | 295 | 505 |
| Historical average (link-hour) | 45 | 100 | 208 | 394 |
| Empirical-Bayes history | 45 | 98 | 203 | 379 |
| Naadi history (LightGBM) | 46 | 98 | 198 | 361 |
| Bus's own recent speed | 72 | 171 | 387 | 755 |
| Live only (last 30 min) | 46 | 96 | 192 | 351 |
| **Naadi (history + live nowcast)** | 40 | 83 | 164 | 301 |

MAE (s) by time of day:

| Method | night 00-06 | morning peak 07-10 | midday 11-16 | evening peak 17-20 | late 21-23 |
|---|---|---|---|---|---|
| Official timetable | 260 | 205 | 275 | 368 | 202 |
| City speed curve | 95 | 185 | 267 | 317 | 167 |
| Historical average (link-hour) | 69 | 132 | 193 | 240 | 122 |
| Empirical-Bayes history | 69 | 128 | 188 | 234 | 118 |
| Naadi history (LightGBM) | 67 | 130 | 179 | 220 | 121 |
| Bus's own recent speed | 125 | 245 | 356 | 431 | 239 |
| Live only (last 30 min) | 75 | 128 | 170 | 211 | 126 |
| **Naadi (history + live nowcast)** | 67 | 110 | 147 | 178 | 104 |

With a per-horizon calibration factor fitted on 25 Oct for every method (fair to all):

| Method | MAE (s) | MAPE |
|---|---|---|
| Official timetable | 265.8 | 29.6% |
| City speed curve | 225.5 | 26.0% |
| Historical average (link-hour) | 158.2 | 17.2% |
| Empirical-Bayes history | 158.7 | 17.1% |
| Naadi history (LightGBM) | 161.2 | 17.6% |
| Bus's own recent speed | 302.0 | 33.5% |
| Live only (last 30 min) | 148.7 | 18.1% |
| **Naadi (history + live nowcast)** | 128.3 | 15.5% |

Paired cluster bootstrap over bus trips (1,000 resamples), MAE difference (negative = Naadi better):

- naadi_vs_live_only: -21.5 s, 95% CI [-22.0, -21.1], one-sided p = 0.000
- naadi_vs_gbm: -25.2 s, 95% CI [-25.7, -24.8], one-sided p = 0.000
- naadi_vs_ha: -34.3 s, 95% CI [-34.9, -33.6], one-sided p = 0.000
- naadi_vs_timetable: -131.3 s, 95% CI [-132.4, -130.2], one-sided p = 0.000
- gbm_vs_ha: -9.0 s, 95% CI [-9.4, -8.6], one-sided p = 0.000
