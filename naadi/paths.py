"""Shared project and data paths.

REPO is the checkout with code, validation/ and docs/. DATA is NAADI_ROOT/data
when NAADI_ROOT is set (the server and agent worktrees), otherwise REPO/data.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("NAADI_ROOT") or REPO)
DATA = ROOT / "data"
PROCESSED = DATA / "processed"
WORK = PROCESSED / "speed_tables" / "_work"
GTFS = PROCESSED / "gtfs_fixed" / "bus_v1-2"
METRO_GTFS = PROCESSED / "gtfs_fixed" / "metro"
MODEL = PROCESSED / "model"
L2 = PROCESSED / "gps_l2"
ROWS = PROCESSED / "validation"
RAW = DATA / "raw"
ETA = RAW / "eta_s3"
TMP = DATA / "tmp_duckdb"
RESULTS = REPO / "validation" / "results"
