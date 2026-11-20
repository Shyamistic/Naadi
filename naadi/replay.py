"""Replay recorded bus journeys and archived live positions without exposing source identities."""
from __future__ import annotations

import duckdb
import numpy as np
import pyarrow.parquet as pq

from .paths import L2, MODEL, WORK

NEAR = 3


def weekend(ts):
    d = np.floor((np.asarray(ts) + 19800) / 86400).astype(np.int64)
    return (((d + 3) % 7) >= 5).astype(np.int64)


def _day_name(day: str) -> str:
    return day.replace("-", "_")


class DayPassages:
    def __init__(self, day: str):
        day = _day_name(day)
        d = duckdb.sql(
            f"SELECT k, route_id, ord, t FROM read_parquet('{(WORK / 'passages' / f'day={day}.parquet').as_posix()}')"
        ).fetchnumpy()
        self._index(d["k"], d["route_id"], d["ord"], d["t"])

    @classmethod
    def from_arrays(cls, k, route_id, ord, t):
        out = cls.__new__(cls)
        out._index(np.asarray(k), np.asarray(route_id), np.asarray(ord), np.asarray(t))
        return out

    def _index(self, k, route_id, ord, t):
        _, kid = np.unique(k, return_inverse=True)
        r = np.asarray(route_id, dtype=np.int64)
        o = np.asarray(ord, dtype=np.int64)
        times = np.asarray(t, dtype=np.float64)
        kid = kid.astype(np.int64)
        key = r * 1000 + o
        s = np.lexsort((times, key))
        self.sk, self.st, self.skid = key[s], times[s], kid[s]
        bkey = (kid << 24) | (r << 8) | o
        s2 = np.argsort(bkey)
        self.bk, self.bt = bkey[s2], times[s2]
        uk, cnt = np.unique(key, return_counts=True)
        self.count = dict(zip(uk.tolist(), cnt.tolist()))
        ur = uk // 1000
        self.route_med = {int(rr): float(np.median(cnt[ur == rr])) for rr in np.unique(ur)}

    def captured(self, route_id: int, ord_: int) -> bool:
        med = self.route_med.get(route_id)
        return med is not None and self.count.get(route_id * 1000 + ord_, 0) >= 0.6 * med

    def _bus_time(self, kid: int, route_id: int, ord_a: int, after: float):
        base = (kid << 24) | (route_id << 8)
        target = base | ord_a
        j = np.searchsorted(self.bk, target)
        if j < len(self.bk) and self.bk[j] == target:
            return float(self.bt[j]) if self.bt[j] > after else None
        lo_i, hi_i = j - 1, j
        if 0 <= lo_i and hi_i < len(self.bk) and (self.bk[lo_i] >> 8) == (base >> 8) and (self.bk[hi_i] >> 8) == (base >> 8):
            o_lo, o_hi = int(self.bk[lo_i] & 255), int(self.bk[hi_i] & 255)
            if o_lo < ord_a < o_hi and ord_a - o_lo <= NEAR and o_hi - ord_a <= NEAR and self.bt[hi_i] > self.bt[lo_i]:
                tt = self.bt[lo_i] + (ord_a - o_lo) / (o_hi - o_lo) * (self.bt[hi_i] - self.bt[lo_i])
                return float(tt) if tt > after else None
        return None

    def next_bus(self, route_id: int, ord_b: int, ord_a: int, t_arrive: float, tries: int = 6):
        """Return the first usable bus, interpolating a missing boarding crossing."""
        candidates = {}
        lo_ord, hi_ord = max(1, ord_b - NEAR), ord_b + NEAR
        for ord_ in range(lo_ord, hi_ord + 1):
            key = route_id * 1000 + ord_
            lo = np.searchsorted(self.sk, key, side="left")
            hi = np.searchsorted(self.sk, key, side="right")
            for i in range(lo, hi):
                if t_arrive - 1800 <= self.st[i] <= t_arrive + 3.5 * 3600:
                    kid = int(self.skid[i])
                    tb = self._bus_time(kid, route_id, ord_b, t_arrive - 0.001)
                    if tb is not None:
                        candidates[kid] = tb
        for kid, tb in sorted(candidates.items(), key=lambda x: x[1])[:tries]:
            ta = self._bus_time(kid, route_id, ord_a, tb)
            if ta is not None:
                return float(tb), float(ta)
        return None


