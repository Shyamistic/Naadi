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
import re
from dataclasses import replace

import numpy as np

from .router import Journey, Planner, TRANSFER_PENALTY_S, _hw, _interp

ALIGHT_WALK_M = 300.0


def _alight_targets(net, stop: int):
    """The alight stop itself plus stops within walking range, with walking seconds."""
    out = {int(stop): 0.0}
    for j in range(net.fp_ptr[stop], net.fp_ptr[stop + 1]):
        if net.fp_s[j] <= ALIGHT_WALK_M * 1.35 / 1.25:
            out[int(net.fp_to[j])] = float(net.fp_s[j])
    return out


def leg_options(pl: Planner, board_stop: int, alight_stop: int, t: float, cum=None):
    """Candidates (route, board_rs, alight_rs, rate, ride_s) for a leg starting at time t."""
    net = pl.net
    we, table_cum, wait = pl.tables(t)
    cum = table_cum if cum is None else cum
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
        ew = _interp(wait[h0, b], wait[h1, b], w)
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


def refine(pl: Planner, j: Journey, t_dep: float, calib=None, cum=None) -> Journey | None:
    """Re-time a journey with common lines at every boarding; returns None if a leg has no service.
    calib = (wait factor, ride factor) fitted on replayed journeys (scripts/build_summary.py); default pl.calib."""
    cw, cr = calib if calib is not None else getattr(pl, "calib", (1.0, 1.0))
    t = t_dep
    legs = []
    for l in j.legs:
        if l.kind == "walk":
            d = l.t1 - l.t0
            legs.append(replace(l, t0=t, t1=t + d))
            t += d
            continue
        if l.kind == "metro":
            nl = replace(l, t0=t, t1=t + l.wait_s + l.ride_s)
            legs.append(nl)
            t = nl.t1
            continue
        chosen, ew, er = attractive_set(leg_options(pl, l.from_stop, l.to_stop, t, cum=cum))
        if not chosen:
            return None
        ew, er = ew * cw, er * cr
        nl = replace(l, t0=t, t1=t + ew + er, wait_s=ew, ride_s=er)
        nl.alternatives = [(c[0], c[1], c[2], c[3]) for c in chosen]
        legs.append(nl)
        t += ew + er
    return Journey(legs=legs, depart=t_dep, arrive=t)


def route_label(short: str) -> str:
    return re.sub(r"(UP|DOWN)\d*$", "", short).strip()


def with_first_wait(j: Journey, t_dep: float, next_arrivals, factor=1.0) -> Journey:
    """Replace the first transit wait with arrivals from a supplied live-bus lookup."""
    t = t_dep
    if next((l for l in j.legs if l.kind != "walk"), None) is not None:
        if next(l for l in j.legs if l.kind != "walk").kind == "metro":
            return j
    for i, l in enumerate(j.legs):
        if l.kind == "walk":
            d = l.t1 - l.t0
            l.t0, l.t1 = t, t + d
            t += d
            continue
        if l.kind == "metro":
            t += l.t1 - l.t0
            continue
        rs = [a[1] for a in getattr(l, "alternatives", [(l.route, l.board_rs, l.alight_rs, 1.0)])]
        arrivals = sorted(x for x in next_arrivals(rs, t) if x >= t)
        info = {"live": True, "next": [round((x - t) / 60, 1) for x in arrivals[:3]]}
        if arrivals:
            new_wait = factor * (arrivals[0] - t)
            shift = new_wait - l.wait_s
            l.wait_s = new_wait
            l.t0 = t
            l.t1 += shift
            for later in j.legs[i + 1:]:
                later.t0 += shift
                later.t1 += shift
            j.arrive += shift
            info["wait_source"] = "live bus"
        l.live_info = info
        for later in j.legs[i + 1:]:
            if later.kind != "walk":
                later.live_info = {"live": True}
        break
    return j


def option_signature(net, j: Journey):
    out = []
    for l in j.legs:
        if l.kind == "walk":
            continue
        alts = getattr(l, "alternatives", None) or [(l.route,)]
        out.append((net.stop_names[l.from_stop], frozenset(route_label(net.route_short[a[0]]) for a in alts)))
    return tuple(out)


def plan_options(pl: Planner, o, d, t_dep, n=3, live_mult=None, calib=None, first_wait=None,
                 live_wait_factor=1.0, n_candidates=8, modes=("bus",), require_metro=False):
    """Rank with uncalibrated expected times, then show calibrated times."""
    js = pl.plan(o, d, t_dep, n_options=n_candidates, live_mult=live_mult, modes=modes)
    cum = pl.tables(t_dep, live_mult)[1] if live_mult is not None else None
    ranked = []
    for j in js:
        if require_metro and not any(l.kind == "metro" for l in j.legs):
            continue
        r = refine(pl, j, t_dep, calib=(1.0, 1.0), cum=cum)
        if r is None:
            continue
        if first_wait is not None:
            r = with_first_wait(r, t_dep, first_wait, 1.0)
        ranked.append(r)
    ranked.sort(key=lambda j: j.total_s + TRANSFER_PENALTY_S * (j.n_transit - 1))
    chosen, seen = [], set()
    for j in ranked:
        sig = option_signature(pl.net, j)
        if sig not in seen:
            seen.add(sig)
            chosen.append(j)
        if len(chosen) >= n:
            break
    if calib == (1.0, 1.0) and live_wait_factor == 1.0:
        return chosen
    out = []
    for j in chosen:
        r = refine(pl, j, t_dep, calib=calib, cum=cum)
        if r is None:
            continue
        if first_wait is not None:
            r = with_first_wait(r, t_dep, first_wait, live_wait_factor)
        out.append(r)
    return out


def best_journey(pl: Planner, o, d, t_dep):
    js, _ = pl.run(o, d, t_dep)
    best = None
    for j in js:
        r = refine(pl, j, t_dep)
        if r is not None and (best is None or r.total_s + 300 * (r.n_bus - 1) < best.total_s + 300 * (best.n_bus - 1)):
            best = r
    return best
