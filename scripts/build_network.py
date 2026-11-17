"""Build the routable network from a link-prediction grid and a service table.

Usage: python scripts/build_network.py --grid grid_oct01_24 --service service_oct01_24 --name eval_oct
Writes data/processed/model/network_<name>/
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from naadi.network import MODEL, build  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", required=True)
    ap.add_argument("--service", required=True)
    ap.add_argument("--name", required=True)
    a = ap.parse_args()
    build(MODEL / f"{a.grid}.parquet", MODEL / f"{a.service}.parquet", MODEL / f"network_{a.name}")
