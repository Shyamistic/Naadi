# Bus ETA accuracy, held-out days 26 to 31 Oct 2026

Task: a bus is at a stop now; predict when it reaches a stop 1 to 30 stops ahead. 1,987,389 predictions from 112,777 bus trips. History from 1 to 24 Oct only; nowcast tuned on 25 Oct (window 1200 s, k_link 5, k_cell 1, tau 9600 s; tuning MAE 112.4 s). LNKF noise q=0.01, r=1.0 was tuned on 25 Oct only.

| Method | MAE (s) | MAPE | RMSE (s) | P90 error (s) | within 2 min | bias (s) |
|---|---|---|---|---|---|---|
| Official timetable | 273.6 | 33.5% | 531.4 | 687 | 50.9% | -91.4 |
| City speed curve | 235.1 | 27.3% | 489.3 | 588 | 56.8% | -121.1 |
| Historical average (link-hour) | 173.1 | 17.4% | 411.5 | 435 | 68.4% | -125.5 |
| Empirical-Bayes history | 168.8 | 17.3% | 406.0 | 415 | 69.1% | -114.4 |
| Naadi history (LightGBM) | 165.5 | 17.9% | 394.2 | 401 | 68.9% | -95.7 |
| Bus's own recent speed | 280.4 | 30.3% | 743.3 | 695 | 58.3% | -49.6 |
| Live only (last 30 min) | 157.2 | 18.2% | 366.4 | 383 | 68.7% | -76.7 |
| LNKF (published log-normal Kalman) | 163.1 | 18.3% | 386.4 | 389 | 68.7% | -77.3 |
| **Naadi (history + live nowcast)** | 133.3 | 15.6% | 328.5 | 309 | 72.9% | -67.8 |

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
| LNKF (published log-normal Kalman) | 46 | 101 | 204 | 374 |
| **Naadi (history + live nowcast)** | 39 | 83 | 165 | 305 |

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
| LNKF (published log-normal Kalman) | 72 | 131 | 189 | 252 | 131 |
| **Naadi (history + live nowcast)** | 66 | 112 | 150 | 196 | 112 |

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
| LNKF (published log-normal Kalman) | 163.0 | 17.7% |
| **Naadi (history + live nowcast)** | 130.2 | 15.5% |

Paired cluster bootstrap over bus trips (1,000 resamples), MAE difference (negative = Naadi better):

- naadi_vs_live_only: -23.9 s, 95% CI [-24.5, -23.4], one-sided p = 0.000
- naadi_vs_gbm: -32.2 s, 95% CI [-32.8, -31.6], one-sided p = 0.000
- naadi_vs_ha: -39.8 s, 95% CI [-40.6, -39.1], one-sided p = 0.000
- naadi_vs_timetable: -140.3 s, 95% CI [-141.6, -138.9], one-sided p = 0.000
- gbm_vs_ha: -7.6 s, 95% CI [-8.0, -7.2], one-sided p = 0.000

Calendar and weather strata (Naadi raw; 26 Oct is a gazetted holiday but remains a weekday in the primary run):

| Stratum | n | MAE (s) | bias (s) |
|---|---:|---:|---:|
| 2026_10_26 | 243854 | 125.21186129918296 | -55.83564463249406 |
| 2026_10_27 | 274943 | 139.58130192444216 | -72.30489783234793 |
| 2026_10_28 | 307136 | 140.13449734244918 | -73.18616058906899 |
| 2026_10_29 | 367268 | 110.12321637957454 | -33.91099249563001 |
| 2026_10_30 | 342679 | 132.23732050842645 | -67.96371240720124 |
| 2026_10_31 | 451509 | 148.74439265324625 | -95.19174488933422 |
| foggy_morning | 0 | n/a | n/a |
| non_foggy_morning | 725730 | 96.05673798621123 | -48.592988094183546 |

Holiday sensitivity for 26 Oct: standard weekday MAE 125.2 s; treating the gazetted holiday as weekend gives 152.8 s.

The signed Naadi bias becomes more early at longer horizons (from -6.7 s at 1 stops to -251.1 s at 30 stops). With tau at 1e9 s, the live correction does not decay; this persistent correction is a plausible mechanism for the accumulating early error.

LNKF is the published log-normal Kalman baseline described by Achar et al. (arXiv:1904.03444) and Bhutani, Pachal & Achar (arXiv:2210.01655).
