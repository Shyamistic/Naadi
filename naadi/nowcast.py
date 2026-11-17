"""Live nowcast: how much slower or faster than usual are buses on a link right now.

Each completed traversal gives a residual r = ln(observed time) - ln(historical prediction).
For a query at time t0 on link L (road cell C), with residuals from the last W seconds:
    r_cell = S_C / (n_C + k_cell)
    r_link = (S_L + k_link * r_cell) / (n_L + k_link)
and the correction applied to a link the bus reaches at time te >= t0 is r_link * exp(-(te - t0) / tau).
With no recent buses the correction is 0, so the model falls back to history alone.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class NowcastParams:
    window_s: float = 1800.0
    k_link: float = 3.0
    k_cell: float = 6.0
    tau_s: float = 1800.0


class ResidualIndex:
    """Sorted (group, end_time) residual store with O(log n) window sums."""

    def __init__(self, group: np.ndarray, t_end: np.ndarray, res: np.ndarray, t_ref: float):
        rel = np.round(np.asarray(t_end, dtype=np.float64) - t_ref).astype(np.int64)
        key = np.asarray(group, dtype=np.int64) * (1 << 31) + rel
        o = np.argsort(key, kind="stable")
        self.key = key[o]
        self.cs = np.concatenate([[0.0], np.cumsum(np.asarray(res, dtype=np.float64)[o])])
        self.t_ref = t_ref

    def window(self, group: np.ndarray, t0: np.ndarray, w: float):
        g = np.asarray(group, dtype=np.int64) * (1 << 31)
        hi_t = np.round(np.asarray(t0, dtype=np.float64) - self.t_ref).astype(np.int64)
        lo = np.searchsorted(self.key, g + hi_t - int(w), side="left")
        hi = np.searchsorted(self.key, g + hi_t, side="left")
        return self.cs[hi] - self.cs[lo], (hi - lo).astype(np.float64)


def correction(p: NowcastParams, link_idx: ResidualIndex, cell_idx: ResidualIndex,
               link: np.ndarray, cell: np.ndarray, t0: np.ndarray, te: np.ndarray) -> np.ndarray:
    sl, nl = link_idx.window(link, t0, p.window_s)
    sc, nc = cell_idx.window(cell, t0, p.window_s)
    r_cell = sc / (nc + p.k_cell)
    r_link = (sl + p.k_link * r_cell) / (nl + p.k_link)
    return r_link * np.exp(-np.maximum(np.asarray(te) - np.asarray(t0), 0.0) / p.tau_s)
