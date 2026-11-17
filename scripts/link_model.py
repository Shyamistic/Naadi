"""Link travel-time model: features, LightGBM training and the hour-by-hour prediction grid.

Target: stop-to-stop travel time (s) of one bus on one link (route_id, ord); gamma objective, so the model\npredicts the MEAN time. Means add up along a ride, medians do not (sums of medians run ~100 s short).
Features come only from historical tables built on EARLIER days (no leakage):
  link-hour, link all-hours, neighbouring hours, stop pair (all routes), road cell x heading,
  city curve, geometry, plus an empirical-Bayes estimate that shrinks each level into the next.

Outputs (data/processed/model/):
  link_gbm.txt                LightGBM model (trained on Oct 18-23 with oct01_17 tables, early stop on Oct 24)
  grid_<tables>.parquet       per link x hour x day type: log-time predictions of every method + sd
Methods in the grid:
  tt   official timetable (straight-line distance at the GTFS constant 18.01 km/h)
  city city-wide speed curve by hour (pace x distance)
  ha   historical median for the link-hour, falling back to link all-hours, then city
  eb   empirical-Bayes hierarchy (link-hour <- link all-hours shifted by hour <- road cell <- city)
  gbm  LightGBM on all features (Naadi historical model)

Usage:
  python scripts/link_model.py train
  python scripts/link_model.py grid --tables oct01_24
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import duckdb
import lightgbm as lgb
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "data" / "processed" / "speed_tables" / "_work"
GTFS = ROOT / "data" / "processed" / "gtfs_fixed" / "bus_v1-2"
MODEL = ROOT / "data" / "processed" / "model"
TABLES = MODEL / "tables"
TMP = ROOT / "data" / "tmp_duckdb"
K1, K2, K3 = 5.0, 20.0, 10.0  # shrinkage strengths (link-hour, link-all, cell)
TT_KMH = 18.01

FEATURES = ["log_dist", "hour", "we", "ord", "hd", "gy", "gx",
            "lh_n", "lh_mean", "lh_sd", "lh_med", "lp_n", "lp_mean", "ln_n", "ln_mean",
            "la_n", "la_mean", "la_sd", "pr_n", "pr_mean", "ce_n", "ce_mean", "ce_sd", "ci_mean", "eb", "ha", "tt"]


def connect() -> duckdb.DuckDBPyConnection:
    TMP.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"SET TimeZone='UTC'; SET memory_limit='5GB'; SET threads=8; SET temp_directory='{TMP.as_posix()}'; "
                "SET max_temp_directory_size='12GiB'; SET preserve_insertion_order=false")
    return con


def feature_sql(tables: str, base: str) -> str:
    """base must provide route_id, ord, hour, we (and anything else to carry through)."""
    T = TABLES / tables
    r = lambda n: f"read_parquet('{(T / f'{n}.parquet').as_posix()}')"
    return f"""
    WITH g AS (
        SELECT *, ln(dist_m / 1000.0) AS ldk,
               6371000 * 2 * asin(sqrt(pow(sin(radians(lat2 - lat1) / 2), 2) +
                    cos(radians(lat1)) * cos(radians(lat2)) * pow(sin(radians(lon2 - lon1) / 2), 2))) AS crow_m
        FROM {r('geom')}
    ), ca AS (SELECT sum(n * lpace_mean) / sum(n) AS m FROM {r('city_h')}),
    b AS (SELECT * FROM ({base}) JOIN g USING (route_id, ord))
    SELECT b.*, b.ldk AS log_dist,
           coalesce(lh.n, 0) AS lh_n, lh.ltt_mean AS lh_mean, lh.ltt_sd AS lh_sd, ln(lh.tt_med) AS lh_med,
           coalesce(lp.n, 0) AS lp_n, lp.ltt_mean AS lp_mean, coalesce(lnx.n, 0) AS ln_n, lnx.ltt_mean AS ln_mean,
           coalesce(la.n, 0) AS la_n, la.ltt_mean AS la_mean, la.ltt_sd AS la_sd,
           coalesce(pr.n, 0) AS pr_n, pr.ltt_mean AS pr_mean,
           coalesce(ce.n, 0) AS ce_n, ce.lpace_mean + b.ldk AS ce_mean, ce.lpace_sd AS ce_sd,
           ci.lpace_mean + b.ldk AS ci_mean,
           ln(greatest(b.crow_m, 20) / ({TT_KMH} / 3.6)) AS tt,
           coalesce(ln(lh.tt_med), ln(la.tt_med) + ci.lpace_mean - ca.m, ci.lpace_mean + b.ldk) AS ha,
           -- empirical Bayes: city -> cell -> link all-hours (shifted to this hour) -> link-hour
           (coalesce(ce.n, 0) * coalesce(ce.lpace_mean + b.ldk, 0) + {K3} * (ci.lpace_mean + b.ldk)) / (coalesce(ce.n, 0) + {K3}) AS p1,
           (coalesce(la.n, 0) * coalesce(la.ltt_mean + ci.lpace_mean - ca.m, 0)
              + {K2} * ((coalesce(ce.n, 0) * coalesce(ce.lpace_mean + b.ldk, 0) + {K3} * (ci.lpace_mean + b.ldk)) / (coalesce(ce.n, 0) + {K3})))
              / (coalesce(la.n, 0) + {K2}) AS p2
    FROM b
    CROSS JOIN ca
    LEFT JOIN {r('link_h')} lh ON lh.route_id = b.route_id AND lh.ord = b.ord AND lh.hour = b.hour AND lh.we = b.we
    LEFT JOIN {r('link_h')} lp ON lp.route_id = b.route_id AND lp.ord = b.ord AND lp.hour = (b.hour + 23) % 24 AND lp.we = b.we
    LEFT JOIN {r('link_h')} lnx ON lnx.route_id = b.route_id AND lnx.ord = b.ord AND lnx.hour = (b.hour + 1) % 24 AND lnx.we = b.we
    LEFT JOIN {r('link_a')} la ON la.route_id = b.route_id AND la.ord = b.ord
    LEFT JOIN {r('pair_h')} pr ON pr.from_stop = b.from_stop AND pr.to_stop = b.to_stop AND pr.hour = b.hour AND pr.we = b.we
    LEFT JOIN {r('cell_h')} ce ON ce.gy = b.gy AND ce.gx = b.gx AND ce.hd = b.hd AND ce.hour = b.hour AND ce.we = b.we
    LEFT JOIN {r('city_h')} ci ON ci.hour = b.hour AND ci.we = b.we
    """


def finish(con, sql: str) -> dict:
    """Run the feature query, add eb, return numpy columns."""
    d = con.execute(f"SELECT *, (lh_n * coalesce(lh_mean, 0) + {K1} * p2) / (lh_n + {K1}) AS eb FROM ({sql})").fetchnumpy()
    return {k: (np.asarray(v.filled(np.nan) if hasattr(v, "filled") else v)) for k, v in d.items()}


def matrix(d: dict) -> np.ndarray:
    return np.column_stack([np.asarray(d[f], dtype=np.float32) for f in FEATURES])


def traversals(days: list[str], sample: float | None) -> str:
    files = ", ".join(f"'{(WORK / 'links' / f'day={d}.parquet').as_posix()}'" for d in days)
    s = f"USING SAMPLE {sample * 100:.4f} PERCENT (bernoulli, 7)" if sample else ""
    return (f"SELECT route_id, ord, CAST(hour AS INTEGER) AS hour, (daytype = 'weekend')::INTEGER AS we, "
            f"ln(tt_s) AS y, tt_s, t FROM read_parquet([{files}]) {s}")


def days(a: str, b: str) -> list[str]:
    return sorted(p.stem.split("=")[1] for p in (WORK / "links").glob("day=*.parquet") if a <= p.stem.split("=")[1] <= b)


def train() -> None:
    con = connect()
    t0 = time.time()
    tr = finish(con, feature_sql("oct01_17", traversals(days("2026_10_18", "2026_10_23"), 0.45)))
    va = finish(con, feature_sql("oct01_17", traversals(["2026_10_24"], 0.5)))
    print(f"features: train {len(tr['y']):,} valid {len(va['y']):,} rows in {time.time() - t0:.0f}s", flush=True)
    Xtr, Xva = matrix(tr), matrix(va)
    params = dict(objective="gamma", learning_rate=0.05, num_leaves=255, min_data_in_leaf=200,
                  feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1, lambda_l2=1.0, num_threads=12,
                  verbose=-1, max_bin=255)
    dtr = lgb.Dataset(Xtr, tr["tt_s"], feature_name=FEATURES, categorical_feature=["hd", "we"], free_raw_data=True)
    dva = lgb.Dataset(Xva, va["tt_s"], reference=dtr)
    m = lgb.train(params, dtr, num_boost_round=3000, valid_sets=[dva], valid_names=["oct24"],
                  callbacks=[lgb.early_stopping(100, verbose=False), lgb.log_evaluation(250)])
    MODEL.mkdir(parents=True, exist_ok=True)
    m.save_model(str(MODEL / "link_gbm.txt"), num_iteration=m.best_iteration)
    p = np.log(m.predict(Xva, num_iteration=m.best_iteration))
    ytt = va["tt_s"]
    rep = {"best_iteration": m.best_iteration, "train_rows": int(len(tr["y"])), "valid_rows": int(len(va["y"])),
           "valid_mae_s": {k: float(np.nanmean(np.abs(np.exp(va[k]) - ytt))) for k in ("tt", "ha", "eb")}}
    rep["valid_mae_s"]["gbm"] = float(np.mean(np.abs(np.exp(p) - ytt)))
    imp = m.feature_importance("gain")
    rep["importance"] = {f: round(float(g / imp.sum()), 4) for f, g in sorted(zip(FEATURES, imp), key=lambda x: -x[1])}
    (MODEL / "link_gbm_train.json").write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep["valid_mae_s"]), "iters", m.best_iteration, f"{time.time() - t0:.0f}s", flush=True)


def grid(tables: str) -> None:
    con = connect()
    m = lgb.Booster(model_file=str(MODEL / "link_gbm.txt"))
    base = (f"SELECT route_id, ord, h.hour, w.we FROM read_parquet('{(TABLES / tables / 'geom.parquet').as_posix()}') "
            f"CROSS JOIN (SELECT range AS hour FROM range(24)) h CROSS JOIN (SELECT range AS we FROM range(2)) w")
    d = finish(con, feature_sql(tables, base))
    gbm = np.log(m.predict(matrix(d), num_threads=12))  # model predicts mean seconds
    # spread for intervals: link-hour log-sd shrunk towards the cell sd
    sd = np.where(d["lh_n"] >= 5, np.nan_to_num(d["lh_sd"], nan=0.35), np.nan_to_num(d["ce_sd"], nan=0.35))
    sd = (d["lh_n"] * np.nan_to_num(d["lh_sd"], nan=0.35) + 10 * np.nan_to_num(d["ce_sd"], nan=0.35)) / (d["lh_n"] + 10)
    out = MODEL / f"grid_{tables}.parquet"
    cols = {"route_id": d["route_id"].astype(np.int32), "ord": d["ord"].astype(np.int32), "hour": d["hour"].astype(np.int8),
            "we": d["we"].astype(np.int8), "dist_m": d["dist_m"].astype(np.float32), "n": d["lh_n"].astype(np.int32),
            "tt": d["tt"].astype(np.float32), "city": d["ci_mean"].astype(np.float32), "ha": d["ha"].astype(np.float32),
            "eb": d["eb"].astype(np.float32), "gbm": gbm.astype(np.float32), "sd": sd.astype(np.float32)}
    import pyarrow as pa
    import pyarrow.parquet as pq
    pq.write_table(pa.table(cols), out, compression="zstd")
    print(f"grid {tables}: {len(gbm):,} rows -> {out.name}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["train", "grid"])
    ap.add_argument("--tables", default="oct01_24")
    a = ap.parse_args()
    train() if a.cmd == "train" else grid(a.tables)
