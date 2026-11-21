"""Multi-stop bus ETA evaluation on held-out days (task: a bus is at stop i now; when will it reach stop i+h?).

Truth comes from stop passages (interpolated crossing times) of buses on held-out days.
History for every method comes only from earlier days (tables oct01_24, model trained on Oct 18-23).
  tuning day  : 2026_10_25 (nowcast parameters and per-horizon calibration)
  test days   : 2026_10_26 .. 2026_10_31
Methods:
  timetable  official GTFS times (constant 18.01 km/h straight-line)
  city       city-wide speed curve by hour (pace x distance)
  ha         historical median of each link-hour (classic historical average)
  eb         empirical-Bayes hierarchy (link-hour <- link <- road cell <- city)
  gbm        LightGBM historical model (Naadi, history only)
  persist    the bus's own speed over its last 3 stops
  live_only  mean of the last 30 min observed times on each link, else ha
  naadi      gbm + live nowcast (Naadi full model)
Outputs: validation/results/eta_oct.json and eta_oct.md (aggregates only).
"""
from __future__ import annotations

import itertools
import json
import sys
import time
import csv
import io
import urllib.request
from pathlib import Path

import duckdb
import numpy as np
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from naadi.linkgrid import LinkGrid  # noqa: E402
from naadi.nowcast import NowcastParams, ResidualIndex, correction  # noqa: E402

from naadi.paths import MODEL, RESULTS, WORK
RES = RESULTS
HORIZONS = [1, 2, 3, 5, 8, 12, 16, 20, 25, 30]
BANDS = [("1-2 stops", 1, 2), ("3-5 stops", 3, 5), ("8-12 stops", 8, 12), ("16-30 stops", 16, 30)]
TOD = [("night 00-06", 0, 6), ("morning peak 07-10", 7, 10), ("midday 11-16", 11, 16),
       ("evening peak 17-20", 17, 20), ("late 21-23", 21, 23)]
TUNE, TEST = ["2026_10_25"], [f"2026_10_{d}" for d in range(26, 32)]
METHODS = ["timetable", "city", "ha", "eb", "gbm", "persist", "live_only", "lnkf", "naadi"]
SAMPLE_PCT = 3.0
LNKF_GRID = [(q, r) for q in (0.01, 0.03, 0.1, 0.3, 1.0) for r in (0.03, 0.1, 0.3, 1.0)]
HOLIDAYS = {"2026_10_26": "Maharishi Valmiki Jayanti"}
GRAP_STAGE = {d: "I" for d in TEST}
METAR_URL = ("https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?"
             "station=VIDP&station=VIDD&data=all&year1=2026&month1=10&day1=26&"
             "year2=2026&month2=11&day2=1&tz=Asia%2FCalcutta&format=onlycomma&"
             "latlon=no&elev=no&missing=M&trace=T&direct=no&report_type=3&report_type=4")


class Ctx:
    def __init__(self, grid: LinkGrid, days: list[str]):
        self.grid = grid
        geom = pq.read_table(MODEL / "tables" / "oct01_24" / "geom.parquet").to_pydict()
        gi = grid.index(np.array(geom["route_id"]), np.array(geom["ord"]))
        cellkey = (np.array(geom["gy"], np.int64) * 100000 + np.array(geom["gx"], np.int64)) * 8 + np.array(geom["hd"])
        _, cid = np.unique(cellkey, return_inverse=True)
        self.cell = np.zeros(len(grid.route), np.int64)
        self.sd = np.zeros(len(grid.route), np.float64)
        ok = gi >= 0
        self.cell[gi[ok]] = cid[ok]
        self.sd[gi[ok]] = np.array(geom["sd1"])[ok]
        files = [f"'{(WORK / 'links' / f'day={d}.parquet').as_posix()}'" for d in days]
        L = duckdb.sql(f"SELECT route_id, ord, t, tt_s FROM read_parquet([{', '.join(files)}])").fetchnumpy()
        idx = grid.index(L["route_id"], L["ord"])
        m = idx >= 0
        idx, t, tt = idx[m], L["t"][m], L["tt_s"][m]
        we = weekend(t)
        res = np.log(tt) - grid.log_tt("gbm", idx, we, t)
        tref = float(t.min()) - 7200
        self.links = ResidualIndex(idx, t + tt, res, tref)
        self.cells = ResidualIndex(self.cell[idx], t + tt, res, tref)
        self.obs = ResidualIndex(idx, t + tt, np.log(tt), tref)


