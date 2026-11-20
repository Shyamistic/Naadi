# Door-to-door journeys, v2 (2026-10-29, 2026-10-30, 2026-10-31)

Held-out protocol: factors fitted on 25-26 Oct; grouped ranges calibrated on 27-28 Oct; test metrics on 29-31 Oct.

| Planner | Raw MAE (min) | Calibrated MAE (min) | Test n |
|---|---:|---:|---:|
| Naadi (history) | 19.6 | 17.9 | 3613 |
| Naadi (nowcast) | 19.0 | 17.3 | 3606 |
| Naadi (history + live) | 17.7 | 15.5 | 3598 |
| Timetable planner | 26.5 | 22.9 | 3366 |

## Calibration factors

| Planner | Wait history | Live wait | Ride |
|---|---:|---:|---:|
| Naadi (history) | 0.85 | 1.00 | 1.18 |
| Naadi (nowcast) | 0.80 | 1.00 | 1.20 |
| Naadi (history + live) | 1.40 | 0.90 | 1.14 |
| Timetable planner | 1.85 | 1.00 | 1.17 |

## Ranges

| Planner | Coverage | Median width (min) |
|---|---:|---:|
| Naadi (history) | 77.5% | 47.2 |
| Naadi (history + live) | 78.1% | 40.0 |

## Old versus v2

The previous `journeys_oct` aggregate remains untouched and is included in `journeys.legacy` in the JSON for side-by-side review.
