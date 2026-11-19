"""Build and describe schedule-estimated Delhi Metro routes.

The builder keeps the bus network arrays byte-for-byte unchanged in memory and
appends a separate platform for each station, line, and direction group.  The
same representation can therefore accommodate other timetable rail feeds and
frequency-based modes without changing the router's bus data model.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

from .network import FOOT_RADIUS_M, MAX_WAIT_S, MIN_BPH, haversine, walk_s
from .paths import METRO_GTFS

METRO_ID_BASE = 90_000_000
ENTRY_S = 180.0
EXIT_S = 90.0
INTERCHANGE_S = 240.0
STATION_WALK_M = 300.0

LINES = {
    "RED": ("Red Line", "#E2231A", True),
    "YELLOW": ("Yellow Line", "#F7C600", True),
    "BLUE": ("Blue Line", "#0072BC", True),
    "GREEN": ("Green Line", "#00A651", True),
    "VIOLET": ("Violet Line", "#8E44AD", True),
    "PINK": ("Pink Line", "#E75480", True),
    "MAGENTA": ("Magenta Line", "#B5179E", True),
    "GRAY": ("Grey Line", "#8C8C8C", True),
    "AIRPORT": ("Airport Express", "#F58220", False),
    "RAPID": ("Rapid Metro", "#00838F", False),
    "AQUA": ("Aqua Line", "#00B5E2", False),
}
FARE_WEEKDAY = [(2, 11), (5, 21), (12, 32), (21, 43), (32, 54), (math.inf, 64)]
FARE_SUNDAY = [(2, 11), (5, 11), (12, 21), (21, 32), (32, 43), (math.inf, 54)]
NOTE = ("Metro times come from the DMRC timetable (GTFS v1). Its calendar ended on 31 Dec 2025 and it has no "
        "Sunday trips, so the weekday timetable is used on every day. They are timetable estimates, not checked "
        "against live trains, and are not part of Naadi's accuracy results.")


def _read(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _seconds(value: str) -> int:
    h, m, s = (int(float(x)) for x in value.split(":"))
    return h * 3600 + m * 60 + s


def line_code(route_long_name: str) -> str:
    code = route_long_name.split("_", 1)[0].strip().upper()
    return "AIRPORT" if code == "ORANGE/AIRPORT" else code


def metro_fare(distance_km: float, sunday: bool = False) -> int:
    for limit, fare in (FARE_SUNDAY if sunday else FARE_WEEKDAY):
        if distance_km <= limit:
            return fare
    return (FARE_SUNDAY if sunday else FARE_WEEKDAY)[-1][1]


def _shape_rows(gtfs: Path):
    out = defaultdict(list)
    for row in _read(gtfs / "shapes.txt"):
        out[row["shape_id"]].append(row)
    for rows in out.values():
        rows.sort(key=lambda r: int(r["shape_pt_sequence"]))
    return out


def metro_patterns(gtfs_dir: Path = METRO_GTFS):
    """Read weekday DMRC trips into one pattern per directional GTFS route."""
    gtfs_dir = Path(gtfs_dir)
    routes = {str(r["route_id"]): r for r in _read(gtfs_dir / "routes.txt")}
    stations = {str(r["stop_id"]): (r["stop_name"], float(r["stop_lat"]), float(r["stop_lon"]))
                for r in _read(gtfs_dir / "stops.txt")}
    trips = [r for r in _read(gtfs_dir / "trips.txt") if r.get("service_id") == "weekday"]
    times = defaultdict(list)
    for row in _read(gtfs_dir / "stop_times.txt"):
        times[row["trip_id"]].append(row)
    by_route = defaultdict(list)
    for trip in trips:
        seq = sorted(times.get(trip["trip_id"], []), key=lambda r: int(r["stop_sequence"]))
        if seq:
            by_route[str(trip["route_id"])].append((trip, seq))
    shapes = _shape_rows(gtfs_dir)
    patterns = []
    for rid in sorted(by_route, key=int):
        rows = by_route[rid]
        trip, selected = min(rows, key=lambda x: (-len(x[1]), int(x[0]["trip_id"])))
        first = _seconds(selected[0]["arrival_time"])
        deps = np.zeros((len(selected), 24), dtype=np.float32)
        for _, seq in rows:
            for i, stop in enumerate(seq[:len(selected)]):
                deps[i, (_seconds(stop["departure_time"]) // 3600) % 24] += 1
        shape = [[float(x["shape_pt_lat"]), float(x["shape_pt_lon"])] for x in shapes.get(trip.get("shape_id", ""), [])]
        if not shape:
            shape = [[stations[s][1], stations[s][2]] for s in [x["stop_id"] for x in selected]]
        route = routes.get(rid, {})
        code = line_code(route.get("route_long_name", ""))
        patterns.append({
            "route_id": rid,
            "line": code,
            "line_code": code,
            "desc": route.get("route_long_name", "").split("_", 1)[-1].strip(),
            "stations": [x["stop_id"] for x in selected],
            "offsets_s": np.asarray([_seconds(x["arrival_time"]) - first for x in selected], dtype=np.float32),
            "sd_m": np.asarray([float(x.get("shape_dist_traveled") or 0.0) for x in selected], dtype=np.float32),
            "deps": deps,
            "shape": shape,
            "towards": stations[selected[-1]["stop_id"]][0],
            "trip_id": trip["trip_id"],
        })
    by_line = defaultdict(list)
    for p in patterns:
        by_line[p["line_code"]].append(p)
    for code, ps in by_line.items():
        ref = min(ps, key=lambda p: (-len(p["stations"]), int(p["route_id"])))
        ref_pos = {s: i for i, s in enumerate(ref["stations"])}
        for p in ps:
            shared = [s for s in p["stations"] if s in ref_pos]
            if len(shared) < 2:
                p["group"] = 2 + int(p["route_id"])
            else:
                p["group"] = 0 if ref_pos[shared[1]] > ref_pos[shared[0]] else 1
    for p in patterns:
        p.pop("trip_id", None)
    return stations, patterns


def _csr(from_idx, to_idx, seconds, n):
    if not from_idx:
        return np.zeros(n + 1, np.int32), np.zeros(0, np.int32), np.zeros(0, np.float32)
    order = np.argsort(np.asarray(from_idx), kind="stable")
    f = np.asarray(from_idx, np.int32)[order]
    return (np.searchsorted(f, np.arange(n + 1)).astype(np.int32),
            np.asarray(to_idx, np.int32)[order], np.asarray(seconds, np.float32)[order])


def _base_footpaths(lat, lon, fp_ptr, fp_to, fp_s):
    from_idx = np.repeat(np.arange(len(lat), dtype=np.int32), np.diff(fp_ptr)).tolist()
    return from_idx, fp_to.tolist(), fp_s.tolist()


def _nearby_indices(lat, lon, query_i, radius):
    cell_size = 0.005
    cells = np.floor(np.column_stack((lat, lon)) / cell_size).astype(np.int64)
    buckets = defaultdict(list)
    for i, (y, x) in enumerate(cells):
        buckets[(int(y), int(x))].append(i)
    out = []
    y, x = cells[query_i]
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            for j in buckets.get((int(y + dy), int(x + dx)), []):
                if j != query_i:
                    d = float(haversine(lat[query_i], lon[query_i], lat[j], lon[j]))
                    if d <= radius:
                        out.append((j, d))
    return out


def build_multimodal(bus_dir: Path, metro_dir: Path = METRO_GTFS, out_dir: Path | None = None):
    """Write ``out_dir`` as the bus network plus schedule-estimated metro."""
    if out_dir is None:  # convenient two-argument form: bus directory, output directory
        out_dir, metro_dir = metro_dir, METRO_GTFS
    bus_dir, metro_dir, out_dir = Path(bus_dir), Path(metro_dir), Path(out_dir)
    z = np.load(bus_dir / "network.npz")
    a = {k: z[k] for k in z.files}
    bus_meta = json.loads((bus_dir / "network_meta.json").read_text(encoding="utf-8"))
    stations, patterns = metro_patterns(metro_dir)
    bus_n_stops = len(a["stop_ids"])
    bus_n_routes = len(a["route_ids"])
    bus_n_rs = len(a["rs_stop"])

    # Platform identity is station × line × direction group.  First appearance
    # is deterministic and follows the GTFS route/station order.
    platform_key = {}
    platforms = []
    for p in patterns:
        for sid in p["stations"]:
            key = (sid, p["line_code"], p["group"])
            if key not in platform_key:
                platform_key[key] = len(platforms)
                platforms.append(key)
    pidx = {key: bus_n_stops + i for i, key in enumerate(platforms)}
    n_stops = bus_n_stops + len(platforms)
    stop_ids = np.concatenate([a["stop_ids"].astype(np.int64),
                               np.asarray([METRO_ID_BASE + int(s) for s, _, _ in platforms], np.int64)]).astype(np.int32)
    plat_lat = np.asarray([stations[s][1] for s, _, _ in platforms], np.float64)
    plat_lon = np.asarray([stations[s][2] for s, _, _ in platforms], np.float64)
    lat = np.concatenate([a["lat"], plat_lat])
    lon = np.concatenate([a["lon"], plat_lon])
    stop_names = list(bus_meta["stop_names"]) + [stations[s][0] + " Metro Station" for s, _, _ in platforms]

    r_ptr = a["r_ptr"].astype(np.int32).tolist()
    rs_stop = a["rs_stop"].astype(np.int32).tolist()
    rs_sd = a["rs_sd"].astype(np.float32).tolist()
    rs_ord = a["rs_ord"].astype(np.int32).tolist()
    rs_route = a["rs_route"].astype(np.int32).tolist()
    rs_link = a["rs_link"].astype(np.int32).tolist()
    route_ids = a["route_ids"].astype(np.int64).tolist()
    route_short = list(bus_meta["route_short"])
    route_desc = list(bus_meta["route_desc"])
    route_agency = list(bus_meta["route_agency"])
    route_kind = list(bus_meta.get("route_kind", ["bus"] * bus_n_routes))
    route_mode = np.zeros(bus_n_routes, np.int8).tolist()
    line_code = [""] * bus_n_routes
    line_name = [""] * bus_n_routes
    line_color = [""] * bus_n_routes
    metro_route_id = [None] * bus_n_routes
    towards = [""] * bus_n_routes
    metro_route_meta = {}

    cum_naadi = [a["cum_naadi"].astype(np.float32)]
    cum_timetable = [a["cum_timetable"].astype(np.float32)]
    wait_naadi = [a["wait_naadi"].astype(np.float32)]
    wait_timetable = [a["wait_timetable"].astype(np.float32)]
    cv = [a["cv"].astype(np.float32)]
    f_eff = [a["f_eff"].astype(np.float32)]
    f_sched = [a["f_sched"].astype(np.float32)]
    w_emp = [a["w_emp"].astype(np.float32)]
    for p in patterns:
        ridx = len(route_ids)
        start = len(rs_stop)
        code = p["line_code"]
        display, colour, fare_known = LINES.get(code, (code.title(), "#666666", False))
        route_ids.append(METRO_ID_BASE + int(p["route_id"]))
        route_short.append(code)
        route_desc.append(p["desc"])
        route_agency.append("DMRC")
        route_kind.append("metro")
        route_mode.append(1)
        line_code.append(code)
        line_name.append(display)
        line_color.append(colour)
        metro_route_id.append(str(p["route_id"]))
        towards.append(p["towards"])
        for i, sid in enumerate(p["stations"]):
            rs_stop.append(pidx[(sid, code, p["group"])])
            rs_sd.append(float(p["sd_m"][i]))
            rs_ord.append(i + 1)
            rs_route.append(ridx)
            rs_link.append(-1)
        r_ptr.append(len(rs_stop))
        n = len(p["stations"])
        offsets = np.asarray(p["offsets_s"], np.float32)
        freq = np.asarray(p["deps"], np.float32).T
        c = np.broadcast_to(offsets, (2, 24, n)).copy()
        w = np.full((2, 24, n), np.inf, np.float32)
        w[:, :, :-1] = np.where(freq[:, :-1] >= MIN_BPH, np.minimum(1800.0 / np.maximum(freq[:, :-1], 1), MAX_WAIT_S), np.inf)
        c0 = np.zeros((2, 24, bus_n_rs), np.float32)
        w0 = np.zeros((2, 24, bus_n_rs), np.float32)
        # The bus arrays already have the same row count and are extended below.
        cum_naadi.append(c); cum_timetable.append(c.copy())
        wait_naadi.append(w); wait_timetable.append(w.copy())
        cv.append(np.zeros((2, 24, n), np.float32))
        f_eff.append(np.broadcast_to(freq, (2, 24, n)).copy())
        f_sched.append(np.broadcast_to(freq, (2, 24, n)).copy())
        w_emp.append(np.full((2, 24, n), np.nan, np.float32))
        metro_route_meta[str(ridx)] = {"line_code": code, "line": display, "color": colour,
                                       "fare_known": fare_known, "gtfs_route_id": str(p["route_id"]),
                                       "headway": {str(h): (3600.0 / max(float(freq[h, 0]), 1.0)) for h in range(24) if freq[h, 0] > 0},
                                       "towards": p["towards"], "group": int(p["group"])}

    for ridx, info in metro_route_meta.items():
        info["also_towards"] = sorted({x["towards"] for x in metro_route_meta.values()
                                        if x["line_code"] == info["line_code"] and x.get("group") == info.get("group")
                                        and x["towards"] != info["towards"]})

    # Every new table is concatenated only once after all route patterns exist.
    cum_n = np.concatenate([np.concatenate(cum_naadi, axis=2), np.zeros((0,))]) if False else np.concatenate(cum_naadi, axis=2)
    cum_tt = np.concatenate(cum_timetable, axis=2)
    wait_n = np.concatenate(wait_naadi, axis=2)
    wait_tt = np.concatenate(wait_timetable, axis=2)
    cv_all = np.concatenate(cv, axis=2)
    f_eff_all = np.concatenate(f_eff, axis=2)
    f_sched_all = np.concatenate(f_sched, axis=2)
    w_emp_all = np.concatenate(w_emp, axis=2)
    rs_stop_a = np.asarray(rs_stop, np.int32)
    order = np.argsort(rs_stop_a, kind="stable")
    sr_ptr = np.searchsorted(rs_stop_a[order], np.arange(n_stops + 1)).astype(np.int32)

    # Keep all bus footpaths, then add directed station access, interchange,
    # and short street links between metro platforms.
    fp_from, fp_to, fp_s = _base_footpaths(lat[:bus_n_stops], lon[:bus_n_stops], a["fp_ptr"], a["fp_to"], a["fp_s"])
    for pi in range(len(platforms)):
        pstop = bus_n_stops + pi
        # Explicitly query the bus set without relying on the platform index.
        for bi in range(bus_n_stops):
            d = float(haversine(lat[pstop], lon[pstop], lat[bi], lon[bi]))
            if d <= FOOT_RADIUS_M:
                fp_from.extend([bi, pstop]); fp_to.extend([pstop, bi]); fp_s.extend([float(walk_s(d) + ENTRY_S), float(walk_s(d) + EXIT_S)])
    for i, (sid, _, _) in enumerate(platforms):
        for j in range(i + 1, len(platforms)):
            sj = platforms[j][0]
            d = float(haversine(lat[bus_n_stops + i], lon[bus_n_stops + i], lat[bus_n_stops + j], lon[bus_n_stops + j]))
            if sid == sj:
                fp_from.extend([bus_n_stops + i, bus_n_stops + j]); fp_to.extend([bus_n_stops + j, bus_n_stops + i]); fp_s.extend([INTERCHANGE_S, INTERCHANGE_S])
            elif d <= STATION_WALK_M:
                sec = float(walk_s(d) + ENTRY_S + EXIT_S)
                fp_from.extend([bus_n_stops + i, bus_n_stops + j]); fp_to.extend([bus_n_stops + j, bus_n_stops + i]); fp_s.extend([sec, sec])
    fp_ptr, fp_to_a, fp_s_a = _csr(fp_from, fp_to, fp_s, n_stops)

    shp_ptr = a["shp_ptr"].astype(np.int32).tolist()
    shp_lat = a["shp_lat"].astype(np.float32).tolist(); shp_lon = a["shp_lon"].astype(np.float32).tolist(); shp_d = a["shp_d"].astype(np.float32).tolist()
    for p in patterns:
        xy = p["shape"]
        if not xy:
            xy = [[stations[s][1], stations[s][2]] for s in p["stations"]]
        distance = [0.0]
        for (la, lo), (la2, lo2) in zip(xy, xy[1:]):
            distance.append(distance[-1] + float(haversine(la, lo, la2, lo2)))
        shp_lat.extend(x[0] for x in xy); shp_lon.extend(x[1] for x in xy); shp_d.extend(distance); shp_ptr.append(len(shp_lat))

    stop_kind = np.r_[np.zeros(bus_n_stops, np.int8), np.ones(len(platforms), np.int8)]
    entry = np.r_[np.zeros(bus_n_stops, np.float32), np.full(len(platforms), ENTRY_S, np.float32)]
    exit_ = np.r_[np.zeros(bus_n_stops, np.float32), np.full(len(platforms), EXIT_S, np.float32)]
    station_id = [""] * bus_n_stops + [s for s, _, _ in platforms]
    station_name = [""] * bus_n_stops + [stations[s][0] for s, _, _ in platforms]
    meta = dict(bus_meta)
    meta.update({"route_short": route_short, "route_desc": route_desc, "route_agency": route_agency,
                 "route_kind": route_kind, "stop_names": stop_names,
                 "line_name": line_name, "line_code": line_code, "line_color": line_color, "metro_route_id": metro_route_id,
                 "towards": towards, "station_id": station_id, "station_name": station_name,
                 "metro": {"source": "data/processed/gtfs_fixed/metro (DMRC GTFS v1)", "service": "weekday trips used on every day",
                           "entry_s": ENTRY_S, "exit_s": EXIT_S, "interchange_s": INTERCHANGE_S,
                           "station_walk_m": STATION_WALK_M, "platforms": len(platforms),
                           "patterns": len(patterns), "routes": metro_route_meta, "note": NOTE}})
    out_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out_dir / "network.npz", stop_ids=stop_ids, lat=lat, lon=lon,
                        route_ids=np.asarray(route_ids, np.int32), r_ptr=np.asarray(r_ptr, np.int32),
                        rs_stop=rs_stop_a, rs_sd=np.asarray(rs_sd, np.float32), rs_ord=np.asarray(rs_ord, np.int32),
                        rs_route=np.asarray(rs_route, np.int32), rs_link=np.asarray(rs_link, np.int32),
                        sr_ptr=sr_ptr, sr_rs=order.astype(np.int32), fp_ptr=fp_ptr, fp_to=fp_to_a, fp_s=fp_s_a,
                        cum_naadi=cum_n, cum_timetable=cum_tt, wait_naadi=wait_n, wait_timetable=wait_tt,
                        cv=cv_all, f_eff=f_eff_all, f_sched=f_sched_all, w_emp=w_emp_all,
                        stop_kind=stop_kind, stop_entry_s=entry, stop_exit_s=exit_, route_mode=np.asarray(route_mode, np.int8),
                        shp_ptr=np.asarray(shp_ptr, np.int32), shp_lat=np.asarray(shp_lat, np.float32),
                        shp_lon=np.asarray(shp_lon, np.float32), shp_d=np.asarray(shp_d, np.float32))
    (out_dir / "network_meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    print(f"multimodal network: {n_stops} stops, {len(route_ids)} routes, {len(patterns)} metro patterns, {len(platforms)} platforms -> {out_dir}")


def journey_metro_fare(net, j, t_dep):
    """Charge one DMRC token fare for each continuous known metro trip."""
    ist_day = int((t_dep + 19800) // 86400)
    sunday = (ist_day + 3) % 7 == 6
    total = 0
    active = []
    for leg in j.legs + [None]:
        if leg is not None and leg.kind == "metro":
            active.append(leg)
            continue
        if not active:
            continue
        km = 0.0
        known = True
        for m in active:
            r = int(m.route)
            if r < 0 or r >= len(net.route_ids):
                known = False
                break
            code = net.meta.get("line_code", [""] * net.n_routes)[r] if "line_code" in net.meta else net.metro_meta.get("routes", {}).get(str(r), {}).get("line_code", "")
            if code and not LINES.get(code, ("", "", False))[2]:
                known = False
                break
            km += float(net.rs_sd[m.alight_rs] - net.rs_sd[m.board_rs]) / 1000.0
        if not known:
            return None
        total += metro_fare(km, sunday)
        active = []
    return total