def weekend(ts) -> np.ndarray:
    d = np.floor((np.asarray(ts) + 19800) / 86400).astype(np.int64)  # days since epoch, IST
    return (((d + 3) % 7) >= 5).astype(np.int64)  # 1970-01-01 was a Thursday (dow 3, Mon=0)


def cases(days: list[str], seed: int) -> dict:
    pf = ", ".join(f"'{(WORK / 'passages' / f'day={d}.parquet').as_posix()}'" for d in days)
    hs = ", ".join(map(str, HORIZONS))
    q = f"""
        WITH p AS (SELECT k, route_id, ord, t FROM read_parquet([{pf}])),
        o AS (SELECT * FROM p USING SAMPLE {SAMPLE_PCT} PERCENT (bernoulli, {seed})),
        h AS (SELECT unnest([{hs}]) AS h)
        SELECT o.k, o.route_id, o.ord AS i, h.h, o.t AS t0, p2.t AS t1, p3.t AS tb, p3.ord AS ib
        FROM o CROSS JOIN h
        JOIN p p2 ON p2.k = o.k AND p2.route_id = o.route_id AND p2.ord = o.ord + h.h
        LEFT JOIN p p3 ON p3.k = o.k AND p3.route_id = o.route_id AND p3.ord = o.ord - 3 AND p3.t < o.t
        WHERE p2.t - o.t BETWEEN 5 * h.h AND least(1800 * h.h, 10800)
    """
    d = duckdb.sql(q).fetchnumpy()
    return {k: np.asarray(v.astype(np.float64).filled(np.nan) if hasattr(v, "filled") and v.mask.any() else (v.data if hasattr(v, "filled") else v)) for k, v in d.items()}


def predict(ctx: Ctx, c: dict, method: str, p: NowcastParams | None = None, daytype: np.ndarray | None = None,
            lnkf: tuple[float, float] | None = None) -> np.ndarray:
    g = ctx.grid
    idx0 = g.index(c["route_id"], c["i"])
    we = weekend(c["t0"]) if daytype is None else np.asarray(daytype, dtype=np.int64)
    h = c["h"].astype(np.int64)
    t0 = c["t0"].astype(np.float64)
    if method == "lnkf":
        return predict_lnkf(ctx, {**c, "t0": t0}, *(lnkf or (0.1, 0.3)), daytype=we)
    if method == "persist":
        dist = ctx.sd[idx0 + h - 1] + g.dist[idx0 + h - 1] - ctx.sd[idx0]
        prev = g.index(c["route_id"], np.nan_to_num(c["ib"], nan=1).astype(np.int64))
        v = (ctx.sd[idx0] - ctx.sd[np.maximum(prev, 0)]) / (t0 - c["tb"])
        v = np.where(np.isfinite(v) & (v > 0.3) & (prev >= 0), v, np.nan)
        fb = predict(ctx, c, "ha")
        return np.where(np.isfinite(v), dist / np.maximum(v, 0.3), fb)
    cur = t0.copy()
    for s in range(int(h.max())):
        a = s < h
        ix = np.where(a, idx0 + s, idx0)
        if method == "timetable":
            lt = g.log_tt("tt", ix, we, cur)
        elif method in ("city", "ha", "eb", "gbm"):
            lt = g.log_tt(method, ix, we, cur)
        elif method == "naadi":
            lt = g.log_tt("gbm", ix, we, cur) + correction(p, ctx.links, ctx.cells, ix, ctx.cell[ix], t0, cur)
        elif method == "live_only":
            sm, n = ctx.obs.window(ix, t0, 1800)
            lt = np.where(n > 0, sm / np.maximum(n, 1), g.log_tt("ha", ix, we, cur))
        else:
            raise ValueError(method)
        cur = np.where(a, cur + np.exp(lt), cur)
    return cur - t0


def metrics(y, p) -> dict:
    e = np.abs(p - y)
    return {"n": int(len(y)), "mae_s": float(e.mean()), "mape_pct": float(100 * np.mean(e / y)),
            "rmse_s": float(np.sqrt(np.mean((p - y) ** 2))), "p90_abs_s": float(np.quantile(e, 0.9)),
            "within_2min_pct": float(100 * np.mean(e <= 120)), "bias_s": float(np.mean(p - y))}


def lnkf_gain(q: float, r: float) -> float:
    """Steady-state log-normal Kalman gain for the published LNKF baseline."""
    return float(q / (q + r))


