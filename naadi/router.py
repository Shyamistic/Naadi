"""Journey planner: frequency-based RAPTOR on observed service levels and model ride times.

Most Delhi bus trips do not follow the timetable (about 70% of live trips are unscheduled), so the router does
not pretend to know departure minutes. Boarding a route at a stop costs the expected wait for that route,
stop and hour; riding costs the model's predicted time at that hour; walking uses straight-line distance
x 1.35 at 1.25 m/s. Round k of RAPTOR finds the best arrival with at most k bus legs (k <= 3).
Alternatives come from re-running with the routes of earlier options banned.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from numba import njit

from .network import Network, haversine, walk_s

IST_S = 19800
K_MAX = 3
INF = 1e18
ACCESS_M = 1000.0
TRANSFER_PENALTY_S = 300.0  # ranking only: a change counts as 5 extra minutes


@njit(cache=True)
def _hw(t):
    x = ((t + IST_S) % 86400.0) / 3600.0 - 0.5
    h0 = math.floor(x)
    w = x - h0
    h0 = int(h0) % 24
    return h0, (h0 + 1) % 24, w


@njit(cache=True)
def _interp(a, b, w):
    return a if w <= 0.0 else (1.0 - w) * a + w * b


@njit(cache=True)
def _raptor(t_dep, cum, wait, r_ptr, rs_stop, sr_ptr, sr_rs, rs_route, fp_ptr, fp_to, fp_s,
            route_ok, acc_stop, acc_s, n_stops, k_max):
    tau = np.full((k_max + 1, n_stops), INF)
    kind = np.zeros((k_max + 1, n_stops), np.int8)       # 1 access, 2 ride, 3 walk, 4 carried from k-1
    pa = np.full((k_max + 1, n_stops), -1, np.int32)      # ride: board rs; walk: from stop
    pb = np.full((k_max + 1, n_stops), -1, np.int32)      # ride: alight rs
    ptb = np.zeros((k_max + 1, n_stops))                  # ride: time reached the boarding stop
    pw = np.zeros((k_max + 1, n_stops))                   # ride: expected wait
    marked = np.zeros(n_stops, np.bool_)
    for i in range(len(acc_stop)):
        s = acc_stop[i]
        t = t_dep + acc_s[i]
        if t < tau[0, s]:
            tau[0, s] = t
            kind[0, s] = 1
            pa[0, s] = i
            marked[s] = True
    n_routes = len(r_ptr) - 1
    for k in range(1, k_max + 1):
        for s in range(n_stops):
            if tau[k - 1, s] < INF:
                tau[k, s] = tau[k - 1, s]
                kind[k, s] = 4
        start = np.full(n_routes, 1 << 30, np.int64)
        any_marked = False
        for s in range(n_stops):
            if marked[s]:
                any_marked = True
                for j in range(sr_ptr[s], sr_ptr[s + 1]):
                    rs = sr_rs[j]
                    r = rs_route[rs]
                    if route_ok[r] and rs < start[r]:
                        start[r] = rs
        if not any_marked:
            break
        new_marked = np.zeros(n_stops, np.bool_)
        for r in range(n_routes):
            if start[r] == (1 << 30):
                continue
            b_rs = -1
            b_dep = 0.0
            b_h0 = 0
            b_h1 = 0
            b_w = 0.0
            b_tb = 0.0
            b_wait = 0.0
            for rs in range(start[r], r_ptr[r + 1]):
                s = rs_stop[rs]
                arr = INF
                if b_rs >= 0:
                    c_here = (1 - b_w) * cum[b_h0, rs] + b_w * cum[b_h1, rs]
                    c_b = (1 - b_w) * cum[b_h0, b_rs] + b_w * cum[b_h1, b_rs]
                    arr = b_dep + c_here - c_b
                    if arr < tau[k, s]:
                        tau[k, s] = arr
                        kind[k, s] = 2
                        pa[k, s] = b_rs
                        pb[k, s] = rs
                        ptb[k, s] = b_tb
                        pw[k, s] = b_wait
                        new_marked[s] = True
                tb = tau[k - 1, s]
                if tb < INF:
                    h0, h1, w = _hw(tb)
                    wt = _interp(wait[h0, rs], wait[h1, rs], w)
                    if wt < 1e8:
                        dep = tb + wt
                        if b_rs < 0 or dep < arr:
                            b_rs, b_dep, b_h0, b_h1, b_w, b_tb, b_wait = rs, dep, h0, h1, w, tb, wt
        # transfer walks from stops improved this round
        for s in range(n_stops):
            if new_marked[s] and kind[k, s] == 2:
                for j in range(fp_ptr[s], fp_ptr[s + 1]):
                    s2 = fp_to[j]
                    t2 = tau[k, s] + fp_s[j]
                    if t2 < tau[k, s2]:
                        tau[k, s2] = t2
                        kind[k, s2] = 3
                        pa[k, s2] = s
                        new_marked[s2] = True
        marked = new_marked
    return tau, kind, pa, pb, ptb, pw


@njit(cache=True)
def _cum_live(cum, rs_link, r_ptr, mult):
    """Ride-time table with each link's time multiplied by mult[link] (live nowcast)."""
    out = np.empty_like(cum)
    for h in range(cum.shape[0]):
        for r in range(len(r_ptr) - 1):
            a = r_ptr[r]
            out[h, a] = 0.0
            for rs in range(a + 1, r_ptr[r + 1]):
                tt = cum[h, rs] - cum[h, rs - 1]
                li = rs_link[rs - 1]
                m = mult[h, li] if li >= 0 else 1.0
                out[h, rs] = out[h, rs - 1] + tt * m
    return out


