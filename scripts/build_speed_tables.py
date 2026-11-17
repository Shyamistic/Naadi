"""Stop events, link traversals and speed tables (L2 -> L3/L4/L5).

Per day (resumable, skips days with a stats file):
  1. Stops of each route (all stops in stop_times for the route's trips) are projected
     onto the route's single shape, giving shape_dist_m per stop (cached once).
  2. Stop events: matched points within STOP_RADIUS_M (along the shape) of a stop,
     grouped per bus-trip and stop. dwell_s = seconds spent (near-)stationary there.
  3. Link traversals: time the bus crosses each stop is interpolated between the two
     consecutive matched points that bracket the stop. Link = consecutive stops.
Then aggregates: per route x from_stop x to_stop x hour (IST) x day type.
vehicle_id is used only inside a day's query (as a hashed key) and never written.

Usage: python scripts/build_speed_tables.py [--days 2026_10_01 ...] [--force]

Thresholds (see SPEED_REPORT.md):
  point pair: gap 1..120 s, forward progress, implied speed <= 30 m/s
  link: 5..1800 s, 30..5000 m, 0.5..80 km/h
shortcuts: stop positions come from nearest shape segment (a loop route's stop can snap to
the wrong pass); one segment table per route (no direction); upgrade with a monotone
stop-order match if loop routes show in QA.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from match_routes import GTFS, KX, KY, ROOT, build_segments  # noqa: E402

L2 = ROOT / "data" / "processed" / "gps_l2"
OUT = ROOT / "data" / "processed" / "speed_tables"
WORK = OUT / "_work"
TMP = ROOT / "data" / "tmp_duckdb"

STOP_RADIUS_M = 40
STOP_OFFSET_MAX_M = 60  # stop farther than this from the shape is not on the shape
GAP_MAX_S, PAIR_VMAX_MS = 120, 30.0
TT_MIN_S, TT_MAX_S = 5, 1800
DIST_MIN_M, DIST_MAX_M = 30, 5000
V_MIN_KMH, V_MAX_KMH = 0.5, 80.0
STATIONARY_M = 5
MIN_SAMPLES = 30
AGG_CHUNKS = 20

# IST hour. floor() matters: t is fractional and CAST(DOUBLE AS INT) rounds, which shifted
# every bin by 30 min and produced an hour 24 (fixed 17 Nov 2026).
HOUR = "CAST(floor((t + 19800) / 3600) AS BIGINT) % 24"
# Days used to build the historical tables. Later days (Nov live recording) are test data only.
TRAIN_PREFIX = "2026_10"
DAYTYPE = "CASE WHEN isodow(to_timestamp(t + 19800)) >= 6 THEN 'weekend' ELSE 'weekday' END"


def build_stops(con):
    f = WORK / "stops_on_shape.parquet"
    if not f.exists():
        con.execute(f"""
            COPY (
                WITH rs AS (
                    SELECT DISTINCT t.route_id, st.stop_id
                    FROM read_csv('{GTFS / "trips.txt"}') t
                    JOIN read_csv('{GTFS / "stop_times.txt"}', all_varchar=true) st USING (trip_id)
                ), p AS (
                    SELECT rs.route_id, rs.stop_id, CAST(s.stop_lon AS DOUBLE)*{KX} AS px, CAST(s.stop_lat AS DOUBLE)*{KY} AS py
                    FROM rs JOIN read_csv('{GTFS / "stops.txt"}', all_varchar=true) s USING (stop_id)
                ), c AS (
                    SELECT p.route_id, p.stop_id, seg.cum, seg.len,
                           least(1.0, greatest(0.0, ((px-x1)*(x2-x1)+(py-y1)*(y2-y1))/(len*len))) AS t,
                           px, py, x1, y1, x2, y2
                    FROM p JOIN seg USING (route_id)
                ), d AS (
                    SELECT route_id, stop_id, cum + t*len AS sd,
                           sqrt((px-(x1+t*(x2-x1)))^2 + (py-(y1+t*(y2-y1)))^2) AS off FROM c
                ), m AS (
                    SELECT route_id, stop_id, arg_min(sd, off) AS sd, min(off) AS off
                    FROM d GROUP BY 1, 2
                )
                SELECT route_id, stop_id, sd,
                       row_number() OVER (PARTITION BY route_id ORDER BY sd) AS ord
                FROM m WHERE off <= {STOP_OFFSET_MAX_M}
            ) TO '{f}' (FORMAT parquet)
        """)
    con.execute(f"CREATE OR REPLACE TEMP TABLE st AS SELECT route_id, stop_id, sd, ord "
                f"FROM read_parquet('{f}')")


def process_day(con, day):
    t0 = time.time()
    src = L2 / f"day={day}.parquet"
    # Hashed bus-run key; vehicle_id never leaves this query. The feed's trip_id often changes in the middle
    # of a run, so a run is one vehicle on one route until a 20-min gap or a jump back of > 1 km.
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE pts AS
        WITH a AS (
            SELECT vehicle_id, route_id, ts, shape_dist_m AS d,
                   lag(ts) OVER w AS pt, lag(shape_dist_m) OVER w AS pd
            FROM read_parquet('{src}')
            WHERE match_status = 'matched' AND route_id IN (SELECT route_id FROM st)
            WINDOW w AS (PARTITION BY vehicle_id, route_id ORDER BY ts)
        ), b AS (
            SELECT *, sum(CASE WHEN pt IS NULL OR ts - pt > 1200 OR d < pd - 1000 THEN 1 ELSE 0 END)
                      OVER (PARTITION BY vehicle_id, route_id ORDER BY ts) AS run
            FROM a
        )
        SELECT hash(vehicle_id, route_id, run) AS k, route_id, ts, d,
               lag(ts) OVER w2 AS ts0, lag(d) OVER w2 AS d0
        FROM b WINDOW w2 AS (PARTITION BY vehicle_id, route_id, run ORDER BY ts)
    """)
    n_pts = con.execute("SELECT count(*) FROM pts").fetchone()[0]

    # stop events
    ev = WORK / "events" / f"day={day}.parquet"
    ev.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"""
        COPY (
            WITH sb AS (
                SELECT route_id, stop_id, sd, unnest(generate_series(
                    CAST(floor((sd-{STOP_RADIUS_M})/{STOP_RADIUS_M}) AS INT),
                    CAST(floor((sd+{STOP_RADIUS_M})/{STOP_RADIUS_M}) AS INT))) AS b FROM st
            ), j AS (
                SELECT pts.k, pts.route_id, sb.stop_id, pts.ts,
                       CASE WHEN pts.ts - pts.ts0 BETWEEN 1 AND {GAP_MAX_S}
                                 AND abs(pts.d - pts.d0) <= {STATIONARY_M}
                            THEN pts.ts - pts.ts0 ELSE 0 END AS still
                FROM pts JOIN sb ON pts.route_id = sb.route_id
                 AND CAST(floor(pts.d/{STOP_RADIUS_M}) AS INT) = sb.b
                 AND abs(pts.d - sb.sd) <= {STOP_RADIUS_M}
            )
            SELECT route_id, stop_id, min(ts) AS arr_ts, max(ts) AS dep_ts,
                   CAST(sum(still) AS INT) AS dwell_s, count(*) AS n_pts,
                   CAST(floor((min(ts) + 19800) / 3600) AS BIGINT) % 24 AS hour,
                   CASE WHEN isodow(to_timestamp(min(ts) + 19800)) >= 6
                        THEN 'weekend' ELSE 'weekday' END AS daytype
            FROM j GROUP BY k, route_id, stop_id
        ) TO '{ev}' (FORMAT parquet, COMPRESSION zstd)
    """)

    # link traversals
    lk = WORK / "links" / f"day={day}.parquet"
    lk.parent.mkdir(parents=True, exist_ok=True)
    ps = WORK / "passages" / f"day={day}.parquet"
    ps.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE xing AS
            WITH pr AS (
                SELECT k, route_id, ts0 AS t1, ts AS t2, d0 AS d1, d AS d2,
                       unnest(generate_series(CAST(floor(d0/500) AS INT),
                                              CAST(floor(d/500) AS INT))) AS b
                FROM pts
                WHERE ts - ts0 BETWEEN 1 AND {GAP_MAX_S} AND d > d0
                  AND (d - d0) / (ts - ts0) <= {PAIR_VMAX_MS}
            ), x AS (
                SELECT pr.k, pr.route_id, st.stop_id, st.ord, st.sd,
                       min(t1 + (st.sd - d1) / (d2 - d1) * (t2 - t1)) AS t
                FROM pr JOIN st ON pr.route_id = st.route_id
                 AND pr.b = CAST(floor(st.sd/500) AS INT)
                 AND st.sd >= d1 AND st.sd < d2
                GROUP BY ALL
            )
            SELECT * FROM x
    """)
    # stop passages: when each bus-trip (hashed key k) crossed each stop on its route
    con.execute(f"COPY (SELECT k, route_id, stop_id, ord, t FROM xing) TO '{ps}' "
                f"(FORMAT parquet, COMPRESSION zstd)")
    con.execute(f"""
        COPY (
            WITH y AS (
                SELECT k, route_id, stop_id AS from_stop_id, ord, sd, t,
                       lead(stop_id) OVER w AS to_stop_id, lead(ord) OVER w AS ord2,
                       lead(sd) OVER w AS sd2, lead(t) OVER w AS t2
                FROM xing WINDOW w AS (PARTITION BY k, route_id ORDER BY ord)
            ), z AS (
                SELECT k, route_id, from_stop_id, to_stop_id, ord, sd2 - sd AS dist_m,
                       t2 - t AS tt_s, t,
                       (sd2 - sd) / (t2 - t) * 3.6 AS speed_kmh
                FROM y WHERE ord2 = ord + 1 AND t2 - t > 0
            )
            SELECT k, route_id, from_stop_id, to_stop_id, ord, dist_m, tt_s, speed_kmh, t,
                   {HOUR} AS hour, {DAYTYPE} AS daytype
            FROM z
            WHERE tt_s BETWEEN {TT_MIN_S} AND {TT_MAX_S}
              AND dist_m BETWEEN {DIST_MIN_M} AND {DIST_MAX_M}
              AND speed_kmh BETWEEN {V_MIN_KMH} AND {V_MAX_KMH}
        ) TO '{lk}' (FORMAT parquet, COMPRESSION zstd)
    """)
    n_ev = con.execute(f"SELECT count(*) FROM read_parquet('{ev}')").fetchone()[0]
    n_lk = con.execute(f"SELECT count(*) FROM read_parquet('{lk}')").fetchone()[0]
    r = dict(day=day, matched_points=n_pts, stop_events=n_ev, link_traversals=n_lk,
             seconds=round(time.time() - t0, 1))
    (WORK / "stats").mkdir(exist_ok=True)
    (WORK / "stats" / f"day={day}.json").write_text(json.dumps(r))
    return r


def aggregate(con):
    links = (WORK / "links" / f"day={TRAIN_PREFIX}_*.parquet").as_posix()
    events = (WORK / "events" / f"day={TRAIN_PREFIX}_*.parquet").as_posix()
    parts = WORK / "agg_parts"
    parts.mkdir(exist_ok=True)
    for f in parts.glob("*.parquet"):
        f.unlink()
    for c in range(AGG_CHUNKS):
        con.execute(f"""
            COPY (
                SELECT route_id, from_stop_id, to_stop_id, ord AS from_ord, hour, daytype,
                       count(*) AS n, avg(dist_m) AS dist_m,
                       avg(speed_kmh) AS speed_mean, median(speed_kmh) AS speed_median,
                       quantile_cont(speed_kmh, 0.1) AS speed_p10,
                       quantile_cont(speed_kmh, 0.5) AS speed_p50,
                       quantile_cont(speed_kmh, 0.9) AS speed_p90,
                       avg(tt_s) AS tt_mean, median(tt_s) AS tt_median,
                       quantile_cont(tt_s, 0.1) AS tt_p10, quantile_cont(tt_s, 0.5) AS tt_p50,
                       quantile_cont(tt_s, 0.9) AS tt_p90
                FROM read_parquet('{links}') WHERE route_id % {AGG_CHUNKS} = {c}
                GROUP BY route_id, from_stop_id, to_stop_id, ord, hour, daytype
            ) TO '{parts / f"p{c}.parquet"}' (FORMAT parquet, COMPRESSION zstd)
        """)
    f = OUT / "speed_by_link_hour_daytype.parquet"
    con.execute(f"COPY (SELECT * FROM read_parquet('{(parts / '*.parquet').as_posix()}') "
                f"ORDER BY route_id, from_ord, daytype, hour) TO '{f}' "
                f"(FORMAT parquet, COMPRESSION zstd)")
    d = OUT / "stop_dwell_by_hour_daytype.parquet"
    dparts = WORK / "dwell_parts"
    dparts.mkdir(exist_ok=True)
    for c in range(AGG_CHUNKS):
        con.execute(f"""
            COPY (
                SELECT route_id, stop_id, hour, daytype, count(*) AS n,
                       avg(dwell_s) AS dwell_mean, median(dwell_s) AS dwell_median,
                       quantile_cont(dwell_s, 0.1) AS dwell_p10,
                       quantile_cont(dwell_s, 0.9) AS dwell_p90,
                       avg((dwell_s >= 10)::INT) AS share_dwell_10s
                FROM read_parquet('{events}') WHERE route_id % {AGG_CHUNKS} = {c}
                GROUP BY route_id, stop_id, hour, daytype
            ) TO '{dparts / f"p{c}.parquet"}' (FORMAT parquet, COMPRESSION zstd)
        """)
    con.execute(f"COPY (SELECT * FROM read_parquet('{(dparts / '*.parquet').as_posix()}')) "
                f"TO '{d}' (FORMAT parquet, COMPRESSION zstd)")
    return f, d


def report(con, f, d, days):
    q = lambda s: con.execute(s).fetchall()
    F = f"read_parquet('{f}')"
    n_rows = q(f"SELECT count(*) FROM {F}")[0][0]
    n_dw = q(f"SELECT count(*) FROM read_parquet('{d}')")[0][0]
    tot = {k: sum(x[k] for x in days) for k in ("matched_points", "stop_events", "link_traversals")}
    seg_all = q("SELECT count(*) FROM (SELECT route_id, ord FROM st QUALIFY "
                "lead(ord) OVER (PARTITION BY route_id ORDER BY ord) IS NOT NULL)")[0][0]
    seg = q(f"SELECT count(*), count(*) FILTER (WHERE n >= {MIN_SAMPLES}) FROM "
            f"(SELECT route_id, from_ord, sum(n) AS n FROM {F} GROUP BY 1, 2)")[0]
    cell_ok = q(f"SELECT count(*) FILTER (WHERE n >= {MIN_SAMPLES}) FROM {F}")[0][0]
    pct = lambda a, b: f"{100 * a / b:.1f}%" if b else "n/a"
    sane = q(f"""SELECT sum(n), sum(n) FILTER (WHERE speed_median BETWEEN 5 AND 40),
                 sum(n) FILTER (WHERE speed_median < 5), sum(n) FILTER (WHERE speed_median > 40),
                 median(speed_median), min(speed_p10), max(speed_p90) FROM {F}""")[0]
    hours = q(f"""SELECT hour, daytype, count(*) cells, sum(n) n,
                 round(median(speed_median), 1) med FROM {F} GROUP BY 1, 2 ORDER BY 2, 1""")
    dw = q(f"SELECT median(dwell_median), avg(share_dwell_10s) FROM read_parquet('{d}') WHERE n >= 30")[0]
    L = ["# Speed tables report", "",
         f"Training days aggregated: {len(days)} (prefix {TRAIN_PREFIX}; all L2 days: "
         f"{len(list(L2.glob('day=*.parquet')))}). Later days are test data and are not in these tables.", "",
         "## Row counts",
         f"- Matched points used: {tot['matched_points']:,}",
         f"- Stop events: {tot['stop_events']:,}",
         f"- Link traversals kept: {tot['link_traversals']:,}",
         f"- `speed_by_link_hour_daytype.parquet`: {n_rows:,} rows "
         "(route x from_stop x to_stop x hour x daytype)",
         f"- `stop_dwell_by_hour_daytype.parquet`: {n_dw:,} rows", "",
         "## Coverage",
         f"- Segments (route, stop to next stop) in GTFS with a stop on shape: {seg_all:,}",
         f"- Segments with any traversal: {seg[0]:,} ({pct(seg[0], seg_all)})",
         f"- Segments with >= {MIN_SAMPLES} samples (all hours, both day types): "
         f"{seg[1]:,} ({pct(seg[1], seg_all)} of all, {pct(seg[1], seg[0])} of observed)",
         f"- Segment x hour x daytype cells with >= {MIN_SAMPLES} samples: "
         f"{cell_ok:,} ({pct(cell_ok, n_rows)} of cells)", "",
         "## Sanity checks",
         f"- Median of cell median speeds: {sane[4]:.1f} km/h",
         f"- Traversals in cells with median 5-40 km/h: {pct(sane[1], sane[0])}; "
         f"< 5: {pct(sane[2], sane[0])}; > 40: {pct(sane[3], sane[0])}",
         f"- Lowest cell p10: {sane[5]:.1f} km/h; highest cell p90: {sane[6]:.1f} km/h",
         f"- Stops with >= 30 events: median dwell {dw[0]:.0f} s; "
         f"share of events with dwell >= 10 s {100 * dw[1]:.0f}%", "",
         "Median speed by hour (IST), median over cells:", "",
         "| daytype | hour | cells | traversals | median km/h |", "|---|---|---|---|---|"]
    L += [f"| {h[1]} | {h[0]} | {h[2]:,} | {h[3]:,} | {h[4]} |" for h in hours]
    L += ["", "## Method and thresholds",
          f"- Stop event: matched points within {STOP_RADIUS_M} m (along shape) of a stop, per bus-trip. "
          f"dwell_s = seconds between consecutive points (gap <= {GAP_MAX_S} s) that moved <= {STATIONARY_M} m.",
          f"- Stop on shape: nearest shape point within {STOP_OFFSET_MAX_M} m. Stops are all stops "
          "of the route's trips, ordered by distance along the shape.",
          f"- Crossing time: linear interpolation between two consecutive matched points "
          f"(gap 1-{GAP_MAX_S} s, forward progress, implied speed <= {PAIR_VMAX_MS:.0f} m/s) bracketing the stop.",
          f"- Link: consecutive stops. Kept if time {TT_MIN_S}-{TT_MAX_S} s, length {DIST_MIN_M}-{DIST_MAX_M} m, "
          f"speed {V_MIN_KMH}-{V_MAX_KMH} km/h. Travel time includes dwell at the from-stop "
          "(stop centre to stop centre).",
          "- Hour and day type use IST (weekend = Sat/Sun), hour = floor of local time. GTFS calendar runs every day, so it is not used.",
          "- GPS `speed` column is not used (it does not track position change).",
          "- No vehicle_id or trip_id in any aggregate output.",
          "- Known limits: nearest-segment stop projection and no direction check, so loop routes can mix passes; "
          "links skip when a stop is not bracketed by two close GPS points."]
    (OUT / "SPEED_REPORT.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return dict(link_traversals=tot["link_traversals"], stop_events=tot["stop_events"],
                matched_points=tot["matched_points"], speed_table_rows=n_rows,
                dwell_table_rows=n_dw, segments_total=seg_all, segments_observed=seg[0],
                segments_ge30=seg[1], days=len(days))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", nargs="*")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    TMP.mkdir(parents=True, exist_ok=True)
    all_days = sorted(p.stem.split("=")[1] for p in L2.glob("day=*.parquet"))
    days = a.days or all_days
    con = duckdb.connect()
    # UTC session: the code adds +19800 s itself; an IST session would shift IST times a second time
    con.execute(f"SET TimeZone='UTC'; SET memory_limit='1500MB'; SET threads=2; "
                f"SET temp_directory='{TMP.as_posix()}'; SET preserve_insertion_order=false")
    build_segments(con)
    build_stops(con)
    for day in days:
        if (WORK / "stats" / f"day={day}.json").exists() and not a.force:
            print(day, "skip (done)", flush=True)
            continue
        r = process_day(con, day)
        print(day, r, flush=True)
    train_days = [d for d in all_days if d.startswith(TRAIN_PREFIX)]
    done = [json.loads(p.read_text()) for p in sorted((WORK / "stats").glob(f"day={TRAIN_PREFIX}_*.json"))]
    if len(done) < len(train_days):
        print(f"{len(done)}/{len(train_days)} training days done; no aggregate yet")
        return
    f, d = aggregate(con)
    counts = report(con, f, d, done)
    (OUT / "DONE.json").write_text(json.dumps(counts, indent=2))
    print("DONE", counts)


if __name__ == "__main__":
    main()
