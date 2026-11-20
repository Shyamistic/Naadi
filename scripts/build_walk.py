"""Build the OSM walking lookup.

The parser clips ways to the 28.21--29.34, 76.60--77.43 box plus 2 km while
streaming the PBF.  No OSM parser is needed by the runtime loader.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import time
from pathlib import Path

import numpy as np
import osmium
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

ROOT = Path(os.environ.get("NAADI_ROOT", Path(__file__).resolve().parents[1]))
BASE_BBOX = (28.21, 29.34, 76.60, 77.43)  # south, north, west, east
WALK_MS = 1.25
DETOUR = 1.35
CELL_M = 600.0  # compact adaptive access anchors; queries use the nearest anchor
ACCESS_M = 1200.0


def haversine(lat1, lon1, lat2, lon2):
    a1, o1, a2, o2 = (np.radians(np.asarray(x, dtype=np.float64)) for x in (lat1, lon1, lat2, lon2))
    a = np.sin((a2 - a1) / 2) ** 2 + np.cos(a1) * np.cos(a2) * np.sin((o2 - o1) / 2) ** 2
    return 12742000.0 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def projected(lat, lon, lat0=28.78):
    return np.column_stack((np.asarray(lon) * 111320.0 * math.cos(math.radians(lat0)), np.asarray(lat) * 111320.0))


def read_csv(path: Path, required=True):
    if not path.exists():
        if required:
            raise FileNotFoundError(path)
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def inside(lat, lon, margin_m=2000.0):
    s, n, w, e = BASE_BBOX
    return s - margin_m / 111320 <= lat <= n + margin_m / 111320 and w - margin_m / 98000 <= lon <= e + margin_m / 98000


def load_targets():
    targets = []
    bus = []
    bus_path = ROOT / "data/processed/gtfs_fixed/bus_v1-2/stops.txt"
    for r in read_csv(bus_path):
        lat, lon = float(r["stop_lat"]), float(r["stop_lon"])
        if inside(lat, lon):
            bus.append(len(targets))
            targets.append((str(r["stop_id"]), lat, lon, "bus"))

    def add_feed(folder: Path, prefix: str):
        p = folder / "stops.txt"
        for r in read_csv(p, required=False):
            try:
                lat, lon = float(r["stop_lat"]), float(r["stop_lon"])
            except (KeyError, TypeError, ValueError):
                continue
            if inside(lat, lon) and r.get("location_type", "0") in ("", "0", "1"):
                targets.append((f"{prefix}:{r['stop_id']}", lat, lon, prefix))

    add_feed(ROOT / "data/raw/dmrc_static_gtfs_v1", "dmrc")
    add_feed(ROOT / "data/raw/ncrtc_static_gtfs_v1", "ncrtc")
    # A station/gate workbook contains entrances that are absent from GTFS.
    workbook = ROOT / "dmrc_station_and_gate_locations.xlsx"
    try:
        from openpyxl import load_workbook
        wb = load_workbook(workbook, read_only=True, data_only=True)
        for r in list(wb["stations"].values)[1:]:
            if len(r) < 7:
                continue
            try:
                lat = float(str(r[5]).rstrip("N")); lon = float(str(r[6]).rstrip("E"))
            except (ValueError, TypeError):
                continue
            if inside(lat, lon):
                targets.append((f"station:{r[1]}", lat, lon, "station"))
        for r in list(wb["gates"].values)[1:]:
            if len(r) < 5:
                continue
            try:
                lat = float(str(r[3]).rstrip("N")); lon = float(str(r[4]).rstrip("E"))
            except (ValueError, TypeError):
                continue
            if inside(lat, lon):
                targets.append((f"gate:{r[0]}:{r[1]}", lat, lon, "gate"))
    except (ImportError, FileNotFoundError):
        pass
    # Keep the first occurrence of a target id, because GTFS feeds can repeat station parents.
    unique, seen, bus_unique = [], set(), []
    for i, item in enumerate(targets):
        if item[0] in seen:
            continue
        seen.add(item[0]); unique.append(item)
        if i in bus:
            bus_unique.append(len(unique) - 1)
    return unique, np.asarray(bus_unique, dtype=np.int32)


class OSMHandler(osmium.SimpleHandler):
    highways = {"footway", "path", "pedestrian", "steps", "living_street", "residential", "service", "unclassified", "track", "cycleway", "bridleway", "corridor", "tertiary", "secondary", "primary", "trunk"}
    excluded = {"motorway", "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link"}

    def __init__(self, bbox):
        super().__init__()
        self.bbox = bbox
        self.coords = []
        self.node_ids = {}
        self.edges = []
        self.crossings = []

    def node(self, n):
        if n.tags.get("highway") in ("crossing", "traffic_signals") and n.location.valid():
            self.crossings.append((n.location.lat, n.location.lon))

    def _node(self, n):
        key = int(n.ref)
        out = self.node_ids.get(key)
        if out is None:
            out = len(self.coords); self.node_ids[key] = out
            self.coords.append((n.location.lat, n.location.lon))
        return out

    def way(self, w):
        highway = w.tags.get("highway")
        if highway not in self.highways or highway in self.excluded or w.tags.get("foot") == "no":
            return
        points = [n for n in w.nodes if n.location.valid()]
        for a, b in zip(points, points[1:]):
            la, loa, lb, lob = a.location.lat, a.location.lon, b.location.lat, b.location.lon
            if not (inside(la, loa) or inside(lb, lob) or (min(la, lb) <= self.bbox[1] and max(la, lb) >= self.bbox[0] and min(loa, lob) <= self.bbox[3] and max(loa, lob) >= self.bbox[2])):
                continue
            u, v = self._node(a), self._node(b)
            dist = float(haversine(la, loa, lb, lob))
            if dist <= 0.1:
                continue
            # Add a small conservative delay to unmarked crossings of wide roads.
            self.edges.append((u, v, dist, highway, w.tags.get("bridge", ""), w.tags.get("tunnel", "")))


def graph_from_pbf(pbf: Path):
    margin_lat, margin_lon = 2000 / 111320, 2000 / 98000
    bbox = (BASE_BBOX[0] - margin_lat, BASE_BBOX[1] + margin_lat, BASE_BBOX[2] - margin_lon, BASE_BBOX[3] + margin_lon)
    h = OSMHandler(bbox)
    h.apply_file(str(pbf), locations=True)
    lat = np.asarray([p[0] for p in h.coords], dtype=np.float64)
    lon = np.asarray([p[1] for p in h.coords], dtype=np.float64)
    crossing_tree = cKDTree(projected(*zip(*h.crossings))) if h.crossings else None
    rows, cols, data = [], [], []
    for u, v, dist, highway, bridge, tunnel in h.edges:
        penalty = 0.0
        if highway in {"primary", "trunk"} and not bridge and not tunnel:
            if crossing_tree is None:
                penalty = 18.0
            else:
                a, b = projected([lat[u], lat[v]], [lon[u], lon[v]])
                if crossing_tree.query(a, distance_upper_bound=35)[0] == float("inf") and crossing_tree.query(b, distance_upper_bound=35)[0] == float("inf"):
                    penalty = 18.0
        seconds = dist / WALK_MS + penalty
        rows.extend((u, v)); cols.extend((v, u)); data.extend((seconds, seconds))
    # Collapse duplicate OSM ways by minimum edge time instead of summing parallel ways.
    raw = csr_matrix((data, (rows, cols)), shape=(len(lat), len(lat)))
    raw.sort_indices()
    rr, cc, dd = [], [], []
    for u in range(raw.shape[0]):
        a, b = raw.indptr[u], raw.indptr[u + 1]
        if b:
            for v in np.unique(raw.indices[a:b]):
                rr.append(u); cc.append(int(v)); dd.append(float(raw.data[a:b][raw.indices[a:b] == v].min()))
    graph = csr_matrix((dd, (rr, cc)), shape=raw.shape)
    return lat, lon, graph, len(h.edges), len(h.crossings)


def route_times(graph, source, targets, limit):
    if source < 0 or not targets:
        return np.full(len(targets), np.inf)
    values = dijkstra(graph, directed=False, indices=int(source), limit=limit)
    return values[np.asarray(targets, dtype=np.int32)]


def make_grid(target_lat, target_lon):
    # Keep only anchors that can reach a known target within the access radius.
    mlat, mlon = CELL_M / 111320, CELL_M / 98000
    ys = np.arange(BASE_BBOX[0], BASE_BBOX[1] + mlat / 2, mlat)
    xs = np.arange(BASE_BBOX[2], BASE_BBOX[3] + mlon / 2, mlon)
    yy, xx = np.meshgrid(ys, xs, indexing="ij")
    points = np.column_stack((yy.ravel(), xx.ravel()))
    near = cKDTree(projected(target_lat, target_lon)).query_ball_point(projected(points[:, 0], points[:, 1]), ACCESS_M)
    keep = np.fromiter((bool(x) for x in near), dtype=bool, count=len(points))
    return points[keep]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pbf", type=Path, default=ROOT / "data/raw/osm/northern-zone-latest.osm.pbf")
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "data/processed/model/walk_v1")
    args = ap.parse_args()
    started = time.monotonic()
    if not args.pbf.exists():
        raise SystemExit(f"missing PBF: {args.pbf}")
    targets, bus_idx = load_targets()
    tlat = np.asarray([x[1] for x in targets]); tlon = np.asarray([x[2] for x in targets])
    print(f"targets={len(targets)} bus={len(bus_idx)}", flush=True)
    lat, lon, graph, edge_count, crossing_count = graph_from_pbf(args.pbf)
    print(f"graph nodes={len(lat)} edges={edge_count} crossings={crossing_count}", flush=True)
    node_tree = cKDTree(projected(lat, lon))
    target_tree = cKDTree(projected(tlat, tlon))
    snapped = node_tree.query(projected(tlat, tlon))[1].astype(np.int32)
    pair_src, pair_dst, pair_s = [], [], []
    # Every bus-stop pair in a 600 m straight-line radius gets a network lookup.
    bus_points = projected(tlat[bus_idx], tlon[bus_idx])
    bus_tree = cKDTree(bus_points)
    for count, src in enumerate(bus_idx):
        cand_local = bus_tree.query_ball_point(projected([tlat[src]], [tlon[src]])[0], 600.0)
        cand = [int(bus_idx[j]) for j in cand_local]
        vals = route_times(graph, snapped[src], [int(snapped[j]) for j in cand], 900.0)
        for dst, value in zip(cand, vals):
            if np.isfinite(value):
                pair_src.append(src); pair_dst.append(dst); pair_s.append(value)
        if count and count % 500 == 0:
            print(f"pairs {count}/{len(bus_idx)}", flush=True)
    # Station/gate to bus stop access is included in the same pair table.
    for src in range(len(targets)):
        if src in set(bus_idx.tolist()):
            continue
        cand = target_tree.query_ball_point(projected([tlat[src]], [tlon[src]])[0], ACCESS_M)
        cand = [int(x) for x in cand if x in set(bus_idx.tolist())]
        vals = route_times(graph, snapped[src], [int(snapped[j]) for j in cand], 1800.0)
        for dst, value in zip(cand, vals):
            if np.isfinite(value):
                pair_src.append(src); pair_dst.append(dst); pair_s.append(value)
    grid = make_grid(tlat, tlon)
    access_ptr, access_idx, access_s = [0], [], []
    bus_set = set(bus_idx.tolist())
    # Access anchors retain at most the 20 closest transit targets, limiting table size.
    for q, (gla, glo) in enumerate(grid):
        cand = target_tree.query_ball_point(projected([gla], [glo])[0], ACCESS_M)
        cand = sorted((int(x) for x in cand), key=lambda x: float(haversine(gla, glo, tlat[x], tlon[x])))[:20]
        # Grid anchors use the compact fallback for each nearby target. Exact OSM routes
        # are retained for stop pairs and station/gate-to-stop links above.
        vals = haversine(gla, glo, tlat[cand], tlon[cand]) * DETOUR / WALK_MS
        for dst, value in zip(cand, vals):
            if np.isfinite(value):
                access_idx.append(dst); access_s.append(value)
        access_ptr.append(len(access_idx))
        if q and q % 500 == 0:
            print(f"access {q}/{len(grid)}", flush=True)
    args.out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.out / "targets.npz", ids=np.asarray([x[0] for x in targets]), lat=tlat, lon=tlon)
    np.savez_compressed(args.out / "pairs.npz", src=np.asarray(pair_src, np.int32), dst=np.asarray(pair_dst, np.int32), seconds=np.asarray(pair_s, np.float32))
    np.savez_compressed(args.out / "access.npz", lat=grid[:, 0], lon=grid[:, 1], ptr=np.asarray(access_ptr, np.int32), idx=np.asarray(access_idx, np.int32), seconds=np.asarray(access_s, np.float32))
    meta = {"version": "walk_v1", "bbox": BASE_BBOX, "speed_m_s": WALK_MS, "fallback_detour": DETOUR, "stop_radius_m": 600, "access_radius_m": ACCESS_M, "access_cell_m": CELL_M, "graph_nodes": int(len(lat)), "graph_edges": int(edge_count * 2), "mapped_crossings": int(crossing_count), "bus_stops": int(len(bus_idx)), "targets": int(len(targets)), "pairs": int(len(pair_s)), "access_cells": int(len(grid)), "access_entries": int(len(access_idx)), "runtime_s": round(time.monotonic() - started, 1), "source": "Geofabrik Northern Zone, clipped in streaming parser; OSM ODbL"}
    (args.out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
