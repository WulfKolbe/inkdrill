r"""cellrect.py -- a table cell's rectangle, from emitted rule positions (602).

The consumer half of 601's spec, written BEFORE the emitter so the
spec can be checked against the lattice for ten rows rather than
corrected after 316,007 have been emitted to it.

WHAT IT REPLACES. `_table_cells` finds a page's table by nesting,
clusters its ruling into a lattice, drops slivers under a floor and
refuses a page whose rows cover too little of the region. Every one of
those is a decision with a measured constant behind it and each has
been wrong once. Given the rule positions the typesetter already
knows, none of them is needed: a cell is the rectangle between two
vertical rules and two horizontal ones.

THE CELL IS THE INTERIOR, NOT THE SPAN BETWEEN RULE CENTRES. A rule
has width, `_table_cells` reports the enclosed BACKGROUND region, and
the background begins where the rule ends. So the rect is inset by
half a rule on each side. At 0.4 pt and 300 dpi that is 0.83 px a
side -- small, and not zero, and the difference is systematic rather
than noise, which is what makes it worth insetting rather than
tolerating.

CONTRACT
========

G1  pure -- numbers in, a `Rect` out. No file access, no process, and
    no page raster: the geometry is decided by the typesetter, not
    measured from ink.
G2  input is PDF USER SPACE in bp, y UP from the bottom of the page,
    which is what 601 measured `\zsavepos` to give once the TeX-point
    conversion is applied. Output is RASTER pixels, y DOWN, inclusive
    on both bounds -- `raster`'s convention, so a caller can slice a
    mask with it directly.
G3  the y flip needs the page height, so it is required and not
    defaulted. A page height guessed as A4 is wrong on every landscape
    report in this corpus, and reports are a3 landscape.
G4  the rect is INSET by half a rule on each side (G2's paragraph
    above). `rule_bp` is an argument because `\arrayrulewidth` is a
    document setting; the default is LaTeX's own 0.4 pt.
G5  column rules are given left to right and row rules as
    (above, below) in user space, so `above > below`. Both orders are
    ASSERTED rather than silently sorted: a caller that has them
    backwards has a bug the rect would otherwise hide.
G6  an empty rect -- rules closer together than the ink they bound --
    is returned as-is with `x1 < x0` or `y1 < y0` rather than clamped,
    because a zero-width cell is a finding about the emission and
    clamping it to one pixel would hide it.
"""

from __future__ import annotations

import math
from typing import NamedTuple

__all__ = ["Rect", "cell_rect", "row_rects", "ARRAYRULE_BP"]

#: LaTeX's `\arrayrulewidth` default, in PDF points
ARRAYRULE_BP = 0.4


class Rect(NamedTuple):
    """Raster pixels, y down, inclusive on both bounds (G2)."""
    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def width(self) -> int:
        return self.x1 - self.x0 + 1

    @property
    def height(self) -> int:
        return self.y1 - self.y0 + 1

    @property
    def is_empty(self) -> bool:
        return self.x1 < self.x0 or self.y1 < self.y0


def cell_rect(column_rules_bp, rule_above_bp, rule_below_bp, col, *,
              page_height_bp, dpi, rule_bp=ARRAYRULE_BP) -> Rect:
    """The interior of cell `col` of one row (G1-G6)."""
    n = len(column_rules_bp)
    if not 0 <= col < n - 1:
        raise IndexError(f"column {col} of {n - 1} (need {n} rules)")
    if any(b <= a for a, b in zip(column_rules_bp, column_rules_bp[1:])):
        raise ValueError("column rules must ascend left to right")   # G5
    if rule_above_bp <= rule_below_bp:
        raise ValueError("rule_above must be above rule_below in user "
                         "space, where y increases upward")          # G5
    s = dpi / 72.0
    half = rule_bp / 2.0
    x0 = (column_rules_bp[col] + half) * s
    x1 = (column_rules_bp[col + 1] - half) * s
    # user y up -> raster y down
    y0 = (page_height_bp - (rule_above_bp - half)) * s
    y1 = (page_height_bp - (rule_below_bp + half)) * s
    # `ceil` for the low bound and `floor` for the high one is the
    # half-open-to-closed conversion: floor(x) is already the last
    # pixel index at or inside x. Subtracting a further 1 -- which the
    # first version did -- put x1 one pixel short on every cell of
    # every row, which the checker in tools/cellcheck.py reported as a
    # constant -1 across 60 cells before anything was emitted. A
    # SYSTEMATIC residual is a bug in the consumer; a scattered one
    # would have been a difference between the two detections.
    return Rect(math.ceil(x0), math.ceil(y0),
                math.floor(x1), math.floor(y1))                      # G6


def row_rects(column_rules_bp, rule_above_bp, rule_below_bp, *,
              page_height_bp, dpi, rule_bp=ARRAYRULE_BP) -> list:
    """Every cell of one row, left to right."""
    return [cell_rect(column_rules_bp, rule_above_bp, rule_below_bp, c,
                      page_height_bp=page_height_bp, dpi=dpi,
                      rule_bp=rule_bp)
            for c in range(len(column_rules_bp) - 1)]
