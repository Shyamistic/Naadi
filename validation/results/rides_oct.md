# Ride-only ETA comparison, held-out 26 to 31 Oct 2026

Each row is a ride of 5 to 40 consecutive stops on one bus trip. History is 1 to 24 Oct; the nowcast is tuned on 25 Oct. The primary Naadi sample includes all observed gaps; the sensitivity excludes rides with any consecutive-stop gap over 10 minutes.

| Sample | n | mean error (min) | mean ride (min) | within 5 min | within 10 min | 5-9 stops | 10-20 stops | 21-40 stops |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Naadi, with >10 min gaps | 2,876,808 | 4.31 | 32.96 | 76.4% | 90.4% | 2.20 | 3.86 | 6.73 |
| Naadi, no >10 min gaps | 966,316 | 2.65 | 27.16 | 85.1% | 97.2% | 1.60 | 2.63 | 4.07 |

## Delhi Pulse published figure

The following is Delhi Pulse's own published figure on a different sample, shown for like-for-like context, not as a re-score of their data.

| Sample | mean error (min) | mean ride (min) | within 5 min | within 10 min | 5-9 stops | 10-20 stops | 21-40 stops |
|---|---:|---:|---:|---:|---:|---:|---:|
| Delhi Pulse published, different sample | published | 4.60 | 30.90 | 69.0% | 90.5% | 3.55 | 4.14 | 5.76 |

Source: `.agents/tasks/research-competitors-2026-11-17.md §1 (Validation) and §10 (idea 4)`.
