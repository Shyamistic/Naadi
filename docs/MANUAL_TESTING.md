# Naadi manual testing guide

Written Mon 23 Nov 2026 for web build `cd56a9d`. Live site: https://13-235-147-97.sslip.io/

This guide is for testing the live site by hand. It covers what the automated tests can't judge: how the app looks on real screens, whether the times are plausible to someone who rides these buses, real phones and GPUs, real location, installing the app, screen readers, and how the app behaves over minutes on a real network.

| Pass | Time |
| --- | --- |
| Smoke test (section 4), before every demo and after every deploy | 10 minutes |
| Full pass in one browser (sections 5 to 11) | About 3 hours |
| The P1 cases on each extra browser or device | 30 to 45 minutes each |

## 1. What the automated tests already cover

| Suite | Where | What it checks |
| --- | --- | --- |
| Python, 46 tests | `tests\` | Router and model logic, API endpoints, the rate limiter, route links on departures, fares, walking, trails, the pulse |
| Web unit tests, 7 | `web\src` (Vitest) | Map style; the API client's guards (shared requests, burst limit, waiting out a 429) |
| Browser tests on a mocked API, 60 | `web\e2e`, desktop and phone | Shell and settings, layout, axe accessibility on key pages, every control has a test id, every screen's heading with data loaded, the number of requests each screen sends, the Live → route → stop path, recovery from 429 |
| Browser tests on live data, 12 per viewport | `web\e2e\live-flows.spec.ts` | The main screens and the reported Live → route → stop path on real data, in English and Hindi: no 429 or 5xx answers, no page errors, no screen that keeps re-fetching |

Last run against the deployed site, 23 Nov, from 14:21: 24 of 24 passed (12 desktop, 12 phone). Seven phone tests first failed during about ten minutes of network trouble on the test laptop's mobile connection. The server's logs show nothing wrong on its side (it received no requests at all for five of those minutes, with CPU under 4%), and all seven passed on a re-run.

To repeat the live-data tests against the deployed site, from `web\`:

```powershell
$env:NAADI_BASE_URL = 'https://13-235-147-97.sslip.io'
npx playwright test -c playwright.live.config.ts --project=desktop --project=phone
```

The other suites are in `docs\LOCAL_DEVELOPMENT.md`, "Build and test".

## 2. Before you start

| | |
| --- | --- |
| Web app | https://13-235-147-97.sslip.io/ |
| API documentation | https://13-235-147-97.sslip.io/api/docs |
| API health | https://13-235-147-97.sslip.io/api/health |
| Published results | https://13-235-147-97.sslip.io/api/accuracy |

1. **Check the build.** Open About → "Version and data" → "Web app build". It should read `cd56a9d 2026-11-22T18:50Z` or later. Write it on your results sheet: every result belongs to a build.
2. **Test live features between 08:00 and 21:00 IST** and note the time of each live test. Bus counts run from about 600 after midnight to about 5,000 at peaks.
3. **Start clean.** Use a new browser profile or clear the site's data (DevTools → Application → Storage → "Clear site data"), so saved places, recent journeys and settings don't carry over. Private windows can't install the app, so use a normal profile for section 7.
4. **Tools.** Chrome DevTools (F12): Network (tick "Preserve log", filter `api`), Console (errors), Application (storage), and the throttling menu. Test phones on real devices; DevTools' device mode is only a rough check.
5. **Check your own network first.** If the site seems down, open `/api/health` from another device or network before reporting it. On 23 Nov, connection drops on a mobile connection looked exactly like a server failure.

**Browsers and devices**

| Priority | Browser and device |
| --- | --- |
| P1 | Chrome on Windows (1920 × 1080 and 1366 × 768); Chrome on an Android phone |
| P2 | Edge on Windows; Firefox on Windows; Safari on an iPhone |
| P3 | Safari on macOS; Samsung Internet |

**Priorities:** P1 must pass before the submission and any demo; P2 should pass; P3 is nice to have.

**Severity of a bug:** S1, a main screen is unusable, a published number is wrong, or private data leaks; S2, a feature fails but there's a way round it; S3, cosmetic, wording or a rare case.

## 3. Test data

| Use | Value |
| --- | --- |
| The brief's example | GGS University ISBT Kashmere Gate (28.665476, 77.230173) to Nehru Place Terminal (28.548700, 77.256981), Tue 24 Nov 2026, 08:30. Link: `/?from=28.665476,77.230173&fromName=GGS+University+ISBT+Kashmere+Gate&to=28.548700,77.256981&toName=Nehru+Place+Terminal&depart=2026-11-24T08:30&modes=bus,metro,rail,shared_auto` |
| What the example should show | 69 min, arrive 09:39, usually 59–109 min; 405 (or 402, 411) to Delhi Public School, then 445A (or 244, 374, 930) to Nehru Place / Paras Cinema; ₹20 non-AC or ₹30 AC cash, ₹18 or ₹27 in the One Delhi app; quieter at 06:30: 61 min; timetable 62 min. With metro: a Violet Line option of about 53 min |
| "Leave now" pairs | Dhaula Kuan → Nehru Place; Rajouri Garden → Karol Bagh; Mehrauli → Saket. Links are in `docs\DEMO_VIDEO_SCRIPT.md`, scene 6 |
| A busy stop | Gandhi Darshan: `/stop/817` (one side of the road), `/stop/817,823` (both sides); about 31 departures |
| A quiet stop | Bakauli crossing: `/stop/10046` (one route) |
| A route through Gandhi Darshan | Route 03 towards Shalimar Bagh Desu Colony: `/route/1468`; Gandhi Darshan is stop 9 of 48 |
| Route 405 | `/route/1900` (towards Badarpur Border) and `/route/1899` (towards Mori Gate Terminal) |
| Bad links | `/stop/abc`, `/stop/999999`, `/route/77777`, `/route/abc`, `/nope`, `/journey/abc` |
| No bus option | From 28.408900, 77.317800 (Faridabad edge) to Connaught Place (28.631500, 77.216700) |
| Outside Delhi NCR | Mumbai, 19.07, 72.87 (API only; the map can't be moved there) |

## 4. Smoke test (10 minutes)

| ID | Steps | Expected |
| --- | --- | --- |
| SM-01 | Open About | "Web app build" is the build you expect |
| SM-02 | Open the home page in a fresh tab | The "Loading Naadi…" screen clears within 5 s; the header chip shows "N buses live" (over 1,000 in the daytime) |
| SM-03 | Click "Show this journey" in the example card | Results as in the test data, within about 2 s |
| SM-04 | Click the first card | Numbered steps, a bus driving the route on the map, and the 24-spoke dial |
| SM-05 | Open Live buses | Buses on the map; "positions at" is within 2 minutes of now |
| SM-06 | Open `/route/1468`, then click "Gandhi Darshan" | Hourly charts and the stop list, then a departures board with live minutes |
| SM-07 | On that stop page, watch DevTools → Network (filter `api`) for 60 s | At most 3 requests to `/stops/817/departures`, nothing else repeating, no 429 |
| SM-08 | Open Road speeds | Tilted map with coloured columns; a sentence giving the city's average bus speed |
| SM-09 | Open Accuracy | Five tiles: 2.2, 4.3, 15.5, 12.3 and 7.4 min |
| SM-10 | Click "हिन्दी", then "English" | The interface and map place names switch to Hindi and back |

## 5. Screens

### 5.1 Header and navigation

| ID | Pri | Steps | Expected |
| --- | --- | --- | --- |
| NAV-01 | P1 | Open the site in a fresh window | The loading screen clears within 5 s. The header shows the Naadi logo, Plan, Live buses, Road speeds, Accuracy, About, the live chip, "हिन्दी", the theme button, Help and Settings. The planner panel floats over the map |
| NAV-02 | P1 | Click each header link in turn, then Plan | Each page opens in under a second without reloading: the loading screen doesn't come back and the map stays. The current page's link is underlined |
| NAV-03 | P1 | Use the browser's Back and Forward buttons across several pages | Each step returns to the previous page and its state |
| NAV-04 | P1 | Paste each of these into a new tab, then press F5 on each: `/live`, `/speeds`, `/accuracy`, `/about`, `/help`, `/settings`, `/privacy`, `/accessibility`, `/terms`, `/route/1468`, `/stop/817`, `/stop/817,823`, the example link | Each page opens directly with its own heading; no server 404 |
| NAV-05 | P2 | Compare the live chip with `/api/health` (`live.buses`); wait a minute | The numbers are close; the chip updates within a minute |
| NAV-06 | P2 | Open `/nope`, then `/journey/abc` | "Page not found" with "Plan a journey"; `/journey/abc` opens the planner |
| NAV-07 | P2 | On About, Help or Settings, use the footer links | About, Privacy and Help open in the app; "API docs" opens in a new tab |

### 5.2 Planner (home page)

| ID | Pri | Steps | Expected |
| --- | --- | --- | --- |
| PLAN-01 | P1 | Type "Kashmere" in From and wait a second | Suggestions grouped as Stops, Places and Routes within 1 to 2 s, including ISBT Kashmere Gate stops |
| PLAN-02 | P1 | Pick a From suggestion with the mouse. In To, type "Nehru Place", press ↓ then Enter | Both fields show the chosen names; "Find buses" becomes active |
| PLAN-03 | P2 | Type landmarks that aren't stops: "India Gate", "AIIMS", "Select Citywalk" | A Places group lists matches; picking one fills the field |
| PLAN-04 | P2 | Type "Kashmiri Gate" and "Nehru Plce" | The right places, or "No stops or places match". Record which |
| PLAN-05 | P3 | Type "कश्मीरी गेट" | Record the result; the stop search may be English only |
| PLAN-06 | P2 | Type "405" in From and pick the route suggestion | Record what happens (a route page or a filled field) |
| PLAN-07 | P1 | Click the ↕ button between the fields | From and To swap |
| PLAN-08 | P2 | Clear a field with its × button | The field empties and "Find buses" turns inactive |
| PLAN-09 | P2 | Choose the same stop for From and To | "Find buses" stays inactive (no message says why: K10) |
| PLAN-10 | P1 | Click into an empty From field | The list offers "Use my location" and "Choose on map", plus Home and Work once saved |
| PLAN-11 | P1 | On a phone, choose "Use my location" and allow it | From reads "My location" and the map moves to you. Denied: "Location is turned off for this site". Outside Delhi NCR: "You seem to be outside Delhi NCR" |
| PLAN-12 | P2 | Choose "Choose on map", then tap the map; repeat and press Cancel | A banner "Tap the map to set your start" with Cancel; the tap sets "Pinned location"; Cancel leaves the field unchanged |
| PLAN-13 | P2 | With From filled, use its save button → "Save as Home". Reload, click into an empty field | "Home" with the saved place is offered; picking it fills the field |
| PLAN-14 | P1 | Click "Depart at": open the day list, change the time, then try a time chip (07:30, 08:30, 13:00, 18:00, 22:30). Click "Find buses" | The day list shows Today, Tomorrow and five more days, each marked weekday or weekend. The results say "Leaving <day>, <time> · weekday" (or weekend) |
| PLAN-15 | P2 | Search the example with "Include metro and other transit (timetable times)" on, then off | Off: only "By bus". On: a "With metro" group as well. The bus cards are identical both ways |
| PLAN-16 | P1 | Click "Show this journey" in the example card | Results as in the test data, within about 2 s |
| PLAN-17 | P2 | Run two searches, then go back with "← Plan a bus journey" | "Recent journeys" lists both, newest first; clicking one runs it again; × removes it. A journey from "My location" isn't stored |
| PLAN-18 | P1 | Read the "Delhi right now" card | A bus count; a comparison with an ordinary October day at this hour ("as usual" below 3%, otherwise "N% slower" or "faster"); up to three "Slowest stretches now" with their ratio and routes; a note "From N stretches driven by buses in the last 20 minutes…". The time in its corner is within a few minutes of now |
| PLAN-19 | P2 | Click a slow stretch | The map jumps to it and zooms in; a red line marks the stretch |
| PLAN-20 | P2 | Watch the home map for a minute | An orange glow where buses are and red lines on slow stretches, refreshed every 30 s |
| PLAN-21 | P2 | Click the quick links "See live buses", "Road speeds by hour" and "How accurate is Naadi?" | Each opens its page without reloading |

### 5.3 Journey options

| ID | Pri | Steps | Expected |
| --- | --- | --- | --- |
| RES-01 | P1 | Look at the top of the results | "Journey options"; "Leaving Tue, 24 Nov, 08:30 · weekday" (or "Leaving now · Live"); "N km apart"; buttons "15 min earlier", "15 min later", "Share", "Refresh"; "About these times"; "See the API answer" |
| RES-02 | P1 | Read the first bus card | Labels (Fastest, Fewest changes, Least walking); a "Live" or "Typical" badge; the minutes; "Arrive HH:MM" and "usually A–B min"; a bar split into walk, wait and ride; route badges with "or" alternatives and "AC" where most buses are AC; "walk N m · N change · from <stop>"; cash fares with "Fare estimated" or "Fare observed"; the One Delhi app fares; "Quieter at HH:30: N min"; "Timetable says N min"; "Timed from N past bus trips" |
| RES-03 | P1 | Judge whether the card makes sense | Arrival equals departure plus the total; the range contains the estimate; the routes serve both stops (check on their route pages); the times feel right for the trip and hour. Note anything surprising, with the time you tested |
| RES-04 | P2 | Click "15 min later", then "15 min earlier" | The departure moves by 15 min and new results load. In "Leaving now" mode, "15 min earlier" is inactive |
| RES-05 | P2 | Click "Refresh" | The results reload; in live mode the values may change |
| RES-06 | P2 | Open and close "About these times" | An explanation opens and closes |
| RES-07 | P2 | Click "See the API answer" | The raw JSON for the same search: options, legs, fares, `samay_chakra` |
| RES-08 | P1 | Scroll to "With metro" | Cards with metro line badges (such as the Violet Line), a "Timetable estimate" label, a note that metro, Namo Bharat and shared-auto times are estimates, and fares such as "₹X incl. metro ₹Y" or "Metro fare not known" |
| RES-09 | P2 | Hover each card in turn | The map highlights that option's route; the others stay light |
| RES-10 | P1 | Click "Share" and open the link in a new window | A share sheet opens (Windows, Android, iOS) or "Link copied" appears; the link shows the same search. See K4 |
| RES-11 | P2 | Click "← Plan a bus journey" | The planner, with both fields kept |
| RES-12 | P2 | Search the "No bus option" pair from the test data | A clear "No bus journey found" message. Today "By bus" is empty (K6) |
| RES-13 | P2 | Search a very short trip: Gandhi Darshan → Rajghat Gandhi Darshan | No error; record what's suggested |
| RES-14 | P3 | Search a long trip across Delhi, such as Narela → Badarpur | Results within about 5 s; record the minutes and changes |

### 5.4 Journey detail

| ID | Pri | Steps | Expected |
| --- | --- | --- | --- |
| DET-01 | P1 | Click the first card of the example | "69 min · Arrive 09:39"; "All options", "Share" and "Print"; a box "Leaving at 06:30 usually takes 61 min, 9 min less" with "Plan for 06:30"; numbered steps: Start at…, Board 405 towards Badarpur Border (T) at… (Wait about 4 min · Ride 30 min · 17 stops · 7.8 km · Based on 28,691 past trips · cash fare, "free with a Pink Saheli card", app fare), Get off at Delhi Public School, Board 445A…, Get off at…, Walk 195 m (about 4 min) to…, Arrive at Nehru Place Terminal |
| DET-02 | P1 | Watch the map | A bus icon drives the route from boarding to arrival, leaving a trail, and loops; on metro legs it's a train |
| DET-03 | P2 | Click a step | The step is highlighted and the map moves to it |
| DET-04 | P1 | Scroll to "Every hour of the day"; hover or tap several spokes; with the keyboard, Tab to the dial and press Enter or the arrow keys | The centre shows that hour's minutes and "HH:30"; the line below reads "HH:30 · N min faster" (or slower), with "quietest hour" on the quickest spoke; hours without service show a short grey spoke. Record which keys work |
| DET-05 | P1 | Click "Plan for 06:30" (in the box or under the dial) | The planner runs again for 06:30 |
| DET-06 | P2 | Look beside and under the dial | The hour chart is fully visible and "slowest around" names the longest spoke. Today the chart is cut off (K3) and the slowest time always reads 18:30 (K2) |
| DET-07 | P2 | Read the notes below the dial | The fares note (indicative; Pink Saheli; app tickets 10% less) and "Timetable says 62 min for this trip. Naadi expects 69 min from real buses." |
| DET-08 | P2 | Under "How we estimate", click "How accurate is Naadi?" | The Accuracy page |
| DET-09 | P1 | Open a "leave now" pair, then its first card | The boarding step shows "Next buses: <route> in N min · …", updated every 20 s. Open that boarding stop's page: its board should roughly agree |
| DET-10 | P2 | Open a "With metro" card | Steps such as "Take the Violet Line towards…", "Trains about every N min · wait about N min", "Ride N min · N stations · N km", "Timetable estimate", and "Change to the … inside the station" where there's an interchange |
| DET-11 | P2 | Click "Share", then "Print" | Share works as RES-10; the print preview shows a readable journey |
| DET-12 | P2 | Click "All options" | Back to the same list without a new search |

### 5.5 Live buses

| ID | Pri | Steps | Expected |
| --- | --- | --- | --- |
| LIVE-01 | P1 | Open Live buses | "Live buses"; "N buses · positions at HH:MM:SS"; the route filter; a list of routes with counts ("405 · 12 buses"); "Bus ids are anonymised. Licence plates are never shown."; a legend; clusters with counts on the map |
| LIVE-02 | P1 | Wait 60 s | "positions at" moves forward every 15 to 30 s and the buses move |
| LIVE-03 | P1 | Type "405" in "Route filter", choose an option, then "Clear route filter" | Options such as "405 · N buses"; choosing one shows only that route on the map and in the count, and adds `?route=405` to the address; clearing brings everything back |
| LIVE-04 | P1 | Zoom into a busy area, then press the cube (3D) button | Clusters split into buses. From zoom 14 each bus is an icon pointing the way it's going, with its route number from zoom 15; from zoom 16 they're 3D bus bodies with depth when tilted. Green is a position under 2 minutes old, grey older |
| LIVE-05 | P1 | Click a single bus | A popup: "Route N", "Position N s old", "Route details", "Close"; "Route details" opens the route page |
| LIVE-06 | P2 | Click a cluster | The map zooms in until it splits |
| LIVE-07 | P1 | Click a route number in the list | That route's page opens |

### 5.6 Route page

| ID | Pri | Steps | Expected |
| --- | --- | --- | --- |
| ROUTE-01 | P1 | Open `/route/1468` | "Route 03 towards Shalimar Bagh Desu Colony", "From Sarai Kale Khan ISBT · DTC"; "Other direction" and "Share"; buses an hour now, end-to-end minutes now (or "No service this hour") and live buses now; Weekday and Weekend; the charts "End-to-end minutes" and "Buses per hour" with the current hour marked; 48 stops with "+N min"; the route drawn on the map and framed |
| ROUTE-02 | P1 | Switch to Weekend and back | The charts and figures change without the page going blank |
| ROUTE-03 | P2 | Click "Other direction" | The route in the opposite direction |
| ROUTE-04 | P1 | Wait 30 s | Green dots move on the map; "Bus · position N s old" appears under the stops the buses are between; "live buses now" agrees |
| ROUTE-05 | P1 | Click "Gandhi Darshan" (stop 9) | The stop page opens at once, without reloading |
| ROUTE-06 | P2 | Open `/route/77777` and `/route/abc` | "Route not found" with "Go to planner" |
| ROUTE-07 | P2 | Click "Share" | "Link copied" appears at the bottom of the screen |

### 5.7 Stop page

| ID | Pri | Steps | Expected |
| --- | --- | --- | --- |
| STOP-01 | P1 | Open `/stop/817` | "Gandhi Darshan"; "Bus stop · 1 stop here · N routes"; "Plan from here", "Plan to here", "Share"; "Updated N s ago · Refreshes every 30 s"; All and Live; rows with the route badge, "towards…", and live minutes in green (the next one large, then up to two more) or "Typical wait about N min" or "No service now"; the map centred on the stop with nearby stops as blue dots |
| STOP-02 | P1 | Wait 70 s | "Updated N s ago" counts up in 5-second steps and goes back to 0 about every 30 s; the live minutes change |
| STOP-03 | P1 | Choose Live, then All | Live shows only rows with live minutes |
| STOP-04 | P1 | Click a departure row | That route's page, in the direction the row says |
| STOP-05 | P1 | Click "Plan from here", go back, click "Plan to here" | The planner opens with the stop as the start, then as the destination |
| STOP-06 | P2 | Zoom in and click another stop's dot (names show from zoom 16) | That stop's page |
| STOP-07 | P2 | Open `/stop/817,823` | "2 stops here"; both sides' departures in one list, soonest first |
| STOP-08 | P2 | Open `/stop/999999`, `/stop/abc`, `/stop/10046` | "This stop doesn't exist"; "This stop link is invalid"; Bakauli crossing with a short board |
| STOP-09 | P2 | Click "Share" | "Link copied" |

### 5.8 Road speeds

| ID | Pri | Steps | Expected |
| --- | --- | --- | --- |
| SPEED-01 | P1 | Open Road speeds | The map tilts and 3D columns rise, coloured from red (slow) to blue (fast); "Road speeds"; a sentence "At HH:00 on weekdays, buses average N km/h across Delhi; at HH:00, N km/h."; Weekday and Weekend; "Play the day"; the Hour slider at the current hour; the legend; "N road cells · N km/h median"; a 24-hour chart; the data source |
| SPEED-02 | P1 | Drag the slider to 02:00, then 18:00 | Weekday averages of 34.8 and 16.3 km/h; the columns change; the address gains `?day=weekday&hour=18` |
| SPEED-03 | P1 | Click "Play the day", wait 10 s, click "Pause" | The hour advances about every 1.2 s and loops; orange bus trails move along the roads; Pause stops it, and so does moving the slider |
| SPEED-04 | P2 | Choose Weekend | Different values (18:00 is 17.9 km/h on weekends) |
| SPEED-05 | P2 | Click a column | A popup "N km/h at HH:00 on weekdays · N observations" with Close |

The columns and trails need a GPU. If they're missing, check that hardware acceleration is on before filing a bug.

### 5.9 Accuracy

| ID | Pri | Steps | Expected |
| --- | --- | --- | --- |
| ACC-01 | P1 | Open Accuracy | "How accurate is Naadi?"; "Results updated 21 Nov 2026, 6:02 pm"; five tiles: 2.2 min (Published timetable: 4.6 min; 19,87,389 predictions, tested 26–31 Oct 2026); 4.3 min (13.1% of a 33 min ride; 90.4% within 10 min; 28,76,808 rides); 15.5 min (Timetable planner: 22.9 min; 3,598 journeys, tested 29–31 Oct); 12.3 min (Google Maps: 36.5 min; 91 trips, tested 15–16 Nov); 7.4 min (Transport Stack ETA Calculator: 9.7 min; 9,616 answers, tested 15–16 Nov) |
| ACC-02 | P1 | Open `/api/accuracy` and compare three figures with the tiles | They match, after rounding |
| ACC-03 | P2 | Scroll through the page | "Bus arrival at a stop, by method" (nine methods, Naadi first at 133.3 s); the error by stops ahead; "Time on the bus, ride only"; "Door to door, replayed on real buses", with the note that walking was straight-line; "How often the range held the real time"; the ETA Calculator section (with Naadi's error when answering from the latest position, and the age of the Calculator's bus positions); the Google section (with the small-sample note); "All published figures" |
| ACC-04 | P2 | Click "Download the results (JSON)", then "Read the full validation report…" | `naadi-accuracy.json` downloads. The report link goes to GitHub, which answers 404 until the repo is public (K5) |
| ACC-05 | P2 | Switch to Hindi | The whole page is in Hindi |

### 5.10 About, Help, Settings and other pages

| ID | Pri | Steps | Expected |
| --- | --- | --- | --- |
| DOC-01 | P1 | Open About | The introduction; "Version and data" (version "naadi-1.0 (history: Oct 2026, 31 days; …)", web app build, data sources, licence); "Data and privacy"; credits; the statement that Naadi is an independent project, not a DTC or government service |
| DOC-02 | P2 | Open Help and use its contents links | They jump to "How to read a card", "The dial and ranges" and "'Or' routes and schedule-estimated metro" |
| DOC-03 | P1 | In Settings, change Language, Theme, Text size (100, 112, 125%) and Reduce motion; reload; then "Reset settings" | Each change applies at once and survives a reload; Reset returns to English, light, 100%, motion on |
| DOC-04 | P3 | Open Privacy, Accessibility and Terms | Each has its heading and text |
| DOC-05 | P2 | On About, click "Send feedback" | GitHub issues; 404 until the repo is public (K5) |

### 5.11 Map controls

| ID | Pri | Steps | Expected |
| --- | --- | --- | --- |
| MAP-01 | P1 | Zoom with the + and − buttons, the mouse wheel and pinch; drag to pan | Smooth movement and readable labels; the map can't be dragged far beyond the NCR |
| MAP-02 | P2 | Click the locate button | The browser asks for your location, then the map centres on you |
| MAP-03 | P2 | Click full screen, then press Esc | The page fills the screen; Esc exits |
| MAP-04 | P2 | Rotate the map (right-drag, or two fingers), then click the compass button | North returns to the top |
| MAP-05 | P2 | Press the cube button twice while zoomed into the city | The map tilts and 3D buildings appear; the second press flattens it |
| MAP-06 | P2 | Click the map, then use the arrow keys and + and − | The map pans and zooms |
| MAP-07 | P3 | Click the attribution links | OpenStreetMap, OpenFreeMap and OpenMapTiles open in new tabs |

### 5.12 Phone layout (a real phone, portrait)

| ID | Pri | Steps | Expected |
| --- | --- | --- | --- |
| PHONE-01 | P1 | Open the home page; tap the panel's handle repeatedly | The panel is a bottom sheet over the map and moves between small, half and full height. No page scrolls sideways |
| PHONE-02 | P1 | Tap the menu button | A drawer with every page, Help, Settings, Light and Dark, English and हिन्दी; Close and a tap outside both close it |
| PHONE-03 | P1 | Run the example, open the first card, tap dial spokes | Everything works by touch |
| PHONE-04 | P1 | Plan from "Use my location" | "My location", with a sensible boarding stop |
| PHONE-05 | P2 | Use Live buses, a route and a stop | Text is readable, buttons are easy to tap, popups aren't hidden under the sheet, and "Link copied" shows above the sheet |
| PHONE-06 | P2 | Turn the phone to landscape | The layout adjusts and nothing is cut off |

### 5.13 Hindi

| ID | Pri | Steps | Expected |
| --- | --- | --- | --- |
| HI-01 | P1 | Click "हिन्दी" on the home page | The header, planner and "Delhi right now" switch to Hindi; map place names appear in correctly shaped Devanagari (for example दिल्ली); the button now reads "English" |
| HI-02 | P1 | Run the example and open the first card | Labels, steps and the dial text are in Hindi; times and fares read correctly |
| HI-03 | P2 | Open Live buses, a route and a stop | Headings and main labels are in Hindi. Some phrases are still English (K7); note any others |
| HI-04 | P2 | Reload | Hindi stays on |

### 5.14 Theme, text size and reduced motion

| ID | Pri | Steps | Expected |
| --- | --- | --- | --- |
| PREF-01 | P1 | Click the theme button on every page | A dark theme and dark map; all text, badges and charts stay readable; it survives a reload |
| PREF-02 | P2 | Set Text size to 125% and visit every page | Larger text, nothing overlapping, the panel scrolls |
| PREF-03 | P2 | Turn on Reduce motion (or Windows Settings → Accessibility → Visual effects → Animation effects off) and open a journey | The bus no longer drives the route; the rest works |

## 6. Over time and under failure

### 6.1 Request count: the 22 Nov bug

On 22 Nov, opening a stop from a route page made the stop page ask for its departures again and again, over 1,000 requests a minute, until the server refused every request from that address (HTTP 429) and Live buses and Road speeds stopped working until a reload. Build `cd56a9d` fixed it. Repeat this check after any change to the screens.

**REQ-01 (P1), the reported path**

1. Open DevTools → Network, tick "Preserve log" and type `api` in the filter.
2. Open `/live`. Type `03` in "Route filter", choose "03 · …", then click "03" in the route list. (Or open `/route/1468`.)
3. On "Route 03 towards Shalimar Bagh Desu Colony", click "Gandhi Darshan".
4. Leave the stop page open for 2 minutes and count the requests.
5. Click "Live buses", then "Road speeds".

**Expected:** on the stop page, `/stops/817/departures` about every 30 s (4 or 5 in two minutes), `/stops/all` once (it may come from the browser's cache) and `/health` about once a minute: about 10 requests in all. No 429 in the Status column. Live buses and Road speeds load normally. **Fail** if any address repeats every few seconds, or if any answer is a 429.

**REQ-02 (P1): every page.** Keep each page open for 2 minutes and compare with this table.

| Page | Requests while it's open |
| --- | --- |
| Every page | `/health` once a minute, for the header chip |
| Plan (home) | `/pulse` every 30 s |
| Journey options | One `/journeys` per search, then nothing |
| Journey detail, leaving now | `/legs/next-buses` every 20 s |
| Live buses | `/live/buses` every 15 s; `/routes/search` once each time you pause typing |
| Route | `/routes/<id>` once per weekday or weekend choice; `/live/buses?route_id=<id>` every 15 s |
| Stop | `/stops/<id>/departures` every 30 s for each stop in the link; `/stops/all` once |
| Road speeds | `/speeds/cells` once; `/trails/<day>/<hour>` once for each hour you view, plus the next hour |
| Accuracy, About | One request each, then nothing |

**REQ-03 (P2): hidden tab.** Switch to another tab for 2 minutes, then come back. While hidden, the log shows no new requests; on return, the data refreshes once.

**REQ-04 (P2): leaving a page.** Open a stop, then go to About and wait a minute. No more departures requests appear.

### 6.2 Offline and recovery

There are two ways to cut the connection, and the app behaves differently in each:

- **The browser knows it's offline** (DevTools → Network → throttling menu → "Offline", or airplane mode). Most screens then wait quietly and fetch again as soon as the connection returns; you may see no error at all.
- **The browser thinks it's online but the API fails** (a café Wi-Fi without internet, or a blocked server). To simulate it: DevTools → More tools → Network request blocking → add the pattern `*/api/*` and tick "Enable network request blocking". This is the case that shows the error messages.

| ID | Pri | Steps | Expected |
| --- | --- | --- | --- |
| FAIL-01 | P1 | On Live buses, block `*/api/*` for 60 s, then untick the block. Don't press anything | While blocked: the buses stay on the map and, after a few seconds, "Updates paused: connection problem" with Retry appears. After unblocking, updates resume by themselves within about 15 s and the warning goes |
| FAIL-02 | P1 | The same on `/stop/817` | "Couldn't refresh. Retrying in 30 s." while blocked; it goes away by itself within 30 s of unblocking |
| FAIL-03 | P1 | Block the API, then open `/route/1468` from the address bar; unblock and press Retry. Repeat on Road speeds and Accuracy without pressing anything | The app still opens and shows an error with Retry ("Couldn't load this route", "Road speeds are unavailable", the Accuracy error). Retry works once unblocked; Road speeds and Accuracy recover on their own within 30 s |
| FAIL-04 | P1 | Go Offline (throttling menu) on Live buses for 40 s, then back to "No throttling" | No crash and no reload needed; the buses stay; updates resume within about 15 s of reconnecting |
| FAIL-05 | P2 | Block the API and click "Find buses"; unblock and click Retry | "The planner could not be reached. Try again.", then results |
| FAIL-06 | P2 | Use "Slow 4G" on every page | Placeholders or a spinner while loading, then the content; nothing is requested twice at the same moment |

### 6.3 Server busy (HTTP 429), optional

This blocks `/journeys` for everyone on your internet connection for up to a minute and makes the server plan about 60 journeys in 30 s. Run it once, never during a demo or while judges might be using the site.

**SRV-01 (P2).** In PowerShell:

```powershell
$u = 'https://13-235-147-97.sslip.io/api/journeys?from=28.6315,77.2167&to=28.5677,77.2433&depart=2026-11-24T09:00&options=1&modes=bus'
1..65 | ForEach-Object { try { (Invoke-WebRequest $u -UseBasicParsing -TimeoutSec 30).StatusCode } catch { [int]$_.Exception.Response.StatusCode } } | Group-Object | Select-Object Name, Count
try { Invoke-WebRequest $u -UseBasicParsing } catch { 'Retry-After: ' + $_.Exception.Response.Headers['Retry-After'] }
```

**Expected:** about 60 answers of 200, then 429s. A 429 carries `Retry-After` in seconds (1 to 60).

**SRV-02 (P2).** Straight after, on the same connection, plan a journey in the browser. A notice "Naadi is busy. Trying again in N s." appears under the header and counts down; the results appear by themselves when it reaches zero, without a reload. While it counts down, every request from that tab waits; Live buses in a new tab keeps working, because only journeys are over their limit. In Hindi the notice reads "नाड़ी अभी व्यस्त है। N सेकंड में फिर कोशिश होगी।"

### 6.4 A browser without WebGL

**FAIL-07 (P2).** Press Win+R and run:

```text
chrome.exe --disable-webgl --user-data-dir="%TEMP%\naadi-nowebgl" https://13-235-147-97.sslip.io/
```

**Expected:** the loading screen clears and the map area says "The map can't be shown in this browser." with "You can still plan journeys…". Planning, results, journey steps, the Live buses list and Accuracy all work. Close that window afterwards; your normal profile isn't affected.

### 6.5 Long sessions

| ID | Pri | Steps | Expected |
| --- | --- | --- | --- |
| LONG-01 | P2 | Keep Live buses open and visible for 15 minutes; check Chrome's Task Manager (Shift+Esc) at the start and end | The tab's memory stays roughly level, CPU is low between updates, and the page still responds |
| LONG-02 | P3 | Leave the home page open for 30 minutes on a laptop running on battery | No sustained CPU use or fan noise |

## 7. Installable app

| ID | Pri | Steps | Expected |
| --- | --- | --- | --- |
| PWA-01 | P2 | Desktop Chrome: click the install button in the address bar, then Install | Naadi opens in its own window with its icon and works like the site |
| PWA-02 | P2 | Android Chrome: menu → "Install app" (or "Add to Home screen") | An icon on the home screen; it opens full screen |
| PWA-03 | P2 | iPhone Safari: Share → "Add to Home Screen" | It opens without the browser bars |
| PWA-04 | P2 | After one visit, turn on airplane mode and open the installed app; then reconnect | The app opens; the parts that need data wait or show a connection message, and load by themselves once reconnected |
| PWA-05 | P3 | After a new deploy, open the installed app and reload once | About shows the new web app build |

## 8. Accessibility

| ID | Pri | Steps | Expected |
| --- | --- | --- | --- |
| A11Y-01 | P1 | Without a mouse: Tab on a fresh page, press Enter on "Skip to main content", then fill both fields, pick suggestions with the arrow keys and Enter, submit, Tab to a card and press Enter | Everything is reachable in a sensible order and works with Enter and Space; Esc closes menus and popups |
| A11Y-02 | P1 | Tab through every page in light and dark | The focused control always has a clear outline |
| A11Y-03 | P2 | Use a screen reader: Narrator (Win+Ctrl+Enter) or NVDA; TalkBack on Android; VoiceOver on iPhone | Headings are announced in order; buttons have names ("Zoom in", "3D", "Swap start and destination", "Toggle theme"); the route charts are read out with their values; updates such as the busy notice are announced politely, not repeatedly |
| A11Y-04 | P2 | At 1280 px wide, set the browser zoom to 200% | The content reflows; nothing overlaps; the panel doesn't scroll sideways |
| A11Y-05 | P2 | Look for meaning carried by colour alone | Live minutes also have a dot and "min"; the speed legend has labels; contrast is readable in both themes |
| A11Y-06 | P3 | Scan Home, a result, a journey, Live buses, a route, a stop and Accuracy with the axe DevTools extension | Record serious and critical findings (the automated axe check covers only a few pages, on mocked data) |

## 9. API

Use a browser or PowerShell (`Invoke-RestMethod`). Base address: `https://13-235-147-97.sslip.io/api`.

| ID | Pri | Request | Expected |
| --- | --- | --- | --- |
| API-01 | P1 | `/health` | `status` ok; `version` "naadi-1.0 (history: Oct 2026, 31 days; …)"; `live.buses` above 0; `live.feed_ts` (Unix seconds) within 2 minutes of now; 9,294 stops; 2,907 routes |
| API-02 | P1 | `/docs`, then "Try it out" on `GET /journeys` with the example | The endpoints are listed with their parameters; the example returns 200 |
| API-03 | P1 | `/journeys?from=28.665476,77.230173&to=28.5487,77.256981&depart=2026-11-24T08:30&options=3&modes=bus,metro,rail,shared_auto` | Within 2 s: `options[0]` with `total_min` 69.4, `range_min` [59, 109], legs walk → bus 405 (`also` 402, 411) → bus 445A (`also` 244, 374, 930) → walk, `fare_inr` 20 and 30, 24 `samay_chakra` values, `timetable_min` 61.7; `multimodal_options` with the Violet Line and `schedule_estimated` true |
| API-04 | P1 | Bad inputs: `from=19.07,72.87`; `depart=tomorrow`; both `depart` and `arrive`; `modes=car`; `from=stop:999999999`; no `from` | 400 "Coordinates must be inside Delhi NCR."; 400 "depart must be 'now' or ISO time…"; 422 "Send either depart or arrive, not both."; 400 "modes must contain only bus, metro, rail, or shared_auto."; 404 "Unknown stop_id."; 422 |
| API-05 | P2 | The example with `arrive=2026-11-24T09:30%2B05:30` instead of `depart` | `query.arrive_by` is set, the departure is 07:45, and the options arrive by 09:30 |
| API-06 | P2 | `from=Kashmere Gate&to=Nehru Place` (stop names) | The names resolve to stops; options return |
| API-07 | P1 | `/v2/get_multi_modal?src=%5B28.665476,77.230173%5D&src_type=place&dst=%5B28.5487,77.256981%5D&dst_type=place&mode=bus&time=08:30:00` | 200 with `journeys` (the same option objects), `query` and `source`: the organisers' journey-planner format |
| API-08 | P2 | `/stops/search?q=gandhi`; `/stops/nearby?lat=28.6369&lon=77.2469&radius_m=500`; `/stops/817/departures`; `/stops/999999999/departures`; `/stops/all` | "Gandhi Darshan" with stop ids 817 and 823; Gandhi Darshan 22 m away; departures each with `route`, `route_variant`, `route_id`, `towards`, `live_eta_min` and `typical_wait_min`; 404; 6,812 stops with `Cache-Control: public, max-age=86400` |
| API-09 | P2 | `/routes/search?q=405`; `/routes/1900`; `/routes/999999999` | 405UP (1900) and 405DOWN (1899); stops, geometry and hourly figures; 404 |
| API-10 | P2 | `/live/buses`; `/live/buses?route_id=1468`; `/legs/next-buses?board=1373&alight=6054` | Fields `route_id, route, variant, lat, lon, age_s, progress_m` and `Cache-Control: no-store`; only route 1468's buses; `live`, `routes` and `buses` with `eta_min` |
| API-11 | P2 | `/pulse`, `/speeds/cells`, `/trails/index`, `/trails/weekday/8`, `/accuracy`, `/about`, `/capabilities`, `/vehicles` | All 200; `/capabilities` is `{"web_api_version": 1}`; `/speeds/cells` has 2,346 cells |
| API-12 | P3 | In the console of any other website: `fetch('https://13-235-147-97.sslip.io/api/health').then(r => r.json()).then(console.log)` | Works: the API accepts GET requests from any site |

## 10. Privacy and security

| ID | Pri | Steps | Expected |
| --- | --- | --- | --- |
| PRIV-01 | P1 | Search the live answers for licence plates: `(Invoke-WebRequest https://13-235-147-97.sslip.io/api/vehicles -UseBasicParsing).Content -match 'DL ?\d{1,2} ?[A-Z]{1,3} ?\d{3,4}'`, and the same for `/api/live/buses`. Click buses on the Live page | `False` both times. The bus popup shows only the route and the age of the position |
| PRIV-02 | P1 | Look at the padlock; open `http://13-235-147-97.sslip.io/` | A valid certificate for 13-235-147-97.sslip.io; http answers with a permanent redirect (308) to https |
| PRIV-03 | P2 | In DevTools → Network (no filter), use the home page, search a place, switch to Hindi | Requests go only to the site, `tiles.openfreemap.org` (map), `photon.komoot.io` (only while typing a place) and `wipfli.github.io` (Hindi map lettering). No analytics or advertising domains |
| PRIV-04 | P2 | DevTools → Application → Local storage and Cookies | Only settings, saved places and recent journeys; Naadi sets no cookies |
| PRIV-05 | P2 | Watch when the browser asks for your location | Only after "Use my location" or the locate button. A journey from "My location" isn't added to Recent journeys; sharing it puts your coordinates in the link (K11) |

## 11. Performance

| ID | Pri | Steps | Expected |
| --- | --- | --- | --- |
| PERF-01 | P1 | First visit with an empty cache (DevTools → Network → "Disable cache"): desktop on broadband, then a phone on 4G | The planner is usable within about 3 s on desktop and 6 s on the phone. Record both times |
| PERF-02 | P1 | A repeat visit | Under about 1.5 s |
| PERF-03 | P1 | Run the example | Results within 2 s (the server itself takes 0.3 to 0.6 s) |
| PERF-04 | P2 | Switch pages from the header | Under half a second |
| PERF-05 | P2 | Open Road speeds for the first time in a session | The columns appear within about 3 s |
| PERF-06 | P3 | Run Lighthouse (DevTools → Lighthouse, mobile) on Home and Accuracy | Record the Performance, Accessibility and Best Practices scores |

## 12. Known issues (23 Nov 2026)

Mark a failure caused by one of these as "Known issue Kn" rather than filing it again.

| # | Issue | Where | Seen in |
| --- | --- | --- | --- |
| K1 | The home subtitle says "Times from 38 million real Delhi bus trips and live GPS" (Hindi: "3.8 करोड़ … बस यात्राओं"). The 38 million are stop-to-stop traversals (README), not trips | `plan.subtitle` in `web\src\features\plan\strings.en.ts` and `strings.hi.ts` | Home page |
| K2 | "slowest around 18:30" is fixed text; only its minutes are real. For the example the slowest spoke is 13:30 (138 min) | `slowTime: "18:30"` in `web\src\features\plan\PlanPage.tsx` | DET-06 |
| K3 | On desktop the hour chart beside the dial is cut off at the panel's right edge | `.chakra-layout` in `web\src\features\plan\plan.css` (stacked only below 768 px) | DET-06 |
| K4 | Shared planner links lose part of their state: `&option=bus-0` opens the list rather than that journey, and `modes=bus` still includes metro, because the automatic search that a link starts ignores both values | The automatic search and `submit()` in `PlanPage.tsx` | RES-10 |
| K5 | "Read the full validation report…" and "Send feedback" point to github.com/Shyamistic/Naadi, which isn't public yet, so they answer 404 | `AccuracyPage.tsx`, `DocumentPages.tsx` | ACC-04, DOC-05 |
| K6 | No message when there's no bus option: "By bus" is simply empty ("No bus journey found" exists but isn't used) | `PlanPage.tsx` | RES-12 |
| K7 | Some text on Live buses, Route and Stop pages is still English in Hindi mode: "towards", "Share", "Typical wait about … min", "No service now", "End-to-end minutes", "Buses per hour", "From … · DTC", the Live map hint, bus counts | Those pages' components | HI-03 |
| K8 | The dial and "Quieter at" always show HH:30, even when you leave at another minute; the values are worked out at your own departure minute | `PlanPage.tsx`, `SamayChakra.tsx` | DET-04 |
| K9 | Around midday, "leave now" answers can include first waits of 20 to 45 min when no bus is near the boarding stop, and often show one option carrying all three labels. This may be right; compare with the stop's board before filing | Live planning | DET-09 |
| K10 | With the same start and destination, "Find buses" stays inactive without saying why ("Start and destination are the same place" exists but isn't shown) | `PlanPage.tsx` | PLAN-09 |
| K11 | Sharing a journey that starts at "My location" puts your coordinates in the link, without the planned warning ("This link includes your start location" exists but isn't shown) | `PlanPage.tsx` | PRIV-05 |
| K12 | The nightly data refresh isn't running: 17 to 22 Nov are recorded but not processed. Users don't see this; the model uses October history plus the live feed | `scripts\daily_refresh.py`, Windows Task Scheduler | — |

## 13. Recording results

Copy this table into a spreadsheet, one row per test and device:

| ID | Build | Device and browser | Language and theme | Date and time (IST) | Result | Notes | Screenshot or bug |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SM-01 | cd56a9d | Chrome 1xx, Windows 11, 1920 × 1080 | English, light | 23 Nov 16:10 | Pass | | |

Result is one of Pass, Fail, Blocked (couldn't run it), or Known issue Kn.

**Bug report**

```text
Title:      [Page] What's wrong, in one line
Build:      (About → Version and data → Web app build)
Page:       (full address)
Device:     (phone or computer, OS, browser and version; language; theme)
Time (IST): (live data changes by the minute)
Steps:      1. … 2. … 3. …
Expected:   …
Actual:     …
How often:  always / sometimes / once
Severity:   S1 / S2 / S3
Attached:   screenshot or screen recording; for loading or data problems, a HAR file
            (DevTools → Network → right-click → "Save all as HAR with content").
            A HAR file contains the addresses you opened, including any coordinates.
```

Until the repository is public, send bug reports to the team directly; afterwards, file them as GitHub issues.
