"""Live engine: turns GTFS-RT snapshots into bus positions on routes, link residuals and next-bus ETAs.

Every snapshot (about every 11 s):
  1. Each bus is projected onto its route's shape (nearest segment within 60 m), giving metres along the route.
  2. When a bus moves forward past stops, crossing times are interpolated; two consecutive crossings give a
     completed link traversal, compared with the model: residual = ln(observed) - ln(model).
  3. Residuals from the last 30 min feed the nowcast (naadi/nowcast.py), which corrects ride times for routing.
  4. Next-bus ETAs at a stop come from every source unit upstream on a serving route: remaining model ride time,
     corrected by the nowcast, minus the age of the GPS fix.
Source identities stay inside this module; anything returned uses a salted hash.
"""
from __future__ import annotations

import hashlib
import math
import os
import threading
import time
from collections import deque
from pathlib import Path

import numpy as np
from numba import njit

from .network import Network
from .nowcast import NowcastParams

KX, KY = 111320.0 * 0.8780, 110574.0
SNAP_M = 60.0
IST_S = 19800
SALT = os.environ.get("NAADI_SALT", "naadi-2026")


@njit(cache=True)
def _project(px, py, rid, shp_ptr, sx, sy, sd):
    n = len(px)
    out_d = np.full(n, -1.0)
    out_off = np.full(n, 1e9)
    for i in range(n):
        r = rid[i]
        if r < 0:
            continue
        a, b = shp_ptr[r], shp_ptr[r + 1]
        best, bd = 1e18, -1.0
        for j in range(a, b - 1):
            x1, y1, x2, y2 = sx[j], sy[j], sx[j + 1], sy[j + 1]
            dx, dy = x2 - x1, y2 - y1
            L2 = dx * dx + dy * dy
            if L2 <= 0:
                continue
            t = ((px[i] - x1) * dx + (py[i] - y1) * dy) / L2
            t = min(1.0, max(0.0, t))
            ex, ey = x1 + t * dx - px[i], y1 + t * dy - py[i]
            e = ex * ex + ey * ey
            if e < best:
                best = e
                bd = sd[j] + t * (sd[j + 1] - sd[j])
        out_off[i] = math.sqrt(best)
        out_d[i] = bd
    return out_d, out_off


def public_id(unit_key: str) -> str:
    return hashlib.sha256((SALT + unit_key).encode()).hexdigest()[:10]


def upcoming(net, buses, now, rs_list, t_at_stop, cum_h, max_ahead_s=3600):
    """Return upcoming bus arrivals as (route-stop, ETA, anonymised id)."""
    out = []
    by_route = {}
    for b in buses:
        if b[1] >= 0 and b[5] >= 0:
            by_route.setdefault(b[1], []).append(b)
    for rs in rs_list:
        r = int(net.rs_route[rs])
        a = int(net.r_ptr[r])
        sd_stop = float(net.rs_sd[rs])
        for pid, _, _, _, ts, d in by_route.get(r, []):
            if d > sd_stop + 20:
                continue
            k = int(np.searchsorted(net.rs_sd[a:rs + 1], d, side="right")) - 1 + a
            k = max(a, min(k, rs))
            frac = 0.0
            if k < rs:
                seg = float(net.rs_sd[k + 1] - net.rs_sd[k])
                frac = (d - float(net.rs_sd[k])) / seg if seg > 0 else 0.0
            remain = float(cum_h[rs] - cum_h[k]) - frac * float(cum_h[min(k + 1, rs)] - cum_h[k])
            eta = ts + max(remain, 0.0)
            if eta >= now - 60 and eta - now <= max_ahead_s:
                out.append((rs, eta, pid))
    out.sort(key=lambda x: x[1])
    return out


