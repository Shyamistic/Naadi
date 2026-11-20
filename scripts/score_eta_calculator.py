"""Fair, same-run head-to-head with the organisers' ETA Calculator.

The two reported variants keep the same cases and differ only in the prediction
anchor: ``as_served`` starts at the request, while ``same_fix`` starts at the
ETA Calculator's own GPS fix.  Actual crossings are restricted to that bus run.
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
from naadi.paths import ETA, L2, MODEL, RESULTS, TMP, WORK  # noqa: E402

RES = RESULTS
BANDS = [("0-5 min", 0, 5), ("5-10 min", 5, 10), ("10-20 min", 10, 20),
         ("20-40 min", 20, 40), ("40+ min", 40, 1e9)]


def weekend(ts):
    d = np.floor((np.asarray(ts) + 19800) / 86400).astype(np.int64)
    return (((d + 3) % 7) >= 5).astype(np.int64)


def _arrays(d):
    out = {}
    for k, v in d.items():
        if hasattr(v, "filled"):
            fill = 0 if np.issubdtype(v.dtype, np.integer) else np.nan
            out[k] = np.asarray(v.filled(fill), dtype=np.float64)
        else:
            out[k] = np.asarray(v)
    return out


def cases(con, day: str, sample_pct: float) -> dict:
    """Return matched cases; vehicle identifiers never leave this query."""
    iso = day.replace("_", "-")
    q = f"""
    WITH e0 AS (
        SELECT req_ts, vehicle_id, vehicle_ts, CAST(route_id AS INTEGER) AS route_id,
               CAST(stop_id AS INTEGER) AS stop_id, eta_min
        FROM read_parquet('{(ETA / f'date={iso}' / '*.parquet').as_posix()}')
        WHERE kind = 'bus' AND http = 200 AND eta_min IS NOT NULL
    ), e AS (
        SELECT * FROM e0 USING SAMPLE {sample_pct} PERCENT (bernoulli, 5)
    ), s AS (
        SELECT route_id, CAST(stop_id AS INTEGER) AS stop_id, min(ord) AS ord, min(sd) AS sd
        FROM read_parquet('{(WORK / 'stops_on_shape.parquet').as_posix()}') GROUP BY 1, 2
    ), p0 AS (
        SELECT vehicle_id, route_id, ts, shape_dist_m AS d
        FROM read_parquet('{(L2 / f'day={day}.parquet').as_posix()}')
        WHERE match_status = 'matched'
    ), p1 AS (
        SELECT *, lag(ts) OVER w AS pt, lag(d) OVER w AS pd
        FROM p0 WINDOW w AS (PARTITION BY vehicle_id, route_id ORDER BY ts)
    ), p AS (
        SELECT *, sum(CASE WHEN pt IS NULL OR ts - pt > 1200 OR d < pd - 1000 THEN 1 ELSE 0 END)
                   OVER (PARTITION BY vehicle_id, route_id ORDER BY ts) AS run
        FROM p1
    ), seg AS (
        SELECT *, lead(ts) OVER w AS t1, lead(d) OVER w AS d1
        FROM p WINDOW w AS (PARTITION BY vehicle_id, route_id, run ORDER BY ts)
    ), ec AS (
        SELECT e.*, s.ord, s.sd
        FROM e JOIN s USING (route_id, stop_id)
    ), pos AS (
        SELECT ec.*, p.ts AS ts_p, p.d AS d_p, p.run AS run_p
        FROM ec ASOF JOIN p
          ON ec.vehicle_id = p.vehicle_id AND ec.route_id = p.route_id AND ec.req_ts >= p.ts
    ), posf AS (
        SELECT pos.*,
               CASE WHEN pos.vehicle_ts - f.ts <= 60 AND f.run = pos.run_p AND f.d < pos.sd - 10 THEN f.ts END AS ts_f,
               CASE WHEN pos.vehicle_ts - f.ts <= 60 AND f.run = pos.run_p AND f.d < pos.sd - 10 THEN f.d END AS d_f,
               f.run AS run_f
        FROM pos ASOF LEFT JOIN p AS f
          ON pos.vehicle_id = f.vehicle_id AND pos.route_id = f.route_id AND pos.vehicle_ts >= f.ts
         AND pos.vehicle_ts - f.ts <= 60
    ), act AS (
        SELECT pos.req_ts, pos.vehicle_id, pos.route_id, pos.stop_id,
               min(seg.ts + (pos.sd - seg.d) / (seg.d1 - seg.d) * (seg.t1 - seg.ts)) AS t_actual
        FROM pos JOIN seg
          ON seg.vehicle_id = pos.vehicle_id AND seg.route_id = pos.route_id AND seg.run = pos.run_p
         AND seg.t1 > pos.req_ts AND seg.t1 <= pos.req_ts + 10800
         AND seg.d < pos.sd AND seg.d1 >= pos.sd AND seg.t1 - seg.ts BETWEEN 1 AND 120
         AND seg.d1 > seg.d
        WHERE pos.req_ts - pos.ts_p <= 180 AND pos.d_p < pos.sd - 10
        GROUP BY 1, 2, 3, 4
    )
    SELECT posf.req_ts, posf.route_id, posf.ord, posf.sd, posf.eta_min, posf.ts_p, posf.d_p,
           posf.vehicle_ts, posf.ts_f, posf.d_f, posf.run_f, posf.run_p, act.t_actual,
           count(*) OVER () AS sampled_n
    FROM posf JOIN act USING (req_ts, vehicle_id, route_id, stop_id)
    WHERE act.t_actual > posf.req_ts
    """
    d = _arrays(con.execute(q).fetchnumpy())
    sampled_n = int(d.pop("sampled_n")[0]) if d else 0
    d["_sampled_n"] = sampled_n
    return d


def naadi_arrival(c: dict, grid: LinkGrid, sd_of: np.ndarray, cell: np.ndarray,
                  p: NowcastParams, links_ix: ResidualIndex, cells_ix: ResidualIndex,
                  ts_fix, d_fix, t_ref, live: bool) -> np.ndarray:
    """Predict absolute stop-arrival timestamps from a chosen GPS fix."""
    n = len(c["req_ts"])
    idx0 = grid.index(c["route_id"], np.ones(n, dtype=np.int64))
    idx_bus = np.full(n, -1, dtype=np.int64)
    for i in range(n):
        b = idx0[i]
        if b < 0 or not np.isfinite(d_fix[i]):
            continue
        while grid.has_next[b] and sd_of[b + 1] <= d_fix[i]:
            b += 1
        idx_bus[i] = b
    ok = idx_bus >= 0
    safe = np.maximum(idx_bus, 0)
    t = np.asarray(ts_fix, dtype=np.float64).copy()
    we = weekend(t)
    tgt = grid.index(c["route_id"], c["ord"]) - 1
    frac = np.clip((np.asarray(d_fix) - sd_of[safe]) / np.maximum(grid.dist[safe], 1), 0, 1)
    lt = grid.log_tt("gbm", safe, we, t)
    if live:
        lt = lt + correction(p, links_ix, cells_ix, safe, cell[safe], np.asarray(t_ref), t)
    t = t + (1 - frac) * np.exp(lt)
    steps = np.clip(tgt - idx_bus, 0, 200)
    for s in range(1, int(max(steps.max(), 0)) + 1):
        active = (s <= steps) & ok
        j = np.where(active, idx_bus + s, safe)
        ltj = grid.log_tt("gbm", j, we, t)
        if live:
            ltj = ltj + correction(p, links_ix, cells_ix, j, cell[j], np.asarray(t_ref), t)
        t = np.where(active, t + np.exp(ltj), t)
    return np.where(ok, t, np.nan)


def report(y, preds) -> dict:
    out = {"n": int(len(y)), "methods": {}}
    for name, pr in preds.items():
        e = np.abs(pr - y)
        out["methods"][name] = {
            "mae_min": float(e.mean() / 60), "median_abs_min": float(np.median(e) / 60),
            "within_2min_pct": float(100 * np.mean(e <= 120)), "bias_min": float(np.mean(pr - y) / 60),
            "by_band_mae_min": {b: float(np.mean(e[(y >= lo * 60) & (y < hi * 60)]) / 60)
                                if np.any((y >= lo * 60) & (y < hi * 60)) else None
                                for b, lo, hi in BANDS}}
    return out


def main() -> None:
    con = duckdb.connect()
    con.execute(f"SET TimeZone='UTC'; SET memory_limit='1.5GB'; SET threads=4; SET temp_directory='{TMP.as_posix()}'")
    days = sorted(p.stem.split("=")[1] for p in L2.glob("day=2026_11_*.parquet"))
    days = [d for d in days if (ETA / f"date={d.replace('_', '-')}").exists()]
    grid = LinkGrid(MODEL / "grid_oct_all.parquet", methods=("gbm",))
    so = _arrays(con.execute(f"SELECT route_id, ord, sd FROM read_parquet('{(WORK / 'stops_on_shape.parquet').as_posix()}')").fetchnumpy())
    sd_idx = grid.index(so["route_id"], so["ord"])
    sd_of = np.zeros(len(grid.route)); good = sd_idx >= 0; sd_of[sd_idx[good]] = so["sd"][good]
    files = ", ".join(f"'{(WORK / 'links' / f'day={d}.parquet').as_posix()}'" for d in days)
    L = _arrays(con.execute(f"SELECT route_id, ord, t, tt_s FROM read_parquet([{files}])").fetchnumpy())
    li = grid.index(L["route_id"], L["ord"]); m = li >= 0
    li, lt, ltt = li[m], L["t"][m], L["tt_s"][m]
    res = np.log(ltt) - grid.log_tt("gbm", li, weekend(lt), lt)
    geom = _arrays(con.execute(f"SELECT route_id, ord, gy, gx, hd FROM read_parquet('{(MODEL / 'tables' / 'oct_all' / 'geom.parquet').as_posix()}')").fetchnumpy())
    gi = grid.index(geom["route_id"], geom["ord"]); ggood = gi >= 0
    _, cid = np.unique((geom["gy"].astype(np.int64) * 100000 + geom["gx"]) * 8 + geom["hd"], return_inverse=True)
    cell = np.zeros(len(grid.route), np.int64); cell[gi[ggood]] = cid[ggood]
    tref = float(lt.min()) - 7200
    links_ix, cells_ix = ResidualIndex(li, lt + ltt, res, tref), ResidualIndex(cell[li], lt + ltt, res, tref)
    p = NowcastParams(**json.loads((RES / "eta_oct.json").read_text())["nowcast"])

    allc, sampled_total = {}, 0
    for d in days:
        cday = cases(con, d, 3.0)
        sampled_total += cday.pop("_sampled_n", 0)
        print(d, f"{len(cday.get('req_ts', [])):,} same-run cases", flush=True)
        for k, v in cday.items():
            allc.setdefault(k, []).append(v)
    if not allc:
        raise RuntimeError("No ETA Calculator cases matched the same-run protocol")
    c = {k: np.concatenate(v) for k, v in allc.items()}
    y = c["t_actual"] - c["req_ts"]
    as_hist = naadi_arrival(c, grid, sd_of, cell, p, links_ix, cells_ix,
                            c["ts_p"], c["d_p"], c["req_ts"], False)
    as_live = naadi_arrival(c, grid, sd_of, cell, p, links_ix, cells_ix,
                            c["ts_p"], c["d_p"], c["req_ts"], True)
    same_ok = np.isfinite(c["ts_f"]) & np.isfinite(c["d_f"]) & (c["run_f"] == c.get("run_p", c["run_f"]))
    # The SQL has already matched actuals to run_p; same_ok only gates the calculator fix.
    usable = np.isfinite(as_hist) & (y > 0)
    if not np.any(usable):
        raise RuntimeError("No finite as-served Naadi predictions")
    y1 = y[usable]
    eta1 = c["eta_min"][usable] * 60.0
    a1 = {"ETA Calculator (Transport Stack)": eta1,
          "Naadi history": as_hist[usable] - c["req_ts"][usable],
          "Naadi history + live": as_live[usable] - c["req_ts"][usable]}
    sf_hist = naadi_arrival(c, grid, sd_of, cell, p, links_ix, cells_ix,
                            c["ts_f"], c["d_f"], c["ts_f"], False)
    sf_live = naadi_arrival(c, grid, sd_of, cell, p, links_ix, cells_ix,
                            c["ts_f"], c["d_f"], c["ts_f"], True)
    same = usable & same_ok & np.isfinite(sf_hist) & np.isfinite(sf_live)
    y2 = y[same]
    eta2 = c["eta_min"][same] * 60.0
    a2 = {"ETA Calculator (Transport Stack)": eta2,
          "Naadi history": sf_hist[same] - c["ts_f"][same],
          "Naadi history + live": sf_live[same] - c["ts_f"][same]}
    reps = {"as_served": report(y1, a1), "same_fix": report(y2, a2)}
    headline = min(reps, key=lambda v: reps[v]["methods"]["ETA Calculator (Transport Stack)"]["mae_min"])
    age = c["req_ts"][usable] - c["vehicle_ts"][usable]
    rep = {"days": days, "n": reps[headline]["n"], "methods": reps[headline]["methods"],
           "headline_variant": headline, "variants": reps,
           "dropped": {"no_same_run_crossing": max(0, sampled_total - len(c["req_ts"])),
                       "no_usable_fix": int(np.sum(usable & ~same_ok))},
           "notes": {"answers_whole_minutes": True, "median_fix_age_s": float(np.median(age)),
                     "fix_age_p10_p90_s": [float(np.quantile(age, .1)), float(np.quantile(age, .9))],
                     "run_rule": "new run after >1200 s gap or >1000 m backward jump; actual crossing and fix are same vehicle run",
                     "anchors": {"as_served": "request timestamp", "same_fix": "ETA Calculator vehicle_ts"},
                     "sampled_cases": sampled_total}}
    RES.mkdir(parents=True, exist_ok=True)
    (RES / "eta_calculator_nov.json").write_text(json.dumps(rep, indent=1))
    def table(r):
        lines = ["| Method | MAE (min) | median error (min) | within 2 min | bias (min) | " + " | ".join(b for b, _, _ in BANDS) + " |",
                 "|---|---|---|---|---|" + "---|" * len(BANDS)]
        for name, v in r["methods"].items():
            lines.append(f"| {name} | {v['mae_min']:.2f} | {v['median_abs_min']:.2f} | {v['within_2min_pct']:.1f}% | {v['bias_min']:+.2f} | " +
                         " | ".join("n/a" if v["by_band_mae_min"][b] is None else f"{v['by_band_mae_min'][b]:.2f}" for b, _, _ in BANDS) + " |")
        return lines
    Lout = [f"# Fair head-to-head with the Transport Stack ETA Calculator ({', '.join(days)})", "",
            f"Headline variant: **{headline}**, chosen because it gives the ETA Calculator the lower MAE. {rep['n']:,} same-run cases.", "",
            "## Headline table", ""] + table(reps[headline]) + ["", "## Other anchor", ""] + table(reps["same_fix" if headline == "as_served" else "as_served"])
    Lout += ["", f"As-served anchors both methods at the request; same-fix anchors both at the Calculator's vehicle_ts. The Calculator fix is {rep['notes']['median_fix_age_s']:.0f} s older at the median (p10-p90 {rep['notes']['fix_age_p10_p90_s'][0]:.0f}-{rep['notes']['fix_age_p10_p90_s'][1]:.0f} s).", "",
             f"Actuals use the same vehicle run, split after a gap over 1,200 s or a backward jump over 1,000 m. Dropped no-same-run cases: {rep['dropped']['no_same_run_crossing']}; cases without a usable same-run fix: {rep['dropped']['no_usable_fix']}."]
    (RES / "eta_calculator_nov.md").write_text("\n".join(Lout) + "\n", encoding="utf-8")
    print("\n".join(Lout), flush=True)


if __name__ == "__main__":
    main()
