"""Read-only endpoints used by the Naadi web application."""
from __future__ import annotations

import datetime as dt
import importlib
import re
import time
from collections import defaultdict

import numpy as np
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse


class _CoreProxy:
    def __getattr__(self, name):
        return getattr(importlib.import_module(".api", __package__), name)


core = _CoreProxy()
router = APIRouter()
_STOPS_ROWS = None
_ROUTES_BY_BASE = None
_VARIANT_INDEX = None
_ROUTE_BASES_AT_STOP = None
_NET_ID = None


def base_name(variant: str) -> str:
    return re.sub(r"(UP|DOWN)\d*$", "", str(variant)).strip()


def opposite_variant(variant: str):
    m = re.fullmatch(r"(.*?)(UP|DOWN)(\d*)", str(variant).strip(), re.I)
    if not m:
        return None
    return m.group(1) + ("DOWN" if m.group(2).upper() == "UP" else "UP") + m.group(3)


def natural_key(value: str):
    return [int(x) if x.isdigit() else x.upper() for x in re.split(r"(\d+)", str(value))]


def decimate(points, max_n: int = 600):
    points = list(points)
    if len(points) <= max_n:
        return points
    if max_n < 2:
        return points[:max_n]
    idx = np.linspace(0, len(points) - 1, max_n, dtype=int)
    return [points[i] for i in idx]


def in_box(lat: float, lon: float) -> bool:
    return core.BOX[0] <= lat <= core.BOX[1] and core.BOX[2] <= lon <= core.BOX[3]


def validate_bbox(min_lat, max_lat, min_lon, max_lon):
    if min_lat > max_lat or min_lon > max_lon:
        raise HTTPException(400, "Bad bounding box.")
    if not (in_box(min_lat, min_lon) and in_box(max_lat, max_lon)):
        raise HTTPException(400, "Coordinates must be inside Delhi NCR.")


def _is_bus_route(net, r):
    return str(net.route_agency[r]) in ("DTC", "DOT")


def _ensure_cache():
    global _STOPS_ROWS, _ROUTES_BY_BASE, _VARIANT_INDEX, _ROUTE_BASES_AT_STOP, _NET_ID
    net = core.S.net
    if net is None:
        raise HTTPException(503, "Model is not loaded.")
    if _NET_ID == id(net):
        return
    _NET_ID = id(net)
    _STOPS_ROWS = []
    _ROUTES_BY_BASE = defaultdict(list)
    _VARIANT_INDEX = {}
    _ROUTE_BASES_AT_STOP = defaultdict(set)
    nroutes = np.diff(net.sr_ptr)
    for i, stop_id in enumerate(net.stop_ids):
        if int(stop_id) >= 90_000_000:
            continue
        _STOPS_ROWS.append([int(stop_id), net.stop_names[i], round(float(net.lat[i]), 5),
                            round(float(net.lon[i]), 5), int(nroutes[i])])
        for rs in net.sr_rs[net.sr_ptr[i]:net.sr_ptr[i + 1]]:
            r = int(net.rs_route[int(rs)])
            if _is_bus_route(net, r):
                _ROUTE_BASES_AT_STOP[i].add(base_name(net.route_short[r]))
    for r in range(net.n_routes):
        if not _is_bus_route(net, r):
            continue
        variant = str(net.route_short[r]).strip()
        base = base_name(variant)
        _ROUTES_BY_BASE[base].append(r)
        _VARIANT_INDEX[variant.upper()] = r
    for base in _ROUTES_BY_BASE:
        _ROUTES_BY_BASE[base].sort(key=lambda r: ("DOWN" in str(net.route_short[r]).upper(), natural_key(str(net.route_short[r]))))
    for stop in _ROUTE_BASES_AT_STOP:
        _ROUTE_BASES_AT_STOP[stop] = sorted(_ROUTE_BASES_AT_STOP[stop], key=natural_key)


def _desc(net, r):
    bits = str(net.route_desc[r] or "").split(" to ", 1)
    return (bits[0], bits[1] if len(bits) == 2 else "")


def _route_stops(net, r):
    return range(int(net.r_ptr[r]), int(net.r_ptr[r + 1]))


@router.get("/capabilities")
def capabilities():
    return {"web_api_version": 1}


@router.get("/stops/all")
def stops_all():
    _ensure_cache()
    return JSONResponse({"fields": ["stop_id", "name", "lat", "lon", "routes"], "count": len(_STOPS_ROWS),
                         "stops": _STOPS_ROWS, "attribution": core.ATTRIBUTION},
                        headers={"Cache-Control": "public, max-age=86400"})


