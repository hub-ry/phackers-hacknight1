"""Taste vectors from ratings.

The real algorithm (k clusters, uncertainty sampling, round-robin) slots in at
score(). For now this is the single-vector version so the UI has a live feed.
"""
import json, pathlib
import numpy as np

ROOT = pathlib.Path(__file__).parent

# Three-way swipe. Asymmetric on purpose: positives define where you're going,
# a dislike only nudges you off the worst stuff, because "no" is diffuse
# (could be the cut, colour, styling, or the photo) while "yes" is directional.
NOPE, LIKE, LOVE = 1, 2, 3
WEIGHTS = {LOVE: 2.0, LIKE: 1.0, NOPE: -1.0}


class Corpus:
    def __init__(self):
        M = np.load(ROOT / "data" / "embeddings.npy")
        # Mean-center, then re-normalize: CLIP vectors sit in a narrow cone
        # (mean pairwise sim 0.73), which makes raw dot products nearly uniform.
        self.mean = M.mean(0)
        Mc = M - self.mean
        self.M = Mc / np.linalg.norm(Mc, axis=1, keepdims=True)

        self.uids = json.loads((ROOT / "data" / "embedding_uids.json").read_text())
        self.index = {u: i for i, u in enumerate(self.uids)}
        items = json.loads((ROOT / "data" / "manifest.json").read_text())
        self.items = {i["uid"]: i for i in items}

    def taste_vector(self, ratings):
        """ratings: {uid: NOPE|LIKE|LOVE} -> one unit vector, or None if no signal."""
        rows, weights = [], []
        for uid, r in ratings.items():
            w = WEIGHTS.get(r, 0.0)
            if w != 0.0 and uid in self.index:
                rows.append(self.index[uid])
                weights.append(w)
        if not rows:
            return None
        v = np.asarray(weights) @ self.M[rows]      # weighted sum of rated vectors
        n = np.linalg.norm(v)
        return None if n < 1e-8 else v / n

    def score(self, ratings):
        """Score every unrated item. Returns (uids, scores) sorted best-first."""
        t = self.taste_vector(ratings)
        unrated = [i for i, u in enumerate(self.uids) if u not in ratings]
        if t is None:
            # Cold start: nothing learned yet, so order is arbitrary.
            return [self.uids[i] for i in unrated], np.zeros(len(unrated))
        s = self.M[unrated] @ t                     # the whole recommender
        order = np.argsort(-s)
        return [self.uids[unrated[i]] for i in order], s[order]


if __name__ == "__main__":
    c = Corpus()
    print("corpus:", c.M.shape)
    fake = {c.uids[i]: LOVE for i in range(0, 60, 20)}
    uids, s = c.score(fake)
    print("top 5 for a fake taste:")
    for u, sc in zip(uids[:5], s[:5]):
        print(f"  {sc:.3f}  {c.items[u]['title'][:50]}")
