"""Evaluate the exact bus-only options served by Naadi on archived October days."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
import time
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from naadi.linkgrid import LinkGrid  # noqa: E402
from naadi.live import upcoming  # noqa: E402
from naadi.network import Network  # noqa: E402
from naadi.nowcast import NowcastParams  # noqa: E402
from naadi.paths import MODEL, RESULTS, ROWS  # noqa: E402
from naadi.replay import DayPassages, LiveDay, positions_at, realise_legs  # noqa: E402
from naadi.router import Planner, _hw  # noqa: E402
from naadi.strategy import plan_options  # noqa: E402

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
SLOTS = ["07:30", "08:30", "10:00", "13:00", "16:00", "18:00", "20:00", "22:30"]


def weekend(ts):
    d = np.floor((np.asarray(ts) + 19800) / 86400).astype(np.int64)
    return (((d + 3) % 7) >= 5).astype(np.int64)


def _predicted_components(j):
    bus = [l for l in j.legs if l.kind == "bus"]
    wait_hist = sum(l.wait_s for l in bus if l.live_info.get("wait_source") != "live bus")
    wait_live = sum(l.wait_s for l in bus if l.live_info.get("wait_source") == "live bus")
    walk_s = sum(l.t1 - l.t0 for l in j.legs if l.kind == "walk")
    ride_s = sum(l.ride_s for l in bus)
    first = bus[0] if bus else None
    return walk_s, wait_hist, wait_live, ride_s, (first.wait_s if first else 0.0), (first.live_info.get("wait_source", "history") if first else "history")


def _actual_components(legs):
    if not legs:
        return None, None, None
    waits = [board - at_stop for at_stop, board, _ in legs]
    rides = [alight - board for _, board, alight in legs]
    return float(sum(waits)), float(sum(rides)), float(waits[0])


def _summary(rows):
    out = {}
    for name in sorted({r["planner"] for r in rows}):
        ok = [r for r in rows if r["planner"] == name and r["status"] == "ok"]
        e = np.array([r["pred_s"] - r["actual_s"] for r in ok], float)
        act = np.array([r["actual_s"] for r in ok], float)
        status = {}
        for r in rows:
            if r["planner"] == name:
                status[r["status"]] = status.get(r["status"], 0) + 1
        out[name] = {"n_ok": len(ok), "status": status,
                     "mae_min": float(np.mean(np.abs(e)) / 60) if len(e) else None,
                     "median_abs_min": float(np.median(np.abs(e)) / 60) if len(e) else None,
                     "mape_pct": float(100 * np.mean(np.abs(e) / act)) if len(e) else None,
                     "bias_min": float(np.mean(e) / 60) if len(e) else None,
                     "within_5min_pct": float(100 * np.mean(np.abs(e) <= 300)) if len(e) else None,
                     "within_10min_pct": float(100 * np.mean(np.abs(e) <= 600)) if len(e) else None,
                     "actual_median_min": float(np.median(act) / 60) if len(act) else None}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--network", required=True)
    ap.add_argument("--days", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--grid", default="grid_oct01_24")
    ap.add_argument("--tables", default="oct01_24")
    ap.add_argument("--limit-od", type=int, default=None)
    a = ap.parse_args()

    net = Network(MODEL / f"network_{a.network}")
    planners = {"naadi": Planner(net, "naadi"), "timetable": Planner(net, "timetable")}
    grid = LinkGrid(MODEL / f"{a.grid}.parquet", methods=("gbm",)) if a.live else None
    eta = RESULTS / "eta_oct.json"
    params = NowcastParams(**json.loads(eta.read_text())["nowcast"]) if a.live and eta.exists() else None
    od = list(csv.DictReader((ROOT / "validation" / "od_set.csv").open(encoding="utf-8")))
    if a.limit_od is not None:
        od = od[:a.limit_od]
    rows = []
    started = time.time()
    for day in a.days:
        passages = DayPassages(day)
        live_day = LiveDay(grid, a.tables, day, params) if a.live else None
        y, m, d = map(int, day.replace("_", "-").split("-"))
        for slot in SLOTS:
            hh, mm = map(int, slot.split(":"))
            t_dep = dt.datetime(y, m, d, hh, mm, tzinfo=IST).timestamp()
            mult = live_day.mult(t_dep) if live_day else None
            buses = positions_at(net, day, t_dep) if a.live else []
            first_wait = None
            if buses:
                cum_live = planners["naadi"].tables(t_dep, mult)[1]

                def first_wait(rs, t_at, *, _cum=cum_live, _buses=buses):
                    h0, h1, w = _hw(t_at)
                    cum_h = (1 - w) * _cum[h0] + w * _cum[h1]
                    return [x[1] for x in upcoming(net, _buses, t_dep, rs, t_at, cum_h)]
            for r in od:
                o = (float(r["o_lat"]), float(r["o_lon"]))
                dest = (float(r["d_lat"]), float(r["d_lon"]))
                runs = [("naadi", planners["naadi"], None, None), ("timetable", planners["timetable"], None, None)]
                if a.live:
                    runs += [("naadi_nowcast", planners["naadi"], mult, None), ("naadi_live", planners["naadi"], mult, first_wait)]
                for name, pl, mu, fw in runs:
                    js = plan_options(pl, o, dest, t_dep, n=1, live_mult=mu, calib=(1.0, 1.0), first_wait=fw,
                                      live_wait_factor=1.0, modes=("bus",))
                    row = {"day": day, "slot": slot, "od_id": r["od_id"], "kind": r["kind"], "planner": name,
                           "pred_s": None, "actual_s": None, "status": "no journey", "n_bus": 0, "walk_m": 0.0,
                           "walk_s": None, "wait_hist_s": None, "wait_live_s": None, "ride_s": None,
                           "wait1_pred_s": None, "wait1_source": "history", "act_wait_s": None, "act_ride_s": None,
                           "act_wait1_s": None, "routes": ""}
                    if js:
                        j = js[0]
                        actual, status, actual_legs = realise_legs(net, j, passages)
                        walk_s, wait_hist, wait_live, ride_s, wait1, wait1_source = _predicted_components(j)
                        act_wait, act_ride, act_wait1 = _actual_components(actual_legs) if status == "ok" else (None, None, None)
                        row.update(pred_s=float(j.total_s), actual_s=actual, status=status, n_bus=j.n_bus,
                                   walk_m=float(j.walk_m()), walk_s=float(walk_s), wait_hist_s=float(wait_hist),
                                   wait_live_s=float(wait_live), ride_s=float(ride_s), wait1_pred_s=float(wait1),
                                   wait1_source=wait1_source, act_wait_s=act_wait, act_ride_s=act_ride,
                                   act_wait1_s=act_wait1,
                                   routes="+".join(net.route_short[l.route] for l in j.legs if l.kind == "bus"))
                    rows.append(row)
        print(f"{day} done, {len(rows):,} rows, {time.time() - started:.0f}s", flush=True)

    ROWS.mkdir(parents=True, exist_ok=True)
    table = pa.table({k: [r[k] for r in rows] for k in rows[0]})
    tmp = ROWS / f"{a.out}.parquet.tmp"
    pq.write_table(table, tmp)
    tmp.replace(ROWS / f"{a.out}.parquet")
    summary = _summary(rows)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"{a.out}.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
