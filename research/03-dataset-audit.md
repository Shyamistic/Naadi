# Dataset audit and gap list

Audited 13 Nov 2026, 19:00 to 19:30 IST, on the files in this repo and a 2-minute sample of the live feed. Raw data stays out of git (Transport Stack Licence 1.0 forbids redistributing it on its own); see `.gitignore`.

---

## 1. Summary

- **The bus timetable you downloaded (`delhi_buses_static_gtfs_v1-2`) matches the live feed.** 98% of live route IDs exist in it, and 80% of buses sit within 300 m of a stop on their claimed route, against 3% for a randomly assigned route. Earlier audits of the 2023 archive found no usable match, so this removes the biggest data risk.
- **Its times carry no information.** Every stop-to-stop hop runs at exactly 18.01 km/h straight-line speed in every hour of the day, and arrival always equals departure. Real travel times must come entirely from GPS.
- **The live feed is healthy:** 5,690 buses, refreshed every 11 to 12 s. There is no speed, bearing or stop field. 70% of trips are unscheduled (`ADDED`). 2% of positions are more than 5 minutes old.
- **The metro timetable has expired** (calendar ends 31 Dec 2025) and has no Sunday trips and only 59 Saturday trips. It needs an updated feed or a documented fix before metro legs can be trusted.
- **The Papli AI layers (streetlights, subways, road widths) cover only central Delhi**, roughly a 15 × 18 km box. 97% of road rows have image coordinates that disagree with the point coordinates. Use them as hints, not as ground truth.
- **A stopgap recorder is running on this laptop** (`scripts/record_feed.py`). It writes one Parquet file per hour to `data/raw/rt/` and stops if the laptop sleeps or shuts down. It moves to AWS in the implementation phase.

---

## 2. What is in the repo

### 2.1 Bus static GTFS v1-2 (DTC + DoT)

| Item | Value |
| --- | --- |
| Stops / routes / trips | 6,812 / 2,554 (DTC 1,619, DoT 935) / 65,322 |
| Stop times / shapes | 2,385,381 / 2,554 shapes, 765,633 points. Every trip has a shape |
| Route naming | Direction in the name: 1,252 `…UP`, 1,231 `…DOWN`, 71 with suffixes (`116AUP2`). No `direction_id` |
| Trips per route | Median 18 (P10 2, P90 61, max 123) |
| Trip ids | `route_HH_MM`, e.g. `1000_06_10` |
| Calendar | One service, every day, 2025-01-01 to 2040-01-01. No weekday/weekend difference |
| Times | Arrival = departure in all 2.39 M rows (no dwell). Straight-line speed 18.01 km/h in every hour |
| Fares | `fare_stage` is a 0/1 boundary flag (229,499 boundaries). No `fare_attributes` or `fare_rules` files, despite the metadata listing them |
| Stops | Extend to lat 28.21–29.34, lon 76.60–77.43 (NCR beyond Delhi). 1,254 stop pairs within ~20 m of each other (opposite sides of a road or duplicates). English names only |
| Version | The brief and DLM1 metadata say 10,559 stops / 2,403 routes / 89,393 trips. This file is a different version, but it is the one the live feed uses |

### 2.2 Live feed (OTD key, 10 polls, 13 Nov 2026 ~19:17 IST)

| Check | Result |
| --- | --- |
| Buses | 5,683 to 5,686 per poll; 5,690 distinct |
| Refresh | Header every 11 to 12 s; per-bus update gap median 11 s, P90 22 s |
| Fields present (100%) | `trip_id`, `route_id`, `start_time`, `start_date`, `vehicle.id`, `vehicle.label` |
| Fields absent | Speed, bearing, `stop_id`, `current_status`, occupancy, congestion |
| Trip type | `ADDED` 4,004 (70%), `SCHEDULED` 1,679 |
| Position age | Median 18 s, P90 247 s; 128 buses older than 5 min |
| Join with static | Route ids 98% (1,361 of 1,391). Trip ids 7%, because unscheduled trips carry their real start time |
| Spatial check | 80% within 300 m of a stop on the claimed route; 3% for random routes |
| Vehicle ids | Licence plates. `DL51EV…` 1,052 (electric series), the rest mostly `DL1PD…`. The catalog's "DTC buses coming soon" note may be out of date; confirm with organisers |
| Volume | 580 KB per poll, about 4.5 GB/day raw. The recorder keeps only changed positions in Parquet, plus one raw snapshot every 10 min |

