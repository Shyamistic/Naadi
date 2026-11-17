"""Bring our own live recordings (Nov 2026 onward) into the L1 format of the October archive.

Sources, merged and de-duplicated on (vehicle_id, ts):
  * the AWS server's recordings in s3://naadi-data-<acct>/raw/rt/date=YYYY-MM-DD/ (primary);
  * the laptop backup in data/raw/rt/date=YYYY-MM-DD/ (fills server gaps).
Cleaning matches scripts/ingest_dtc_hist.py: Delhi box, non-null ids, one row per (vehicle_id, ts).
Output: data/processed/gps_l1/day=YYYY_MM_DD.parquet (IST date). These days are test data only.

Usage: .venv\\Scripts\\python.exe scripts\\ingest_live.py [--days 2026-11-16 ...] [--force]
Default: every recorded day up to yesterday (IST) that is not yet in L1.
"""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import boto3
import duckdb

from ingest_dtc_hist import LAT, LNG, MAX_SPEED  # same cleaning bounds as the archive

ROOT = Path(__file__).resolve().parents[1]
S3_CACHE = ROOT / "data" / "raw" / "rt_s3"
LAPTOP = ROOT / "data" / "raw" / "rt"
OUT = ROOT / "data" / "processed" / "gps_l1"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def sync(day: str) -> None:
    s = boto3.Session(profile_name="naadi", region_name="ap-south-1")
    acct = s.client("sts").get_caller_identity()["Account"]
    s3 = s.client("s3")
    dest = S3_CACHE / f"date={day}"
    dest.mkdir(parents=True, exist_ok=True)
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=f"naadi-data-{acct}", Prefix=f"raw/rt/date={day}/"):
        for o in page.get("Contents", []):
            f = dest / Path(o["Key"]).name
            if not f.exists() or f.stat().st_size != o["Size"]:
                s3.download_file(f"naadi-data-{acct}", o["Key"], str(f))


def ingest(day: str, force: bool) -> None:
    out = OUT / f"day={day.replace('-', '_')}.parquet"
    if out.exists() and not force:
        print(f"{day}: already in L1")
        return
    sync(day)
    globs = [p.as_posix() for p in ((S3_CACHE / f"date={day}"), (LAPTOP / f"date={day}")) if any(p.glob("*.parquet"))]
    if not globs:
        print(f"{day}: no recordings")
        return
    src = ", ".join(f"'{g}/*.parquet'" for g in globs)
    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'; SET memory_limit='3GB'; SET threads=4")
    raw_n = con.execute(f"SELECT count(*) FROM read_parquet([{src}], union_by_name=true)").fetchone()[0]
    con.execute(f"""
        COPY (
          SELECT vehicle_id, lat, lng, speed, route_id, trip_id, ts FROM (
            SELECT vehicle_id, CAST(lat AS DOUBLE) AS lat, CAST(lon AS DOUBLE) AS lng,
                   CAST(speed AS REAL) AS speed, TRY_CAST(route_id AS INTEGER) AS route_id,
                   trip_id, CAST(ts AS BIGINT) AS ts,
                   row_number() OVER (PARTITION BY vehicle_id, ts ORDER BY poll_ts) AS rn
            FROM read_parquet([{src}], union_by_name=true)
            WHERE vehicle_id IS NOT NULL AND vehicle_id <> '' AND ts > 0
              AND lat BETWEEN {LAT[0]} AND {LAT[1]} AND lon BETWEEN {LNG[0]} AND {LNG[1]}
              AND (speed IS NULL OR (speed >= 0 AND speed <= {MAX_SPEED}))
              AND strftime(to_timestamp(ts + 19800), '%Y-%m-%d') = '{day}'
          ) WHERE rn = 1 AND route_id IS NOT NULL
          ORDER BY vehicle_id, ts
        ) TO '{out.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    kept = con.execute(f"SELECT count(*), count(DISTINCT vehicle_id) FROM read_parquet('{out.as_posix()}')").fetchone()
    print(f"{day}: raw {raw_n:,} from {len(globs)} source(s) -> kept {kept[0]:,} rows, {kept[1]:,} buses")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", nargs="*")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if a.days:
        days = a.days
    else:
        today = dt.datetime.now(IST).date()
        d, days = dt.date(2026, 11, 15), []
        while d < today:
            days.append(d.isoformat())
            d += dt.timedelta(days=1)
    for day in days:
        ingest(day, a.force)


if __name__ == "__main__":
    main()
