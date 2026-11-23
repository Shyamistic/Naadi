# Naadi demo video script

Written Mon 23 Nov 2026 for web build `7bb8f44` (About → Version and data → Web app build). It replaces the 17 Nov script, whose accuracy figures were out of date. Every number below was checked on the live site or in `validation\results` on 23 Nov.

| | |
| --- | --- |
| Length | **3:00.** The brief asks for a "short demo video" and sets no limit; check the submission form. A 2:00 cut and optional extra scenes are at the end. |
| Voice-over | English, about 400 words at a calm pace (about 140 words a minute). Hindi appears on screen in scene 9. |
| Site | https://13-235-147-97.sslip.io/ |
| Time needed | About 2 to 3 hours: 30 minutes of setup and checks, an hour of recording, an hour of editing. |

**The story in one sentence:** Naadi learns how long Delhi's buses really take from their own GPS, plans door to door with real waits and honest ranges, and shows how accurate it is on days it never saw.

## What the judges look for, and where the video shows it

| From the brief (`research\00-hackathon-brief.md`) | Scene |
| --- | --- |
| Accuracy against observed trips and against Google Maps (what Problem 1 is "judged on") | 8 |
| A working API: two locations in, journey options with times out | 3, 9 |
| Each option lists the walk, boarding stop, route, alighting stop, changes, final walk and total | 3, 5 |
| Different answers by time of day, and the time at a quieter hour | 2, 5 |
| A map screen to inspect the results | every scene |
| Real data: mock-only or slide-only entries don't qualify | 1, 2, 6 |
| Usability, impact and innovation (indicative judging) | 5 (SamayChakra), 6 (live buses), 9 (Hindi, installable app) |

## Before you record

### Fixed before recording (live since build `7bb8f44`, 23 Nov)

The issues that would have shown on camera are fixed and deployed: the home subtitle now says "38 million real stop-to-stop bus runs" (not trips), the sentence under the dial names the real slowest hour, the hour chart sits fully under the dial, the quieter-hour box and the dial agree ("8 min"), shared journey links open the journey, and a trip with no bus option shows a message instead of an error. Details: `docs\MANUAL_TESTING.md`, "Known issues".

One thing to keep in mind: the 13:30 spoke of the example's dial is its longest (138 min, against 91 at 12:30 and 102 at 14:30), and the sentence under the dial now says so. The dial re-times the same two buses at each hour, so a long spoke usually means a long wait at that hour; I haven't traced which bus. Don't use it as an example.

### When to record

- A weekday between 10:00 and 20:00 IST. The evening peak, 17:30 to 19:30, has the most buses and the clearest road-speed contrast. After midnight only about 600 buses report (628 at 00:21 on 23 Nov).
- Tue 24 Nov is Guru Nanak Jayanti, a gazetted holiday, so traffic and the live counts may be lighter that day.

### Browser

1. Chrome with a new profile ("Demo"): no extensions, no history. "Recent journeys" stays empty and the settings are the defaults (English, light theme).
2. A 1920 × 1080 screen, browser maximised, page zoom 110% (Ctrl and +) so the text reads on video. Hide the bookmarks bar (Ctrl+Shift+B).
3. Hardware acceleration on (`chrome://settings/system`). The 3D buses, the road-speed columns and the bus trails need the GPU.
4. Windows "Do not disturb" on; close chat apps and other tabs.
5. A visible cursor: PowerToys Mouse Highlighter (Win+Shift+H) or OBS's cursor highlight.

### Warm-up, 10 minutes before

1. https://13-235-147-97.sslip.io/about → "Version and data" → "Web app build" reads `7bb8f44 2026-11-23T11:09Z` or later.
2. https://13-235-147-97.sslip.io/api/health → `"buses"` above 2,000.
3. Run the brief's example once, open Road speeds once and Live buses once, so the first-load downloads are cached. Then reload the home page.
4. Choose the "leave now" pair for scene 6 (see that scene) and keep its link ready.
5. The header chip ("3,628 buses live") and the "Delhi right now" card should show live numbers. If the card says "The live feed is not updating right now", the Transport Stack feed is stale: record scenes 2 to 5 and 8, and the live scenes later.

### Recording tools

- **OBS Studio** (free): a Display Capture source at 1920 × 1080 and 30 fps, recording format MKV (File → Remux to MP4 afterwards), quality "Indistinguishable". Or the Windows 11 Snipping Tool (Win+Shift+R) for capture, and Clipchamp (built into Windows 11) for editing.
- Record each scene as its own clip. Record the voice-over separately in a quiet room with a headset microphone, then fit the clips to it.
- Pause one second before and after every click, and move the cursor slowly and in straight lines.

