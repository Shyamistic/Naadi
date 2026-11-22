# Naadi (नाड़ी) · Dilli ki naadi, har pal

**Delhi bus journeys timed from real bus GPS.** Transport Stack Hackathon 2026, Problem 1: real-time bus traffic model and journey planner.

- **Live app:** https://13-235-147-97.sslip.io/
- **API and docs:** https://13-235-147-97.sslip.io/api/docs
- **Brief's example:** `GET https://13-235-147-97.sslip.io/api/journeys?from=28.665476,77.230173&to=Nehru%20Place&depart=2026-11-24T08:30`

Delhi's published bus timetable runs every hop at the same 18 km/h, all day. Real buses run at 35 km/h at 3 am and 16 km/h at 6 pm, and 70% of live trips are not in the timetable at all. Naadi does three things:
- learns stop-to-stop times for every route and hour from 38 million real bus traversals (October 2026);
- corrects them with what buses are doing in the last 30 minutes;
- plans door-to-door journeys on waits measured from the buses that really came.

| Test | Naadi | Comparison |
| --- | --- | --- |
| When will this bus reach a stop 1 to 30 stops ahead (1.99 M held-out predictions) | **134.7 s** mean error | timetable 273.6 s, historical average 173.1 s |
| Door-to-door time, replayed on the buses that actually ran (3,595 journeys) | **18.0 min** | timetable planner 23.8 min |
| Organisers' ETA Calculator, scored on its own 88,620 live answers | **8.0 min** (median 1.7) | ETA Calculator 12.5 min (median 7.3) |
| Google Maps bus directions, replayed (91 trips) | **12.3 min** | Google 36.5 min |

Methods and caveats: [technical note](docs/TECHNICAL_NOTE.md) and [validation report](docs/VALIDATION_REPORT.md).

## What the app does

- **Inputs:** origin and destination as coordinates, stop id (`stop:7571`) or name ("Kashmiri Gate" works), plus a departure time or "now".
- **Up to three options**, each with:
  - walk, boarding stop, route(s), alighting stop, transfers, final walk and total time;
  - an 80% range ("usually 54 to 70 min");
  - fare (non-AC/AC; free with a Pink Saheli card).
- **Common lines:** "take 405 or 402 or 411, whichever comes first", the way Delhi riders actually travel.
- **SamayChakra (समयचक्र):** the Ashoka Chakra's 24 spokes as the 24 hours. Each spoke is this trip's time at that hour, so the quieter hour the brief asks for stands out.
- **Leaving now:** the live nowcast applies, the next live buses are shown, and the first wait comes from the bus actually approaching.
- **Map layers:** live buses (anonymised) and a 3D road-speed layer by hour and weekday/weekend.
- **Languages:** Hindi and English.
- **Accuracy panel** with the numbers above.

## Repository

| Path | Contents |
| --- | --- |
| `naadi/` | Runtime: link-time grid, nowcast, network, RAPTOR router, common lines, live engine, replay, FastAPI app |
| `scripts/` | Pipeline and evaluation (ingest, match, stop crossings, tables, model, service levels, networks, evaluations, Google sampler) |
| `web/` | React + MapLibre GL + deck.gl app ("Dilli dusk" style over OpenFreeMap tiles) |
| `infra/` | AWS setup: limited deploy user, recorder server, API deploy with Caddy (HTTPS via sslip.io) |
| `validation/` | Fixed OD set and result tables (aggregates only) |
| `docs/` | Technical note, validation report, OpenAPI spec, proposal, demo-video script |
| `research/` | Background research and data audits |
| `tests/` | `pytest` suite |

## Run it yourself

Requirements: Python 3.11+, Node 20+, about 40 GB of free disk for the October archive work. Full instructions, including running only the web app against the live API, are in [docs/LOCAL_DEVELOPMENT.md](docs/LOCAL_DEVELOPMENT.md).

1. **Get the data.**
   - Register at https://delhi.transportstack.in. Download "Delhi Buses: GTFS Static Data" (v1-2) into `delhi_buses_static_gtfs_v1-2/`, and the historical archive from the hackathon page into the repo root.
   - For live data, request an OTD key (https://otd.delhi.gov.in/data/realtime/).
   - Copy `.env.example` to `.env` and fill in the keys. Never commit `.env`.
2. **Python setup:** `python -m venv .venv`, then `.venv\Scripts\python.exe -m pip install -r requirements.txt`.
3. **Pipeline:** `python scripts/ingest_dtc_hist.py`, then `python scripts/gtfs_fix.py`, `python scripts/match_routes.py`, `python scripts/build_speed_tables.py` and `python scripts/rebuild_all.py --from-step 3`. On one laptop (16 threads, 16 GB) this takes about 2 hours, mostly the archive ingest.
4. **API:** `uvicorn naadi.api:app --port 8000`. Live data appears when `scripts/record_feed.py` is running; it publishes `data/live/latest.pb`.
5. **Web:** `cd web && npm ci && npm run dev`, then open http://localhost:5173. By default `/api` goes to the live API; set `NAADI_API_TARGET=http://127.0.0.1:8000` to use your local one.
6. **Tests:** `python -m pytest -q tests`.
7. **Deploy:** `python infra/deploy_api.py` (AWS profile `naadi`).

## Data, licence and credits

- **Bus data:** Delhi Transport Stack (delhi.transportstack.in) and Delhi Open Transit Data (Department of Transport, GNCTD; IIIT-Delhi). Raw data is not redistributed, as Transport Stack Licence 1.0 requires; this repo holds code and aggregate results only. Vehicle ids (licence plates) never leave the pipeline.
- **Map:** © OpenStreetMap contributors, tiles by OpenFreeMap. Fares are indicative, from the Delhi Tourism city-bus table.
- **Open-source libraries:** DuckDB, Polars, PyArrow, LightGBM, Numba, NumPy, SciPy, scikit-learn, FastAPI, Uvicorn, gtfs-realtime-bindings, React, Vite, MapLibre GL JS, deck.gl, Caddy.
- **Methods:**
  - RAPTOR (Delling, Pajor & Werneck 2014);
  - optimal strategies for common lines (Chriqui & Robillard 1975; Spiess & Florian 1989);
  - empirical-Bayes shrinkage;
  - gradient-boosted trees (Ke et al. 2017);
  - split conformal prediction (Romano et al. 2019).
- **AI assistance:** built with AI coding assistance (Kiro), which the hackathon rules allow. Design, data checks and results are reviewed in this repository.
- **Code licence:** MIT (see `LICENSE`).
