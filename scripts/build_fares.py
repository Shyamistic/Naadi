"""Build empirical fares and rider-demand artefacts from October e-tickets.

The input archive is licensed hackathon data and is never copied to an output
artefact.  The CSV is streamed to a temporary file, loaded into DuckDB with
vehicle_number omitted, and removed before this script exits.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import shutil
import tempfile
import unicodedata
import zipfile
from pathlib import Path

import duckdb


DEFAULT_ROOT = Path(os.environ.get("NAADI_ROOT", Path(__file__).resolve().parents[1]))
GTFS = DEFAULT_ROOT / "data" / "processed" / "gtfs_fixed" / "bus_v1-2"
ARCHIVE = DEFAULT_ROOT / "data" / "raw" / "eticket" / "October-Delhi.csv.zip"
MODEL = DEFAULT_ROOT / "data" / "processed" / "model"
STOPS_ON_SHAPE = DEFAULT_ROOT / "data" / "processed" / "speed_tables" / "_work" / "stops_on_shape.parquet"
FARES = MODEL / "fares_v1"
DEMAND = MODEL / "demand_v1"


def sql_path(path: Path) -> str:
    return path.as_posix().replace("'", "''")


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").casefold()
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def extract_csv(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as zf:
        members = [x for x in zf.infolist() if x.filename.lower().endswith(".csv") and not x.filename.startswith("__MACOSX/")]
        if len(members) != 1:
            raise RuntimeError(f"expected one ticket CSV, found {[x.filename for x in members]}")
        with zf.open(members[0]) as source, destination.open("wb") as target:
            shutil.copyfileobj(source, target, length=1024 * 1024)


def load_gtfs(con: duckdb.DuckDBPyConnection) -> None:
    stop_rows = []
    with (GTFS / "stops.txt").open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            stop_rows.append((int(row["stop_id"]), row["stop_name"], norm(row["stop_name"])))
    route_rows = []
    with (GTFS / "routes.txt").open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            route_rows.append((int(row["route_id"]), row["route_short_name"], norm(row["route_short_name"])))
    con.execute("CREATE TABLE gtfs_stops(stop_id INTEGER, stop_name VARCHAR, stop_norm VARCHAR)")
    con.executemany("INSERT INTO gtfs_stops VALUES (?, ?, ?)", stop_rows)
    con.execute("CREATE TABLE gtfs_routes(route_id INTEGER, route_short_name VARCHAR, route_norm VARCHAR)")
    con.executemany("INSERT INTO gtfs_routes VALUES (?, ?, ?)", route_rows)


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build(archive: Path = ARCHIVE, root: Path = DEFAULT_ROOT) -> dict:
    if not archive.exists():
        raise FileNotFoundError(archive)
    fares_dir = root / "data" / "processed" / "model" / "fares_v1"
    demand_dir = root / "data" / "processed" / "model" / "demand_v1"
    fares_dir.mkdir(parents=True, exist_ok=True)
    demand_dir.mkdir(parents=True, exist_ok=True)
    (fares_dir / "README.md").write_text("""# October 2026 fare model

`fare_table.parquet` is an aggregate empirical modal fare table learned on 1--24 October, keyed by GTFS route ID, boarding stop ID, alighting stop ID, and AC flag. Cells need at least 20 observations and a modal share of 50% or more. Sparse cells use the official DTC distance slabs with the observed 10% One Delhi app discount. `profile.json` records source coverage and holdout results.

The raw e-ticket archive and vehicle numbers are not included in this artefact.
""", encoding="utf-8")
    (demand_dir / "README.md").write_text("""# October 2026 rider demand aggregates

Built by `scripts/build_fares.py` from the organisers' October 2026 ONDC e-ticket archive. The raw CSV is not redistributed and `vehicle_number` is dropped before loading.

- `boardings.parquet`: matched boarding stop ID, ticket boardings, passenger count, and route counts. Use `boardings` to rank stop-name search results.
- `od_pairs.parquet`: matched boarding/alighting stop IDs by IST hour and `weekday`/`weekend`, with ticket and passenger counts. Use `tickets` or `passengers` as validation OD-set weights.

