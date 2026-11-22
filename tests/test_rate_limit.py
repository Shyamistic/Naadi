"""Per-IP request budgets in naadi.api. No model is loaded: refused requests never reach an endpoint, and allowed
ones go to paths that don't exist (404), so the middleware is tested on its own."""
from fastapi.testclient import TestClient

from naadi import api


def test_rate_check_counts_within_a_sliding_window():
    api._hits.clear()
    key = ("198.51.100.1", "all")
    assert [api._rate_check(key, 3, 1000.0 + i) for i in range(3)] == [0, 0, 0]
    wait = api._rate_check(key, 3, 1010.0)
    assert wait == 50  # the first request (t=1000) leaves the 60 s window at t=1060
    assert api._rate_check(key, 3, 1060.5) == 0  # a slot is free again
    api._hits.clear()


def test_middleware_refuses_with_retry_after(monkeypatch):
    api._hits.clear()
    monkeypatch.setattr(api, "RATE_LIMITS", {"all": 3, "journeys": 2})
    client = TestClient(api.app)
    me = {"x-forwarded-for": "203.0.113.9"}
    assert [client.get("/no-such-page", headers=me).status_code for _ in range(3)] == [404, 404, 404]
    refused = client.get("/no-such-page", headers=me)
    assert refused.status_code == 429
    assert 1 <= int(refused.headers["retry-after"]) <= 60
    # another address has its own budget
    assert client.get("/no-such-page", headers={"x-forwarded-for": "203.0.113.10"}).status_code == 404
    api._hits.clear()


def test_journeys_have_their_own_tighter_budget(monkeypatch):
    api._hits.clear()
    monkeypatch.setattr(api, "RATE_LIMITS", {"all": 50, "journeys": 2})
    client = TestClient(api.app)
    me = {"x-forwarded-for": "203.0.113.11"}
    assert [client.get("/x/journeys", headers=me).status_code for _ in range(3)] == [404, 404, 429]
    assert client.get("/no-such-page", headers=me).status_code == 404  # other endpoints still work
    api._hits.clear()
