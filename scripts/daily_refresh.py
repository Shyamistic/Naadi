"""Daily refresh (run after midnight IST): new recorded days -> validation -> redeploy results.

1. Recorded live days not yet processed go through the pipeline (scripts/run_test_days.py).
2. Google comparison and ETA Calculator head-to-head are re-run on all recorded November days.
3. The accuracy summary is rebuilt and the artefacts are redeployed to the server.
Logs to data/daily_refresh.log. Registered as the Windows task "Naadi daily refresh".
"""
from __future__ import annotations

import datetime as dt
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def main() -> None:
    today = dt.datetime.now(IST).date()
    d, todo = dt.date(2026, 11, 15), []
    while d < today:
        if not (ROOT / "data" / "processed" / "speed_tables" / "_work" / "links" / f"day={d.isoformat().replace('-', '_')}.parquet").exists():
            todo.append(d.isoformat())
        d += dt.timedelta(days=1)
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    steps = []
    if todo:
        steps.append([PY, "-u", "scripts/run_test_days.py", *todo])
    steps += [[PY, "-u", "scripts/fetch_eta_logs.py"], [PY, "-u", "scripts/compare_google.py"],
              [PY, "-u", "scripts/score_eta_calculator.py"], [PY, "-u", "scripts/build_summary.py"],
              [PY, "-u", "infra/deploy_api.py"]]
    with (ROOT / "data" / "daily_refresh.log").open("a", encoding="utf-8") as log:
        log.write(f"\n==== {dt.datetime.now(IST):%Y-%m-%d %H:%M} new days: {todo}\n")
        for cmd in steps:
            log.write(f"--- {' '.join(cmd[2:])}\n")
            log.flush()
            r = subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, env=env)
            if r.returncode != 0:
                log.write(f"step failed rc={r.returncode}\n")
                if "run_test_days.py" in cmd[2]:
                    break


if __name__ == "__main__":
    main()
