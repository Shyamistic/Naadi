"""Dense in-memory access to the per-link, per-hour prediction grid.

Links are numbered so that (route, ord) and (route, ord + 1) are consecutive integers, which lets a
multi-stop ride be predicted by stepping idx, idx + 1, ... while carrying the clock forward.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

IST_S = 19800
METHODS = ("tt", "city", "ha", "eb", "gbm")


class LinkGrid:
    def __init__(self, path: Path, methods=METHODS):
        t = pq.read_table(path).sort_by([("route_id", "ascending"), ("ord", "ascending"),
                                          ("we", "ascending"), ("hour", "ascending")])
        n = t.num_rows // 48
        route = t["route_id"].to_numpy()[::48]
        ordn = t["ord"].to_numpy()[::48]
        self.route, self.ord = route.astype(np.int32), ordn.astype(np.int32)
        self.dist = t["dist_m"].to_numpy()[::48].astype(np.float32)
        self.n_hist = t["n"].to_numpy().reshape(n, 2, 24).astype(np.int32)
        self.g = {m: t[m].to_numpy().reshape(n, 2, 24).astype(np.float32) for m in methods}
        self.sd = t["sd"].to_numpy().reshape(n, 2, 24).astype(np.float32)
        key = route.astype(np.int64) * 10000 + ordn
        self._key = key
        # last link of each route has no successor on the same route
        self.has_next = np.zeros(n, dtype=bool)
        self.has_next[:-1] = (route[1:] == route[:-1]) & (ordn[1:] == ordn[:-1] + 1)

    def index(self, route_id, ord_) -> np.ndarray:
        """Link index for (route_id, ord) arrays; -1 where the link is unknown."""
        k = np.asarray(route_id, dtype=np.int64) * 10000 + np.asarray(ord_, dtype=np.int64)
        i = np.searchsorted(self._key, k)
        i = np.clip(i, 0, len(self._key) - 1)
        return np.where(self._key[i] == k, i, -1)

    @staticmethod
    def hour_weights(ts: np.ndarray):
        """Linear interpolation between hour centres for unix times ts (IST hour of day)."""
        x = ((np.asarray(ts, dtype=np.float64) + IST_S) % 86400) / 3600.0 - 0.5
        h0 = np.floor(x)
        w = (x - h0).astype(np.float32)
        h0 = (h0.astype(np.int64)) % 24
        return h0, (h0 + 1) % 24, w

    def log_tt(self, method: str, idx: np.ndarray, we: np.ndarray, ts: np.ndarray) -> np.ndarray:
        g = self.g[method]
        h0, h1, w = self.hour_weights(ts)
        return (1 - w) * g[idx, we, h0] + w * g[idx, we, h1]

    def log_sd(self, idx, we, ts):
        h0, h1, w = self.hour_weights(ts)
        return (1 - w) * self.sd[idx, we, h0] + w * self.sd[idx, we, h1]
