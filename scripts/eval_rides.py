"""Ride-only ETA table comparable with Delhi Pulse, on Naadi's held-out days."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from eval_eta import Ctx, TEST, predict  # noqa: E402
from naadi.linkgrid import LinkGrid  # noqa: E402
from naadi.nowcast import NowcastParams  # noqa: E402
from naadi.paths import MODEL, RESULTS, TMP, WORK  # noqa: E402

RES = RESULTS
HORIZONS = list(range(5, 41))
SAMPLE_PCT = 3.0
COMPETITOR = {"sample": "Delhi Pulse published ride sample (different sample)", "mean_error_min": 4.6,
              "mean_ride_min": 30.9, "within_5min_pct": 69.0, "within_10min_pct": 90.5,
              "by_length_mae_min": {"5-9 stops": 3.55, "10-20 stops": 4.14, "21-40 stops": 5.76},
              "source": ".agents/tasks/research-competitors-2026-11-17.md §1 (Validation) and §10 (idea 4)"}


def cases(con) -> dict:
    files = ", ".join(f"'{(WORK / 'passages' / f'day=2026_10_{d:02d}.parquet').as_posix()}'" for d in range(26, 32))
    hs = ", ".join(map(str, HORIZONS))
    q = f"""
    WITH p AS (SELECT k, route_id, ord, t FROM read_parquet([{files}])),
    o AS (SELECT * FROM p USING SAMPLE {SAMPLE_PCT} PERCENT (bernoulli, 41)),
    h AS (SELECT unnest([{hs}]) AS h),
    g AS (SELECT k, route_id, ord, t, lead(t) OVER (PARTITION BY k, route_id ORDER BY ord) AS next_t FROM p),
    r AS (
      SELECT o.k, o.route_id, o.ord AS i, h.h, o.t AS t0, p2.t AS t1,
             max(g.next_t - g.t) AS max_gap_s
      FROM o CROSS JOIN h
      JOIN p p2 ON p2.k=o.k AND p2.route_id=o.route_id AND p2.ord=o.ord+h.h
      LEFT JOIN g ON g.k=o.k AND g.route_id=o.route_id AND g.ord BETWEEN o.ord AND o.ord+h.h-1
      GROUP BY o.k, o.route_id, o.ord, h.h, o.t, p2.t
    )
    SELECT * FROM r WHERE t1-t0 BETWEEN 5*h AND least(1800*h, 10800)
    """
    d = con.execute(q).fetchnumpy()
    return {k: np.asarray(v.filled(np.nan) if hasattr(v, "filled") else v) for k, v in d.items()}


def summary(y, pred, h, include):
    keep = include & np.isfinite(pred) & np.isfinite(y)
    e = np.abs(pred[keep] - y[keep]) / 60
    hh = h[keep]
    def band(lo, hi):
        m = (hh >= lo) & (hh <= hi)
        return float(np.mean(e[m])) if np.any(m) else None
    return {"n": int(keep.sum()), "mean_ride_min": float(np.mean(y[keep]) / 60),
            "mean_error_min": float(np.mean(e)), "within_5min_pct": float(100*np.mean(e <= 5)),
            "within_10min_pct": float(100*np.mean(e <= 10)),
            "by_length_mae_min": {"5-9 stops": band(5, 9), "10-20 stops": band(10, 20), "21-40 stops": band(21, 40)}}


def main():
    con = duckdb.connect()
    con.execute(f"SET TimeZone='UTC'; SET memory_limit='1.5GB'; SET threads=4; SET temp_directory='{TMP.as_posix()}'")
    grid = LinkGrid(MODEL / "grid_oct01_24.parquet")
    ctx = Ctx(grid, TEST)
    c = cases(con)
    y = c["t1"] - c["t0"]
    p = NowcastParams(**json.loads((RES / "eta_oct.json").read_text())["nowcast"])
    pred = predict(ctx, c, "naadi", p)
    all_mask = np.ones(len(y), bool)
    gap_mask = c["max_gap_s"] <= 600
    result = {"history_days": ["2026_10_01" + " to 2026_10_24"], "test_days": TEST,
              "protocol": "one bus trip, 5 to 40 consecutive stops, Naadi nowcast tuned on 25 Oct",
              "sample_pct": SAMPLE_PCT, "method": "Naadi history + live nowcast",
              "with_gaps_over_10min": summary(y, pred, c["h"], all_mask),
              "without_gaps_over_10min": summary(y, pred, c["h"], gap_mask),
              "published_comparator": COMPETITOR}
    RES.mkdir(parents=True, exist_ok=True)
    (RES / "rides_oct.json").write_text(json.dumps(result, indent=1))
    def row(name, r):
        n = "published" if r.get("n") is None else f"{r['n']:,}"
        return f"| {name} | {n} | {r['mean_error_min']:.2f} | {r['mean_ride_min']:.2f} | {r['within_5min_pct']:.1f}% | {r['within_10min_pct']:.1f}% | {r['by_length_mae_min']['5-9 stops']:.2f} | {r['by_length_mae_min']['10-20 stops']:.2f} | {r['by_length_mae_min']['21-40 stops']:.2f} |"
    L = ["# Ride-only ETA comparison, held-out 26 to 31 Oct 2026", "",
         "Each row is a ride of 5 to 40 consecutive stops on one bus trip. History is 1 to 24 Oct; the nowcast is tuned on 25 Oct. The primary Naadi sample includes all observed gaps; the sensitivity excludes rides with any consecutive-stop gap over 10 minutes.", "",
         "| Sample | n | mean error (min) | mean ride (min) | within 5 min | within 10 min | 5-9 stops | 10-20 stops | 21-40 stops |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
         row("Naadi, with >10 min gaps", result["with_gaps_over_10min"]), row("Naadi, no >10 min gaps", result["without_gaps_over_10min"]), "",
         "## Delhi Pulse published figure", "",
         "The following is Delhi Pulse's own published figure on a different sample, shown for like-for-like context, not as a re-score of their data.", "",
         "| Sample | mean error (min) | mean ride (min) | within 5 min | within 10 min | 5-9 stops | 10-20 stops | 21-40 stops |", "|---|---:|---:|---:|---:|---:|---:|---:|",
         row("Delhi Pulse published, different sample", {"n": None, **COMPETITOR}), "",
         f"Source: `{COMPETITOR['source']}`."]
    (RES / "rides_oct.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L), flush=True)


if __name__ == "__main__":
    main()
