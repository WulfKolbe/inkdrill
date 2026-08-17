"""typeface.py -- page-level typeface signals from ink alone.

CONTRACT (written before implementation; premises measured first)
=================================================================

Four signals, each RELATIVE and each with its measured premise:

`stroke_width(mask)` -- the classic pen estimate `2*area/perimeter`,
perimeter from `trace.contours` (each crack is unit length, so the
perimeter is exact, not an approximation over a smoothed curve). For a
long stroke of width w and length L, area ~ wL and perimeter ~ 2L, so
the estimate converges on w. Premise, TeX Gyre at 96 px/em: bold is
1.43-1.58x regular across n/o/e/H in both Termes and Heros -- the
1.4x floor holds with margin.

`font_weight_class(items)` -- 1-D clustering of stroke_width/height
ratios, gap-split like `emit.cell_grid`: sorted ratios start a new
class where the gap exceeds `tol` times the median ratio. RELATIVE,
NEVER ABSOLUTE: a page's own weights are clusters; calling one of them
"bold" needs a font, which inkdrill does not have.

`slant(moments)` -- `abs(Moments.shear)`; the caller medians it over a
page. Premise: italic medians 3.2x (Termes) and 11.9x (Heros) the
roman medians -- the 1.7x floor holds with a wide margin.

`serif_excess(row, col)` -- total termini minus 2*(Reeb births +
closes). WEAK, and recorded as such: Termes (serif) medians 0 and
Heros (sans) -1 per glyph, overlapping ranges -- directional over a
page median, useless per glyph. A signal, not a discriminator.

`hollow(...)` -- an OUTLINE-face glyph against its filled form:
`cycles >= 3 and fill < 0.35`. Every stroke of an outline face is two
boundary lines, so its interior becomes one more hole class and the
fill collapses; a filled `B` has 2 holes and fill ~0.5.
"""

from __future__ import annotations

import statistics

from .aggregate import Moments
from .raster import InkMask
from .reeb import contract, signature
from .sweep import Capture, SweepResult, sweep, termini
from .trace import contours

__all__ = ["stroke_width", "font_weight_class", "slant", "serif_excess",
           "hollow"]


def stroke_width(mask: InkMask) -> float:
    """`2*area/perimeter` in px; 0.0 for an empty mask."""
    if not mask.ink_count:
        return 0.0
    per = sum(len(c.points) for comp in contours(mask) for c in comp)
    return 2.0 * mask.ink_count / per


def font_weight_class(items, *, tol: float = 0.25):
    """Cluster (stroke_width, height) pairs into weight classes.

    `items` is a sequence of `(width_px, height_px)`. Returns
    `(classes, modal)`: one class index per item, classes ordered
    light-to-heavy, and the index of the page's modal class.

    The ratio width/height is what makes it size-free: a heading is
    thicker than body text in px but not in ratio, while bold is
    thicker in ratio. The gap rule is `cell_grid`'s: a new class where
    the sorted-ratio gap exceeds `tol` times the MEDIAN ratio -- a
    threshold in the page's own units, so a dpi change cannot retune
    it.
    """
    if not items:
        return [], 0
    ratios = [w / max(h, 1.0) for w, h in items]
    order = sorted(range(len(ratios)), key=lambda i: ratios[i])
    med = statistics.median(ratios)
    cut = tol * med
    classes = [0] * len(ratios)
    cls = 0
    for a, b in zip(order, order[1:]):
        if ratios[b] - ratios[a] > cut:
            cls += 1
        classes[b] = cls
    counts = {}
    for c in classes:
        counts[c] = counts.get(c, 0) + 1
    modal = max(counts, key=lambda c: (counts[c], -c))
    return classes, modal


def slant(moments: Moments) -> float:
    """`abs(shear)` -- the caller medians a page. Exists so the report
    has one name rather than an expression at each call site."""
    return abs(moments.shear)


def serif_excess(row: SweepResult, col: SweepResult) -> int:
    """Total termini minus 2*(Reeb births + closes).

    WEAK BY MEASUREMENT: per glyph the serif/sans ranges overlap
    (Termes -2..+1, Heros -4..+1); only the page MEDIAN is
    directional, 0 (serif) vs -1 (sans) on TeX Gyre. Quote it as a
    page signal or not at all.
    """
    t, b = termini(row)
    lt, rt = termini(col)
    sig = signature(contract(row))
    return t + b + lt + rt - 2 * (sig.births + sig.closes)


def hollow(*, area: int, width: int, height: int, cycles: int,
           max_fill: float = 0.35, min_cycles: int = 3) -> bool:
    """An outline-face glyph, not a filled one.

    Both conditions, both needed: an outline face doubles every stroke
    boundary, so holes multiply AND the fill collapses. A filled `B`
    has 2 holes at fill ~0.5 (cycles fail); a thin frame has fill
    ~0.05 at 1 hole (cycles fail); a halftone blob can reach 3 cycles
    at high fill (fill fails).
    """
    if width <= 0 or height <= 0:
        return False
    return cycles >= min_cycles and area / (width * height) < max_fill
