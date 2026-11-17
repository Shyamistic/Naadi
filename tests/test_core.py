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
from naadi.strategy import attractive_set  # noqa: E402

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
        t = ts(2026, 11, d, 22, 0)  # late evening: the hour where the old time-zone bug flipped the day
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
    # (route, board, alight, rate=1/wait, ride)
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
        resolve("19.07,72.87")  # Mumbai is outside Delhi NCR


NET = ROOT / "data" / "processed" / "model" / "network_prod"


@pytest.mark.skipif(not (NET / "network.npz").exists(), reason="built network not present")
def test_brief_example_differs_by_time_of_day():
    from naadi.network import Network
    from naadi.router import Planner
    from naadi.strategy import best_journey
    pl = Planner(Network(NET), "naadi")
    o, d = (28.665476, 77.230173), (28.548700, 77.256981)  # Kashmere Gate ISBT -> Nehru Place
    am = best_journey(pl, o, d, ts(2026, 11, 17, 8, 30))
    pm = best_journey(pl, o, d, ts(2026, 11, 17, 23, 0))
    assert am is not None and pm is not None
    assert am.n_bus >= 1 and all(l.kind in ("walk", "bus") for l in am.legs)
    assert abs(am.total_s - pm.total_s) > 60
