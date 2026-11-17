"""Common lines: at a stop, a rider takes whichever useful bus comes first.

For a bus leg from stop B to stop A, every route that serves B and later reaches A (or a stop within a short
walk of A) is a candidate. Following the optimal-strategy rule for transit (Chriqui & Robillard 1975;
Spiess & Florian 1989), candidates are added in order of ride time while a candidate's ride is shorter than
the expected wait plus ride of the set chosen so far. Each route's rate is 1 / its expected wait at that stop
and hour (measured waits for Naadi; regular scheduled headways for the timetable planner):
    E[wait] = 1 / sum(rate_i)                 (independent arrivals)
    E[ride] = sum(rate_i * ride_i) / sum(rate_i)
"""
from __future__ import annotations

import math
from dataclasses import replace

import numpy as np

from .router import Journey, Planner, _hw

ALIGHT_WALK_M = 300.0


def _alight_targets(net, stop: int):
    """The alight stop itself plus stops within walking range, with walking seconds."""
    out = {int(stop): 0.0}
    for j in range(net.fp_ptr[stop], net.fp_ptr[stop + 1]):
        if net.fp_s[j] <= ALIGHT_WALK_M * 1.35 / 1.25:
            out[int(net.fp_to[j])] = float(net.fp_s[j])
    return out


def leg_options(pl: Planner, board_stop: int, alight_stop: int, t: float):
    """Candidates (route, board_rs, alight_rs, rate, ride_s) for a leg starting at time t."""
    net = pl.net
    we, cum, wait = pl.tables(t)
    h0, h1, w = _hw(t)
    targets = _alight_targets(net, alight_stop)
    cands = []
    for j in range(net.sr_ptr[board_stop], net.sr_ptr[board_stop + 1]):
        b = int(net.sr_rs[j])
        r = int(net.rs_route[b])
        end = int(net.r_ptr[r + 1])
        best = None
        for a in range(b + 1, end):
            s = int(net.rs_stop[a])
            if s in targets:
                ride = (1 - w) * (cum[h0, a] - cum[h0, b]) + w * (cum[h1, a] - cum[h1, b]) + targets[s]
                best = (a, ride)
                break
        if best is None:
            continue
        ew = (1 - w) * wait[h0, b] + w * wait[h1, b]
        if not np.isfinite(ew) or ew > 1e8:
            continue
        cands.append((r, b, best[0], 1.0 / max(float(ew), 30.0), float(best[1])))
    return cands


def attractive_set(cands):
    cands = sorted(cands, key=lambda c: c[4])
    chosen, R, RR = [], 0.0, 0.0
    for c in cands:
        if chosen and c[4] >= 1.0 / R + RR / R:
            break
        chosen.append(c)
        R += c[3]
        RR += c[3] * c[4]
    if not chosen:
        return [], math.inf, math.inf
    return chosen, min(1.0 / R, 3600.0), RR / R


def refine(pl: Planner, j: Journey, t_dep: float) -> Journey | None:
    """Re-time a journey with common lines at every boarding; returns None if a leg has no service."""
    t = t_dep
    legs = []
    for l in j.legs:
        if l.kind == "walk":
            d = l.t1 - l.t0
            legs.append(replace(l, t0=t, t1=t + d))
            t += d
            continue
        chosen, ew, er = attractive_set(leg_options(pl, l.from_stop, l.to_stop, t))
        if not chosen:
            return None
        nl = replace(l, t0=t, t1=t + ew + er, wait_s=ew, ride_s=er)
        nl.alternatives = [(c[0], c[1], c[2], c[3]) for c in chosen]
        legs.append(nl)
        t += ew + er
    return Journey(legs=legs, depart=t_dep, arrive=t)


def best_journey(pl: Planner, o, d, t_dep):
    js, _ = pl.run(o, d, t_dep)
    best = None
    for j in js:
        r = refine(pl, j, t_dep)
        if r is not None and (best is None or r.total_s + 300 * (r.n_bus - 1) < best.total_s + 300 * (best.n_bus - 1)):
            best = r
    return best
