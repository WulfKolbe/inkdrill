"""fuzzyalign.py -- align the expressions exact matching cannot reach.

out/650 measured the match rate falling from 72.5% at ten characters to
1.5% past 160: a row aligns only if EVERY difference in it is
normalised at once, so the long expressions -- the ones the whitespace
defect is said to live in -- are almost all unaligned.

Exact matching cannot be fixed by more rules; out/650 tried and the
marginal return collapses. This aligns on SIMILARITY instead:
`difflib.SequenceMatcher` over the fully normalised strings, with a
character-4-gram index to keep it from being quadratic.

WHITESPACE IS STRIPPED FOR THE MATCH AND MEASURED ON THE RAW FORMS.
That is the whole design. If whitespace took part in the alignment,
the rows with unusual whitespace would fail to align and the
measurement would be taken on exactly the rows that do not have the
defect.

THE THRESHOLD IS THE MEASUREMENT'S WEAKEST POINT, so it is checked
rather than chosen: `--selfcheck` runs the fuzzy matcher on rows that
ALREADY align exactly and reports how often it recovers the same
partner. A matcher that cannot reproduce a known answer has no
business proposing new ones.
"""
from __future__ import annotations

import argparse
import collections
import difflib
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.alignlatex import author_math, expand_macros, norm   # noqa: E402
from tools.authordiff import author_tex                          # noqa: E402
from tools.formulafind import rows                               # noqa: E402

#: spaces BETWEEN two ordinary atoms -- `x y` for `xy`. TeX ignores
#: them, so they are invisible on the page (out/656) and they are the
#: class being counted.
TOKEN_GAP = re.compile(r"(?<=[A-Za-z0-9\)\]\}])\s+(?=[A-Za-z0-9\(\[\\])")
#: spacing that RENDERS.
EXPLICIT = re.compile(r"\\quad\b|\\qquad\b|\\,|\;|\\!|\\:|\\ (?![a-zA-Z])|~")


def grams(s, n=4):
    return {s[i:i + n] for i in range(max(0, len(s) - n + 1))}


class Index:
    """Author expressions, retrievable by shared character 4-grams."""

    def __init__(self, exprs):
        self.raw, self.key, self.post = [], [], collections.defaultdict(list)
        for x in exprs:
            k = norm(x)
            if len(k) < 6:
                continue
            i = len(self.raw)
            self.raw.append(x); self.key.append(k)
            for g in grams(k):
                self.post[g].append(i)

    def best(self, q, cap=40):
        """(ratio, raw author expression) for the closest entry."""
        k = norm(q)
        if len(k) < 6:
            return 0.0, None
        c = collections.Counter()
        for g in grams(k):
            for i in self.post.get(g, ()):
                c[i] += 1
        best = (0.0, None)
        for i, _ in c.most_common(cap):
            r = difflib.SequenceMatcher(None, k, self.key[i]).ratio()
            if r > best[0]:
                best = (r, self.raw[i])
        return best


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--library", type=pathlib.Path,
                    default=pathlib.Path.home() / "pdfdrill-library")
    ap.add_argument("--ratio", type=float, default=0.90)
    ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()
    docs = sorted(d for d in a.library.iterdir() if d.is_dir()
                  and list(d.glob("*.tgz"))
                  and (d / "evidence-formula.tex").exists())

    if a.selfcheck:
        print("SELF-CHECK -- can the fuzzy matcher recover the EXACT answer?\n")
        print(f"{'document':<14} {'exact pairs':>12} {'recovered':>10} {'rate':>7}")
        tot = rec = 0
        for d in docs:
            src, _ = expand_macros(author_tex(list(d.glob("*.tgz"))[0]))
            ex = author_math(src)
            idx = Index(ex)
            byn = {}
            for x in ex:
                byn.setdefault(norm(x), x)
            n = k = 0
            for r in rows(d / "evidence-formula.tex"):
                q = norm(r["math"])
                if q not in byn or len(q) < 6:
                    continue
                n += 1
                ratio, hit = idx.best(r["math"])
                if hit is not None and norm(hit) == q:
                    k += 1
            tot += n; rec += k
            if n:
                print(f"{d.name:<14} {n:>12} {k:>10} {100*k/n:>6.1f}%")
        print(f"\n{'TOTAL':<14} {tot:>12} {rec:>10} {100*rec/max(1,tot):>6.1f}%")
        return 0

    B = [(0, 24), (25, 49), (50, 99), (100, 199), (200, 10**6)]
    agg = {b: collections.Counter() for b in B}
    print(f"aligning at ratio >= {a.ratio}\n")
    for d in docs:
        src, _ = expand_macros(author_tex(list(d.glob("*.tgz"))[0]))
        ex = author_math(src)
        idx = Index(ex)
        for r in rows(d / "evidence-formula.tex"):
            q = r["math"]
            L = len(re.sub(r"\s+", "", q))
            b = next(x for x in B if x[0] <= L <= x[1])
            agg[b]["rows"] += 1
            ratio, hit = idx.best(q)
            if hit is None or ratio < a.ratio:
                continue
            au = " ".join(hit.split())
            agg[b]["aligned"] += 1
            mt, at = len(TOKEN_GAP.findall(q)), len(TOKEN_GAP.findall(au))
            me, ae = len(EXPLICIT.findall(q)), len(EXPLICIT.findall(au))
            agg[b]["m_tok"] += mt; agg[b]["a_tok"] += at
            agg[b]["m_exp"] += me; agg[b]["a_exp"] += ae
            agg[b]["more"] += mt > at
            agg[b]["less"] += mt < at
            agg[b]["exp_diff"] += me != ae
    print(f"{'length':>10} {'rows':>6} {'aligned':>8} {'rate':>7}   "
          f"{'tok MP':>7} {'tok AU':>7} {'ratio':>6}  {'more':>6} {'less':>6} "
          f"{'expl':>5}")
    for b in B:
        v = agg[b]
        if not v["aligned"]:
            continue
        lab = f"{b[0]}-{b[1]}" if b[1] < 10**5 else f"{b[0]}+"
        print(f"{lab:>10} {v['rows']:>6} {v['aligned']:>8} "
              f"{100*v['aligned']/v['rows']:>6.1f}%   {v['m_tok']:>7} "
              f"{v['a_tok']:>7} {v['m_tok']/max(1,v['a_tok']):>5.2f}x  "
              f"{100*v['more']/v['aligned']:>5.1f}% "
              f"{100*v['less']/v['aligned']:>5.1f}% "
              f"{100*v['exp_diff']/v['aligned']:>4.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
