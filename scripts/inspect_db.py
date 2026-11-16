"""Print schema, row counts and sample rows of a SQLite bus-movements day file."""
import sqlite3
import sys

path = sys.argv[1]
c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
for name, sql in c.execute("select name, sql from sqlite_master"):
    print(name, sql)
for (t,) in c.execute("select name from sqlite_master where type='table'").fetchall():
    print(t, c.execute(f"select count(*) from {t}").fetchone())
    for r in c.execute(f"select * from {t} limit 3"):
        print("  ", r)
