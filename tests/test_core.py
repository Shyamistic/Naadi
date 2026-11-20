"""Unit and integration tests. Run: .venv\\Scripts\\python.exe -m pytest -q tests"""
from __future__ import annotations

import datetime as dt
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from naadi.linkgrid import LinkGrid  # noqa: E402
from naadi.nowcast import NowcastParams, ResidualIndex, correction  # noqa: E402
from naadi.router import Journey, Leg, _interp  # noqa: E402
from naadi.strategy import attractive_set, option_signature, plan_options, with_first_wait  # noqa: E402
from naadi.paths import MODEL as DATA_MODEL  # noqa: E402

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def ts(y, m, d, hh, mm):
    return dt.datetime(y, m, d, hh, mm, tzinfo=IST).timestamp()


def test_hour_weights_interpolate_between_hour_centres():
    h0, h1, w = LinkGrid.hour_weights(np.array([ts(2026, 11, 17, 8, 30), ts(2026, 11, 17, 9, 0), ts(2026, 11, 17, 0, 0)]))
    assert (h0[0], h1[0]) == (8, 9) and w[0] == pytest.approx(0.0)
    assert (h0[1], h1[1]) == (8, 9) and w[1] == pytest.approx(0.5)
    assert (h0[2], h1[2]) == (23, 0) and w[2] == pytest.approx(0.5)


def test_weekend_arithmetic_matches_calendar():
    from eval_eta import weekend
    for d in range(1, 31):
        t = ts(2026, 11, d, 22, 0)
        assert weekend(np.array([t]))[0] == int(dt.date(2026, 11, d).weekday() >= 5)


def test_residual_window_sums_only_the_window():
    idx = ResidualIndex(np.array([1, 1, 1, 2]), np.array([100.0, 200.0, 300.0, 250.0]), np.array([0.1, 0.2, 0.3, 5.0]), 0.0)
    s, n = idx.window(np.array([1]), np.array([301.0]), 150)
    assert n[0] == 2 and s[0] == pytest.approx(0.5)
    s, n = idx.window(np.array([3]), np.array([301.0]), 1000)
    assert n[0] == 0 and s[0] == 0


def test_nowcast_without_live_data_is_zero():
    idx = ResidualIndex(np.array([1]), np.array([100.0]), np.array([0.5]), 0.0)
    c = correction(NowcastParams(), idx, idx, np.array([7]), np.array([7]), np.array([500.0]), np.array([600.0]))
    assert c[0] == 0.0


def test_attractive_set_combines_frequencies_and_drops_slow_routes():
    fast_rare = (0, 0, 1, 1 / 1200, 1000.0)
    slower_frequent = (1, 0, 1, 1 / 300, 1100.0)
    very_slow = (2, 0, 1, 1 / 300, 5000.0)
    chosen, ew, er = attractive_set([very_slow, slower_frequent, fast_rare])
    assert {c[0] for c in chosen} == {0, 1}
    assert ew == pytest.approx(1 / (1 / 1200 + 1 / 300))
    assert 1000 < er < 1100


def test_conformal_quantiles_cover():
    from build_summary import conformal
    r = np.random.default_rng(0).normal(size=5000)
    lo, hi = conformal(r)
    assert np.mean((r >= lo) & (r <= hi)) >= 0.79


def test_fare_slabs():
    from naadi.api import fare
    assert fare(3) == (5, 10) and fare(9) == (10, 20) and fare(15) == (15, 25)


def test_coordinates_are_validated():
    from fastapi import HTTPException
    from naadi.api import resolve
    assert resolve("28.6655,77.2302")[:2] == (28.6655, 77.2302)
    with pytest.raises(HTTPException):
        resolve("19.07,72.87")


def test_interp_keeps_finite_wait_at_hour_centre():
    assert _interp(300.0, np.inf, 0.0) == 300.0
    assert np.isinf(_interp(300.0, np.inf, 0.5))


def test_option_signature_merges_same_stop_and_route_set():
    import types
    net = types.SimpleNamespace(stop_names=["ISBT", "ISBT", "Yamuna Bazaar"], route_short=["412UP", "244UP"])
    alts = [(0, 0, 0, 1.0), (1, 0, 0, 1.0)]
    j1 = Journey([Leg("bus", 0, 0, route=0, from_stop=0, alternatives=alts)])
    j2 = Journey([Leg("bus", 0, 0, route=1, from_stop=0, alternatives=list(reversed(alts)))])
    j3 = Journey([Leg("bus", 0, 0, route=0, from_stop=2, alternatives=alts)])
    assert option_signature(net, j1) == option_signature(net, j2)
    assert option_signature(net, j1) != option_signature(net, j3)