### 2.3 Delhi Metro GTFS (DMRC v1)

| Item | Value |
| --- | --- |
| Size | 262 stations, 36 directional routes (all lines plus Rapid Metro Gurugram), 5,438 trips, 128,434 stop times |
| Quality | Real dwell (20 s), `shape_dist_traveled`, timepoints |
| Problems | Calendar ends **2025-12-31** (expired). Trips: weekday 5,379, Saturday 59, **Sunday 0** |
| Station names | 71 of 264 names in the gate file do not match GTFS names exactly. Most are spelling variants ("Mansrover park"); some may be stations added since the feed was built. Needs a station crosswalk |

### 2.4 Other files

| File | Content | Use | Caveat |
| --- | --- | --- | --- |
| `dmrc_station_and_gate_locations.xlsx` | 264 stations (line, code, elevated/underground, interchange) and 687 gates with coordinates | Walk to the exact gate | Coordinates stored as text with N/E suffix |
| `dmrc_station_details_with_parking.xlsx` | 261 stations: toilets, parking by vehicle type, parking coordinates | Park-and-ride, amenities | |
| `ncrtc_static_gtfs_v1` (Namo Bharat) | 16 stations Jangpura/Sarai Kale Khan to Modipuram, 2 routes, 130 trips, calendar to 2029 | Rapid rail legs | `route_type` = 3 (bus); should be 2 (rail) |
| `shared_mobility_gtfs_v1` (IIIT Delhi survey) | 316 e-rickshaw and shared-auto routes, 1,900 stops, frequency-based (typically every 5 min), shapes | First and last mile | Survey data; frequencies are estimates |
| `pathways.zip` (DMRC accessibility) | 220 stations, 2,433 gates/lifts/platforms, 1,635 lift links (GTFS Pathways) | Step-free flags | No lengths or times; child nodes share the station's coordinates; README says Red, Yellow and Pink lines |
| `Data Layer 01_Streetlight.xlsb` | 39,766 points with streetlight counts | Lit walking routes at night | Central Delhi only |
| `Data Layer 03_Subway.xlsb` | 417 pedestrian subway locations | Safe road crossings | Central Delhi only |
| `Data Layer 04_Road.xlsb` | 104,444 points with road width (ft) | Phase 2 Problem 4 | Central Delhi only; widths P5–P95 6.8–25 ft, none over 12 m; 97% image/point coordinate mismatch |

---

## 3. Multimodal decision: yes, bus-first

1. **The brief allows it.** It says multimodal journeys are "a welcome extension but not required".
2. **The brief's own example needs it.** Kashmere Gate ISBT → Nehru Place is a direct Violet Line metro ride. A bus-only planner would return options worse than what any Delhi commuter already knows.
3. **The data is already here:** metro, gates, Namo Bharat and shared autos.
4. **Scoring stays clean.** Bus-only journeys are validated against observed bus trips and Google (bus-only), as the brief asks. Multimodal results are reported separately.

How each mode is timed:

| Mode | Source of time |
| --- | --- |
| Bus legs | Our GPS-trained model (the core contribution) |
| Metro and Namo Bharat legs | Timetables, plus gate-to-platform walking |
| Shared autos | Survey frequencies, with wide uncertainty |

**Blocker:** the expired metro calendar and missing weekend trips. Get an updated DMRC feed. If none arrives, apply the weekday pattern with a visible "schedule estimated" label.

---

## 4. What else is needed

### 4.1 From you (account actions)