@router.get("/stops/nearby")
def stops_nearby(lat: float, lon: float, radius_m: int = Query(500, ge=50, le=1500),
                 limit: int = Query(10, ge=1, le=30)):
    if not in_box(lat, lon):
        raise HTTPException(400, "Coordinates must be inside Delhi NCR.")
    _ensure_cache()
    net = core.S.net
    indices, distances = net.nearby(lat, lon, radius_m)
    rows = []
    for i, distance in zip(indices[:limit], distances[:limit]):
        i = int(i)
        if int(net.stop_ids[i]) >= 90_000_000:
            continue
        routes = list(_ROUTE_BASES_AT_STOP.get(i, []))
        rows.append({"stop_id": int(net.stop_ids[i]), "name": net.stop_names[i], "lat": round(float(net.lat[i]), 5),
                     "lon": round(float(net.lon[i]), 5), "distance_m": round(float(distance)),
                     "walk_min": round(float(distance) * 1.35 / 1.25 / 60, 1), "routes": routes[:12],
                     "routes_more": max(0, len(routes) - 12)})
    return {"query": {"lat": lat, "lon": lon, "radius_m": radius_m}, "stops": rows}


@router.get("/routes/search")
def routes_search(q: str = Query(..., min_length=1, max_length=40), limit: int = Query(8, ge=1, le=20)):
    q = q.strip()
    if not q:
        raise HTTPException(400, "Give a route number, e.g. 405.")
    _ensure_cache()
    query = q.upper()
    matches = []
    for base, variants in _ROUTES_BY_BASE.items():
        upper = base.upper()
        score = 3 if query == upper or any(query == str(core.S.net.route_short[r]).upper() for r in variants) else 2 if upper.startswith(query) else 1 if query in upper else 0
        if score:
            matches.append((score, base, variants))
    matches.sort(key=lambda x: (-x[0], natural_key(x[1])))
    net = core.S.net
    out = []
    for _, base, variants in matches[:limit]:
        rows = []
        for r in variants:
            frm, towards = _desc(net, r)
            rows.append({"route_id": int(net.route_ids[r]), "variant": str(net.route_short[r]), "from": frm,
                         "towards": towards, "stops": int(net.r_ptr[r + 1] - net.r_ptr[r]), "agency": str(net.route_agency[r])})
        out.append({"route": base, "variants": rows})
    return {"query": q, "routes": out}


def _route_index(route_id: int):
    _ensure_cache()
    r = core.S.net.route_index.get(route_id)
    if r is None or not _is_bus_route(core.S.net, r):
        raise HTTPException(404, "Unknown route_id.")
    return int(r)


@router.get("/routes/{route_id}")
def route_detail(route_id: int, day_type: str | None = None, hour: int | None = Query(None, ge=0, le=23)):
    r = _route_index(route_id)
    if day_type is None:
        day_type = "weekend" if dt.datetime.now(core.IST).weekday() >= 5 else "weekday"
    if day_type not in ("weekday", "weekend"):
        raise HTTPException(422, "day_type must be weekday or weekend.")
    if hour is None:
        hour = dt.datetime.now(core.IST).hour
    net, pl = core.S.net, core.S.naadi
    we = 1 if day_type == "weekend" else 0
    first, last = int(net.r_ptr[r]), int(net.r_ptr[r + 1]) - 1
    cum = pl.cum[we]
    factor = getattr(pl, "calib", (1, 1))[1]
    stops = []
    for rs in range(first, last + 1):
        si = int(net.rs_stop[rs])
        mins = (float(cum[hour, rs]) - float(cum[hour, first])) / 60 * factor
        stops.append({"stop_id": int(net.stop_ids[si]), "name": net.stop_names[si], "lat": round(float(net.lat[si]), 5),
                      "lon": round(float(net.lon[si]), 5), "ord": int(net.rs_ord[rs]), "dist_m": round(float(net.rs_sd[rs] - net.rs_sd[first]), 1),
                      "min_from_start": round(max(0, mins), 1)})
    hourly = {}
    for name, wi in (("weekday", 0), ("weekend", 1)):
        vals, bph = [], []
        for h in range(24):
            rates = np.asarray(net.f_eff[wi, h, first:last], dtype=float)
            rate = float(np.median(rates)) if rates.size else 0
            served = rate >= 0.35
            bph.append(round(rate, 2) if served else None)
            vals.append(round(float(pl.cum[wi, h, last] - pl.cum[wi, h, first]) / 60 * factor, 1) if served else None)
        hourly[name] = {"end_to_end_min": vals, "buses_per_hour": bph}
    variant = str(net.route_short[r])
    opposite = opposite_variant(variant)
    opp_r = _VARIANT_INDEX.get(opposite.upper()) if opposite else None
    frm, towards = _desc(net, r)
    body = {"route_id": int(net.route_ids[r]), "route": base_name(variant), "variant": variant, "from": frm,
            "towards": towards, "agency": str(net.route_agency[r]), "opposite_route_id": int(net.route_ids[opp_r]) if opp_r is not None else None,
            "day_type": day_type, "hour": hour, "stops": stops,
            "geometry": decimate(core.shape_slice(r, 0, 1e12)), "hourly": hourly, "attribution": core.ATTRIBUTION}
    return JSONResponse(body, headers={"Cache-Control": "public, max-age=600"})


