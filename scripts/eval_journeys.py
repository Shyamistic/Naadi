"""Door-to-door journey validation by replay on recorded days.

For every OD pair x departure slot x test day, each planner proposes its best journey and its predicted
door-to-door time; the replay (naadi/replay.py) gives the actual time a rider following that journey
would have had, using the buses that really ran that day.
Planners (one router, one network built from history before the test days):
  naadi       model ride times, measured waits, common lines
  naadi_live  the same plus the live nowcast from traversals completed before the departure time
  timetable   GTFS times and scheduled regular headways
Usage:
  python scripts/eval_journeys.py --network eval_oct --days 2026_10_26 ... --out journeys_oct [--live]
Writes validation/results/<out>.parquet (one row per case and planner, no vehicle ids) and <out>.json.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
import time
from pathlib import Path

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from naadi.linkgrid import LinkGrid  # noqa: E402
from naadi.network import MODEL, Network  # noqa: E402
from naadi.nowcast import NowcastParams, ResidualIndex, correction  # noqa: E402
from naadi.replay import DayPassages, realise  # noqa: E402
from naadi.router import Planner  # noqa: E402
from naadi.strategy import refine  # noqa: E402

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
SLOTS = ["07:30", "08:30", "10:00", "13:00", "16:00", "18:00", "20:00", "22:30"]
from naadi.paths import MODEL, RESULTS, WORK


def weekend(ts):
    d = np.floor((np.asarray(ts) + 19800) / 86400).astype(np.int64)
    return (((d + 3) % 7) >= 5).astype(np.int64)


class LiveDay:
    """Nowcast multipliers for routing at time t, from the day's traversals completed before t."""

    def __init__(self, grid: LinkGrid, tables: str, day: str, p: NowcastParams):
        self.grid, self.p = grid, p
        geom = pq.read_table(MODEL / "tables" / tables / "geom.parquet").to_pydict()
        gi = grid.index(np.array(geom["route_id"]), np.array(geom["ord"]))
        _, cid = np.unique((np.array(geom["gy"], np.int64) * 100000 + np.array(geom["gx"])) * 8 + np.array(geom["hd"]), return_inverse=True)
        self.cell = np.zeros(len(grid.route), np.int64)
        self.cell[gi[gi >= 0]] = cid[gi >= 0]
        L = duckdb.sql(f"SELECT route_id, ord, t, tt_s FROM read_parquet('{(WORK / 'links' / f'day={day}.parquet').as_posix()}')").fetchnumpy()
        li = grid.index(L["route_id"], L["ord"]); m = li >= 0
        li, t, tt = li[m], L["t"][m], L["tt_s"][m]
        res = np.log(tt) - grid.log_tt("gbm", li, weekend(t), t)
        tref = float(t.min()) - 7200
        self.links = ResidualIndex(li, t + tt, res, tref)
        self.cells = ResidualIndex(self.cell[li], t + tt, res, tref)
        self.all = np.arange(len(grid.route))

    def mult(self, t: float) -> np.ndarray:
        out = np.ones((24, len(self.all)), np.float32)
        h_now = ((t + 19800) % 86400) / 3600
        t0 = np.full(len(self.all), t)
        for h in range(24):
            ahead = ((h + 0.5 - h_now) % 24) * 3600
            if ahead > 6 * 3600:
                continue
            out[h] = np.exp(correction(self.p, self.links, self.cells, self.all, self.cell, t0, t0 + ahead))
        return out


def best(pl: Planner, o, d, t, mult=None):
    js, _ = pl.run(o, d, t, live_mult=mult)
    bj = None
    for j in js:
        r = refine_live(pl, j, t, mult)
        if r is not None and (bj is None or r.total_s + 300 * (r.n_bus - 1) < bj.total_s + 300 * (bj.n_bus - 1)):
            bj = r
    return bj


