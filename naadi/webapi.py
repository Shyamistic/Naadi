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
                         "note": "Source identities and licence plates are never published."}, headers={"Cache-Control": "no-store"})


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


# ---------------------------------------------------------------- city pulse ("Delhi right now")
import json  # noqa: E402
import math  # noqa: E402

IST_S = 19800
PULSE_TTL_S = 15              # cache: the feed itself refreshes about every 11 s
PULSE_MIN_TRAVERSALS = 200    # below this the city-wide comparison is too noisy to show
SLOW_MIN_TRAVERSALS = 3       # a stretch needs at least this many buses through it in the window
SLOW_MIN_RATIO = 1.35         # and must be taking at least 35% longer than usual
STALE_FEED_S = 600
_pulse_cache: dict = {"at": 0.0, "body": None}
_link_rs_cache: dict = {}


def _link_to_rs(net) -> np.ndarray:
    """For each link id, the route-stop index j such that the link runs from stop j to stop j + 1 of one route."""
    key = id(net)
    m = _link_rs_cache.get(key)
    if m is None:
        rs_link = np.asarray(net.rs_link, np.int64)
        m = np.full(int(rs_link.max()) + 1 if len(rs_link) else 0, -1, np.int64)
        j = np.nonzero(rs_link >= 0)[0]
        m[rs_link[j]] = j
        _link_rs_cache.clear()
        _link_rs_cache[key] = m
    return m


def _pulse_baseline() -> dict | None:
    """Median live-style residual by hour on ordinary October days (scripts/build_pulse_baseline.py), or None."""
    if "baseline" not in _pulse_cache:
        path = core.MODEL / "pulse_baseline.json"
        try:
            _pulse_cache["baseline"] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        except (OSError, ValueError):
            _pulse_cache["baseline"] = None
    return _pulse_cache["baseline"]


def pulse_summary(buses, residuals, feed_ts: float, window_s: float, net, now: float | None = None,
                  baseline: dict | None = None) -> dict:
    """Delhi right now, from the buses' own GPS. A pure function of the live engine's state, so it is testable.

    buses: (public id, route index, lat, lon, ts, progress) for buses reporting in the last 5 minutes.
    residuals: (t_end, link, cell, r) for stretches completed in the last window_s seconds, where
    r = ln(observed stretch time) - ln(the history model's time for that stretch at that hour and day type).
    exp(median r) is therefore "times the usual" for the city, and exp(mean r) per stretch the same for one stretch.
    """
    now = time.time() if now is None else now
    hour = int(((feed_ts + IST_S) % 86400) // 3600) if feed_ts else None
    day = math.floor((feed_ts + IST_S) / 86400) if feed_ts else 0
    stale = not feed_ts or now - feed_ts > STALE_FEED_S
    density: dict = defaultdict(int)  # buses per 0.004-degree cell (about 450 m), for the home map's glow
    for b in buses:
        density[(round(b[2] * 250), round(b[3] * 250))] += 1
    body = {"feed_time": dt.datetime.fromtimestamp(feed_ts, core.IST).isoformat(timespec="minutes") if feed_ts else None,
            "stale": bool(stale), "buses": len(buses), "on_route": sum(1 for b in buses if b[1] >= 0 and b[5] >= 0),
            "window_min": int(round(window_s / 60)), "traversals": len(residuals), "hour": hour,
            "day_type": "weekend" if (day + 3) % 7 >= 5 else "weekday", "vs_usual": None, "slow": [],
            "density": [[k[1] / 250, k[0] / 250, n] for k, n in sorted(density.items())]}
    if stale or not residuals:
        return body
    # On an ordinary day the median residual is already below zero (the model predicts mean times and stretch times
    # are right-skewed), so compare with the same hour and day type on ordinary October days, not with zero.
    offset = 0.0
    if baseline and hour is not None:
        offset = float((baseline.get(body["day_type"]) or {}).get("median_r", [0.0] * 24)[hour] or 0.0)
        body["baseline"] = "ordinary October days, same hour and day type"
    r = np.fromiter((x[3] for x in residuals), np.float64, len(residuals)) - offset
    if len(r) >= PULSE_MIN_TRAVERSALS:
        ratio = float(np.exp(np.median(r)))
        body["vs_usual"] = {"ratio": round(ratio, 3), "pct": int(round((ratio - 1) * 100))}
    links = np.fromiter((x[1] for x in residuals), np.int64, len(residuals))
    l2r = _link_to_rs(net)
    if not len(l2r):
        return body
    ok = (links >= 0) & (links < len(l2r))
    j = np.where(ok, l2r[np.clip(links, 0, len(l2r) - 1)], -1)
    rs_route, rs_stop = np.asarray(net.rs_route), np.asarray(net.rs_stop)
    nxt = np.minimum(j + 1, len(rs_route) - 1)
    ok &= (j >= 0) & (j + 1 < len(rs_route)) & (rs_route[nxt] == rs_route[np.maximum(j, 0)])
    groups: dict = defaultdict(lambda: [0.0, 0, set()])
    for a, b, x, jj in zip(rs_stop[j[ok]].tolist(), rs_stop[nxt[ok]].tolist(), r[ok].tolist(), j[ok].tolist()):
        g = groups[(a, b)]
        g[0] += x
        g[1] += 1
        g[2].add(int(rs_route[jj]))
    slow = [(s / n, n, ab, routes) for ab, (s, n, routes) in groups.items()
            if n >= SLOW_MIN_TRAVERSALS and math.exp(s / n) >= SLOW_MIN_RATIO]
    slow.sort(key=lambda c: -c[0])
    for mean, n, (a, b), routes in slow[:10]:
        names = sorted({base_name(str(net.route_short[x])) for x in routes}, key=natural_key)
        body["slow"].append({"from": str(net.stop_names[a]), "to": str(net.stop_names[b]), "routes": names[:3],
                             "ratio": round(math.exp(mean), 2), "buses": int(n),
                             "coords": [[float(net.lon[a]), float(net.lat[a])], [float(net.lon[b]), float(net.lat[b])]]})
    return body


@router.get("/pulse")
def pulse():
    """Delhi right now: buses reporting, bus travel time against a usual day at this hour, and the slowest stretches."""
    now = time.time()
    if _pulse_cache["body"] is not None and now - _pulse_cache["at"] < PULSE_TTL_S:
        return _pulse_cache["body"]
    live = core.S.live
    with live.lock:
        buses = list(live.buses)
        feed_ts = float(live.feed_ts or 0)
        window = float(live.p.window_s)
        res = [x for x in live.res if x[0] >= feed_ts - window]
    body = pulse_summary(buses, res, feed_ts, window, core.S.net, now, _pulse_baseline())
    _pulse_cache.update(at=now, body=body)
    return body
