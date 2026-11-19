"""Static gzip trail files for the Road speeds play-the-day view."""
from __future__ import annotations

import gzip
import json
import re
from pathlib import Path
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

ROOT = Path(os.environ.get("NAADI_ROOT", Path(__file__).resolve().parents[1]))

router = APIRouter(prefix="/trails", tags=["trails"])
TRAILS = ROOT / "data" / "processed" / "model" / "trails_v1"
CACHE = {"Cache-Control": "public, max-age=86400"}


def _gzip_json(path: Path) -> Response:
    if not path.is_file():
        raise HTTPException(404, "Trail data not found.")
    body = path.read_bytes() if path.suffix == ".gz" else gzip.compress(path.read_bytes(), compresslevel=6, mtime=0)
    return Response(body, media_type="application/json", headers={**CACHE, "Content-Encoding": "gzip"})


@router.get("/index")
def trail_index():
    return _gzip_json(TRAILS / "index.json")


@router.get("/{day_type}/{hour}")
def trail_chunk(day_type: str, hour: int):
    if day_type not in ("weekday", "weekend") or not 0 <= hour <= 23:
        raise HTTPException(404, "Unknown trail chunk.")
    return _gzip_json(TRAILS / f"{day_type}_{hour:02d}.json.gz")
