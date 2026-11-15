"""Check whether Google's Delhi bus times change with time of day (2 Routes API calls).

Asks for bus-only transit from Kashmere Gate ISBT to Nehru Place tomorrow at 08:30 and 23:00 IST
and prints in-vehicle time per bus leg. Identical in-vehicle times mean a fixed timetable.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "google_probe"
IST = dt.timedelta(hours=5, minutes=30)
O = {"location": {"latLng": {"latitude": 28.6676, "longitude": 77.2280}}}
D = {"location": {"latLng": {"latitude": 28.5494, "longitude": 77.2513}}}
FM = ",".join([
    "routes.duration", "routes.legs.steps.travelMode", "routes.legs.steps.transitDetails.transitLine.nameShort",
    "routes.legs.steps.transitDetails.stopDetails.departureTime", "routes.legs.steps.transitDetails.stopDetails.arrivalTime",
    "routes.legs.steps.transitDetails.stopDetails.departureStop.name",
    "routes.legs.steps.transitDetails.stopDetails.arrivalStop.name", "routes.legs.steps.transitDetails.stopCount",
])


def main() -> None:
    load_dotenv(ROOT / ".env")
    key = os.environ["GOOGLE_MAPS_API_KEY"]
    tomorrow = (dt.datetime.now(dt.timezone.utc) + IST + dt.timedelta(days=1)).date()
    for hh, mm in ((8, 30), (23, 0)):
        t = dt.datetime(tomorrow.year, tomorrow.month, tomorrow.day, hh, mm, tzinfo=dt.timezone.utc) - IST
        body = {"origin": O, "destination": D, "travelMode": "TRANSIT", "departureTime": t.isoformat().replace("+00:00", "Z"),
                "transitPreferences": {"allowedTravelModes": ["BUS"]}}
        r = requests.post("https://routes.googleapis.com/directions/v2:computeRoutes", json=body,
                          headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": FM}, timeout=30)
        (OUT / f"tod_{hh:02d}{mm:02d}.json").write_bytes(r.content)
        js = r.json()
        print(f"== depart {hh:02d}:{mm:02d} IST: HTTP {r.status_code}")
        for ro in js.get("routes", [])[:1]:
            print(f"   door to door {int(ro['duration'].rstrip('s')) / 60:.1f} min")
            for st in ro["legs"][0]["steps"]:
                if st["travelMode"] != "TRANSIT":
                    continue
                td = st["transitDetails"]
                sd = td["stopDetails"]
                dep = dt.datetime.fromisoformat(sd["departureTime"].replace("Z", "+00:00"))
                arr = dt.datetime.fromisoformat(sd["arrivalTime"].replace("Z", "+00:00"))
                print(f"   bus {td['transitLine'].get('nameShort')}: {sd['departureStop']['name']} -> {sd['arrivalStop']['name']}, "
                      f"boards {(dep + IST):%H:%M:%S} IST, in-vehicle {(arr - dep).total_seconds() / 60:.1f} min for "
                      f"{td['stopCount']} stops")
        if "error" in js:
            print("  ", js["error"].get("status"), js["error"].get("message", "")[:200])


if __name__ == "__main__":
    main()
