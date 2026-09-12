"""glyphangle.py -- the junction angle of a stem-and-arm glyph, from runs.

WHY. MathPix reads Mielke's interior-product operator `⌋` (`\\rfloor`)
as `⇃` (`\\downharpoonleft`). The two glyphs carry almost the same ink:
same stem, a short arm at the bottom left, within a pixel or two of the
same bounding box. Component counts, hole counts and ink distance all
pass them, and on a SCAN there is no text layer and no `/Encoding` to
appeal to -- the geometry is the only evidence there is.

The difference is in HOW the arm meets the stem:

    ⌋  the foot is perpendicular and FLAT
    ⇃  the barb is oblique and CURVED

so two numbers separate them, both read off the per-row spans of the
run adjacency:

    angle   the arm against the stem. 90 deg is a horizontal foot.
    drift   how far the leftmost ink moves per scan row along the arm.
            A flat foot does not move (0.0); a barb ramps (>= 1 px/row).

NOT FROM A SKELETON. A thinned skeleton would give the same angle in
principle, and `measure.py` found 26% of glyphs change their junction
count with size -- the instability would be inherited. Spans are exact
at any size.

MEASURED (out/661), rendered from the fonts at the size Mielke's ink
actually has, 40-47 px tall:

    glyph                        angle        drift      arm rows
    ⌋ cmsy10/floorright        83.7-84.3      0.0           2
    ⇃ msam10/harpoondownleft   63.4-69.4    1.0-1.33       3-5

and on 62 real instances in that book, EVERY one -- including all 14
MathPix read as a harpoon -- measured 79.7-80.5 deg at drift 0.0.

WHAT IT REFUSES. A component that is not a tall stem with a short arm
at its bottom pointing left returns None rather than an angle: a
letter, an accent, a fragment. Below about 40 px of glyph height the
foot collapses to a single scan row and the angle saturates at 90, so
the caller is given `height` and decides.

    python3 tools/glyphangle.py reference [--sizes 34,40,46,52]
    python3 tools/glyphangle.py document <bibkey> --out F.json
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from inkdrill import raster                                # noqa: E402
from inkdrill.sweep import sweep                           # noqa: E402
from tools.formulafind import (blobs, first_occurrence_lines,  # noqa: E402
                               frame_rect, fullres_crop, locate_refit,
                               page_frames, render, rows)

#: the pair this was built for; `\left.`/`\right.` forms included
SYMBOLS = ("rfloor", "downharpoonleft")
#: below this many scan rows the arm is one row and the angle saturates
MIN_HEIGHT = 40


def spans(mask, box=None):
    """row -> (leftmost, rightmost) ink column, within `box` if given."""
    x0, x1, y0, y1 = box if box else (0, mask.width - 1, 0, mask.height - 1)
    out = {}
    for r in raster.iter_runs(mask):
        if r.line < y0 or r.line > y1:
            continue
        lo, hi = max(r.lo, x0), min(r.hi, x1)
        if lo <= hi:
            out.setdefault(r.line, []).append((lo, hi))
    return {y: (min(a for a, b in v), max(b for a, b in v))
            for y, v in out.items()}


#: a column belongs to the stem when it carries ink in this share of the
#: glyph's rows. The stem is the ONLY part present from top to bottom.
STEM_SHARE = 0.6


def stem_arm(mask, box=None, side="left"):
    """(angle, drift, arm_rows, height) for a tall stem with a short arm
    at its bottom reaching `side`, else None.

    `angle` is degrees from the stem: 90 is a horizontal foot. `drift`
    is the mean absolute movement of the arm's outer edge per scan row.

    THE STEM IS FOUND, NOT ASSUMED. The first version took the extreme
    columns -- rightmost as the stem, leftmost as the arm tip -- which
    is direction-blind: it read a mirrored `⌊` as a `⌋` and could not
    refuse it, so the "reaches left" guard in this docstring was prose.
    A test built by mirroring the real glyph caught it.
    """
    s = spans(mask, box)
    if len(s) < 6:
        return None
    ys = sorted(s)
    height = len(ys)
    cols = collections.Counter()
    for y in ys:
        lo, hi = s[y]
        for x in range(lo, hi + 1):
            cols[x] += 1
    tall = sorted(x for x, n in cols.items() if n >= STEM_SHARE * height)
    if not tall:
        return None                      # nothing runs the whole height
    # the stem is the widest CONTIGUOUS band of those columns
    bands, run = [], [tall[0]]
    for x in tall[1:]:
        if x == run[-1] + 1:
            run.append(x)
        else:
            bands.append(run)
            run = [x]
    bands.append(run)
    band = max(bands, key=len)
    x0, x1 = band[0], band[-1]
    stem_w = x1 - x0 + 1
    if height / max(1, max(s[y][1] - s[y][0] + 1 for y in ys)) < 1.2:
        return None                      # squat: not a stem at all
    if side == "left":
        arm = [y for y in ys if s[y][0] < x0]
        edge = lambda y: s[y][0]
        reach = lambda y: x1 - s[y][0]
    else:
        arm = [y for y in ys if s[y][1] > x1]
        edge = lambda y: s[y][1]
        reach = lambda y: s[y][1] - x0
    if not arm or min(arm) < ys[0] + 0.55 * height:
        return None                      # the arm must be at the BOTTOM
    if max(reach(y) for y in arm) < stem_w:
        return None                      # and reach beyond the stem
    e = [edge(y) for y in arm]
    steps = [abs(e[i] - e[i - 1]) for i in range(1, len(e))]
    angle = math.degrees(math.atan2(max(reach(y) for y in arm),
                                    max(max(arm) - min(arm), 1e-9)))
    return (round(angle, 1), round(sum(steps) / max(1, len(steps)), 2),
            len(arm), height)


def reference(sizes):
    """The two glyphs' own features, rendered from the TeX tree. The
    control any reading of real ink is judged against."""
    from inkdrill import charstring, scan, type1
    tex = pathlib.Path("/usr/share/texmf-dist/fonts/type1")
    out = []
    for em in sizes:
        row = {"em": em}
        for font, glyph, name in (("cmsy10", "floorright", "rfloor"),
                                  ("msam10", "harpoondownleft",
                                   "downharpoonleft")):
            p = next(tex.rglob(f"{font}.pfb"), None)
            if p is None:
                row[name] = None
                continue
            m, _ = scan.render(charstring.outline(type1.load(str(p)), glyph),
                               1000, em)
            row[name] = stem_arm(m)
        out.append(row)
    return out


def _clean(text):
    r"""A display line arrives wrapped as `\[ ... \]`, which cannot go
    inside `$...$`: pdflatex answers "Bad math environment delimiter"
    and every row of the document fails at once."""
    t = text.strip()
    if t.startswith("\\[") and t.endswith("\\]"):
        t = t[2:-2]
    elif t.startswith("$$") and t.endswith("$$"):
        t = t[2:-2]
    return " ".join(re.sub(r"\\tag\{[^}]*\}", "", t).split())


def _instances(mask_c, mask_f, blobs_f, blobs_c, labels, place):
    """Pair each located rendered glyph with the ink under it.

    `place` maps a rendered x to a crop x. Left-to-right order matches
    the LaTeX order, because one line of maths does not stack.
    """
    found = [(b, stem_arm(mask_f, (b[0], b[1], b[2], b[3]))) for b in blobs_f]
    found = [(b, f) for b, f in found if f]
    if len(found) != len(labels):
        return None, f"locator: {len(labels)} in the LaTeX, {len(found)} found"
    sw = sweep(mask_c, conn=8, moments=True)
    out = []
    for (b, ref), label in zip(sorted(found, key=lambda z: z[0][0]), labels):
        x0, x1 = place(b[0]), place(b[1])
        pad = max(3, int(0.2 * (x1 - x0)))
        near = [mo for mo in sw.moments.values()
                if x0 - pad <= (mo.x0 + mo.x1) / 2 <= x1 + pad]
        if not near:
            out.append((label, None, ref, "no component at the mapped x", None))
            continue
        mo = max(near, key=lambda m: m.area)
        ink = stem_arm(mask_c, (mo.x0, mo.x1, mo.y0, mo.y1))
        out.append((label, ink, ref,
                    "" if ink else "the ink is not a stem and arm",
                    (mo.x0, mo.y0, mo.x1, mo.y1)))
    return out, ""


def document(library, bib, symbols, scale, crops=None):
    """Every occurrence of `symbols` in one document, measured on the
    LOSSLESS page. Display lines are placed by their ink-width ratio (the
    line IS the expression); inline spans are placed by `locate_refit`.
    """
    doc = library / bib
    sym = re.compile(r"\\(" + "|".join(symbols) + r")\b")
    frames, _ = page_frames(library, bib)
    lj = json.loads((doc / f"{bib}.lines.json").read_text())
    res, skip = [], collections.Counter()
    if crops:
        crops.mkdir(parents=True, exist_ok=True)

    def cut(page, region, out):
        x, y, w, h = frame_rect(region, frames[page])
        subprocess.run(["magick", str(doc / "inspect" / "pages" / f"p{page}.png"),
                        "-crop", f"{w}x{h}+{x}+{y}", "+repage", "-colorspace",
                        "Gray", "-depth", "8", str(out)],
                       capture_output=True, check=True)

    def record(page, where, label, ink, ref, why, mask=None, box=None):
        if ink is None:
            skip[why] += 1
            return
        res.append(dict(page=page, where=where, label=label, ink=ink,
                        rendered=ref))
        if crops and mask is not None and box is not None:
            n = f"{label}_p{page}_{where}_{box[0]}.png"
            subprocess.run(["magick", str(mask), "-crop",
                            f"{box[2]-box[0]+1}x{box[3]-box[1]+1}+{box[0]}+{box[1]}",
                            "+repage", "-resize", "400%", str(crops / n)],
                           capture_output=True)

    with tempfile.TemporaryDirectory() as td:
        t = pathlib.Path(td)
        # --- display lines: the line is the whole expression
        for page, pg in enumerate(lj.get("pages") or [], 1):
            for i, ln in enumerate(pg.get("lines") or []):
                text = ln.get("text") or ""
                if ln.get("type") != "math" or not sym.search(text):
                    continue
                if page not in frames:
                    skip["no page frame"] += 1
                    continue
                labels = sym.findall(text)
                if not render(_clean(text), t / "f.pgm", 600):
                    skip["render failed"] += 1
                    continue
                cut(page, ln["region"], t / "c.pgm")
                fm, fb = blobs(t / "f.pgm", 600.0)
                cm, cb = blobs(t / "c.pgm", 400.0)
                if not fb or not cb:
                    skip["no ink"] += 1
                    continue
                fw, cw = fb[-1][1] - fb[0][0], cb[-1][1] - cb[0][0]
                if fw <= 0 or cw <= 0:
                    skip["degenerate"] += 1
                    continue
                s = cw / fw
                got, why = _instances(cm, fm, fb, cb, labels,
                                      lambda rx: cb[0][0] + (rx - fb[0][0]) * s)
                if got is None:
                    skip[why] += 1
                    continue
                for label, ink, ref, w, box in got:
                    record(page, f"line{i}", label, ink, ref, w, t / "c.pgm",
                           box)
        # --- inline spans: place the expression in its host line
        first = first_occurrence_lines(library, bib)
        for r in rows(doc / "evidence-formula.tex"):
            m = r["math"]
            if not m or not sym.search(m):
                continue
            hit = first.get(m.strip())
            if not hit:
                skip["no host line"] += 1
                continue
            page, region = hit
            if page not in frames:
                skip["no page frame"] += 1
                continue
            if not fullres_crop(library, bib, page, region, frames[page],
                                t / "c.pgm"):
                skip["no crop"] += 1
                continue
            if not render(m, t / "f.pgm", 600):
                skip["render failed"] += 1
                continue
            fm, fb = blobs(t / "f.pgm", 600.0)
            cm, cb = blobs(t / "c.pgm", 400.0)
            if not fb or not cb:
                skip["no ink"] += 1
                continue
            got = locate_refit(fb, fm.width, cb, cm.width, scale, 0.12, 0.002)
            if got is None:
                skip["not placed"] += 1
                continue
            _, px0, _, _, _, own, _ = got
            inst, why = _instances(cm, fm, fb, cb, sym.findall(m),
                                   lambda rx: px0 + (rx - fb[0][0]) * own)
            if inst is None:
                skip[why] += 1
                continue
            for label, ink, ref, w, box in inst:
                record(page, r["id"].split("_")[-1], label, ink, ref, w,
                       t / "c.pgm", box)
    return res, dict(skip)


def report(res, skip):
    print(f"measured {len(res)} glyph instances; skipped {sum(skip.values())} "
          f"{skip}")
    for label in sorted({r["label"] for r in res}):
        g = [r for r in res if r["label"] == label]
        small = sum(1 for r in g if r["ink"][3] < MIN_HEIGHT)
        print(f"\n  read as \\{label}: n={len(g)} on "
              f"{len({(r['page'], r['where']) for r in g})} distinct places"
              f"{f'; {small} below {MIN_HEIGHT} px and not readable' if small else ''}")
        for k, i in (("angle", 0), ("drift", 1), ("arm rows", 2),
                     ("height", 3)):
            v = sorted(r["ink"][i] for r in g)
            print(f"     {k:<9} min {v[0]:<7} median {v[len(v)//2]:<7} "
                  f"max {v[-1]:<7} distinct {sorted(set(v))[:6]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("reference")
    a.add_argument("--sizes", default="34,40,46,52,58,64")
    b = sub.add_parser("document")
    b.add_argument("bibkey")
    b.add_argument("--library", type=pathlib.Path,
                   default=pathlib.Path.home() / "pdfdrill-library")
    b.add_argument("--symbols", default=",".join(SYMBOLS))
    b.add_argument("--scale", type=float, default=0.64,
                   help="the document scale for inline placement (out/660)")
    b.add_argument("--crops", type=pathlib.Path,
                   help="write each measured glyph as a picture, for the eye")
    b.add_argument("--out", type=pathlib.Path)
    args = ap.parse_args()
    if args.cmd == "reference":
        for row in reference([int(s) for s in args.sizes.split(",")]):
            print(f"  em {row['em']:>3}  "
                  + "  ".join(f"{k} {row[k]}" for k in row if k != "em"))
        return 0
    res, skip = document(args.library, args.bibkey,
                         tuple(args.symbols.split(",")), args.scale,
                         args.crops)
    report(res, skip)
    if args.out:
        args.out.write_text(json.dumps(dict(bibkey=args.bibkey, rows=res,
                                            skipped=skip), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
