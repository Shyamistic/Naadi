"""Snap L1 GPS points to their route's GTFS shape (L1 -> L2).

Each route_id in bus GTFS v1-2 has exactly one shape (direction is part of the
route_id), so the match is route_id -> shape_id, then nearest shape segment.
Output adds: shape_id, shape_dist_m (metres along the shape), offset_m (metres
from the shape), match_status (matched | off_shape | no_shape).
vehicle_id stays in the L2 parquet (git-ignored, internal only).

Usage: python scripts/match_routes.py [--days 2026_10_01 ...] [--max-offset 50]
One day at a time, distinct positions only, routes in batches: low memory.
shortcut: nearest segment only (no direction/progress check), so loop routes
can snap to the wrong pass; add an HMM/monotonic check if that shows in QA.
"""
import argparse
import json
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
L1 = ROOT / "data" / "processed" / "gps_l1"
GTFS = ROOT / "data" / "processed" / "gtfs_fixed" / "bus_v1-2"
OUT = ROOT / "data" / "processed" / "gps_l2"
STATS = OUT / "_stats"
TMP = ROOT / "data" / "tmp_duckdb"

# Local metric projection for Delhi (fixed latitude, error < 0.5% over the city).
KX = 111320.0 * 0.8780  # cos(28.6 deg)
KY = 110574.0
ROUTES_PER_BATCH = 100


def build_segments(con):
    con.execute(f"""
        CREATE TEMP TABLE seg AS
        WITH r AS (
            SELECT t.route_id, s.shape_id, s.shape_pt_sequence AS sq,
                   s.shape_pt_lon * {KX} AS x, s.shape_pt_lat * {KY} AS y
            FROM (SELECT DISTINCT route_id, shape_id
                  FROM read_csv('{GTFS / "trips.txt"}')) t
            JOIN read_csv('{GTFS / "shapes.txt"}') s USING (shape_id)
        ), p AS (
            SELECT *, lead(x) OVER w AS x2, lead(y) OVER w AS y2 FROM r
            WINDOW w AS (PARTITION BY shape_id ORDER BY sq)
        ), q AS (
            SELECT *, sqrt((x2-x)^2 + (y2-y)^2) AS len FROM p WHERE x2 IS NOT NULL
        )
        SELECT dense_rank() OVER (ORDER BY route_id) // {ROUTES_PER_BATCH} AS b,
               route_id, shape_id, x AS x1, y AS y1, x2, y2, len,
               coalesce(sum(len) OVER (PARTITION BY shape_id ORDER BY sq
                        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0) AS cum
        FROM q WHERE len > 0
    """)


