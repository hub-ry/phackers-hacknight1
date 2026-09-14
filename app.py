"""Swatch server: swipe queue, taste report, and the brand suggestion board."""
import json, pathlib, sqlite3, sys, time, uuid, collections, re
from fastapi import FastAPI, Request, Response
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
                "user_id TEXT NOT NULL, uid TEXT NOT NULL, "
                "rating INTEGER NOT NULL, ts REAL NOT NULL, "
                "PRIMARY KEY (user_id, uid))")
    return con


# A coat check ticket, not an account: the id names which rows are yours and
# carries no meaning of its own. 122 random bits, so nobody guesses their way
# into someone else's taste, which is also why it needs no signature.
COOKIE = "swatch_uid"
COOKIE_YEARS = 10


def user_id(request: Request, response: Response) -> str:
    uid = request.cookies.get(COOKIE)
    if not uid:
        uid = uuid.uuid4().hex
        response.set_cookie(COOKIE, uid, max_age=COOKIE_YEARS * 365 * 24 * 3600,
                            path="/", httponly=True, secure=True, samesite="lax")
    return uid


def all_ratings(user):
    with db() as con:
        return {u: r for u, r in con.execute(
            "SELECT uid, rating FROM ratings WHERE user_id = ?", (user,))}


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
def queue(request: Request, response: Response):
    ratings = all_ratings(user_id(request, response))
    uids, mode = corpus.feed(ratings, n=QUEUE)
    return {"cards": [card(u) for u in uids], "rated": len(ratings), "mode": mode}


@app.post("/api/rate")
def rate(r: Rating, request: Request, response: Response):
    if r.rating not in taste.WEIGHTS:
        return {"ok": False, "error": "rating must be 1 (nope), 2 (like) or 3 (love)"}
    with db() as con:
        con.execute("INSERT OR REPLACE INTO ratings VALUES (?,?,?,?)",
                    (user_id(request, response), r.uid, r.rating, time.time()))
    return {"ok": True}


@app.post("/api/undo")
def undo(request: Request, response: Response):
    me = user_id(request, response)
    with db() as con:
        con.execute("DELETE FROM ratings WHERE user_id = ? AND ts = "
                    "(SELECT MAX(ts) FROM ratings WHERE user_id = ?)", (me, me))
    return {"ok": True}


@app.post("/api/reset")
def reset(request: Request, response: Response):
    """Wipe the caller's ratings: the taste vectors are derived, so they go too.

    Scoped to one user, so the button on the taste page can no longer take
    everyone else's swipes down with it.
    """
    import shutil
    me = user_id(request, response)
    with db() as con:
        n = con.execute("SELECT COUNT(*) FROM ratings WHERE user_id = ?",
                        (me,)).fetchone()[0]
    shutil.copy(DB, DB.with_suffix(".db.backup"))   # never lose swipes to one click
    with db() as con:
        con.execute("DELETE FROM ratings WHERE user_id = ?", (me,))
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
def report(request: Request, response: Response):
    """Describe the taste the swipes have produced so far."""
    ratings = all_ratings(user_id(request, response))
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
def liked(request: Request, response: Response):
    """Everything rated love or like, loved first, each in the order it was rated."""
    me = user_id(request, response)
    with db() as con:
        rows = list(con.execute(
            "SELECT uid, rating FROM ratings WHERE user_id = ? AND rating IN (?,?) "
            "ORDER BY rating DESC, ts", (me, taste.LIKE, taste.LOVE)))
        noped = con.execute(
            "SELECT COUNT(*) FROM ratings WHERE user_id = ? AND rating = ?",
            (me, taste.NOPE)).fetchone()[0]
    items = [card(u) | {"rating": r} for u, r in rows if u in corpus.items]
    return {
        "loved": [c for c in items if c["rating"] == taste.LOVE],
        "liked": [c for c in items if c["rating"] == taste.LIKE],
        "noped": noped,
        "rated": len(rows) + noped,
    }


@app.get("/api/stats")
def stats(request: Request, response: Response):
    with db() as con:
        rows = list(con.execute(
            "SELECT rating, COUNT(*) FROM ratings WHERE user_id = ? "
            "GROUP BY rating ORDER BY rating", (user_id(request, response),)))
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