def test_with_first_wait_uses_next_bus_and_shifts_later_legs():
    t0 = 1000.0
    legs = [Leg("walk", t0, t0 + 60), Leg("bus", t0 + 60, t0 + 1560, from_stop=1, wait_s=600, ride_s=900),
            Leg("walk", t0 + 1560, t0 + 1680)]
    j = Journey(legs, t0, t0 + 1680)
    j.legs[1].alternatives = [(0, 2, 3, 1.0)]
    out = with_first_wait(j, t0, lambda rs, t: [t0 + 160, t0 + 960])
    assert out.legs[1].wait_s == 100 and out.arrive == t0 + 1180
    assert out.legs[2].t0 == t0 + 1060 and out.legs[1].live_info["wait_source"] == "live bus"
    assert out.legs[1].live_info["next"] == [1.7, 15.0]
    j = Journey(legs, t0, t0 + 1680)
    j.legs[1].alternatives = [(0, 2, 3, 1.0)]
    assert with_first_wait(j, t0, lambda rs, t: [t0 + 160], 1.2).legs[1].wait_s == 120


def test_metro_patterns_tiny_gtfs(tmp_path):
    from naadi.multimodal import metro_patterns
    (tmp_path / "stops.txt").write_text("stop_id,stop_name,stop_lat,stop_lon\nA,A,28.0,77.0\nB,B,28.0,77.01\nC,C,28.0,77.02\n")
    (tmp_path / "routes.txt").write_text("route_id,route_long_name\n0,VIOLET_A to C\n1,VIOLET_C to A\n")
    trips, times = [], []
    for route, reverse in (("0", False), ("1", True)):
        order = ["C", "B", "A"] if reverse else ["A", "B", "C"]
        for k in range(6):
            tid = f"{route}{k}"
            trips.append(f"{route},weekday,{tid},,0,shp_{route}")
            for i, stop in enumerate(order):
                sec = 6 * 3600 + k * 600 + i * 120
                hh, rem = divmod(sec, 3600); mm, ss = divmod(rem, 60)
                arr = f"{hh:02d}:{mm:02d}:{ss:02d}"
                dep = f"{hh:02d}:{mm:02d}:{ss + 20:02d}"
                times.append(f"{tid},{arr},{dep},{stop},{i},")
    (tmp_path / "trips.txt").write_text("route_id,service_id,trip_id,trip_headsign,direction_id,shape_id\n" + "\n".join(trips) + "\n")
    (tmp_path / "stop_times.txt").write_text("trip_id,arrival_time,departure_time,stop_id,stop_sequence,shape_dist_traveled\n" + "\n".join(times) + "\n")
    (tmp_path / "shapes.txt").write_text("shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\nshp_0,28.0,77.0,0\nshp_0,28.0,77.01,1\nshp_0,28.0,77.02,2\nshp_1,28.0,77.02,0\nshp_1,28.0,77.01,1\nshp_1,28.0,77.0,2\n")
    stations, patterns = metro_patterns(tmp_path)
    assert len(stations) == 3 and len(patterns) == 2
    assert patterns[0]["offsets_s"].tolist() == [0, 120, 240]
    assert patterns[0]["deps"][0, 6] == 6
    assert {p["group"] for p in patterns} == {0, 1}
    assert len({(s, p["line_code"], p["group"]) for p in patterns for s in p["stations"]}) == 6


def test_metro_fare_slabs():
    from naadi.multimodal import metro_fare
    assert metro_fare(1.5, False) == 11 and metro_fare(19.0, False) == 43
    assert metro_fare(19.0, True) == 32 and metro_fare(40.0, False) == 64 and metro_fare(40.0, True) == 54


NET = DATA_MODEL / "network_prod"
MM_NET = DATA_MODEL / "network_prod_mm"


@pytest.mark.skipif(not (NET / "network.npz").exists(), reason="built network not present")
def test_brief_example_differs_by_time_of_day():
    from naadi.network import Network
    from naadi.router import Planner
    from naadi.strategy import best_journey
    pl = Planner(Network(NET), "naadi")
    o, d = (28.665476, 77.230173), (28.548700, 77.256981)
    am = best_journey(pl, o, d, ts(2026, 11, 17, 8, 30))
    pm = best_journey(pl, o, d, ts(2026, 11, 17, 23, 0))
    assert am is not None and pm is not None
    assert am.n_bus >= 1 and all(l.kind in ("walk", "bus") for l in am.legs)
    assert abs(am.total_s - pm.total_s) > 60


