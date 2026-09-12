"""Mark non-garment / small-object items so they stay out of the swipe corpus.

Matching is word-boundary based: naive substring matching wrongly killed
"baggy" (bag), "patchwork" (patch) and "necklace" (lace).
"""
import json, pathlib, re

ROOT = pathlib.Path(__file__).parent

DENY = [
    # jewelry & small metal
    "jewelry", "jewellery", "necklace", "necklaces", "bracelet", "bracelets",
    "earring", "earrings", "pendant", "pendants", "signet", "brooch",
    # eyewear
    "sunglasses", "eyewear", "spectacles", "goggles",
    # fragrance / home / print
    "perfume", "fragrance", "cologne", "candle", "candles", "incense",
    "homeware", "houseware", "blanket", "towel", "mug", "ceramics",
    "book", "books", "magazine", "zine", "poster", "postcard", "sticker", "stickers",
    # small carry / misc
    "keychain", "keyring", "wallet", "cardholder", "tote", "backpack",
    "socks", "sock", "belt", "belts", "gift card", "giftcard", "deposit",
]
DENY_RE = re.compile(r"\b(?:" + "|".join(re.escape(d) for d in DENY) + r")\b")


def is_garment(item):
    hay = " ".join(
        [item["title"], item["product_type"], " ".join(item["tags"])]
    ).lower()
    return not DENY_RE.search(hay)


def main():
    p = ROOT / "data" / "manifest.json"
    items = json.loads(p.read_text())
    for it in items:
        it["keep"] = is_garment(it)
    p.write_text(json.dumps(items, indent=2))
    dropped = [i for i in items if not i["keep"]]
    print(f"keep {len(items)-len(dropped)} / {len(items)}  (dropped {len(dropped)})")
    print("\n-- all dropped --")
    for it in dropped:
        print(f"  [{it['brand']:18}] {it['title'][:60]}")


if __name__ == "__main__":
    main()
