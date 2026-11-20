"""Smoke test of a running Naadi API. Usage: python scripts/smoke_api.py [base_url]"""
from __future__ import annotations

import sys
import time

import requests

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
FAIL = False


def fail(message):
    global FAIL
    FAIL = True
    print("FAIL:", message)


def show(o, i):
    legs = []
    for l in o["legs"]:
        if l["type"] == "bus":
            also = f" (or {', '.join(l['also'][:3])})" if l["also"] else ""
            legs.append(f"{l['route']}{also} {l['board']['name'][:20]}->{l['alight']['name'][:20]} wait {l['wait_min']} [{l['wait_source']}] "
                        f"next {l['next_buses_min'][:2]} ride {l['ride_min']}")
        elif l["type"] == "metro":
            legs.append(f"{l['line']} {l['board']['name'][:20]}->{l['alight']['name'][:20]} wait {l['wait_min']} ride {l['ride_min']}")
        elif l["type"] in ("rail", "shared_auto"):
            legs.append(f"{l['type']} {l['board']['name'][:20]}->{l['alight']['name'][:20]} wait {l['wait_min']} ride {l['ride_min']} fare {l['fare_inr']}")
        else:
            legs.append(f"walk {l['metres']}m")
    print(f"  #{i} {o['total_min']} min {o['range_min']} labels {o['labels']} quiet {o['quiet_hour']} timetable {o['timetable_min']} "
          f"fare {o['fare_inr']} live {o['live']}")
    print("     " + " | ".join(legs))


def check_options(body, expected_types=()):
    options = body.get("options", [])
    signatures = set()
    for option in options:
        signature = tuple((leg["board"]["name"], frozenset([leg["route"]] + leg["also"]))
                          for leg in option["legs"] if leg["type"] == "bus")
        if signature in signatures:
            fail("duplicate bus option signature")
        signatures.add(signature)
        try:
            hour = int(option["depart"][11:13])
            if option["samay_chakra"][hour] != option["total_min"]:
                fail("SamayChakra departure spoke differs from card")
        except (KeyError, IndexError, TypeError, ValueError):
            fail("malformed SamayChakra")
    extension = body.get("multimodal_options", [])
    for option in extension:
        if not option.get("schedule_estimated") or option.get("range_min") is not None:
            fail("invalid multimodal option estimate fields")
        types = {leg.get("type") for leg in option.get("legs", [])}
        if expected_types and not any(kind in types for kind in expected_types):
            fail(f"multimodal option has none of {expected_types}")
    return options


def get_journey(params):
    try:
        response = requests.get(f"{BASE}/journeys", params=params, timeout=60)
        if response.status_code != 200:
            fail(f"journeys HTTP {response.status_code}")
            return {}
        return response.json()
    except requests.RequestException as exc:
        fail(f"journeys request failed: {exc}")
        return {}


def main() -> None:
    global FAIL
    health = None
    for _ in range(30):
        try:
            health = requests.get(f"{BASE}/health", timeout=10).json()
            break
        except requests.RequestException:
            time.sleep(2)
    if health is None:
        fail("health endpoint unavailable")
        print("SMOKE FAILED")
        raise SystemExit(1)
    print("health:", health)
    print("search:", [r["name"] for r in requests.get(f"{BASE}/stops/search", params={"q": "kashmiri gate"}, timeout=10).json()["results"][:4]])

    queries = [
        ("brief", {"from": "Kashmere Gate ISBT", "to": "Nehru Place", "depart": "2026-11-24T08:30"}, ("metro",)),
        ("namo", {"from": "Sarai Kale Khan", "to": "Modipuram", "depart": "2026-11-24T08:30", "modes": "rail"}, ("rail",)),
        ("shared first mile", {"from": "Govind Puri", "to": "Iiitd Campus", "depart": "2026-11-24T08:30", "modes": "shared_auto"}, ("shared_auto",)),
        ("arrive-by", {"from": "Kashmere Gate ISBT", "to": "Nehru Place", "arrive": "2026-11-24T09:30+05:30", "modes": "bus"}, ()),
    ]
    for name, params, expected_types in queries:
        t0 = time.time()
        body = get_journey(params)
        print(f"== {name}: in {time.time() - t0:.2f}s, live={body.get('query', {}).get('live')} arrive_by={body.get('query', {}).get('arrive_by')}")
        if name == "arrive-by" and "arrive_by" not in body.get("query", {}):
            fail("arrive-by response missing query.arrive_by")
        for i, option in enumerate(body.get("options", [])):
            show(option, i)
        for i, option in enumerate(body.get("multimodal_options", [])):
            print(f"  multimodal #{i}:")
            show(option, i)
        check_options(body, expected_types)
    adapter_params = {"src": "[28.6655,77.2302]", "src_type": "place", "dst": "[28.5487,77.2570]",
                      "dst_type": "place", "mode": "bus", "time": "08:30:00"}
    try:
        adapter_response = requests.get(f"{BASE}/v2/get_multi_modal", params=adapter_params, timeout=60)
        print("== adapter: HTTP", adapter_response.status_code)
        if adapter_response.status_code != 200 or "journeys" not in adapter_response.json():
            fail("adapter response missing journeys")
    except requests.RequestException as exc:
        fail(f"adapter request failed: {exc}")
    bus_body = get_journey({"from": "Kashmere Gate ISBT", "to": "Nehru Place", "depart": "2026-11-24T08:30", "modes": "bus"})
    if bus_body.get("multimodal_options") != []:
        fail("modes=bus returned multimodal options")

    live_available = False
    for _ in range(18):
        try:
            h = requests.get(f"{BASE}/health", timeout=10).json()
            if h.get("live", {}).get("residuals_30min", 0) > 0:
                live_available = True
                break
        except requests.RequestException:
            pass
        time.sleep(10)
    if live_available:
        body = get_journey({"from": "28.665476,77.230173", "to": "Nehru Place", "depart": "now"})
        print(f"== now: live={body.get('query', {}).get('live')}")
        for i, option in enumerate(body.get("options", [])):
            show(option, i)
        check_options(body, ("metro",))
    else:
        print("live not available, live checks skipped")

    d = requests.get(f"{BASE}/stops/7571/departures", timeout=10).json()
    print("departures at", d["stop"]["name"], [(x["route"], x["live_eta_min"], x["typical_wait_min"]) for x in d["departures"][:6]])
    v = requests.get(f"{BASE}/vehicles", timeout=10).json()
    print("vehicles:", v["count"], v["vehicles"][:1])
    print("speeds cells:", len(requests.get(f"{BASE}/speeds/cells", timeout=20).json()["cells"]))
    if FAIL:
        print("SMOKE FAILED")
        raise SystemExit(1)
    print("SMOKE OK")


if __name__ == "__main__":
    main()
