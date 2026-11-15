"""Log predictions from the Transport Stack ETA Calculator so we can score them later.

Every 60 s it asks the service for ETAs of 30 random live buses (bus/etas, all
upcoming stops) and 30 fixed busy stops (stop/etas). Rows are written every 5 min
to data/raw/eta_baseline/date=YYYY-MM-DD/*.parquet. Actual arrivals come later from
our GPS archive, which gives the organisers' baseline error by horizon.

Load: about 1 request per second, 3 at a time.
Usage: .venv\\Scripts\\python.exe -u scripts\\log_eta_baseline.py
"""
from __future__ import annotations

import os
import random
import signal
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import requests
from dotenv import load_dotenv
from google.transit import gtfs_realtime_pb2

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "eta_baseline"
GTFS = ROOT / "delhi_buses_static_gtfs_v1-2"
BASE = "https://dts-backend.transportstack.in/api/serviceset/eta-calculator"
OTD = "https://otd.delhi.gov.in/api/realtime/VehiclePositions.pb"
IST = timezone(timedelta(hours=5, minutes=30))
N_BUSES, N_STOPS, CYCLE = 30, 30, 60.0
SCHEMA = pa.schema([
    ("req_ts", pa.int64()), ("kind", pa.string()), ("vehicle_id", pa.string()), ("route_id", pa.string()),
    ("stop_id", pa.string()), ("stop_idx", pa.int32()), ("stops_in_btw", pa.int32()), ("eta_min", pa.float32()),
    ("vehicle_ts", pa.int64()), ("ac", pa.string()), ("agency", pa.string()), ("color", pa.string()),
    ("http", pa.int16()),
])
running = True


def stop_signal(*_):
    global running
    running = False


def busy_stops() -> list[str]:
    con = duckdb.connect()
    # Busiest stop (most routes) in each ~5 km grid cell, then the busiest cells, so the panel spans the city.
    rows = con.execute(f"""
        WITH n AS (
            SELECT s.stop_id, count(DISTINCT t.route_id) n_routes
            FROM read_csv('{GTFS / 'stop_times.txt'}', all_varchar=true) s
            JOIN read_csv('{GTFS / 'trips.txt'}', all_varchar=true) t USING (trip_id) GROUP BY 1),
        g AS (
            SELECT n.stop_id, n.n_routes, floor(p.stop_lat::DOUBLE / 0.045) gy, floor(p.stop_lon::DOUBLE / 0.05) gx
            FROM n JOIN read_csv('{GTFS / 'stops.txt'}', all_varchar=true) p USING (stop_id)),
        best AS (SELECT stop_id, n_routes, row_number() OVER (PARTITION BY gy, gx ORDER BY n_routes DESC, stop_id) rk FROM g)
        SELECT stop_id FROM best WHERE rk = 1 ORDER BY n_routes DESC, stop_id LIMIT {N_STOPS}""").fetchall()
    return [r[0] for r in rows]


def main() -> None:
    load_dotenv(ROOT / ".env")
    h = {"x-api-key": os.environ["ETA_API_KEY"]}
    otd_key = os.environ["OTD_API_KEY"]
    signal.signal(signal.SIGINT, stop_signal)
    signal.signal(signal.SIGTERM, stop_signal)
    panel = busy_stops()
    print(f"stop panel ({len(panel)}): {panel}", flush=True)
    session = requests.Session()
    rnd = random.Random()
    rows: list[dict] = []
    last_flush = time.time()

    def bus(vid: str) -> list[dict]:
        t = int(time.time())
        try:
            r = session.get(f"{BASE}/bus/etas", params={"vehicle_id": vid}, headers=h, timeout=30)
        except requests.RequestException:
            return [{"req_ts": t, "kind": "bus", "vehicle_id": vid, "http": -1}]
        if r.status_code != 200:
            return [{"req_ts": t, "kind": "bus", "vehicle_id": vid, "http": r.status_code}]
        return [{"req_ts": t, "kind": "bus", "vehicle_id": d.get("vehicle_id"), "route_id": str(d.get("route_id")),
                 "stop_id": str(d.get("upcoming_stop_id")), "stop_idx": d.get("upcoming_stop_idx"),
                 "stops_in_btw": d.get("stops_in_btw"), "eta_min": d.get("eta"),
                 "vehicle_ts": d.get("vehicle_timestamp"), "http": 200} for d in r.json().get("data", [])]

    def stop(sid: str) -> list[dict]:
        t = int(time.time())
        try:
            r = session.get(f"{BASE}/stop/etas", params={"stop_id": sid}, headers=h, timeout=30)
        except requests.RequestException:
            return [{"req_ts": t, "kind": "stop", "stop_id": sid, "http": -1}]
        if r.status_code != 200:
            return [{"req_ts": t, "kind": "stop", "stop_id": sid, "http": r.status_code}]
        out = []
        for b in r.json().get("buses", []):
            for e in b.get("etas", []):
                out.append({"req_ts": t, "kind": "stop", "vehicle_id": e.get("vehicle_id"), "route_id": str(b.get("route_id")),
                            "stop_id": sid, "eta_min": e.get("eta"), "vehicle_ts": e.get("timestamp"),
                            "ac": e.get("ac"), "agency": e.get("agency"), "color": e.get("color"), "http": 200})
        return out or [{"req_ts": t, "kind": "stop", "stop_id": sid, "http": 200}]

    with ThreadPoolExecutor(max_workers=3) as pool:
        while running:
            t0 = time.time()
            try:
                feed = gtfs_realtime_pb2.FeedMessage()
                for attempt in range(3):
                    try:
                        feed.ParseFromString(session.get(OTD, params={"key": otd_key}, timeout=30).content)
                        if len(feed.entity) >= 10:
                            break
                    except requests.RequestException:
                        pass
                    time.sleep(3)
                live = [e.vehicle.vehicle.id for e in feed.entity
                        if e.HasField("vehicle") and feed.header.timestamp - e.vehicle.timestamp < 120]
                sample = rnd.sample(live, min(N_BUSES, len(live)))
                for res in pool.map(bus, sample):
                    rows += res
                for res in pool.map(stop, panel):
                    rows += res
            except Exception as ex:  # keep logging through errors
                print(f"{datetime.now(IST):%H:%M:%S} cycle error {type(ex).__name__}: {str(ex)[:200]}", flush=True)
            if time.time() - last_flush >= 300 and rows:
                d = OUT / f"date={datetime.now(IST):%Y-%m-%d}"
                d.mkdir(parents=True, exist_ok=True)
                pq.write_table(pa.Table.from_pylist(rows, schema=SCHEMA), d / f"eta_{int(time.time())}.parquet",
                               compression="zstd")
                print(f"{datetime.now(IST):%H:%M:%S} wrote {len(rows)} rows", flush=True)
                rows, last_flush = [], time.time()
            time.sleep(max(0.0, CYCLE - (time.time() - t0)))


if __name__ == "__main__":
    main()
