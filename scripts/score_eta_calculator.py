"""Head-to-head with the organisers' ETA Calculator on our own recorded days (Nov 2026).

For each logged ETA Calculator answer (bus X will reach stop S in N minutes, asked at time T):
  actual   when bus X really crossed stop S after T (interpolated from its GPS along the route shape)
  naadi    our prediction from the same bus position at T: remaining links at the model's hourly MEAN times
           (history from October only), with and without the live nowcast from November traversals.
Only cases where the bus had not yet reached the stop and the crossing is bracketed by GPS fixes <= 120 s apart.
Output: validation/results/eta_calculator_nov.json and .md (aggregates only).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from naadi.linkgrid import LinkGrid  # noqa: E402
from naadi.nowcast import NowcastParams, ResidualIndex, correction  # noqa: E402

WORK = ROOT / "data" / "processed" / "speed_tables" / "_work"
MODEL = ROOT / "data" / "processed" / "model"
L2 = ROOT / "data" / "processed" / "gps_l2"
ETA = ROOT / "data" / "raw" / "eta_s3"
RES = ROOT / "validation" / "results"
BANDS = [("0-5 min", 0, 5), ("5-10 min", 5, 10), ("10-20 min", 10, 20), ("20-40 min", 20, 40), ("40+ min", 40, 1e9)]


def weekend(ts):
    d = np.floor((np.asarray(ts) + 19800) / 86400).astype(np.int64)
    return (((d + 3) % 7) >= 5).astype(np.int64)


def cases(con, day: str, sample_pct: float) -> dict:
    iso = day.replace("_", "-")
    q = f"""
    WITH e AS (
        SELECT req_ts, vehicle_id, CAST(route_id AS INTEGER) AS route_id, CAST(stop_id AS INTEGER) AS stop_id, eta_min
        FROM read_parquet('{(ETA / f'date={iso}' / '*.parquet').as_posix()}')
        WHERE kind = 'bus' AND http = 200 AND eta_min IS NOT NULL
        USING SAMPLE {sample_pct} PERCENT (bernoulli, 5)
    ), s AS (
        SELECT route_id, CAST(stop_id AS INTEGER) AS stop_id, min(ord) AS ord, min(sd) AS sd
        FROM read_parquet('{(WORK / 'stops_on_shape.parquet').as_posix()}') GROUP BY 1, 2
    ), p AS (
        SELECT vehicle_id, route_id, ts, shape_dist_m AS d FROM read_parquet('{(L2 / f'day={day}.parquet').as_posix()}')
        WHERE match_status = 'matched'
    ), seg AS (
        SELECT vehicle_id, route_id, ts AS t1, d AS d1, lag(ts) OVER w AS t0, lag(d) OVER w AS d0 FROM p
        WINDOW w AS (PARTITION BY vehicle_id, route_id ORDER BY ts)
    ), ec AS (SELECT e.*, s.ord, s.sd FROM e JOIN s USING (route_id, stop_id)),
    pos AS (
        SELECT ec.*, p.ts AS ts_p, p.d AS d_p FROM ec ASOF JOIN p
        ON ec.vehicle_id = p.vehicle_id AND ec.route_id = p.route_id AND ec.req_ts >= p.ts
    ), act AS (
        SELECT pos.req_ts, pos.vehicle_id, pos.route_id, pos.stop_id,
               min(seg.t0 + (pos.sd - seg.d0) / (seg.d1 - seg.d0) * (seg.t1 - seg.t0)) AS t_actual
        FROM pos JOIN seg ON seg.vehicle_id = pos.vehicle_id AND seg.route_id = pos.route_id
         AND seg.t1 > pos.req_ts AND seg.t1 <= pos.req_ts + 10800
         AND seg.d0 < pos.sd AND seg.d1 >= pos.sd AND seg.t1 - seg.t0 BETWEEN 1 AND 120 AND seg.d1 > seg.d0
        WHERE pos.req_ts - pos.ts_p <= 180 AND pos.d_p < pos.sd - 10
        GROUP BY 1, 2, 3, 4
    )
    SELECT pos.req_ts, pos.route_id, pos.ord, pos.sd, pos.eta_min, pos.ts_p, pos.d_p, act.t_actual
    FROM pos JOIN act USING (req_ts, vehicle_id, route_id, stop_id)
    WHERE act.t_actual > pos.req_ts
    """
    return {k: np.asarray(v) for k, v in con.execute(q).fetchnumpy().items()}


def main() -> None:
    con = duckdb.connect()
    con.execute(f"SET TimeZone='UTC'; SET memory_limit='6GB'; SET threads=8; SET temp_directory='{(ROOT / 'data' / 'tmp_duckdb').as_posix()}'")
    days = sorted(p.stem.split("=")[1] for p in L2.glob("day=2026_11_*.parquet"))
    days = [d for d in days if (ETA / f"date={d.replace('_', '-')}").exists()]
    grid = LinkGrid(MODEL / "grid_oct_all.parquet", methods=("gbm",))
    so = con.execute(f"SELECT route_id, ord, sd FROM read_parquet('{(WORK / 'stops_on_shape.parquet').as_posix()}')").fetchnumpy()
    sd_idx = grid.index(so["route_id"], so["ord"])
    sd_of = np.zeros(len(grid.route)); sd_of[sd_idx[sd_idx >= 0]] = so["sd"][sd_idx >= 0]
    # nowcast store from November traversals
    files = ", ".join(f"'{(WORK / 'links' / f'day={d}.parquet').as_posix()}'" for d in days)
    L = con.execute(f"SELECT route_id, ord, t, tt_s FROM read_parquet([{files}])").fetchnumpy()
    li = grid.index(L["route_id"], L["ord"]); m = li >= 0
    li, lt, ltt = li[m], L["t"][m], L["tt_s"][m]
    res = np.log(ltt) - grid.log_tt("gbm", li, weekend(lt), lt)
    geom = con.execute(f"SELECT route_id, ord, gy, gx, hd FROM read_parquet('{(MODEL / 'tables' / 'oct_all' / 'geom.parquet').as_posix()}')").fetchnumpy()
    gi = grid.index(geom["route_id"], geom["ord"])
    _, cid = np.unique((geom["gy"].astype(np.int64) * 100000 + geom["gx"]) * 8 + geom["hd"], return_inverse=True)
    cell = np.zeros(len(grid.route), np.int64); cell[gi[gi >= 0]] = cid[gi >= 0]
    tref = float(lt.min()) - 7200
    links_ix, cells_ix = ResidualIndex(li, lt + ltt, res, tref), ResidualIndex(cell[li], lt + ltt, res, tref)
    p = NowcastParams(**json.loads((RES / "eta_oct.json").read_text())["nowcast"])
    allc = {}
    for d in days:
        c = cases(con, d, 25.0)
        print(d, f"{len(c['req_ts']):,} cases", flush=True)
        for k, v in c.items():
            allc.setdefault(k, []).append(v)
    c = {k: np.concatenate(v) for k, v in allc.items()}
    y = c["t_actual"] - c["req_ts"]
    eta = c["eta_min"] * 60.0
    # Naadi: from bus position (ts_p, d_p) to the stop
    out = {}
    for live in (False, True):
        k0 = grid.index(c["route_id"], np.ones_like(c["ord"]))  # first link of route
        # link containing the bus: largest ord whose stop sd <= d_p (searching along the route)
        idx_bus = np.full(len(y), -1)
        for i in range(len(y)):
            a = k0[i]
            if a < 0:
                continue
            b = a
            while grid.has_next[b] and sd_of[b + 1] <= c["d_p"][i]:
                b += 1
            idx_bus[i] = b
        okm = (idx_bus >= 0)
        t = c["ts_p"].astype(np.float64).copy()
        we = weekend(t)
        tgt = grid.index(c["route_id"], c["ord"]) - 1  # last link before the stop
        ix = idx_bus.copy()
        frac = np.clip((c["d_p"] - sd_of[ix]) / np.maximum(grid.dist[ix], 1), 0, 1)
        lt0 = grid.log_tt("gbm", ix, we, t) + (correction(p, links_ix, cells_ix, ix, cell[ix], c["req_ts"], t) if live else 0)
        t = t + (1 - frac) * np.exp(lt0)
        steps = np.clip(tgt - idx_bus, 0, 200)
        for s in range(1, int(steps.max()) + 1):
            a = s <= steps
            j = np.where(a, idx_bus + s, idx_bus)
            ltj = grid.log_tt("gbm", j, we, t) + (correction(p, links_ix, cells_ix, j, cell[j], c["req_ts"], t) if live else 0)
            t = np.where(a, t + np.exp(ltj), t)
        out["naadi_live" if live else "naadi_history"] = np.where(okm, t - c["req_ts"], np.nan)
    keep = np.isfinite(out["naadi_live"]) & (y > 0)
    y, eta = y[keep], eta[keep]
    preds = {"ETA Calculator (Transport Stack)": eta, "Naadi history": out["naadi_history"][keep], "Naadi history + live": out["naadi_live"][keep]}
    rep = {"days": days, "n": int(len(y)), "methods": {}}
    for name, pr in preds.items():
        e = np.abs(pr - y)
        rep["methods"][name] = {"mae_min": float(e.mean() / 60), "median_abs_min": float(np.median(e) / 60),
                                "within_2min_pct": float(100 * np.mean(e <= 120)), "bias_min": float(np.mean(pr - y) / 60),
                                "by_band_mae_min": {b: float(np.mean(e[(y >= lo * 60) & (y < hi * 60)]) / 60) for b, lo, hi in BANDS}}
    RES.mkdir(parents=True, exist_ok=True)
    (RES / "eta_calculator_nov.json").write_text(json.dumps(rep, indent=1))
    L = [f"# Head-to-head with the Transport Stack ETA Calculator ({', '.join(days)})", "",
         f"{len(y):,} logged ETA Calculator answers for live buses, scored against when each bus actually reached the stop.", "",
         "| Method | MAE (min) | median error (min) | within 2 min | bias (min) | " + " | ".join(b for b, _, _ in BANDS) + " |",
         "|---|---|---|---|---|" + "---|" * len(BANDS)]
    for name, r in rep["methods"].items():
        L.append(f"| {name} | {r['mae_min']:.2f} | {r['median_abs_min']:.2f} | {r['within_2min_pct']:.1f}% | {r['bias_min']:+.2f} | "
                 + " | ".join(f"{r['by_band_mae_min'][b]:.2f}" for b, _, _ in BANDS) + " |")
    (RES / "eta_calculator_nov.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