| # | Item | Why | Status |
| --- | --- | --- | --- |
| 1 | Transport Stack API key (DLM7 live feed, DLM18 static API) | Second feed with failover; detect timetable updates | Waiting for email. Put it in `.env` as `DTS_API_KEY` |
| 2 | **ETA Calculator for Buses** (Transport Stack service 1) | The organisers' own ETA: the most relevant baseline to beat | Request in progress. Please save its Introduction and Access PDFs into `research/_dts/` |
| 3 | Approval-based DLM4 (hourly metro footfall), DLM8/DLM9 (metro OD) | Phase 2 (Problems 3 to 5) | Request now; approval is manual |
| 4 | Email to organisers | (a) historical GPS traces: dates, format; (b) the 10,559-stop timetable version and whether it replaces v1-2; (c) an updated DMRC GTFS (expired calendar, no Sunday trips); (d) whether DLM7 now includes DTC buses; (e) a DTC fare table | Not sent |
| 5 | Google Cloud project with Maps Platform billing | Routes API for the required Google comparison (India free tier: 35K to 70K calls per product per month) | Not started |
| 6 | AWS access (an IAM user or role limited to EC2, S3, CloudFront, SSM and Budgets) | Move the recorder and host the backend | Not started |
| 7 | Kaggle API token from each account owner | Automated training runs | Not started |
| 8 | Keep this laptop awake and online until the recorder moves to AWS | Every missed hour is lost history | Recorder running now |

### 4.2 Public data I will fetch (no account needed)

| Data | Source | Use |
| --- | --- | --- |
| Road and footpath network, signals, crossings, Hindi names (`name:hi`) | OpenStreetMap extract for Delhi NCR (Geofabrik / BBBike) | Map matching, road links, walking, signals, bilingual search |
| Building footprints and heights | Overture Maps buildings; Google Open Buildings 2.5D Temporal (India, CC BY 4.0) | 3D city |
| Places and landmarks | Overture Maps places, OSM | Search ("Nehru Place", "AIIMS") |
| Weather (rain, fog, temperature) | Open-Meteo historical and forecast | Model feature (winter fog matters in Nov–Dec) |
| Air quality and GRAP stage | CPCB via OpenAQ; CAQM GRAP orders | GRAP III/IV restricts vehicles, which changes traffic |
| Holidays and events | 2026 gazetted holidays; wedding-season dates; major events | Model feature and validation strata |
| DTC fare chart | DTC public fare notices | Fill the missing fare tables |
| Basemap tiles | Protomaps (PMTiles) Delhi extract | Self-hosted 2D/3D map |

### 4.3 Ground truth

| Item | Status |
| --- | --- |
| 15 to 30 recorded rides with a phone GPS logger | Needs someone in Delhi. Not answered yet |
| Google Routes sampler on a fixed OD set (transit looks back 7 days; driving with traffic is live only) | Starts once item 5 exists |

---

## 5. Update, 15 Nov 2026

### 5.1 Recorder outage

The first recorder stopped on 13 Nov around 19:30 IST and saved nothing. It only wrote a file once an hour, and the laptop slept and restarted before the first hour closed. About 46 hours of history were lost.

Fix: the recorder now writes every 5 minutes and runs as a detached process (restarted 15 Nov 17:21). Volume is about 16 MB/hour, roughly 400 MB/day; 30 GB is free. It still stops if the laptop restarts or sleeps (sleep after 25 min on AC, 10 min on battery). Moving it to AWS is the real fix.

### 5.2 ETA Calculator for Buses (Transport Stack service 1)

| Check | Result |
| --- | --- |
| Endpoints | `GET /api/serviceset/eta-calculator/bus/etas?vehicle_id=` and `/stop/etas?stop_id=`, header `x-api-key` (key in `.env` as `ETA_API_KEY`, valid to 14 Nov 2027) |
| IDs | Same route and stop ids as our static GTFS v1-2 (90 of 90 routes matched; stop names match) |
| Bus endpoint | ETA in whole minutes to every remaining stop (median 22 stops), with stop index and stops in between. 85 to 88% of requests succeed; the rest return HTTP 502. Latency median 1.5 s |
| Stop endpoint | All 25 sampled stops answered. Lists buses arriving within 30 minutes only, in whole minutes, plus bus attributes: AC/non-AC, agency (`dtc`/`dimts`), colour (`red`, `light_blue`, …). Refresh 30 s |
| Uncertainty | None. Single point estimates |
| Rate limits | No rate-limit headers seen |

