"""Count why ingest_dtc_hist.py drops rows, for already-extracted day .db files.

Usage: python scripts/l1_drop_breakdown.py 2026_10_01 2026_10_02
Buckets use first-hit order: null -> box -> timestamp -> speed -> duplicate.
"""
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).parent))
from ingest_dtc_hist import LAT, LNG, MAX_SPEED, RAW

for day in sys.argv[1:]:
    con = duckdb.connect()
    con.execute("SET memory_limit='1GB'; SET threads=2; SET temp_directory='data/raw/duck_tmp'")
    con.execute("LOAD sqlite")
    con.execute(f"ATTACH '{(RAW / f'bus_movements_{day}.db').as_posix()}' AS src (TYPE sqlite, READ_ONLY)")
    print(day, con.execute("DESCRIBE src.vehicle_feed").fetchall())
    con.execute(f"""
    CREATE TEMP TABLE t AS SELECT vehicle_id, TRY_CAST(lat AS DOUBLE) la, TRY_CAST(lng AS DOUBLE) lo,
      TRY_CAST(timestamp AS BIGINT) ts, speed,
      CASE
        WHEN vehicle_id IS NULL OR lat IS NULL OR lng IS NULL THEN '1_null'
        WHEN la IS NULL OR lo IS NULL OR NOT (la BETWEEN {LAT[0]} AND {LAT[1]} AND lo BETWEEN {LNG[0]} AND {LNG[1]}) THEN '2_outside_box'
        WHEN ts IS NULL THEN '3_bad_timestamp'
        WHEN speed IS NOT NULL AND NOT (speed >= 0 AND speed <= {MAX_SPEED}) THEN '4_speed'
        ELSE 'ok' END AS b
      FROM (SELECT *, TRY_CAST(lat AS DOUBLE) la, TRY_CAST(lng AS DOUBLE) lo,
                   TRY_CAST(timestamp AS BIGINT) ts FROM src.vehicle_feed)""")
    print(con.execute("SELECT b, count(*) FROM t GROUP BY 1 ORDER BY 1").fetchall())
    print("dup rows dropped / groups / groups with conflicting lat,lng / conflicting speed:")
    print(con.execute("""
    WITH g AS (SELECT vehicle_id, ts, count(*) n, count(DISTINCT (la, lo)) pos, count(DISTINCT speed) sp
               FROM t WHERE b='ok' GROUP BY 1,2 HAVING count(*) > 1)
    SELECT sum(n-1), count(*), count(*) FILTER (WHERE pos>1), count(*) FILTER (WHERE sp>1) FROM g""").fetchall())
    print("ts range / total:", con.execute("SELECT min(ts), max(ts), count(*) FROM t").fetchall())
    print("speed>120 samples:", con.execute("SELECT min(speed), max(speed), count(*) FILTER (WHERE speed<0) FROM t WHERE b='4_speed'").fetchall())
    con.close()
