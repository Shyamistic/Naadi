"""Historical travel-time tables for the model, built from link traversals of chosen days.

A "link" is one stop-to-stop hop of one route (route_id, ord). Tables, by IST hour x day type:
  link_h  route_id, ord                 count, median and quantiles of travel time (s), mean/sd of log time
  link_a  route_id, ord                 the same over all hours and both day types
  pair_h  from_stop, to_stop            pooled over every route serving the same stop pair
  cell_h  ~500 m grid cell x heading     pace (s/km), pooled over all routes on that stretch of road
  city_h  hour x day type               city-wide pace
plus geom.parquet: per link the stops, along-route length, grid cell and heading.

Thin cells borrow strength level by level: link-hour -> stop pair -> road cell -> city.
Aggregation runs in chunks (key modulus) so it fits in memory and temp disk.

Usage: python scripts/model_tables.py --name oct01_24 --from 2026_10_01 --to 2026_10_24
Writes data/processed/model/tables/<name>/*.parquet
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "data" / "processed" / "speed_tables" / "_work"
GTFS = ROOT / "data" / "processed" / "gtfs_fixed" / "bus_v1-2"
OUT = ROOT / "data" / "processed" / "model" / "tables"
TMP = ROOT / "data" / "tmp_duckdb"
CELL_LAT, CELL_LON = 0.0045, 0.0051  # ~500 m
CHUNKS = 8


def build_geom(con: duckdb.DuckDBPyConnection, out: Path) -> None:
    f = out / "geom.parquet"
    con.execute(f"""
        COPY (
        WITH s AS (
            SELECT o.route_id, o.ord, CAST(o.stop_id AS INTEGER) AS stop_id, o.sd,
                   CAST(p.stop_lat AS DOUBLE) lat, CAST(p.stop_lon AS DOUBLE) lon
            FROM read_parquet('{(WORK / "stops_on_shape.parquet").as_posix()}') o
            JOIN read_csv('{(GTFS / "stops.txt").as_posix()}', all_varchar=true) p USING (stop_id)
        ), l AS (
            SELECT route_id, ord, stop_id AS from_stop, lat AS lat1, lon AS lon1, sd,
                   lead(stop_id) OVER w AS to_stop, lead(lat) OVER w AS lat2, lead(lon) OVER w AS lon2,
                   lead(sd) OVER w AS sd2, lead(ord) OVER w AS ord2
            FROM s WINDOW w AS (PARTITION BY route_id ORDER BY ord)
        )
        SELECT route_id, ord, from_stop, to_stop, sd AS sd1, sd2, sd2 - sd AS dist_m,
               lat1, lon1, lat2, lon2,
               CAST(floor((lat1 + lat2) / 2 / {CELL_LAT}) AS INTEGER) AS gy,
               CAST(floor((lon1 + lon2) / 2 / {CELL_LON}) AS INTEGER) AS gx,
               CAST(floor(((degrees(atan2((lon2 - lon1) * 0.878, lat2 - lat1)) + 360 + 22.5) % 360) / 45) AS INTEGER) % 8 AS hd
        FROM l WHERE to_stop IS NOT NULL AND ord2 = ord + 1 AND sd2 > sd
        ) TO '{f.as_posix()}' (FORMAT parquet, COMPRESSION zstd)
    """)


def build(con: duckdb.DuckDBPyConnection, d0: str, d1: str, out: Path) -> dict:
    files = sorted(p.as_posix() for p in (WORK / "links").glob("day=*.parquet") if d0 <= p.stem.split("=")[1] <= d1)
    if not files:
        raise SystemExit(f"no link files between {d0} and {d1}")
    src = "[" + ", ".join(f"'{f}'" for f in files) + "]"
    lk = out / "_lk.parquet"
    con.execute(f"""
        COPY (
            SELECT l.route_id, l.ord, g.from_stop, g.to_stop, CAST(l.hour AS TINYINT) AS hour,
                   (l.daytype = 'weekend')::TINYINT AS we, CAST(l.tt_s AS FLOAT) AS tt,
                   CAST(ln(l.tt_s) AS FLOAT) AS ltt, CAST(ln(l.tt_s / (l.dist_m / 1000)) AS FLOAT) AS lpace,
                   g.gy, g.gx, CAST(g.hd AS TINYINT) AS hd
            FROM read_parquet({src}) l JOIN read_parquet('{(out / "geom.parquet").as_posix()}') g USING (route_id, ord)
        ) TO '{lk.as_posix()}' (FORMAT parquet, COMPRESSION zstd)
    """)
    L = f"read_parquet('{lk.as_posix()}')"
    full = ("count(*)::INTEGER AS n, CAST(median(tt) AS FLOAT) AS tt_med, CAST(quantile_cont(tt, 0.1) AS FLOAT) AS tt_q10, "
            "CAST(quantile_cont(tt, 0.9) AS FLOAT) AS tt_q90, CAST(avg(ltt) AS FLOAT) AS ltt_mean, "
            "CAST(coalesce(stddev_samp(ltt), 0) AS FLOAT) AS ltt_sd")
    lite = "count(*)::INTEGER AS n, CAST(avg({v}) AS FLOAT) AS {v}_mean, CAST(coalesce(stddev_samp({v}), 0) AS FLOAT) AS {v}_sd"
    specs = {
        "link_h": ("route_id, ord, hour, we", full, "route_id"),
        "link_a": ("route_id, ord", full, "route_id"),
        "pair_h": ("from_stop, to_stop, hour, we", lite.format(v="ltt"), "from_stop"),
        "cell_h": ("gy, gx, hd, hour, we", lite.format(v="lpace"), "gx"),
        "city_h": ("hour, we", lite.format(v="lpace"), None),
    }
    counts = {}
    for name, (keys, agg, part) in specs.items():
        tgt = out / f"{name}.parquet"
        if part is None:
            con.execute(f"COPY (SELECT {keys}, {agg} FROM {L} GROUP BY {keys}) TO '{tgt.as_posix()}' (FORMAT parquet)")
        else:
            pdir = out / f"_{name}"
            pdir.mkdir(exist_ok=True)
            for c in range(CHUNKS):
                con.execute(f"COPY (SELECT {keys}, {agg} FROM {L} WHERE abs({part}) % {CHUNKS} = {c} GROUP BY {keys}) "
                            f"TO '{(pdir / f'p{c}.parquet').as_posix()}' (FORMAT parquet, COMPRESSION zstd)")
            con.execute(f"COPY (SELECT * FROM read_parquet('{(pdir / '*.parquet').as_posix()}')) TO '{tgt.as_posix()}' "
                        f"(FORMAT parquet, COMPRESSION zstd)")
            shutil.rmtree(pdir)
        counts[name] = con.execute(f"SELECT count(*) FROM read_parquet('{tgt.as_posix()}')").fetchone()[0]
    counts["traversals"] = con.execute(f"SELECT count(*) FROM {L}").fetchone()[0]
    counts["days"] = len(files)
    lk.unlink()
    return counts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--from", dest="d0", required=True)
    ap.add_argument("--to", dest="d1", required=True)
    a = ap.parse_args()
    out = OUT / a.name
    out.mkdir(parents=True, exist_ok=True)
    TMP.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"SET TimeZone='UTC'; SET memory_limit='4GB'; SET threads=4; SET temp_directory='{TMP.as_posix()}'; "
                "SET max_temp_directory_size='12GiB'; SET preserve_insertion_order=false")
    build_geom(con, out)
    print(a.name, build(con, a.d0, a.d1, out), flush=True)


if __name__ == "__main__":
    main()
