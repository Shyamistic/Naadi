"""Small DMRC timetable helpers shared by the API and evaluation branch."""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


def metro_fare(distance_km: float, airport: bool = False) -> int:
    """Return the published Delhi Metro distance slab fare used by the API."""
    d = float(distance_km)
    if airport:
        return 20 if d <= 2 else 32 if d <= 20 else 43 if d <= 30 else 54
    return 11 if d <= 2 else 21 if d <= 5 else 32 if d <= 12 else 43 if d <= 21 else 54 if d <= 32 else 64


def metro_patterns(gtfs: str | Path):
    """Read a compact weekday GTFS and return stations plus one pattern per route."""
    root = Path(gtfs)
    with (root / "stops.txt").open(newline="", encoding="utf-8") as f:
        stations = list(csv.DictReader(f))
    with (root / "routes.txt").open(newline="", encoding="utf-8") as f:
        routes = {r["route_id"]: r for r in csv.DictReader(f)}
    trips = defaultdict(list)
    with (root / "trips.txt").open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            trips[row["route_id"]].append(row)
    by_trip = defaultdict(list)
    with (root / "stop_times.txt").open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            by_trip[row["trip_id"]].append(row)
    patterns = []
    for route_id, rows in routes.items():
        trip = trips[route_id][0]
        stops = sorted(by_trip[trip["trip_id"]], key=lambda x: int(x["stop_sequence"]))
        def sec(v):
            h, m, s = map(int, v.split(":")); return h * 3600 + m * 60 + s
        start = sec(stops[0]["arrival_time"])
        offsets = [sec(x["arrival_time"]) - start for x in stops]
        deps = [[0] * 24]
        for tr in trips[route_id]:
            st = sorted(by_trip[tr["trip_id"]], key=lambda x: int(x["stop_sequence"]))
            deps[0][(sec(st[0]["departure_time"]) // 3600) % 24] += 1
        name = routes[route_id].get("route_long_name", route_id)
        line = name.split("_", 1)[0]
        group = int(trip.get("direction_id") or 0)
        if group == 0 and route_id.isdigit():
            group = int(route_id) % 2
        patterns.append({"route_id": route_id, "line_code": line, "group": group,
                         "stations": [x["stop_id"] for x in stops], "offsets_s": __import__("numpy").array(offsets),
                         "deps": __import__("numpy").array(deps, dtype=int)})
    return stations, patterns


def journey_metro_fare(net, journey, t_dep):
    metro = [l for l in journey.legs if getattr(l, "kind", None) == "metro"]
    if not metro:
        return None
    # Network builds expose route distances; ride time is a conservative fallback.
    distance_km = sum(max(0.1, float(getattr(l, "ride_s", 0)) / 60 * 0.30) for l in metro)
    return metro_fare(distance_km, False)
