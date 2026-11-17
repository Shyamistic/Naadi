# Naadi vs Google Maps, bus-only transit (2026-11-15, 2026-11-16)

187 Google answers sampled; 91 where both itineraries could be replayed on the buses that ran.

| | Google Maps | Naadi |
|---|---|---|
| Mean error of predicted door-to-door time (min) | 36.5 | 12.3 |
| Median error (min) | 26.7 | 7.2 |
| Bias (min, negative = too optimistic) | -36.4 | -4.1 |
| Predictions within 10 min | 22% | 63% |
| Median actual time of the recommended trip (min) | 59.6 | 45.0 |

Naadi minus Google mean error: -24.3 min (95% bootstrap CI -31.3 to -17.8). Naadi's recommended trip was actually faster in 73% of cases.

Google itinerary matching: {"google line '425' not matched": 5, 'ok': 97, "google line 'DW4' not matched": 2, "google line '740EXT.' not matched": 2, 'no bus observed': 11, 'boarding stop poorly captured': 17, "google line 'ETAWAHTOLONIVIABAH' not matched": 2, "google line '175' not matched": 2, "google line '118EXT.' not matched": 2, "google line 'CBD(+)' not matched": 2, "google line '214' not matched": 2, "google line 'KAROLBAGH-GURUGRAM' not matched": 2, "google line 'YELLOWLINE' not matched": 2, "google line '113EXT.' not matched": 2, "google line '73' not matched": 2, "google line '988' not matched": 2, "google line '33' not matched": 2, "google line '801STL' not matched": 2, "google line '116A' not matched": 2, "google line '136' not matched": 2, "google line '523' not matched": 2, "google line '990ASTL' not matched": 2, "google line 'DW3' not matched": 2, "google line '2001' not matched": 2, "google line '405' not matched": 2, 'no bus within 3 h': 1, "google line '130' not matched": 1, "google line '978' not matched": 1, "google line 'DS-22' not matched": 1, "google line '935' not matched": 1, "google line 'OMS(+)BURARI-DHAULAKUAN' not matched": 1, "google line '181A' not matched": 1, "google line '972' not matched": 1, "google line '221' not matched": 1, "google line 'YMS(+)' not matched": 1, "google line 'TMS(-)' not matched": 1, "google line '7104' not matched": 1, "google line '205' not matched": 1, "google line '429' not matched": 1, "google line '0740NS' not matched": 1}
