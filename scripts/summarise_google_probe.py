"""Print a short summary of the saved Google Routes probe responses in data/raw/google_probe/."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

for f in sorted((ROOT / "data" / "raw" / "google_probe").glob("*.json")):
    js = json.loads(f.read_text(encoding="utf-8"))
    print(f"== {f.stem}")
    if "error" in js:
        print("  ERROR", js["error"].get("status"), js["error"].get("message", "")[:300])
        continue
    routes = js.get("routes", [])
    if not routes:
        print("  no routes:", json.dumps(js)[:200])
    for i, ro in enumerate(routes[:4]):
        print(f"  option {i}: duration {ro.get('duration')}, static {ro.get('staticDuration')}, {ro.get('distanceMeters')} m")
        for st in ro.get("legs", [{}])[0].get("steps", []):
            if st.get("travelMode") != "TRANSIT":
                continue
            td = st["transitDetails"]
            sd = td.get("stopDetails", {})
            line = td.get("transitLine", {})
            print(f"     {line.get('vehicle', {}).get('type')} {line.get('nameShort', '?')}: "
                  f"{sd.get('departureStop', {}).get('name', '?')} -> {sd.get('arrivalStop', {}).get('name', '?')} "
                  f"({td.get('stopCount')} stops), departs {sd.get('departureTime', '')}")