def test_api_brief_example_no_duplicates_and_dial_matches_card():
    from fastapi.testclient import TestClient
    from naadi.api import app
    with TestClient(app) as client:
        response = client.get("/journeys", params={"from": "Kashmere Gate ISBT", "to": "Nehru Place", "depart": "2026-11-24T08:30", "modes": "bus"})
    assert response.status_code == 200
    body = response.json()
    assert len(body["options"]) >= 2
    signatures = []
    for option in body["options"]:
        signature = tuple((leg["board"]["name"], frozenset([leg["route"]] + leg["also"]))
                          for leg in option["legs"] if leg["type"] == "bus")
        signatures.append(signature)
        assert option["samay_chakra"][8] == option["total_min"]
    assert len(signatures) == len(set(signatures))


@pytest.mark.skipif(not (MM_NET / "network.npz").exists(), reason="multimodal network not built")
def test_bus_options_unchanged_with_metro_network():
    from naadi.network import Network
    from naadi.router import Planner
    pl_bus = Planner(Network(NET), "naadi")
    pl_mm = Planner(Network(MM_NET), "naadi")
    o, d = (28.665476, 77.230173), (28.548700, 77.256981)
    t = ts(2026, 11, 24, 8, 30)
    left = plan_options(pl_bus, o, d, t, n=3, calib=(1.0, 1.0))
    right = plan_options(pl_mm, o, d, t, n=3, calib=(1.0, 1.0))
    assert [(round(j.total_s), option_signature(pl_bus.net, j)) for j in left] == [(round(j.total_s), option_signature(pl_mm.net, j)) for j in right]


@pytest.mark.skipif(not (MM_NET / "network.npz").exists(), reason="multimodal network not built")
def test_api_brief_example_multimodal():
    from fastapi.testclient import TestClient
    from naadi.api import app
    with TestClient(app) as client:
        response = client.get("/journeys", params={"from": "Kashmere Gate ISBT", "to": "Nehru Place", "depart": "2026-11-24T08:30"})
        bus_only = client.get("/journeys", params={"from": "Kashmere Gate ISBT", "to": "Nehru Place", "depart": "2026-11-24T08:30", "modes": "bus"})
        invalid = client.get("/journeys", params={"from": "Kashmere Gate ISBT", "to": "Nehru Place", "modes": "car"})
    assert response.status_code == 200 and response.json()["multimodal_options"]
    for option in response.json()["multimodal_options"]:
        assert any(leg["type"] == "metro" for leg in option["legs"])
        assert option["schedule_estimated"] and option["range_min"] is None
    assert bus_only.json()["multimodal_options"] == [] and invalid.status_code == 400


def test_next_bus_interpolates_missing_boarding_crossing():
    from naadi.replay import DayPassages
    day = DayPassages.from_arrays([1, 1, 1, 1], [10, 10, 10, 10], [1, 2, 4, 5], [100, 200, 400, 500])
    assert day.next_bus(10, 3, 5, 0.0) == pytest.approx((300.0, 500.0))
    day = DayPassages.from_arrays([1, 1, 1, 1, 1], [10] * 5, [1, 2, 3, 4, 5], [100, 200, 310, 400, 500])
    assert day.next_bus(10, 3, 5, 0.0) == pytest.approx((310.0, 500.0))


def test_fit_finds_wait_factor_below_0_8():
    from build_summary import fit
    rng = np.random.default_rng(0)
    n = 2000
    c = {"walk": rng.uniform(0, 300, n), "wait_hist": rng.uniform(0, 900, n), "wait_live": np.zeros(n),
         "ride": rng.uniform(300, 3600, n)}
    c["act"] = c["walk"] + 0.5 * c["wait_hist"] + 1.1 * c["ride"]
    a, b = fit(c, np.ones(n, dtype=bool))
    assert a == pytest.approx(0.5, abs=0.05) and b == pytest.approx(1.1, abs=0.02)


def test_interval_uses_wait_group_then_band():
    import naadi.api as api
    old = getattr(api.S, "intervals", None)
    api.S.intervals = {"history": {"bands": [{"max_min": 9999, "q_lo": -0.1, "q_hi": 0.2}],
                                    "wait_edges_min": [5, 10, 20],
                                    "groups": [{"max_min": 9999, "wait_class": 0, "q_lo": -0.05, "q_hi": 0.1}]}}
    try:
        assert api.interval(3600, False, 0) == pytest.approx((3600 * np.exp(-0.05), 3600 * np.exp(0.1)))
        assert api.interval(3600, False, 900) == pytest.approx((3600 * np.exp(-0.1), 3600 * np.exp(0.2)))
    finally:
        api.S.intervals = old
