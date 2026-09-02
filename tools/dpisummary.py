"""496 -- summarise tools/dpiclass.py's rows.

Three questions, kept apart because they have different answers:

  1. PER CHANNEL. Which of the five numbers moves between 300 and 600
     dpi? `A=B` in the corpus TSV is a conjunction over all ten and
     cannot say. Holes is the channel 495's caveat is about.
  2. NEAR A CHANGE. Of the pairs actually measured, how many have a
     hole count that differs between the two resolutions, and by how
     much. A pair whose holes move IS a pair sitting on a boundary --
     no proxy needed.
  3. CLASS. `flag_of` recomputed from the 600 dpi five-tuples against
     the class the 300 dpi ones give. `scale_stable` is the same input
     to both, so the only thing that can move the class is the
     measurement.

The all-zero rows are reported separately throughout. They are
`absent` at both resolutions and cannot change class, so folding them
in would divide the rate by a population that cannot contribute to it.
"""

from __future__ import annotations

import collections
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from findings import flag_of

KEYS = ("components", "holes", "stacked", "centred", "offset")


def load(path):
    out = []
    for i, l in enumerate(pathlib.Path(path).read_text().splitlines()):
        if i == 0:
            continue
        c = l.split("\t")
        if len(c) < 23:
            continue
        n = [int(x) for x in c[3:23]]
        out.append((c[0], int(c[1]), int(c[2]),
                    tuple(n[0:5]), tuple(n[5:10]),
                    tuple(n[10:15]), tuple(n[15:20])))
    return out


def cls(L, R, stable):
    dis = sum(abs(a - b) for a, b in zip(L, R))
    cd = abs(L[0] - R[0])
    return flag_of(dis, cd, stable, empty=(L[0] == 0 and R[0] == 0)), dis, cd


def main():
    rows = load(sys.argv[1])
    docs = len({r[0] for r in rows})
    zero = [r for r in rows
            if r[3][0] == 0 and r[4][0] == 0 and r[5][0] == 0 and r[6][0] == 0]
    live = [r for r in rows
            if not (r[3][0] == 0 and r[4][0] == 0
                    and r[5][0] == 0 and r[6][0] == 0)]
    print(f"POPULATION  {docs} documents, {len(rows)} compared rows")
    print(f"            {len(zero)} all-zero at both resolutions "
          f"(`absent`; cannot change class)")
    print(f"            {len(live)} rows carry ink -- every rate below "
          f"is over these\n")

    # 1. per channel
    print("1. WHICH CHANNEL MOVES BETWEEN 300 AND 600 dpi")
    print(f"   {'channel':<12} {'left col':>14} {'right col':>14} "
          f"{'either':>14}")
    for i, k in enumerate(KEYS):
        l = sum(1 for r in live if r[3][i] != r[5][i])
        rr = sum(1 for r in live if r[4][i] != r[6][i])
        e = sum(1 for r in live if r[3][i] != r[5][i] or r[4][i] != r[6][i])
        print(f"   {k:<12} {l:6d} {100*l/len(live):6.1f}% "
              f"{rr:6d} {100*rr/len(live):6.1f}% "
              f"{e:6d} {100*e/len(live):6.1f}%")
    aeqb = sum(1 for r in live if (r[3], r[4]) != (r[5], r[6]))
    print(f"   {'ALL TEN':<12} {'':>14} {'':>14} "
          f"{aeqb:6d} {100*aeqb/len(live):6.1f}%   (= A=B says NO)\n")

    # 2. holes specifically
    print("2. HOW FAR THE HOLE COUNT MOVES")
    d = collections.Counter()
    rel = []
    for r in live:
        for a, b in ((r[3], r[5]), (r[4], r[6])):
            d[b[1] - a[1]] += 1
            if a[1]:
                rel.append(abs(b[1] - a[1]) / a[1])
    tot = sum(d.values())
    print(f"   {tot} cell measurements (two columns x {len(live)} rows)")
    print(f"   unchanged            {d[0]:6d}  {100*d[0]/tot:5.1f}%")
    ch = tot - d[0]
    print(f"   changed              {ch:6d}  {100*ch/tot:5.1f}%")
    for delta in sorted(k for k in d if k):
        if abs(delta) <= 3 or d[delta] > tot / 200:
            print(f"     delta {delta:+4d}         {d[delta]:6d}  "
                  f"{100*d[delta]/tot:5.1f}%")
    rel.sort()
    if rel:
        print(f"   relative change, of cells with holes at 300: "
              f"p50 {rel[len(rel)//2]:.3f}  p95 {rel[int(.95*len(rel))]:.3f}")
    print()

    # 3. class
    print("3. DOES THE CLASS CHANGE")
    move = collections.Counter()
    at300 = collections.Counter()
    for r in live:
        stable = (r[3], r[4]) == (r[5], r[6])
        c3, _, _ = cls(r[3], r[4], stable)
        c6, _, _ = cls(r[5], r[6], stable)
        at300[c3] += 1
        move[(c3, c6)] += 1
    same = sum(v for (a, b), v in move.items() if a == b)
    print(f"   class at 300 dpi: "
          + "  ".join(f"{k} {v}" for k, v in at300.most_common()))
    print(f"   SAME class at 600 dpi   {same:6d}  "
          f"{100*same/len(live):5.1f}%")
    print(f"   CHANGED class           {len(live)-same:6d}  "
          f"{100*(len(live)-same)/len(live):5.1f}%")
    print("   transitions (300 -> 600), most common first:")
    for (a, b), v in move.most_common():
        if a != b:
            print(f"     {a:<10} -> {b:<10} {v:6d}  "
                  f"{100*v/len(live):5.1f}%")
    print()

    # per document, so a single document cannot carry the rate
    print("4. BY DOCUMENT (no single document carrying the rate)")
    per = collections.defaultdict(lambda: [0, 0])
    for r in live:
        stable = (r[3], r[4]) == (r[5], r[6])
        c3, _, _ = cls(r[3], r[4], stable)
        c6, _, _ = cls(r[5], r[6], stable)
        per[r[0]][0] += 1
        per[r[0]][1] += (c3 != c6)
    q = sorted((v[1] / v[0], v[1], v[0], k) for k, v in per.items())
    print(f"   {len(q)} documents; class-change rate "
          f"p50 {100*q[len(q)//2][0]:.1f}%  "
          f"min {100*q[0][0]:.1f}%  max {100*q[-1][0]:.1f}%")
    for rt, c, n, k in q[-6:][::-1]:
        print(f"     {100*rt:6.1f}%  {c:4d}/{n:4d}  {k[:50]}")


if __name__ == "__main__":
    main()
