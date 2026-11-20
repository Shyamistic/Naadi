import gzip
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient

from naadi.trails import router
from fastapi import FastAPI

ROOT = Path(os.environ.get("NAADI_ROOT", Path(__file__).resolve().parents[1]))
OUT = ROOT / "data/processed/model/trails_v1"


def _app():
    app = FastAPI()
    app.include_router(router)
    return app


def test_index_contract_and_privacy():
    p = OUT / "index.json"
    assert p.exists()
    x = json.loads(p.read_text())
    assert x["version"] == 1
    assert x["hours"] == list(range(24))
    assert set(x["day_types"]) == {"weekday", "weekend"}
    assert all(len(x["buses_per_hour"][d]) == 24 for d in x["day_types"])
    assert not any(k in json.dumps(x).lower() for k in ("vehicle_id", "plate", "run_id"))


def test_all_chunks_size_and_privacy():
    chunks = sorted(OUT.glob("*.json.gz"))
    assert len(chunks) == 48
    for p in chunks:
        assert p.stat().st_size <= 1_500_000
        text = gzip.decompress(p.read_bytes()).decode()
        assert "vehicle_id" not in text and "run_id" not in text and "plate" not in text
        payload = json.loads(text)
        for trip in payload["trips"]:
            assert set(trip) == {"r", "c", "t", "s"}
            assert len(trip["c"]) == len(trip["t"]) == len(trip["s"])
            assert all(len(c) == 2 and len(str(c[0]).split(".")[-1]) <= 5 for c in trip["c"])
            assert all(b - a >= 30 for a, b in zip(trip["t"], trip["t"][1:]))
            assert all(0 <= s <= 80 for s in trip["s"])


def test_trip_order_is_shuffled():
    payload = json.loads(gzip.decompress((OUT / "weekday_08.json.gz").read_bytes()))
    routes = [trip["r"] for trip in payload["trips"]]
    assert len(routes) > 2
    assert routes != sorted(routes)


def test_router_serves_gzip_and_cache_headers():
    client = TestClient(_app())
    r = client.get("/trails/index")
    assert r.status_code == 200
    assert r.headers["content-encoding"] == "gzip"
    assert r.headers["cache-control"] == "public, max-age=86400"
    r = client.get("/trails/weekday/0")
    assert r.status_code == 200
    assert r.headers["content-encoding"] == "gzip"
