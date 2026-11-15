"""Probe the Delhi OTD GTFS-RT VehiclePositions feed and check it against the static GTFS.

Usage: .venv\\Scripts\\python.exe scripts\\probe_feed.py [polls] [interval_s]
Reads OTD_API_KEY from .env. Raw snapshots go to data/raw/rt_probe/ (git-ignored).
"""
from __future__ import annotations

import math
import os
import random
import statistics as stats
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import duckdb
import requests
from dotenv import load_dotenv
from google.transit import gtfs_realtime_pb2

ROOT = Path(__file__).resolve().parents[1]
GTFS = ROOT / "delhi_buses_static_gtfs_v1-2"
OUT = ROOT / "data" / "raw" / "rt_probe"
URL = "https://otd.delhi.gov.in/api/realtime/VehiclePositions.pb"


def haversine(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def q(values, ps=(0.1, 0.5, 0.9)):
    if not values:
        return "n/a"
    s = sorted(values)
    return " / ".join(f"{s[min(len(s) - 1, int(p * len(s)))]:.0f}" for p in ps)


def main():
    load_dotenv(ROOT / ".env")
    key = os.environ.get("OTD_API_KEY")
    if not key:
        sys.exit("OTD_API_KEY missing in .env")
    polls = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    interval = float(sys.argv[2]) if len(sys.argv) > 2 else 12
    OUT.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    routes = {r[0]: r[1] for r in con.execute(
        f"SELECT route_id, route_short_name FROM read_csv('{GTFS / 'routes.txt'}', all_varchar=true)").fetchall()}
    trips = {r[0]: r[1] for r in con.execute(
        f"SELECT trip_id, route_id FROM read_csv('{GTFS / 'trips.txt'}', all_varchar=true)").fetchall()}
    stops = {r[0]: (float(r[1]), float(r[2])) for r in con.execute(
        f"SELECT stop_id, stop_lat, stop_lon FROM read_csv('{GTFS / 'stops.txt'}', all_varchar=true)").fetchall()}
    route_stops = defaultdict(list)
    for rid, sid in con.execute(
            f"SELECT DISTINCT t.route_id, s.stop_id FROM read_csv('{GTFS / 'stop_times.txt'}', all_varchar=true) s "
            f"JOIN read_csv('{GTFS / 'trips.txt'}', all_varchar=true) t USING (trip_id)").fetchall():
        if sid in stops:
            route_stops[rid].append(stops[sid])

    snaps = []
    for i in range(polls):
        t0 = time.time()
        try:
            r = requests.get(URL, params={"key": key}, timeout=30)
            r.raise_for_status()
            feed = gtfs_realtime_pb2.FeedMessage()
            feed.ParseFromString(r.content)
            (OUT / f"vp_{int(t0)}.pb").write_bytes(r.content)
            snaps.append((t0, feed, len(r.content)))
            print(f"poll {i + 1}/{polls}: {len(feed.entity)} entities, {len(r.content) / 1024:.0f} KB, "
                  f"header ts {feed.header.timestamp}, fetch {time.time() - t0:.1f}s")
        except Exception as e:  # report and keep polling
            print(f"poll {i + 1}/{polls}: ERROR {type(e).__name__}: {e}".replace(key, "****"))
        if i < polls - 1:
            time.sleep(max(0, interval - (time.time() - t0)))

    if not snaps:
        sys.exit("no successful polls")

    t0, feed, _ = snaps[-1]
    vs = [e.vehicle for e in feed.entity if e.HasField("vehicle")]
    print(f"\n== Last snapshot: {len(vs)} vehicles, gtfs_realtime_version {feed.header.gtfs_realtime_version}")
    present = Counter()
    for v in vs:
        for name, val in (("trip_id", v.trip.trip_id), ("route_id", v.trip.route_id), ("start_time", v.trip.start_time),
                          ("start_date", v.trip.start_date), ("vehicle.id", v.vehicle.id), ("vehicle.label", v.vehicle.label),
                          ("license_plate", v.vehicle.license_plate), ("stop_id", v.stop_id)):
            if val:
                present[name] += 1
        if v.position.speed:
            present["speed>0"] += 1
        if v.position.bearing:
            present["bearing>0"] += 1
        if v.HasField("current_status"):
            present["current_status"] += 1
        if v.HasField("occupancy_status"):
            present["occupancy_status"] += 1
        if v.HasField("congestion_level"):
            present["congestion_level"] += 1
    for k, n in sorted(present.items()):
        print(f"  {k:18s} {n:6d}  ({100 * n / max(1, len(vs)):.0f}%)")
    sr = Counter(gtfs_realtime_pb2.TripDescriptor.ScheduleRelationship.Name(v.trip.schedule_relationship) for v in vs)
    print("  schedule_relationship:", dict(sr))
    ages = [feed.header.timestamp - v.timestamp for v in vs if v.timestamp]
    print(f"  position age vs header (s) p10/p50/p90: {q(ages)}; negative (clock ahead): {sum(a < 0 for a in ages)}; "
          f"older than 5 min: {sum(a > 300 for a in ages)}")
    lats = [v.position.latitude for v in vs]
    lons = [v.position.longitude for v in vs]
    print(f"  bbox lat {min(lats):.3f}..{max(lats):.3f}, lon {min(lons):.3f}..{max(lons):.3f}")
    ids = [v.vehicle.id for v in vs]
    print(f"  example vehicle ids (prefix only): {sorted({i[:6] for i in ids if i})[:8]}")
    prefixes = Counter(i[:6] for i in ids if i)
    print(f"  vehicle id prefixes: {prefixes.most_common(6)}")

    live_routes = {v.trip.route_id for v in vs if v.trip.route_id}
    live_trips = {v.trip.trip_id for v in vs if v.trip.trip_id}
    r_hit = sum(r in routes for r in live_routes)
    t_hit = sum(t in trips for t in live_trips)
    print(f"\n== Join with static GTFS v1-2")
    print(f"  live route_ids: {len(live_routes)}, found in routes.txt: {r_hit} ({100 * r_hit / max(1, len(live_routes)):.0f}%)")
    print(f"  live trip_ids:  {len(live_trips)}, found in trips.txt: {t_hit} ({100 * t_hit / max(1, len(live_trips)):.0f}%)")
    print(f"  example live trip_ids: {sorted(live_trips)[:5]}")

    def near_share(pairs, radius=300):
        hit = tot = 0
        for (lat, lon), rid in pairs:
            pts = route_stops.get(rid)
            if not pts:
                continue
            tot += 1
            if min(haversine(lat, lon, a, b) for a, b in pts) <= radius:
                hit += 1
        return hit, tot

    pairs = [((v.position.latitude, v.position.longitude), v.trip.route_id) for v in vs if v.trip.route_id in route_stops]
    hit, tot = near_share(pairs)
    rnd = random.Random(7)
    pool = list(route_stops)
    hit_r, tot_r = near_share([(p, rnd.choice(pool)) for p, _ in pairs])
    print(f"  buses within 300 m of a stop on their claimed route: {hit}/{tot} ({100 * hit / max(1, tot):.0f}%)")
    print(f"  same check with random routes (control):            {hit_r}/{tot_r} ({100 * hit_r / max(1, tot_r):.0f}%)")

    if len(snaps) > 1:
        seen = defaultdict(list)
        for _, f, _ in snaps:
            for e in f.entity:
                if e.HasField("vehicle"):
                    seen[e.vehicle.vehicle.id].append(e.vehicle.timestamp)
        gaps = []
        for ts in seen.values():
            u = sorted(set(ts))
            gaps += [b - a for a, b in zip(u, u[1:])]
        counts = [len(f.entity) for _, f, _ in snaps]
        hdr = [f.header.timestamp for _, f, _ in snaps]
        print(f"\n== Across {len(snaps)} polls")
        print(f"  entities per poll: {counts}")
        print(f"  header refresh gaps (s): {[b - a for a, b in zip(hdr, hdr[1:])]}")
        print(f"  per-bus position update gap (s) p10/p50/p90: {q(gaps)}")
        print(f"  distinct buses seen: {len(seen)}")


if __name__ == "__main__":
    main()
