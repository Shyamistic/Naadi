# Naadi web app

Naadi is a responsive Delhi journey planner for measured bus travel times. It uses MapLibre for the planner and map screens. The Road speeds screen lazy-loads deck.gl for 3D speed columns and the play-the-day bus trails, so the planner's main JavaScript chunk stays free of deck.gl code.

## Screens

- **Plan:** search Delhi stops, Photon places, route numbers, saved places, example journey, leave-now and depart-at planning, and bus/metro mode selection.
- **Results:** separate validated bus results from schedule-estimated metro options, with fares, uncertainty, live status, alternatives, and quieter-hour comparisons.
- **Journey detail:** numbered walking and riding legs, route geometry on the map, SamayChakra hourly dial, time range, fare, and next-bus evidence.
- **Stop:** stop location, live and typical departures, filtering, and links back to planning.
- **Route:** direction, stop sequence, current-hour statistics, weekday/weekend charts, and live buses.
- **Live buses:** privacy-safe fleet map, route filtering, clustering, and live refresh.
- **Road speeds:** speed cells, 3D columns, weekday/weekend curves, hour controls, and real matched GPS trails for play-the-day.
- **Accuracy:** validation summaries and links to the validation report.
- **About, Privacy, Help, Settings, Accessibility, Terms:** project attribution, Photon and map privacy notes, usage guidance, display preferences, accessibility controls, and terms.
- **404:** a clear recovery link back to planning.

The header provides English/Hindi language selection and light/dark themes. Settings also controls text size, reduced motion, saved places, and reset behavior. The app is installable as a PWA and avoids caching API responses.

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
npm run screens
```

The production build runs the bundle check. It verifies the main chunk contains no deck.gl symbols and enforces the JavaScript and CSS budgets. Use `npm run e2e:live` for the live API acceptance configuration after starting the local API and Vite proxy.

## Release screenshots

Final real-Chrome screenshots are stored in `.agents/tasks/web-rebuild/screenshots/release/`. The set covers desktop (`1440x900`) and phone (`390x844`) views, light and dark themes, English and Hindi, with real API data. The screenshot index in that directory records the screen, viewport, theme, language, and interaction used for each capture.
