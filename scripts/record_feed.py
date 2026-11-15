"""Stopgap 24/7 recorder for the Delhi OTD GTFS-RT VehiclePositions feed.

Keeps only positions whose vehicle timestamp changed, and writes a zstd Parquet
file every 5 minutes to data/raw/rt/date=YYYY-MM-DD/hour=HH_<epoch>.parquet. Also keeps one raw
.pb snapshot every 10 minutes for audit. Replace with the AWS recorder later.

Usage: .venv\\Scripts\\python.exe scripts\\record_feed.py
"""
from __future__ import annotations

import os
import signal
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import requests
from dotenv import load_dotenv
from google.transit import gtfs_realtime_pb2

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "rt"
URL = "https://otd.delhi.gov.in/api/realtime/VehiclePositions.pb"
IST = timezone(timedelta(hours=5, minutes=30))
INTERVAL = 10.0
SCHEMA = pa.schema([
    ("poll_ts", pa.int64()), ("feed_ts", pa.int64()), ("ts", pa.int64()),
    ("vehicle_id", pa.string()), ("route_id", pa.string()), ("trip_id", pa.string()),
    ("start_time", pa.string()), ("start_date", pa.string()), ("sched_rel", pa.int8()),
    ("lat", pa.float64()), ("lon", pa.float64()), ("speed", pa.float32()), ("bearing", pa.float32()),
])
running = True


def stop(*_):
    global running
    running = False


def flush(rows: list[dict], hour_key: str) -> None:
    if not rows:
        return
    date, hour = hour_key.split("T")
    d = OUT / f"date={date}"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"hour={hour}_{int(time.time())}.parquet"
    pq.write_table(pa.Table.from_pylist(rows, schema=SCHEMA), path, compression="zstd")
    print(f"{datetime.now(IST):%H:%M:%S} wrote {len(rows)} rows -> {path.relative_to(ROOT)}", flush=True)


def main() -> None:
    load_dotenv(ROOT / ".env")
    key = os.environ["OTD_API_KEY"]
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    (OUT / "_raw_pb").mkdir(parents=True, exist_ok=True)
    last_ts: dict[str, int] = {}
    rows: list[dict] = []
    hour_key = datetime.now(IST).strftime("%Y-%m-%dT%H")
    last_raw = 0.0
    last_flush = time.time()
    session = requests.Session()
    while running:
        t0 = time.time()
        try:
            r = session.get(URL, params={"key": key}, timeout=30)
            r.raise_for_status()
            feed = gtfs_realtime_pb2.FeedMessage()
            feed.ParseFromString(r.content)
            if t0 - last_raw >= 600:
                (OUT / "_raw_pb" / f"vp_{int(t0)}.pb").write_bytes(r.content)
                last_raw = t0
            if len(feed.entity) < 10:
                print(f"{datetime.now(IST):%H:%M:%S} truncated feed ({len(feed.entity)} entities), skipped", flush=True)
            for e in feed.entity:
                if not e.HasField("vehicle"):
                    continue
                v = e.vehicle
                vid = v.vehicle.id or e.id
                if last_ts.get(vid) == v.timestamp:
                    continue
                last_ts[vid] = v.timestamp
                rows.append({
                    "poll_ts": int(t0), "feed_ts": feed.header.timestamp, "ts": v.timestamp, "vehicle_id": vid,
                    "route_id": v.trip.route_id, "trip_id": v.trip.trip_id, "start_time": v.trip.start_time,
                    "start_date": v.trip.start_date, "sched_rel": v.trip.schedule_relationship,
                    "lat": v.position.latitude, "lon": v.position.longitude,
                    "speed": v.position.speed, "bearing": v.position.bearing,
                })
        except Exception as ex:  # keep running through network errors
            print(f"{datetime.now(IST):%H:%M:%S} poll error {type(ex).__name__}: {str(ex).replace(key, '****')[:200]}",
                  flush=True)
        now_key = datetime.now(IST).strftime("%Y-%m-%dT%H")
        if now_key != hour_key or time.time() - last_flush >= 300 or len(rows) > 400_000:
            flush(rows, hour_key)
            rows, hour_key, last_flush = [], now_key, time.time()
        time.sleep(max(0.0, INTERVAL - (time.time() - t0)))
    flush(rows, hour_key)


if __name__ == "__main__":
    main()
