"""Download product images concurrently, with on-disk caching."""
import json, pathlib, hashlib, concurrent.futures as cf
import httpx

ROOT = pathlib.Path(__file__).parent
RAW = ROOT / "data" / "images"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126"
WORKERS = 16


def cache_path(item):
    """Stable filename per product, extension preserved from the CDN url."""
    ext = item["image"].split("?")[0].rsplit(".", 1)[-1].lower()
    if ext not in {"jpg", "jpeg", "png", "webp", "avif"}:
        ext = "jpg"
    key = hashlib.sha1(item["uid"].encode()).hexdigest()[:16]
    return RAW / f"{item['brand']}_{key}.{ext}"


def fetch(client, item):
    dest = cache_path(item)
    if dest.exists() and dest.stat().st_size > 1000:
        return "cached", item["uid"]
    try:
        # Shopify CDN resizes on demand; ask for what we need, not the 4320px original.
        url = item["image"]
        sep = "&" if "?" in url else "?"
        r = client.get(f"{url}{sep}width=1200", timeout=30, follow_redirects=True)
        r.raise_for_status()
        dest.write_bytes(r.content)
        return "ok", item["uid"]
    except Exception as e:
        return f"fail {type(e).__name__}", item["uid"]


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    items = json.loads((ROOT / "data" / "manifest.json").read_text())
    counts = {}
    with httpx.Client(headers={"User-Agent": UA}, http2=False) as client:
        with cf.ThreadPoolExecutor(WORKERS) as pool:
            for i, (status, uid) in enumerate(
                pool.map(lambda it: fetch(client, it), items), 1
            ):
                key = status.split()[0]
                counts[key] = counts.get(key, 0) + 1
                if i % 200 == 0:
                    print(f"  {i}/{len(items)} {counts}")
                if status.startswith("fail"):
                    print(f"  ! {uid}: {status}")
    print("done:", counts)


if __name__ == "__main__":
    main()
