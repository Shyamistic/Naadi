"""Walking lookup tests; they use a tiny fixture and never need an OSM parser."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from naadi.walk import DETOUR, WALK_MS, WalkLookup, fallback_seconds


def fixture(tmp_path: Path) -> Path:
    out = tmp_path / "walk_v1"
    out.mkdir()
    np.savez_compressed(out / "targets.npz", ids=np.array(["A", "B", "station:X"]), lat=np.array([28.0, 28.0, 28.005]), lon=np.array([77.0, 77.005, 77.0]))
    np.savez_compressed(out / "pairs.npz", src=np.array([0], np.int32), dst=np.array([1], np.int32), seconds=np.array([321.0], np.float32))
    np.savez_compressed(out / "access.npz", lat=np.array([28.0]), lon=np.array([77.0]), ptr=np.array([0, 2], np.int32), idx=np.array([0, 2], np.int32), seconds=np.array([12.0, 88.0], np.float32))
    (out / "meta.json").write_text(json.dumps({"version": "walk_v1"}), encoding="utf-8")
    return out


def test_network_pair_and_symmetric_fallback(tmp_path):
    lookup = WalkLookup(fixture(tmp_path))
    assert lookup.walk_time("A", "B") == pytest.approx(321.0)
    expected = fallback_seconds(28.0, 77.005, 28.0, 77.0)
    assert lookup.walk_time("B", "A") == pytest.approx(expected)
    assert expected > 0 and DETOUR / WALK_MS > 1


def test_access_returns_stops_and_stations(tmp_path):
    lookup = WalkLookup(fixture(tmp_path))
    assert lookup.access(28.0, 77.0) == [("A", 12.0), ("station:X", 88.0)]


def test_unknown_target_is_explicit(tmp_path):
    lookup = WalkLookup(fixture(tmp_path))
    with pytest.raises(KeyError):
        lookup.walk_time("missing", "A")
