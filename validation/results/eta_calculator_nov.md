# Head-to-head with the Transport Stack ETA Calculator (2026_11_15, 2026_11_16)

88,620 logged ETA Calculator answers for live buses, scored against when each bus actually reached the stop.

| Method | MAE (min) | median error (min) | within 2 min | bias (min) | 0-5 min | 5-10 min | 10-20 min | 20-40 min | 40+ min |
|---|---|---|---|---|---|---|---|---|---|
| ETA Calculator (Transport Stack) | 12.50 | 7.26 | 12.4% | +0.88 | 6.12 | 6.78 | 7.95 | 9.70 | 26.15 |
| Naadi history | 8.99 | 2.53 | 43.8% | -2.94 | 1.20 | 2.15 | 3.57 | 5.85 | 25.17 |
| Naadi history + live | 8.01 | 1.65 | 55.3% | -5.15 | 1.01 | 1.68 | 2.71 | 4.40 | 23.86 |
