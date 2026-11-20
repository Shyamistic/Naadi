"""Build anonymous, route-snapped GPS trail chunks for the play-the-day map."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import random
import time
from bisect import bisect_right
from pathlib import Path

import duckdb

ROOT = Path(os.environ.get("NAADI_ROOT", Path(__file__).resolve().parents[1]))
GTFS = ROOT / "data/processed/gtfs_fixed/bus_v1-2"
GPS = ROOT / "data/processed/gps_l2"
MODEL = ROOT / "data/processed/model"
OUT = MODEL / "trails_v1"
TMP = ROOT / "data/tmp_duckdb"
DAYS = {"weekday": "2026_10_27", "weekend": "2026_10_25"}
SPEED_BINS = [0, 5, 10, 15, 20, 25, 30, 40]


def read_csv(name: str):
    with (GTFS / name).open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def shapes_and_routes():
    route_shape = {}
    for row in read_csv("trips.txt"):
        route_shape.setdefault(str(row["route_id"]), row["shape_id"])
    routes = {}
    for row in read_csv("routes.txt"):
        name = row.get("route_short_name") or row.get("route_long_name") or row["route_id"]
        name = name.strip()
        for suffix in ("UP", "DOWN"):
            if name.upper().endswith(suffix):
                name = name[:-len(suffix)].strip()
        routes[str(row["route_id"])] = name
    by_shape = {}
    for row in read_csv("shapes.txt"):
        sid = row["shape_id"]
        by_shape.setdefault(sid, []).append((float(row["shape_dist_traveled"]), float(row["shape_pt_lon"]), float(row["shape_pt_lat"])))
    segments = []
    for route, sid in route_shape.items():
        pts = sorted(by_shape.get(sid, []))
        for a, b in zip(pts, pts[1:]):
            if b[0] > a[0]:
                segments.append((route, a[0], b[0], a[1], a[2], b[1], b[2]))
    return routes, segments


def city_curve():
    p = MODEL / "tables/oct_all/city_h.parquet"
    con = duckdb.connect()
    cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{p}')").fetchall()]
    day_col = next((x for x in ("daytype", "day_type", "we") if x in cols), None)
    hour_col = next((x for x in ("hour", "h") if x in cols), None)
    speed_col = next((x for x in ("speed_kmh", "speed_mean", "speed", "kmh") if x in cols), None)
    pace_col = "lpace_mean" if "lpace_mean" in cols else None
    if not (day_col and hour_col and (speed_col or pace_col)):
        raise RuntimeError(f"city_h lacks day/hour/speed columns: {cols}")
    value_expr = speed_col if speed_col else f"3600 / exp({pace_col})"
    rows = con.execute(f"SELECT {day_col}, {hour_col}, {value_expr} FROM read_parquet('{p}')").fetchall()
    out = {"weekday": [None] * 24, "weekend": [None] * 24}
    vals = {k: [[] for _ in range(24)] for k in out}
    for day, hour, speed in rows:
        if isinstance(day, (int, float)):
            key = "weekend" if int(day) else "weekday"
        else:
            key = str(day).lower()
            key = "weekend" if key in ("weekend", "we", "1") else "weekday"
        if 0 <= int(hour) < 24 and speed is not None:
            vals[key][int(hour)].append(float(speed))
    for day in out:
        out[day] = [round(sum(v) / len(v), 1) if v else None for v in vals[day]]
    return out


def build_day(day_type, day, routes, segments):
    con = duckdb.connect()
    TMP.mkdir(parents=True, exist_ok=True)
    con.execute("SET memory_limit='1200MB'; SET threads=4; SET temp_directory=?", [str(TMP)])
    con.execute("CREATE TEMP TABLE seg(route VARCHAR, d0 DOUBLE, d1 DOUBLE, lon0 DOUBLE, lat0 DOUBLE, lon1 DOUBLE, lat1 DOUBLE)")
    con.executemany("INSERT INTO seg VALUES (?, ?, ?, ?, ?, ?, ?)", segments)
    src = GPS / f"day={day}.parquet"
    # k is only an internal grouping key and never enters an output object.
    sql = f"""
    WITH a AS (
      SELECT CAST(route_id AS VARCHAR) route, vehicle_id, CAST(ts AS DOUBLE) t,
             CAST(shape_dist_m AS DOUBLE) d
      FROM read_parquet('{src}') WHERE match_status='matched' AND shape_dist_m IS NOT NULL
    ), b AS (
      SELECT *, lag(t) OVER w pt, lag(d) OVER w pd
      FROM a WINDOW w AS (PARTITION BY vehicle_id, route ORDER BY t)
    ), c AS (
      SELECT *, sum(CASE WHEN pt IS NULL OR t-pt > 1200 OR d < pd-1000 THEN 1 ELSE 0 END)
        OVER (PARTITION BY vehicle_id, route ORDER BY t) run
      FROM b
    ), d AS (
      SELECT hash(vehicle_id, route, run) k, route, t, d,
        lag(t) OVER w pt, lag(d) OVER w pd
      FROM c WINDOW w AS (PARTITION BY vehicle_id, route, run ORDER BY t)
    ), e AS (
      SELECT *, lag(t) OVER (PARTITION BY k ORDER BY t) kt
      FROM d WHERE pt IS NULL OR t-pt >= 30
    )
    SELECT e.k, e.route, e.t, e.d, s.lon0, s.lat0, s.lon1, s.lat1, s.d0, s.d1
    FROM e JOIN seg s ON s.route=e.route AND e.d BETWEEN s.d0 AND s.d1
    WHERE e.t >= 0
    """
    groups = {}
    result = con.execute(sql)
    while True:
        batch = result.fetchmany(100000)
        if not batch:
            break
        for k, route, t, dist, lon0, lat0, lon1, lat1, d0, d1 in batch:
            hour = int((t + 19800) // 3600) % 24
            sec = (t + 19800) % 86400
            # A point belongs to its hour and the adjacent five-minute overlap.
            for h in (hour, (hour - 1) % 24, (hour + 1) % 24):
                hs = h * 3600
                if hs - 300 <= sec <= hs + 3900:
                    f = max(0.0, min(1.0, (dist - d0) / (d1 - d0)))
                    key = (h, k, route)
                    groups.setdefault(key, []).append(([round(lon0 + f * (lon1 - lon0), 5), round(lat0 + f * (lat1 - lat0), 5)], sec, float(dist)))
    chunks = {}
    for (hour, k, route), points in groups.items():
        points.sort(key=lambda x: x[1])
        if len(points) < 2:
            continue
        coords, ts, speeds = [], [], []
        prev = None
        prev_dist = None
        for coord, sec, dist in points:
            if prev is not None and sec - prev < 30:
                continue
            coords.append(coord); ts.append(int(round(sec)))
            if prev is None or sec <= prev:
                speeds.append(0.0)
            else:
                speeds.append(round(max(0.0, min(80.0, (dist - prev_dist) / (sec - prev) * 3.6)), 1))
            prev = sec
            prev_dist = dist
        if len(ts) < 2:
            continue
        trip = {"r": routes.get(route, route), "c": coords, "t": ts, "s": speeds}
        chunks.setdefault(hour, []).append(trip)
    return chunks


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--force", action="store_true"); args = ap.parse_args()
    t0 = time.time(); OUT.mkdir(parents=True, exist_ok=True)
    routes, segments = shapes_and_routes()
    # city_h is the published city curve used by the player, rather than recomputing it from trails.
    curve = city_curve()
    all_chunks = {day: {h: [] for h in range(24)} for day in DAYS}
    for day_type, day in DAYS.items():
        all_chunks[day_type] = build_day(day_type, day, routes, segments)
    rng = random.Random(20261027)
    for day_type in DAYS:
        for h in range(24):
            trips = all_chunks[day_type].get(h, [])
            rng.shuffle(trips)
            payload = {"day_type": day_type, "hour": h, "t0": h * 3600, "trips": trips}
            raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
            (OUT / f"{day_type}_{h:02d}.json.gz").write_bytes(gzip.compress(raw, compresslevel=6, mtime=0))
    index = {"version": 1, "source": "matched bus GPS: Tue 27 Oct 2026 (weekday), Sun 25 Oct 2026 (weekend)",
             "day_types": ["weekday", "weekend"], "hours": list(range(24)),
             "buses_per_hour": {d: [len(all_chunks[d].get(h, [])) for h in range(24)] for d in DAYS},
             "city_speed_kmh": curve, "speed_bins_kmh": SPEED_BINS}
    (OUT / "index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"seconds": round(time.time()-t0, 1), "chunks": 48,
                      "max_bytes": max((p.stat().st_size for p in OUT.glob("*.json.gz")), default=0),
                      "buses": index["buses_per_hour"]}))

if __name__ == "__main__":
    main()
