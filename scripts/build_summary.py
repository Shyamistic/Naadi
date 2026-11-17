"""Calibrated journey-time ranges (split conformal) and the public accuracy summary.

Intervals: on calibration days, r = ln(actual / predicted) for Naadi's door-to-door predictions, by band of
predicted time. The 80% range uses the finite-sample conformal quantiles of r at 10% and 90%; coverage is then
checked on separate test days. Written to data/processed/model/intervals.json.
Summary: validation/results/summary.json (served at /accuracy).
Usage: python scripts/build_summary.py --journeys journeys_oct --calib 2026_10_26 2026_10_27 2026_10_28
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "validation" / "results"
BANDS = [30, 60, 90, 1e9]
NAMES = {"timetable": "Official timetable", "city": "City speed curve", "ha": "Historical average", "eb": "Empirical-Bayes history",
         "gbm": "Naadi history only", "persist": "Bus's own recent speed", "live_only": "Live only (30 min)",
         "naadi": "Naadi (history + live)"}


def conformal(r: np.ndarray, lo=0.1, hi=0.9):
    n = len(r)
    s = np.sort(r)
    k_lo = max(0, math.floor((n + 1) * lo) - 1)
    k_hi = min(n - 1, math.ceil((n + 1) * hi) - 1)
    return float(s[k_lo]), float(s[k_hi])


def intervals(t: dict, planner: str, calib: set[str]):
    m = (np.array(t["planner"]) == planner) & (np.array(t["status"]) == "ok")
    pred = np.array(t["pred_s"], dtype=float)[m]
    act = np.array(t["actual_s"], dtype=float)[m]
    day = np.array(t["day"])[m]
    r = np.log(act / pred)
    cal = np.isin(day, list(calib))
    bands, prev = [], 0
    cover_n = cover_k = 0
    for b in BANDS:
        sel = (pred / 60 > prev) & (pred / 60 <= b)
        rc = r[sel & cal]
        if len(rc) < 30:
            rc = r[cal]
        q_lo, q_hi = conformal(rc)
        tst = sel & ~cal
        cover_k += int(np.sum((r[tst] >= q_lo) & (r[tst] <= q_hi)))
        cover_n += int(tst.sum())
        bands.append({"max_min": b if b < 1e9 else 9999, "q_lo": q_lo, "q_hi": q_hi, "n_calib": int((sel & cal).sum())})
        prev = b
    return {"bands": bands, "nominal": 0.8, "test_coverage": cover_k / max(1, cover_n), "n_test": cover_n}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--journeys", default="journeys_oct")
    ap.add_argument("--calib", nargs="+", default=["2026_10_26", "2026_10_27", "2026_10_28"])
    a = ap.parse_args()
    t = pq.read_table(RES / f"{a.journeys}.parquet").to_pydict()
    iv = {"history": intervals(t, "naadi", set(a.calib))}
    if "naadi_live" in set(t["planner"]):
        iv["live"] = intervals(t, "naadi_live", set(a.calib))
    (ROOT / "data" / "processed" / "model" / "intervals.json").write_text(json.dumps(iv, indent=1))
    eta = json.loads((RES / "eta_oct.json").read_text())
    rows = sorted(((NAMES[m], v["mae_s"]) for m, v in eta["raw"].items()), key=lambda x: -x[1])
    js = json.loads((RES / f"{a.journeys}.json").read_text())
    lines = []
    if "naadi" in js and "timetable" in js:
        n, tt = js["naadi"], js["timetable"]
        lines.append(f"Door to door, replayed on the buses that really ran ({n['n_ok']:,} journeys on held-out days): Naadi's "
                     f"predicted time was off by {n['mae_min']:.1f} min on average; a planner using the official timetable "
                     f"was off by {tt['mae_min']:.1f} min.")
        if "naadi_live" in js:
            lines.append(f"With the live nowcast: {js['naadi_live']['mae_min']:.1f} min.")
    for k, v in iv.items():
        lines.append(f"80% range ({k}): actual time fell inside it for {100 * v['test_coverage']:.0f}% of {v['n_test']:,} test journeys.")
    calc = RES / "eta_calculator_nov.json"
    out = {"updated": dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).isoformat(timespec="minutes"),
           "eta": {"caption": f"Mean absolute error predicting when a bus reaches a stop 1 to 30 stops ahead "
                              f"({eta['n_cases']:,} predictions, held-out days 26 to 31 Oct 2026). Lower is better.", "rows": rows},
           "journeys": {"lines": lines, "summary": js}, "intervals": iv}
    if calc.exists():
        out["eta_calculator"] = json.loads(calc.read_text())
    g = RES / "google_nov.json"
    if g.exists():
        out["google"] = json.loads(g.read_text())
    (RES / "summary.json").write_text(json.dumps(out, indent=1))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