def match_day(con, day, max_off):
    src = L1 / f"day={day}.parquet"
    dst = OUT / f"day={day}.parquet"
    t0 = time.time()
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE pos AS
        SELECT DISTINCT route_id, lat, lng FROM read_parquet('{src}')
        WHERE route_id IN (SELECT route_id FROM seg)
    """)
    con.execute("CREATE OR REPLACE TEMP TABLE snap (route_id INT, lat DOUBLE, lng DOUBLE,"
                " shape_id VARCHAR, dist DOUBLE, off DOUBLE)")
    batches = [r[0] for r in con.execute("SELECT DISTINCT b FROM seg ORDER BY b").fetchall()]
    for b in batches:
        con.execute(f"""
            INSERT INTO snap
            WITH p AS (
                SELECT pos.route_id, lat, lng, lng*{KX} AS px, lat*{KY} AS py
                FROM pos JOIN (SELECT DISTINCT route_id FROM seg WHERE b={b}) USING (route_id)
            ), c AS (
                SELECT p.route_id, p.lat, p.lng, s.shape_id, s.cum, s.len,
                       least(1.0, greatest(0.0,
                         ((px-x1)*(x2-x1) + (py-y1)*(y2-y1)) / (len*len))) AS t,
                       px, py, x1, y1, x2, y2
                FROM p JOIN (SELECT * FROM seg WHERE b={b}) s USING (route_id)
                WHERE px BETWEEN least(x1,x2)-{max_off*4} AND greatest(x1,x2)+{max_off*4}
                  AND py BETWEEN least(y1,y2)-{max_off*4} AND greatest(y1,y2)+{max_off*4}
            ), d AS (
                SELECT *, sqrt((px-(x1+t*(x2-x1)))^2 + (py-(y1+t*(y2-y1)))^2) AS off,
                       cum + t*len AS dist FROM c
            )
            SELECT route_id, lat, lng, arg_min(shape_id, off), arg_min(dist, off), min(off)
            FROM d GROUP BY route_id, lat, lng
        """)
    # Positions with no segment inside the (4x) search box are 'far' too: left join gives NULL.
    con.execute(f"""
        COPY (
            SELECT l.*, s.shape_id,
                   CASE WHEN s.off <= {max_off} THEN s.dist END AS shape_dist_m,
                   s.off AS offset_m,
                   CASE WHEN l.route_id NOT IN (SELECT route_id FROM seg) THEN 'no_shape'
                        WHEN s.off <= {max_off} THEN 'matched'
                        ELSE 'off_shape' END AS match_status
            FROM read_parquet('{src}') l
            LEFT JOIN snap s ON l.route_id = s.route_id AND l.lat = s.lat AND l.lng = s.lng
        ) TO '{dst}' (FORMAT parquet, COMPRESSION zstd)
    """)
    st = con.execute(f"""
        SELECT count(*), count(*) FILTER (WHERE match_status='matched'),
               count(*) FILTER (WHERE match_status='off_shape'),
               count(*) FILTER (WHERE match_status='no_shape'),
               count(*) FILTER (WHERE match_status='off_shape' AND offset_m IS NULL),
               count(*) FILTER (WHERE match_status='off_shape' AND offset_m <= 200),
               count(*) FILTER (WHERE offset_m <= 25),
               median(offset_m) FILTER (WHERE match_status='matched')
        FROM read_parquet('{dst}')
    """).fetchone()
    rows = dict(zip(
        ["rows", "matched", "off_shape", "no_shape", "off_over_search_box",
         "off_50_200m", "within_25m", "median_offset_m"], st))
    rows.update(day=day, seconds=round(time.time() - t0, 1), max_offset_m=max_off)
    STATS.mkdir(parents=True, exist_ok=True)
    (STATS / f"day={day}.json").write_text(json.dumps(rows))
    return rows


def write_report():
    days = [json.loads(p.read_text()) for p in sorted(STATS.glob("day=*.json"))]
    if not days:
        return
    tot = {k: sum(d[k] for d in days) for k in ("rows", "matched", "off_shape", "no_shape")}
    pct = lambda a, b: f"{100 * a / b:.2f}%" if b else "n/a"
    L = ["# L2 map-matching report", "",
         f"Rule: route_id -> its single GTFS shape; nearest segment; matched if offset <= "
         f"{days[0]['max_offset_m']} m. Days done: {len(days)}.", "",
         f"Overall: {tot['rows']:,} rows, matched {pct(tot['matched'], tot['rows'])}, "
         f"off_shape {pct(tot['off_shape'], tot['rows'])}, no_shape {pct(tot['no_shape'], tot['rows'])}.", "",
         "| day | rows | matched | off_shape | no_shape | off 50-200 m | median offset m | sec |",
         "|---|---|---|---|---|---|---|---|"]
    for d in days:
        L.append(f"| {d['day']} | {d['rows']:,} | {pct(d['matched'], d['rows'])} | "
                 f"{pct(d['off_shape'], d['rows'])} | {pct(d['no_shape'], d['rows'])} | "
                 f"{d['off_50_200m']:,} | {d['median_offset_m']:.1f} | {d['seconds']} |")
    L += ["", "## Unmatched reasons",
          "- no_shape: route_id has no trips/shape in GTFS v1-2.",
          "- off_shape: nearest shape segment is farther than the offset limit "
          "(bus off route, GPS error, detour, or stale GTFS shape).",
          "- Known limit: nearest segment only, no direction or progress check; "
          "loop routes may snap to the wrong pass."]
    (OUT / "MATCH_REPORT.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", nargs="*")
    ap.add_argument("--max-offset", type=float, default=50.0)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    TMP.mkdir(parents=True, exist_ok=True)
    days = a.days or sorted(p.stem.split("=")[1] for p in L1.glob("day=*.parquet"))
    con = duckdb.connect()
    con.execute(f"SET memory_limit='1200MB'; SET threads=4; SET temp_directory='{TMP.as_posix()}'")
    build_segments(con)
    for day in days:
        if (STATS / f"day={day}.json").exists() and not a.force:
            print(day, "skip (done)", flush=True)
            continue
        r = match_day(con, day, a.max_offset)
        print(day, f"matched {100*r['matched']/r['rows']:.2f}% of {r['rows']:,} in {r['seconds']}s",
              flush=True)
        write_report()
    write_report()


if __name__ == "__main__":
    main()
