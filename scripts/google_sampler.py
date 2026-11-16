"""Query Google Routes (transit) for the fixed OD set on recorded test days.

The Maps Demo Key allows only about 100 ComputeRoutes calls per day (measured 16 Nov 2026), so
calls are spent in priority order. Google's planned Delhi bus times do not change from day to day
(identical answers for Fri 13 and Tue 17 Nov at 08:30), so each (OD, slot) is queried once per day
type, plus a repeat sample on a second weekday that tests that assumption.

Priorities (lower first):
  1  tier A pairs, bus only, a weekday            (110 pairs x 4 slots)
  2  landmark pairs, any transit mode, a weekday  (30 x 4)
  3  repeat sample: 20 pairs x 08:30/18:00, bus, a second weekday
  4  tier A pairs, bus only, a weekend day
  5  tier B, bus only, a weekday
Each job uses the most recent recorded day of the right type whose slot is in the past and still
inside Google's 7-day look-back. A job without such a day waits for a later run.

Raw responses are private: data/raw/google/date=YYYY-MM-DD/responses.jsonl (git-ignored).
Usage: python -u scripts/google_sampler.py [--max-calls N]. Exit code 3 = daily quota reached.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "google"
VAL = ROOT / "validation"
URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
RECORD_START = dt.datetime(2026, 11, 15, 18, 0, tzinfo=IST)  # recording began 17:21 IST
LOOKBACK = dt.timedelta(days=7) - dt.timedelta(minutes=30)
FIELDS = ",".join([
    "routes.duration", "routes.distanceMeters", "routes.legs.duration",
    "routes.legs.steps.travelMode", "routes.legs.steps.staticDuration", "routes.legs.steps.distanceMeters",
    "routes.legs.steps.startLocation", "routes.legs.steps.endLocation", "routes.legs.steps.transitDetails",
])
GAP_S = 1.0
REPEAT_SLOTS = ("08:30", "18:00")


def daytype(d: dt.date) -> str:
    return "weekend" if d.weekday() >= 5 else "weekday"


def history() -> dict:
    """(od, slot, mode) -> set of dates with a successful response."""
    h = defaultdict(set)
    for f in OUT.glob("date=*/responses.jsonl"):
        day = dt.date.fromisoformat(f.parent.name.split("=")[1])
        for line in f.open(encoding="utf-8"):
            r = json.loads(line)
            if r.get("http") == 200:
                h[(r["od_id"], r["slot"], r["mode"])].add(day)
    return h


def jobs(od: dict, slots: list) -> list:
    tier_a = [s for s in slots if s["tier"] == "A"]
    landmarks = [k for k, r in od.items() if r["kind"] == "landmark"]
    rep_pairs = landmarks[:10] + [k for k, r in od.items() if r["kind"] == "direct" and r["tier"] == "A"][:10]
    out = [(1, s["od_id"], s["slot"], "bus", "weekday", 1) for s in tier_a]
    out += [(2, s["od_id"], s["slot"], "any", "weekday", 1) for s in tier_a if s["od_id"] in landmarks]
    out += [(3, p, sl, "bus", "weekday", 2) for p in rep_pairs for sl in REPEAT_SLOTS]
    out += [(4, s["od_id"], s["slot"], "bus", "weekend", 1) for s in tier_a]
    out += [(5, s["od_id"], s["slot"], "bus", "weekday", 1) for s in slots if s["tier"] == "B"]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-calls", type=int, default=100000)
    a = ap.parse_args()
    load_dotenv(ROOT / ".env")
    key = os.environ["GOOGLE_MAPS_API_KEY"]
    od = {r["od_id"]: r for r in csv.DictReader((VAL / "od_set.csv").open(encoding="utf-8"))}
    slots = list(csv.DictReader((VAL / "od_slots.csv").open(encoding="utf-8")))
    now = dt.datetime.now(IST)
    days = []
    d = RECORD_START.date()
    while d <= now.date():
        days.append(d)
        d += dt.timedelta(days=1)
    hist = history()
    todo = []
    for prio, od_id, slot, mode, dtype, need in jobs(od, slots):
        have = {x for x in hist[(od_id, slot, mode)] if daytype(x) == dtype}
        if len(have) >= need or (need > 1 and not have):  # repeats only after the first answer exists
            continue
        hh, mm = map(int, slot.split(":"))
        for day in reversed(days):  # most recent usable day of the right type, not already used
            t = dt.datetime(day.year, day.month, day.day, hh, mm, tzinfo=IST)
            if daytype(day) != dtype or day in have or t < RECORD_START:
                continue
            if t > now - dt.timedelta(minutes=5) or now - t > LOOKBACK:
                continue
            todo.append((prio, t, day, od_id, slot, mode))
            break
    todo.sort(key=lambda w: (w[0], w[1]))
    print(f"{now:%Y-%m-%d %H:%M} runnable calls: {len(todo)} "
          f"(by priority {dict(sorted({p: sum(1 for w in todo if w[0] == p) for p, *_ in todo}.items()))})", flush=True)
    session = requests.Session()
    n = 0
    for prio, t, day, od_id, slot, mode in todo[: a.max_calls]:
        r = od[od_id]
        body = {"origin": {"location": {"latLng": {"latitude": float(r["o_lat"]), "longitude": float(r["o_lon"])}}},
                "destination": {"location": {"latLng": {"latitude": float(r["d_lat"]), "longitude": float(r["d_lon"])}}},
                "travelMode": "TRANSIT", "computeAlternativeRoutes": True,
                "departureTime": t.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")}
        if mode == "bus":
            body["transitPreferences"] = {"allowedTravelModes": ["BUS"]}
        t0 = time.time()
        try:
            resp = session.post(URL, json=body, headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": FIELDS}, timeout=30)
            code, js = resp.status_code, resp.json()
        except (requests.RequestException, ValueError) as ex:
            code, js = -1, {"error": {"message": type(ex).__name__}}
        if code == 429 or (code != 200 and "RESOURCE_EXHAUSTED" in json.dumps(js)):
            print(f"quota reached after {n} calls this run", flush=True)
            sys.exit(3)
        rec = {"od_id": od_id, "slot": slot, "mode": mode, "priority": prio, "depart_ist": t.isoformat(),
               "request_ts": int(t0), "http": code, "body": js}
        f = OUT / f"date={day.isoformat()}" / "responses.jsonl"
        f.parent.mkdir(parents=True, exist_ok=True)
        with f.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        n += 1
        if code != 200:
            print(f"{od_id} {slot} {mode} {day}: HTTP {code} {json.dumps(js)[:160]}", flush=True)
        if n % 25 == 0:
            print(f"{dt.datetime.now(IST):%H:%M:%S} {n} calls (priority {prio}, {day} {slot})", flush=True)
        time.sleep(max(0.0, GAP_S - (time.time() - t0)))
    print(f"done: {n} calls", flush=True)


if __name__ == "__main__":
    main()
