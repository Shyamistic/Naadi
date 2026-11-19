"""Replay ground truth: what would have happened if a rider followed an itinerary on a recorded day.

The rider walks to the boarding stop, boards the FIRST bus of any route in the leg's set that actually
passed that stop afterwards (from GPS stop passages), rides it to its alighting stop, and so on. Walking
time is taken as planned (it is not observed).
GPS gaps: a bus that passed the boarding stop but has no passage exactly at the alighting stop is followed
through its nearest passages within 3 stops either side, interpolated by stop count. A leg is "no data" when
the boarding stop's passages that day are under 60% of the route's typical stop (poor GPS capture there).
"""
from __future__ import annotations

import duckdb
import numpy as np

from .paths import WORK
NEAR = 3


class DayPassages:
    def __init__(self, day: str):
        d = duckdb.sql(f"SELECT k, route_id, ord, t FROM read_parquet('{(WORK / 'passages' / f'day={day}.parquet').as_posix()}')").fetchnumpy()
        _, kid = np.unique(d["k"], return_inverse=True)
        r, o, t = d["route_id"].astype(np.int64), d["ord"].astype(np.int64), d["t"].astype(np.float64)
        kid = kid.astype(np.int64)
        key = r * 1000 + o
        s = np.lexsort((t, key))
        self.sk, self.st, self.skid = key[s], t[s], kid[s]
        bkey = (kid << 24) | (r << 8) | o
        s2 = np.argsort(bkey)
        self.bk, self.bt = bkey[s2], t[s2]
        uk, cnt = np.unique(key, return_counts=True)
        self.count = dict(zip(uk.tolist(), cnt.tolist()))
        ur = uk // 1000
        self.route_med = {int(rr): float(np.median(cnt[ur == rr])) for rr in np.unique(ur)}

    def captured(self, route_id: int, ord_: int) -> bool:
        med = self.route_med.get(route_id)
        return med is not None and self.count.get(route_id * 1000 + ord_, 0) >= 0.6 * med

    def _bus_time(self, kid: int, route_id: int, ord_a: int, after: float):
        base = (kid << 24) | (route_id << 8)
        j = np.searchsorted(self.bk, base | ord_a)
        if j < len(self.bk) and self.bk[j] == (base | ord_a):
            return float(self.bt[j]) if self.bt[j] > after else None
        # bracketing passages of the same bus around ord_a, within NEAR stops
        lo_i, hi_i = j - 1, j
        if 0 <= lo_i and hi_i < len(self.bk) and (self.bk[lo_i] >> 8) == (base >> 8) and (self.bk[hi_i] >> 8) == (base >> 8):
            o_lo, o_hi = int(self.bk[lo_i] & 255), int(self.bk[hi_i] & 255)
            if ord_a - o_lo <= NEAR and o_hi - ord_a <= NEAR and self.bt[hi_i] > self.bt[lo_i]:
                tt = self.bt[lo_i] + (ord_a - o_lo) / (o_hi - o_lo) * (self.bt[hi_i] - self.bt[lo_i])
                return float(tt) if tt > after else None
        return None

    def next_bus(self, route_id: int, ord_b: int, ord_a: int, t_arrive: float, tries: int = 6):
        """First bus of the route passing ord_b at or after t_arrive that also reaches ord_a: (t_board, t_alight)."""
        key = route_id * 1000 + ord_b
        lo = np.searchsorted(self.sk, key, side="left")
        hi = np.searchsorted(self.sk, key, side="right")
        i = lo + np.searchsorted(self.st[lo:hi], t_arrive, side="left")
        for _ in range(tries):
            if i >= hi:
                return None
            ta = self._bus_time(int(self.skid[i]), route_id, ord_a, float(self.st[i]))
            if ta is not None:
                return float(self.st[i]), ta
            i += 1
        return None


def realise(net, j, day: DayPassages):
    """Actual door-to-door seconds of journey j on this day, or (None, reason)."""
    t = j.depart
    for l in j.legs:
        if l.kind == "walk":
            t += l.t1 - l.t0
            continue
        if l.kind == "metro":
            return None, "metro leg"
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
                best = nb
        if not any_captured:
            return None, "boarding stop poorly captured"
        if best is None:
            return None, "no bus observed"
        if best[0] - t > 3 * 3600:
            return None, "no bus within 3 h"
        t = best[1]
    return t - j.depart, "ok"
