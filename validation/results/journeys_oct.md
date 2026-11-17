# Door-to-door journeys replayed on real buses (test days 2026_10_29, 2026_10_30, 2026_10_31)

Each planner's best journey for 190 OD pairs x 8 departure times per day, followed on the buses that actually ran. Calibration factors fitted on 2026_10_25, 2026_10_26; ranges calibrated on 2026_10_27, 2026_10_28.

| Planner | journeys | MAE (min) | median error (min) | bias (min) | within 10 min | MAE after calibration | 80% range coverage |
|---|---|---|---|---|---|---|---|
| Naadi (history) | 3,600 | 20.1 | 9.0 | -16.1 | 53% | 18.7 | 78% |
| Naadi (history + live) | 3,595 | 19.4 | 8.6 | -15.5 | 54% | 18.0 | 78% |
| Timetable planner | 3,330 | 27.2 | 13.8 | -24.1 | 42% | 23.8 | 79% |

Calibration factors (wait x, ride x): Naadi (history) 0.85, 1.16; Naadi (history + live) 0.80, 1.19; Timetable planner 1.75, 1.17
