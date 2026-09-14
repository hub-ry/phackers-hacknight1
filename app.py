"""Swatch server: swipe queue, taste report, and the brand suggestion board."""
import json, pathlib, sqlite3, sys, time, collections, re
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import numpy as np

import download, taste

ROOT = pathlib.Path(__file__).parent
DB = ROOT / "data" / "ratings.db"
NORM = ROOT / "data" / "normalized"
QUEUE = 12

app = FastAPI()
corpus = taste.Corpus()

# Product pages live at <store>/products/<handle>; the manifest only keeps the
# handle, so the store base comes back from brands.json.
BRAND_BASE = {k: v["url"].rstrip("/")
              for k, v in json.loads((ROOT / "brands.json").read_text()).items()}


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
        "link": f"{BRAND_BASE.get(it['brand'], '')}/products/{it['url']}",
    }


class Rating(BaseModel):
    uid: str
    rating: int  # 1 nope, 2 like, 3 love


@app.get("/api/queue")
def queue():
    ratings = all_ratings()
    uids, mode = corpus.feed(ratings, n=QUEUE)
    return {"cards": [card(u) for u in uids], "rated": len(ratings), "mode": mode}


@app.post("/api/rate")
def rate(r: Rating):
    if r.rating not in taste.WEIGHTS:
        return {"ok": False, "error": "rating must be 1 (nope), 2 (like) or 3 (love)"}
    with db() as con:
        con.execute("INSERT OR REPLACE INTO ratings VALUES (?,?,?)",
                    (r.uid, r.rating, time.time()))
    return {"ok": True}


@app.post("/api/undo")
def undo():
    with db() as con:
        con.execute("DELETE FROM ratings WHERE ts = (SELECT MAX(ts) FROM ratings)")
    return {"ok": True}


@app.post("/api/reset")
def reset(request: Request):
    """Wipe every rating: the taste vectors are derived, so this clears them too.

    Loopback only. The app is served publicly through a tunnel, and this is the
    one endpoint a stranger with the URL could use to destroy real data.
    """
    host = request.client.host if request.client else ""
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(403, "reset is only available on the machine hosting swatch")
    import shutil
    with db() as con:
        n = con.execute("SELECT COUNT(*) FROM ratings").fetchone()[0]
    shutil.copy(DB, DB.with_suffix(".db.backup"))   # never lose swipes to one click
    with db() as con:
        con.execute("DELETE FROM ratings")
    return {"ok": True, "cleared": n}


# Words that describe a garment's shape or finish rather than naming the product,
# so a cluster summary reads like a style rather than like a product list.
STOP = set("""the a an and or for with of in on to by new ss aw fw men women mens
womens unisex size one 20 21 22 23 24 25 26 27 co ltd inc rts""".split())


def describe(uids, n=6):
    """Cheapest honest summary of a cluster: what its titles and tags repeat."""
    words = collections.Counter()
    brands = collections.Counter()
    for u in uids:
        it = corpus.items[u]
        brands[it["brand"]] += 1
        text = f"{it['title']} {it['product_type']} {' '.join(it['tags'])}".lower()
        for w in re.findall(r"[a-z][a-z'-]{2,}", text):
            if w not in STOP:
                words[w] += 1
    return {
        "words": [w for w, _ in words.most_common(n)],
        "brands": [b for b, _ in brands.most_common(3)],
    }


@app.get("/api/report")
def report():
    """Describe the taste the swipes have produced so far."""
    ratings = all_ratings()
    hist = collections.Counter(ratings.values())
    n_pos = hist[taste.LIKE] + hist[taste.LOVE]

    out = {
        "rated": len(ratings),
        "loved": hist[taste.LOVE], "liked": hist[taste.LIKE], "noped": hist[taste.NOPE],
        "ready": n_pos >= 8,
        "clusters": [], "top_picks": [], "avoiding": {},
    }
    if not out["ready"]:
        out["message"] = f"rate {8 - n_pos} more things you like to get a report"
        return out

    T = corpus.taste_vectors(ratings)
    uids, scores, which, margin = corpus.score(ratings)
    order = np.argsort(-scores)

    # Describe each taste by the items you rated into it, not by the items it
    # recommends -- the report should reflect your swipes, not the model's guess.
    pos = {u: r for u, r in ratings.items() if taste.WEIGHTS.get(r, 0) > 0}
    pos_uids = list(pos)
    if pos_uids:
        P = corpus.M[[corpus.index[u] for u in pos_uids]] @ T.T
        owner = P.argmax(axis=1)
        for c in range(T.shape[0]):
            members = [pos_uids[i] for i in range(len(pos_uids)) if owner[i] == c]
            if not members:
                continue
            d = describe(members)
            picks = [i for i in order if which[i] == c][:3]
            out["clusters"].append({
                "id": c, "size": len(members),
                "words": d["words"], "brands": d["brands"],
                "examples": [corpus.items[u]["title"] for u in members[:3]],
                "recommends": [card(uids[i]) | {"score": round(float(scores[i]), 3)}
                               for i in picks],
            })

    out["top_picks"] = [card(uids[i]) | {"score": round(float(scores[i]), 3)}
                        for i in order[:6]]

    noped = [u for u, r in ratings.items() if r == taste.NOPE]
    if noped:
        out["avoiding"] = describe(noped)
    return out


@app.get("/api/liked")
def liked():
    """Everything rated love or like, loved first, each in the order it was rated."""
    with db() as con:
        rows = list(con.execute(
            "SELECT uid, rating FROM ratings WHERE rating IN (?,?) ORDER BY rating DESC, ts",
            (taste.LIKE, taste.LOVE)))
        noped = con.execute("SELECT COUNT(*) FROM ratings WHERE rating = ?",
                            (taste.NOPE,)).fetchone()[0]
    items = [card(u) | {"rating": r} for u, r in rows if u in corpus.items]
    return {
        "loved": [c for c in items if c["rating"] == taste.LOVE],
        "liked": [c for c in items if c["rating"] == taste.LIKE],
        "noped": noped,
        "rated": len(rows) + noped,
    }


@app.get("/api/stats")
def stats():
    with db() as con:
        rows = list(con.execute(
            "SELECT rating, COUNT(*) FROM ratings GROUP BY rating ORDER BY rating"))
    return {"histogram": {str(r): c for r, c in rows}}


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/report")
def report_page():
    return FileResponse(ROOT / "static" / "report.html")


app.mount("/img", StaticFiles(directory=NORM), name="img")

# The brand board runs as a sub-app so there is one server and one URL to host,
# rather than asking anyone to remember a second port.
sys.path.insert(0, str(ROOT / "branddir"))
import importlib.util
_spec = importlib.util.spec_from_file_location("branddir_app", ROOT / "branddir" / "app.py")
_bd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bd)
app.mount("/brands", _bd.app, name="brands")
