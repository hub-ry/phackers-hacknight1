"""One-off: give every rating an owner.

The table was keyed by product alone, so everyone who opened swatch swiped into
the same pile. This rewrites it keyed by (user_id, product) and hands the
existing rows to OWNER, whoever was swiping before there was such a thing.

Safe to run twice: it does nothing if the table already has a user_id column.
Run it once here and once on slim, since deploy.sh never copies the database.
"""
import pathlib, shutil, sqlite3, sys

DB = pathlib.Path(__file__).parent / "data" / "ratings.db"
OWNER = sys.argv[1] if len(sys.argv) > 1 else "ryan"

con = sqlite3.connect(DB)
cols = [r[1] for r in con.execute("PRAGMA table_info(ratings)")]
if "user_id" in cols:
    print("already migrated")
    sys.exit()

shutil.copy(DB, DB.with_suffix(".db.premigrate"))
n = con.execute("SELECT COUNT(*) FROM ratings").fetchone()[0]
with con:
    con.execute("ALTER TABLE ratings RENAME TO ratings_old")
    con.execute("CREATE TABLE ratings (user_id TEXT NOT NULL, uid TEXT NOT NULL, "
                "rating INTEGER NOT NULL, ts REAL NOT NULL, "
                "PRIMARY KEY (user_id, uid))")
    con.execute("INSERT INTO ratings SELECT ?, uid, rating, ts FROM ratings_old",
                (OWNER,))
    con.execute("DROP TABLE ratings_old")
print(f"moved {n} ratings to {OWNER}; backup at {DB.with_suffix('.db.premigrate').name}")
