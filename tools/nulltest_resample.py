"""nulltest_resample.py -- does the MathPix-size resample move the five-tuple?

NULL TEST. No fix, no threshold tuning, no repair of anything it finds.
One question: take a crop we rendered OURSELVES, apply ONLY the
downsample-to-MathPix-size plus JPEG q92, and measure whether the
structural five-tuple moves.

    (components, holes, stacked, centred, offset)   mathstruct.pair_stats

WHY IT MATTERS. Every published table / image / host-line residual
compares a locally rendered crop against a MathPix one. Those two
differ in at least two ways at once -- the content may genuinely
disagree, AND one of them has been through a resample. If the resample
alone moves the five-tuple SYSTEMATICALLY, it is inside every one of
those residuals as a constant confound. If it moves it in a scattered
way, it is noise and not a confound. The distribution is the answer;
a pass/fail would throw it away.

THE RESAMPLE RATIO IS MEASURED, NOT CHOSEN. 0902.0431 is 612 x 792 pt
and MathPix rasterises it to 2125 x 2750, which is 250.00 dpi on both
axes. Rendering locally at 400 dpi therefore makes the downsample
exactly 250/400 = 0.625.

BOTH SIDES USE THE SAME THRESHOLD (200). Changing it between the two
would be a fix, and this is a null test.

    python3 tools/nulltest_resample.py --n 20
"""
from __future__ import annotations

import argparse
import pathlib
import random
import statistics
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from inkdrill.mathstruct import pair_stats                 # noqa: E402
from inkdrill.pnmio import load_mask                       # noqa: E402
from tools.formulafind import STANDALONE, rows             # noqa: E402

KEYS = ("components", "holes", "stacked", "centred", "offset")


def render(math, out, dpi):
    with tempfile.TemporaryDirectory() as td:
        t = pathlib.Path(td)
        (t / "f.tex").write_text(STANDALONE % math, encoding="utf-8")
        subprocess.run(["pdflatex", "-interaction=nonstopmode",
                        "-halt-on-error", "f.tex"],
                       cwd=t, capture_output=True, text=True)
        if not (t / "f.pdf").exists():
            return False
        subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=pgmraw",
                        f"-r{dpi}", f"-sOutputFile={out}", str(t / "f.pdf")],
                       capture_output=True, check=True)
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--library", type=pathlib.Path,
                    default=pathlib.Path.home() / "pdfdrill-library")
    ap.add_argument("--bibkey", default="0902.0431")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=20260910)
    ap.add_argument("--dpi", type=int, default=400)
    ap.add_argument("--target-dpi", type=float, default=250.0)
    ap.add_argument("--quality", type=int, default=92)
    ap.add_argument("--threshold", type=int, default=200)
    args = ap.parse_args()

    pct = 100.0 * args.target_dpi / args.dpi
    tex = args.library / args.bibkey / "evidence-formula.tex"
    all_rows = list(rows(tex))
    # SEEDED RANDOM, not the first N. The table is ordered by page and
    # its opening rows are single symbols -- `G`, `\sigma`, `w` -- which
    # have one component and almost nothing for a resample to change.
    # Taking the head would have made a null result nearly certain
    # before the instrument ran.
    pick = random.Random(args.seed).sample(all_rows, min(args.n, len(all_rows)))

    print(f"{len(pick)} locally-rendered crops, seed {args.seed}, "
          f"from {len(all_rows)} rows of {args.bibkey}")
    print(f"native {args.dpi} dpi  ->  LANCZOS {pct:.4g}%  ->  JPEG q"
          f"{args.quality}  ->  {args.target_dpi:g} dpi (MathPix size)")
    print(f"threshold {args.threshold} on BOTH sides\n")
    print(f"{'id':<8} {'px native':>12} {'px resampled':>14}  "
          + " ".join(f"{k[:4]:>10}" for k in KEYS))

    deltas, kept = [], []
    with tempfile.TemporaryDirectory() as td:
        t = pathlib.Path(td)
        for row in pick:
            if not render(row["math"], t / "a.pgm", args.dpi):
                print(f"{row['id'].split('_')[-1]:<8} RENDER FAILED")
                continue
            subprocess.run(["magick", str(t / "a.pgm"), "-filter", "Lanczos",
                            "-resize", f"{pct}%", "-quality", str(args.quality),
                            str(t / "b.jpg")], capture_output=True, check=True)
            subprocess.run(["magick", str(t / "b.jpg"), "-colorspace", "Gray",
                            "-depth", "8", str(t / "b.pgm")],
                           capture_output=True, check=True)
            ma = load_mask(str(t / "a.pgm"), dpi=float(args.dpi),
                           threshold=args.threshold)
            mb = load_mask(str(t / "b.pgm"), dpi=args.target_dpi,
                           threshold=args.threshold)
            sa, sb = pair_stats(ma), pair_stats(mb)
            d = {k: sb[k] - sa[k] for k in KEYS}
            deltas.append(d)
            kept.append((row, sa, sb))
            print(f"{row['id'].split('_')[-1]:<8} "
                  f"{f'{ma.width}x{ma.height}':>12} "
                  f"{f'{mb.width}x{mb.height}':>14}  "
                  + " ".join(f"{sa[k]:>4}{d[k]:>+3d}" for k in KEYS))

    if not deltas:
        return 1
    print()
    print("PER-KEY DELTA DISTRIBUTION (resampled minus native)")
    print(f"  {'key':<12} {'zero':>5} {'neg':>5} {'pos':>5} "
          f"{'min':>5} {'max':>5} {'mean':>8} {'median':>7}")
    for k in KEYS:
        v = [d[k] for d in deltas]
        print(f"  {k:<12} {sum(1 for x in v if x == 0):>5} "
              f"{sum(1 for x in v if x < 0):>5} {sum(1 for x in v if x > 0):>5} "
              f"{min(v):>5} {max(v):>5} {statistics.mean(v):>8.3f} "
              f"{statistics.median(v):>7.1f}")
    print()
    comp = [d["components"] for d in deltas]
    import collections
    print(f"COMPONENT DELTA HISTOGRAM  "
          f"{dict(sorted(collections.Counter(comp).items()))}")
    print(f"  n={len(comp)}  zero={comp.count(0)}  "
          f"nonzero={len(comp)-comp.count(0)}  "
          f"mean={statistics.mean(comp):+.3f}  "
          f"sd={statistics.pstdev(comp):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