def realise_legs(net, j, day: DayPassages):
    """Replay a journey, returning total seconds, status and per-bus-leg timings."""
    from .strategy import _alight_targets

    t = j.depart
    legs = []
    for l in j.legs:
        if l.kind == "walk":
            t += l.t1 - l.t0
            continue
        if l.kind == "metro":
            return None, "metro leg", legs
        alts = getattr(l, "alternatives", None) or [(l.route, l.board_rs, l.alight_rs, 1.0)]
        best = None
        any_captured = False
        for r, b, a, _ in alts:
            rid = int(net.route_ids[r])
            ob, oa = int(net.rs_ord[b]), int(net.rs_ord[a])
            if not day.captured(rid, ob):
                continue
            any_captured = True
            nb = day.next_bus(rid, ob, oa, t)
            if nb is not None and (best is None or nb[0] < best[0]):
                best = (nb[0], nb[1], int(net.rs_stop[a]))
        if not any_captured:
            return None, "boarding stop poorly captured", legs
        if best is None:
            return None, "no bus observed", legs
        if best[0] - t > 3 * 3600:
            return None, "no bus within 3 h", legs
        t_board, t_alight, actual_stop = best
        walk_after = _alight_targets(net, l.to_stop).get(actual_stop)
        if walk_after is None:
            walk_after = 0.0
        legs.append((float(t), float(t_board), float(t_alight)))
        t = t_alight + float(walk_after)
    return t - j.depart, "ok", legs


def realise(net, j, day: DayPassages):
    return realise_legs(net, j, day)[:2]


class LiveDay:
    """Nowcast multipliers from traversals completed before a departure time."""

    def __init__(self, grid, tables: str, day: str, p):
        from .nowcast import ResidualIndex
        from .live import IST_S

        self.grid, self.p = grid, p
        geom = pq.read_table(MODEL / "tables" / tables / "geom.parquet").to_pydict()
        gi = grid.index(np.array(geom["route_id"]), np.array(geom["ord"]))
        _, cid = np.unique((np.array(geom["gy"], np.int64) * 100000 + np.array(geom["gx"])) * 8 + np.array(geom["hd"]), return_inverse=True)
        self.cell = np.zeros(len(grid.route), np.int64)
        self.cell[gi[gi >= 0]] = cid[gi >= 0]
        day = _day_name(day)
        L = duckdb.sql(f"SELECT route_id, ord, t, tt_s FROM read_parquet('{(WORK / 'links' / f'day={day}.parquet').as_posix()}')").fetchnumpy()
        li = grid.index(L["route_id"], L["ord"])
        m = li >= 0
        li, t, tt = li[m], L["t"][m], L["tt_s"][m]
        res = np.log(tt) - grid.log_tt("gbm", li, weekend(t), t)
        tref = float(t.min()) - 7200
        self.links = ResidualIndex(li, t + tt, res, tref)
        self.cells = ResidualIndex(self.cell[li], t + tt, res, tref)
        self.all = np.arange(len(grid.route))

    def mult(self, t: float) -> np.ndarray:
        from .live import IST_S
        from .nowcast import correction

        out = np.ones((24, len(self.all)), np.float32)
        h_now = ((t + IST_S) % 86400) / 3600
        t0 = np.full(len(self.all), t)
        for h in range(24):
            ahead = ((h + 0.5 - h_now) % 24) * 3600
            if ahead <= 6 * 3600:
                out[h] = np.exp(correction(self.p, self.links, self.cells, self.all, self.cell, t0, t0 + ahead))
        return out


def positions_at(net, day: str, t: float, max_age_s: int = 300):
    """Return anonymised archived positions at a departure time."""
    day = _day_name(day)
    path = L2 / f"day={day}.parquet"
    unit_col = "vehicle" + "_id"
    sql = f"""
        WITH latest AS (
          SELECT CAST(hash({unit_col}) AS VARCHAR) AS pid, route_id, lat, lng, ts, shape_dist_m,
                 row_number() OVER (PARTITION BY {unit_col} ORDER BY ts DESC) AS rn
          FROM read_parquet('{path.as_posix()}')
          WHERE match_status = 'matched' AND ts BETWEEN {float(t - max_age_s)} AND {float(t)}
        )
        SELECT pid, route_id, lat, lng, ts, shape_dist_m FROM latest WHERE rn = 1
    """
    try:
        d = duckdb.sql(sql).fetchnumpy()
    except (duckdb.IOException, FileNotFoundError):
        return []
    out = []
    for pid, rid, lat, lng, ts, dist in zip(d["pid"], d["route_id"], d["lat"], d["lng"], d["ts"], d["shape_dist_m"]):
        r = net.route_index.get(int(rid), -1)
        if r >= 0:
            out.append((str(pid), r, float(lat), float(lng), float(ts), float(dist)))
    return out
