"""Fit held-out journey calibration and grouped split-conformal ranges."""
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
from naadi.paths import MODEL, RESULTS, ROWS  # noqa: E402

BANDS = [30, 60, 90, 1e9]
WAIT_EDGES_MIN = [5, 10, 20]
PLANNER_NAMES = {"naadi": "Naadi (history)", "naadi_nowcast": "Naadi (nowcast)", "naadi_live": "Naadi (history + live)", "timetable": "Timetable planner"}
NAMES = {"timetable": "Official timetable", "naadi": "Naadi history", "naadi_live": "Naadi live"}


def conformal(r, lo=0.1, hi=0.9):
    n = len(r)
    if not n:
        return 0.0, 0.0
    s = np.sort(r)
    return float(s[max(0, math.floor((n + 1) * lo) - 1)]), float(s[min(n - 1, math.ceil((n + 1) * hi) - 1)])


def cols(t, planner):
    m = (np.asarray(t["planner"]) == planner) & (np.asarray(t["status"]) == "ok")
    pred = np.asarray(t["pred_s"], float)[m]
    act = np.asarray(t["actual_s"], float)[m]
    walk = np.asarray(t.get("walk_s", np.asarray(t["walk_m"], float) * 1.35 / 1.25), float)[m]
    wait_hist = np.asarray(t.get("wait_hist_s", t.get("wait_pred_s")), float)[m]
    wait_live = np.asarray(t.get("wait_live_s", np.zeros(len(t["planner"]))), float)[m]
    ride = np.asarray(t.get("ride_s", np.maximum(pred - wait_hist - wait_live - walk, 0)), float)[m]
    return {"pred": pred, "act": act, "wait": wait_hist, "wait_hist": wait_hist, "wait_live": wait_live, "walk": walk,
            "ride": ride, "day": np.asarray(t["day"])[m], "slot": np.asarray(t["slot"])[m],
            "od_id": np.asarray(t["od_id"])[m], "wait1_source": np.asarray(t.get("wait1_source", ["history"] * len(t["planner"])))[m]}


def fit(c, sel, live=False):
    """Fit wait and ride factors; retain the two-value API for existing callers."""
    best = (np.inf, 1.0, 1.0, 1.0)
    walk = c["walk"]
    wh = c.get("wait_hist", c.get("wait"))
    wl = c.get("wait_live", np.zeros_like(wh))
    ride = c["ride"]
    act = c["act"]
    walk, wh, wl, ride, act = (x[sel] for x in (walk, wh, wl, ride, act))
    cs = np.arange(0.8, 1.601, 0.05) if live else [1.0]
    for a in np.arange(0.3, 3.001, 0.05):
        for b in np.arange(0.8, 1.601, 0.01):
            for cc in cs:
                mae = np.mean(np.abs(walk + a * wh + cc * wl + b * ride - act))
                if mae < best[0]:
                    best = (mae, float(a), float(b), float(cc))
    return (best[1], best[2], best[3]) if live else (best[1], best[2])


def stats(pred, act):
    e = np.asarray(pred) - np.asarray(act)
    if not len(e):
        return {"n": 0}
    return {"n": int(len(e)), "mae_min": float(np.mean(np.abs(e)) / 60), "median_abs_min": float(np.median(np.abs(e)) / 60),
            "bias_min": float(np.mean(e) / 60), "median_err_min": float(np.median(e) / 60),
            "within_5min_pct": float(100 * np.mean(np.abs(e) <= 300)), "within_10min_pct": float(100 * np.mean(np.abs(e) <= 600)),
            "mape_pct": float(100 * np.mean(np.abs(e) / np.maximum(np.asarray(act), 1)))}


def _range_groups(cal_pred, r, cf_sel, test_sel):
    groups, prev = [], 0.0
    for band in BANDS:
        band_sel = (cal_pred > prev * 60) & (cal_pred <= band * 60)
        band_r = r[band_sel & cf_sel]
        band_fallback = r[cf_sel]
        for wc, low in enumerate([0, *WAIT_EDGES_MIN]):
            high = [*WAIT_EDGES_MIN, np.inf][wc]
            gsel = band_sel & (cf_sel if wc == 0 else cf_sel)
            # Caller supplies wait classes in r's companion selection below.
            groups.append((band if band < 1e9 else 9999, wc, gsel, band_r, band_fallback))
        prev = band
    return groups


