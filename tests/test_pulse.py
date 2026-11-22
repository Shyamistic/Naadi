"""Tests for the city-pulse summary (no feed or built network needed)."""
from __future__ import annotations

import math
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from naadi.webapi import pulse_summary, _link_rs_cache  # noqa: E402


def _net():
    # Two routes. Route 0: stops 0 -> 1 -> 2 (links 0, 1). Route 1: stops 3 -> 4 (link 2).
    return SimpleNamespace(
        rs_link=np.array([0, 1, -1, 2, -1]), rs_route=np.array([0, 0, 0, 1, 1]), rs_stop=np.array([0, 1, 2, 3, 4]),
        r_ptr=np.array([0, 3, 5]), stop_names=["A", "B", "C", "D", "E"], route_short=["405UP", "522DOWN"],
        lat=np.array([28.60, 28.61, 28.62, 28.63, 28.64]), lon=np.array([77.20, 77.21, 77.22, 77.23, 77.24]))


def test_pulse_city_ratio_slow_stretch_and_density():
    _link_rs_cache.clear()
    net = _net()
    feed = 1_795_350_000.0
    # 300 normal traversals on link 2, and 4 buses taking twice the usual time on link 1 (B -> C).
    res = [(feed - 60, 2, 0, 0.0)] * 300 + [(feed - 30, 1, 0, math.log(2.0))] * 4
    buses = [("x1", 0, 28.601, 77.201, feed, 10.0), ("x2", 0, 28.6012, 77.2011, feed, 12.0), ("x3", -1, 28.7, 77.3, feed, -1.0)]
    body = pulse_summary(buses, res, feed, 1200, net, now=feed + 5)
    assert body["stale"] is False and body["buses"] == 3 and body["on_route"] == 2
    assert body["vs_usual"] == {"ratio": 1.0, "pct": 0}           # the median stretch runs as usual
    assert len(body["slow"]) == 1
    s = body["slow"][0]
    assert (s["from"], s["to"], s["routes"], s["ratio"], s["buses"]) == ("B", "C", ["405"], 2.0, 4)
    assert s["coords"] == [[77.21, 28.61], [77.22, 28.62]]
    assert sorted(n for _, _, n in body["density"]) == [1, 2]       # two buses share one 0.01-degree cell


def test_pulse_stale_or_thin_feed_shows_no_comparison():
    _link_rs_cache.clear()
    net = _net()
    feed = 1_795_350_000.0
    stale = pulse_summary([], [(feed, 1, 0, 1.0)] * 500, feed, 1200, net, now=feed + 3600)
    assert stale["stale"] is True and stale["vs_usual"] is None and stale["slow"] == []
    thin = pulse_summary([], [(feed, 1, 0, 0.1)] * 50, feed, 1200, net, now=feed)
    assert thin["vs_usual"] is None                                 # fewer than 200 traversals


def test_pulse_compares_with_the_hours_ordinary_baseline():
    _link_rs_cache.clear()
    net = _net()
    feed = 1_795_350_000.0          # a Sunday, 17:30 IST
    hour = int(((feed + 19800) % 86400) // 3600)
    ordinary = -0.06                 # an ordinary day's median residual at this hour
    baseline = {"weekend": {"median_r": [ordinary] * 24}, "weekday": {"median_r": [0.0] * 24}}
    as_usual = pulse_summary([], [(feed, 2, 0, ordinary)] * 300, feed, 1200, net, now=feed, baseline=baseline)
    assert as_usual["day_type"] == "weekend" and as_usual["hour"] == hour
    assert as_usual["vs_usual"]["pct"] == 0                   # an ordinary moment reads "as usual", not "6% faster"
    slower = pulse_summary([], [(feed, 2, 0, ordinary + math.log(1.2))] * 300, feed, 1200, net, now=feed, baseline=baseline)
    assert slower["vs_usual"]["pct"] == 20