Stop and route names are matched to `data/processed/gtfs_fixed/bus_v1-2`. See `../fares_v1/profile.json` for match rates and caveats. E-ticket coverage is app-biased and is not a population-wide ridership estimate.
""", encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="naadi_eticket_") as temp:
        csv_path = Path(temp) / "October-Delhi.csv"
        extract_csv(archive, csv_path)
        con = duckdb.connect()
        con.execute("SET memory_limit='1536MB'")
        con.execute("SET threads=4")
        con.execute(
            f"""CREATE TABLE tickets AS
            SELECT CAST(passenger_count AS INTEGER) AS passenger_count,
                   CAST(amount AS DOUBLE) AS amount,
                   CAST(ticket_type_id AS VARCHAR) AS ticket_type_id,
                   CAST(end_stop_name AS VARCHAR) AS end_stop_name,
                   CAST(route AS VARCHAR) AS route,
                   CAST(start_stop_name AS VARCHAR) AS start_stop_name,
                   CAST(created_at AS TIMESTAMPTZ) AS created_at,
                   CAST(is_ac AS BOOLEAN) AS is_ac
            FROM read_csv('{sql_path(csv_path)}', header=true, all_varchar=true,
                          columns={{'passenger_count':'VARCHAR','amount':'VARCHAR','vehicle_number':'VARCHAR',
                          'ticket_type_id':'VARCHAR','end_stop_name':'VARCHAR',
                          'route':'VARCHAR','start_stop_name':'VARCHAR',
                          'created_at':'VARCHAR','is_ac':'VARCHAR'}})"""
        )
        load_gtfs(con)
        con.execute("ALTER TABLE tickets ADD COLUMN start_norm VARCHAR")
        con.execute("ALTER TABLE tickets ADD COLUMN end_norm VARCHAR")
        con.execute("ALTER TABLE tickets ADD COLUMN route_norm VARCHAR")
        # The Python normaliser is mirrored here for the ASCII route and stop names.
        con.execute("UPDATE tickets SET start_norm=lower(trim(regexp_replace(regexp_replace(start_stop_name, '[^A-Za-z0-9]+', ' ', 'g'), ' +', ' ', 'g'))), end_norm=lower(trim(regexp_replace(regexp_replace(end_stop_name, '[^A-Za-z0-9]+', ' ', 'g'), ' +', ' ', 'g'))), route_norm=lower(trim(regexp_replace(regexp_replace(route, '[^A-Za-z0-9]+', ' ', 'g'), ' +', ' ', 'g')))" )
        # Keep the published match rates at the name level.  Ambiguous GTFS names
        # are mapped to their smallest stable stop_id for the fare/OD artefacts.
        con.execute("CREATE TABLE stop_map AS SELECT stop_norm, min(stop_id) AS stop_id, count(*) AS gtfs_stop_ids FROM gtfs_stops GROUP BY stop_norm")
        con.execute("CREATE TABLE route_map AS SELECT route_norm, min(route_id) AS route_id, count(*) AS gtfs_route_ids FROM gtfs_routes GROUP BY route_norm")
        if not STOPS_ON_SHAPE.exists():
            raise FileNotFoundError(STOPS_ON_SHAPE)
        con.execute(f"CREATE TABLE route_stop_dist AS SELECT CAST(route_id AS INTEGER) route_id, CAST(stop_id AS INTEGER) stop_id, min(CAST(sd AS DOUBLE)) sd FROM read_parquet('{sql_path(STOPS_ON_SHAPE)}') GROUP BY 1, 2")
        stats = con.execute(
            """SELECT count(*) AS tickets,
               count(*) FILTER (WHERE route_map.route_id IS NOT NULL) AS route_matched,
               count(*) FILTER (WHERE sm1.stop_id IS NOT NULL) AS board_matched,
               count(*) FILTER (WHERE sm2.stop_id IS NOT NULL) AS alight_matched,
               count(*) FILTER (WHERE route_map.route_id IS NOT NULL AND sm1.stop_id IS NOT NULL AND sm2.stop_id IS NOT NULL) AS all_matched,
               count(*) FILTER (WHERE sm1.gtfs_stop_ids > 1) AS board_ambiguous,
               count(*) FILTER (WHERE sm2.gtfs_stop_ids > 1) AS alight_ambiguous,
               count(DISTINCT route) AS ticket_route_names,
               count(DISTINCT route_map.route_id) AS matched_route_ids
            FROM tickets t
            LEFT JOIN route_map ON route_map.route_norm=t.route_norm
            LEFT JOIN stop_map sm1 ON sm1.stop_norm=t.start_norm
            LEFT JOIN stop_map sm2 ON sm2.stop_norm=t.end_norm"""
        ).fetchone()
        columns = ["tickets", "route_matched", "board_matched", "alight_matched", "all_matched", "board_ambiguous", "alight_ambiguous", "ticket_route_names", "matched_route_ids"]
        profile = dict(zip(columns, map(int, stats)))
        profile.update({"route_match_rate": profile["route_matched"] / profile["tickets"],
                        "boarding_stop_match_rate": profile["board_matched"] / profile["tickets"],
                        "alighting_stop_match_rate": profile["alight_matched"] / profile["tickets"],
                        "all_fields_match_rate": profile["all_matched"] / profile["tickets"]})
        # Train on 1--24 October. A dense key is an exact route/OD/AC cell with
        # at least 20 observations and a modal amount covering at least half.
        con.execute("""CREATE TABLE matched AS
          SELECT t.*, rm.route_id, sm1.stop_id AS boarding_stop_id, sm2.stop_id AS alighting_stop_id,
                 b.sd AS boarding_sd, a.sd AS alighting_sd,
                 CASE WHEN EXTRACT(hour FROM created_at) BETWEEN 0 AND 23 THEN EXTRACT(hour FROM created_at)::INTEGER END AS hour,
                 CASE WHEN EXTRACT(isodow FROM created_at) IN (6,7) THEN 'weekend' ELSE 'weekday' END AS day_type
          FROM tickets t
          JOIN route_map rm ON rm.route_norm=t.route_norm
          JOIN stop_map sm1 ON sm1.stop_norm=t.start_norm
          JOIN stop_map sm2 ON sm2.stop_norm=t.end_norm
          LEFT JOIN route_stop_dist b ON b.route_id=rm.route_id AND b.stop_id=sm1.stop_id
          LEFT JOIN route_stop_dist a ON a.route_id=rm.route_id AND a.stop_id=sm2.stop_id""")
        con.execute("""CREATE TABLE fare_counts AS
          SELECT route_id, boarding_stop_id, alighting_stop_id, is_ac,
                 round(amount, 2) AS amount, count(*)::INTEGER AS n
          FROM matched WHERE CAST(created_at AS DATE) BETWEEN DATE '2026-10-01' AND DATE '2026-10-24'
          GROUP BY ALL""")
        con.execute("""CREATE TABLE fare_keys AS
          SELECT route_id, boarding_stop_id, alighting_stop_id, is_ac,
                 amount AS fare_inr, n, total_n,
                 n::DOUBLE / total_n AS modal_share
          FROM (SELECT *, sum(n) OVER (PARTITION BY route_id, boarding_stop_id, alighting_stop_id, is_ac) AS total_n,
                       row_number() OVER (PARTITION BY route_id, boarding_stop_id, alighting_stop_id, is_ac ORDER BY n DESC, amount) AS rn
                FROM fare_counts)
          WHERE rn=1 AND total_n >= 20 AND n::DOUBLE / total_n >= 0.50""")
        con.execute(f"COPY (SELECT route_id, boarding_stop_id, alighting_stop_id, is_ac, fare_inr, n, total_n, modal_share FROM fare_keys ORDER BY route_id, boarding_stop_id, alighting_stop_id, is_ac) TO '{sql_path(fares_dir / 'fare_table.parquet')}' (FORMAT PARQUET)")
        con.execute(f"COPY (SELECT route_id, boarding_stop_id, alighting_stop_id, is_ac, fare_inr, n, total_n, modal_share FROM fare_keys ORDER BY route_id, boarding_stop_id, alighting_stop_id, is_ac) TO '{sql_path(fares_dir / 'fare_table.csv')}' (HEADER, DELIMITER ',')")
        # Validation uses the same dense table learned strictly from days 1--24.
        accuracy = con.execute("""SELECT count(*)::INTEGER AS n,
          sum(CASE WHEN fk.fare_inr IS NOT NULL AND round(m.amount,2)=fk.fare_inr THEN 1 ELSE 0 END)::INTEGER AS empirical_exact,
          sum(CASE WHEN fk.fare_inr IS NOT NULL THEN 1 ELSE 0 END)::INTEGER AS empirical_n,
          sum(CASE WHEN fk.fare_inr IS NULL AND m.boarding_sd IS NOT NULL AND m.alighting_sd IS NOT NULL THEN 1 ELSE 0 END)::INTEGER AS slab_fallback_n,
          sum(CASE WHEN fk.fare_inr IS NULL AND m.boarding_sd IS NOT NULL AND m.alighting_sd IS NOT NULL AND round(m.amount,2)=round(0.9 * CASE WHEN m.is_ac THEN CASE WHEN (m.alighting_sd-m.boarding_sd)/1000 <= 4 THEN 10 WHEN (m.alighting_sd-m.boarding_sd)/1000 <= 8 THEN 15 WHEN (m.alighting_sd-m.boarding_sd)/1000 <= 12 THEN 20 ELSE 25 END
             ELSE CASE WHEN (m.alighting_sd-m.boarding_sd)/1000 <= 4 THEN 5 WHEN (m.alighting_sd-m.boarding_sd)/1000 <= 10 THEN 10 ELSE 15 END END, 2) THEN 1 ELSE 0 END)::INTEGER AS slab_fallback_exact
          FROM matched m LEFT JOIN fare_keys fk USING(route_id, boarding_stop_id, alighting_stop_id, is_ac)
          WHERE CAST(m.created_at AS DATE) BETWEEN DATE '2026-10-25' AND DATE '2026-10-31'""").fetchone()
        validation = {"holdout_tickets": int(accuracy[0]), "empirical_exact": int(accuracy[1] or 0), "empirical_n": int(accuracy[2] or 0),
                      "empirical_exact_rate_on_empirical_keys": (int(accuracy[1] or 0) / int(accuracy[2])) if accuracy[2] else None,
                      "empirical_coverage": (int(accuracy[2] or 0) / int(accuracy[0])) if accuracy[0] else None,
                      "slab_fallback_n": int(accuracy[3] or 0), "slab_fallback_exact": int(accuracy[4] or 0),
                      "slab_fallback_exact_rate": (int(accuracy[4] or 0) / int(accuracy[3])) if accuracy[3] else None,
                      "model_exact_rate": (int(accuracy[1] or 0) + int(accuracy[4] or 0)) / int(accuracy[0]) if accuracy[0] else None}
        con.execute(f"COPY (SELECT boarding_stop_id AS stop_id, count(*)::INTEGER AS boardings, sum(passenger_count)::INTEGER AS passengers, count(DISTINCT route_id)::INTEGER AS routes, count(DISTINCT route_id || ':' || is_ac::VARCHAR)::INTEGER AS route_ac_cells FROM matched GROUP BY boarding_stop_id ORDER BY boardings DESC) TO '{sql_path(demand_dir / 'boardings.parquet')}' (FORMAT PARQUET)")
        con.execute(f"COPY (SELECT hour, day_type, boarding_stop_id, alighting_stop_id, count(*)::INTEGER AS tickets, sum(passenger_count)::INTEGER AS passengers FROM matched GROUP BY hour, day_type, boarding_stop_id, alighting_stop_id ORDER BY day_type, hour, tickets DESC) TO '{sql_path(demand_dir / 'od_pairs.parquet')}' (FORMAT PARQUET)")
        con.execute(f"COPY (SELECT route_id, count(*)::INTEGER AS tickets, sum(passenger_count)::INTEGER AS passengers, min(CAST(created_at AS DATE)) AS first_date, max(CAST(created_at AS DATE)) AS last_date FROM matched GROUP BY route_id ORDER BY tickets DESC) TO '{sql_path(fares_dir / 'route_profile.parquet')}' (FORMAT PARQUET)")
        type_rows = con.execute("SELECT ticket_type_id, count(*)::INTEGER AS n, min(amount), max(amount), avg(amount) FROM tickets GROUP BY ticket_type_id ORDER BY ticket_type_id").fetchall()
        amount_rows = con.execute("SELECT round(amount,2) AS amount, count(*)::INTEGER AS n FROM tickets GROUP BY amount ORDER BY n DESC LIMIT 20").fetchall()
        row_count = int(con.execute("SELECT count(*) FROM tickets").fetchone()[0])
        con.close()
    profile["ticket_type_counts"] = [{"ticket_type_id": str(r[0]), "n": int(r[1]), "min_amount": r[2], "max_amount": r[3], "mean_amount": r[4]} for r in type_rows]
    profile["common_amounts"] = [{"amount": r[0], "n": int(r[1])} for r in amount_rows]
    profile["fare_dense_keys"] = int(connectionsafe_count(fares_dir / "fare_table.parquet"))
    profile["validation"] = validation
    profile["raw_vehicle_number_dropped"] = True
    profile["source_archive"] = archive.name
    write_json(fares_dir / "profile.json", profile)
    write_json(fares_dir / "validation.json", validation)
    return profile


def connectionsafe_count(path: Path) -> int:
    con = duckdb.connect()
    n = int(con.execute(f"SELECT count(*) FROM read_parquet('{sql_path(path)}')").fetchone()[0])
    con.close()
    return n


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, default=ARCHIVE)
    args = parser.parse_args()
    result = build(args.archive)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
