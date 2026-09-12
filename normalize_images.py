"""Crop/pad every product image to a uniform 3:4 canvas on a neutral background."""
import json, pathlib, concurrent.futures as cf
from PIL import Image, ImageOps
import download

ROOT = pathlib.Path(__file__).parent
OUT = ROOT / "data" / "normalized"
W, H = 768, 1024
TARGET_AR = W / H          # 0.75
BG = (255, 255, 255)     # match the dominant white product photography
MARGIN = 0.04              # breathing room when padding


def trim_border(im):
    """Drop uniform surrounding whitespace so garments sit at a consistent scale."""
    gray = im.convert("L")
    # Anything near the corner color is treated as background.
    bbox = ImageOps.invert(gray.point(lambda p: 255 if p > 246 else 0)).getbbox()
    if bbox:
        w, h = im.size
        # Ignore absurd crops (busy/dark photos where the heuristic misfires).
        if (bbox[2] - bbox[0]) > w * 0.2 and (bbox[3] - bbox[1]) > h * 0.2:
            return im.crop(bbox)
    return im


def fit(im):
    im = im.convert("RGB")
    im = trim_border(im)
    w, h = im.size
    ar = w / h

    if ar > TARGET_AR:
        # Wider than 3:4 (squares, landscapes): PAD, never crop -- cropping a
        # landscape shot would slice the garment in half.
        scale = (W * (1 - MARGIN)) / w
    else:
        # Taller than 3:4: crop top/bottom lightly by filling the width.
        scale = W / w

    new = (max(1, round(w * scale)), max(1, round(h * scale)))
    im = im.resize(new, Image.LANCZOS)

    canvas = Image.new("RGB", (W, H), BG)
    if im.height > H:
        # Crop from slightly above center: garments sit high, shoes get cut, not collars.
        top = int((im.height - H) * 0.35)
        im = im.crop((0, top, im.width, top + H))
    canvas.paste(im, ((W - im.width) // 2, (H - im.height) // 2))
    return canvas


def process(item):
    src = download.cache_path(item)
    dest = OUT / f"{src.stem}.jpg"
    if dest.exists():
        return "cached"
    if not src.exists():
        return "missing"
    try:
        with Image.open(src) as im:
            fit(im).save(dest, "JPEG", quality=88, optimize=True)
        return "ok"
    except Exception as e:
        print(f"  ! {item['uid']}: {type(e).__name__} {e}")
        return "fail"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    items = json.loads((ROOT / "data" / "manifest.json").read_text())
    items = [i for i in items if i.get("keep", True)]
    counts = {}
    with cf.ThreadPoolExecutor(8) as pool:
        for i, s in enumerate(pool.map(process, items), 1):
            counts[s] = counts.get(s, 0) + 1
            if i % 400 == 0:
                print(f"  {i}/{len(items)} {counts}")
    print("done:", counts)


if __name__ == "__main__":
    main()
