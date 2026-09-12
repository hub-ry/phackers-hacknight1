"""Swatch server: serves the swipe queue and records 1-5 ratings."""
import json, pathlib, sqlite3, random
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import download, taste

ROOT = pathlib.Path(__file__).parent
DB = ROOT / "data" / "ratings.db"
NORM = ROOT / "data" / "normalized"
QUEUE = 12

app = FastAPI()
corpus = taste.Corpus()


def db():
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS ratings ("
                "uid TEXT PRIMARY KEY, rating INTEGER, ts REAL)")
    return con


def all_ratings():
    with db() as con:
        return {u: r for u, r in con.execute("SELECT uid, rating FROM ratings")}


def card(uid):
    it = corpus.items[uid]
    return {
        "uid": uid,
        "title": it["title"],
        "brand": it["brand"],
        "price": it["price"],
        "image": f"/img/{download.cache_path(it).stem}.jpg",
    }


class Rating(BaseModel):
    uid: str
    rating: int


@app.get("/api/queue")
def queue():
    ratings = all_ratings()
    uids, scores = corpus.score(ratings)
    if not uids:
        return {"cards": [], "rated": len(ratings), "mode": "done"}

    if not ratings:
        # Cold start: no taste yet, so show a random spread.
        picks = random.sample(uids, min(QUEUE, len(uids)))
        mode = "cold start - rating at random"
    else:
        # 80/20 exploit/explore so the taste vector keeps learning.
        n_exploit = int(QUEUE * 0.8)
        picks = uids[:n_exploit]
        rest = uids[n_exploit:]
        picks += random.sample(rest, min(QUEUE - n_exploit, len(rest)))
        random.shuffle(picks)
        mode = f"taste from {len(ratings)} ratings"

    return {"cards": [card(u) for u in picks], "rated": len(ratings), "mode": mode}


@app.post("/api/rate")
def rate(r: Rating):
    import time
    with db() as con:
        con.execute("INSERT OR REPLACE INTO ratings VALUES (?,?,?)",
                    (r.uid, r.rating, time.time()))
    return {"ok": True}


@app.post("/api/undo")
def undo():
    with db() as con:
        con.execute("DELETE FROM ratings WHERE ts = (SELECT MAX(ts) FROM ratings)")
    return {"ok": True}


@app.get("/api/stats")
def stats():
    with db() as con:
        rows = list(con.execute(
            "SELECT rating, COUNT(*) FROM ratings GROUP BY rating ORDER BY rating"))
    return {"histogram": {str(r): c for r, c in rows}}


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


app.mount("/img", StaticFiles(directory=NORM), name="img")
