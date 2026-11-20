"""Street-network walking lookups built from OSM.

The shipped table is deliberately read-only and numpy-only so the API server does
not need an OSM library.  Missing pairs use Naadi's former straight-line rule.
"""
from __future__ import annotations

import csv
import json
import math
import os
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "data" / "processed" / "model" / "walk_v1"
WALK_MS = 1.25
DETOUR = 1.35
MAX_ACCESS_M = 1200.0


def haversine(lat1: Any, lon1: Any, lat2: Any, lon2: Any) -> np.ndarray:
    a1, o1, a2, o2 = (np.radians(np.asarray(x, dtype=np.float64)) for x in (lat1, lon1, lat2, lon2))
    a = np.sin((a2 - a1) / 2) ** 2 + np.cos(a1) * np.cos(a2) * np.sin((o2 - o1) / 2) ** 2
    return 12742000.0 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def fallback_seconds(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return float(haversine(lat1, lon1, lat2, lon2) * DETOUR / WALK_MS)


def _key(value: Any) -> str:
    return str(value).strip()


class WalkLookup:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        meta_path = self.directory / "meta.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"walking artefact not found: {self.directory}")
        self.meta = json.loads(meta_path.read_text(encoding="utf-8"))
        with np.load(self.directory / "targets.npz", allow_pickle=False) as z:
            self.target_ids = z["ids"].astype(str)
            self.target_lat = z["lat"].astype(np.float64)
            self.target_lon = z["lon"].astype(np.float64)
        with np.load(self.directory / "pairs.npz", allow_pickle=False) as z:
            self.pair_src = z["src"].astype(np.int32)
            self.pair_dst = z["dst"].astype(np.int32)
            self.pair_s = z["seconds"].astype(np.float32)
        with np.load(self.directory / "access.npz", allow_pickle=False) as z:
            self.grid_lat = z["lat"].astype(np.float64)
            self.grid_lon = z["lon"].astype(np.float64)
            self.access_ptr = z["ptr"].astype(np.int32)
            self.access_idx = z["idx"].astype(np.int32)
            self.access_s = z["seconds"].astype(np.float32)
        self.target_index = {_key(v): i for i, v in enumerate(self.target_ids.tolist())}
        self._pair_index = {(int(a), int(b)): float(s) for a, b, s in zip(self.pair_src, self.pair_dst, self.pair_s)}

    def _coordinates(self, value: Any) -> tuple[float, float] | None:
        i = self.target_index.get(_key(value))
        if i is None:
            return None
        return float(self.target_lat[i]), float(self.target_lon[i])

    def walk_time(self, stop_a: Any, stop_b: Any) -> float:
        ia, ib = self.target_index.get(_key(stop_a)), self.target_index.get(_key(stop_b))
        if ia is not None and ib is not None:
            value = self._pair_index.get((ia, ib))
            if value is not None and math.isfinite(value):
                return value
        a, b = self._coordinates(stop_a), self._coordinates(stop_b)
        if a is None or b is None:
            raise KeyError(f"unknown walking target: {stop_a!r} or {stop_b!r}")
        return fallback_seconds(*a, *b)

    def access(self, lat: float, lon: float) -> list[tuple[str, float]]:
        if not self.grid_lat.size:
            return []
        # The 150 m grid keeps the server table compact; query the nearest cell.
        d = haversine(lat, lon, self.grid_lat, self.grid_lon)
        row = int(np.argmin(d))
        out: list[tuple[str, float]] = []
        for j, seconds in zip(self.access_idx[self.access_ptr[row]:self.access_ptr[row + 1]], self.access_s[self.access_ptr[row]:self.access_ptr[row + 1]]):
            if np.isfinite(seconds):
                out.append((str(self.target_ids[int(j)]), float(seconds)))
        if out:
            return out
        # A sparse/disconnected graph must not make access disappear.
        for i in np.flatnonzero(d <= MAX_ACCESS_M):
            out.append((str(self.target_ids[int(i)]), fallback_seconds(lat, lon, self.target_lat[i], self.target_lon[i])))
        return sorted(out, key=lambda x: x[1])


_DEFAULT: WalkLookup | None = None


def load(directory: str | Path | None = None) -> WalkLookup:
    global _DEFAULT
    path = Path(directory or os.environ.get("NAADI_WALK_DIR", DEFAULT_DIR))
    if _DEFAULT is None or _DEFAULT.directory != path:
        _DEFAULT = WalkLookup(path)
    return _DEFAULT


def walk_time(stop_a: Any, stop_b: Any) -> float:
    return load().walk_time(stop_a, stop_b)


def access(lat: float, lon: float) -> list[tuple[str, float]]:
    return load().access(float(lat), float(lon))
