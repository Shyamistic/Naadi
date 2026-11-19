"""Tests for the read-only web API additions."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from naadi.webapi import base_name, decimate, in_box, natural_key, opposite_variant, validate_bbox  # noqa: E402


def test_route_variant_helpers():
    assert base_name("405UP") == "405"
    assert opposite_variant("405UP") == "405DOWN"
    assert opposite_variant("412DOWN2") == "412UP2"
    assert opposite_variant("BYPASS EXPRESS") is None


def test_natural_key_order():
    assert sorted(["10A", "D-022", "9", "10"], key=natural_key) == ["9", "10", "10A", "D-022"]


def test_decimate_keeps_ends():
    points = list(range(100))
    result = decimate(points, 10)
    assert len(result) == 10 and result[0] == 0 and result[-1] == 99
    assert decimate(points, 100) == points


def test_bbox_validation():
    assert in_box(28.6, 77.2)
    with pytest.raises(HTTPException) as exc:
        validate_bbox(29.0, 28.0, 77.0, 77.1)
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        validate_bbox(19.0, 19.1, 72.0, 72.1)
    assert exc.value.status_code == 400


NET = ROOT / "data" / "processed" / "model" / "network_prod"


@pytest.mark.skipif(not (NET / "network.npz").exists(), reason="built network not present")
def test_capabilities_and_stop_endpoints():
    from fastapi.testclient import TestClient
    from naadi.api import app

    with TestClient(app) as client:
        assert client.get("/capabilities").json() == {"web_api_version": 1}
        response = client.get("/stops/all")
        assert response.status_code == 200
        body = response.json()
        assert body["fields"] == ["stop_id", "name", "lat", "lon", "routes"]
        assert body["count"] == len(body["stops"])
        assert "Cache-Control" in response.headers


@pytest.mark.skipif(not (NET / "network.npz").exists(), reason="built network not present")
def test_endpoint_validation():
    from fastapi.testclient import TestClient
    from naadi.api import app

    with TestClient(app) as client:
        assert client.get("/stops/nearby?lat=19.07&lon=72.87").status_code == 400
        assert client.get("/stops/nearby?lat=28.6&lon=77.2&radius_m=5000").status_code == 422
        assert client.get("/routes/999999999").status_code == 404
        assert client.get("/legs/next-buses?board=1&alight=1").status_code in (400, 404)