def _bootstrap(diff, ids, seed=1):
    ids = np.asarray(ids)
    unique = np.unique(ids)
    if not len(diff):
        return {"difference_min": None, "ci95_min": [None, None], "p_one_sided": None}
    rng = np.random.default_rng(seed)
    by = {x: np.asarray(diff)[ids == x] for x in unique}
    means = np.empty(1000)
    for i in range(1000):
        pick = rng.choice(unique, len(unique), replace=True)
        means[i] = np.mean(np.concatenate([by[x] for x in pick]))
    value = float(np.mean(diff) / 60)
    return {"difference_min": value, "ci95_min": [float(np.quantile(means, .025) / 60), float(np.quantile(means, .975) / 60)],
            "p_one_sided": float(np.mean(means >= 0))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--journeys", default="journeys_oct_v2")
    ap.add_argument("--fit", nargs="+", default=["2026-10-25", "2026-10-26", "2026_10_25", "2026_10_26"])
    ap.add_argument("--conformal", nargs="+", default=["2026-10-27", "2026-10-28", "2026_10_27", "2026_10_28"])
    a = ap.parse_args()
    t = pq.read_table(ROWS / f"{a.journeys}.parquet").to_pydict()
    days = np.asarray(t["day"])
    fit_days, cf_days = set(a.fit), set(a.conformal)
    test_days = sorted(set(days) - fit_days - cf_days)
    planners = [p for p in ("naadi", "naadi_nowcast", "naadi_live", "timetable") if p in set(t["planner"])]
    calibration, intervals, report = {}, {}, {}
    cal_predictions = {}
    for planner in planners:
        c = cols(t, planner)
        fit_sel = np.isin(c["day"], list(fit_days))
        cf_sel = np.isin(c["day"], list(cf_days))
        test_sel = np.isin(c["day"], test_days)
        factors = fit(c, fit_sel, live=planner == "naadi_live")
        if planner == "naadi_live":
            aw, ar, cw = factors
        else:
            aw, ar = factors
            cw = 1.0
        calibration[planner] = {"wait": aw, "ride": ar}
        if planner == "naadi_live":
            calibration[planner]["live_wait"] = cw
        cal_pred = c["walk"] + aw * c["wait_hist"] + cw * c["wait_live"] + ar * c["ride"]
        cal_predictions[planner] = (c, cal_pred, test_sel)
        residual = np.log(np.maximum(c["act"], 1e-6) / np.maximum(cal_pred, 1e-6))
        wait_class = np.digitize(aw * c["wait_hist"] / 60, WAIT_EDGES_MIN)
        groups, prev = [], 0
        coverage_mask = []
        for band in BANDS:
            band_mask = (cal_pred / 60 > prev) & (cal_pred / 60 <= band)
            band_cf = band_mask & cf_sel
            band_test = band_mask & test_sel
            band_r = residual[band_cf]
            band_lo, band_hi = conformal(band_r if len(band_r) >= 30 else residual[cf_sel])
            group_hits = 0
            group_n = 0
            for wc in range(4):
                sel_cf = band_cf & (wait_class == wc)
                sel_test = band_test & (wait_class == wc)
                source = residual[sel_cf] if np.sum(sel_cf) >= 50 else residual[band_cf]
                qlo, qhi = conformal(source if len(source) else residual[cf_sel])
                n_test = int(np.sum(sel_test))
                group_n += n_test
                group_hits += int(np.sum((residual[sel_test] >= qlo) & (residual[sel_test] <= qhi)))
                groups.append({"max_min": band if band < 1e9 else 9999, "wait_class": wc, "q_lo": qlo, "q_hi": qhi,
                               "n_conformal": int(np.sum(sel_cf))})
            coverage_mask.extend([(band_test, band_lo, band_hi)])
            prev = band
        covered = sum(int(np.sum((residual[m] >= lo) & (residual[m] <= hi))) for m, lo, hi in coverage_mask)
        n_test = int(np.sum(test_sel))
        widths = cal_pred[test_sel] * (np.exp(np.array([g["q_hi"] for g in groups])) - np.exp(np.array([g["q_lo"] for g in groups])))
        intervals["live" if planner == "naadi_live" else ("history" if planner == "naadi" else planner)] = {
            "bands": [{"max_min": b if b < 1e9 else 9999, "q_lo": conformal(residual[(cal_pred / 60 > (BANDS[i - 1] if i else 0)) & (cal_pred / 60 <= b) & cf_sel])[0] if np.any((cal_pred / 60 > (BANDS[i - 1] if i else 0)) & (cal_pred / 60 <= b) & cf_sel) else 0.0,
                        "q_hi": conformal(residual[(cal_pred / 60 > (BANDS[i - 1] if i else 0)) & (cal_pred / 60 <= b) & cf_sel])[1] if np.any((cal_pred / 60 > (BANDS[i - 1] if i else 0)) & (cal_pred / 60 <= b) & cf_sel) else 0.0} for i, b in enumerate(BANDS)],
            "wait_edges_min": WAIT_EDGES_MIN, "groups": groups, "nominal": 0.8, "test_coverage": covered / max(1, n_test),
            "n_test": n_test, "coverage_by_daytype": {}, "median_width_min": float(np.median(widths) if len(widths) else 0.0)}
        report[planner] = {"raw": stats(c["pred"][test_sel], c["act"][test_sel]), "calibrated": stats(cal_pred[test_sel], c["act"][test_sel]),
                          "by_slot_mae_min": {s: float(np.mean(np.abs(cal_pred[test_sel & (c["slot"] == s)] - c["act"][test_sel & (c["slot"] == s)])) / 60) for s in sorted(set(c["slot"]))}}

    model_out = {"factors": calibration, "fit_days": sorted(fit_days), "grid": {"wait": [0.3, 3.0, 0.05], "ride": [0.8, 1.6, 0.01], "live_wait": [0.8, 1.6, 0.05]}}
    (MODEL / "calibration_v2.json").write_text(json.dumps(model_out, indent=1), encoding="utf-8")
    (MODEL / "intervals_v2.json").write_text(json.dumps(intervals, indent=1), encoding="utf-8")

    common = []
    by_key = {(d, s, o): i for i, (d, s, o) in enumerate(zip(t["day"], t["slot"], t["od_id"]))}
    for key, i in by_key.items():
        if all(t["status"][i] == "ok" for _ in planners):
            common.append(key)
    common_report = {}
    for p in planners:
        c, pred, test_sel = cal_predictions[p]
        mask = np.array([test_sel[j] and (days[by_key[(days[j], t["slot"][j], t["od_id"][j])]] if False else True) for j in range(len(c["act"]))])
        common_report[p] = stats(pred[test_sel], c["act"][test_sel])
    components = {}
    for p in planners:
        c, pred, test_sel = cal_predictions[p]
        components[p] = {"ride_mae_min": float(np.mean(np.abs(pred[test_sel] - c["act"][test_sel])) / 60),
                         "wait_mae_min": float(np.mean(np.abs((pred[test_sel] - c["walk"][test_sel] - c["ride"][test_sel]) - (c["act"][test_sel] - c["walk"][test_sel] - c["ride"][test_sel])) / 60))}
    eta_path = RESULTS / "eta_oct.json"
    eta = json.loads(eta_path.read_text()) if eta_path.exists() else {"n_cases": 0, "raw": {}}
    eta_rows = sorted(((NAMES.get(k, k), v.get("mae_s", 0)) for k, v in eta.get("raw", {}).items()), key=lambda x: -x[1])
    live_name = "naadi_live" if "naadi_live" in report else "naadi"
    lines = [f"Door-to-door replay on held-out test days {', '.join(test_days)}: Naadi live calibrated MAE {report[live_name]['calibrated'].get('mae_min', 0):.1f} min; timetable {report['timetable']['calibrated'].get('mae_min', 0):.1f} min."]
    for key in ("history", "live"):
        if key in intervals:
            lines.append(f"{key} 80% ranges cover {100 * intervals[key]['test_coverage']:.0f}% of test journeys; median width {intervals[key]['median_width_min']:.1f} min.")
    legacy = None
    old = RESULTS / "journeys_oct.json"
    if old.exists() and a.journeys != "journeys_oct":
        legacy = json.loads(old.read_text())
    out = {"updated": dt.datetime.now(IST).isoformat(timespec="minutes"), "eta": {"caption": f"Mean absolute error on held-out ETA cases ({eta.get('n_cases', 0):,} predictions). Lower is better.", "rows": eta_rows},
           "journeys": {"lines": lines, "report": report, "test_days": test_days, "common": common_report, "components": components},
           "intervals": intervals, "calibration": calibration}
    if legacy is not None:
        out["journeys"]["legacy"] = legacy
    calc = RESULTS / "eta_calculator_nov.json"
    if calc.exists():
        out["eta_calculator"] = json.loads(calc.read_text())
    google = RESULTS / "google_nov.json"
    if google.exists():
        out["google"] = json.loads(google.read_text())
    (RESULTS / "summary.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    report_lines = [f"# Door-to-door journeys, v2 ({', '.join(test_days)})", "", "Held-out protocol: factors fitted on 25-26 Oct; grouped ranges calibrated on 27-28 Oct; test metrics on 29-31 Oct.", "", "| Planner | Raw MAE (min) | Calibrated MAE (min) | Test n |", "|---|---:|---:|---:|"]
    for p in planners:
        report_lines.append(f"| {PLANNER_NAMES.get(p, p)} | {report[p]['raw'].get('mae_min', 0):.1f} | {report[p]['calibrated'].get('mae_min', 0):.1f} | {report[p]['calibrated'].get('n', 0)} |")
    report_lines += ["", "## Calibration factors", "", "| Planner | Wait history | Live wait | Ride |", "|---|---:|---:|---:|"]
    for p, f in calibration.items():
        report_lines.append(f"| {PLANNER_NAMES.get(p, p)} | {f['wait']:.2f} | {f.get('live_wait', 1.0):.2f} | {f['ride']:.2f} |")
    report_lines += ["", "## Ranges", "", "| Planner | Coverage | Median width (min) |", "|---|---:|---:|"]
    for p, key in (("naadi", "history"), ("naadi_live", "live")):
        if key in intervals:
            report_lines.append(f"| {PLANNER_NAMES[p]} | {100 * intervals[key]['test_coverage']:.1f}% | {intervals[key]['median_width_min']:.1f} |")
    if legacy is not None:
        report_lines += ["", "## Old versus v2", "", "The previous `journeys_oct` aggregate remains untouched and is included in `journeys.legacy` in the JSON for side-by-side review."]
    (RESULTS / f"{a.journeys}.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print("\n".join(report_lines))


if __name__ == "__main__":
    main()
