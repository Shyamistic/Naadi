from __future__ import annotations

import pyarrow as pa
import pyarrow.parquet as pq

from naadi.fares import FareModel


def test_empirical_cell_returns_observed_fare(tmp_path):
    path = tmp_path / "fare_table.parquet"
    pq.write_table(pa.table({
        "route_id": [8], "boarding_stop_id": [101], "alighting_stop_id": [202],
        "is_ac": [True], "fare_inr": [13.5], "n": [25], "total_n": [30], "modal_share": [5 / 6],
    }), path)
    quote = FareModel(path).fare_for_leg(8, 101, 202, True, 20000)
    assert quote.cash_fare_inr == 25.0
    assert quote.app_fare_inr == 13.5
    assert quote.source == "empirical"


def test_missing_cell_uses_official_slab():
    model = FareModel()
    assert model.fare_for_leg(1, 2, 3, False, 3000).as_dict() == {"cash_fare_inr": 5.0, "app_fare_inr": 4.5, "source": "slab_app_discount"}
    quote = model.fare_for_leg(1, 2, 3, True, 9000)
    assert quote.cash_fare_inr == 20.0 and quote.app_fare_inr == 18.0


def test_ac_share_selects_ac_table(tmp_path):
    path = tmp_path / "fare_table.parquet"
    pq.write_table(pa.table({
        "route_id": [8, 8], "boarding_stop_id": [101, 101], "alighting_stop_id": [202, 202],
        "is_ac": [False, True], "fare_inr": [9.0, 13.5], "n": [20, 20], "total_n": [20, 20], "modal_share": [1.0, 1.0],
    }), path)
    quote = FareModel(path).fare_for_leg(8, 101, 202, 0.75, 9000)
    assert quote.cash_fare_inr == 20.0 and quote.app_fare_inr == 13.5
