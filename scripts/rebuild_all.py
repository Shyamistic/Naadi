"""Rebuild everything downstream of L1 in order (after a pipeline fix). Logs to data/rebuild.log.

Steps: live days -> L1, L2 for live days, links/passages for all days, model tables, service tables,
link model (train + grids), networks, held-out ETA evaluation.
Usage: python -u scripts/rebuild_all.py [--from-step N]
"""
from __future__ import annotations

import argparse
import datetime as dt
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def live_days() -> list[str]:
    d, today, out = dt.date(2026, 11, 15), dt.datetime.now(IST).date(), []
    while d < today:
        out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def steps() -> list[tuple[str, list[str], Path]]:
    ld = live_days()
    lu = [d.replace("-", "_") for d in ld]
    s = [("ingest live", [PY, "-u", "ingest_live.py", "--force", "--days", *ld], ROOT / "scripts"),
         ("match live", [PY, "-u", "scripts/match_routes.py", "--days", *lu], ROOT),
         ("links all days", [PY, "-u", "scripts/build_speed_tables.py", "--force"], ROOT)]
    for name, a, b in (("oct01_17", "2026_10_01", "2026_10_17"), ("oct01_24", "2026_10_01", "2026_10_24"),
                       ("oct_all", "2026_10_01", "2026_10_31")):
        s.append((f"tables {name}", [PY, "-u", "scripts/model_tables.py", "--name", name, "--from", a, "--to", b], ROOT))
    for name, a, b in (("oct01_24", "2026_10_01", "2026_10_24"), ("oct_all", "2026_10_01", "2026_10_31")):
        s.append((f"service {name}", [PY, "-u", "scripts/build_service.py", "--name", name, "--from", a, "--to", b], ROOT))
    s += [("train", [PY, "-u", "scripts/link_model.py", "train"], ROOT),
          ("grid eval", [PY, "-u", "scripts/link_model.py", "grid", "--tables", "oct01_24"], ROOT),
          ("grid prod", [PY, "-u", "scripts/link_model.py", "grid", "--tables", "oct_all"], ROOT),
          ("network eval", [PY, "-u", "scripts/build_network.py", "--grid", "grid_oct01_24", "--service", "service_oct01_24", "--name", "eval_oct"], ROOT),
          ("network prod", [PY, "-u", "scripts/build_network.py", "--grid", "grid_oct_all", "--service", "service_oct_all", "--name", "prod"], ROOT),
          ("network prod + metro", [PY, "-u", "scripts/build_multimodal.py", "--bus", "network_prod", "--name", "prod_mm"], ROOT),
          ("eval eta", [PY, "-u", "scripts/eval_eta.py"], ROOT)]
    return s


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-step", type=int, default=0)
    a = ap.parse_args()
    log = (ROOT / "data" / "rebuild.log").open("a", encoding="utf-8")
    st = steps()
    if a.from_step <= 1:  # L2 for live days must be redone because L1 changed
        for d in live_days():
            for f in (ROOT / "data" / "processed" / "gps_l2").glob(f"day={d.replace('-', '_')}.parquet"):
                f.unlink()
            for f in (ROOT / "data" / "processed" / "gps_l2" / "_stats").glob(f"day={d.replace('-', '_')}.json"):
                f.unlink()
    for i, (name, cmd, cwd) in enumerate(st):
        if i < a.from_step:
            continue
        log.write(f"\n=== [{i}] {name} {dt.datetime.now(IST):%H:%M:%S}\n")
        log.flush()
        r = subprocess.run(cmd, cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
        if r.returncode != 0:
            log.write(f"FAILED step {i} ({name}) rc={r.returncode}\n")
            sys.exit(r.returncode)
    shutil.rmtree(ROOT / "data" / "tmp_duckdb", ignore_errors=True)
    log.write(f"\n=== ALL DONE {dt.datetime.now(IST):%H:%M:%S}\n")


if __name__ == "__main__":
    main()
