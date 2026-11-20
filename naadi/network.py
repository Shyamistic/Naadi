"""The routable bus network: stops, routes in stop order, walking links, ride times and waits.

Ride times: cum[we][hour][rs] = seconds from the route's first stop to route-stop rs, built from the link
model's predicted MEAN time of each link at that hour (so rides add up without bias).
Waits: wait[we][hour][rs] = expected wait for a passenger arriving at random,
       E[W] = (H / 2) (1 + CV^2), H = 3600 / buses per hour (observed), CV from observed headways.
A route-stop-hour with fewer than MIN_BPH buses per hour is treated as not served (wait = inf).
Two variants are built: "naadi" (model times, observed waits) and "timetable" (GTFS times, scheduled
regular headways), so both planners share one router and one network.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import duckdb
import numpy as np

from .linkgrid import LinkGrid
from .paths import GTFS, MODEL, ROOT, WORK
WALK_MS = 1.25        # walking speed (m/s)
DETOUR = 1.35         # street network detour over straight line
FOOT_RADIUS_M = 450   # transfer walks between nearby stops
MIN_BPH = 0.35        # below this a route-stop-hour is not served
MAX_WAIT_S = 3600.0


def walk_s(dist_m):
    return np.asarray(dist_m) * DETOUR / WALK_MS


def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = (np.radians(np.asarray(x, dtype=np.float64)) for x in (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 12742000.0 * np.arcsin(np.sqrt(a))


def build(grid_path: Path, service_path: Path, out: Path) -> None:
    con = duckdb.connect()
    g = LinkGrid(grid_path, methods=("gbm", "tt"))
    st = con.execute(f"SELECT CAST(stop_id AS INTEGER) sid, stop_name, CAST(stop_lat AS DOUBLE), CAST(stop_lon AS DOUBLE) "
                     f"FROM read_csv('{(GTFS / 'stops.txt').as_posix()}', all_varchar=true) ORDER BY 1").fetchall()
    stop_ids = np.array([r[0] for r in st], np.int32)
    names = [r[1] for r in st]
    lat = np.array([r[2] for r in st]); lon = np.array([r[3] for r in st])
    sidx = {s: i for i, s in enumerate(stop_ids.tolist())}
    rt = con.execute(f"SELECT CAST(route_id AS INTEGER), route_short_name, route_long_name, route_desc, agency_id "
                     f"FROM read_csv('{(GTFS / 'routes.txt').as_posix()}', all_varchar=true)").fetchall()
    rinfo = {r[0]: r[1:] for r in rt}
    so = con.execute(f"SELECT route_id, ord, CAST(stop_id AS INTEGER) AS stop_id, sd FROM read_parquet('{(WORK / 'stops_on_shape.parquet').as_posix()}') "
                     f"ORDER BY route_id, ord").fetchnumpy()
    rids, first = np.unique(so["route_id"], return_index=True)
    r_ptr = np.append(first, len(so["route_id"])).astype(np.int32)
    rs_stop = np.array([sidx[s] for s in so["stop_id"]], np.int32)
    rs_sd = so["sd"].astype(np.float32)
    rs_ord = so["ord"].astype(np.int32)
    rs_route = np.repeat(np.arange(len(rids), dtype=np.int32), np.diff(r_ptr))
    rs_link = g.index(so["route_id"], so["ord"]).astype(np.int32)
    last = np.zeros(len(rs_stop), bool); last[r_ptr[1:] - 1] = True
    rs_link[last] = -1
    # stop -> (route, position) CSR
    o = np.argsort(rs_stop, kind="stable")
    sr_ptr = np.searchsorted(rs_stop[o], np.arange(len(stop_ids) + 1)).astype(np.int32)
    sr_rs = o.astype(np.int32)
    # footpaths between nearby stops (grid bucketing)
    cell = (np.floor(lat / 0.005).astype(np.int64) * 100000 + np.floor(lon / 0.005).astype(np.int64))
    buckets: dict[int, list[int]] = {}
    for i, c in enumerate(cell):
        buckets.setdefault(int(c), []).append(i)
    fp_from, fp_to, fp_s = [], [], []
    for i in range(len(stop_ids)):
        cy, cx = divmod(int(cell[i]), 100000)
        cand = [j for dy in (-1, 0, 1) for dx in (-1, 0, 1) for j in buckets.get((cy + dy) * 100000 + cx + dx, []) if j != i]
        if not cand:
            continue
        cand = np.array(cand)
        d = haversine(lat[i], lon[i], lat[cand], lon[cand])
        m = d <= FOOT_RADIUS_M
        fp_from += [i] * int(m.sum()); fp_to += cand[m].tolist(); fp_s += walk_s(d[m]).tolist()
    fp_from = np.array(fp_from, np.int32); fp_to = np.array(fp_to, np.int32); fp_s = np.array(fp_s, np.float32)
    o = np.argsort(fp_from, kind="stable")
    fp_ptr = np.searchsorted(fp_from[o], np.arange(len(stop_ids) + 1)).astype(np.int32)
    fp_to, fp_s = fp_to[o], fp_s[o]
    # ride times per hour: mean link time (gbm) and timetable time
    n_rs = len(rs_stop)
    link_ok = rs_link >= 0
    cum = {}
    for name, meth in (("naadi", "gbm"), ("timetable", "tt")):
        c = np.zeros((2, 24, n_rs), np.float32)
        for we in (0, 1):
            for h in range(24):
                tt = np.zeros(n_rs, np.float32)
                tt[link_ok] = np.exp(g.g[meth][rs_link[link_ok], we, h])
                # fallback for links missing from the grid: distance at 15 km/h
                miss = (~link_ok) & (~last)
                if miss.any():
                    nxt = np.minimum(np.arange(n_rs) + 1, n_rs - 1)
                    tt[miss] = np.maximum(rs_sd[nxt][miss] - rs_sd[miss], 30) / (15 / 3.6)
                cs = np.concatenate([[0.0], np.cumsum(tt[:-1], dtype=np.float64)])
                base = cs[r_ptr[:-1]]
                c[we, h] = (cs - np.repeat(base, np.diff(r_ptr))).astype(np.float32)
        cum[name] = c
    # waits
    sv = con.execute(f"SELECT route_id, ord, hour, we, f_obs, cv, f_sched, w_emp FROM read_parquet('{service_path.as_posix()}')").fetchnumpy()
    pos = {(int(r), int(o_)): i for i, (r, o_) in enumerate(zip(so["route_id"], so["ord"]))}
    ii = np.array([pos.get((int(r), int(o_)), -1) for r, o_ in zip(sv["route_id"], sv["ord"])])
    keep = ii >= 0
    f_obs = np.zeros((2, 24, n_rs), np.float32); cv = np.full((2, 24, n_rs), 0.8, np.float32); f_sc = np.zeros((2, 24, n_rs), np.float32)
    f_obs[sv["we"][keep], sv["hour"][keep], ii[keep]] = sv["f_obs"][keep]
    cv[sv["we"][keep], sv["hour"][keep], ii[keep]] = np.clip(sv["cv"][keep], 0.0, 2.0)
    f_sc[sv["we"][keep], sv["hour"][keep], ii[keep]] = sv["f_sched"][keep]
    w_emp = np.full((2, 24, n_rs), np.nan, np.float32)
    we_ = np.asarray(sv["w_emp"].filled(np.nan) if hasattr(sv["w_emp"], "filled") else sv["w_emp"], np.float32)
    w_emp[sv["we"][keep], sv["hour"][keep], ii[keep]] = we_[keep]
    # passages are missed at some stops (off-shape GPS); a bus passing one stop passes them all, so use
    # the larger of the stop's own rate and 90% of the route's well-observed (p90) rate in that hour
    f_route = np.zeros_like(f_obs)
    for r in range(len(rids)):
        a, b = r_ptr[r], r_ptr[r + 1]
        f_route[:, :, a:b] = np.quantile(f_obs[:, :, a:b], 0.9, axis=2)[:, :, None]
    f_eff = np.maximum(f_obs, 0.9 * f_route)
    wait = {}
    with np.errstate(divide="ignore"):
        w = (1800.0 / f_eff) * (1 + cv ** 2)
        # observed waits (bunching and service gaps included) where measured, else the headway formula
        w = np.where(np.isfinite(w_emp), w_emp, w)
        wait["naadi"] = np.where(f_eff >= MIN_BPH, np.minimum(w, MAX_WAIT_S), np.inf).astype(np.float32)
        ws = 1800.0 / f_sc
        wait["timetable"] = np.where(f_sc >= MIN_BPH, np.minimum(ws, MAX_WAIT_S), np.inf).astype(np.float32)
    for wv in wait.values():
        wv[:, :, last] = np.inf  # cannot board at the final stop
    # route shapes for map display
    sh = con.execute(f"""
        SELECT DISTINCT CAST(t.route_id AS INTEGER) AS route_id, s.shape_pt_sequence::INTEGER AS q,
               s.shape_pt_lat::DOUBLE AS la, s.shape_pt_lon::DOUBLE AS lo, s.shape_dist_traveled::DOUBLE AS d
        FROM (SELECT DISTINCT route_id, shape_id FROM read_csv('{(GTFS / 'trips.txt').as_posix()}', all_varchar=true)) t
        JOIN read_csv('{(GTFS / 'shapes.txt').as_posix()}', all_varchar=true) s USING (shape_id)
        ORDER BY 1, 2""").fetchnumpy()
    rpos = {int(r): i for i, r in enumerate(rids)}
    shp_r = np.array([rpos.get(int(r), -1) for r in sh["route_id"]], np.int32)
    k = shp_r >= 0
    shp_r, shp_lat, shp_lon = shp_r[k], sh["la"][k].astype(np.float32), sh["lo"][k].astype(np.float32)
    # recompute distance along shape in metres (shape_dist_traveled units vary)
    seg = np.zeros(len(shp_r), np.float64)
    same = np.r_[False, shp_r[1:] == shp_r[:-1]]
    seg[1:] = np.where(same[1:], haversine(shp_lat[:-1], shp_lon[:-1], shp_lat[1:], shp_lon[1:]), 0)
    shp_d = np.zeros(len(shp_r), np.float64)
    starts = np.r_[0, np.flatnonzero(~same[1:]) + 1]
    cs = np.cumsum(seg)
    shp_d = (cs - np.repeat(cs[starts], np.diff(np.r_[starts, len(shp_r)]))).astype(np.float32)
    shp_ptr = np.searchsorted(shp_r, np.arange(len(rids) + 1)).astype(np.int32)
    meta = {"route_short": [rinfo.get(int(r), ("", "", "", ""))[0] for r in rids],
            "route_desc": [rinfo.get(int(r), ("", "", "", ""))[2] or "" for r in rids],
            "route_agency": [rinfo.get(int(r), ("", "", "", ""))[3] or "" for r in rids],
            "stop_names": names, "grid": grid_path.name, "service": service_path.name}
    out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out / "network.npz", stop_ids=stop_ids, lat=lat, lon=lon, route_ids=rids.astype(np.int32),
                        r_ptr=r_ptr, rs_stop=rs_stop, rs_sd=rs_sd, rs_ord=rs_ord, rs_route=rs_route, rs_link=rs_link,
                        sr_ptr=sr_ptr, sr_rs=sr_rs, fp_ptr=fp_ptr, fp_to=fp_to, fp_s=fp_s,
                        cum_naadi=cum["naadi"], cum_timetable=cum["timetable"], wait_naadi=wait["naadi"],
                        wait_timetable=wait["timetable"], cv=cv, f_eff=f_eff, f_sched=f_sc, w_emp=w_emp,
                        shp_ptr=shp_ptr, shp_lat=shp_lat, shp_lon=shp_lon, shp_d=shp_d)
    (out / "network_meta.json").write_text(json.dumps(meta, ensure_ascii=False))
    print(f"network: {len(stop_ids)} stops, {len(rids)} routes, {n_rs} route-stops, {len(fp_to)} walking links, "
          f"{len(shp_r)} shape points -> {out}")


class Network:
    def __init__(self, path: Path):
        z = np.load(path / "network.npz")
        for k in z.files:
            setattr(self, k, z[k])
        meta = json.loads((path / "network_meta.json").read_text(encoding="utf-8"))
        self.route_short, self.route_desc = meta["route_short"], meta["route_desc"]
        self.route_agency, self.stop_names = meta["route_agency"], meta["stop_names"]
        self.route_kind = np.asarray(getattr(self, "route_kind", meta.get("route_kind", ["bus"] * len(self.route_ids))))
        self.metro_meta = meta.get("metro", {})
        self.line_name = meta.get("line_name", [""] * len(self.route_ids))
        self.line_code = meta.get("line_code", [""] * len(self.route_ids))
        self.line_color = meta.get("line_color", [""] * len(self.route_ids))
        self.metro_route_id = meta.get("metro_route_id", [None] * len(self.route_ids))
        self.towards = meta.get("towards", [""] * len(self.route_ids))
        self.route_operator = meta.get("route_operator", [""] * len(self.route_ids))
        self.route_time_source = meta.get("route_time_source", [""] * len(self.route_ids))
        self.route_fare = meta.get("route_fare", [None] * len(self.route_ids))
        self.station_id = meta.get("station_id", [""] * len(self.stop_ids))
        self.station_name = meta.get("station_name", [""] * len(self.stop_ids))
        self.meta = meta
        self.n_stops, self.n_routes = len(self.stop_ids), len(self.route_ids)
        self.stop_index = {int(s): i for i, s in enumerate(self.stop_ids)}
        self.route_index = {int(r): i for i, r in enumerate(self.route_ids)}
        self._cell = (np.floor(self.lat / 0.01).astype(np.int64) * 100000 + np.floor(self.lon / 0.01).astype(np.int64))
        self._buckets: dict[int, np.ndarray] = {}
        for c in np.unique(self._cell):
            self._buckets[int(c)] = np.flatnonzero(self._cell == c)
        self._walk_target_index = self._apply_walking_lookup()

    def _apply_walking_lookup(self):
        """Replace static footpath times with OSM times when the artefact is available."""
        try:
            from .walk import load as load_walk
            lookup = load_walk()
        except (FileNotFoundError, OSError, ValueError):
            return {}
        coord_targets = {(round(float(la), 6), round(float(lo), 6)): str(tid)
                         for tid, la, lo in zip(lookup.target_ids, lookup.target_lat, lookup.target_lon)}
        keys = {}
        for i, sid in enumerate(self.stop_ids):
            numeric = str(int(sid))
            if numeric in lookup.target_index:
                keys[i] = numeric
                continue
            station = self.station_id[i] if i < len(self.station_id) else ""
            station_key = f"dmrc:{station}" if station else ""
            if station_key in lookup.target_index:
                keys[i] = station_key
                continue
            coord_key = coord_targets.get((round(float(self.lat[i]), 6), round(float(self.lon[i]), 6)))
            if coord_key is not None:
                keys[i] = coord_key
        for src in range(self.n_stops):
            for pos in range(int(self.fp_ptr[src]), int(self.fp_ptr[src + 1])):
                dst = int(self.fp_to[pos])
                a, b = keys.get(src), keys.get(dst)
                if a is None or b is None:
                    continue
                try:
                    self.fp_s[pos] = lookup.walk_time(a, b)
                except KeyError:
                    pass
        return keys

    def walk_target_index(self):
        return self._walk_target_index

    def nearby(self, lat: float, lon: float, radius_m: float):
        cy, cx = math.floor(lat / 0.01), math.floor(lon / 0.01)
        r = int(math.ceil(radius_m / 1000)) + 1
        cand = [self._buckets.get((cy + dy) * 100000 + cx + dx) for dy in range(-r, r + 1) for dx in range(-r, r + 1)]
        cand = [c for c in cand if c is not None]
        if not cand:
            return np.zeros(0, np.int32), np.zeros(0)
        cand = np.concatenate(cand)
        d = haversine(lat, lon, self.lat[cand], self.lon[cand])
        m = d <= radius_m
        o = np.argsort(d[m])
        return cand[m][o].astype(np.int32), d[m][o]
