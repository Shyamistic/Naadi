# Running Naadi locally

Checked on 22 Nov 2026 on the project laptop (Windows 11, PowerShell). On macOS or Linux, use `.venv/bin/python` and `export NAME=value` instead of the Windows forms.

There are two ways to run it:

| Mode | What runs locally | Needs the data folder? | Use it for |
| --- | --- | --- | --- |
| A. Web only | The web app (Vite dev server). `/api` goes to the live API | No | Frontend work |
| B. Full stack | The API from this checkout, plus the web app pointed at it | Yes (`data\processed\model`, about 180 MB of artefacts) | Backend and model work, end-to-end checks |

## Prerequisites

| Tool | Version | Notes |
| --- | --- | --- |
| Python | 3.11 or newer (tested with 3.13.9) | |
| Node.js and npm | Node 20 or newer (tested with 24.16 and npm 11.13) | |
| Google Chrome | Current | The Playwright tests run in the installed Chrome (`channel: 'chrome'`) |
| Git | Any recent version | |
| Disk, full pipeline only | About 40 GB free | The October archive is 16.1 GB packed and 124 GB unpacked. The ingest extracts one day at a time and deletes it after conversion |

## No database

There is no database server and nothing to migrate. The pipeline (`scripts\`) runs DuckDB in-process over Parquet files and writes artefacts to `data\processed\model\`. At startup, the API loads those artefacts and `validation\results\*.json` into memory. On this laptop it uses about 0.5 GB.

The `data\` folder is gitignored, except the street-walking tables in `data\processed\model\walk_v1\`. A fresh clone can therefore only run mode A, until the aggregate model tables are published or the pipeline is run (see "Data" below).

## Install

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
cd web
npm ci
cd ..
```

`requirements.txt` covers the API runtime, the data pipeline and the tests. The AWS server installs only `infra\requirements-api.txt`, the API's runtime needs.

## Environment variables

Copy `.env.example` to `.env` and fill in the keys you need. Never commit `.env`.

| Variable | Read by | Needed for |
| --- | --- | --- |
| `OTD_API_KEY` | `scripts\record_feed.py`, `scripts\probe_feed.py`, `scripts\log_eta_baseline.py` | The live GTFS-RT feed (recording, live mode). Request a key at https://otd.delhi.gov.in/data/realtime/ |
| `ETA_API_KEY` | `scripts\log_eta_baseline.py`, `scripts\probe_eta.py` | Logging the organisers' ETA Calculator for the head-to-head test |
| `GOOGLE_MAPS_API_KEY` | `scripts\google_sampler.py` | Sampling Google Maps bus directions for the Google comparison |
| `DTS_API_KEY` | Not read by the current code | Kept for Transport Stack portal downloads |

Optional overrides, all read by the API:

| Variable | Default | Purpose |
| --- | --- | --- |
| `NAADI_ROOT` | This checkout | The folder that holds `data\`. Set it when running from a git worktree, which has no `data\` |
| `NAADI_NETWORK` | `network_prod`, or `network_prod_mm` when it exists | Routable network (bus only, or bus plus metro, Namo Bharat and shared autos) |
| `NAADI_GRID`, `NAADI_TABLES` | `grid_oct_all.parquet`, `oct_all` | Link-time grid and history tables |
| `NAADI_CALIBRATION`, `NAADI_INTERVALS` | `calibration_v2.json`, `intervals_v2.json` | Calibration factors and range parameters |
| `NAADI_SNAPSHOT` | `data\live\latest.pb` | Latest live-feed snapshot, written by the recorder |
| `NAADI_FARES`, `NAADI_WALK_DIR` | `fares_v1`, `walk_v1` | Fare table and walking tables |
| `NAADI_SALT` | A fixed value in `naadi\live.py` | Salt for the anonymised bus ids the API returns. Set a secret value on any public server |

Web app variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `NAADI_API_TARGET` | `https://13-235-147-97.sslip.io/api` (the live API) | Where `npm run dev` and `vite preview` send `/api` requests. Include the path the API is served under: `/api` on the server, none for a local uvicorn |
| `VITE_API_BASE` | `/api` | Build-time base URL the app calls |

## Mode A: web app against the live API

```powershell
cd web
npm run dev
```

Open http://localhost:5173. Use `localhost`, not `127.0.0.1`: on this laptop Vite listens on the IPv6 loopback only, so `http://127.0.0.1:5173` refuses the connection.

## Mode B: full stack

Terminal 1, the API:

```powershell
$env:NAADI_ROOT = 'C:\Users\shyam.BATCONSOLE\Desktop\transport'   # the checkout that holds data\
.venv\Scripts\python.exe -m uvicorn naadi.api:app --host 127.0.0.1 --port 8010
```

It answers within a few seconds. Then check it:

```powershell
.venv\Scripts\python.exe scripts\smoke_api.py http://127.0.0.1:8010   # ends with SMOKE OK
```

Terminal 2, the web app:

```powershell
cd web
$env:NAADI_API_TARGET = 'http://127.0.0.1:8010'
npm run dev
```

**Live data.** The API's live mode reads `data\live\latest.pb`, which the recorder rewrites every few seconds. On this laptop the scheduled task "Naadi feed recorder" starts it at logon (`scripts\start_local_recorder.ps1`; it shows as two python processes). Without the recorder, answers use history only and are labelled typical rather than live.

### Local URLs

| What | URL |
| --- | --- |
| Web app (dev) | http://localhost:5173 |
| Web app (production build, `vite preview`) | http://127.0.0.1:4173 |
| API (local) | http://127.0.0.1:8010, interactive docs at `/docs`, health at `/health` |
| Live site | https://13-235-147-97.sslip.io/, API under `/api`, docs at `/api/docs` |

The Playwright configs expect the API on other ports: `npm run e2e` uses `http://127.0.0.1:8000` and `npm run screens` uses `http://127.0.0.1:8020`. Start the API on that port, or set `NAADI_API_TARGET`.

## Build and test

Python, from the repo root:

```powershell
$env:NAADI_ROOT = 'C:\Users\shyam.BATCONSOLE\Desktop\transport'
.venv\Scripts\python.exe -m pytest -q tests     # 47 tests, about one minute
```

Web, from `web\`:

```powershell
npm run typecheck
npm run test          # Vitest unit tests
npm run build         # typecheck, production build into web\dist, bundle-size budget check
npx vite preview --host 127.0.0.1 --port 4173 --strictPort   # serve web\dist
npm run e2e           # Playwright in Chrome; builds and previews on port 4173; most specs mock the API
npm run e2e:live      # tests tagged @live, on real data through vite preview and the live API
npm run screens       # release screenshots against a real API on port 8020
```

To run the `@live` tests against a deployed site as it is, with no local build: `$env:NAADI_BASE_URL='https://13-235-147-97.sslip.io'; npx playwright test -c playwright.live.config.ts`.

What the browser tests cover (23 Nov 2026: 60 pass on desktop and phone, 23 planned tests marked `fixme`):

| Spec | Checks |
|---|---|
| `smoke`, `layout`, `a11y`, `inventory` | the shell and map load, settings persist, no horizontal overflow, axe accessibility, every control has a test id |
| `features` | every screen shows its heading with data loaded (fixture API in `e2e\support\mockData.ts`) |
| `requests` | each screen sends a bounded number of API requests while it stays open, on loaded and failing data; the live → route → stop → live → road speeds path; recovery from 429 with no reload |
| `live-flows` (`@live`) | the same screens and paths on real data, in English and Hindi: no 429 or 5xx, no page errors, no screen that keeps re-fetching |

`web\src\api\client.test.ts` (Vitest) covers the API client's guards: shared requests, the token bucket and waiting out a 429.

Checks that need a person (real phones and GPUs, location, installing the app, screen readers, plausibility of the times) are in `docs\MANUAL_TESTING.md`, with a 10-minute smoke test to run after every deploy.

**Real-browser page check** (gitignored helper, run from the repo root):

```powershell
node .agents\tasks\swarm\pagecheck.cjs http://localhost:5173 <screenshot folder> /accuracy /about
```

For each page it reports whether the boot splash cleared, whether anything covers the page heading, console errors, API calls and failed requests, and it saves a screenshot. Options: `PHONE=1` (390 × 844), `FULL=1` (full-page screenshots), `NOWEBGL=1` (a browser without WebGL), `SETTINGS='{"lang":"hi","theme":"dark"}'`, `WAIT_MS=8000`.

## Data

On the project laptop, `data\` already exists in the main checkout (about 20 GB). Elsewhere, the pipeline rebuilds it. It takes about 2 hours on 16 threads and 16 GB of memory, mostly the archive ingest:

1. Download the static bus GTFS (v1-2) into `delhi_buses_static_gtfs_v1-2\` and the October GPS archive from the hackathon page. The metro, Namo Bharat and shared-mobility GTFS zips sit in the repo root. The e-ticket file goes in `data\raw\eticket\`.
2. Run `scripts\ingest_dtc_hist.py`, `scripts\gtfs_fix.py`, `scripts\match_routes.py` and `scripts\build_speed_tables.py`.
3. Run `scripts\rebuild_all.py --from-step 3`: history tables, service levels, the LightGBM grid, the networks (bus, then bus plus other modes) and the ETA evaluation.
4. Run the extras the API also loads: `scripts\build_walk.py` (OpenStreetMap walking), `scripts\build_fares.py` (e-ticket fares), `scripts\build_trails.py` (road-speed playback) and `scripts\build_summary.py` (calibration, ranges and the Accuracy page summary).

## Other moving parts

- **Nightly job.** The Windows task "Naadi daily refresh" runs `scripts\daily_refresh.py` at 02:30 from the main checkout. It deploys, processes newly recorded days, refreshes the comparisons, rebuilds the summary and deploys again. Whatever is on `main`, in `web\dist` and in `data\processed\model` goes live.
- **Deploy.** `.venv\Scripts\python.exe -u infra\deploy_api.py`, with AWS profile `naadi`; it takes about 3 minutes. Deploy only with the owner's agreement.
- **On the AWS server:** the API (`naadi-api`), the feed recorder (`naadi-feed`), the ETA Calculator logger (`naadi-eta`), the Google sampler (`naadi-google`) and the S3 copy of raw data (`naadi-sync.timer`), behind Caddy.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| A page stays on "Loading Naadi…" | Fixed on 22 Nov: the splash was only removed by the map, so pages without a map stayed covered. If it comes back, open the console and run `document.getElementById('splash')`: the shell (`web\src\app\splash.ts`, `AppShell.tsx`) hides it on pages without a map, and `MapHost.tsx` once the map is ready |
| `/api/...` returns HTML in dev | `NAADI_API_TARGET` points at a website root rather than the API. Use `https://13-235-147-97.sslip.io/api` for the live server, or `http://127.0.0.1:8010` locally |
| The API can't find artefacts | Run it from the main checkout, or set `NAADI_ROOT` to it |
| No live buses locally | The recorder isn't running, or `data\live\latest.pb` is stale |
| Changes don't show after a deploy | Since 22 Nov the service worker updates itself on the next page load. An older installed version may need one reload |