## Storyboard (3:00)

| # | Time | Screen | Voice-over (short) |
| --- | --- | --- | --- |
| 1 | 0:00–0:13 | Home: live glow and red slow stretches, "Delhi right now" | Buses as traffic sensors |
| 2 | 0:13–0:33 | Road speeds: 3D columns, hour slider 02:00 → 18:00 | Timetable says 18 km/h; real buses 35 and 16 |
| 3 | 0:33–1:03 | "Show this journey": the brief's example, first card | 69 min, a range, "405 or 402 or 411" |
| 4 | 1:03–1:10 | "With metro" group | Violet Line, timetable estimate |
| 5 | 1:10–1:36 | Journey detail, bus running on the map, SamayChakra | Same trip at every hour; plan the quieter hour |
| 6 | 1:36–2:00 | A "leave now" journey, then Live buses in 3D | Live first wait and next buses |
| 7 | 2:00–2:12 | A route page, then a stop's departures board | Every route and stop, live |
| 8 | 2:12–2:46 | Accuracy: "At a glance" tiles | The held-out numbers |
| 9 | 2:46–3:00 | Hindi, API docs, end card | Hindi, open API, organiser-shaped endpoint |

## Scenes

### 1 · Delhi right now (0:00–0:13)

**Screen:** the home page, with all of Delhi in view: an orange glow where buses are, red lines on the slowest stretches, and the "Delhi right now" card in the panel.

**Do:**
1. Start on the home page. Scroll the panel until the "Delhi right now" card is fully visible.
2. Hold for 2 s, then move the cursor to the card's bus count.
3. Click the first entry under "Slowest stretches now". The map jumps to that stretch and zooms in.

**Say (30 words):**
> "Right now, about [3,700] Delhi buses are reporting their position, and Naadi reads each one as a traffic sensor. Red lines are the slowest stretches of the last 20 minutes."

If the card's second figure says 5% or more, you can add: "Together, they say traffic is [12%] slower than an ordinary October [weekday] at this hour."

**Caption:** Naadi (नाड़ी) · Delhi bus travel times from the buses' own GPS

**Notes:**
- Read the bus count from the card and round it to the nearest hundred. On Mon 23 Nov at 14:25 it was 3,705.
- The card compares today with ordinary October days at the same hour. November buses have run about 12% faster than October's, so "faster than usual" is common and isn't news. Below 3% the card says "as usual".

### 2 · Road speeds (0:13–0:33)

**Screen:** Road speeds. The map tilts and coloured 3D columns rise over the city; taller and redder columns are slower roads.

**Do:**
1. Click "Road speeds" in the header and wait about 2 s for the camera to tilt and the columns to rise.
2. Drag the "Hour" slider to 02:00. The sentence above reads "At 02:00 on weekdays, buses average 34.8 km/h across Delhi".
3. Drag it to 18:00: 16.3 km/h. The columns grow and turn red.
4. Optional: press "Play the day" for 3 s to show the moving bus trails, then "Pause".

**Say (45 words):**
> "The bus timetable assumes 18 kilometres an hour, all day. A month of real GPS says otherwise: about 35 at 2 a.m., and 16 at 6 p.m. Taller columns are slower roads. Naadi learns every stretch like this, for every hour, on weekdays and weekends."

**Caption:** Weekday bus speed: 34.8 km/h at 02:00 · 16.3 km/h at 18:00 · timetable: 18 km/h

**Notes:** the speeds are medians over 2,346 road cells from 31 days of October 2026 GPS. If the columns or trails don't appear, hardware acceleration is off.

### 3 · The brief's example (0:33–1:03)

**Screen:** the planner panel, then "Journey options" with the map drawing the routes.

**Do:**
1. Click "Plan" in the header. In the panel, under "Try the brief's example: Kashmere Gate ISBT → Nehru Place, Tuesday 08:30", click "Show this journey".
2. The results appear in about a second: "Leaving Tue, 24 Nov, 08:30 · weekday" and "13.2 km apart". Hold on the first card.
3. Move the cursor down the card as you speak: "69 min" → "Arrive 09:39, usually 59–109 min" → the coloured walk, wait and ride bar → "405 AC or 402 · 411" → "445A or 244 · 374 · 930" → "₹20 non-AC · ₹30 AC" and the One Delhi app line → "Quieter at 06:30: 61 min" → "Timetable says 62 min".

