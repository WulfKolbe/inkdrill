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
    python3 tools/mathshape.py --original crop.jpg --candidate out.pdf

Fraction count = stacked - centred - offset. The two discriminators are
one-bit questions the ink answers directly: Fraction vs Stack is a
rule's existence, Limits vs SupSub is horizontal centring.

COMPARE MODE. An original crop against a candidate PDF (a pix2tex or
hand-written reconstruction): the candidate is rendered by ghostscript
and both sides are reduced to (components, holes, stacked, centred,
offset). The per-feature difference is the report -- zero everywhere
says the candidate has the original's STRUCTURE, which is exactly what
a wrong-but-plausible transcription (stacked scripts on an ordinary
symbol where the ink says limits) fails.

SCALE INVARIANCE IS ASSERTED, NOT ASSUMED -- at THREE resolutions,
and the third is measured necessity, not caution. On the first test
candidate the stacked count flapped 6,5,6,6,5,6 across 200-800 dpi,
and the original two-point assertion sampled 300 and 600: the two
agreeing outliers. It passed on a vector that is not invariant, which
is the exact failure the assertion exists to catch. Three points with
the flap between them fire; a candidate that fails is reported per
resolution, because a comparison that moves with a rendering choice is
not a comparison.
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


def features(mask) -> dict:
    """One definition lives in the package now: `mathstruct.pair_stats`."""
    from inkdrill.mathstruct import pair_stats
    return pair_stats(mask)


def measure(p: pathlib.Path, threshold: int):
    m = load_mask(p, dpi=72, threshold=threshold)
    f = features(m)
    regs = ink_only(m).regions
    rules = [r for r in regs if is_rule(r) and (r.x1 - r.x0) >= (r.y1 - r.y0)]
    comps = [r for r in regs if r.id not in {x.id for x in rules}]
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
    return (f["components"], len(rules), f["stacked"], f["centred"],
            f["offset"], leader)


def _any_image_mask(path: pathlib.Path, threshold: int):
    """Any raster `magick` can read, as a mask. PGM goes straight in."""
    import subprocess
    if path.suffix.lower() in (".pgm", ".pnm"):
        return load_mask(path, dpi=72, threshold=threshold)
    r = subprocess.run(["magick", str(path), "-colorspace", "gray",
                        "-depth", "8", "pgm:-"], capture_output=True)
    if r.returncode:
        sys.exit(f"magick cannot read {path}")
    return load_mask(r.stdout, dpi=72, threshold=threshold)


def _render_pdf_mask(pdf: pathlib.Path, dpi: int, threshold: int):
    import subprocess
    r = subprocess.run(
        ["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=pgmraw",
         f"-r{dpi}", "-dFirstPage=1", "-dLastPage=1",
         "-sOutputFile=%stdout", str(pdf)], capture_output=True)
    if r.returncode or not r.stdout.startswith(b"P5"):
        sys.exit(f"ghostscript cannot render {pdf}")
    return load_mask(r.stdout, dpi=dpi, threshold=threshold)


def compare(original: pathlib.Path, candidate: pathlib.Path,
            threshold: int) -> int:
    """Original crop vs rendered candidate, per feature."""
    fo = features(_any_image_mask(original, threshold))
    # Identical at three resolutions, or the comparison would depend on
    # a rendering choice. Three because two agreed by luck on a vector
    # that flaps -- see the module docstring.
    per = {d: features(_render_pdf_mask(candidate, d, threshold))
           for d in (300, 400, 600)}
    if len({tuple(sorted(f.items())) for f in per.values()}) != 1:
        print("SCALE-INVARIANCE FAILED: candidate features move with dpi")
        for d, f in per.items():
            print(f"  {d} dpi: {f}")
        return 1
    f_hi = per[600]
    print(f"{'feature':<12} {'original':>9} {'candidate':>10} {'diff':>6}")
    for k in fo:
        print(f"{k:<12} {fo[k]:>9} {f_hi[k]:>10} {f_hi[k] - fo[k]:>+6}")
    print("(candidate identical at 300, 400 and 600 dpi)")
    return 0 if fo == f_hi else 2


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("directory", type=pathlib.Path, nargs="?")
    ap.add_argument("--original", type=pathlib.Path)
    ap.add_argument("--candidate", type=pathlib.Path)
    ap.add_argument("--threshold", type=int, default=200)
    args = ap.parse_args(argv)
    if args.original or args.candidate:
        if not (args.original and args.candidate):
            ap.error("--original and --candidate go together")
        return compare(args.original, args.candidate, args.threshold)
    if args.directory is None:
        ap.error("a directory, or --original with --candidate")
    print(f"{'name':<38} {'comps':>5} {'rules':>5} {'stacked':>7} "
          f"{'centred':>7} {'offset':>6}  flag")
    for p in sorted(args.directory.glob("*.pgm")):
        n, r, st, c, o, lead = measure(p, args.threshold)
        print(f"{p.stem:<38} {n:>5} {r:>5} {st:>7} {c:>7} {o:>6}"
              f"  {'TOC-LEADER' if lead else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