def predict_lnkf(ctx: Ctx, c: dict, q: float, r: float, daytype: np.ndarray | None = None) -> np.ndarray:
    """Predict with a log travel-time Kalman update from the bus's past section.

    This is the route-agnostic LNKF baseline from Achar et al. (arXiv:1904.03444)
    and Bhutani, Pachal & Achar (arXiv:2210.01655). The observation is available
    only before t0, so it does not use held-out future links.
    """
    g, n = ctx.grid, len(c["t0"])
    idx0 = g.index(c["route_id"], c["i"])
    we, t0 = (weekend(c["t0"]) if daytype is None else np.asarray(daytype, dtype=np.int64)), c["t0"].astype(np.float64)
    prev = g.index(c["route_id"], np.nan_to_num(c["ib"], nan=1).astype(np.int64))
    prior = g.log_tt("gbm", idx0, we, t0)
    prev_dist = ctx.sd[idx0] - ctx.sd[np.maximum(prev, 0)]
    observed = (t0 - c["tb"]) * g.dist[idx0] / np.maximum(prev_dist, 1.0)
    usable = np.isfinite(observed) & (observed > 1.0) & (prev >= 0)
    post = prior + lnkf_gain(q, r) * (np.log(np.maximum(observed, 1.0)) - prior)
    delta = np.where(usable, np.clip(post - prior, -1.5, 1.5), 0.0)
    cur = t0.copy()
    out = np.zeros(n, np.float64)
    h = c["h"].astype(np.int64)
    for s in range(int(h.max())):
        a = s < h
        ix = np.where(a, idx0 + s, idx0)
        lt = g.log_tt("gbm", ix, we, cur) + np.where(a, delta, 0.0)
        cur = np.where(a, cur + np.exp(lt), cur)
    return cur - t0


def calib(y, p, h) -> dict:
    """Per-horizon multiplier minimising absolute error (weighted median of y/p)."""
    out = {}
    for hh in HORIZONS:
        m = h == hh
        r, w = y[m] / p[m], p[m]
        o = np.argsort(r)
        cw = np.cumsum(w[o])
        out[hh] = float(r[o][np.searchsorted(cw, cw[-1] / 2)])
    return out


def boot_diff(y, pa, pb, cluster, reps=1000, seed=1) -> dict:
    """Paired cluster bootstrap of MAE(a) - MAE(b), resampling bus trips."""
    u, inv = np.unique(cluster, return_inverse=True)
    da = np.bincount(inv, np.abs(pa - y)), np.bincount(inv, np.abs(pb - y))
    cnt = np.bincount(inv).astype(float)
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(reps):
        s = rng.integers(0, len(u), len(u))
        diffs.append(da[0][s].sum() / cnt[s].sum() - da[1][s].sum() / cnt[s].sum())
    lo, hi = np.quantile(diffs, [0.025, 0.975])
    return {"diff_mae_s": float(np.mean(np.abs(pa - y)) - np.mean(np.abs(pb - y))), "ci95": [float(lo), float(hi)],
            "p_value_one_sided": float(np.mean(np.array(diffs) >= 0))}


def _foggy_morning_days() -> tuple[dict[str, bool], dict[str, list[dict]]]:
    """Read IEM's public METAR archive and classify visibility under 1 km."""
    fog, observations = {d: False for d in TEST}, {d: [] for d in TEST}
    try:
        with urllib.request.urlopen(METAR_URL, timeout=30) as response:
            rows = csv.DictReader(io.TextIOWrapper(response, encoding="utf-8"))
            for row in rows:
                valid = row.get("valid", "")
                day = valid[:10].replace("-", "_")
                if day not in fog or not valid[11:13].isdigit() or not 5 <= int(valid[11:13]) <= 9:
                    continue
                try:
                    vis_km = float(row.get("vsby", "nan")) * 1.609344
                except (TypeError, ValueError):
                    continue
                rec = {"station": row.get("station"), "valid": valid, "visibility_km": vis_km}
                observations[day].append(rec)
                if vis_km < 1.0:
                    fog[day] = True
    except Exception as exc:  # a failed archive must not change the held-out scores
        observations["error"] = [{"message": str(exc)}]
    return fog, observations


def _empty_metrics() -> dict:
    return {"n": 0, "mae_s": None, "mape_pct": None, "rmse_s": None,
            "p90_abs_s": None, "within_2min_pct": None, "bias_s": None}


def _metrics_if(y, pred) -> dict:
    return metrics(y, pred) if len(y) else _empty_metrics()


