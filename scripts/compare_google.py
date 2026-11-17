"""Compare Naadi with Google Maps (Routes API, bus-only transit) on recorded November days.

For each sampled (OD pair, departure slot, day):
  google_pred     Google's door-to-door duration for its first (recommended) option
  google_actual   replay of Google's itinerary on the buses that really ran: each Google bus step is matched to a
                  route of the same name with stops within 300 m of Google's boarding and alighting stops
  naadi_pred      Naadi's predicted door-to-door time (history from October only)
  naadi_actual    replay of Naadi's itinerary
Google responses stay private (data/raw/google, git-ignored); only aggregates are written:
validation/results/google_nov.json and .md.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path

import boto3
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from naadi.network import MODEL, Network, haversine, walk_s  # noqa: E402
from naadi.replay import DayPassages, realise  # noqa: E402
from naadi.router import Journey, Leg, Planner  # noqa: E402
from naadi.strategy import best_journey  # noqa: E402

RAW = ROOT / "data" / "raw" / "google"
RES = ROOT / "validation" / "results"
WORK = ROOT / "data" / "processed" / "speed_tables" / "_work"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
MATCH_M = 300.0


def sync() -> None:
    s = boto3.Session(profile_name="naadi", region_name="ap-south-1")
    acct = s.client("sts").get_caller_identity()["Account"]
    s3 = s.client("s3")
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=f"naadi-data-{acct}", Prefix="raw/google/"):
        for o in page.get("Contents", []):
            f = RAW / Path(o["Key"]).relative_to("raw/google")
            if not f.exists() or f.stat().st_size != o["Size"]:
                f.parent.mkdir(parents=True, exist_ok=True)
                s3.download_file(f"naadi-data-{acct}", o["Key"], str(f))


def base(name: str) -> str:
    return re.sub(r"(UP|DOWN)\d*$", "", (name or "").upper().replace(" ", "")).strip()


def google_journey(net: Network, by_name: dict, route: dict, t_dep: float):
    """Google's first option as a Journey on our network, or (None, reason)."""
    legs, t = [], t_dep
    for st in route["legs"][0].get("steps", []):
        dur = float(str(st.get("staticDuration", "0s")).rstrip("s") or 0)
        if st.get("travelMode") != "TRANSIT":
            legs.append(Leg("walk", t, t + dur, walk_m=float(st.get("distanceMeters", 0))))
            t += dur
            continue
        td = st["transitDetails"]
        name = base(td.get("transitLine", {}).get("nameShort") or td.get("transitLine", {}).get("name", ""))
        sd = td.get("stopDetails", {})
        a = sd.get("departureStop", {}).get("location", {}).get("latLng") or st["startLocation"]["latLng"]
        b = sd.get("arrivalStop", {}).get("location", {}).get("latLng") or st["endLocation"]["latLng"]
        best = None
        for r in by_name.get(name, []):
            lo, hi = int(net.r_ptr[r]), int(net.r_ptr[r + 1])
            s_idx = net.rs_stop[lo:hi]
            da = haversine(a["latitude"], a["longitude"], net.lat[s_idx], net.lon[s_idx])
            db = haversine(b["latitude"], b["longitude"], net.lat[s_idx], net.lon[s_idx])
            ia = int(np.argmin(da))
            if da[ia] > MATCH_M:
                continue
            later = np.arange(len(s_idx)) > ia
            if not later.any():
                continue
            ib = int(np.argmin(np.where(later, db, np.inf)))
            if db[ib] > MATCH_M:
                continue
            score = da[ia] + db[ib]
            if best is None or score < best[0]:
                best = (score, r, lo + ia, lo + ib)
        if best is None:
            return None, f"google line '{name}' not matched"
        _, r, ba, bb = best
        g_dep = sd.get("departureTime")
        g_arr = sd.get("arrivalTime")
        l = Leg("bus", t, t + dur, from_stop=int(net.rs_stop[ba]), to_stop=int(net.rs_stop[bb]), route=r, board_rs=ba, alight_rs=bb)
        l.alternatives = [(r, ba, bb, 1.0)]
        legs.append(l)
        if g_arr:
            t = dt.datetime.fromisoformat(g_arr.replace("Z", "+00:00")).timestamp()
        else:
            t += dur
    return Journey(legs=legs, depart=t_dep, arrive=t), "ok"


