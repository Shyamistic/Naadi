"""Build the fixed validation OD set (written before any results are seen).

Three kinds of origin-destination pairs, all between bus stops of GTFS v1-2:
  * landmark: 30 named Delhi trips, including the brief's Kashmere Gate ISBT -> Nehru Place
    and Problem 2's Anand Vihar -> Connaught Place;
  * direct: 100 stop pairs on one route, stratified by ride length (2-5, 5-10, 10-20 km
    along the route) and spread over a 5 km grid. Every leg between them was observed at least
    30 times in October, so the replay ground truth exists;
  * random: 60 stop pairs 3-18 km apart, which usually need a transfer.
Departure slots (IST): 07:30 08:30 10:00 13:00 16:00 18:00 20:00 22:30.
Tier A (Google sampled first): landmarks + 50 direct + 30 random at 08:30, 13:00, 18:00, 22:30.
Tier B: the remaining pairs and slots.

Output: validation/od_set.csv and validation/od_slots.csv (seed 20261117, reproducible).
"""
from __future__ import annotations

import csv
import math
import random
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
GTFS = ROOT / "data" / "processed" / "gtfs_fixed" / "bus_v1-2"
STOPS_ON_SHAPE = ROOT / "data" / "processed" / "speed_tables" / "_work" / "stops_on_shape.parquet"
LINKS = ROOT / "data" / "processed" / "speed_tables" / "_work" / "links" / "day=2026_10_*.parquet"
OUT = ROOT / "validation"
SEED = 20261117
SLOTS_A = ["08:30", "13:00", "18:00", "22:30"]
SLOTS_B = ["07:30", "10:00", "16:00", "20:00"]

LANDMARKS = [  # (origin name, origin stop_id, destination name, destination stop_id)
    ("ISBT Kashmere Gate", "7571", "Nehru Place", "2560"),
    ("Anand Vihar ISBT", "7699", "Connaught Place (Shivaji Stadium)", "5100"),
    ("Sarai Kale Khan ISBT", "2714", "AIIMS", "2829"),
    ("Dwarka Sector 21", "8124", "Central Secretariat (Krishi Bhawan)", "1334"),
    ("Rohini Sector 21", "3", "Azadpur", "7587"),
    ("Mehrauli", "7908", "Saket", "2736"),
    ("Badarpur Border", "2640", "ITO", "1037"),
    ("Uttam Nagar", "7976", "Janakpuri A1", "3612"),
    ("Narela", "319", "ISBT Kashmere Gate", "7571"),
    ("Mayur Vihar Phase III", "7670", "ITO", "1037"),
    ("Okhla Phase 1", "2632", "Nehru Place", "2560"),
    ("Karol Bagh", "1325", "Lajpat Nagar", "2365"),
    ("Shahdara", "7829", "Red Fort", "333"),
    ("IGI Airport T1", "3602", "Dhaula Kuan", "3102"),
    ("Najafgarh", "8020", "Dhaula Kuan", "3102"),
    ("Laxmi Nagar", "7889", "Connaught Place (Shivaji Stadium)", "5100"),
    ("Old Delhi Railway Station", "7572", "New Delhi Railway Station", "1574"),
    ("Mundka", "171", "Peera Garhi", "1287"),
    ("Vasant Kunj", "2518", "Munirka", "2413"),
    ("Nangloi", "184", "Punjabi Bagh", "1934"),
    ("Bawana", "672", "Azadpur", "7587"),
    ("Kalkaji Depot", "2842", "Connaught Place (Super Bazar)", "367"),
    ("Seelampur", "929", "ITO", "1037"),
    ("Burari", "7738", "ISBT Kashmere Gate", "7571"),
    ("Tilak Nagar", "1250", "Rajouri Garden", "2695"),
    ("Sangam Vihar", "2300", "AIIMS", "2829"),
    ("Moti Nagar", "591", "Karol Bagh", "1325"),
    ("Jama Masjid", "334", "Nehru Place", "2560"),
    ("Nehru Place", "2560", "ISBT Kashmere Gate", "7571"),
    ("Connaught Place (Shivaji Stadium)", "5100", "Anand Vihar ISBT", "7699"),
]


def km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


