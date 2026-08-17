"""facebench.py -- do the channels identify the FACE, not the character?

    python3 tools/facebench.py [--sizes 60,90,120]

PROTOCOL, because the split rule is the experiment (the U13 lesson):
20 known Type 1 faces x the lowercase alphabet x three sizes. Per
(face, size), one ALPHABET-POOLED feature vector -- pooling is what
averages character identity out. Classification is 1-NN with
LEAVE-ONE-SIZE-OUT: every sample is classified against samples of the
OTHER sizes only, so a correct answer means the vector carried the
face across a rendering change, not that it memorised a raster.

FEATURES, all size-normalised or size-free by construction:
  stem      row-axis stroke_mode / median glyph height
  contrast  col_mode / row_mode              (T17-T19)
  termini   mean (top, bottom, left, right) per glyph  (T1/T2)
  slant     median |Moments.shear|           (T8)
Dimensions are z-scored over the population before the distance.

The report is the CONFUSION MATRIX over faces -- who is mistaken for
whom is the finding; a single accuracy would throw it away.
"""
from __future__ import annotations

import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from inkdrill.aggregate import moments_of_mask          # noqa: E402
from inkdrill.charstring import outline                 # noqa: E402
from inkdrill.raster import iter_runs                   # noqa: E402
from inkdrill.scan import render                        # noqa: E402
from inkdrill.sweep import Capture, sweep, termini      # noqa: E402
from inkdrill.type1 import load                         # noqa: E402

T1 = pathlib.Path("/usr/share/texmf-dist/fonts/type1")
FACES = [  # (label, filename)
    ("Termes", "qtmr.pfb"), ("Termes-B", "qtmb.pfb"),
    ("Termes-I", "qtmri.pfb"), ("Pagella", "qplr.pfb"),
    ("Pagella-B", "qplb.pfb"), ("Schola", "qcsr.pfb"),
    ("Bonum", "qbkr.pfb"), ("Heros", "qhvr.pfb"),
    ("Heros-B", "qhvb.pfb"), ("Heros-I", "qhvri.pfb"),
    ("Adventor", "qagr.pfb"), ("Adventor-B", "qagb.pfb"),
    ("Cursor", "qcrr.pfb"), ("Cursor-B", "qcrb.pfb"),
    ("Chorus", "qzcmi.pfb"),
    ("cmr10", "cmr10.pfb"), ("cmbx10", "cmbx10.pfb"),
    ("cmti10", "cmti10.pfb"), ("cmss10", "cmss10.pfb"),
    ("cmtt10", "cmtt10.pfb"),
]
CH = "abcdefghijklmnopqrstuvwxyz"


def features(font, px):
    import collections
    cnt = {"row": collections.Counter(), "col": collections.Counter()}
    heights, shears = [], []
    tsum = [0, 0, 0, 0]
    n = 0
    for ch in CH:
        if ch not in font.charstrings:
            continue
        m, _ = render(outline(font, ch), font.units_per_em, px)
        if not m.ink_count:
            continue
        n += 1
        heights.append(m.height)
        shears.append(abs(moments_of_mask(m).shear))
        for axis in ("row", "col"):
            for r in iter_runs(m, axis):
                cnt[axis][r.hi - r.lo + 1] += 1
        row = sweep(m, axis="row", conn=8, capture=Capture.GRAPH)
        col = sweep(m, axis="col", conn=8, capture=Capture.GRAPH)
        for i, v in enumerate(termini(row) + termini(col)):
            tsum[i] += v
    rm = min(cnt["row"], key=lambda k: (-cnt["row"][k], k))
    cm = min(cnt["col"], key=lambda k: (-cnt["col"][k], k))
    med_h = statistics.median(heights)
    return [rm / med_h, cm / rm] + [t / n for t in tsum] + \
           [statistics.median(shears)]


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    sizes = [60.0, 90.0, 120.0]
    for a in argv:
        if a.startswith("--sizes"):
            sizes = [float(x) for x in a.split("=", 1)[1].split(",")]
    samples = []          # (face_idx, size, vector)
    for fi, (label, fname) in enumerate(FACES):
        src = next(T1.rglob(fname), None)
        if src is None:
            print(f"MISSING {fname}; substitute or drop", file=sys.stderr)
            return 1
        font = load(src)
        for px in sizes:
            samples.append((fi, px, features(font, px)))
    dims = len(samples[0][2])
    mean = [statistics.mean(s[2][d] for s in samples) for d in range(dims)]
    sd = [statistics.pstdev(s[2][d] for s in samples) or 1.0
          for d in range(dims)]

    def dist(a, b):
        return sum(((a[d] - b[d]) / sd[d]) ** 2 for d in range(dims))

    conf = {}
    right = 0
    for fi, px, v in samples:
        best = min((s for s in samples if s[1] != px),
                   key=lambda s: dist(v, s[2]))
        conf.setdefault(fi, []).append(best[0])
        right += best[0] == fi
    n = len(samples)
    print(f"{len(FACES)} faces x {len(sizes)} sizes = {n} samples, "
          f"leave-one-size-out 1-NN over {dims} z-scored dims")
    print(f"FACE ACCURACY: {right}/{n} = {right / n:.1%}  "
          f"(chance {1 / len(FACES):.1%})\n")
    print(f"{'face':<12} {'correct':>7}  errors -> predicted as")
    for fi, (label, _) in enumerate(FACES):
        preds = conf[fi]
        ok = sum(1 for p in preds if p == fi)
        errs = [FACES[p][0] for p in preds if p != fi]
        print(f"{label:<12} {ok}/{len(preds):<5}  "
              + (", ".join(errs) if errs else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
