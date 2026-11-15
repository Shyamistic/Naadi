# Transport Stack Hackathon 2026: official brief (as provided by the user)

Source: the Where U Elevate hackathon page (https://whereuelevate.com/drills/transport-stack-hackathon-2026) and the full problem briefs (https://delhi.transportstack.in/hackathon/), pasted by the user on 13 Nov 2026. Kept verbatim where possible.

## Overview

The Transport Stack Hackathon 2026 invites teams to build open-source tools using real transit data. It is organized by Transport Stack, an initiative by Japan International Cooperation Agency (JICA), run by Chartr with the Centre for Sustainable Mobility (CSM), IIIT Delhi and owned by Airawat Research Foundation (ARF), IIT Kanpur.

Teams work on five problems built on real Delhi transit data: live bus GPS, e-ticketing, Electronic Ticketing Machine (ETM) records and metro Automatic Fare Collection (AFC) records.

The hackathon runs in two online phases. In Phase 1, every registered team picks Problem 1 or Problem 2 and submits a proposal with a working prototype. Shortlisted teams move to Phase 2, where they refine their Phase 1 work or take on Problem 3, 4 or 5 over about two weeks, with mentor sessions. Phase 2 solutions are presented and judged at the Transport Stack Annual Event at IIIT Delhi (10 or 11 December 2026; the page states both), where winners are announced. The best solutions may be taken forward as open-source components on Transport Stack. Prizes: ₹2,75,000. Team size 2 to 3.

## Timeline

| Phase | Dates | Notes |
| --- | --- | --- |
| Phase 1: Prototype Submission (online) | 29 Oct 2026 10:00 IST to **24 Nov 2026 23:59 IST** | Pick Problem 1 or 2; submit a proposal, a working prototype and a working code repo URL |
| Phase 2: Build Sprint (online) | 25 Nov to 9 Dec 2026 | About 10 to 12 shortlisted teams; refine Phase 1 or take Problem 3, 4 or 5; weekly mentor session |
| Phase 3: Final round (hybrid, IIIT Delhi) | 11 Dec 2026 10:00 to 14:00 IST | Presentations, judging, winners |

## Guidelines

- Phase 1: pick Problem 1 or Problem 2 and submit a proposal and a working prototype. **Mock-only or slide-only submissions will not qualify.**
- Every submission needs **source code with a README, a short technical note and a short demo video**.
- Solutions should be original work by the team. Open-source libraries and AI tools are allowed and should be credited.
- Judging (indicative): problem relevance, technical depth and correct use of the data, feasibility, innovation, and usability and impact. Each brief also lists its own success criteria.
- Teams keep credit for their work. Standout solutions may be taken forward as open-source components on Transport Stack.
- Contacts: transportstack.hackathon@gmail.com, csm@iiitd.ac.in, contact.delhitransportstack@gmail.com (delhitransportstack@gmail.com bounces).

## Problem 1 / Phase 1: Real-time bus traffic model and journey planner (CHOSEN)

| | |
| --- | --- |
| Phase | Phase 1, open to all registered teams |
| Core data | Real-time and historical bus GPS, static GTFS (routes, stops, schedules) |
| You build | A travel-time model and an API that returns bus journey options between two points |
| Judged on | Accuracy of travel-time estimates against observed trips and Google Maps |

### 1 Background
Delhi has several thousand buses on the road. Each bus sends its location every few seconds. If you know where a bus was and when, you know how fast it moved. Put thousands of buses together and you get a picture of traffic on most major roads, at every hour of the day.

Today, bus journey times in Delhi are hard to predict. The published timetable assumes fixed travel times. Real travel times change with the hour, the day and the road. A commuter cannot tell whether a trip will take 30 minutes or 60. This problem asks you to use the bus fleet as a set of moving sensors, and turn its signal into travel times a commuter can rely on.

### 2 The challenge
Build a model of bus travel times from real-time and historical bus locations. Then build a journey planner on top of it. A user gives an origin, a destination and a departure time. Your system returns sensible bus journeys and how long each will take.

#### 2.1 What the system should do
- Accept an origin and a destination, as coordinates or stop names, and a departure time.
- Return one or more journey options. Each option lists the walk to the first stop, the boarding stop, the route, the stop to get off at, any transfers, the walk to the destination, and the total time.
- Estimate time on the bus from your model of how fast buses actually move, not only from the timetable.
- Give different answers at different times. A trip at 9 am on a weekday should not get the same estimate as the same trip at 11 pm.
- Expose all of this as an API, with a simple screen or client that shows the results.

#### 2.2 An example
A user asks: from Kashmere Gate ISBT to Nehru Place, leaving at 8:30 am on a Tuesday. A good answer shows two or three options. For each, it gives the routes to take, where to change, how long to walk, and an estimated arrival time. It also says how long the same trip would usually take at a quieter hour, so the user can see the effect of traffic.

#### 2.3 Scope
The focus is bus journeys. Include walking to and from stops in the total journey time. Multimodal journeys are a welcome extension but not required.

### 3 Data provided
- **Real-time vehicle positions (GTFS-RT):** current position of each DTC and cluster bus, updated every few seconds. Fields: vehicle_id, route_id (joins to static routes.txt), latitude, longitude, timestamp.
- **Historical GPS traces:** past vehicle positions with the same fields, covering several weeks. Exact period and format to be confirmed.
- **Static GTFS:** about 10,500 stops, 2,400 routes and 89,000 scheduled trips; stops.txt, routes.txt, trips.txt, stop_times.txt, shapes.txt.

### 4 Expected deliverables
- A documented API, for example `GET /journeys?from=…&to=…&depart=…`, that returns journey options as JSON.
- A simple map-based or web screen, or an API client, to inspect the results.
- A short technical note. Explain how you link GPS points to roads or routes, how you estimate travel time on each stretch of road, and how you combine live and historical data.
- A validation report. Pick a set of origin–destination pairs. Compare your estimates with actual bus trip times and with Google Maps for the same pairs and times.
- Code and instructions that let someone else run your system.

### 5 Things to think about
- GPS points are noisy and irregular. Some jump off the road. Some arrive late or not at all.
- A bus waits at stops and at traffic signals. That waiting is part of travel time. Decide whether to treat it separately.
- Some roads have few buses at some hours. Explain what your model does when there is little or no live data.

### 6 Data access
All datasets are shared through the Delhi Transport Stack platform (delhi.transportstack.in). Bus schedules follow GTFS Schedule; live positions follow GTFS Realtime.

### Success criteria (hackathon page)
A working API that takes two locations and returns plausible bus journey options with estimated travel times. Estimates should hold up against known actual travel times for sample location pairs and against Google Maps.

## Problem 2 / Phase 1: Crowdedness-aware journey planner (not chosen; Phase 2 relevance via Problem 5)

Use about 4 to 5 weeks of e-ticketing and ETM ticket data to estimate how crowded buses are by route, direction, stretch between stops and time of day; turn it into a crowding level (seats available, standing room, crowded); show it next to each journey option; let the user choose between faster and more comfortable. Deliverables: rerunnable pipeline, queryable/mappable crowding outputs, planner or demo screen, technical note, checks against known peak patterns. Judged on how well crowding is grounded in the data and how clearly it is shown.

## Problems 3 to 5 (Phase 2, shortlisted teams only)

- **Problem 3, OD matrix:** estimate a stop- or zone-level origin–destination matrix for Delhi public transit by scaling a 3 to 4% bus e-ticket sample using metro gate data.
- **Problem 4, metro feeder routes:** design feeder routes for target metro stations with ~500 electric buses; max 7 km per route; account for traffic; roads wider than 6 m each side; charging plan.
- **Problem 5, metro and bus crowding:** load estimates by line/route, segment and time band from about one month of AFC boarding and alighting data.
