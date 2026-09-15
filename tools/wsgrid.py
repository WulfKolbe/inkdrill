r"""wsgrid.py -- the whitespace grid of a displayed array, measured from ink.

For an overlay program that stamps a symbol into EMPTY CELLS of a large
maths expression before MathPix reads the page. This measures only: it
says where the columns and rows are and which cells hold no ink. It
writes nothing on a page.

    python3 tools/wsgrid.py CROP.pgm --dpi 400 --key 0902.0431_EQ0756 \
        [--reading evidence-equation.tex]

Input is the lossless scan cell of ONE expression (a pgm cut from the
page render), never a published crop. Output, one JSON document:

    {key: {dpi, crop:[w,h], stem,
           blocks: [{rows, columns,
                     x: column boundaries as fractions of crop width,
                     y: [[top, bottom], ...] per row, fractions of height,
                     empty: [[bool per column] per row]}],
           gutter_classes: [[min_px, max_px, count], ...] per block,
           reading: {rows, cells_per_row, nonempty_per_row,
                     ink_cells_per_row, disagree: [row, ...]}   # --reading}}

THE PASS, reusing what exists -- no third nest:

1. Components (`sweep`, moments), speck floor area < stem^2. A floor in
   pixels ("both dims >= 2") dropped all 42 thin strokes of EQ0756 at
   300 dpi -- minus signs, equals bars, fraction bars render 1 px tall.
2. `mathstruct.rows`, then LINES: a row of >= 3 members is a line; a
   shorter row (a fraction's numerator or denominator, a lone script)
   attaches to the nearest line. Merging rows by leading instead chains
   every line of a block together wherever a 1/2 bridges the leading.
3. BLOCKS: split at the largest leading between lines. An array set as
   two independently aligned parts (EQ0756: six lines, then four
   centred lines) has two lattices, not one.
4. X-GUTTERS per block: columns blank across EVERY row of the block
   (`raster.profile` run_count == 0), interior, at least 2 x stem wide.
5. COLUMN BOUNDARIES: gutter widths are cut at the LARGEST RATIO JUMP;
   gutters above it are column boundaries, below it are inter-symbol
   space. A cut at mode + gap failed when the widest class was modal.
6. OCCUPANCY: a cell is empty iff it holds fewer than stem^2 ink pixels.
   Centroids were tried first and invented 18 empty cells in sliver
   columns whose ink belongs to a glyph centred next door.

MEASURED ON ONE EXPRESSION (out/666). Every constant above was placed on
EQ0756 of 0902.0431 at 300/400/600 dpi, where all counts agree across
the three resolutions. Nothing here is tested on a second expression or
on an array with genuinely blank cells -- EQ0756 has none.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from inkdrill import mathstruct, pnmio, raster  # noqa: E402
from inkdrill.raster import InkMask  # noqa: E402
from inkdrill.sweep import sweep  # noqa: E402

LINE_MEMBERS = 3        # a row with fewer members is a fraction part or script


def components(m: InkMask, stem: int):
    res = sweep(m, conn=8, moments=True)
    return [mo for mo in res.moments.values() if mo.area >= stem * stem]


def lines(comps):
    glyphs = [mathstruct.Glyph(id=i, x0=mo.x0, top=mo.y0, x1=mo.x1 + 1, bottom=mo.y1 + 1)
              for i, mo in enumerate(comps)]
    rs = sorted(mathstruct.rows(glyphs), key=lambda r: r.top)
    anchors = [r for r in rs if len(r.members) >= LINE_MEMBERS]
    band = {id(r): [r.top, r.bottom] for r in anchors}
    for r in rs:
        if len(r.members) >= LINE_MEMBERS:
            continue
        mid = (r.top + r.bottom) / 2
        a = min(anchors, key=lambda a: abs((a.top + a.bottom) / 2 - mid))
        b = band[id(a)]
        b[0], b[1] = min(b[0], r.top), max(b[1], r.bottom)
    return [band[id(a)] for a in anchors]


def blocks(bands):
    if len(bands) < 3:
        return [bands]
    lead = [bands[i + 1][0] - bands[i][1] for i in range(len(bands) - 1)]
    cut = max(range(len(lead)), key=lambda i: lead[i])
    return [bands[:cut + 1], bands[cut + 1:]]


def gutters(m: InkMask, y0: int, y1: int, stem: int):
    W = m.width
    sub = InkMask(m.data[y0 * W:y1 * W], W, y1 - y0)
    runs = []
    for i, (_cov, _ext, cnt) in enumerate(raster.profile(sub, "col")):
        if cnt:
            continue
        if runs and i == runs[-1][1] + 1:
            runs[-1][1] = i
        else:
            runs.append([i, i])
    return [(a, b) for a, b in runs if a > 0 and b < W - 1 and b - a + 1 >= 2 * stem]


def ratio_cut(widths):
    ws = sorted(widths)
    if len(ws) < 2:
        return None
    i = max(range(len(ws) - 1), key=lambda j: ws[j + 1] / ws[j])
    return (ws[i] + ws[i + 1]) / 2


def classes(widths, jump=1.5):
    ws = sorted(widths)
    out = [[ws[0]]] if ws else []
    for a, b in zip(ws, ws[1:]):
        (out[-1].append(b) if b < jump * a else out.append([b]))
    return [[min(c), max(c), len(c)] for c in out]


def measure(m: InkMask):
    W, H = m.width, m.height
    stem, _ = raster.stroke_mode(m, "row")
    out = dict(crop=[W, H], stem=stem, blocks=[], gutter_classes=[])
    for grp in blocks(lines(components(m, stem))):
        y0, y1 = int(grp[0][0]), int(grp[-1][1])
        g = gutters(m, y0, y1, stem)
        widths = [b - a + 1 for a, b in g]
        cut = ratio_cut(widths)
        cols = [(a, b) for a, b in g if cut is not None and b - a + 1 > cut]
        xb = [0] + [(a + b) // 2 for a, b in cols] + [W]
        empty = [[sum(m.data[y * W + c0:y * W + c1].count(255)
                      for y in range(int(t), int(bt))) < stem * stem
                  for c0, c1 in zip(xb, xb[1:])] for t, bt in grp]
        out["blocks"].append(dict(rows=len(grp), columns=len(xb) - 1,
                                  x=[round(v / W, 4) for v in xb],
                                  y=[[round(t / H, 4), round(b / H, 4)] for t, b in grp],
                                  empty=empty))
        out["gutter_classes"].append(classes(widths))
    return out


def reading_cells(latex: str):
    """Cells per row of the FIRST array in a reading: all, and non-empty."""
    m = re.search(r"\\begin\{array\}\{[^}]*\}(.*?)\\end\{array\}", latex, re.S)
    if not m:
        return None
    rows_ = [r for r in re.split(r"\\\\", m.group(1)) if r.strip()]
    cells = [r.split("&") for r in rows_]
    return [len(c) for c in cells], [sum(1 for x in c if x.strip()) for c in cells]


def compare(result, latex):
    rc = reading_cells(latex)
    if rc is None:
        return dict(refused="no array in the reading")
    allc, nonempty = rc
    ink = [blk["columns"] - sum(row) for blk in result["blocks"] for row in blk["empty"]]
    if len(ink) != len(allc):
        return dict(refused=f"{len(ink)} ink lines against {len(allc)} reading rows")
    return dict(rows=len(allc), cells_per_row=allc, nonempty_per_row=nonempty,
                ink_cells_per_row=ink,
                disagree=[i for i, (a, b) in enumerate(zip(ink, nonempty)) if a != b])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pgm", type=pathlib.Path)
    ap.add_argument("--dpi", type=int, required=True)
    ap.add_argument("--key", required=True, help="e.g. 0902.0431_EQ0756")
    ap.add_argument("--reading", type=pathlib.Path,
                    help="evidence-*.tex holding the row named by --key")
    args = ap.parse_args()
    res = dict(dpi=args.dpi, **measure(pnmio.load_mask(str(args.pgm), dpi=args.dpi)))
    if args.reading:
        from tools.formulafind import rows
        ident = args.key.rsplit("_", 1)[-1]
        hit = next((r for r in rows(args.reading) if r["id"].endswith(ident)), None)
        res["reading"] = compare(res, hit["math"]) if hit else dict(refused="row not found")
    json.dump({args.key: res}, sys.stdout)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
