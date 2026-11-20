"""Calibration, calibrated ranges (split conformal) and the public accuracy summary.

Data: replayed journeys (scripts/eval_journeys.py) on held-out October days, split by day:
  fit days      wait and ride factors per planner, minimising mean absolute error of
                walk + a * wait + b * ride (a fair post-hoc calibration, applied to every planner)
  conformal     r = ln(actual / calibrated prediction); 80% range from finite-sample quantiles at 10% and 90%,
                by band of predicted time
  test days     everything reported (MAE before and after calibration, range coverage)
Writes data/processed/model/calibration.json, intervals.json and validation/results/summary.json (+ journeys_oct.md).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from naadi.paths import MODEL, RESULTS
RES = RESULTS
BANDS = [30, 60, 90, 1e9]
NAMES = {"timetable": "Official timetable", "city": "City speed curve", "ha": "Historical average", "eb": "Empirical-Bayes history",
         "gbm": "Naadi history only", "persist": "Bus's own recent speed", "live_only": "Live only (30 min)",
         "naadi": "Naadi (history + live)"}
PLANNER_NAMES = {"naadi": "Naadi (history)", "naadi_live": "Naadi (history + live)", "timetable": "Timetable planner"}


def conformal(r, lo=0.1, hi=0.9):
    n = len(r)
    s = np.sort(r)
    return float(s[max(0, math.floor((n + 1) * lo) - 1)]), float(s[min(n - 1, math.ceil((n + 1) * hi) - 1)])


def cols(t, planner):
    m = (np.array(t["planner"]) == planner) & (np.array(t["status"]) == "ok")
    pred = np.array(t["pred_s"], float)[m]
    act = np.array(t["actual_s"], float)[m]
    wait = np.array(t["wait_pred_s"], float)[m]
    walk = np.array(t["walk_m"], float)[m] * 1.35 / 1.25
    ride = np.maximum(pred - wait - walk, 0)
    return {"pred": pred, "act": act, "wait": wait, "walk": walk, "ride": ride, "day": np.array(t["day"])[m],
            "slot": np.array(t["slot"])[m]}


def fit(c, sel):
    best = (np.inf, 1.0, 1.0)
    for a in np.arange(0.8, 3.01, 0.05):
        base = c["walk"][sel] + a * c["wait"][sel]
        for b in np.arange(0.9, 1.41, 0.01):
            mae = np.mean(np.abs(base + b * c["ride"][sel] - c["act"][sel]))
            if mae < best[0]:
                best = (mae, float(a), float(b))
    return best[1], best[2]


def stats(pred, act):
    e = pred - act
    return {"n": int(len(e)), "mae_min": float(np.mean(np.abs(e)) / 60), "median_abs_min": float(np.median(np.abs(e)) / 60),
            "bias_min": float(np.mean(e) / 60), "median_err_min": float(np.median(e) / 60),
            "within_5min_pct": float(100 * np.mean(np.abs(e) <= 300)), "within_10min_pct": float(100 * np.mean(np.abs(e) <= 600)),
            "mape_pct": float(100 * np.mean(np.abs(e) / act))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--journeys", default="journeys_oct")
    ap.add_argument("--fit", nargs="+", default=["2026_10_25", "2026_10_26"])
    ap.add_argument("--conformal", nargs="+", default=["2026_10_27", "2026_10_28"])
    a = ap.parse_args()
    t = pq.read_table(RES / f"{a.journeys}.parquet").to_pydict()
    planners = [p for p in ("naadi", "naadi_live", "timetable") if p in set(t["planner"])]
    calib, iv, rep = {}, {}, {}
    for p in planners:
        c = cols(t, p)
        fit_sel = np.isin(c["day"], a.fit)
        cf_sel = np.isin(c["day"], a.conformal)
        test = ~fit_sel & ~cf_sel
        aw, ar = fit(c, fit_sel)
        calib[p] = {"wait": aw, "ride": ar}
        cal_pred = c["walk"] + aw * c["wait"] + ar * c["ride"]
        r = np.log(c["act"] / cal_pred)
        bands, prev, k, n = [], 0, 0, 0
        for b in BANDS:
            sel = (cal_pred / 60 > prev) & (cal_pred / 60 <= b)
            rc = r[sel & cf_sel] if (sel & cf_sel).sum() >= 30 else r[cf_sel]
            q_lo, q_hi = conformal(rc)
            k += int(np.sum((r[sel & test] >= q_lo) & (r[sel & test] <= q_hi)))
            n += int((sel & test).sum())
            bands.append({"max_min": b if b < 1e9 else 9999, "q_lo": q_lo, "q_hi": q_hi})
            prev = b
        iv["live" if p == "naadi_live" else ("history" if p == "naadi" else p)] = {"bands": bands, "nominal": 0.8,
                                                                                   "test_coverage": k / max(1, n), "n_test": n}
        rep[p] = {"raw": stats(c["pred"][test], c["act"][test]), "calibrated": stats(cal_pred[test], c["act"][test]),
                  "by_slot_mae_min": {s: float(np.mean(np.abs(cal_pred[test & (c["slot"] == s)] - c["act"][test & (c["slot"] == s)])) / 60)
                                      for s in sorted(set(c["slot"]))}}
    (MODEL / "calibration.json").write_text(json.dumps({"factors": calib, "fit_days": a.fit}, indent=1))
    (MODEL / "intervals.json").write_text(json.dumps(iv, indent=1))
    test_days = sorted(set(t["day"]) - set(a.fit) - set(a.conformal))
    L = [f"# Door-to-door journeys replayed on real buses (test days {', '.join(test_days)})", "",
         "Each planner's best journey for 190 OD pairs x 8 departure times per day, followed on the buses that actually ran. "
         f"Calibration factors fitted on {', '.join(a.fit)}; ranges calibrated on {', '.join(a.conformal)}.", "",
         "| Planner | journeys | MAE (min) | median error (min) | bias (min) | within 10 min | MAE after calibration | 80% range coverage |",
         "|---|---|---|---|---|---|---|---|"]
    for p in planners:
        k = "live" if p == "naadi_live" else ("history" if p == "naadi" else p)
        L.append(f"| {PLANNER_NAMES[p]} | {rep[p]['raw']['n']:,} | {rep[p]['raw']['mae_min']:.1f} | {rep[p]['raw']['median_abs_min']:.1f} | "
                 f"{rep[p]['raw']['bias_min']:+.1f} | {rep[p]['raw']['within_10min_pct']:.0f}% | {rep[p]['calibrated']['mae_min']:.1f} | "
                 f"{100 * iv[k]['test_coverage']:.0f}% |")
    L += ["", "Calibration factors (wait x, ride x): " + "; ".join(f"{PLANNER_NAMES[p]} {v['wait']:.2f}, {v['ride']:.2f}" for p, v in calib.items())]
    (RES / f"{a.journeys}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    eta = json.loads((RES / "eta_oct.json").read_text())
    rows = sorted(((NAMES[m], v["mae_s"]) for m, v in eta["raw"].items()), key=lambda x: -x[1])
    nn = rep.get("naadi_live", rep["naadi"])["calibrated"]
    lines = [f"Door to door, replayed on the buses that really ran on held-out days: Naadi's predicted time was off by "
             f"{nn['mae_min']:.1f} min on average (median {nn['median_abs_min']:.1f}); a timetable planner by "
             f"{rep['timetable']['calibrated']['mae_min']:.1f} min."]
    g = RES / "google_nov.json"
    out = {"updated": dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).isoformat(timespec="minutes"),
           "eta": {"caption": f"Mean absolute error predicting when a bus reaches a stop 1 to 30 stops ahead "
                              f"({eta['n_cases']:,} predictions, held-out days 26 to 31 Oct 2026). Lower is better.", "rows": rows},
           "journeys": {"lines": lines, "report": rep, "test_days": test_days}, "intervals": iv, "calibration": calib}
    calc = RES / "eta_calculator_nov.json"
    if calc.exists():
        ec = json.loads(calc.read_text())
        out["eta_calculator"] = ec
        m = ec["methods"]
        lines.append(f"Against the Transport Stack ETA Calculator on {ec['n']:,} of its own live answers: Naadi {m['Naadi history + live']['mae_min']:.1f} min "
                     f"mean error vs {m['ETA Calculator (Transport Stack)']['mae_min']:.1f} min.")
    if g.exists():
        gg = json.loads(g.read_text())
        out["google"] = gg
        if gg.get("google"):
            lines.append(f"Against Google Maps (bus only, {gg['both_replayed']} replayed trips): Google's predicted door-to-door time was off by "
                         f"{gg['google']['mae_min']:.0f} min on average, Naadi's by {gg['naadi']['mae_min']:.0f} min.")
    for k, v in iv.items():
        if k in ("history", "live"):
            lines.append(f"Naadi's 80% range ({k}) contained the actual time for {100 * v['test_coverage']:.0f}% of {v['n_test']:,} test journeys.")
    (RES / "summary.json").write_text(json.dumps(out, indent=1))
    print("\n".join(L))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