**Say (70 words):**
> "Here's the brief's own example: Kashmere Gate to Nehru Place, Tuesday at 8:30. Naadi expects 69 minutes door to door, usually 59 to 109, because waits and traffic vary. Take the 405, or the 402 or 411, whichever comes first, then the 445A. The walk, the waits, the cash fare and the One Delhi app fare are all there. The timetable says 62 minutes. At 8:30, real buses take longer."

**Caption:** The brief's example · 69 min (usually 59–109) · timetable 62 min

**Notes:** the chosen option is drawn in dark blue and green, the others in light purple. Hovering another card previews its route.

### 4 · With metro (1:03–1:10)

**Do:** scroll down to "With metro" and point at the card labelled "Fastest" (Violet Line, about 53 min) and its "Timetable estimate" label.

**Say (14 words):**
> "With metro, the Violet Line takes about 53 minutes, marked as a timetable estimate."

**Caption:** Metro times come from the DMRC timetable, not live trains

**Note:** there is no live metro feed, and Naadi's scored accuracy covers bus journeys only. The bus options are the same with or without metro.

### 5 · The journey and SamayChakra (1:10–1:36)

**Screen:** the journey detail. A small bus drives the route on the map, then the 24-spoke dial.

**Do:**
1. Scroll back up and click the first bus card (69 min). The panel shows "69 min · Arrive 09:39", a box "Leaving at 06:30 usually takes 61 min, 8 min less" with a "Plan for 06:30" button, and the numbered steps. A bus icon drives the route on the map and loops.
2. Scroll to "Every hour of the day". Hover the 06 spoke (right side of the dial): the centre shows 61 and the line below reads "06:30 · 9 min faster · quietest hour". Then hover the 18 spoke (left side): 108.
3. Hover the 06 spoke again and click "Plan for 06:30". The options for 06:30 appear.

**Say (57 words):**
> "Open it, and a bus drives the route on the map. This dial is SamayChakra: like the Ashoka Chakra, it has 24 spokes, one for each hour, and each spoke is this same trip at that hour. Leave at 6:30 in the morning: 61 minutes. At 6:30 in the evening: 108. One tap plans the quieter hour."

**Caption:** SamayChakra · the same trip at every hour · 06:30: 61 min · 18:30: 108 min

**Optional:** the hour chart and the sentence under the dial ("Quickest around 06:30 (61 min); slowest around 13:30 (138 min)") can stay in frame. Don't pick the 13:30 spoke as an example (see "Fixed before recording").

### 6 · Leaving now (1:36–2:00)

**Screen:** a "leave now" journey with its next buses, then the Live buses map in 3D.

**Choose the pair 15 minutes before recording.** Open a few of these links and use one whose first card has the "Live" badge, a first wait under 10 minutes, and a "Next buses" line on its boarding step:

| Pair | Link | On Mon 23 Nov, 14:46 |
| --- | --- | --- |
| Dhaula Kuan → Nehru Place | `/?from=28.591800,77.161500&fromName=Dhaula+Kuan&to=28.548700,77.257000&toName=Nehru+Place&depart=now&modes=bus` | 442 or 567A; next buses in 6, 15 and 23 min |
| Rajouri Garden → Karol Bagh | `/?from=28.649200,77.122000&fromName=Rajouri+Garden&to=28.651900,77.190900&toName=Karol+Bagh&depart=now&modes=bus` | 832 or 801-IGI-IND, 813, 817; next in 8 min |
| Mehrauli → Saket | `/?from=28.524400,77.185500&fromName=Mehrauli&to=28.524500,77.206600&toName=Saket&depart=now&modes=bus` | 34 or 356, 427, 463; 33 min |

Put `https://13-235-147-97.sslip.io` in front of the link. Around midday some pairs show first waits of 30 to 45 minutes because no bus is near the stop; skip those. The links are bus-only (`modes=bus`).

**Do:**
1. Open the chosen link. The header reads "Leaving now · Live" and the card has a "Live" badge.
2. Click the first card. On the boarding step, show "Wait about 6 min" and "Next buses: 442 in 6 min · 567A in 12 min". This line refreshes every 20 s.
3. Click "Live buses" in the header. Zoom into a busy area such as ISBT Kashmere Gate or Anand Vihar ISBT. From zoom 14 each bus is an icon pointing the way it's going, with its route number from zoom 15; from zoom 16 they become 3D bus bodies. Click the cube button (top of the controls on the right) to tilt the map.

**Say (56 words):**
> "Leaving now? Naadi switches to live GPS. The first wait comes from the bus that's actually on its way, today's traffic adjusts the ride, and you see the next buses. On Live buses, every marker is a real bus. Zoom in and tilt the map, and they turn into 3D buses, facing the way they're driving."

