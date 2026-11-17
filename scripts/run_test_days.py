"""Run recorded live days (test data) through the pipeline: S3 -> L1 -> L2 -> stop passages and links.

Usage: .venv\\Scripts\\python.exe -u scripts\\run_test_days.py 2026-11-16 [2026-11-17 ...]
With no days: every recorded day up to yesterday (IST). Appends to data/test_days.log.
"""
from __future__ import annotations

import datetime as dt
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def main() -> None:
    days = sys.argv[1:]
    if not days:
        d, today = dt.date(2026, 11, 15), dt.datetime.now(IST).date()
        while d < today:
            days.append(d.isoformat())
            d += dt.timedelta(days=1)
    under = [d.replace("-", "_") for d in days]
    with (ROOT / "data" / "test_days.log").open("a", encoding="utf-8") as log:
        log.write(f"{dt.datetime.now(IST):%Y-%m-%d %H:%M:%S} start {' '.join(days)}\n")
        log.flush()
        steps = [([PY, "-u", "ingest_live.py", "--days", *days], ROOT / "scripts"),
                 ([PY, "-u", "scripts/match_routes.py", "--days", *under], ROOT),
                 ([PY, "-u", "scripts/build_speed_tables.py", "--days", *under], ROOT)]
        for cmd, cwd in steps:
            r = subprocess.run(cmd, cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
            log.flush()
            if r.returncode != 0:
                log.write(f"step failed ({r.returncode}): {' '.join(cmd[1:3])}\n")
                sys.exit(r.returncode)
        log.write(f"{dt.datetime.now(IST):%Y-%m-%d %H:%M:%S} done\n")


if __name__ == "__main__":
    main()
