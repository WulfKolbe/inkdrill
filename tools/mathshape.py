"""mathshape.py -- structure, not symbols, over a directory of crops.

Per image, from geometry alone (no classifier, no identity, no gold):

    name  components  rules  stacked_groups  centred  offset

rules          `is_rule` and horizontal
stacked group  two non-rule components, x-overlap >= 0.5 of the
               narrower, one above the other, no third component
               between them
with a RULE between -> Fraction (in `stacked`, in neither split)
without        centred (x-centres within 15% of the wider) -> Limits
               else -> SupSub
TOC-LEADER     >= 20 near-identical small blobs evenly spaced on one
               row

    python3 tools/mathshape.py <dir-of-pgm> [--threshold 200]

Fraction count = stacked - centred - offset. The two discriminators are
one-bit questions the ink answers directly: Fraction vs Stack is a
rule's existence, Limits vs SupSub is horizontal centring.
"""
from __future__ import annotations

import argparse
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from inkdrill.emit import is_rule          # noqa: E402
from inkdrill.nest import ink_only         # noqa: E402
from inkdrill.pnmio import load_mask       # noqa: E402


def measure(p: pathlib.Path, threshold: int):
    m = load_mask(p, dpi=72, threshold=threshold)
    regs = ink_only(m).regions
    rules = [r for r in regs if is_rule(r) and (r.x1 - r.x0) >= (r.y1 - r.y0)]
    rids = {r.id for r in rules}
    comps = [r for r in regs if r.id not in rids]
    stacked = centred = offset = 0
    for i, a in enumerate(comps):
        for b in comps[i + 1:]:
            top, bot = ((a, b) if a.y1 < b.y0 else
                        ((b, a) if b.y1 < a.y0 else (None, None)))
            if top is None:
                continue
            ov = min(top.x1, bot.x1) - max(top.x0, bot.x0) + 1
            wa, wb = top.x1 - top.x0 + 1, bot.x1 - bot.x0 + 1
            if ov < 0.5 * min(wa, wb):
                continue
            bx0, bx1 = min(top.x0, bot.x0), max(top.x1, bot.x1)
            if any(c is not top and c is not bot and c.y0 > top.y1
                   and c.y1 < bot.y0 and c.x1 >= bx0 and c.x0 <= bx1
                   for c in comps):
                continue
            stacked += 1
            if any(r.y0 > top.y1 and r.y1 < bot.y0
                   and r.x1 >= bx0 and r.x0 <= bx1 for r in rules):
                continue                              # Fraction
            ca = (top.x0 + top.x1) / 2
            cb = (bot.x0 + bot.x1) / 2
            if abs(ca - cb) <= 0.15 * max(wa, wb):
                centred += 1
            else:
                offset += 1
    leader = False
    if len(comps) >= 20:
        mw = statistics.median(r.x1 - r.x0 + 1 for r in comps)
        mh = statistics.median(r.y1 - r.y0 + 1 for r in comps)
        dots = [r for r in comps
                if abs((r.x1 - r.x0 + 1) - mw) <= 0.5 * mw
                and abs((r.y1 - r.y0 + 1) - mh) <= 0.5 * mh]
        if len(dots) >= 20:
            cys = [(r.y0 + r.y1) / 2 for r in dots]
            row = [r for r, cy in zip(dots, cys)
                   if abs(cy - statistics.median(cys)) <= mh]
            if len(row) >= 20:
                xs = sorted((r.x0 + r.x1) / 2 for r in row)
                gaps = [b - a for a, b in zip(xs, xs[1:])]
                mg = statistics.median(gaps)
                if mg > 0 and sum(1 for g in gaps
                                  if abs(g - mg) <= 0.5 * mg) >= 0.8 * len(gaps):
                    leader = True
    return len(regs), len(rules), stacked, centred, offset, leader


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("directory", type=pathlib.Path)
    ap.add_argument("--threshold", type=int, default=200)
    args = ap.parse_args(argv)
    print(f"{'name':<38} {'comps':>5} {'rules':>5} {'stacked':>7} "
          f"{'centred':>7} {'offset':>6}  flag")
    for p in sorted(args.directory.glob("*.pgm")):
        n, r, st, c, o, lead = measure(p, args.threshold)
        print(f"{p.stem:<38} {n:>5} {r:>5} {st:>7} {c:>7} {o:>6}"
              f"  {'TOC-LEADER' if lead else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