@dataclass
class Leg:
    kind: str                 # "walk", "bus" or "metro"
    t0: float                 # leg start (unix s)
    t1: float                 # leg end
    from_stop: int = -1       # stop index (network) or -1 for the origin point
    to_stop: int = -1         # stop index or -1 for the destination point
    route: int = -1           # route index for bus legs
    board_rs: int = -1
    alight_rs: int = -1
    wait_s: float = 0.0
    ride_s: float = 0.0
    walk_m: float = 0.0
    alternatives: list = field(default_factory=list)
    live_info: dict = field(default_factory=dict)

@dataclass
class Journey:
    legs: list = field(default_factory=list)
    depart: float = 0.0
    arrive: float = 0.0

    @property
    def total_s(self):
        return self.arrive - self.depart

    @property
    def n_transit(self):
        return sum(1 for l in self.legs if l.kind in ("bus", "metro", "rail", "shared_auto"))

    @property
    def n_bus(self):
        return sum(1 for l in self.legs if l.kind == "bus")

    def signature(self):
        return tuple((l.route, l.board_rs, l.alight_rs) for l in self.legs if l.kind in ("bus", "metro", "rail", "shared_auto"))

    def walk_m(self):
        return sum(l.walk_m for l in self.legs if l.kind == "walk")


class Planner:
    def __init__(self, net: Network, variant: str = "naadi"):
        self.net = net
        self.variant = variant
        self.cum = getattr(net, f"cum_{variant}")      # (2, 24, n_rs)
        self.wait = getattr(net, f"wait_{variant}")
        self.route_kind = np.asarray(getattr(net, "route_kind", ["bus"] * net.n_routes))
        self.metro_routes = np.flatnonzero(np.asarray(getattr(net, "route_mode", self.route_kind == "metro")) == 1).tolist()

    def tables(self, t: float, live_mult=None):
        we = int(((math.floor((t + IST_S) / 86400) + 3) % 7) >= 5)
        cum = self.cum[we]
        if live_mult is not None:
            cum = _cum_live(cum, self.net.rs_link, self.net.r_ptr, live_mult)
        return we, cum, self.wait[we]

    def _access(self, lat, lon, radius=ACCESS_M, egress=False):
        try:
            from .walk import WALK_MS, access as walk_access
            candidates = walk_access(float(lat), float(lon))
            target_index = self.net.walk_target_index()
            rows = []
            extra_s = getattr(self.net, "stop_exit_s" if egress else "stop_entry_s", np.zeros(self.net.n_stops, np.float32))
            for target_id, seconds in candidates:
                stop = target_index.get(str(target_id))
                if stop is None:
                    continue
                distance = float(seconds) * WALK_MS
                if distance <= radius * 1.35:
                    total = float(seconds) + float(extra_s[stop])
                    rows.append((int(stop), total, distance))
            if rows:
                best = {}
                for stop, seconds, distance in rows:
                    if stop not in best or seconds < best[stop][0]:
                        best[stop] = (seconds, distance)
                st = np.asarray(sorted(best), dtype=np.int32)
                acc_s = np.asarray([best[int(s)][0] for s in st], dtype=np.float64)
                acc_d = np.asarray([best[int(s)][1] for s in st], dtype=np.float64)
                order = np.argsort(acc_s)
                return st[order], acc_s[order], acc_d[order]
        except (FileNotFoundError, OSError, ValueError):
            pass
        st, d = self.net.nearby(lat, lon, radius)
        extra = getattr(self.net, "stop_exit_s" if egress else "stop_entry_s", np.zeros(self.net.n_stops, np.float32))[st]
        return st, walk_s(d) + extra, d

    def run(self, o, d, t_dep, banned=(), live_mult=None, cum=None, modes=("bus",)):
        n = self.net
        we, cum_t, wait = self.tables(t_dep, live_mult)
        if cum is not None:
            cum_t = cum
        acc_st, acc_s, acc_d = self._access(*o)
        eg_st, eg_s, eg_d = self._access(d[0], d[1], egress=True)
        if len(acc_st) == 0 or len(eg_st) == 0:
            return [], (acc_st, eg_st)
        ok = np.ones(n.n_routes, np.bool_)
        for r in range(n.n_routes):
            if self.route_kind[r] not in modes:
                ok[r] = False
        tau, kind, pa, pb, ptb, pw = _raptor(float(t_dep), cum_t, wait, n.r_ptr, n.rs_stop, n.sr_ptr, n.sr_rs,
                                             n.rs_route, n.fp_ptr, n.fp_to, n.fp_s, ok, acc_st,
                                             acc_s.astype(np.float64), n.n_stops, K_MAX)
        egress = {int(s): (float(w), float(dm)) for s, w, dm in zip(eg_st, eg_s, eg_d)}
        out = []
        for k in range(1, K_MAX + 1):
            best, bs = INF, -1
            for s, (w, _) in egress.items():
                if kind[k, s] != 0 and tau[k, s] + w < best:
                    best, bs = tau[k, s] + w, s
            if bs < 0:
                continue
            j = self._reconstruct(k, bs, tau, kind, pa, pb, ptb, pw, t_dep, acc_st, acc_s, acc_d, cum_t)
            if j is None or j.n_transit == 0:
                continue
            w, dm = egress[bs]
            j.legs.append(Leg("walk", tau[k, bs], tau[k, bs] + w, from_stop=bs, walk_m=dm))
            j.depart, j.arrive = t_dep, tau[k, bs] + w
            out.append(j)
        return out, (acc_st, eg_st)

    def _reconstruct(self, k, s, tau, kind, pa, pb, ptb, pw, t_dep, acc_st, acc_s, acc_d, cum):
        legs = []
        guard = 0
        while guard < 20:
            guard += 1
            kd = kind[k, s]
            if kd == 4:
                k -= 1
                continue
            if kd == 1:
                i = pa[k, s]
                legs.append(Leg("walk", t_dep, t_dep + acc_s[i], to_stop=s, walk_m=float(acc_d[i])))
                break
            if kd == 3:
                s0 = pa[k, s]
                seconds = float(tau[k, s] - tau[k, s0])
                dm = seconds * 1.25
                legs.append(Leg("walk", tau[k, s0], tau[k, s], from_stop=s0, to_stop=s, walk_m=dm))
                s = s0
                continue
            if kd == 2:
                b, a = pa[k, s], pb[k, s]
                r = int(self.net.rs_route[b])
                sb = int(self.net.rs_stop[b])
                tb, wt = ptb[k, s], pw[k, s]
                legs.append(Leg(self.route_kind[r], tb, tau[k, s], from_stop=sb, to_stop=s, route=r, board_rs=b, alight_rs=a,
                                wait_s=wt, ride_s=tau[k, s] - tb - wt))
                s = sb
                k -= 1
                continue
            return None
        legs.reverse()
        return Journey(legs=legs)

    def plan(self, o, d, t_dep, n_options=4, live_mult=None, modes=("bus",)):
        """Up to n_options distinct journeys, best first by generalised time."""
        found, seen, banned = [], set(), []
        for _ in range(4):
            js, _ = self.run(o, d, t_dep, banned=banned, live_mult=live_mult, modes=modes)
            for j in js:
                sig = j.signature()
                if sig and sig not in seen:
                    seen.add(sig)
                    found.append(j)
            if not js:
                break
            first = min(js, key=lambda j: j.total_s + TRANSFER_PENALTY_S * (j.n_transit - 1))
            banned += [l.route for l in first.legs if l.kind in ("bus", "metro")]
        if not found:
            return []
        found.sort(key=lambda j: j.total_s + TRANSFER_PENALTY_S * (j.n_transit - 1))
        best = found[0].total_s
        keep = [j for j in found if j.total_s <= 1.6 * best + 900]
        return keep[:n_options]

    def evaluate(self, j: Journey, t_dep: float, live_mult=None):
        """Expected door-to-door time of the same itinerary if started at t_dep."""
        t = t_dep
        we, cum, wait = self.tables(t_dep, live_mult)
        for l in j.legs:
            if l.kind == "walk":
                t += l.t1 - l.t0
                continue
            h0, h1, w = _hw(t)
            wt = _interp(wait[h0, l.board_rs], wait[h1, l.board_rs], w)
            if not np.isfinite(wt) or wt > 1e8:
                return None
            t += wt
            h0, h1, w = _hw(t)
            c = lambda rs: (1 - w) * cum[h0, rs] + w * cum[h1, rs]
            t += c(l.alight_rs) - c(l.board_rs)
        return t - t_dep
