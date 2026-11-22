"""Baseline for the city pulse: the median live-style residual by IST hour and day type on ordinary October days.

The live engine scores each stretch a bus drives as r = ln(observed time) - ln(model time). The model (LightGBM with
a gamma loss) predicts the mean stretch time, and stretch times are right-skewed, so even on an ordinary day the
median r is below zero (for log-normal times with spread s, by about s^2 / 2). Without this baseline the pulse would
call every ordinary moment "faster than usual". GET /pulse compares the live median with the median here for the
same hour and day type.

Usage: .venv\\Scripts\\python.exe scripts\\build_pulse_baseline.py [--days 2026_10_06 ...] [--sample 10]
Writes data/processed/model/pulse_baseline.json (48 medians and counts; aggregates only).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import duckdb
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from naadi.linkgrid import LinkGrid  # noqa: E402
from naadi.paths import MODEL, WORK  # noqa: E402

# Ordinary days only: no gazetted holiday (2, 20 and 26 Oct are excluded). Three weekdays, three weekend days.
DAYS = ["2026_10_06", "2026_10_14", "2026_10_22", "2026_10_10", "2026_10_18", "2026_10_24"]


def weekend(ts: np.ndarray) -> np.ndarray:
    d = np.floor((np.asarray(ts) + 19800) / 86400).astype(np.int64)  # days since epoch, IST
    return (((d + 3) % 7) >= 5).astype(np.int64)                     # 1970-01-01 was a Thursday


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", nargs="+", default=DAYS)
    ap.add_argument("--sample", type=float, default=10.0, help="percent of traversals to sample")
    ap.add_argument("--grid", default="grid_oct_all.parquet", help="the grid the live API uses")
    ap.add_argument("--out", default="pulse_baseline.json", help="file name under data/processed/model")
    a = ap.parse_args()
    t0 = time.time()
    grid = LinkGrid(MODEL / a.grid, methods=("gbm",))
    files = ", ".join(f"'{(WORK / 'links' / f'day={d}.parquet').as_posix()}'" for d in a.days)
    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")
    con.execute("SET memory_limit='1GB'")
    L = con.execute(f"SELECT route_id, ord, t, tt_s FROM read_parquet([{files}]) "
                    f"USING SAMPLE {a.sample} PERCENT (bernoulli, 7)").fetchnumpy()
    idx = grid.index(np.asarray(L["route_id"]), np.asarray(L["ord"]))
    tt = np.asarray(L["tt_s"], np.float64)
    t = np.asarray(L["t"], np.float64)
    ok = (idx >= 0) & (tt >= 5) & (tt <= 1800)        # the live engine keeps crossings 5 s to 30 min apart
    idx, tt, t = idx[ok], tt[ok], t[ok]
    we = weekend(t)
    r = np.log(tt) - grid.log_tt("gbm", idx, we, t)
    hour = (((t + 19800) % 86400) // 3600).astype(np.int64)
    out = {"days": a.days, "sample_pct": a.sample, "grid": a.grid, "n": int(len(r)),
           "note": "median of ln(observed stretch time) - ln(model time), by IST hour; see scripts/build_pulse_baseline.py"}
    for name, flag in (("weekday", 0), ("weekend", 1)):
        med, cnt = [], []
        for h in range(24):
            m = (we == flag) & (hour == h)
            cnt.append(int(m.sum()))
            med.append(round(float(np.median(r[m])), 4) if m.sum() >= 200 else None)
        # hours with too few traversals borrow the day type's overall median
        overall = float(np.median(r[we == flag])) if (we == flag).any() else 0.0
        out[name] = {"median_r": [round(overall, 4) if v is None else v for v in med], "n": cnt, "overall_median_r": round(overall, 4)}
    (MODEL / a.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"{len(r):,} traversals in {time.time() - t0:.0f} s")
    for name in ("weekday", "weekend"):
        v = out[name]["median_r"]
        print(f"{name}: overall median r {out[name]['overall_median_r']:+.3f} (x{np.exp(out[name]['overall_median_r']):.3f});"
              f" 08:00 {v[8]:+.3f}, 13:00 {v[13]:+.3f}, 19:00 {v[19]:+.3f}, 23:00 {v[23]:+.3f}")


if __name__ == "__main__":
    main()
