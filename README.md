# Swatch

Rate clothes from small fashion labels by swiping, and the app works out what you
like from the pictures alone. Live at https://swatch.ryhub.dev while slim is up.

Built in one night. 1,634 products from 14 Shopify stores.

## How it works

There are no tags, no categories, and no hand-written rules about style. Every
product photo goes through CLIP, which turns an image into 512 numbers. Similar
looking clothes end up with similar numbers.

Your swipes turn into numbers the same way:

| Swipe | Weight |
|---|---|
| Left, nope | -1.0 |
| Right, like | +1.0 |
| Up, love | +2.0 |

Multiply each rated item's vector by its weight, add them up, and you get one
vector that points at what you like. Score the catalogue with a single matrix
multiply, sort, done.

Dislikes count for half as much as likes. A "yes" points somewhere specific. A
"no" could mean the cut, the colour, the styling, or just a bad photo, so it only
nudges you away from the worst of it.

### More than one taste

Most people like more than one kind of thing. If you like both workwear and
tailoring, averaging them into one vector points at the empty space between them,
and the app would recommend things that are neither.

So once you have 30 positives the likes get split into groups with k-means, one
vector each, and an item scores as well as its best matching group:

```python
S = M @ T.T            # every item against every taste
scores = S.max(axis=1) # keep the best match, ignore the rest
```

`k` grows as you rate more, from 1 up to 4. Below 30 positives it is the plain
single vector model, which is also what makes cold start work.

### What you get shown

Sorting purely by score would only ever show you what you already like, so the
queue of 12 is mixed:

- 10 highest scoring, round robin across your groups so one group cannot take over
- 1 where the top two groups score almost the same, because your answer settles
  something the model is unsure about
- 1 at random, the only way a style far from every group can ever surface

## Pipeline

Each step writes a file the next one reads. Everything before the server runs
once, on a laptop.

```
scrape.py           14 Shopify stores        -> data/manifest.json      1,762 products
filter_items.py     drop accessories         -> manifest.json + keep    1,634 kept
download.py         fetch images             -> data/images/            552 MB
normalize_images.py crop to 3:4 on white     -> data/normalized/        166 MB
embed.py            CLIP ViT-B/32            -> data/embeddings.npy     (1634, 512)
taste.py            ratings -> vectors       (runtime)
app.py              serve                    (runtime)
```

`/products.json` is open on every Shopify store by default, so scraping is a JSON
request per page rather than HTML parsing. Per brand the scraper keeps at most 200
products, sampled with a fixed seed, so no single label dominates. Kapital alone
would have been 40% of the corpus.

Images arrive at every aspect ratio, from 1:1 to 3:2. Portraits get cropped to
3:4, anything wider gets padded instead, because cropping a landscape photo cuts
the garment in half.

## Running it

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python pillow numpy torch torchvision \
  transformers scikit-learn fastapi uvicorn httpx python-dotenv openai

python scrape.py          # -> data/manifest.json
python filter_items.py    # marks non-garments
python download.py        # -> data/images/
python normalize_images.py
python embed.py           # -> data/embeddings.npy

.venv/bin/uvicorn app:app --port 8077
```

Then http://localhost:8077.

| Page | |
|---|---|
| `/` | swipe |
| `/report` | your groups, what they contain, what they recommend |
| `/brands/` | vote on labels to add |

Arrow keys on a laptop, drag the card on a phone. Space skips.

## Deploying

The server does not need PyTorch. Embeddings are already computed, so slim only
runs `fastapi`, `numpy`, `scikit-learn` and `httpx`. The 552 MB of original images
stay on the laptop; only the 166 MB of normalized ones ship.

```bash
./deploy.sh
```

That rsyncs to slim and restarts the service. It skips `data/ratings.db` on
purpose, since slim holds the live ratings.

Two user systemd units keep it alive: `swatch.service` and
`swatch-tunnel.service`. Linger is on, so they start at boot with nobody logged
in. The Cloudflare tunnel means no open ports and no public IP.

## Files

| | |
|---|---|
| `taste.py` | the algorithm, about 190 lines |
| `walkthrough.py` | the same numpy on 4 fake items, small enough to check by hand |
| `app.py` | queue, ratings, report, mounts the brand board at `/brands` |
| `branddir/` | brand suggestions, Wilson score ranking, auto-detects Shopify |
| `brands.json` | the 14 stores |
| `.claude/skills/plain-copy/` | rules for interface text |

Row `i` of `embeddings.npy` is `uids[i]` in `embedding_uids.json`. Order is the
only link between a vector and a product. Regenerate one without the other and
every recommendation silently points at the wrong thing.

## Known gaps

- No accounts. Everyone who opens the link rates into the same pool, and their
  swipes mix with yours.
- CLIP partly encodes photography, not just clothing, so a group can end up being
  "shot on a model" rather than a style.
- It cannot see fabric weight, how something fits, or whether it is well made.
- Brand sizes are uneven, from 200 products down to 9. Small labels rarely appear.
- No dedupe. Standard & Strange resells labels that have their own stores, so the
  same garment can appear twice.
- Prices and stock go stale. There is no re-scrape.

## What did not make it

Ader Error and Junya Watanabe need HTML parsing, COS is behind Akamai, and
risingonline.co is password locked. All four were cut for time.
