"""lengthfloor.py -- a score floor that knows how long the expression is.

out/651 measured the red-flag rate rising from 1% to 42% with
expression length, and identical for rows whose LaTeX matches the
author's and rows MathPix rewrote. A single floor on a
length-dependent score is therefore wrong at both ends: too low for
short rows, too high for long ones.

THE CALIBRATION POPULATION IS THE POINT. The floor is fitted on rows
whose LaTeX is CHARACTER-IDENTICAL to the author's arXiv source, so
the only difference left between our render and the page is the
RENDERING. Their score-versus-length curve is the divergence with
nothing else in it, and a row is flagged when it fits worse than 90%
of verifiably-correct rows of its own length.

That population only exists because the author's e-print is available.
It is a better calibration set than "rows that happen to agree", and
it is the first thing in this chain that could not have been built
from MathPix's output alone.

    python3 tools/lengthfloor.py --resid <residual json> --bibkey <key>
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.alignlatex import author_math, expand_macros, norm   # noqa: E402
from tools.authordiff import author_tex                         # noqa: E402
from tools.formulafind import rows                              # noqa: E402

BUCKETS = [(0, 14), (15, 24), (25, 34), (35, 49), (50, 69), (70, 99)]


def length_of(r):
    return max(1, len(re.sub(r"\s+", "", r["math"])))


def fit(matched, buckets=BUCKETS, q=0.10, min_n=15):
    """floor(L) = a + b*log10(L), least squares on the q-quantile."""
    pts = []
    for lo, hi in buckets:
        g = sorted(r["score"] for r in matched if lo <= length_of(r) <= hi)
        if len(g) >= min_n:
            pts.append((math.log10((lo + hi) / 2), g[int(q * len(g))], len(g)))
    if len(pts) < 3:
        return None
    n = len(pts)
    sx = sum(p[0] for p in pts); sy = sum(p[1] for p in pts)
    sxx = sum(p[0] ** 2 for p in pts); sxy = sum(p[0] * p[1] for p in pts)
    b = (n * sxy - sx * sy) / (n * sxx - sx * sx)
    return (sy - b * sx) / n, b, pts


def floor_at(a, b, x, lo=0.55, hi=0.96):
    return max(lo, min(hi, a + b * math.log10(max(1, x))))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resid", type=pathlib.Path, required=True)
    ap.add_argument("--library", type=pathlib.Path,
                    default=pathlib.Path.home() / "pdfdrill-library")
    ap.add_argument("--bibkey", default="0902.0431")
    ap.add_argument("--single", type=float, default=0.7896,
                    help="the floor now in use, for comparison")
    a = ap.parse_args()

    doc = a.library / a.bibkey
    src, _ = expand_macros(author_tex(list(doc.glob("*.tgz"))[0]))
    idx = {norm(x) for x in author_math(src)}
    matched_ids = {r["id"] for r in rows(doc / "evidence-formula.tex")
                   if norm(r["math"]) in idx}
    img = json.loads(a.resid.read_text())
    placed = [r for r in img if r["gaps"] >= 2 and r["margin"] >= 0.10]
    matched = [r for r in placed if r["id"] in matched_ids]
    print(f"{len(placed)} placed rows, {len(matched)} of them "
          f"character-identical to the author's source")

    got = fit(matched)
    if got is None:
        print("too few matched rows per bucket to fit")
        return 1
    A, B, pts = got
    print(f"\nfloor(L) = {A:.4f} {B:+.4f}*log10(L)")
    for lx, y, n in pts:
        print(f"   L~{10**lx:>5.0f}  p10 {y:.3f}  (n={n})")
    print(f"\n{'L':>6} {'per-length':>11} {'single':>8}")
    for x in (5, 10, 20, 40, 80, 160, 274):
        mark = "  extrapolated" if x > 99 else ""
        print(f"{x:>6} {floor_at(A, B, x):>11.3f} {a.single:>8.3f}{mark}")

    for label, fn in (("single", lambda r: r["score"] < a.single),
                      ("per-length",
                       lambda r: r["score"] < floor_at(A, B, length_of(r)))):
        d = {}
        for r in placed:
            if fn(r):
                d[min(length_of(r) // 25 * 25, 150)] = \
                    d.get(min(length_of(r) // 25 * 25, 150), 0) + 1
        print(f"\nflagged by length, {label:<10} "
              f"{sum(d.values()):>4} rows  {dict(sorted(d.items()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
