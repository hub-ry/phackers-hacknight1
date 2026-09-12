"""Run me: .venv/bin/python walkthrough.py

Every numpy operation the recommender uses, on 4 fake items with 3 dimensions
instead of 1634 items with 512 -- small enough to verify by hand.
"""
import numpy as np
np.set_printoptions(precision=3, suppress=True)

def head(n, t): print(f"\n{'='*62}\n{n}. {t}\n{'='*62}")

# ---------------------------------------------------------------------------
head(1, "THE CORPUS: a matrix, one row per item")

M = np.array([
    [ 1.0,  0.0,  0.0],   # 0: blue jeans
    [ 0.9,  0.1,  0.0],   # 1: black jeans   (similar to 0)
    [ 0.0,  1.0,  0.0],   # 2: white tee     (unrelated)
    [ 0.0,  0.9,  0.1],   # 3: grey tee      (similar to 2)
])
names = ["blue jeans", "black jeans", "white tee", "grey tee"]
print("M =\n", M)
print("\nM.shape =", M.shape, "-> (4 items, 3 dimensions)")
print("M[0] =", M[0], "  <- one item's vector, a row")
print("M[:, 0] =", M[:, 0], "  <- one dimension across all items, a column")

# ---------------------------------------------------------------------------
head(2, "NORMALIZE: make every vector length 1")

lengths = np.linalg.norm(M, axis=1)
print("np.linalg.norm(M, axis=1) =", lengths)
print("  axis=1 means 'collapse the columns' -> one number per ROW")
print("  axis=0 would collapse the rows      ->", np.linalg.norm(M, axis=0))

Mn = M / np.linalg.norm(M, axis=1, keepdims=True)
print("\nkeepdims=True makes it (4,1) not (4,), so it divides row-wise:")
print("  without keepdims, shape is", np.linalg.norm(M, axis=1).shape, "-> wrong broadcast")
print("  with    keepdims, shape is", np.linalg.norm(M, axis=1, keepdims=True).shape)
print("\nMn =\n", Mn)
print("lengths now =", np.linalg.norm(Mn, axis=1))

# ---------------------------------------------------------------------------
head(3, "SIMILARITY: the dot product IS cosine, once lengths are 1")

print("Mn[0] . Mn[1] =", Mn[0] @ Mn[1], " (blue vs black jeans -- close)")
print("Mn[0] . Mn[2] =", Mn[0] @ Mn[2], " (jeans vs tee        -- unrelated)")
print("\nThe @ operator is matrix multiply. For two 1-D vectors it is")
print("just multiply-elementwise-then-sum:")
print("  ", Mn[0], "*", Mn[1], "=", Mn[0]*Mn[1], "-> sum =", (Mn[0]*Mn[1]).sum())

print("\nAll pairs at once -- Mn @ Mn.T gives a (4,4) similarity matrix:")
print(Mn @ Mn.T)
print("  diagonal is 1.0: everything matches itself perfectly")

# ---------------------------------------------------------------------------
head(4, "RATINGS -> WEIGHTS")

NOPE, LIKE, LOVE = 1, 2, 3
WEIGHTS = {LOVE: 2.0, LIKE: 1.0, NOPE: -1.0}

ratings = {0: LOVE, 1: LIKE, 2: NOPE}      # love blue jeans, like black, hate tee
rows    = list(ratings.keys())
weights = np.array([WEIGHTS[r] for r in ratings.values()])

print("ratings =", {names[k]: v for k, v in ratings.items()})
print("rows    =", rows,    "  <- which rows of M to pull")
print("weights =", weights, "  <- how hard each one pulls")
print("\nM[rows] selects just those rows (fancy indexing):\n", Mn[rows])

# ---------------------------------------------------------------------------
head(5, "THE TASTE VECTOR: one weighted sum")

taste = weights @ Mn[rows]
print("taste = weights @ Mn[rows] =", taste)
print("\nWhat that actually computed, term by term:")
for w, r in zip(weights, rows):
    print(f"  {w:+.1f} * {Mn[r]}   ({names[r]})")
print("  " + "-"*46)
print(f"   sum = {taste}")
print("\nShapes: (3,) @ (3,3) -> (3,)   [3 weights, 3 items, 3 dims]")

taste = taste / np.linalg.norm(taste)
print("\nnormalized taste =", taste)
print("-> points toward denim, away from tees. Exactly what we rated.")

# ---------------------------------------------------------------------------
head(6, "SCORING: one more matrix multiply")

scores = Mn @ taste
print("scores = Mn @ taste =", scores)
print("\nShapes: (4,3) @ (3,) -> (4,)   one score per item")
for n, s in zip(names, scores):
    print(f"  {s:+.3f}  {n}")

# ---------------------------------------------------------------------------
head(7, "SORTING: argsort returns INDICES, not values")

order = np.argsort(-scores)      # negate because argsort is ascending
print("np.argsort(-scores) =", order, " <- item indices, best first")
print("scores[order]       =", scores[order])
print("\nRanked:")
for rank, i in enumerate(order, 1):
    print(f"  {rank}. {names[i]:12} {scores[i]:+.3f}")

print("\nWe never rated the grey tee, yet it scores negative (-0.283) --")
print("because it sits near the white tee we noped, so the taste vector")
print("points away from it too. That is the recommender generalizing,")
print("and it is the whole point: 3 ratings produced an opinion on item 4.")

# ---------------------------------------------------------------------------
head(8, "EXCLUDING WHAT YOU ALREADY RATED")

unrated = [i for i in range(len(Mn)) if i not in ratings]
print("unrated rows =", unrated, f"({names[unrated[0]]})")
sub = Mn[unrated] @ taste
print("Mn[unrated] @ taste =", sub, "  shape", sub.shape)
print("\nMap back to real ids with the index list -- this is why the real")
print("code keeps `uids`: row 3 of the matrix means uids[3].")
