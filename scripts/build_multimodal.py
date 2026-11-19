"""Build the bus plus schedule-estimated metro network."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from naadi.multimodal import build_multimodal  # noqa: E402
from naadi.paths import METRO_GTFS, MODEL  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bus", default="network_prod")
    ap.add_argument("--name", default="prod_mm")
    ap.add_argument("--gtfs", type=Path, default=METRO_GTFS)
    a = ap.parse_args()
    build_multimodal(MODEL / a.bus, a.gtfs, MODEL / f"network_{a.name}" if not a.name.startswith("network_") else MODEL / a.name)
