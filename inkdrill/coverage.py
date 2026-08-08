"""coverage.py — cross-checking another tool's regions against real ink.

CONTRACT (written before implementation; see docs/units.md U11)
==============================================================

What this unit is for
---------------------
Another tool -- OCR, MathPix, a layout detector -- returns rectangles it
believes contain content. This unit asks the only question that matters:
**what did it miss, and where is it wrong at the edges?**

That makes the residual the product, exactly as in U10, but for a
different reason. In U10 the residual explains an alignment. Here the
residual IS the deliverable: ink with no region is content the other tool
did not see.

Containment, NOT centres -- the opposite of U10
-----------------------------------------------
U10 matches a component to a glyph by its CENTRE, because pdfminer gives
the ADVANCE box and overlap against it is systematically wrong.

**Here the rule is inverted, and the inversion is the point.** A region
is a real boundary drawn by another tool, and a blob crossing it is the
finding -- that is the case that clips the limits off a tall integral or
sum, where the region was fitted to the body of a line and the glyph
extends above and below it. Using centres would classify such a blob as
comfortably inside and report nothing.

So: a component is INSIDE only when its bounding box lies wholly within
one region, and STRADDLING when it intersects a region without being
contained.

Measured
--------
Real scanned pages with line-level OCR. Two samples, six pages then eight
independent ones:

        ink inside one region        89.29% / 89.19%
        ink with no region            9.94% /  8.17%   per page 0.00 - 100.00%, median 0.53%
        ink straddling a region edge  0.76% /  2.33%   per page 0.00 -  33.63%, median 2.05%
        ink under overlapping regions 0.01% /  0.31%
        region with no ink            0.00% /  0.03%

**The aggregates are stable and nearly useless.** The per-page spread is
the finding: one page reports **100% missed** -- 3 regions against 950 ink
components, an OCR failure the aggregate would bury -- and another reports
**33.63% straddle** on a diagram where regions cut through content.
Against a 0.53% median. Those two pages ARE the deliverable.

`CoverageReport` therefore reports per-class MEMBERS, and a caller should
read the distribution rather than the mean. This is the fourth time a
small-sample aggregate has misled in this project, after the U0 colour
fraction, the U7 density dependence and the U10 residual rates. The rule
it keeps teaching: record the mechanism and the spread.

**Region with no ink is rare but NOT zero** -- 0.00% on the first sample,
0.03% on the second. An early reading that a tool "never hallucinates an
empty region" was a six-page artefact, which is the same lesson again at
small scale.

Guarantees
----------
G1  every component lands in exactly one class -- a partition, nothing
    dropped or double-counted. The partition is over the boxes AT OR
    ABOVE `min_pixels`; `box_count` reports how many those were, so a
    caller can see what the filter removed rather than inferring it
G2  INSIDE requires full containment and STRADDLING is any intersection
    that is not containment; centres are deliberately NOT used, because
    the boundary crossing is the finding
G3  every class is reported with its MEMBERS, not just a count, so the
    missed ink can be looked at
G4  every region is classified too, so an empty region is visible even
    though it measured at zero
G5  classification is deterministic and independent of input order
G6  an empty page yields an empty report rather than a division by zero
G7  regions may overlap; a component inside two of them is its own class
    rather than being silently assigned to the first

Non-guarantees (out of scope for U11)
-------------------------------------
  * no opinion on WHY a region was missed -- this unit reports where, and
    a human or a later unit decides whether it is a figure, maths, or a
    genuine miss
  * no region merging or splitting
  * no reading order -- that is U14
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence

from .space import Affine

__all__ = ["CoverageClass", "Region", "Box", "CoverageReport", "check"]


class CoverageClass(Enum):
    """The four residual classes docs/units.md names, plus the clean
    case. Every one is reported."""
    INSIDE = "ink inside one region"
    MISSED = "ink with no region"
    STRADDLE = "ink straddling a region edge"
    OVERLAPPING = "ink under overlapping regions"
    EMPTY_REGION = "region with no ink"


@dataclass(frozen=True, slots=True)
class Region:
    """A rectangle another tool claims contains content.

    Half-open in the same sense as `raster.Rect`: `x1`/`y1` are exclusive
    bounds in the coordinate system the components use.
    """
    id: int
    x0: float
    y0: float
    x1: float
    y1: float
    label: str = ""

    def contains(self, b: "Box") -> bool:
        return (b.x0 >= self.x0 and b.y0 >= self.y0
                and b.x1 <= self.x1 and b.y1 <= self.y1)

    def intersects(self, b: "Box") -> bool:
        return (b.x0 <= self.x1 and b.x1 >= self.x0
                and b.y0 <= self.y1 and b.y1 >= self.y0)

    def scaled(self, t: Affine) -> "Region":
        """Move this region into another space by composing an affine --
        the same discipline as U10's `page_transform`."""
        ax, ay = t.point(self.x0, self.y0)
        bx, by = t.point(self.x1, self.y1)
        return Region(self.id, min(ax, bx), min(ay, by),
                      max(ax, bx), max(ay, by), self.label)