**Caption:** Live: next buses from real GPS · positions refresh every 15 s

### 7 · A route and a stop (2:00–2:12)

**Do:**
1. On Live buses, click a busy route in the route list (764, 114A and 729 had 14 to 17 buses each at 14:25 on 23 Nov).
2. The route page shows "Route … towards …", buses an hour, end-to-end minutes, weekday and weekend charts, and live buses under the stops they're between. Click a stop name.
3. The stop page shows its departures board: live minutes in green, "Typical wait about … min" where no bus is tracked, and "Updated … s ago · Refreshes every 30 s".

**Say (21 words):**
> "Tap a route for its times through the day and its live buses; tap a stop for a live departures board."

**Caption:** Every route: hourly times and frequency · every stop: live departures

### 8 · Accuracy (2:12–2:46)

**Screen:** Accuracy, "At a glance": five tiles.

**Do:**
1. Click "Accuracy" in the header. Hold on the five tiles and move the cursor across them as you name them.
2. Scroll slowly to "Bus arrival at a stop, by method": Naadi at the top with 133.3 s, eight other methods below.

**Say (78 words):**
> "All of it is measured on days the model never saw. Arrival at a stop: 2.2 minutes off on average, against 4.6 for the timetable. Time on the bus: 4.3 minutes on a 33-minute ride. Door to door, replayed on the buses that really ran: 15.5 minutes, against 22.9 for a timetable planner. Google Maps' bus directions, on 91 trips: 36.5 minutes off; Naadi, 12.3. And on the Transport Stack ETA Calculator's own questions: 7.4 minutes against 9.7."

**Caption:** Held-out tests · arrivals 2.2 vs 4.6 min (19,87,389 predictions) · door to door 15.5 vs 22.9 · Google 12.3 vs 36.5 · ETA Calculator 7.4 vs 9.7

**Notes:** if you're short of time, drop the "Time on the bus" sentence. The tiles show the sample sizes and test days under each number, so the caption can carry them instead of the voice.

### 9 · Hindi, the API, the close (2:46–3:00)

**Do:**
1. Click "हिन्दी" in the header on the home page. The panel and the map's place names switch to Hindi.
2. Cut to https://13-235-147-97.sslip.io/api/docs and scroll past `GET /journeys` and `GET /v2/get_multi_modal`.
3. End card, 3 s.

**Say (33 words):**
> "Naadi works in Hindi and English, installs like an app, and it's all an open API, with an endpoint shaped like the Transport Stack's own journey planner. Naadi: Dilli ki naadi, har pal."

**End card:**
> Naadi (नाड़ी) · https://13-235-147-97.sslip.io · Code: [repo URL, once public]
> Transport Stack Hackathon 2026 · Problem 1 · [team name]
> Data: Delhi Transport Stack · Map: © OpenStreetMap contributors, OpenFreeMap

## Numbers you can quote

| What | Figure | Source |
| --- | --- | --- |
| Buses reporting | 3,705 at 14:25 on Mon 23 Nov; about 600 after midnight | "Delhi right now" card; `/api/health` |
| Timetable's assumed speed | A flat 18 km/h | `docs\TECHNICAL_NOTE.md` |
| Weekday bus speed | 34.8 km/h at 02:00, 16.3 km/h at 18:00 (median of 2,346 road cells) | Road speeds; `/api/speeds/cells` |
| History | 31 days of October 2026 GPS; 38 million stop-to-stop traversals | `/api/health`; README |
| The brief's example, Tue 08:30 | 69 min, arrive 09:39, usually 59–109 min; 405 or 402 · 411, then 445A or 244 · 374 · 930; ₹20 non-AC or ₹30 AC cash (₹18 or ₹27 in the app); quieter at 06:30: 61 min; 18:30: 108 min; timetable 62 min; Violet Line about 53 min | `/api/journeys`, 23 Nov |
| Arrival at a stop, 1 to 30 stops ahead | 2.2 min (133.3 s) against the timetable's 4.6 min (273.6 s); 1,987,389 predictions, tested 26–31 Oct; 72.9% within 2 min; 23.9 s better than the next best method (95% interval 23.4 to 24.5 s) | `validation\results\summary.json` (`eta`) |
| Time on the bus, rides of 5 to 40 stops | 4.31 min on a 32.96 min ride (13.1%); 90.4% within 10 min; 2,876,808 rides, tested 26–31 Oct | `validation\results\rides_oct.md` |
| Door to door | 15.5 min against 22.9 for a timetable planner; 3,598 journeys, tested 29–31 Oct | `validation\results\journeys_oct_v2.md` |
| Ranges | The 80% range held the real time 78% of the time; median width 40 min with live data | same file |
| Google Maps bus directions | 12.3 min against 36.5; 91 trips replayed (of 187 answers), 15–16 Nov; difference −24.3 min (95% interval −31.3 to −17.8); Naadi's suggested trip was faster in 73% of cases | `validation\results\google_nov.md` |
| Transport Stack ETA Calculator | 7.38 min against 9.69, on 9,616 of its answers, 15–16 Nov, both scored from the same bus position; answering from the latest position, Naadi's error is 4.81 min | `validation\results\eta_calculator_nov.md` |

