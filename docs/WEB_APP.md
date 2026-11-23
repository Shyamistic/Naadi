# Naadi web app

Naadi is a responsive Delhi journey planner for measured bus travel times. It uses MapLibre for the planner and map screens. The Road speeds screen lazy-loads deck.gl for 3D speed columns and the play-the-day bus trails, so the planner's main JavaScript chunk stays free of deck.gl code.

## Screens

- **Plan:** search Delhi stops, Photon places, route numbers, saved places, example journey, leave-now and depart-at planning, and bus/metro mode selection. The "Delhi right now" card compares live bus travel times with an ordinary October day at the same hour and lists the slowest stretches; the map glows where buses are.
- **Results:** separate validated bus results from schedule-estimated metro options, with fares, uncertainty, live status, alternatives, and quieter-hour comparisons. A clear message when no bus option exists.
- **Journey detail:** numbered walking and riding legs, route geometry on the map with a bus (or train) driving the route, SamayChakra hourly dial, time range, fare, and next-bus evidence. Shared links (`&option=bus-0`) open the same journey.
- **Stop:** stop location, live and typical departures, filtering, and links back to planning.
- **Route:** direction, stop sequence, current-hour statistics, weekday/weekend charts, and live buses.
- **Live buses:** privacy-safe fleet map, route filtering, clustering, bus icons facing their direction of travel from zoom 14 and 3D buses from zoom 16, and live refresh.
- **Road speeds:** speed cells, 3D columns, weekday/weekend curves, hour controls, and real matched GPS trails for play-the-day.
- **Accuracy:** validation summaries and links to the validation report.
- **About, Privacy, Help, Settings, Accessibility, Terms:** project attribution, Photon and map privacy notes, usage guidance, display preferences, accessibility controls, and terms.
- **404:** a clear recovery link back to planning.

The header provides English/Hindi language selection and light/dark themes. Settings also controls text size, reduced motion, saved places, and reset behavior. The app is installable as a PWA and avoids caching API responses.

Data fetching goes through TanStack Query and one API client (`src/api/client.ts`). The client shares identical requests in flight, throttles a tab to a burst of 40 requests and then 4 a second, and after an HTTP 429 waits out the server's `Retry-After` with a "Naadi is busy" notice, so screens recover without a reload. Screens that need their data retry on their own every 30 s after a failure.

## Run locally

From the repository root:

```powershell
$env:NAADI_ROOT='C:\Users\shyam.BATCONSOLE\Desktop\transport'
& 'C:\Users\shyam.BATCONSOLE\Desktop\transport\.venv\Scripts\python.exe' -m uvicorn naadi.api:app --host 127.0.0.1 --port 8018
```

In a second terminal, proxy the web app to that API:

```powershell
cd web
npm ci
$env:NAADI_API_TARGET='http://127.0.0.1:8018'
npm run dev -- --host 127.0.0.1 --port 5188
```

Open `http://127.0.0.1:5188`. The API process must have `NAADI_ROOT` set so it reads the shared processed model, metro network, and `data/processed/model/trails_v1` artefacts.

## Checks

```powershell
cd web
npm run typecheck
npm run test -- --run
npm run build
npm run typecheck:e2e
npm run e2e -- smoke.spec.ts --project=desktop
npm run e2e -- inventory.spec.ts
npm run e2e -- layout.spec.ts
npm run e2e -- a11y.spec.ts
npm run e2e -- requests.spec.ts
npm run e2e:live
```

The production build runs the bundle check. It verifies the main chunk contains no deck.gl symbols and enforces the JavaScript and CSS budgets. `requests.spec.ts` counts the API requests each screen sends while it stays open, and `npm run e2e:live` runs the real-data checks (set `NAADI_BASE_URL` to test a deployed site).

## Screenshots

The README's screenshots are in `docs/images/`, taken after real interaction with real data: desktop at 1440 × 900, phone at 390 × 844, light and dark, English and Hindi, plus a Road speeds GIF. To retake them, build, start `vite preview` with `/api` proxied to the live API, run `node scripts/readme-shots.mjs` from `web/`, then `python scripts/build_docs_figures.py --images` from the repo root.