@dataclass(frozen=True, slots=True)
class Box:
    """One ink component's bounding box, inclusive pixel bounds."""
    id: int
    x0: int
    y0: int
    x1: int
    y1: int
    area: int = 0

    @property
    def pixels(self) -> int:
        return (self.x1 - self.x0 + 1) * (self.y1 - self.y0 + 1)


@dataclass(slots=True)
class CoverageReport:
    """Members, not just counts (G3)."""
    by_class: dict[CoverageClass, list[int]] = field(default_factory=dict)
    box_count: int = 0
    region_count: int = 0
    regions_of: dict[int, list[int]] = field(default_factory=dict)

    def count(self, k: CoverageClass) -> int:
        return len(self.by_class.get(k, ()))

    def members(self, k: CoverageClass) -> list[int]:
        return list(self.by_class.get(k, ()))

    @property
    def classified_boxes(self) -> int:
        return sum(self.count(k) for k in CoverageClass
                   if k is not CoverageClass.EMPTY_REGION)

    def fraction(self, k: CoverageClass) -> float:
        """Of the INK, for ink classes; of the REGIONS, for empty
        regions. Mixing the two denominators would make the numbers
        incomparable."""
        if k is CoverageClass.EMPTY_REGION:
            return (self.count(k) / self.region_count
                    if self.region_count else 0.0)
        n = self.classified_boxes
        return self.count(k) / n if n else 0.0

    @property
    def missed_fraction(self) -> float:
        """The headline. Read the distribution across pages, not this
        number on one page -- measured 0.00% to 29.19% per page against a
        0.20% median."""
        return self.fraction(CoverageClass.MISSED)

    def report(self) -> str:
        n = self.classified_boxes
        if not n and not self.region_count:
            return "no ink and no regions"
        lines = [f"{self.box_count} components, {self.region_count} regions"]
        for k in CoverageClass:
            c = self.count(k)
            if c:
                lines.append(f"  {c:7} ({self.fraction(k):6.2%})  {k.value}")
        return "\n".join(lines)


def check(boxes: Sequence[Box], regions: Sequence[Region], *,
          to_pixels: Affine | None = None,
          min_pixels: int = 1) -> CoverageReport:
    """Classify ink against another tool's regions.

    `to_pixels` moves regions into the components' space; pass
    `gold.page_transform` or a scale. `min_pixels` drops specks below a
    size, because a 1-px speck reported as "missed content" is noise a
    caller has to filter anyway.

    A box with `x1 < x0` or `y1 < y0` is degenerate and is dropped by the
    same filter, since its pixel count is not positive. `box_count`
    reports how many boxes survived, so the drop is visible.
    """
    regs = [r.scaled(to_pixels) if to_pixels is not None else r
            for r in regions]
    # deterministic, order-independent (G5)
    items = sorted((b for b in boxes if b.pixels >= min_pixels),
                   key=lambda b: (b.y0, b.x0, b.id))

    rep = CoverageReport(box_count=len(items), region_count=len(regs))
    rep.by_class = {k: [] for k in CoverageClass}
    touched = [0] * len(regs)

    for b in items:
        inside = [i for i, r in enumerate(regs) if r.contains(b)]
        meets = [i for i, r in enumerate(regs) if r.intersects(b)]
        for i in meets:
            touched[i] += 1
        if not meets:
            rep.by_class[CoverageClass.MISSED].append(b.id)
        elif len(inside) > 1:
            rep.by_class[CoverageClass.OVERLAPPING].append(b.id)
        elif inside:
            rep.by_class[CoverageClass.INSIDE].append(b.id)
        else:
            # intersects something, contained by nothing: the case that
            # clips the limits off a tall integral or sum
            rep.by_class[CoverageClass.STRADDLE].append(b.id)
        rep.regions_of[b.id] = [regs[i].id for i in meets]

    for i, n in enumerate(touched):
        if n == 0:
            rep.by_class[CoverageClass.EMPTY_REGION].append(regs[i].id)

    rep.by_class = {k: v for k, v in rep.by_class.items() if v}
    return rep