This is the organisers' own ETA and the most relevant baseline. A logger (`scripts/log_eta_baseline.py`) now records its predictions every 60 s for 30 random live buses and 30 busy stops spread across the city (about 1 request per second). Scoring them against arrivals in our GPS archive gives its error by horizon on exactly the same trips as our model.

### 5.3 Metro hourly footfall (`stationwise_hourly_entry_exit_february_2024.xlsx`)

Despite the file name, it covers **1 Sep 2024 to 28 Feb 2025**: 181 days, 247 stations, 10 lines, hourly entries and exits (04:00 to 00:59), no missing cells. Average 2.87 M entries per day (range 1.26 M to 3.46 M). City-wide entries peak at 09:00 (263K) and 18:00 (289K). Uses: Phase 2 (Problems 3 to 5) and demand weighting at metro-bus interchanges. It is about two years old, so treat levels as approximate.

### 5.4 Google Maps Demo Key (15 Nov)

A Maps Demo Key (no billing account) is stored in `.env` as `GOOGLE_MAPS_API_KEY`. Usage pauses at a daily limit that Google does not publish; there are no charges.

| Check (Kashmere Gate ISBT → Nehru Place) | Result |
| --- | --- |
| Transit, bus only, future departure | Works. 4 options; best is route 425, 30 stops, 64.7 min door to door, 50.9 min on the bus |
| Transit, departure 2 days in the past | Works |
| Transit, any mode | Works. Violet Line metro, 14 stops, 43.9 min |
| Driving with live traffic (Pro feature) | Works. 48.5 min with traffic against 41.4 min without |

**Finding:** Google's bus answers for Friday 13 Nov and Tuesday 17 Nov at 08:30 are identical to the second (boards 08:44:13, 3,880 s). Its planned Delhi bus times look timetable-based, with no day-to-day or traffic variation. Its pace (30 stops in 50.9 min) is close to the official 18 km/h template. Google's stop names ("Dr. BR Ambedkar University") are not in our v1-2 feed, so it uses a different timetable version. Whether Google adjusts trips departing "now" for live traffic is still to be tested.

---

## 6. Status

| Area | State |
| --- | --- |
| Research | Done (`01`, `02`, this file) |
| Python 3.13 venv (`.venv`) | Done |
| Secrets | Local `.env` (git-ignored); server reads SSM Parameter Store `/naadi/*`. AWS work uses IAM user `naadi-deploy`; root key removed from disk. Budget `naadi-hosting-cap` US$20 with alerts. Transport Stack feed key pending |
| Live feed recorder | AWS server `naadi-server` (t4g.small, Mumbai) since 15 Nov 18:15 IST, synced to private S3 every 10 min. Laptop keeps a backup copy (logon task "Naadi feed recorder"; sleep on charger disabled) |
| ETA baseline logger | AWS server since 15 Nov 18:15 IST (laptop copy ran 17:30 to 18:20, then stopped) |
| Metro footfall | Received and profiled |
| Public data downloads (§4.2) | Not started |
| Implementation plan | Next |

---

## 7. Draft email to the organisers

To: transportstack.hackathon@gmail.com, csm@iiitd.ac.in

Subject: Transport Stack Hackathon 2026, Problem 1: data questions

> Hello,
>
> We are registered for the Transport Stack Hackathon 2026 and working on Problem 1. We have five data questions:
>
> 1. Historical GPS traces: the brief mentions several weeks of historical bus positions. When will these be shared, which dates do they cover, and in what format?
> 2. Static GTFS version: the DLM1 metadata lists 10,559 stops, 2,403 routes and 89,393 trips, but the file we downloaded (`delhi_buses_static_gtfs_v1-2`) has 6,812 stops, 2,554 routes and 65,322 trips. The live feed's route ids match v1-2. Which version should we use, and is the larger one available?
> 3. Delhi Metro GTFS: the DMRC static feed's calendar ends on 31 Dec 2025 and has no Sunday trips. Is an updated feed available?
> 4. Fleet coverage: does the DLM7 / OTD real-time feed now include all DTC buses, or only former cluster buses?
> 5. Fares: the bus static feed has fare stages but no fare tables. Is there an official fare table we can use?
>
> Thank you,
> [Name], [Team name]