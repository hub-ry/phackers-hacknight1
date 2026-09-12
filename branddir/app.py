"""Crowdsourced brand directory: submit a store, vote on it, rank by Wilson score.

Self-contained - its own SQLite file and static dir, no imports from the parent app.
"""
import math, re, sqlite3, time, pathlib, asyncio, uuid
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

ROOT = pathlib.Path(__file__).parent
DB = ROOT / "data" / "brands.db"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126"
PAGE_SIZE = 250
MAX_PAGES = 10      # ~2500 products is plenty to classify a store; don't crawl forever
DELAY = 0.5         # be a polite guest on someone else's storefront
TIMEOUT = 30.0

app = FastAPI()


# ---------------------------------------------------------------- storage

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS brands (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        url TEXT NOT NULL UNIQUE,
        submitter TEXT,
        created_at REAL NOT NULL,
        platform TEXT,
        product_count INTEGER DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'pending',
        in_corpus INTEGER NOT NULL DEFAULT 0,
        error TEXT)""")
    # UNIQUE(brand_id, voter_token) is what makes a re-vote an update instead of
    # another row - the only cheap defence against double-voting without accounts.
    con.execute("""CREATE TABLE IF NOT EXISTS votes (
        brand_id INTEGER NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
        voter_token TEXT NOT NULL,
        value INTEGER NOT NULL,
        ts REAL NOT NULL,
        UNIQUE(brand_id, voter_token))""")
    seed_corpus_brands(con)
    return con


# The brands Swatch actually swipes are starred by default and always listed.
# Everything the crowd adds is a suggestion only: nobody assembles a personal
# brand stack, because pre-filtering the corpus would defeat the recommender -
# it is supposed to discover taste from a broad fixed set, not be told upfront.
def seed_corpus_brands(con):
    if con.execute("SELECT 1 FROM brands WHERE in_corpus=1").fetchone():
        return
    parent = ROOT.parent / "brands.json"
    if not parent.exists():
        return
    import json as _json
    for name, cfg in _json.loads(parent.read_text()).items():
        if "skip" in cfg:
            continue
        con.execute(
            "INSERT OR IGNORE INTO brands "
            "(name, url, submitter, created_at, platform, status, in_corpus) "
            "VALUES (?,?,?,?, 'shopify', 'done', 1)",
            (name, normalize_url(cfg["url"]), None, time.time()))
    con.commit()


# ---------------------------------------------------------------- ranking

def wilson_score(up: int, down: int, z: float = 1.96) -> float:
    """Lower bound of the 95% Wilson confidence interval on the up-vote rate.

    Raw (up - down) lets a 3/0 brand beat a 200/5 one, and raw up/(up+down)
    lets it beat it even harder: both treat a tiny sample as if it were certain.
    Wilson asks instead "given this sample, how low could the true up-rate
    plausibly be?", so few votes pull the score toward 0 and confidence is only
    earned by volume. z=1.96 is the 95% one-sided-ish normal quantile.
    """
    n = up + down
    if n == 0:
        return 0.0
    p = up / n
    z2 = z * z
    centre = p + z2 / (2 * n)
    margin = z * math.sqrt((p * (1 - p) + z2 / (4 * n)) / n)
    return (centre - margin) / (1 + z2 / n)


# ---------------------------------------------------------------- scraping

def normalize_url(raw: str) -> str:
    """Store one canonical origin per brand so votes can't be split across
    http/https, trailing slashes, or a deep link someone happened to paste."""
    raw = raw.strip()
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw
    p = urlparse(raw)
    if not p.netloc:
        raise ValueError("no hostname in URL")
    return f"{p.scheme.lower()}://{p.netloc.lower()}"


async def count_shopify_products(url: str) -> tuple[str, int]:
    """Return (platform, product_count). /products.json is Shopify's public
    catalog endpoint - its presence is the cheapest reliable platform tell."""
    total = 0
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True,
                                 headers={"User-Agent": UA}) as client:
        for page in range(1, MAX_PAGES + 1):
            r = await client.get(f"{url}/products.json",
                                 params={"limit": PAGE_SIZE, "page": page})
            if r.status_code != 200:
                # A non-Shopify site usually answers the first page with 404/403
                # or an HTML error page; anything after page 1 just ends paging.
                if page == 1:
                    return "unknown", 0
                break
            try:
                products = r.json()["products"]
            except Exception:
                if page == 1:
                    return "unknown", 0
                break
            total += len(products)
            if len(products) < PAGE_SIZE:
                break
            await asyncio.sleep(DELAY)
    return "shopify", total


async def scrape_brand(brand_id: int, url: str):
    """Background job. Failures are recorded, never raised - a bad submission
    should leave a visible 'failed' badge, not take the request worker down."""
    try:
        platform, count = await count_shopify_products(url)
        with db() as con:
            con.execute("UPDATE brands SET platform=?, product_count=?, "
                        "status='done', error=NULL WHERE id=?",
                        (platform, count, brand_id))
    except Exception as e:
        with db() as con:
            con.execute("UPDATE brands SET platform='unknown', product_count=0, "
                        "status='failed', error=? WHERE id=?",
                        (f"{type(e).__name__}: {e}"[:300], brand_id))


# ---------------------------------------------------------------- api

class Submission(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=3, max_length=500)
    submitter: str | None = Field(default=None, max_length=60)


class Vote(BaseModel):
    brand_id: int
    value: int          # +1 up, -1 down
    voter_token: str = Field(min_length=8, max_length=64)


def row_to_brand(r: sqlite3.Row) -> dict:
    return {
        "id": r["id"],
        "name": r["name"],
        "url": r["url"],
        "domain": urlparse(r["url"]).netloc.replace("www.", ""),
        "submitter": r["submitter"],
        "created_at": r["created_at"],
        "platform": r["platform"],
        "product_count": r["product_count"],
        "status": r["status"],
        "in_corpus": r["in_corpus"],
        "error": r["error"],
        "up": r["up"],
        "down": r["down"],
        "score": r["up"] - r["down"],
        "wilson": wilson_score(r["up"], r["down"]),
    }


@app.get("/api/brands")
def list_brands():
    with db() as con:
        rows = con.execute("""
            SELECT b.*,
                   COALESCE(SUM(v.value = 1), 0)  AS up,
                   COALESCE(SUM(v.value = -1), 0) AS down
            FROM brands b LEFT JOIN votes v ON v.brand_id = b.id
            GROUP BY b.id""").fetchall()
    brands = [row_to_brand(r) for r in rows]
    # Wilson first; newest wins ties so a fresh unvoted submission is visible.
    # Starred (in-corpus) brands first, then suggestions by Wilson score.
    brands.sort(key=lambda b: (-b["in_corpus"], -b["wilson"], -b["created_at"]))
    for i, b in enumerate(brands, 1):
        b["rank"] = i
    return {"brands": brands}


@app.post("/api/brands")
def submit(s: Submission, background: BackgroundTasks):
    try:
        url = normalize_url(s.url)
    except ValueError as e:
        raise HTTPException(400, str(e))
    with db() as con:
        existing = con.execute("SELECT id FROM brands WHERE url=?", (url,)).fetchone()
        if existing:
            raise HTTPException(409, "that store is already in the directory")
        cur = con.execute(
            "INSERT INTO brands (name, url, submitter, created_at, status) "
            "VALUES (?,?,?,?, 'pending')",
            (s.name.strip(), url, (s.submitter or "").strip() or None, time.time()))
        brand_id = cur.lastrowid
    # Scraping a storefront takes seconds to a minute; the submitter shouldn't wait.
    background.add_task(scrape_brand, brand_id, url)
    return {"ok": True, "id": brand_id}


@app.post("/api/vote")
def vote(v: Vote):
    if v.value not in (1, -1):
        raise HTTPException(400, "value must be 1 or -1")
    with db() as con:
        if not con.execute("SELECT 1 FROM brands WHERE id=?", (v.brand_id,)).fetchone():
            raise HTTPException(404, "no such brand")
        # Re-voting overwrites: flipping up->down must not leave both on record.
        con.execute("INSERT INTO votes (brand_id, voter_token, value, ts) VALUES (?,?,?,?) "
                    "ON CONFLICT(brand_id, voter_token) DO UPDATE SET value=?, ts=?",
                    (v.brand_id, v.voter_token, v.value, time.time(), v.value, time.time()))
        row = con.execute(
            "SELECT COALESCE(SUM(value=1),0) up, COALESCE(SUM(value=-1),0) down "
            "FROM votes WHERE brand_id=?", (v.brand_id,)).fetchone()
    return {"ok": True, "up": row["up"], "down": row["down"],
            "score": row["up"] - row["down"]}


@app.get("/api/votes/{voter_token}")
def my_votes(voter_token: str):
    """Lets a returning browser paint its own up/down buttons as already pressed."""
    with db() as con:
        rows = con.execute("SELECT brand_id, value FROM votes WHERE voter_token=?",
                           (voter_token,)).fetchall()
    return {"votes": {str(r["brand_id"]): r["value"] for r in rows}}


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")