def main() -> None:
    rnd = random.Random(SEED)
    con = duckdb.connect()
    stops = {r[0]: (r[1], float(r[2]), float(r[3])) for r in con.execute(
        f"SELECT stop_id, stop_name, stop_lat, stop_lon FROM read_csv('{GTFS / 'stops.txt'}', all_varchar=true)").fetchall()}
    nroutes = dict(con.execute(
        f"SELECT st.stop_id, count(DISTINCT t.route_id) FROM read_csv('{GTFS / 'stop_times.txt'}', all_varchar=true) st "
        f"JOIN read_csv('{GTFS / 'trips.txt'}', all_varchar=true) t USING (trip_id) GROUP BY 1").fetchall())
    rname = dict(con.execute(f"SELECT route_id, route_short_name FROM read_csv('{GTFS / 'routes.txt'}', all_varchar=true)").fetchall())

    # legs observed >= 30 times in October, per route in stop order
    cov = con.execute(f"""
        WITH n AS (SELECT route_id, ord, count(*) n FROM read_parquet('{LINKS.as_posix()}') GROUP BY 1, 2)
        SELECT s.route_id, s.stop_id, s.ord, s.sd, coalesce(n.n, 0)
        FROM read_parquet('{STOPS_ON_SHAPE.as_posix()}') s LEFT JOIN n USING (route_id, ord)
        ORDER BY s.route_id, s.ord""").fetchall()
    by_route: dict[int, list] = {}
    for rid, sid, ordn, sd, n in cov:
        by_route.setdefault(rid, []).append((sid, ordn, sd, n))

    rows = []
    for i, (on, os_, dn, ds) in enumerate(LANDMARKS):
        rows.append(dict(kind="landmark", o_stop=os_, o_name=on, d_stop=ds, d_name=dn, route_hint=""))

    # direct pairs: runs of fully observed legs, sampled by length band and grid cell
    bands = [(2, 5, 25), (5, 10, 40), (10, 20, 35)]
    cands = {b: [] for b in range(3)}
    for rid, seq in by_route.items():
        for a in range(len(seq)):
            for b in range(a + 1, len(seq)):
                if seq[b - 1][3] < 30:  # leg b-1 -> b must be observed
                    break
                L = (seq[b][2] - seq[a][2]) / 1000
                for bi, (lo, hi, _) in enumerate(bands):
                    if lo <= L < hi:
                        cands[bi].append((rid, seq[a][0], seq[b][0], L))
    used_cells, direct = set(), []
    for bi, (lo, hi, want) in enumerate(bands):
        pool = cands[bi][:]
        rnd.shuffle(pool)
        got = 0
        for rid, o, d, L in pool:
            if o not in stops or d not in stops:
                continue
            cell = (bi, round(stops[o][1] / 0.045), round(stops[o][2] / 0.05))
            if cell in used_cells:
                continue
            used_cells.add(cell)
            direct.append(dict(kind="direct", o_stop=o, o_name=stops[o][0], d_stop=d, d_name=stops[d][0],
                               route_hint=f"{rid}:{rname.get(str(rid), '')}", band=f"{lo}-{hi} km"))
            got += 1
            if got == want:
                break
    rows += direct

    # random pairs between well-served stops, 3-18 km apart
    pool = [s for s, n in nroutes.items() if n >= 3 and s in stops]
    seen, randp = set(), []
    while len(randp) < 60:
        o, d = rnd.choice(pool), rnd.choice(pool)
        dk = km(stops[o][1:], stops[d][1:])
        if not 3 <= dk <= 18 or (o, d) in seen:
            continue
        seen.add((o, d))
        randp.append(dict(kind="random", o_stop=o, o_name=stops[o][0], d_stop=d, d_name=stops[d][0], route_hint=""))
    rows += randp

    OUT.mkdir(exist_ok=True)
    tier_a_direct = {id(r) for r in direct[::2]}
    tier_a_random = {id(r) for r in randp[:30]}
    out = []
    for i, r in enumerate(rows):
        o, d = stops[r["o_stop"]], stops[r["d_stop"]]
        tier = "A" if r["kind"] == "landmark" or id(r) in tier_a_direct or id(r) in tier_a_random else "B"
        out.append(dict(od_id=f"OD{i + 1:03d}", kind=r["kind"], tier=tier, o_stop=r["o_stop"], o_name=r["o_name"],
                        o_lat=f"{o[1]:.6f}", o_lon=f"{o[2]:.6f}", d_stop=r["d_stop"], d_name=r["d_name"],
                        d_lat=f"{d[1]:.6f}", d_lon=f"{d[2]:.6f}", crow_km=f"{km(o[1:], d[1:]):.2f}",
                        route_hint=r.get("route_hint", ""), band=r.get("band", "")))
    with (OUT / "od_set.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    with (OUT / "od_slots.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["od_id", "slot", "tier"])
        for r in out:
            for s in SLOTS_A:
                w.writerow([r["od_id"], s, r["tier"]])
            for s in SLOTS_B:
                w.writerow([r["od_id"], s, "B"])
    kinds = {k: sum(1 for r in out if r["kind"] == k) for k in ("landmark", "direct", "random")}
    print(f"{len(out)} pairs {kinds}; tier A pairs {sum(r['tier'] == 'A' for r in out)}; "
          f"slots per day A={sum(r['tier'] == 'A' for r in out) * len(SLOTS_A)}, total={len(out) * 8}")


if __name__ == "__main__":
    main()
