"""Download the ETA Calculator logs from S3 and derive per-route bus attributes.

Writes:
  data/raw/eta_s3/date=*/...parquet          (private copy of the logs)
  data/processed/model/route_ac.json         route_id -> share of AC buses seen at stops (no vehicle ids)
"""
from __future__ import annotations

import json
from pathlib import Path

import boto3
import duckdb

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "data" / "raw" / "eta_s3"


def main() -> None:
    s = boto3.Session(profile_name="naadi", region_name="ap-south-1")
    acct = s.client("sts").get_caller_identity()["Account"]
    s3 = s.client("s3")
    n = 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=f"naadi-data-{acct}", Prefix="raw/eta_baseline/"):
        for o in page.get("Contents", []):
            if not o["Key"].endswith(".parquet"):
                continue
            f = DEST / Path(o["Key"]).relative_to("raw/eta_baseline")
            if not f.exists() or f.stat().st_size != o["Size"]:
                f.parent.mkdir(parents=True, exist_ok=True)
                s3.download_file(f"naadi-data-{acct}", o["Key"], str(f))
                n += 1
    print(f"downloaded {n} new files")
    con = duckdb.connect()
    rows = con.execute(f"""
        WITH v AS (SELECT DISTINCT route_id, vehicle_id, ac FROM read_parquet('{(DEST / '**' / '*.parquet').as_posix()}')
                   WHERE kind = 'stop' AND vehicle_id IS NOT NULL AND ac IS NOT NULL)
        SELECT route_id, count(*) n, avg((ac = 'ac')::INT) share FROM v GROUP BY 1 HAVING count(*) >= 3""").fetchall()
    out = {str(r[0]): round(float(r[2]), 2) for r in rows}
    p = ROOT / "data" / "processed" / "model" / "route_ac.json"
    p.write_text(json.dumps(out))
    print(f"route_ac.json: {len(out)} routes; mean AC share {sum(out.values()) / max(1, len(out)):.2f}")


if __name__ == "__main__":
    main()
