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


@pytest.mark.skipif(not (NET / "network.npz").exists(), reason="built network not present")
def test_departures_link_to_their_route():
    """Each departure carries its route_id, so the stop board opens the route without a search request."""
    from fastapi.testclient import TestClient
    from naadi.api import app

    with TestClient(app) as client:
        stops = client.get("/stops/all").json()["stops"]
        stop_id = next(s[0] for s in stops if s[4] > 0)  # a stop that some route serves
        body = client.get(f"/stops/{stop_id}/departures").json()
        assert body["stop"]["stop_id"] == stop_id and body["departures"]
        first = body["departures"][0]
        assert {"route", "route_variant", "route_id", "towards", "live_eta_min", "typical_wait_min"} <= set(first)
        route = client.get(f"/routes/{first['route_id']}")
        assert route.status_code == 200 and route.json()["variant"] == first["route_variant"]
        assert client.get("/stops/999999999/departures").status_code == 404


@pytest.mark.skipif(not (NET / "network.npz").exists(), reason="built network not present")
def test_no_journey_answer_keeps_the_query_shape():
    """An answer without options carries the same query block as any other, so clients need no special case
    (the web app's results header crashed on the reduced block this replaced)."""
    from fastapi.testclient import TestClient
    from naadi.api import app

    with TestClient(app) as client:
        # Faridabad's southern edge: inside the NCR box, more than 1 km from any bus stop.
        body = client.get("/journeys?from=28.4089,77.3178&to=28.6315,77.2167&depart=2026-11-24T09:00&modes=bus").json()
        assert body["options"] == [] and body["message"]
        query = body["query"]
        assert {"from", "to", "depart", "day_type", "live", "crow_km", "modes"} <= set(query)
        assert query["from"]["lat"] == pytest.approx(28.4089) and query["crow_km"] > 20