## Say it this way

| Instead of | Say | Why |
| --- | --- | --- |
| "38 million trips" | "38 million timed stop-to-stop bus runs" | That's what the number counts |
| "Naadi beats Google Maps" | "On the 91 Delhi bus trips we replayed, Google's times were off by 36.5 minutes and Naadi's by 12.3" | Two days, one of them Chhath Puja and the other foggy; many Google lines couldn't be matched |
| "Naadi beats the organisers' ETA Calculator" | "On the Calculator's own questions, scored from the same bus position: 7.4 against 9.7 minutes" | Its answers used bus positions a median of 266 s old, so fresher positions would improve it. Frame it as something Naadi can add to the Stack |
| "Live metro" | "Metro from the timetable" | There's no live metro feed, and the DMRC timetable's calendar ended in December 2025 |
| "Always within the range" | "An 80% range, and it held 78% of the time" | |
| "Tested on November" | "Tested on held-out days in October; the Google and ETA Calculator comparisons used 15 and 16 November" | The November out-of-time test hasn't been run |
| "Door to door with street walking" | "Door to door, replayed on the buses that ran" | That test used straight-line walking distances; the app now uses street walking, and the test will be re-run |
| "X% slower than usual" | "X% slower than an ordinary October weekday at this hour" | |
| Anything as judge or mentor feedback | Nothing | There has been none |

## Shorter and longer versions

**2:00 cut:** scene 1 (0:00–0:12), scene 3 (0:12–0:40), scene 5 (0:40–1:02), scene 6 without the Live buses map (1:02–1:16), scene 8 without "Time on the bus" (1:16–1:50), scene 9 (1:50–2:00). Scenes 2, 4 and 7 go.

**Extras, if there's no limit** (15 to 30 s each):
- A phone: record the live site with Android's Screen record or the iPhone's Screen Recording. The panel becomes a bottom sheet; drag its handle up.
- The dark theme (moon button).
- "See the API answer" on the results: the same journey as JSON.
- Road speeds "Play the day" for 10 s with the bus trails.
- Arrive-by in the API: `/api/journeys?from=28.665476,77.230173&to=28.5487,77.256981&arrive=2026-11-24T09:30%2B05:30&modes=bus` answers "leave by 07:45".
- Installing the app from Chrome's install button in the address bar.

## Edit, export and upload

1. Put the clips in storyboard order and cut page loads to under half a second.
2. Add captions, burned in or as an SRT file. Judges may watch with the sound off; the voice-over text above is the caption text.
3. Add the "Caption" lines as lower thirds, a 2 s title card and the 3 s end card.
4. Music is optional. If you use it, keep it quiet (about −25 dB under the voice) and royalty-free, for example from the YouTube Audio Library.
5. Export 1920 × 1080, 30 fps, MP4 (H.264 video at 8 to 12 Mbps, AAC audio at 128 kbps or more). Three minutes comes to about 150 to 250 MB.
6. Upload to YouTube as "Unlisted", or to Google Drive shared as "Anyone with the link". Open the link in a private window to check it plays, then put it in the submission form and the README.

**Title:** Naadi (नाड़ी): Delhi bus travel times from real GPS · Transport Stack Hackathon 2026, Problem 1

**Description:**
> Naadi learns how long Delhi's buses really take from their own GPS (31 days of October 2026 data from the Delhi Transport Stack) and plans door to door with real waits, live next buses and honest ranges, in English and Hindi. Tested on held-out days: arrivals 2.2 min mean error against the timetable's 4.6; door to door 15.5 min against 22.9; on 91 replayed trips, 12.3 min against Google Maps' 36.5.
> Live app: https://13-235-147-97.sslip.io/ · API docs: https://13-235-147-97.sslip.io/api/docs · Code: [repo URL]
> Data: Delhi Transport Stack. Map data © OpenStreetMap contributors; tiles by OpenFreeMap.
