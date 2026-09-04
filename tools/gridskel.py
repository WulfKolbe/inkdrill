"""621 -- the grid skeleton of a matrix crop, from white space alone.

REPORT ONLY. It reads no LaTeX and knows nothing about what the reader
said; it takes a crop and returns rows x cols, an `&&&\\\\` skeleton and
a rect per cell. The question it exists to answer is whether white
space gets the dimensions right where the reader got them wrong.

THE OUTER DELIMITERS ARE EXCLUDED BY THEIR EXTENT, and that does two
jobs rather than one. A bracket is a component nearly as tall as the
matrix sitting at the left or right extreme, so it is findable without
reading it -- and once found, the grid is what lies BETWEEN the two
delimiters, vertically bounded by their own span. That second part
removes the material a MathPix region routinely swallows: a line of
prose above the matrix, or the `X (x) Y =` that introduces it.

A crop with no delimiters is refused rather than guessed at. An
aligned display is not a matrix, and a detector that returns a grid
for one would be inventing structure -- 0902.0431 p14 is four ragged
lines of an aligned equation, and reporting it as 4x3 would be the
kind of confident wrong answer this project exists to catch.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from typing import NamedTuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from inkdrill.pnmio import mask_from_pgm                      # noqa: E402
from inkdrill.raster import InkMask                           # noqa: E402
from inkdrill.skeleton import parts                           # noqa: E402


class Grid(NamedTuple):
    rows: int
    cols: int
    cells: list          #: [[(x0, y0, x1, y1), ...], ...] crop pixels
    region: tuple        #: the grid's own box, delimiters excluded
    delimiters: tuple    #: (left box, right box)

    def skeleton(self) -> str:
        return " \\\\\n".join(" & ".join("" for _ in range(self.cols))
                              for _ in range(self.rows)) + " \\\\"


def separators(gaps, ratio=2.0):
    """Which white gaps are grid separators, by the BREAK in their
    widths rather than by a width.

    A matrix column separator is a quad; the white between two glyphs
    of one cell is a fraction of a glyph. Sorted widest first the two
    populations are separated by a step, and the first step of at least
    `ratio` is where it is -- 3.8x, 4.2x and 4.9x on the three crops of
    621. Taking the LARGEST step instead is wrong: `clean` has a 4.0x
    step at k=11 between two intra-cell gaps, later and bigger than the
    3.8x that actually divides the columns.

    WHEN THERE IS NO STEP, EVERY GAP IS A SEPARATOR. A matrix whose
    cells are single symbols has no intra-cell white at all, so a rule
    that always looks for a break invents one -- `clean`'s rows are
    40, 40, 39 and the answer is three separators, not two.
    """
    w = sorted(gaps, key=lambda g: -(g[1] - g[0]))
    for k in range(1, len(w)):
        a = w[k - 1][1] - w[k - 1][0] + 1
        b = w[k][1] - w[k][0] + 1
        if a / max(1, b) >= ratio:
            return sorted(w[:k]), f"break at {k} (x{a / max(1, b):.1f})"
    return sorted(w), "no break -- every gap is a separator"


def _bands(flags):
    """Maximal runs of True, as (start, end) inclusive."""
    out, s = [], None
    for i, f in enumerate(flags):
        if f and s is None:
            s = i
        elif not f and s is not None:
            out.append((s, i - 1))
            s = None
    if s is not None:
        out.append((s, len(flags) - 1))
    return out


def find_delimiters(mask: InkMask, min_ink=20, tall=0.55):
    """The leftmost and rightmost components that are nearly as tall as
    the tallest thing in the crop. Returns (left, right) or None."""
    ps = [p for p in parts(mask, min_ink=min_ink)]
    if not ps:
        return None
    hmax = max(p.height for p in ps)
    tallones = [p for p in ps if p.height >= tall * hmax]
    if len(tallones) < 2:
        return None
    left = min(tallones, key=lambda p: p.x0)
    right = max(tallones, key=lambda p: p.x1)
    if left is right or right.x0 <= left.x1:
        return None
    # a delimiter is NARROW: a tall wide component is a matrix column,
    # not a bracket
    if left.width > 0.25 * (right.x1 - left.x0):
        return None
    return left, right


def grid_of(mask: InkMask, *, min_ink=20, gap=1, ratio=2.0):
    d = find_delimiters(mask, min_ink=min_ink)
    if d is None:
        return "no pair of tall outer components -- not a delimited matrix"
    left, right = d
    x0, x1 = left.x1 + 1, right.x0 - 1
    y0 = max(left.y0, right.y0)
    y1 = min(left.y1, right.y1)
    if x1 <= x0 or y1 <= y0:
        return "the delimiters enclose nothing"
    w = x1 - x0 + 1
    colink = [0] * w
    rowink = [0] * (y1 - y0 + 1)
    for y in range(y0, y1 + 1):
        row = mask.data[y * mask.width + x0:y * mask.width + x1 + 1]
        n = row.count(0xFF)
        rowink[y - y0] = n
        if n:
            for i, b in enumerate(row):
                if b:
                    colink[i] += 1
    # a separator is a run of columns (or rows) with NO ink at all
    colgaps = [(a, b) for a, b in _bands([c == 0 for c in colink])
               if b - a + 1 >= gap]
    rowgaps = [(a, b) for a, b in _bands([r == 0 for r in rowink])
               if b - a + 1 >= gap]
    # drop a gap that touches the border: it is padding, not a separator
    colgaps = [g for g in colgaps if g[0] > 0 and g[1] < w - 1]
    rowgaps = [g for g in rowgaps if g[0] > 0 and g[1] < len(rowink) - 1]
    colgaps, colwhy = separators(colgaps, ratio)
    rowgaps, rowwhy = separators(rowgaps, ratio)

    xs = [x0] + [x0 + (a + b) // 2 for a, b in colgaps] + [x1]
    ys = [y0] + [y0 + (a + b) // 2 for a, b in rowgaps] + [y1]
    cells = [[(xs[c], ys[r], xs[c + 1], ys[r + 1])
              for c in range(len(xs) - 1)] for r in range(len(ys) - 1)]
    g = Grid(len(ys) - 1, len(xs) - 1, cells, (x0, y0, x1, y1),
             ((left.x0, left.y0, left.x1, left.y1),
              (right.x0, right.y0, right.x1, right.y1)))
    return g, rowwhy, colwhy


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pgm", type=pathlib.Path, nargs="+")
    ap.add_argument("--gap", type=int, default=1)
    ap.add_argument("--min-ink", type=int, default=20)
    ap.add_argument("--ratio", type=float, default=2.0)
    ap.add_argument("--cells", action="store_true")
    args = ap.parse_args()
    for f in args.pgm:
        m = mask_from_pgm(f, threshold=200)
        got = grid_of(m, min_ink=args.min_ink, gap=args.gap,
                      ratio=args.ratio)
        print(f"\n=== {f.name}   crop {m.width}x{m.height}")
        if isinstance(got, str):
            print(f"    REFUSED: {got}")
            continue
        g, rowwhy, colwhy = got
        print(f"    delimiters L{g.delimiters[0]}  R{g.delimiters[1]}")
        print(f"    grid region {g.region}")
        print(f"    ROWS x COLS = {g.rows} x {g.cols}")
        print(f"      rows: {rowwhy}")
        print(f"      cols: {colwhy}")
        print("    skeleton:")
        for line in g.skeleton().splitlines():
            print(f"      {line}")
        if args.cells:
            for r, rowc in enumerate(g.cells):
                for c, box in enumerate(rowc):
                    print(f"      cell[{r}][{c}] {box}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
