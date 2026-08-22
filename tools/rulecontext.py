"""What each rule on a page DOES, from the ink around it (116).

`ink.rules[]` reports that a rule exists and how wide it is. It does
not say whether the rule is a fraction bar, an overline, an underline
or a table separator -- and those four want different things from a
consumer. They differ only in what sits above and below, which is ink,
so the question is answerable before any symbol is named.

  fraction    ink above AND below   numerator over denominator
  overline    ink above only        a vinculum, or a rule under a heading
  underline   ink below only        a rule over a heading, or a toprule
  separator   neither               a booktabs rule between blocks

The band is the rule's own x-span by one rule-length in y, so the test
scales with the rule instead of with the page -- a 12 pt fraction bar
and a 400 pt booktabs rule get the same treatment.

THE PRESENCE CUT IS MEASURED, NOT CHOSEN. `emit.rule_context`
classifies nothing; this tool prints the coverage distribution first
and applies a cut second, and prints both so the cut can be argued
with.

Usage: python3 tools/rulecontext.py <page.png> [--dpi D] [--reach F]
                                    [--cut C] [--min-length N]
"""
import argparse, pathlib, statistics, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from inkdrill.emit import free_rules, rule_context, _pt_per_px  # noqa
from inkdrill.pngio import read_png, auto_mask                  # noqa
from inkdrill.nest import ink_only                              # noqa

ap = argparse.ArgumentParser(prog="tools/rulecontext.py",
                             description=__doc__.strip().splitlines()[0])
ap.add_argument("page", type=pathlib.Path)
ap.add_argument("--dpi", type=float, default=None)
ap.add_argument("--reach", type=float, default=1.0,
                help="band height, in rule lengths")
ap.add_argument("--cut", type=float, default=None,
                help="ink fraction counting as PRESENT; default is "
                     "measured from this page (see output)")
ap.add_argument("--threshold", type=int, default=200)
A = ap.parse_args()

img = read_png(A.page)
dpi = A.dpi or (img.dpi[0] if img.dpi else None)
if dpi is None:
    raise SystemExit(f"{A.page}: no pHYs and no --dpi; points are "
                     f"undefined and every rule length would be a lie")
mask, _ = auto_mask(img.gray, img.width, img.height, A.threshold)
pt = _pt_per_px((dpi, dpi))
regions = list(ink_only(mask).regions)
rules = free_rules(mask, pt=pt, regions=regions)
print(f"page {A.page.name}  {img.width}x{img.height} px @ {dpi:g} dpi")
print(f"ink regions {len(regions)}   ink.rules[] {len(rules)}")
if not rules:
    raise SystemExit("no free-standing rules on this page -- nothing "
                     "to classify, and that is a fact about the page, "
                     "not an error (P16: it is said, not silent)")

ctx = [(r, rule_context(mask, r, pt=pt, reach=A.reach)) for r in rules]
horiz = [(r, c) for r, c in ctx if not c["vertical"]]
print(f"horizontal {len(horiz)}   vertical {len(ctx) - len(horiz)} "
      f"(no above/below band; excluded)")
if not horiz:
    raise SystemExit("every rule on this page is vertical")

vals = sorted([c["above"] for _, c in horiz] + [c["below"] for _, c in horiz])
print(f"\nCOVERAGE DISTRIBUTION over {len(vals)} bands "
      f"({len(horiz)} rules x above/below), ink fraction of band area")
qs = [0, 5, 10, 25, 50, 75, 90, 95, 100]
print("  " + "  ".join(f"p{q}" for q in qs))
print("  " + "  ".join(
    f"{vals[min(len(vals) - 1, int(q / 100 * (len(vals) - 1)))]:.3f}"
    for q in qs))
zero = sum(1 for v in vals if v == 0.0)
print(f"  exactly zero: {zero} of {len(vals)}")

# The cut, measured: the widest gap between consecutive sorted values
# in the interior is the natural split if there is one. Printed with
# the runners-up so a reader can see whether it is a separation or a
# tie -- a single number would hide the difference.
gaps = sorted(((vals[i + 1] - vals[i], vals[i], vals[i + 1])
               for i in range(len(vals) - 1)), reverse=True)[:3]
print("\n  widest gaps in the sorted coverages (a real cut shows one "
      "gap far larger than the rest):")
for g, lo, hi in gaps:
    print(f"    {g:.4f}   between {lo:.4f} and {hi:.4f}")
cut = A.cut if A.cut is not None else (gaps[0][1] + gaps[0][2]) / 2
print(f"\n  CUT USED {cut:.4f}"
      f"{'  (given)' if A.cut is not None else '  (midpoint of the widest gap)'}")

names = {(True, True): "fraction", (True, False): "overline",
         (False, True): "underline", (False, False): "separator"}
counts = {v: 0 for v in names.values()}
rows = []
for r, c in horiz:
    a, b = c["above"] > cut, c["below"] > cut
    k = names[(a, b)]
    counts[k] += 1
    rows.append((r, c, k))
print("\nDISTRIBUTION")
for k in ("fraction", "overline", "underline", "separator"):
    print(f"  {k:<10} {counts[k]:4d}")

print("\nper rule, sorted down the page")
print("  y0_pt   x0_pt   len_px  above  below  class")
for r, c, k in rows:
    print(f"  {r['y0']:7.1f} {r['x0']:7.1f} {c['length_px']:7d} "
          f"{c['above']:.3f}  {c['below']:.3f}  {k}")
