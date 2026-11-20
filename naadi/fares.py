"""Observed October 2026 fares with an official-slab fallback.

The empirical table contains only aggregate route/OD/AC cells. It does not
contain vehicle identifiers or raw ticket rows.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
from typing import Union

import pyarrow.parquet as pq


ACValue = Union[bool, int, float]
ROOT = Path(os.environ.get("NAADI_ROOT", Path(__file__).resolve().parents[1]))
DEFAULT_TABLE = ROOT / "data" / "processed" / "model" / "fares_v1" / "fare_table.parquet"


@dataclass(frozen=True)
class FareQuote:
    fare_inr: float
    source: str

    def as_dict(self) -> dict[str, float | str]:
        return {"fare_inr": self.fare_inr, "source": self.source}


class FareModel:
    def __init__(self, table_path: Path = DEFAULT_TABLE):
        self.table_path = Path(table_path)
        self._table: dict[tuple[int, int, int, bool], float] = {}
        if self.table_path.exists():
            table = pq.read_table(self.table_path, columns=[
                "route_id", "boarding_stop_id", "alighting_stop_id", "is_ac", "fare_inr"
            ])
            for row in table.to_pylist():
                self._table[(int(row["route_id"]), int(row["boarding_stop_id"]),
                             int(row["alighting_stop_id"]), bool(row["is_ac"] or False))] = float(row["fare_inr"])

    @staticmethod
    def _is_ac(value: ACValue) -> bool:
        # A share is useful when the route's fleet is mixed. The threshold
        # makes the choice deterministic and keeps the public API scalar.
        return float(value) >= 0.5

    @staticmethod
    def _slab(distance_m: float, is_ac: bool) -> float:
        km = max(0.0, float(distance_m)) / 1000.0
        if is_ac:
            return float(10 if km <= 4 else 15 if km <= 8 else 20 if km <= 12 else 25)
        return float(5 if km <= 4 else 10 if km <= 10 else 15)

    def fare_for_leg(self, route_id: int, boarding_stop_id: int,
                     alighting_stop_id: int, is_ac: ACValue,
                     shape_distance_m: float) -> FareQuote:
        ac = self._is_ac(is_ac)
        key = (int(route_id), int(boarding_stop_id), int(alighting_stop_id), ac)
        observed = self._table.get(key)
        if observed is not None:
            return FareQuote(observed, "empirical")
        return FareQuote(round(0.9 * self._slab(shape_distance_m, ac), 2), "slab_app_discount")


_MODEL: FareModel | None = None
_MODEL_PATH: Path | None = None


def fare_for_leg(route_id: int, boarding_stop_id: int, alighting_stop_id: int,
                 is_ac: ACValue, shape_distance_m: float) -> FareQuote:
    """Return the charged fare for one bus leg and its provenance.

    ``is_ac`` accepts a boolean AC flag or an AC share in [0, 1]. A share of
    at least 0.5 selects the AC table. Missing empirical cells use the official
    distance slabs with the observed 10% One Delhi app discount.
    """
    global _MODEL, _MODEL_PATH
    path = Path(os.environ.get("NAADI_FARES", DEFAULT_TABLE))
    if _MODEL is None or _MODEL_PATH != path:
        _MODEL, _MODEL_PATH = FareModel(path), path
    return _MODEL.fare_for_leg(route_id, boarding_stop_id, alighting_stop_id, is_ac, shape_distance_m)
