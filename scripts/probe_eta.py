"""Probe the Transport Stack ETA Calculator service (the organisers' ETA baseline).

Usage: .venv\\Scripts\\python.exe scripts\\probe_eta.py
Reads ETA_API_KEY and OTD_API_KEY from .env. Responses go to data/raw/eta_probe/ (git-ignored).
"""
from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from google.transit import gtfs_realtime_pb2

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "eta_probe"
BASE = "https://dts-backend.transportstack.in/api/serviceset/eta-calculator"
OTD = "https://otd.delhi.gov.in/api/realtime/VehiclePositions.pb"


def show(label: str, r: requests.Response, keep: str) -> object:
    print(f"\n== {label}: HTTP {r.status_code}, {len(r.content)} bytes, {r.elapsed.total_seconds():.2f}s, "
          f"content-type {r.headers.get('content-type')}")
    (OUT / keep).write_bytes(r.content)
    try:
        data = r.json()
    except ValueError:
        print(r.text[:800])
        return None
    print(json.dumps(data, indent=1, ensure_ascii=False)[:2500])
    return data


def main() -> None:
    load_dotenv(ROOT / ".env")
    key = os.environ["ETA_API_KEY"]
    OUT.mkdir(parents=True, exist_ok=True)
    h = {"x-api-key": key}

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(requests.get(OTD, params={"key": os.environ["OTD_API_KEY"]}, timeout=30).content)
    vs = [e.vehicle for e in feed.entity if e.HasField("vehicle")]
    print(f"live buses now: {len(vs)}")
    rnd = random.Random(1)
    sample = rnd.sample(vs, min(3, len(vs)))

    show("bus ETAs, example vehicle from the email", requests.get(f"{BASE}/bus/etas", params={"vehicle_id": "REDACTED"},
                                                                 headers=h, timeout=30), "bus_example.json")
    for i, v in enumerate(sample):
        show(f"bus ETAs, live vehicle #{i} on route {v.trip.route_id}",
             requests.get(f"{BASE}/bus/etas", params={"vehicle_id": v.vehicle.id}, headers=h, timeout=30), f"bus_{i}.json")
        time.sleep(1)
    show("stop ETAs, example stop 2449", requests.get(f"{BASE}/stop/etas", params={"stop_id": "2449"}, headers=h, timeout=30),
         "stop_2449.json")
    show("no key (auth check)", requests.get(f"{BASE}/stop/etas", params={"stop_id": "2449"}, timeout=30), "nokey.json")


if __name__ == "__main__":
    main()