@router.get("/live/buses")
def live_buses(route_id: int | None = None, min_lat: float = core.BOX[0], max_lat: float = core.BOX[1],
              min_lon: float = core.BOX[2], max_lon: float = core.BOX[3]):
    validate_bbox(min_lat, max_lat, min_lon, max_lon)
    _ensure_cache()
    selected = _route_index(route_id) if route_id is not None else None
    net = core.S.net
    with core.S.live.lock:
        buses, feed_ts = list(core.S.live.buses), core.S.live.feed_ts
    rows = []
    for _, r, lat, lon, ts, progress in buses:
        if selected is not None and r != selected or not (min_lat <= lat <= max_lat and min_lon <= lon <= max_lon):
            continue
        rows.append([int(net.route_ids[r]) if r >= 0 else None, base_name(net.route_short[r]) if r >= 0 else "",
                     str(net.route_short[r]) if r >= 0 else "", round(lat, 5), round(lon, 5), int(max(0, feed_ts - ts)),
                     round(progress, 1) if progress >= 0 else None])
    return JSONResponse({"feed_time": core.iso(feed_ts) if feed_ts else None, "count": len(rows),
                         "fields": ["route_id", "route", "variant", "lat", "lon", "age_s", "progress_m"], "buses": rows,
                         "note": "Vehicle identifiers and licence plates are never published."}, headers={"Cache-Control": "no-store"})


@router.get("/legs/next-buses")
def next_buses(board: int, alight: int):
    _ensure_cache()
    net = core.S.net
    b, a = net.stop_index.get(board), net.stop_index.get(alight)
    if b is None or a is None:
        raise HTTPException(404, "Unknown stop_id.")
    if b == a:
        raise HTTPException(400, "board and alight must differ.")
    from . import strategy
    t = time.time()
    candidates = strategy.leg_options(core.S.naadi, b, a, t)
    chosen, _, _ = strategy.attractive_set(candidates)
    _, cum, _ = core.S.naadi.tables(t)
    h0, h1, w = core._hw(t)
    cum_h = (1 - w) * cum[h0] + w * cum[h1]
    upcoming = core.S.live.next_buses([c[1] for c in chosen], t, cum_h, max_ahead_s=3600)
    routes = []
    for c in chosen:
        r = int(c[0]); routes.append({"route": base_name(net.route_short[r]), "variant": str(net.route_short[r]), "route_id": int(net.route_ids[r])})
    buses = []
    with core.S.live.lock:
        positions = {x[0]: x for x in core.S.live.buses}
        feed_ts = core.S.live.feed_ts
    for rs, eta, public_id in sorted(upcoming, key=lambda x: x[1])[:8]:
        r = int(net.rs_route[int(rs)])
        pos = positions.get(public_id)
        row = {"route": base_name(net.route_short[r]), "variant": str(net.route_short[r]), "route_id": int(net.route_ids[r]),
               "eta_min": round(max(0, (eta - t) / 60), 1), "lat": None, "lon": None,
               "age_s": None if not feed_ts else int(max(0, feed_ts - pos[4])) if pos else None}
        if pos:
            row["lat"], row["lon"] = round(pos[2], 5), round(pos[3], 5)
        buses.append(row)
    return {"now": core.iso(t), "live": bool(feed_ts and t - feed_ts <= 600), "routes": routes, "buses": buses}