def refine_live(pl, j, t, mult):
    if mult is None:
        return refine(pl, j, t)
    cum0 = pl.cum
    we = int(weekend(t))
    _, cum_live, _ = pl.tables(t, mult)
    tmp = cum0.copy()
    tmp[we] = cum_live
    pl.cum = tmp
    try:
        return refine(pl, j, t)
    finally:
        pl.cum = cum0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--network", required=True)
    ap.add_argument("--days", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--live", action="store_true", help="also evaluate naadi_live (needs links of the test day)")
    ap.add_argument("--grid", default="grid_oct01_24")
    ap.add_argument("--tables", default="oct01_24")
    a = ap.parse_args()
    net = Network(MODEL / f"network_{a.network}")
    planners = {"naadi": Planner(net, "naadi"), "timetable": Planner(net, "timetable")}
    grid = LinkGrid(MODEL / f"{a.grid}.parquet", methods=("gbm",)) if a.live else None
    p = NowcastParams(**json.loads((ROOT / "validation" / "results" / "eta_oct.json").read_text())["nowcast"]) if a.live else None
    od = list(csv.DictReader((ROOT / "validation" / "od_set.csv").open(encoding="utf-8")))
    rows = []
    t_start = time.time()
    for day in a.days:
        dp = DayPassages(day)
        live = LiveDay(grid, a.tables, day, p) if a.live else None
        y, m, d = map(int, day.split("_"))
        for slot in SLOTS:
            hh, mm = map(int, slot.split(":"))
            t = dt.datetime(y, m, d, hh, mm, tzinfo=IST).timestamp()
            mult = live.mult(t) if live else None
            for r in od:
                o, dd = (float(r["o_lat"]), float(r["o_lon"])), (float(r["d_lat"]), float(r["d_lon"]))
                runs = [("naadi", planners["naadi"], None), ("timetable", planners["timetable"], None)]
                if mult is not None:
                    runs.append(("naadi_live", planners["naadi"], mult))
                for name, pl, mu in runs:
                    j = best(pl, o, dd, t, mu)
                    row = {"day": day, "slot": slot, "od_id": r["od_id"], "kind": r["kind"], "planner": name,
                           "pred_s": None, "actual_s": None, "status": "no journey", "n_bus": 0, "walk_m": 0.0,
                           "wait_pred_s": None, "routes": ""}
                    if j is not None:
                        act, why = realise(net, j, dp)
                        row.update(pred_s=float(j.total_s), actual_s=act, status=why, n_bus=j.n_bus, walk_m=float(j.walk_m()),
                                   wait_pred_s=float(sum(l.wait_s for l in j.legs if l.kind == "bus")),
                                   routes="+".join(net.route_short[l.route] for l in j.legs if l.kind == "bus"))
                    rows.append(row)
        print(f"{day} done, {len(rows):,} rows, {time.time() - t_start:.0f}s", flush=True)
    out = RESULTS
    out.mkdir(parents=True, exist_ok=True)
    cols = {k: [r[k] for r in rows] for k in rows[0]}
    pq.write_table(pa.table(cols), out / f"{a.out}.parquet")
    summ = {}
    for name in sorted({r["planner"] for r in rows}):
        ok = [r for r in rows if r["planner"] == name and r["status"] == "ok"]
        e = np.array([r["pred_s"] - r["actual_s"] for r in ok])
        act = np.array([r["actual_s"] for r in ok])
        st = {}
        for r in rows:
            if r["planner"] == name:
                st[r["status"]] = st.get(r["status"], 0) + 1
        summ[name] = {"n_ok": len(ok), "status": st, "mae_min": float(np.mean(np.abs(e)) / 60),
                      "median_abs_min": float(np.median(np.abs(e)) / 60),
                      "mape_pct": float(100 * np.mean(np.abs(e) / act)), "bias_min": float(np.mean(e) / 60),
                      "within_5min_pct": float(100 * np.mean(np.abs(e) <= 300)),
                      "within_10min_pct": float(100 * np.mean(np.abs(e) <= 600)),
                      "actual_median_min": float(np.median(act) / 60)}
    (out / f"{a.out}.json").write_text(json.dumps(summ, indent=1))
    print(json.dumps({k: {kk: v[kk] for kk in ("n_ok", "mae_min", "bias_min", "within_10min_pct")} for k, v in summ.items()}, indent=1))


if __name__ == "__main__":
    main()
