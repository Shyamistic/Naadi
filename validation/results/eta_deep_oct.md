# Deep spatio-temporal forecaster, October 2026

The fixed ETA protocol is unchanged: history 1--24 Oct, nowcast tuning on 25 Oct, and held-out test 26--31 Oct.

Kaggle dataset: `shyam31415/naadi-deep-input-v1` (private). Kernel: `shyam31415/naadi-deep-stid-v1` v7. CUDA STID training took 107.4 seconds, or 0.0298 GPU-hours.

## Cell residual forecast

| Horizon | Deep MAE | Zero/history MAE | Current nowcast MAE | n |
|---|---:|---:|---:|---:|
| 15min | 0.2077 | 0.2251 | 0.2220 | 3,126,263 |
| 30min | 0.2114 | 0.2252 | 0.2301 | 3,128,784 |
| 60min | 0.2158 | 0.2252 | 0.2385 | 3,132,389 |

Blend weight tuned on 25 Oct: **0.6** (deep residual weight).

## Multi-hop ETA

| Method | MAE (s) | RMSE (s) | P90 (s) | Bias (s) |
|---|---:|---:|---:|---:|
| gbm | 165.5 | 394.2 | 401.1 | -95.7 |
| naadi | 134.7 | 331.9 | 314.6 | -70.7 |
| deep | 136.5 | 342.8 | 316.6 | -79.1 |
| blend | 135.1 | 338.4 | 313.7 | -77.0 |

Paired bootstrap over bus trips, 1,000 resamples. Negative MAE difference means the compared method is better:

- deep_vs_naadi: +1.8 s, 95% CI [+1.6, +2.0], one-sided p=1.000
- blend_vs_naadi: +0.4 s, 95% CI [+0.3, +0.6], one-sided p=1.000
- gbm_vs_naadi: +30.8 s, 95% CI [+30.2, +31.4], one-sided p=1.000

Interpretation: a method helps only if its held-out MAE is lower than current Naadi and the paired interval supports the difference. No improvement is claimed from tuning-day results.
