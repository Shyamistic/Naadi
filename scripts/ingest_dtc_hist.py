"""Stream the DTC historical archive into cleaned daily parquet (L0 -> L1).

Disk is smaller than the archive (124 GB raw), so each day is extracted alone,
converted, and the raw .db deleted. Raw data stays under data/ (gitignored).

Usage: python scripts/ingest_dtc_hist.py [--days 2026_10_01 ...] [--keep-db]
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / "delhi-dtc-bus-gtfs-rt-2026-10.7z"
RAW = ROOT / "data" / "raw" / "dtc_hist"
OUT = ROOT / "data" / "processed" / "gps_l1"
SEVENZ = r"C:\Program Files\7-Zip\7z.exe"

# Delhi bounding box (generous) and speed cap in km/h-equivalent units of the feed.
LAT = (28.2, 29.0)
LNG = (76.7, 77.7)
MAX_SPEED = 120.0

SQL = """
COPY (
  SELECT
    vehicle_id,
    CAST(lat AS DOUBLE) AS lat,
    CAST(lng AS DOUBLE) AS lng,
    CAST(speed AS REAL) AS speed,
    CAST(route_id AS INTEGER) AS route_id,
    trip_id,
    CAST(timestamp AS BIGINT) AS ts
  FROM (
    SELECT *, row_number() OVER (PARTITION BY vehicle_id, timestamp) AS rn
    FROM src.vehicle_feed
    WHERE vehicle_id IS NOT NULL AND lat IS NOT NULL AND lng IS NOT NULL
      AND TRY_CAST(lat AS DOUBLE) BETWEEN {lat0} AND {lat1}
      AND TRY_CAST(lng AS DOUBLE) BETWEEN {lng0} AND {lng1}
      AND TRY_CAST(timestamp AS BIGINT) IS NOT NULL
      AND (speed IS NULL OR (speed >= 0 AND speed <= {vmax}))
  )
  WHERE rn = 1
  ORDER BY vehicle_id, ts
) TO '{out}' (FORMAT PARQUET, COMPRESSION ZSTD);
"""


def list_days():
    out = subprocess.run([SEVENZ, "l", str(ARCHIVE)], capture_output=True, text=True).stdout
    return sorted(
        l.split()[-1][len("bus_movements_"):-3]
        for l in out.splitlines()
        if l.strip().endswith(".db") and "bus_movements_" in l
    )


def process(day, keep_db):
    out = OUT / f"day={day}.parquet"
    if out.exists():
        print(f"{day}: already done")
        return
    name = f"bus_movements_{day}.db"
    db = RAW / name
    t0 = time.time()
    if not db.exists():
        subprocess.run([SEVENZ, "x", str(ARCHIVE), f"-o{RAW}", name, "-y"],
                       check=True, capture_output=True)
    con = duckdb.connect()
    con.execute("INSTALL sqlite; LOAD sqlite;")
    con.execute(f"ATTACH '{db.as_posix()}' AS src (TYPE sqlite, READ_ONLY)")
    raw_n = con.execute("SELECT count(*) FROM src.vehicle_feed").fetchone()[0]
    con.execute(SQL.format(lat0=LAT[0], lat1=LAT[1], lng0=LNG[0], lng1=LNG[1],
                           vmax=MAX_SPEED, out=out.as_posix()))
    kept = con.execute(f"SELECT count(*) FROM read_parquet('{out.as_posix()}')").fetchone()[0]
    con.close()
    if not keep_db:
        db.unlink()
    print(f"{day}: raw={raw_n:,} kept={kept:,} ({kept/raw_n:.1%}) {time.time()-t0:.0f}s", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", nargs="*")
    ap.add_argument("--keep-db", action="store_true")
    a = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    for d in a.days or list_days():
        process(d, a.keep_db)


if __name__ == "__main__":
    sys.exit(main())
