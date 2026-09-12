"""Taste vectors from swipes.

The whole recommender. Load embeddings, turn ratings into one or more taste
vectors, score the catalogue, and decide what to show next.
"""
import json, pathlib
import numpy as np
from sklearn.cluster import KMeans

ROOT = pathlib.Path(__file__).parent

# Three-way swipe. Asymmetric on purpose: positives define where you're going,
# a dislike only nudges you off the worst stuff, because "no" is diffuse
# (could be the cut, colour, styling, or the photo) while "yes" is directional.
NOPE, LIKE, LOVE = 1, 2, 3
WEIGHTS = {LOVE: 2.0, LIKE: 1.0, NOPE: -1.0}

MIN_PER_CLUSTER = 15   # positives needed before splitting off another taste
MAX_CLUSTERS = 4
NEG_PULL = 0.5         # dislikes are subtracted from every cluster, at half strength


class Corpus:
    def __init__(self):
        M = np.load(ROOT / "data" / "embeddings.npy")
        # Mean-center, then re-normalize. CLIP vectors sit in a narrow cone
        # (mean pairwise similarity 0.73) because "product photo of clothing on
        # white" is a huge component shared by every image -- signal about
        # nothing. Removing it drops mean similarity to 0.04, and what is left
        # is the part that actually differs between garments.
        self.mean = M.mean(0)
        Mc = M - self.mean
        self.M = Mc / np.linalg.norm(Mc, axis=1, keepdims=True)

        self.uids = json.loads((ROOT / "data" / "embedding_uids.json").read_text())
        self.index = {u: i for i, u in enumerate(self.uids)}
        items = json.loads((ROOT / "data" / "manifest.json").read_text())
        self.items = {i["uid"]: i for i in items}

    # ---------------------------------------------------------------- tastes

    def _split(self, rows, weights):
        """Group the liked items into k clusters of similar style.

        k grows with evidence: one taste until you have 30 positives, then two,
        and so on. That also solves cold start for free -- early on this is
        exactly the simple single-vector model, and it only splits once there
        is enough data to justify a split.
        """
        k = int(np.clip(len(rows) // MIN_PER_CLUSTER, 1, MAX_CLUSTERS))
        if k == 1:
            return np.zeros(len(rows), dtype=int), 1
        km = KMeans(n_clusters=k, n_init=10, random_state=0)
        return km.fit_predict(self.M[rows]), k

    def taste_vectors(self, ratings):
        """ratings: {uid: NOPE|LIKE|LOVE} -> (k, 512) unit vectors, or None.

        One vector per taste. A single averaged vector cannot represent two
        different tastes: the average of "workwear" and "tailoring" points into
        the empty middle, and scores a mushy hybrid higher than either thing you
        actually liked. Separate vectors plus a max at scoring time fixes that.
        """
        pos_rows, pos_w, neg_rows, neg_w = [], [], [], []
        for uid, r in ratings.items():
            i = self.index.get(uid)
            if i is None or r not in WEIGHTS:
                continue
            if WEIGHTS[r] > 0:
                pos_rows.append(i); pos_w.append(WEIGHTS[r])
            else:
                neg_rows.append(i); neg_w.append(WEIGHTS[r])

        if not pos_rows:
            return None

        pos_rows = np.array(pos_rows); pos_w = np.array(pos_w)
        labels, k = self._split(pos_rows, pos_w)

        # Dislikes are NOT clustered. "No" is diffuse, so pretending it forms
        # distinct anti-tastes would be inventing structure; subtract it from
        # every cluster equally instead.
        neg = np.zeros(self.M.shape[1])
        if neg_rows:
            neg = np.array(neg_w) @ self.M[np.array(neg_rows)]

        out = []
        for c in range(k):
            m = labels == c
            v = pos_w[m] @ self.M[pos_rows[m]] + NEG_PULL * neg
            n = np.linalg.norm(v)
            if n > 1e-8:
                out.append(v / n)
        return np.vstack(out) if out else None

    # ---------------------------------------------------------------- scoring

    def score(self, ratings):
        """Score unrated items.

        Returns (uids, scores, cluster, margin), all aligned and unsorted.
        `cluster` is which taste matched best; `margin` is how much better that
        taste fit than the runner-up, so a small margin means the model is torn.
        """
        T = self.taste_vectors(ratings)
        unrated = np.array([i for i, u in enumerate(self.uids) if u not in ratings])
        if T is None or not len(unrated):
            z = np.zeros(len(unrated))
            return [self.uids[i] for i in unrated], z, z.astype(int), z

        S = self.M[unrated] @ T.T          # (n_unrated, k) -- every item vs every taste
        best = S.max(axis=1)               # an item is as good as its best-matching taste
        which = S.argmax(axis=1)

        if S.shape[1] >= 2:
            srt = np.sort(S, axis=1)
            margin = srt[:, -1] - srt[:, -2]
        else:
            margin = np.full(len(unrated), np.inf)   # no runner-up to compare against

        return [self.uids[i] for i in unrated], best, which, margin

    # ----------------------------------------------------------------- feed

    def feed(self, ratings, n=12, rng=None):
        """Pick the next n items: mostly confident, some uncertain, some random.

        Pure exploitation would only ever show what you already like, so the
        taste vectors would stop learning and k would never grow past whatever
        the first 30 swipes implied.
        """
        rng = rng or np.random.default_rng()
        uids, scores, which, margin = self.score(ratings)
        if not uids:
            return [], "done"
        if not ratings:
            picks = list(rng.choice(len(uids), min(n, len(uids)), replace=False))
            return [uids[i] for i in picks], "cold start"

        n_explore = max(1, n // 10)          # ~1 in 10 is a pure wildcard
        n_uncertain = 1 if np.isfinite(margin).any() else 0
        n_exploit = n - n_explore - n_uncertain

        order = np.argsort(-scores)
        chosen = []

        # Round-robin across tastes rather than sorting globally: whichever
        # cluster is strongest would otherwise dominate the feed, you would rate
        # more of it, and it would run away with the whole model.
        k = int(which.max()) + 1
        buckets = [[i for i in order if which[i] == c] for c in range(k)]
        cursors = [0] * k
        while len(chosen) < n_exploit and any(
                cursors[c] < len(buckets[c]) for c in range(k)):
            for c in range(k):
                if len(chosen) >= n_exploit:
                    break
                if cursors[c] < len(buckets[c]):
                    chosen.append(buckets[c][cursors[c]]); cursors[c] += 1

        taken = set(chosen)

        # Uncertain: sits on the boundary between two tastes, so your rating
        # resolves something the model genuinely does not know (active learning).
        if n_uncertain:
            decent = [i for i in np.argsort(margin)
                      if i not in taken and scores[i] > np.median(scores)]
            if decent:
                chosen.append(decent[0]); taken.add(decent[0])

        # Random: uncertainty sampling only probes the seams between tastes you
        # already have. Only a wildcard can surface a style far from all of them.
        pool = [i for i in range(len(uids)) if i not in taken]
        if pool:
            chosen += list(rng.choice(pool, min(n_explore, len(pool)), replace=False))

        rng.shuffle(chosen)
        return [uids[i] for i in chosen], f"{len(ratings)} rated · {k} taste{'s'[:k^1]}"


if __name__ == "__main__":
    c = Corpus()
    print("corpus:", c.M.shape)
    rng = np.random.default_rng(0)
    fake = {c.uids[i]: LOVE for i in rng.choice(len(c.uids), 40, replace=False)}
    T = c.taste_vectors(fake)
    print("tastes:", T.shape)
    uids, mode = c.feed(fake)
    print("feed:", mode, "->", len(uids), "cards")