def main() -> None:
    sync()
    net = Network(MODEL / "network_prod")
    pl = Planner(net, "naadi")
    by_name: dict[str, list[int]] = {}
    for i, n in enumerate(net.route_short):
        by_name.setdefault(base(n), []).append(i)
    od = {r["od_id"]: r for r in csv.DictReader((ROOT / "validation" / "od_set.csv").open(encoding="utf-8"))}
    rows, days_done = [], []
    for f in sorted(RAW.glob("date=*/responses.jsonl")):
        day = f.parent.name.split("=")[1]
        pf = WORK / "passages" / f"day={day.replace('-', '_')}.parquet"
        if not pf.exists():
            print(f"{day}: no passages yet (run scripts/run_test_days.py {day}); skipped")
            continue
        dp = DayPassages(day.replace("-", "_"))
        days_done.append(day)
        for line in f.open(encoding="utf-8"):
            rec = json.loads(line)
            if rec.get("http") != 200 or rec["mode"] != "bus" or not rec["body"].get("routes"):
                continue
            r = od[rec["od_id"]]
            t = dt.datetime.fromisoformat(rec["depart_ist"]).timestamp()
            groute = rec["body"]["routes"][0]
            gpred = float(groute["legs"][0]["duration"].rstrip("s"))
            gj, why = google_journey(net, by_name, groute, t)
            gact, gwhy = realise(net, gj, dp) if gj is not None else (None, why)
            nj = best_journey(pl, (float(r["o_lat"]), float(r["o_lon"])), (float(r["d_lat"]), float(r["d_lon"])), t)
            nact, nwhy = realise(net, nj, dp) if nj is not None else (None, "no journey")
            rows.append({"day": day, "od": rec["od_id"], "slot": rec["slot"], "kind": r["kind"], "g_pred": gpred, "g_act": gact,
                         "g_status": gwhy, "n_pred": nj.total_s if nj else None, "n_act": nact, "n_status": nwhy,
                         "g_bus_legs": sum(1 for s in groute["legs"][0].get("steps", []) if s.get("travelMode") == "TRANSIT")})
    both = [x for x in rows if x["g_act"] is not None and x["n_act"] is not None]
    g_e = np.array([x["g_pred"] - x["g_act"] for x in both])
    n_e = np.array([x["n_pred"] - x["n_act"] for x in both])
    g_a = np.array([x["g_act"] for x in both]); n_a = np.array([x["n_act"] for x in both])
    statuses = {}
    for x in rows:
        statuses[x["g_status"]] = statuses.get(x["g_status"], 0) + 1
    rng = np.random.default_rng(3)
    diffs = [np.mean(np.abs(n_e[s])) - np.mean(np.abs(g_e[s])) for s in (rng.integers(0, len(both), len(both)) for _ in range(2000))] if both else [0]
    out = {"days": days_done, "google_cases": len(rows), "both_replayed": len(both), "google_match_status": statuses,
           "google": {"mae_min": float(np.mean(np.abs(g_e)) / 60), "median_abs_min": float(np.median(np.abs(g_e)) / 60),
                      "bias_min": float(np.mean(g_e) / 60), "within_10min_pct": float(100 * np.mean(np.abs(g_e) <= 600))} if both else None,
           "naadi": {"mae_min": float(np.mean(np.abs(n_e)) / 60), "median_abs_min": float(np.median(np.abs(n_e)) / 60),
                     "bias_min": float(np.mean(n_e) / 60), "within_10min_pct": float(100 * np.mean(np.abs(n_e) <= 600))} if both else None,
           "mae_diff_naadi_minus_google_min": {"mean": float(np.mean(diffs) / 60),
                                               "ci95": [float(np.quantile(diffs, 0.025) / 60), float(np.quantile(diffs, 0.975) / 60)]},
           "actual_time_median_min": {"google_itinerary": float(np.median(g_a) / 60) if both else None,
                                      "naadi_itinerary": float(np.median(n_a) / 60) if both else None},
           "naadi_itinerary_faster_pct": float(100 * np.mean(n_a < g_a)) if both else None}
    RES.mkdir(parents=True, exist_ok=True)
    (RES / "google_nov.json").write_text(json.dumps(out, indent=1))
    L = [f"# Naadi vs Google Maps, bus-only transit ({', '.join(days_done)})", "",
         f"{len(rows)} Google answers sampled; {len(both)} where both itineraries could be replayed on the buses that ran.", ""]
    if both:
        L += ["| | Google Maps | Naadi |", "|---|---|---|",
              f"| Mean error of predicted door-to-door time (min) | {out['google']['mae_min']:.1f} | {out['naadi']['mae_min']:.1f} |",
              f"| Median error (min) | {out['google']['median_abs_min']:.1f} | {out['naadi']['median_abs_min']:.1f} |",
              f"| Bias (min, negative = too optimistic) | {out['google']['bias_min']:+.1f} | {out['naadi']['bias_min']:+.1f} |",
              f"| Predictions within 10 min | {out['google']['within_10min_pct']:.0f}% | {out['naadi']['within_10min_pct']:.0f}% |",
              f"| Median actual time of the recommended trip (min) | {out['actual_time_median_min']['google_itinerary']:.1f} | "
              f"{out['actual_time_median_min']['naadi_itinerary']:.1f} |", "",
              f"Naadi minus Google mean error: {out['mae_diff_naadi_minus_google_min']['mean']:+.1f} min "
              f"(95% bootstrap CI {out['mae_diff_naadi_minus_google_min']['ci95'][0]:+.1f} to {out['mae_diff_naadi_minus_google_min']['ci95'][1]:+.1f}). "
              f"Naadi's recommended trip was actually faster in {out['naadi_itinerary_faster_pct']:.0f}% of cases."]
    L += ["", f"Google itinerary matching: {statuses}"]
    (RES / "google_nov.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
