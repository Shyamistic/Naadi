"""Observed service levels: how often buses of each route pass each stop, and how irregularly.

From stop passages of the chosen days, per route x stop (ord) x IST hour x day type:
  f_obs   buses per hour (passages / number of days of that type)
and per route x hour x day type (pooled over stops, because single stops are thin):
  cv      coefficient of variation of headways between consecutive buses at a stop
          (headways over 90 min are service gaps, not waits, and are dropped)
From the official timetable (GTFS stop_times), per route x stop x hour:
  f_sched scheduled buses per hour (the timetable planner baseline uses this with regular headways)

Expected wait for a passenger arriving at random: E[W] = E[H^2] / (2 E[H]) = (H / 2) (1 + CV^2).

Usage: python scripts/build_service.py --name oct01_24 --from 2026_10_01 --to 2026_10_24
Writes data/processed/model/service_<name>.parquet
"""
from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "data" / "processed" / "speed_tables" / "_work"
GTFS = ROOT / "data" / "processed" / "gtfs_fixed" / "bus_v1-2"
MODEL = ROOT / "data" / "processed" / "model"
TMP = ROOT / "data" / "tmp_duckdb"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--from", dest="d0", required=True)
    ap.add_argument("--to", dest="d1", required=True)
    a = ap.parse_args()
    files = sorted(p for p in (WORK / "passages").glob("day=*.parquet") if a.d0 <= p.stem.split("=")[1] <= a.d1)
    src = "[" + ", ".join(f"'{p.as_posix()}'" for p in files) + "]"
    con = duckdb.connect()
    con.execute(f"SET TimeZone='UTC'; SET memory_limit='5GB'; SET threads=8; SET temp_directory='{TMP.as_posix()}'; SET preserve_insertion_order=false")
    import datetime as dt
    ds = [dt.date(*map(int, f.stem.split("=")[1].split("_"))) for f in files]
    days = (sum(d.weekday() < 5 for d in ds), sum(d.weekday() >= 5 for d in ds))
    print(f"{len(files)} files; weekday days {days[0]}, weekend days {days[1]}")
    out = MODEL / f"service_{a.name}.parquet"
    con.execute(f"""
        CREATE TEMP TABLE p AS
        SELECT route_id, ord, t, CAST(floor((t + 19800) / 3600) AS BIGINT) % 24 AS hour,
               (isodow(to_timestamp(t + 19800)) >= 6)::INTEGER AS we,
               CAST(to_timestamp(t + 19800) AS DATE) AS d
        FROM read_parquet({src})
    """)
    con.execute(f"""
        COPY (
        WITH f AS (
            SELECT route_id, ord, hour, we, count(*) / (CASE WHEN we = 1 THEN {max(days[1], 1)} ELSE {max(days[0], 1)} END) AS f_obs
            FROM p GROUP BY route_id, ord, hour, we
        ), hw AS (
            SELECT route_id, ord, hour, we, t - lag(t) OVER (PARTITION BY route_id, ord, d ORDER BY t) AS h FROM p
        ), we_stop AS (
            -- empirical mean wait for a rider arriving at random: sum(h^2) / (2 sum(h)); keeps bunching and gaps
            SELECT route_id, ord, hour, we, count(*) AS n_w, sum(h * h) / (2 * sum(h)) AS w_stop
            FROM hw WHERE h BETWEEN 20 AND 7200 GROUP BY route_id, ord, hour, we
        ), we_route AS (
            SELECT route_id, hour, we, sum(h * h) / (2 * sum(h)) AS w_route
            FROM hw WHERE h BETWEEN 20 AND 7200 GROUP BY route_id, hour, we
        ), cv AS (
            SELECT route_id, hour, we, count(*) AS n_hw, stddev_samp(h) / avg(h) AS cv
            FROM hw WHERE h BETWEEN 20 AND 5400 GROUP BY route_id, hour, we
        ), sched AS (
            SELECT CAST(t.route_id AS INTEGER) AS route_id, CAST(st.stop_id AS INTEGER) AS stop_id,
                   CAST(split_part(st.arrival_time, ':', 1) AS INTEGER) % 24 AS hour, count(*) AS f_sched
            FROM read_csv('{(GTFS / "stop_times.txt").as_posix()}', all_varchar=true) st
            JOIN read_csv('{(GTFS / "trips.txt").as_posix()}', all_varchar=true) t USING (trip_id) GROUP BY 1, 2, 3
        ), so AS (
            SELECT route_id, ord, CAST(stop_id AS INTEGER) AS stop_id
            FROM read_parquet('{(WORK / "stops_on_shape.parquet").as_posix()}')
        )
        SELECT so.route_id, so.ord, h.hour, w.we, coalesce(f.f_obs, 0)::FLOAT AS f_obs,
               coalesce(cv.cv, 0.8)::FLOAT AS cv, coalesce(cv.n_hw, 0)::INTEGER AS n_hw,
               coalesce(sched.f_sched, 0)::FLOAT AS f_sched,
               ((coalesce(ws.n_w, 0) * coalesce(ws.w_stop, 0) + 10 * wr.w_route) / (coalesce(ws.n_w, 0) + 10))::FLOAT AS w_emp,
               coalesce(ws.n_w, 0)::INTEGER AS n_w
        FROM so CROSS JOIN (SELECT range AS hour FROM range(24)) h CROSS JOIN (SELECT range AS we FROM range(2)) w
        LEFT JOIN f ON f.route_id = so.route_id AND f.ord = so.ord AND f.hour = h.hour AND f.we = w.we
        LEFT JOIN cv ON cv.route_id = so.route_id AND cv.hour = h.hour AND cv.we = w.we
        LEFT JOIN sched ON sched.route_id = so.route_id AND sched.stop_id = so.stop_id AND sched.hour = h.hour
        LEFT JOIN we_stop ws ON ws.route_id = so.route_id AND ws.ord = so.ord AND ws.hour = h.hour AND ws.we = w.we
        LEFT JOIN we_route wr ON wr.route_id = so.route_id AND wr.hour = h.hour AND wr.we = w.we
        ) TO '{out.as_posix()}' (FORMAT parquet, COMPRESSION zstd)
    """)
    s = con.execute(f"""SELECT count(*), avg(f_obs) FILTER (WHERE f_obs > 0), median(cv) FILTER (WHERE n_hw >= 30),
        avg(f_sched) FILTER (WHERE f_sched > 0) FROM read_parquet('{out.as_posix()}')""").fetchone()
    print(f"{out.name}: {s[0]:,} rows; mean buses/h where served {s[1]:.2f}; median route-hour CV {s[2]:.2f}; "
          f"mean scheduled buses/h {s[3]:.2f}")


if __name__ == "__main__":
    main()