def _day_key(ts: np.ndarray) -> np.ndarray:
    return np.array([time.strftime("%Y_%m_%d", time.gmtime(float(x) + 19800)) for x in ts])


def _strata(c, y, pred, foggy_days):
    day = _day_key(c["t0"])
    hr = ((c["t0"] + 19800) % 86400) // 3600
    rows = {}
    for d in TEST:
        rows[d] = _metrics_if(y[day == d], pred[day == d])
    rows["holiday_2026_10_26"] = _metrics_if(y[(day == "2026_10_26")], pred[(day == "2026_10_26")])
    fog = np.array([foggy_days.get(x, False) for x in day]) & (hr >= 5) & (hr <= 9)
    rows["foggy_morning"] = _metrics_if(y[fog], pred[fog])
    rows["non_foggy_morning"] = _metrics_if(y[(hr >= 5) & (hr <= 9) & ~fog], pred[(hr >= 5) & (hr <= 9) & ~fog])
    return rows


def main() -> None:
    t_start = time.time()
    grid = LinkGrid(MODEL / "grid_oct01_24.parquet")
    # ---- tuning day
    ctx = Ctx(grid, TUNE)
    ct = cases(TUNE, 11)
    yt = ct["t1"] - ct["t0"]
    print(f"tuning cases {len(yt):,}", flush=True)
    sub = np.random.default_rng(0).random(len(yt)) < min(1.0, 120000 / len(yt))
    cs = {k: v[sub] for k, v in ct.items()}
    base_grid = ([1200, 1800, 2700], [5, 10, 20, 40], [0.5, 1, 3, 6], [9600, 1e9])
    grid_lists = [list(x) for x in base_grid]

    def tune_nowcast(lists):
        best_local = None
        for w, kl, kc, tau in itertools.product(*lists):
            candidate = NowcastParams(w, kl, kc, tau)
            mae = float(np.mean(np.abs(predict(ctx, cs, "naadi", candidate) - yt[sub])))
            if best_local is None or mae < best_local[0]:
                best_local = (mae, candidate)
        return best_local

    best = tune_nowcast(grid_lists)
    # The plan allows one extension step for every dimension that still ends at an edge.
    extensions = {0: {1200: 900, 2700: 3600}, 1: {5: 2.5, 40: 80},
                  2: {0.5: 0.25, 6: 12}}
    edge = False
    for i, values in enumerate(grid_lists[:3]):
        value = getattr(best[1], ("window_s", "k_link", "k_cell")[i])
        if value == values[0] and values[0] in extensions[i]:
            values.insert(0, extensions[i][values[0]]); edge = True
        elif value == values[-1] and values[-1] in extensions[i]:
            values.append(extensions[i][values[-1]]); edge = True
    if edge:
        best = tune_nowcast(grid_lists)
    p = best[1]
    lnkf_best = min(LNKF_GRID, key=lambda qr: float(np.mean(np.abs(
        predict(ctx, cs, "lnkf", lnkf=qr) - yt[sub]))))
    print(f"nowcast params {p} (tuning MAE {best[0]:.1f}s), LNKF q/r {lnkf_best}", flush=True)
    cal = {m: calib(yt, predict(ctx, ct, m, p, lnkf=lnkf_best), ct["h"]) for m in METHODS}
    # ---- test days
    ctx = Ctx(grid, TEST)
    c = cases(TEST, 23)
    y = c["t1"] - c["t0"]
    hr = ((c["t0"] + 19800) % 86400) // 3600
    we = weekend(c["t0"])
    day = _day_key(c["t0"])
    foggy_days, metar = _foggy_morning_days()
    print(f"test cases {len(y):,} from {len(np.unique(c['k'])):,} bus trips", flush=True)
    preds = {m: predict(ctx, c, m, p, lnkf=lnkf_best) for m in METHODS}
    holiday_we = we.copy()
    holiday_we[day == "2026_10_26"] = 1
    holiday_preds = {m: predict(ctx, c, m, p, daytype=holiday_we, lnkf=lnkf_best) for m in METHODS}
    out = {"tuning_day": TUNE, "test_days": TEST, "nowcast": p.__dict__,
           "nowcast_grid": {"window_s": grid_lists[0], "k_link": grid_lists[1],
                            "k_cell": grid_lists[2], "tau_s": grid_lists[3]},
           "nowcast_tuning_mae_s": best[0], "lnkf_noise_grid": {"q": sorted(set(q for q, _ in LNKF_GRID)),
                                                                    "r": sorted(set(r for _, r in LNKF_GRID))},
           "lnkf_noise": {"q": lnkf_best[0], "r": lnkf_best[1]},
           "n_cases": int(len(y)), "n_trips": int(len(np.unique(c["k"]))), "raw": {},
           "calibrated": {}, "by_band": {}, "by_tod": {}, "by_daytype": {}, "by_day": {},
           "by_stratum": {}, "holiday_sensitivity": {}, "by_hour": {}, "significance": {},
           "calendar": {"2026_10_26": {"label": HOLIDAYS["2026_10_26"], "gazetted_holiday": True,
                                         "model_daytype": "weekday", "sensitivity_daytype": "weekend"},
                        "grap_stage": GRAP_STAGE},
           "weather": {"source": "IEM METAR VIDP and VIDD", "url": METAR_URL,
                       "visibility_threshold_km": 1.0, "hours_ist": "05:00-09:00",
                       "foggy_days": [d for d, flag in foggy_days.items() if flag], "observations": metar}}
    for m in METHODS:
        pr = preds[m]
        pc = pr * np.array([cal[m][hh] for hh in c["h"]])
        out["raw"][m] = metrics(y, pr)
        out["calibrated"][m] = metrics(y, pc)
        out["by_band"][m] = {b: _metrics_if(y[(c["h"] >= lo) & (c["h"] <= hi)], pr[(c["h"] >= lo) & (c["h"] <= hi)])
                              for b, lo, hi in BANDS}
        out["by_tod"][m] = {b: _metrics_if(y[(hr >= lo) & (hr <= hi)], pr[(hr >= lo) & (hr <= hi)]) for b, lo, hi in TOD}
        out["by_daytype"][m] = {d: _metrics_if(y[we == i], pr[we == i]) for i, d in ((0, "weekday"), (1, "weekend"))}
        out["by_day"][m] = {d: _metrics_if(y[day == d], pr[day == d]) for d in TEST}
        out["by_stratum"][m] = _strata(c, y, pr, foggy_days)
        out["holiday_sensitivity"][m] = {"calendar": out["by_day"][m].get("2026_10_26", _empty_metrics()),
                                          "treat_26_oct_as_weekend": _metrics_if(y[day == "2026_10_26"], holiday_preds[m][day == "2026_10_26"])}
        out["by_hour"][m] = {int(h): _metrics_if(y[hr == h], pr[hr == h])["mae_s"] for h in range(24) if (hr == h).sum() > 200}
        out.setdefault("bias_by_horizon", {})[m] = {int(hh): _metrics_if(y[c["h"] == hh], pr[c["h"] == hh])["bias_s"] for hh in HORIZONS}
    horizon_bias = out["bias_by_horizon"]["naadi"]
    first_bias = horizon_bias[min(horizon_bias)]
    last_bias = horizon_bias[max(horizon_bias)]
    if abs(last_bias) > abs(first_bias):
        bias_text = "The signed Naadi bias becomes more early at longer horizons (from %.1f s at %s stops to %.1f s at %s stops). With tau at 1e9 s, the live correction does not decay; this persistent correction is a plausible mechanism for the accumulating early error." % (first_bias, min(horizon_bias), last_bias, max(horizon_bias))
    else:
        bias_text = "The signed Naadi bias does not grow in magnitude over the tested horizons (%.1f s at %s stops versus %.1f s at %s stops); the horizon table is retained so the early bias is not attributed to tau without evidence." % (first_bias, min(horizon_bias), last_bias, max(horizon_bias))
    out["bias_explanation"] = {"naadi_bias_s": out["raw"]["naadi"]["bias_s"],
                                "mean_naadi_minus_gbm_s": float(np.mean(preds["naadi"] - preds["gbm"])),
                                "by_horizon_s": horizon_bias, "interpretation": bias_text}
    base = [m for m in METHODS if m != "naadi"]
    best_base = min(base, key=lambda m: out["raw"][m]["mae_s"])
    for b in (best_base, "gbm", "ha", "timetable"):
        out["significance"][f"naadi_vs_{b}"] = boot_diff(y, preds["naadi"], preds[b], c["k"])
    out["significance"]["gbm_vs_ha"] = boot_diff(y, preds["gbm"], preds["ha"], c["k"])
    out["best_baseline"] = best_base
    out["seconds"] = round(time.time() - t_start)
    RES.mkdir(parents=True, exist_ok=True)
    (RES / "eta_oct.json").write_text(json.dumps(out, indent=1))
    names = {"timetable": "Official timetable", "city": "City speed curve", "ha": "Historical average (link-hour)",
             "eb": "Empirical-Bayes history", "gbm": "Naadi history (LightGBM)", "persist": "Bus's own recent speed",
             "live_only": "Live only (last 30 min)", "lnkf": "LNKF (published log-normal Kalman)",
             "naadi": "**Naadi (history + live nowcast)**"}
    L = ["# Bus ETA accuracy, held-out days 26 to 31 Oct 2026", "",
         f"Task: a bus is at a stop now; predict when it reaches a stop 1 to 30 stops ahead. "
         f"{len(y):,} predictions from {out['n_trips']:,} bus trips. History from 1 to 24 Oct only; nowcast "
         f"tuned on 25 Oct (window {p.window_s:.0f} s, k_link {p.k_link}, k_cell {p.k_cell}, tau {p.tau_s:.0f} s; "
         f"tuning MAE {best[0]:.1f} s). LNKF noise q={lnkf_best[0]}, r={lnkf_best[1]} was tuned on 25 Oct only.", "",
         "| Method | MAE (s) | MAPE | RMSE (s) | P90 error (s) | within 2 min | bias (s) |", "|---|---|---|---|---|---|---|"]
    for m in METHODS:
        r = out["raw"][m]
        L.append(f"| {names[m]} | {r['mae_s']:.1f} | {r['mape_pct']:.1f}% | {r['rmse_s']:.1f} | {r['p90_abs_s']:.0f} | "
                 f"{r['within_2min_pct']:.1f}% | {r['bias_s']:+.1f} |")
    L += ["", "MAE (s) by how far ahead:", "", "| Method | " + " | ".join(b for b, _, _ in BANDS) + " |",
          "|---|" + "---|" * len(BANDS)]
    for m in METHODS:
        L.append(f"| {names[m]} | " + " | ".join(f"{out['by_band'][m][b]['mae_s']:.0f}" for b, _, _ in BANDS) + " |")
    L += ["", "MAE (s) by time of day:", "", "| Method | " + " | ".join(b for b, _, _ in TOD) + " |", "|---|" + "---|" * len(TOD)]
    for m in METHODS:
        L.append(f"| {names[m]} | " + " | ".join(f"{out['by_tod'][m][b]['mae_s']:.0f}" for b, _, _ in TOD) + " |")
    L += ["", "With a per-horizon calibration factor fitted on 25 Oct for every method (fair to all):", "",
          "| Method | MAE (s) | MAPE |", "|---|---|---|"]
    for m in METHODS:
        r = out["calibrated"][m]
        L.append(f"| {names[m]} | {r['mae_s']:.1f} | {r['mape_pct']:.1f}% |")
    L += ["", "Paired cluster bootstrap over bus trips (1,000 resamples), MAE difference (negative = Naadi better):", ""]
    for k, v in out["significance"].items():
        L.append(f"- {k}: {v['diff_mae_s']:+.1f} s, 95% CI [{v['ci95'][0]:+.1f}, {v['ci95'][1]:+.1f}], "
                 f"one-sided p = {v['p_value_one_sided']:.3f}")
    L += ["", "Calendar and weather strata (Naadi raw; 26 Oct is a gazetted holiday but remains a weekday in the primary run):", "",
          "| Stratum | n | MAE (s) | bias (s) |", "|---|---:|---:|---:|"]
    for label in ["2026_10_26", "2026_10_27", "2026_10_28", "2026_10_29", "2026_10_30", "2026_10_31", "foggy_morning", "non_foggy_morning"]:
        r = out["by_stratum"]["naadi"].get(label, _empty_metrics())
        L.append(f"| {label} | {r['n']} | {r['mae_s'] if r['mae_s'] is not None else 'n/a'} | {r['bias_s'] if r['bias_s'] is not None else 'n/a'} |")
    hs = out["holiday_sensitivity"]["naadi"]
    L += ["", f"Holiday sensitivity for 26 Oct: standard weekday MAE {hs['calendar']['mae_s']:.1f} s; treating the gazetted holiday as weekend gives {hs['treat_26_oct_as_weekend']['mae_s']:.1f} s.",
          "", bias_text,
          "", "LNKF is the published log-normal Kalman baseline described by Achar et al. (arXiv:1904.03444) and Bhutani, Pachal & Achar (arXiv:2210.01655)."]
    (RES / "eta_oct.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[4:14]), flush=True)
    print(f"done in {out['seconds']} s")


if __name__ == "__main__":
    main()
