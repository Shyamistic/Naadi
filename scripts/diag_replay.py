"""Diagnostic: split replay error of direct (one-bus) journeys into wait and ride parts."""
from __future__ import annotations

import csv
import datetime as dt
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from naadi.network import MODEL, Network  # noqa: E402
from naadi.replay import DayPassages  # noqa: E402
from naadi.router import Planner  # noqa: E402
from naadi.strategy import best_journey  # noqa: E402

day = sys.argv[1] if len(sys.argv) > 1 else "2026_10_27"
net = Network(MODEL / "network_eval_oct")
pl = Planner(net, "naadi")
dp = DayPassages(day)
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
od = list(csv.DictReader(open(ROOT / "validation" / "od_set.csv", encoding="utf-8")))
y, m, d = map(int, day.split("_"))
pw, aw, pr, ar, na, aw1 = [], [], [], [], [], []
for slot in ("08:30", "13:00", "18:00", "22:30"):
    hh, mm = map(int, slot.split(":"))
    t = dt.datetime(y, m, d, hh, mm, tzinfo=IST).timestamp()
    for r in od[30:130]:
        j = best_journey(pl, (float(r["o_lat"]), float(r["o_lon"])), (float(r["d_lat"]), float(r["d_lon"])), t)
        if j is None or j.n_bus != 1:
            continue
        tt = t
        for l in j.legs:
            if l.kind == "walk":
                tt += l.t1 - l.t0
                continue
            best, first_only = None, None
            for i, (rr, b, a, f) in enumerate(l.alternatives):
                rid = int(net.route_ids[rr])
                nb = dp.next_bus(rid, int(net.rs_ord[b]), int(net.rs_ord[a]), tt)
                if nb and (best is None or nb[0] < best[0]):
                    best = nb
                if i == 0:
                    first_only = nb
            if best is None:
                break
            pw.append(l.wait_s); aw.append(best[0] - tt); pr.append(l.ride_s); ar.append(best[1] - best[0])
            na.append(len(l.alternatives)); aw1.append((first_only[0] - tt) if first_only else np.nan)
            tt = best[1]
pw, aw, pr, ar, aw1 = map(np.array, (pw, aw, pr, ar, aw1))
print(f"{day}: direct legs {len(pw)}; routes in set: median {np.median(na)}, mean {np.mean(na):.1f}")
print(f"wait  predicted median {np.median(pw) / 60:.1f} mean {pw.mean() / 60:.1f} | actual median {np.median(aw) / 60:.1f} mean {aw.mean() / 60:.1f}"
      f" | actual if only first route: median {np.nanmedian(aw1) / 60:.1f}")
print(f"ride  predicted median {np.median(pr) / 60:.1f} mean {pr.mean() / 60:.1f} | actual median {np.median(ar) / 60:.1f} mean {ar.mean() / 60:.1f}")
print(f"ride MAE {np.mean(np.abs(pr - ar)) / 60:.1f} min, wait MAE {np.mean(np.abs(pw - aw)) / 60:.1f} min")
q = np.quantile(aw / 60, [0.5, 0.75, 0.9, 0.95])
print("actual wait quantiles (min) p50/p75/p90/p95:", np.round(q, 1))
