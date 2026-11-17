"""Smoke test of a running Naadi API. Usage: python scripts/smoke_api.py [base_url]"""
from __future__ import annotations

import sys
import time

import requests

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"


def show(o, i):
    legs = []
    for l in o["legs"]:
        if l["type"] == "bus":
            also = f" (or {', '.join(l['also'][:3])})" if l["also"] else ""
            legs.append(f"{l['route']}{also} {l['board']['name'][:20]}->{l['alight']['name'][:20]} wait {l['wait_min']} [{l['wait_source']}] "
                        f"next {l['next_buses_min'][:2]} ride {l['ride_min']}")
        else:
            legs.append(f"walk {l['metres']}m")
    print(f"  #{i} {o['total_min']} min {o['range_min']} labels {o['labels']} quiet {o['quiet_hour']} timetable {o['timetable_min']} "
          f"fare {o['fare_inr']} live {o['live']}")
    print("     " + " | ".join(legs))


def main() -> None:
    for _ in range(30):
        try:
            h = requests.get(f"{BASE}/health", timeout=10).json()
            break
        except requests.RequestException:
            time.sleep(2)
    print("health:", h)
    print("search:", [r["name"] for r in requests.get(f"{BASE}/stops/search", params={"q": "kashmiri gate"}, timeout=10).json()["results"][:4]])
    for dep in ("2026-11-17T08:30", "2026-11-17T23:00", "now"):
        t0 = time.time()
        r = requests.get(f"{BASE}/journeys", params={"from": "28.665476,77.230173", "to": "Nehru Place", "depart": dep}, timeout=60)
        js = r.json()
        print(f"== {dep}: HTTP {r.status_code} in {time.time() - t0:.2f}s, live={js.get('query', {}).get('live')}")
        for i, o in enumerate(js.get("options", [])):
            show(o, i)
    d = requests.get(f"{BASE}/stops/7571/departures", timeout=10).json()
    print("departures at", d["stop"]["name"], [(x["route"], x["live_eta_min"], x["typical_wait_min"]) for x in d["departures"][:6]])
    v = requests.get(f"{BASE}/vehicles", timeout=10).json()
    print("vehicles:", v["count"], v["vehicles"][:1])
    print("speeds cells:", len(requests.get(f"{BASE}/speeds/cells", timeout=20).json()["cells"]))


if __name__ == "__main__":
    main()
