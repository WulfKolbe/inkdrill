"""midtest.py -- does `\\mid`'s relation spacing explain the misfits?

THE HYPOTHESIS, from out/645. `\\mid` is a \\mathrel, so TeX puts a
thickmuskip (5mu, 0.2778em) on EACH side of it. If the page sets an
ordinary bar with no such space, every glyph after the bar sits about
0.55em further right in our render than in the ink -- a displacement
INSIDE the expression, which is exactly "placed uniquely, shape
disagrees". Set-builder rows were 3.7x enriched among the red rows.

TWO PREDICTIONS, AND BOTH ARE CHECKED HERE:

  P1  Re-rendering with a TIGHT bar (`|`, a \\mathord, no relation
      space) should FIT BETTER. If the score does not move, the
      spacing is not the cause.
  P2  The residual should sit to ONE SIDE of the bar -- little
      disagreement before it, more after it.

P1 is the decisive one. P2 is what makes the mechanism legible if P1
holds, and evidence against a shift if it does not.

The 7 placed rows that contain `\\mid` and are NOT flagged are run as a
CONTROL. A cause that also "improves" rows which already fit is not a
cause, it is a fitting artefact.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.formulafind import (blobs, fullres_crop, line_index,  # noqa: E402
                               locate_refit, match_rows_to_lines, profile,
                               render, resample, rows, trimmed)

LIB = pathlib.Path.home() / "pdfdrill-library"
BIB = "0902.0431"
DOC_SCALE, DPI, CROP_DPI = 0.665, 600, 400.0
RED = ("EDGE_CUT", "BLOB_COUNT", "POOR_FIT", "OVERLAP", "ORDER")
GREY = ("UNPLACEABLE", "AMBIGUOUS")

#: `thin` is not a guess. The author's own arXiv source -- `SpEcxp.tex`
#: inside `0902.0431.tgz`, dated February 2009 -- writes `\, | \,` 329
#: times and `\mid` NOT ONCE. So the true spacing is 3mu each side
#: against MathPix's 5mu, and the first version of this test bracketed
#: that value without containing it: `bar` removes ALL space where the
#: author used thin ones.
VARIANTS = {
    "mid": r"\mid",       # as MathPix emits it: \mathrel, 5mu each side
    "thin": r"\, | \,",   # THE AUTHOR'S OWN FORM: \mathord, 3mu each side
    "bar": r"|",          # \mathord, no space at all -- tighter than either
    "wide": r"\;|\;",     # 5mu each side, to check the DIRECTION
}


def bar_column(fb, fw):
    """x of the vertical bar inside the rendered template, or None.

    The bar is the tallest thin stroke: height at least 60% of the
    template's ink height, and at least four times as tall as wide.
    Returns None when no blob qualifies or several do, because a
    guessed bar would put the split in the wrong place and the left /
    right test would be meaningless.
    """
    if not fb:
        return None
    top = min(b[2] for b in fb)
    bot = max(b[3] for b in fb)
    h = bot - top + 1
    cand = [b for b in fb
            if (b[3] - b[2] + 1) >= 0.6 * h
            and (b[3] - b[2] + 1) >= 4 * (b[1] - b[0] + 1)]
    return None if len(cand) != 1 else (cand[0][0] + cand[0][1]) / 2


def residual_split(fp, cp, x0, n, bar_frac):
    """Disagreeing columns before and after the bar, as fractions."""
    q = resample(fp, n)
    split = int(round(bar_frac * n))
    pre = post = pre_n = post_n = 0
    for i, v in enumerate(q):
        w = cp[x0 + i] if 0 <= x0 + i < len(cp) else 0
        bad = 1 if (v != w) else 0
        if i < split:
            pre += bad; pre_n += 1
        else:
            post += bad; post_n += 1
    return (pre / pre_n if pre_n else 0.0), (post / post_n if post_n else 0.0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resid", type=pathlib.Path, required=True)
    ap.add_argument("--band", type=float, default=0.12)
    ap.add_argument("--step", type=float, default=0.002)
    args = ap.parse_args()

    data = json.load(open(args.resid))
    mid = [r for r in data if r"\mid" in r["math"]
           and not (set(r["flags"]) & set(GREY))]
    mid.sort(key=lambda r: r["id"])
    index, raster_w, _ = line_index(LIB, BIB)
    pw = int(subprocess.run(["magick", "identify", "-format", "%w",
                             str(LIB/BIB/"inspect/pages/p1.png")],
                            capture_output=True, text=True).stdout)
    ratio = pw / raster_w
    allrows = {r["id"]: r for r in rows(LIB/BIB/"evidence-formula.tex")}
    regs = match_rows_to_lines([allrows[r["id"]] for r in mid], index)

    print(f"{len(mid)} placed rows contain \\mid  "
          f"({sum(1 for r in mid if set(r['flags']) & set(RED))} red, "
          f"{sum(1 for r in mid if not set(r['flags']) & set(RED))} control)\n")
    print(f"{'id':<8} {'grp':<8} " + " ".join(f"{v:>7}" for v in VARIANTS)
          + f" {'best':>6} {'gain':>7}   {'resid pre/post':>16}")

    out = []
    with tempfile.TemporaryDirectory() as td:
        t = pathlib.Path(td)
        for r in mid:
            grp = "RED" if set(r["flags"]) & set(RED) else "control"
            fullres_crop(LIB, BIB, int(r["page"]), regs[r["id"]], ratio,
                         t/"c.pgm")
            cm, cb = blobs(t/"c.pgm", CROP_DPI)
            sc, pre, post = {}, None, None
            for name, tok in VARIANTS.items():
                math = r["math"].replace(r"\mid", tok)
                if not render(math, t/"f.pgm", DPI):
                    sc[name] = float("nan"); continue
                fm, fb = blobs(t/"f.pgm", float(DPI))
                got = locate_refit(fb, fm.width, cb, cm.width, DOC_SCALE,
                                   args.band, args.step)
                if got is None:
                    sc[name] = float("nan"); continue
                sc[name] = got[0]
                if name == "mid":
                    bx = bar_column(fb, fm.width)
                    if bx is not None:
                        fp = trimmed(fb, fm.width)
                        lo = min(b[0] for b in fb)
                        frac = (bx - lo) / max(1, len(fp))
                        n = got[2] - got[1] + 1
                        pre, post = residual_split(
                            fp, profile(cb, cm.width), got[1], n, frac)
            best = max(sc, key=lambda k: (sc[k] if sc[k] == sc[k] else -1))
            gain = sc[best] - sc["mid"]
            rs = (f"{pre:.2f} / {post:.2f}" if pre is not None else "no bar")
            print(f"{r['id'].split('_')[-1]:<8} {grp:<8} "
                  + " ".join(f"{sc[v]:>7.3f}" for v in VARIANTS)
                  + f" {best:>6} {gain:>+7.3f}   {rs:>16}")
            out.append(dict(id=r["id"], grp=grp, sc=sc, best=best, gain=gain,
                            pre=pre, post=post))

    print()
    for grp in ("RED", "control"):
        g = [o for o in out if o["grp"] == grp]
        if not g:
            continue
        print(f"{grp:<8} n={len(g):<3} "
              f"median gain from the best variant "
              f"{statistics.median(o['gain'] for o in g):+.3f}   "
              f"tight bar wins on {sum(1 for o in g if o['best']=='bar')}, "
              f"\\mid wins on {sum(1 for o in g if o['best']=='mid')}, "
              f"wide wins on {sum(1 for o in g if o['best']=='wide')}")
    ps = [(o['pre'], o['post']) for o in out if o['pre'] is not None]
    if ps:
        print(f"\nresidual before / after the bar, median over {len(ps)} rows: "
              f"{statistics.median(p for p, _ in ps):.3f} / "
              f"{statistics.median(q for _, q in ps):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
