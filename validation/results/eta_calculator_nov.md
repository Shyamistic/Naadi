# Fair head-to-head with the Transport Stack ETA Calculator (2026_11_15, 2026_11_16)

Headline variant: **same_fix**, chosen because it gives the ETA Calculator the lower MAE. 9,616 same-run cases.

## Headline table

| Method | MAE (min) | median error (min) | within 2 min | bias (min) | 0-5 min | 5-10 min | 10-20 min | 20-40 min | 40+ min |
|---|---|---|---|---|---|---|---|---|---|
| ETA Calculator (Transport Stack) | 9.69 | 6.97 | 12.2% | +4.17 | 6.14 | 6.61 | 8.03 | 9.76 | 15.50 |
| Naadi history | 9.42 | 6.65 | 8.1% | +4.97 | 5.70 | 6.17 | 7.40 | 9.43 | 15.85 |
| Naadi history + live | 7.38 | 4.93 | 13.1% | +2.58 | 5.02 | 5.02 | 5.68 | 6.75 | 12.81 |

## Other anchor

| Method | MAE (min) | median error (min) | within 2 min | bias (min) | 0-5 min | 5-10 min | 10-20 min | 20-40 min | 40+ min |
|---|---|---|---|---|---|---|---|---|---|
| ETA Calculator (Transport Stack) | 9.73 | 6.99 | 12.2% | +4.16 | 6.13 | 6.58 | 8.05 | 9.86 | 15.45 |
| Naadi history | 5.82 | 2.34 | 45.7% | +0.40 | 1.19 | 1.91 | 3.57 | 5.99 | 13.16 |
| Naadi history + live | 4.81 | 1.54 | 57.0% | -1.66 | 1.03 | 1.50 | 2.70 | 4.59 | 11.54 |

As-served anchors both methods at the request; same-fix anchors both at the Calculator's vehicle_ts. The Calculator fix is 266 s older at the median (p10-p90 198-351 s).

Actuals use the same vehicle run, split after a gap over 1,200 s or a backward jump over 1,000 m. Dropped no-same-run cases: 0; cases without a usable same-run fix: 530.
