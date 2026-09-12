"""Scrape product catalogs from Shopify stores into a single manifest."""
import json, random, time, urllib.request, urllib.error, pathlib

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126"
PER_BRAND_CAP = 200
PAGE_SIZE = 250
DELAY = 0.6
ROOT = pathlib.Path(__file__).parent


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def products_url(base, collection, page):
    path = f"/collections/{collection}/products.json" if collection else "/products.json"
    return f"{base}{path}?limit={PAGE_SIZE}&page={page}"


def fetch_brand(name, cfg):
    """Page through a store's public catalog until a short page ends it."""
    out, page = [], 1
    while True:
        url = products_url(cfg["url"], cfg.get("collection"), page)
        try:
            batch = fetch_json(url)["products"]
        except (urllib.error.URLError, KeyError, TimeoutError) as e:
            print(f"  ! {name} page {page}: {e}")
            break
        out += batch
        print(f"  {name} page {page}: +{len(batch)} (total {len(out)})")
        if len(batch) < PAGE_SIZE:
            break
        page += 1
        time.sleep(DELAY)
    return out


def normalize(name, raw):
    """Keep only the fields we need, one record per product with a usable image."""
    images = raw.get("images") or []
    if not images:
        return None
    variants = raw.get("variants") or [{}]
    return {
        "uid": f"{name}:{raw['id']}",
        "brand": name,
        "title": raw["title"],
        "product_type": raw.get("product_type", ""),
        "tags": raw.get("tags", []),
        "price": variants[0].get("price"),
        "url": f"{raw['handle']}",
        "image": images[0]["src"],
        "image_wh": [images[0].get("width"), images[0].get("height")],
        "n_images": len(images),
    }


def main():
    brands = json.loads((ROOT / "brands.json").read_text())
    rng = random.Random(42)
    manifest = []

    for name, cfg in brands.items():
        if "skip" in cfg:
            print(f"- {name}: skipped ({cfg['skip']})")
            continue
        raw = fetch_brand(name, cfg)
        items = [r for r in (normalize(name, p) for p in raw) if r]
        if len(items) > PER_BRAND_CAP:
            items = rng.sample(items, PER_BRAND_CAP)
        print(f"= {name}: {len(items)} kept\n")
        manifest += items

    path = ROOT / "data" / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2))
    print(f"wrote {len(manifest)} products -> {path}")


if __name__ == "__main__":
    main()