class LiveEngine:
    def __init__(self, net: Network, grid, cell_of_link: np.ndarray, snapshot_path: Path, params: NowcastParams):
        self.net, self.grid, self.cell_of_link, self.path, self.p = net, grid, cell_of_link, snapshot_path, params
        self.sx = (net.shp_lon.astype(np.float64) * KX)
        self.sy = (net.shp_lat.astype(np.float64) * KY)
        self.sd = net.shp_d.astype(np.float64)
        self.lock = threading.Lock()
        self.state: dict[str, tuple] = {}         # vehicle -> (route idx, t, d)
        self.res: deque = deque()                 # (t_end, link, cell, residual)
        self.buses = []                           # latest positions
        self.feed_ts = 0
        self.last_mtime = 0.0
        self.stats = {"snapshots": 0, "traversals": 0}

    # ---- ingestion
    def poll(self) -> bool:
        try:
            m = self.path.stat().st_mtime
        except FileNotFoundError:
            return False
        if m == self.last_mtime:
            return False
        self.last_mtime = m
        from google.transit import gtfs_realtime_pb2
        f = gtfs_realtime_pb2.FeedMessage()
        f.ParseFromString(self.path.read_bytes())
        if len(f.entity) < 10:
            return False
        self.ingest(f)
        return True

    def ingest(self, feed) -> None:
        net = self.net
        vid, rid, ts, lat, lon = [], [], [], [], []
        for e in feed.entity:
            if not e.HasField("vehicle"):
                continue
            v = e.vehicle
            try:
                r = net.route_index.get(int(v.trip.route_id), -1)
            except ValueError:
                r = -1
            vid.append(v.vehicle.id or e.id); rid.append(r); ts.append(v.timestamp)
            lat.append(v.position.latitude); lon.append(v.position.longitude)
        rid = np.array(rid, np.int64); ts = np.array(ts, np.float64)
        lat = np.array(lat); lon = np.array(lon)
        d, off = _project(lon * KX, lat * KY, rid, net.shp_ptr.astype(np.int64), self.sx, self.sy, self.sd)
        now = float(feed.header.timestamp or time.time())
        buses = []
        new_res = []
        with self.lock:
            for i, v in enumerate(vid):
                r = int(rid[i])
                fresh = now - ts[i] < 300
                on = r >= 0 and off[i] <= SNAP_M and fresh
                if on:
                    prev = self.state.get(v)
                    if prev and prev[0] == r and 0 < ts[i] - prev[1] <= 120 and d[i] > prev[2]:
                        new_res += self._crossings(r, prev[1], prev[2], ts[i], d[i], v)
                    if prev is None or prev[0] != r or ts[i] > prev[1]:
                        self.state[v] = (r, float(ts[i]), float(d[i]))
                if fresh:
                    buses.append((public_id(v), r, float(lat[i]), float(lon[i]), float(ts[i]), float(d[i]) if on else -1.0))
            self.buses = buses
            self.feed_ts = now
            for x in new_res:
                self.res.append(x)
            cutoff = now - 2 * self.p.window_s
            while self.res and self.res[0][0] < cutoff:
                self.res.popleft()
            self.stats["snapshots"] += 1
            self.stats["traversals"] += len(new_res)

    def _crossings(self, r, t0, d0, t1, d1, v):
        """Link traversals completed by a bus moving from d0 to d1; uses pending crossings per vehicle."""
        net = self.net
        a, b = int(net.r_ptr[r]), int(net.r_ptr[r + 1])
        sd = net.rs_sd[a:b]
        out = []
        k0 = np.searchsorted(sd, d0, side="right")
        k1 = np.searchsorted(sd, d1, side="right")
        pend = getattr(self, "_pending", None)
        if pend is None:
            self._pending = pend = {}
        for kk in range(k0, k1):
            tc = t0 + (sd[kk] - d0) / (d1 - d0) * (t1 - t0)
            last = pend.get(v)
            if last and last[0] == r and last[1] == kk - 1 and 5 <= tc - last[2] <= 1800:
                li = int(net.rs_link[a + kk - 1])
                if li >= 0:
                    we = int(((math.floor((last[2] + IST_S) / 86400) + 3) % 7) >= 5)
                    model = float(self.grid.log_tt("gbm", np.array([li]), np.array([we]), np.array([last[2]]))[0])
                    out.append((tc, li, int(self.cell_of_link[li]), math.log(tc - last[2]) - model))
            pend[v] = (r, kk, tc)
        return out

    # ---- queries
    def nowcast_mult(self, t_now: float, hours=24) -> np.ndarray | None:
        """(24, n_links) ride-time multipliers for routing from t_now; None without live data."""
        with self.lock:
            if not self.res or t_now - self.feed_ts > 600:
                return None
            arr = np.array([x for x in self.res if x[0] >= t_now - self.p.window_s and x[0] <= t_now])
        n_links = self.grid.g["gbm"].shape[0]
        if len(arr) == 0:
            return None
        li, ce, r = arr[:, 1].astype(np.int64), arr[:, 2].astype(np.int64), arr[:, 3]
        sl = np.bincount(li, r, n_links); nl = np.bincount(li, minlength=n_links).astype(float)
        nc_ = int(self.cell_of_link.max()) + 1
        sc = np.bincount(ce, r, nc_); ncn = np.bincount(ce, minlength=nc_).astype(float)
        r_cell = (sc / (ncn + self.p.k_cell))[self.cell_of_link]
        r_link = (sl + self.p.k_link * r_cell) / (nl + self.p.k_link)
        mult = np.ones((24, n_links), np.float32)
        h_now = ((t_now + IST_S) % 86400) / 3600
        for h in range(24):
            ahead = ((h + 0.5 - h_now) % 24) * 3600
            if ahead > 6 * 3600:
                continue
            mult[h] = np.exp(r_link * math.exp(-ahead / self.p.tau_s))
        return mult

    def summary(self):
        with self.lock:
            n = len(self.buses)
            on = sum(1 for b in self.buses if b[5] >= 0)
            return {"feed_ts": self.feed_ts, "buses": n, "on_route": on, "residuals_30min": sum(
                1 for x in self.res if x[0] >= self.feed_ts - self.p.window_s), **self.stats}

    def next_buses(self, rs_list, t_at_stop: float, cum_h, max_ahead_s=3600):
        """For route-stops rs_list, upcoming live buses: list of (rs, eta_unix, public_id)."""
        with self.lock:
            return upcoming(self.net, self.buses, self.feed_ts, rs_list, t_at_stop, cum_h, max_ahead_s)
