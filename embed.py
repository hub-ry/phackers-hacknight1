"""Turn every normalized product image into a unit-length CLIP vector."""
import json, pathlib
import numpy as np, torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor
import download

ROOT = pathlib.Path(__file__).parent
NORM = ROOT / "data" / "normalized"
MODEL_ID = "openai/clip-vit-base-patch32"
BATCH = 32


def device():
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def main():
    items = [i for i in json.loads((ROOT / "data" / "manifest.json").read_text())
             if i.get("keep", True)]
    dev = device()
    print(f"device={dev}  items={len(items)}")

    model = CLIPModel.from_pretrained(MODEL_ID).to(dev).eval()
    proc = CLIPProcessor.from_pretrained(MODEL_ID)

    uids, vecs = [], []
    for start in range(0, len(items), BATCH):
        chunk = items[start:start + BATCH]
        imgs, keep = [], []
        for it in chunk:
            p = NORM / f"{download.cache_path(it).stem}.jpg"
            if p.exists():
                imgs.append(Image.open(p).convert("RGB"))
                keep.append(it["uid"])
        if not imgs:
            continue
        inputs = proc(images=imgs, return_tensors="pt").to(dev)
        with torch.no_grad():
            out = model.get_image_features(**inputs)
        # transformers v5 returns an output object; pooler_output is the 512-d
        # projected image embedding (older versions returned the tensor directly).
        f = out.pooler_output if hasattr(out, "pooler_output") else out
        # Unit-normalize so a dot product IS cosine similarity.
        f = f / f.norm(dim=-1, keepdim=True)
        vecs.append(f.cpu().numpy().astype("float32"))
        uids += keep
        for im in imgs:
            im.close()
        if (start // BATCH) % 10 == 0:
            print(f"  {start + len(chunk)}/{len(items)}")

    M = np.vstack(vecs)
    np.save(ROOT / "data" / "embeddings.npy", M)
    (ROOT / "data" / "embedding_uids.json").write_text(json.dumps(uids))
    print(f"wrote embeddings {M.shape} -> data/embeddings.npy")
    # Sanity: norms should be 1.0, and a vector should match itself at 1.0.
    print("norm mean:", float(np.linalg.norm(M, axis=1).mean()))
    print("self-sim:", float(M[0] @ M[0]))
    print("mean pairwise sim (first 300):", float((M[:300] @ M[:300].T).mean()))


if __name__ == "__main__":
    main()
