"""Transport Stack SLM2-shaped adapter.

GET /v2/get_multi_modal?src=[lat,lon]&src_type=place&dst=[lat,lon]&dst_type=place&mode=bus|metro|multi&time=HH:MM:SS
returns ``journeys`` containing the same option objects as Naadi's native endpoint,
plus ``query`` and ``source`` metadata. This keeps the organiser integration thin:
callers can consume each option's legs, expected duration, and arrival time without
knowing Naadi's internal planner classes.
"""
from __future__ import annotations

import datetime as dt
import json

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def _point(value: str, name: str) -> tuple[float, float]:
    try:
        point = json.loads(value)
        if not isinstance(point, list) or len(point) != 2:
            raise ValueError
        lat, lon = float(point[0]), float(point[1])
    except (TypeError, ValueError, json.JSONDecodeError):
        raise HTTPException(400, f"{name} must be a JSON [lat,lon] array.")
    return lat, lon


@router.get("/v2/get_multi_modal")
def get_multi_modal(src: str = Query(...), src_type: str = Query("place"), dst: str = Query(...),
                    dst_type: str = Query("place"), mode: str = Query("multi"), time: str = Query(...)):
    if src_type != "place" or dst_type != "place":
        raise HTTPException(400, "src_type and dst_type must be 'place'.")
    if mode not in {"bus", "metro", "multi"}:
        raise HTTPException(400, "mode must be bus, metro, or multi.")
    try:
        clock = dt.time.fromisoformat(time)
    except ValueError:
        raise HTTPException(400, "time must be HH:MM:SS.")
    day = dt.datetime.now(IST).date()
    depart = dt.datetime.combine(day, clock, tzinfo=IST).isoformat(timespec="seconds")
    from . import api
    origin = _point(src, "src")
    destination = _point(dst, "dst")
    modes = "bus" if mode == "bus" else "bus,metro"
    body = api.journeys(f"{origin[0]},{origin[1]}", f"{destination[0]},{destination[1]}", depart=depart,
                        arrive=None, options=3, modes=modes)
    journeys = list(body.get("options", []))
    if mode != "bus":
        journeys.extend(body.get("multimodal_options", []))
    return {"journeys": journeys, "query": {"src": [origin[0], origin[1]], "dst": [destination[0], destination[1]],
                                               "mode": mode, "time": time},
            "source": "Naadi journey planner", "count": len(journeys),
            "multimodal_note": body.get("multimodal_note")}
