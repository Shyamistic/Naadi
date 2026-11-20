"""Naadi HTTP API (FastAPI). Run: uvicorn naadi.api:app --host 0.0.0.0 --port 8000

Main endpoint: GET /journeys?from=...&to=...&depart=... (the brief's example API).
Data: Delhi Transport Stack (delhi.transportstack.in) and Delhi Open Transit Data; see /about.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from .linkgrid import LinkGrid
from .live import LiveEngine
from .network import Network, haversine
from .nowcast import NowcastParams
from .paths import DATA, MODEL, RESULTS, ROOT
from .router import IST_S, Planner, _hw, _interp
from .fares import fare_for_leg
from .strategy import plan_options, refine, route_label
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
BOX = (28.15, 29.40, 76.55, 77.75)  # Delhi NCR bounds accepted for coordinates
VERSION = "naadi-1.0 (history: Oct 2026, 31 days; model: LightGBM link times + live nowcast)"
EXTENSION_NOTE = ("Metro and Namo Bharat times come from GTFS timetables; shared-auto times come from frequency survey data. "
                  "All multimodal extension times are estimates, not live observations, and are excluded from Naadi's scored bus accuracy results.")
NOTE = ("Metro times come from the DMRC timetable (GTFS v1). Its calendar ended on 31 Dec 2025 and it has no Sunday trips, "
        "so the weekday timetable is used on every day. They are timetable estimates, not checked against live trains, "
        "and are not part of Naadi's accuracy results.")
ATTRIBUTION = ("Bus data: Delhi Transport Stack (delhi.transportstack.in) and Delhi Open Transit Data "
               "(Department of Transport, GNCTD; IIIT-Delhi). Map data: OpenStreetMap contributors.")
ALIASES = {"kashmiri gate": "kashmere gate", "kashmiri": "kashmere", "cp": "connaught place", "connaught": "shivaji stadium",
           "aiims": "aiims", "isbt kashmere gate": "isbt kashmere gate", "new delhi station": "new delhi railway station",
           "ndls": "new delhi railway station", "old delhi station": "old delhi railway station", "airport": "igi airport",
           "nehru place": "nehru place", "anand vihar": "anand vihar isbt"}


class State:
    pass


S = State()


def load() -> None:
    net_name = os.environ.get("NAADI_NETWORK", "network_prod")
    mm = MODEL / "network_prod_mm"
    if net_name == "network_prod" and mm.exists():
        net_name = "network_prod_mm"
    net = Network(MODEL / net_name)
    grid = LinkGrid(MODEL / os.environ.get("NAADI_GRID", "grid_oct_all.parquet"), methods=("gbm",))
    geom = pq.read_table(MODEL / "tables" / os.environ.get("NAADI_TABLES", "oct_all") / "geom.parquet").to_pydict()
    gi = grid.index(np.array(geom["route_id"]), np.array(geom["ord"]))
    ck = (np.array(geom["gy"], np.int64) * 100000 + np.array(geom["gx"], np.int64)) * 8 + np.array(geom["hd"])
    _, cid = np.unique(ck, return_inverse=True)
    cell_of_link = np.zeros(len(grid.route), np.int64)
    cell_of_link[gi[gi >= 0]] = cid[gi >= 0]
    p = NowcastParams()
    ev = RESULTS / "eta_oct.json"
    if ev.exists():
        p = NowcastParams(**json.loads(ev.read_text())["nowcast"])
    S.net, S.grid = net, grid
    S.has_multimodal = bool(np.any(np.isin(np.asarray(getattr(net, "route_kind", ["bus"] * net.n_routes)), ["metro", "rail", "shared_auto"])))
    S.naadi, S.tt = Planner(net, "naadi"), Planner(net, "timetable")
    S.live = LiveEngine(net, grid, cell_of_link, Path(os.environ.get("NAADI_SNAPSHOT", DATA / "live" / "latest.pb")), p)
    cal = MODEL / os.environ.get("NAADI_CALIBRATION", "calibration_v2.json")
    if not cal.exists():
        cal = MODEL / "calibration.json"
    S.calib_live = (1.0, 1.0)
    if cal.exists():
        f = json.loads(cal.read_text())["factors"]
        if "naadi" in f:
            S.naadi.calib = (f["naadi"]["wait"], f["naadi"]["ride"])
        if "naadi_live" in f:
            S.calib_live = (f["naadi_live"]["wait"], f["naadi_live"]["ride"])
            S.live_wait_factor = f["naadi_live"].get("live_wait", 1.0)
        else:
            S.live_wait_factor = 1.0
    else:
        S.live_wait_factor = 1.0
    iv = MODEL / os.environ.get("NAADI_INTERVALS", "intervals_v2.json")
    if not iv.exists():
        iv = MODEL / "intervals.json"
    S.intervals = json.loads(iv.read_text()) if iv.exists() else None
    acc = RESULTS / "summary.json"
    S.accuracy = json.loads(acc.read_text()) if acc.exists() else {}
    ac = MODEL / "route_ac.json"
    S.route_ac = json.loads(ac.read_text()) if ac.exists() else {}
    # stop search index: one entry per distinct name, centroid of its stops
    groups = defaultdict(list)
    for i, n in enumerate(net.stop_names):
        groups[norm(n)].append(i)
    nroutes = np.diff(net.sr_ptr)
    S.search = [(k, v, net.stop_names[v[0]], float(np.mean(net.lat[v])), float(np.mean(net.lon[v])), int(nroutes[v].sum()))
                for k, v in groups.items()]
    S.cells = speed_cells()
    threading.Thread(target=live_loop, daemon=True).start()


def live_loop():
    while True:
        try:
            S.live.poll()
        except Exception as e:  # keep serving if one snapshot is bad
            print("live poll error", type(e).__name__, e)
        time.sleep(4)


def norm(s: str) -> str:
    s = re.sub(r"[^a-z0-9 ]+", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def speed_cells():
    t = pq.read_table(MODEL / "tables" / os.environ.get("NAADI_TABLES", "oct_all") / "cell_h.parquet").to_pydict()
    acc = defaultdict(lambda: np.zeros((2, 24, 2)))
    for gy, gx, h, we, n, lp in zip(t["gy"], t["gx"], t["hour"], t["we"], t["n"], t["lpace_mean"]):
        a = acc[(gy, gx)]
        a[we, h, 0] += n * lp
        a[we, h, 1] += n
    out = []
    for (gy, gx), a in acc.items():
        if a[:, :, 1].sum() < 200:
            continue
        with np.errstate(invalid="ignore", divide="ignore"):
            kmh = 3600.0 / np.exp(a[:, :, 0] / a[:, :, 1])
        kmh = np.where(a[:, :, 1] >= 10, np.round(kmh, 1), np.nan)
        out.append({"lat": round((gy + 0.5) * 0.0045, 5), "lon": round((gx + 0.5) * 0.0051, 5),
                    "weekday": [None if not np.isfinite(x) else float(x) for x in kmh[0]],
                    "weekend": [None if not np.isfinite(x) else float(x) for x in kmh[1]], "n": int(a[:, :, 1].sum())})
    return out


app = FastAPI(title="Naadi API", version="1.0",
              description="Delhi bus travel-time model and journey planner built on the Delhi Transport Stack. "
                          "Times come from 31 days of real bus GPS (Oct 2026) plus a live nowcast. " + ATTRIBUTION)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=1000)
_hits: dict[str, deque] = defaultdict(deque)


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    q, now = _hits[ip], time.time()
    while q and q[0] < now - 60:
        q.popleft()
    if len(q) >= 120:
        return JSONResponse({"detail": "Too many requests; try again in a minute."}, status_code=429)
    q.append(now)
    return await call_next(request)


@app.on_event("startup")
def _startup():
    load()


# ---------------------------------------------------------------- helpers
def resolve(q: str):
    q = (q or "").strip()
    if not q or len(q) > 120:
        raise HTTPException(400, "Give a place as 'lat,lon', a stop_id (e.g. 'stop:7571') or a stop name.")
    m = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*", q)
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        if not (BOX[0] <= lat <= BOX[1] and BOX[2] <= lon <= BOX[3]):
            raise HTTPException(400, "Coordinates must be inside Delhi NCR.")
        return lat, lon, f"{lat:.5f}, {lon:.5f}"
    m = re.fullmatch(r"stop:(\d+)", q)
    if m:
        i = S.net.stop_index.get(int(m.group(1)))
        if i is None:
            raise HTTPException(404, "Unknown stop_id.")
        return float(S.net.lat[i]), float(S.net.lon[i]), S.net.stop_names[i]
    hits = search_stops(q, 1)
    if not hits:
        raise HTTPException(404, f"No stop matches '{q}'.")
    h = hits[0]
    return h["lat"], h["lon"], h["name"]


def search_stops(q: str, limit: int = 8):
    n = norm(q)
    n = ALIASES.get(n, n)
    toks = n.split()
    out = []
    for key, idx, name, lat, lon, nr in S.search:
        if key.startswith(n):
            sc = 3.0
        elif all(any(w.startswith(t) for w in key.split()) for t in toks):
            sc = 2.0
        elif n in key:
            sc = 1.0
        else:
            continue
        out.append((sc, nr, name, lat, lon, idx))
    out.sort(key=lambda x: (-x[0], -x[1]))
    return [{"name": nm, "lat": round(la, 6), "lon": round(lo, 6), "routes": nr,
             "stop_ids": [int(S.net.stop_ids[i]) for i in idx]} for _, nr, nm, la, lo, idx in out[:limit]]


def parse_depart(s: str | None) -> tuple[float, bool]:
    now = time.time()
    if not s or s == "now":
        return now, True
    try:
        t = dt.datetime.fromisoformat(s)
    except ValueError:
        raise HTTPException(400, "depart must be 'now' or ISO time, e.g. 2026-11-17T08:30 (IST).")
    if t.tzinfo is None:
        t = t.replace(tzinfo=IST)
    return t.timestamp(), abs(t.timestamp() - now) <= 900


def iso(t: float) -> str:
    return dt.datetime.fromtimestamp(t, IST).isoformat(timespec="minutes")


def fare(dist_km: float):
    na = 5 if dist_km <= 4 else 10 if dist_km <= 10 else 15
    ac = 10 if dist_km <= 4 else 15 if dist_km <= 8 else 20 if dist_km <= 12 else 25
    return na, ac


def shape_slice(r: int, d0: float, d1: float, step: int = 1):
    n = S.net
    a, b = int(n.shp_ptr[r]), int(n.shp_ptr[r + 1])
    sd = n.shp_d[a:b]
    i0 = max(0, int(np.searchsorted(sd, d0)) - 1)
    i1 = min(b - a, int(np.searchsorted(sd, d1)) + 1)
    lat, lon = n.shp_lat[a + i0:a + i1], n.shp_lon[a + i0:a + i1]
    return [[round(float(x), 5), round(float(y), 5)] for x, y in zip(lon[::step], lat[::step])]


def interval(total_s: float, live: bool, wait_hist_s: float = 0.0):
    iv = S.intervals
    if not iv:
        return None
    key = "live" if live and "live" in iv else "history"
    spec = iv.get(key)
    if not spec:
        return None
    band = next((b for b in spec["bands"] if total_s / 60 <= b["max_min"]), spec["bands"][-1])
    q_lo, q_hi = band.get("q_lo", 0.0), band.get("q_hi", 0.0)
    groups = spec.get("groups", [])
    if groups:
        wait_class = int(np.digitize(wait_hist_s / 60, spec.get("wait_edges_min", [])))
        group = next((g for g in groups if g.get("max_min") == band.get("max_min") and g.get("wait_class") == wait_class), None)
        if group is not None:
            q_lo, q_hi = group.get("q_lo", q_lo), group.get("q_hi", q_hi)
    return total_s * math.exp(q_lo), total_s * math.exp(q_hi)


def leg_json(l, live_info):
    n = S.net
    if l.kind == "walk":
        pts = []
        a = (float(n.lat[l.from_stop]), float(n.lon[l.from_stop])) if l.from_stop >= 0 else None
        b = (float(n.lat[l.to_stop]), float(n.lon[l.to_stop])) if l.to_stop >= 0 else None
        return {"type": "walk", "minutes": round((l.t1 - l.t0) / 60, 1), "metres": round(l.walk_m),
                "from_stop": int(n.stop_ids[l.from_stop]) if l.from_stop >= 0 else None,
                "to_stop": int(n.stop_ids[l.to_stop]) if l.to_stop >= 0 else None,
                "_ends": (a, b)}
    if l.kind in ("metro", "rail", "shared_auto"):
        ridx = l.route
        if l.kind in ("rail", "shared_auto"):
            operator = getattr(n, "route_operator", [""] * n.n_routes)[ridx]
            source = getattr(n, "route_time_source", [""] * n.n_routes)[ridx]
            fare_data = getattr(n, "route_fare", [None] * n.n_routes)[ridx]
            board = {"stop_id": int(n.stop_ids[l.from_stop]), "name": n.stop_names[l.from_stop], "lat": float(n.lat[l.from_stop]),
                     "lon": float(n.lon[l.from_stop]), "time": iso(l.t0 + l.wait_s)}
            alight = {"stop_id": int(n.stop_ids[l.to_stop]), "name": n.stop_names[l.to_stop], "lat": float(n.lat[l.to_stop]),
                      "lon": float(n.lon[l.to_stop]), "time": iso(l.t1)}
            if l.kind == "rail":
                return {"type": "rail", "operator": operator or "NCRTC", "service": "Namo Bharat", "route_id": int(n.route_ids[ridx]),
                        "route": n.route_short[ridx], "towards": n.towards[ridx], "board": board, "alight": alight,
                        "wait_min": round(l.wait_s / 60, 1), "ride_min": round(l.ride_s / 60, 1),
                        "schedule_estimated": True, "estimated": True, "time_source": source or "NCRTC timetable (GTFS v1)",
                        "fare_inr": None, "geometry": shape_slice(ridx, float(n.rs_sd[l.board_rs]), float(n.rs_sd[l.alight_rs]))}
            return {"type": "shared_auto", "operator": operator or "Shared Last Mile", "service": "Shared auto / e-rickshaw",
                    "route_id": int(n.route_ids[ridx]), "route": n.route_short[ridx], "towards": n.towards[ridx], "board": board, "alight": alight,
                    "wait_min": round(l.wait_s / 60, 1), "ride_min": round(l.ride_s / 60, 1), "frequency_estimated": True,
                    "estimated": True, "time_source": source or "Shared mobility GTFS v1 frequency survey (estimated)",
                    "fare_inr": fare_data, "geometry": shape_slice(ridx, float(n.rs_sd[l.board_rs]), float(n.rs_sd[l.alight_rs]))}
        info = n.metro_meta.get("routes", {}).get(str(ridx), {})
        board_sid = n.station_id[l.from_stop] if hasattr(n, "station_id") else str(int(n.stop_ids[l.from_stop]) - 90000000)
        alight_sid = n.station_id[l.to_stop] if hasattr(n, "station_id") else str(int(n.stop_ids[l.to_stop]) - 90000000)
        headways = info.get("headway", {})
        h = str(int(((l.t0 + IST_S) % 86400) // 3600))
        toward = n.towards[ridx] if getattr(n, "towards", None) else info.get("towards", "")
        return {"type": "metro", "line": n.line_name[ridx], "line_code": n.line_code[ridx],
                "line_color": n.line_color[ridx], "route_id": str(n.metro_route_id[ridx]), "towards": toward,
                "also_towards": sorted(set(info.get("also_towards", [])) - {toward}),
                "board": {"station_id": str(board_sid), "name": n.station_name[l.from_stop], "lat": float(n.lat[l.from_stop]),
                          "lon": float(n.lon[l.from_stop]), "time": iso(l.t0 + l.wait_s)},
                "alight": {"station_id": str(alight_sid), "name": n.station_name[l.to_stop], "lat": float(n.lat[l.to_stop]),
                           "lon": float(n.lon[l.to_stop]), "time": iso(l.t1)},
                "wait_min": round(2 * l.wait_s / 60, 1), "ride_min": round(l.ride_s / 60, 1),
                "headway_min": round(float(headways.get(h, 1800.0)) / 60, 1),
                "stops": int(n.rs_ord[l.alight_rs] - n.rs_ord[l.board_rs]),
                "distance_km": round(float(n.rs_sd[l.alight_rs] - n.rs_sd[l.board_rs]) / 1000, 1),
                "schedule_estimated": True, "time_source": "DMRC timetable (GTFS v1)", "fare_inr": None,
                "geometry": shape_slice(l.route, float(n.rs_sd[l.board_rs]), float(n.rs_sd[l.alight_rs]))}
    r = l.route
    short = n.route_short[r]
    label = route_label(short)
    dist_km = float(n.rs_sd[l.alight_rs] - n.rs_sd[l.board_rs]) / 1000
    board_stop_id = int(n.stop_ids[n.rs_stop[l.board_rs]])
    alight_stop_id = int(n.stop_ids[n.rs_stop[l.alight_rs]])
    route_id = int(n.route_ids[r])
    non_ac_quote = fare_for_leg(route_id, board_stop_id, alight_stop_id, False, dist_km * 1000.0)
    ac_quote = fare_for_leg(route_id, board_stop_id, alight_stop_id, True, dist_km * 1000.0)
    alts = sorted({route_label(n.route_short[a[0]]) for a in getattr(l, "alternatives", [])} - {label})
    samples = int(S.grid.n_hist[n.rs_link[l.board_rs:l.alight_rs][n.rs_link[l.board_rs:l.alight_rs] >= 0]].sum()) if l.alight_rs > l.board_rs else 0
    return {"type": "bus", "route": label, "route_variant": short.strip(),
            "route_id": int(n.route_ids[r]), "towards": n.route_desc[r].split(" to ")[-1] if n.route_desc[r] else "",
                      "also": alts,
            "board": {"stop_id": int(n.stop_ids[l.from_stop]), "name": n.stop_names[l.from_stop],
                      "lat": float(n.lat[l.from_stop]), "lon": float(n.lon[l.from_stop]), "time": iso(l.t0 + l.wait_s)},
            "alight": {"stop_id": int(n.stop_ids[l.to_stop]), "name": n.stop_names[l.to_stop],
                       "lat": float(n.lat[l.to_stop]), "lon": float(n.lon[l.to_stop]), "time": iso(l.t1)},
            "wait_min": round(l.wait_s / 60, 1), "ride_min": round(l.ride_s / 60, 1),
            "stops": int(n.rs_ord[l.alight_rs] - n.rs_ord[l.board_rs]), "distance_km": round(dist_km, 1),
            "fare_inr": {"non_ac": non_ac_quote.fare_inr, "ac": ac_quote.fare_inr, "pink_saheli": 0},
            "fare_source": {"non_ac": "observed" if non_ac_quote.source == "empirical" else "estimated",
                            "ac": "observed" if ac_quote.source == "empirical" else "estimated"},
            "ac_share": S.route_ac.get(str(int(n.route_ids[r]))),
            "wait_source": live_info.get("wait_source", "history"), "next_buses_min": live_info.get("next", []),
            "ride_source": "live+history" if live_info.get("live") else "history",
            "history_samples": samples,
            "geometry": shape_slice(r, float(n.rs_sd[l.board_rs]), float(n.rs_sd[l.alight_rs]))}


def journey_json(j, label_set, live, t_dep, pl_tt, o_xy, d_xy, multimodal=False):
    n = S.net
    legs, info = [], []
    for l in j.legs:
        li = getattr(l, "live_info", {}) if live else {}
        legs.append(leg_json(l, li))
    # walk geometries: straight segments between known points
    for i, lg in enumerate(legs):
        if lg["type"] == "walk":
            a, b = lg.pop("_ends")
            prev = legs[i - 1]["alight"] if i > 0 and legs[i - 1]["type"] in ("bus", "metro") else None
            nxt = legs[i + 1]["board"] if i + 1 < len(legs) and legs[i + 1]["type"] in ("bus", "metro") else None
            p0 = (prev["lat"], prev["lon"]) if prev else a or o_xy
            p1 = (nxt["lat"], nxt["lon"]) if nxt else b or d_xy
            lg["geometry"] = [[round(p0[1], 5), round(p0[0], 5)], [round(p1[1], 5), round(p1[0], 5)]]
            kinds = getattr(n, "stop_kind", np.zeros(n.n_stops, np.int8))
            from_stop, to_stop = j.legs[i].from_stop, j.legs[i].to_stop
            from_platform = from_stop >= 0 and int(kinds[from_stop]) == 1
            to_platform = to_stop >= 0 and int(kinds[to_stop]) == 1
            if from_platform and to_platform and getattr(n, "station_id", [""] * n.n_stops)[from_stop] == getattr(n, "station_id", [""] * n.n_stops)[to_stop]:
                lg["interchange"] = True
                lg["minutes"] = 4.0
            else:
                access = (1.5 if from_platform else 0.0) + (3.0 if to_platform else 0.0)
                if from_platform and to_platform:
                    access = 4.5
                if access:
                    lg["station_access_min"] = access

    tot = j.total_s
    wait_hist_s = sum(l.wait_s for l in j.legs if l.kind == "bus" and l.live_info.get("wait_source") != "live bus")
    rng = None if multimodal else interval(tot, live, wait_hist_s)
    h_dep = int(((t_dep + IST_S) % 86400) // 3600)
    off = (t_dep + IST_S) % 3600
    day0 = math.floor((t_dep + IST_S) / 86400) * 86400 - IST_S
    chakra = []
    for h in range(24):
        r2 = refine(S.naadi, j, day0 + h * 3600 + off)
        chakra.append(None if r2 is None else round(r2.total_s / 60, 1))
    chakra[h_dep] = round(j.total_s / 60, 1)
    vals = [(h, v) for h, v in enumerate(chakra) if v is not None]
    quiet = min(vals, key=lambda x: x[1]) if vals else None
    tt = refine(pl_tt, j, t_dep)
    transit_legs = [l for l in legs if l["type"] in ("bus", "metro", "rail", "shared_auto")]
    bus_legs = [l for l in legs if l["type"] == "bus"]
    fare_na = sum(l["fare_inr"]["non_ac"] for l in bus_legs)
    fare_ac = sum(l["fare_inr"]["ac"] for l in bus_legs)
    shared_fare = sum((l.get("fare_inr") or {}).get("amount", 0) for l in legs if l["type"] == "shared_auto")
    rail_present = any(l["type"] == "rail" for l in legs)
    fare = {"non_ac": fare_na, "ac": fare_ac, "pink_saheli": 0}
    if multimodal:
        from .multimodal import journey_metro_fare
        metro_fare = journey_metro_fare(S.net, j, t_dep)
        unknown = metro_fare is None or rail_present
        fare = {"non_ac": None if unknown else fare_na + (metro_fare or 0) + shared_fare,
                "ac": None if unknown else fare_ac + (metro_fare or 0) + shared_fare,
                "pink_saheli": None if unknown else (metro_fare or 0) + shared_fare,
                "metro": metro_fare, "rail": None if rail_present else 0,
                "shared_auto": shared_fare}
    mode_order = {"bus": 0, "metro": 1, "rail": 2, "shared_auto": 3}
    modes = sorted({l["type"] for l in transit_legs}, key=lambda x: mode_order.get(x, 99))
    return {"labels": sorted(label_set), "total_min": round(tot / 60, 1),
            "range_min": [round(rng[0] / 60), round(rng[1] / 60)] if rng else None,
            "depart": iso(t_dep), "arrive": iso(j.arrive),
            "arrive_range": [iso(t_dep + rng[0]), iso(t_dep + rng[1])] if rng else None,
            "transfers": max(0, len(transit_legs) - 1), "walk_m": round(j.walk_m()),
            "wait_min": round(sum(l.get("wait_min", 0) for l in transit_legs), 1), "ride_min": round(sum(l.get("ride_min", 0) for l in transit_legs), 1),
            "fare_inr": fare,
            "quiet_hour": {"hour": quiet[0], "total_min": quiet[1]} if quiet else None,
            "samay_chakra": chakra, "timetable_min": round(tt.total_s / 60, 1) if tt else None,
            "live": live, "legs": legs,
            **({"modes": modes, "schedule_estimated": True} if multimodal else {})}


def _arrive_by(frm: str, to: str, arrive: str, options: int, modes: str):
    target, _ = parse_depart(arrive)
    candidates, multimodal = [], []
    for i in range(37):
        departure = target - (36 - i) * 300
        body = journeys(frm, to, depart=iso(departure), arrive=None, options=options, modes=modes)
        for option in body.get("options", []):
            if dt.datetime.fromisoformat(option["arrive"]).timestamp() <= target + 1:
                candidates.append(option)
        for option in body.get("multimodal_options", []):
            if dt.datetime.fromisoformat(option["arrive"]).timestamp() <= target + 1:
                multimodal.append(option)
    def signature(option):
        return tuple((leg.get("type"), leg.get("route") or leg.get("line"), leg.get("board", {}).get("stop_id") or leg.get("board", {}).get("station_id"))
                       for leg in option.get("legs", []) if leg.get("type") != "walk")
    def ranked(items):
        unique = {}
        for item in items:
            unique.setdefault(signature(item), item)
        return sorted(unique.values(), key=lambda x: (-dt.datetime.fromisoformat(x["depart"]).timestamp(), x["total_min"]))[:options]
    selected = ranked(candidates)
    selected_mm = ranked(multimodal)
    if selected:
        result = journeys(frm, to, depart=selected[0]["depart"], arrive=None, options=options, modes=modes)
        result["options"] = selected
        result["multimodal_options"] = selected_mm
    else:
        result = {"query": {"arrive_by": iso(target)}, "options": [], "multimodal_options": selected_mm,
                  "message": "No journey reaches the requested arrival time."}
    result.setdefault("query", {})["arrive_by"] = iso(target)
    return result


# ---------------------------------------------------------------- endpoints
@app.get("/health")
def health():
    return {"status": "ok", "version": VERSION, "live": S.live.summary(), "stops": S.net.n_stops, "routes": S.net.n_routes}


@app.get("/stops/search")
def stops_search(q: str = Query(..., min_length=2, max_length=80), limit: int = Query(8, ge=1, le=25)):
    return {"query": q, "results": search_stops(q, limit)}


@app.get("/journeys")
def journeys(frm: str = Query(..., alias="from", description="'lat,lon', 'stop:<id>' or a stop name"),
             to: str = Query(..., description="'lat,lon', 'stop:<id>' or a stop name"),
             depart: str | None = Query(None, description="'now' (default) or ISO time in IST, e.g. 2026-11-17T08:30"),
             arrive: str | None = Query(None, description="ISO arrival deadline with timezone offset"),
             options: int = Query(3, ge=1, le=5),
             modes: str = Query("bus,metro,rail,shared_auto")):
    if depart is not None and arrive is not None:
        raise HTTPException(422, "Send either depart or arrive, not both.")
    if arrive is not None:
        return _arrive_by(frm, to, arrive, options, modes)
    valid_modes = {"bus", "metro", "rail", "shared_auto"}
    requested = {x.strip() for x in modes.split(",") if x.strip()}
    if not requested or not requested.issubset(valid_modes):
        raise HTTPException(400, "modes must contain only bus, metro, rail, or shared_auto.")
    mode_set = tuple(x for x in ("bus", "metro", "rail", "shared_auto") if x in requested)
    o, d = resolve(frm), resolve(to)
    t_dep, near_now = parse_depart(depart)
    o_xy, d_xy = (o[0], o[1]), (d[0], d[1])
    mult = S.live.nowcast_mult(t_dep) if near_now else None
    live = mult is not None
    first_wait = None
    if live:
        cum_live = S.naadi.tables(t_dep, mult)[1]
        def first_wait(rs, t):
            h0, h1, w = _hw(t)
            cum_h = (1 - w) * cum_live[h0] + w * cum_live[h1]
            return [x[1] for x in S.live.next_buses(rs, t, cum_h)]
    uniq = plan_options(S.naadi, o_xy, d_xy, t_dep, n=options, live_mult=mult,
                        calib=S.calib_live if live else S.naadi.calib,
                        first_wait=first_wait if live else None,
                        live_wait_factor=S.live_wait_factor if live else 1.0, modes=("bus",))
    multimodal = []
    requested_extension = tuple(x for x in mode_set if x != "bus")
    if requested_extension and S.has_multimodal:
        search_modes = tuple(x for x in mode_set if x in ("bus", "metro", "rail", "shared_auto"))
        multimodal = [j for j in plan_options(S.naadi, o_xy, d_xy, t_dep, n=2, live_mult=mult,
                                               calib=S.calib_live if live else S.naadi.calib,
                                               first_wait=first_wait if live else None,
                                               live_wait_factor=S.live_wait_factor if live else 1.0,
                                               modes=search_modes, require_metro=False)
                      if any(l.kind in requested_extension for l in j.legs)]
    if not uniq and not multimodal:
        return {"query": {"from": o[2], "to": d[2], "depart": iso(t_dep), "modes": list(mode_set)}, "options": [],
                "message": "No bus journey found within 1 km of both places at this time.", "attribution": ATTRIBUTION,
                "multimodal_options": [], "multimodal_note": EXTENSION_NOTE if requested_extension and getattr(S, "has_multimodal", False) else None}
    labels = defaultdict(set)
    if uniq:
        labels[min(range(len(uniq)), key=lambda i: uniq[i].total_s)].add("fastest")
        labels[min(range(len(uniq)), key=lambda i: (uniq[i].n_bus, uniq[i].total_s))].add("fewest_changes")
        labels[min(range(len(uniq)), key=lambda i: (uniq[i].walk_m(), uniq[i].total_s))].add("least_walking")
    out = [journey_json(j, labels[i], live, t_dep, S.tt, o_xy, d_xy) for i, j in enumerate(uniq)]
    mm_labels = defaultdict(set)
    if multimodal:
        mm_labels[min(range(len(multimodal)), key=lambda i: multimodal[i].total_s)].add("fastest")
        mm_labels[min(range(len(multimodal)), key=lambda i: (multimodal[i].n_transit, multimodal[i].total_s))].add("fewest_changes")
        mm_labels[min(range(len(multimodal)), key=lambda i: (multimodal[i].walk_m(), multimodal[i].total_s))].add("least_walking")
    mm_out = [journey_json(j, mm_labels[i], live, t_dep, S.tt, o_xy, d_xy, multimodal=True)
              for i, j in enumerate(multimodal)]
    we = int(((math.floor((t_dep + IST_S) / 86400) + 3) % 7) >= 5)
    return {"query": {"from": {"name": o[2], "lat": o[0], "lon": o[1]}, "to": {"name": d[2], "lat": d[0], "lon": d[1]},
                      "depart": iso(t_dep), "day_type": "weekend" if we else "weekday", "live": live,
                      "crow_km": round(float(haversine(o[0], o[1], d[0], d[1])) / 1000, 1), "modes": list(mode_set)},
            "options": out, "model": VERSION, "attribution": ATTRIBUTION,
            "notes": "Times are expected door-to-door minutes. Waits use observed bus frequencies and bunching; rides use "
                     "the model's time for that hour. Fares are indicative (Delhi Tourism city-bus table); women ride free "
                     "with a Pink Saheli card.",
            "multimodal_options": mm_out,
            "multimodal_note": EXTENSION_NOTE if requested_extension and S.has_multimodal else None}


@app.get("/stops/{stop_id}/departures")
def departures(stop_id: int):
    i = S.net.stop_index.get(stop_id)
    if i is None:
        raise HTTPException(404, "Unknown stop_id.")
    n = S.net
    t = time.time()
    _, cum, wait = S.naadi.tables(t)
    h0, h1, w = _hw(t)
    rs = [int(n.sr_rs[j]) for j in range(n.sr_ptr[i], n.sr_ptr[i + 1])]
    cum_h = (1 - w) * cum[h0] + w * cum[h1]
    nb = S.live.next_buses(rs, t, cum_h, max_ahead_s=2700)
    by = defaultdict(list)
    for r_s, eta, pid in nb:
        if eta >= t - 30:
            by[int(r_s)].append(max(0.0, round((eta - t) / 60, 1)))
    rows = []
    for r_s in rs:
        r = int(n.rs_route[r_s])
        ew = _interp(wait[h0, r_s], wait[h1, r_s], w)
        rows.append({"route": re.sub(r"(UP|DOWN)\d*$", "", n.route_short[r]).strip(), "route_variant": n.route_short[r].strip(),
                     "towards": n.route_desc[r].split(" to ")[-1] if n.route_desc[r] else "",
                     "live_eta_min": by.get(r_s, [])[:3],
                     "typical_wait_min": None if not np.isfinite(ew) or ew > 1e8 else round(float(ew) / 60, 1)})
    rows.sort(key=lambda x: (x["live_eta_min"][0] if x["live_eta_min"] else 999, x["typical_wait_min"] or 999))
    return {"stop": {"stop_id": stop_id, "name": n.stop_names[i], "lat": float(n.lat[i]), "lon": float(n.lon[i])},
            "now": iso(t), "departures": rows, "attribution": ATTRIBUTION}


@app.get("/vehicles")
def vehicles(min_lat: float = BOX[0], max_lat: float = BOX[1], min_lon: float = BOX[2], max_lon: float = BOX[3]):
    n = S.net
    with S.live.lock:
        bs = list(S.live.buses)
        ft = S.live.feed_ts
    out = [[pid, n.route_short[r] if r >= 0 else "", round(la, 5), round(lo, 5), int(ft - ts)]
           for pid, r, la, lo, ts, d in bs if min_lat <= la <= max_lat and min_lon <= lo <= max_lon]
    return {"feed_time": iso(ft) if ft else None, "count": len(out),
            "fields": ["id", "route", "lat", "lon", "age_s"], "vehicles": out,
            "note": "ids are anonymised; licence plates are never published."}


@app.get("/speeds/cells")
def speeds():
    return {"cell_size_m": 500, "hours": list(range(24)), "cells": S.cells,
            "source": "Median bus pace per ~500 m road cell from 37.8 M stop-to-stop bus traversals, Oct 2026."}


@app.get("/accuracy")
def accuracy():
    return S.accuracy




from .ts_adapter import router as ts_adapter_router
app.include_router(ts_adapter_router)
