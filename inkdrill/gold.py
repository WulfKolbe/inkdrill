"""gold.py — pdfminer alignment and the many-to-many matcher.

CONTRACT (written before implementation; see docs/units.md U10)
==============================================================

What this unit is for
---------------------
Ink components come from U3. Glyph boxes come from pdfminer, in PDF
points. Aligning them gives a gold label per glyph -- free training data
and, more immediately, a way to find what other tools missed.

The residual is the product, not the leftovers
----------------------------------------------
docs/units.md is explicit that the four classes are REPORTED rather than
discarded. The premise check says why (§3 "U10 premise check", 18,519
assignments at 400 dpi):

                         3 pages   12 pages   per-page spread
        1 : 1              66.93%     85.17%     81.2 - 86.7%
        N ink : 1 glyph    12.34%     13.75%     --
        glyph with no ink   1.11%      0.64%     0.00 - 1.86%
        ink with no glyph  19.61%      0.39%     0.0 - 2.8%
        1 ink : N glyphs    0.02%      0.05%     --

All at 400 dpi, the corpus render; the stated target is 600.

**Two of the first five numbers were artefacts of a three-page sample**
and are corrected above -- one figure-heavy page contributed 3,572
image-only components against 4 and 35 on the others, moving 1:1 by 50
points and image-only by a factor of fifty. The three structural classes
reproduced.

Even at 85% clean, a single "agreement rate" would throw away everything
interesting. **N ink per glyph is the largest genuine residual** at
13-14% -- `i`, `j`, `:`, accents and broken strokes, the multi-component
glyphs U4 already had to accommodate. **Ink with no glyph is figures and
rules**, so it tracks page content entirely and a diagram correctly has
no glyph.

**The feared case barely exists.** One blob straddling two glyphs is
0.02%. So the matcher does NOT split blobs; it reports the rare case and
lets a caller decide. Building a splitter would have been effort spent on
two thousandths of the data.

Composition, not a formula
--------------------------
The pt -> px transform is built by COMPOSING U1 affines -- flip, scale,
crop, rotate -- never by writing out a single closed-form expression.
That is the whole reason U1 exists, and it is what lets `/Rotate` and a
crop box arrive later without rederiving anything. `page_transform()`
returns an `Affine`, so a caller can compose further or invert it.

The y flip is where this bites: PDF y grows upward from the bottom-left,
raster y grows downward from the top-left. Getting it wrong produces a
vertically mirrored match that still looks plausible in aggregate,
because text lines are roughly symmetric down a page.

Resolution
----------
Also measured: **100 dpi is unusable** -- 58.78% of glyphs leave no
recoverable ink at all. 200 dpi loses about one glyph in eleven, 400 dpi
about one in ninety. `MatchReport.glyphs_without_ink` is the rate to
watch, and it is a better resolution signal than the N-to-1 rate, which
*falls* at low dpi because components merge while glyphs vanish.

Guarantees
----------
G1  the pt -> px transform is built by composing `space.Affine`s, and
    `page_transform` returns one, so it stays composable and invertible
G2  every component and every glyph appears in exactly one class -- the
    classification is a partition, nothing dropped, nothing double-counted
G3  the four residual classes are reported with their members, not just
    counted, so a caller can act on them. When a glyph is BOTH split and
    merged -- several components, one of which a neighbour also claims --
    SPLIT wins. That precedence is a choice, and it is tested.
G4  a component matches a glyph when its CENTRE lies inside the glyph
    box; centres rather than overlap, because pdfminer's box is the
    ADVANCE box and overlap against it is systematically wrong -- the
    failure that wasted the first U4 premise check
G5  `GoldGlyph` export is lossless with respect to the match: every
    exported glyph names its class and its component ids
G6  matching is deterministic and independent of input order
G7  an empty page yields an empty report rather than a division by zero

Non-guarantees (out of scope for U10)
-------------------------------------
  * no blob splitting -- measured at 0.02% of assignments; reported,
    not repaired
  * no rasterization and no ink-to-ink comparison; that needs U9's
    rasterizer half, which is not built. This unit compares ink to the
    ADVANCE box and is honest about the difference.
  * no reading order, no line grouping -- that is U14
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Sequence

from .space import Affine

__all__ = ["MatchKind", "Glyph", "Component", "GoldGlyph", "MatchReport",
           "page_transform", "match", "to_coco"]


class MatchKind(Enum):
    """The four residual classes docs/units.md names, plus the easy case.

    Every one is reported. A single agreement rate would discard the
    two thirds of the data that is interesting.
    """
    ONE_TO_ONE = "1:1"
    IMAGE_ONLY = "ink with no glyph"
    SPLIT = "N ink : 1 glyph"
    MISSING_INK = "glyph with no ink"
    MERGED = "1 ink : N glyphs"


@dataclass(frozen=True, slots=True)
class Glyph:
    """One pdfminer character, in PDF points, y measured from the
    bottom."""
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    fontname: str = ""


@dataclass(frozen=True, slots=True)
class Component:
    """One ink component, in raster pixels, y measured from the top."""
    id: int
    x0: int
    y0: int
    x1: int
    y1: int
    area: int = 0

    @property
    def centre(self) -> tuple[float, float]:
        return ((self.x0 + self.x1 + 1) / 2.0, (self.y0 + self.y1 + 1) / 2.0)


@dataclass(frozen=True, slots=True)
class GoldGlyph:
    """One aligned glyph, exportable. Names its class and its components
    (G5)."""
    text: str
    fontname: str
    kind: MatchKind
    components: tuple[int, ...]
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def bbox_xywh(self) -> tuple[float, float, float, float]:
        return (self.x0, self.y0, self.x1 - self.x0, self.y1 - self.y0)


def page_transform(page_height_pt: float, dpi: float, *,
                   rotate: int = 0,
                   crop_x0_pt: float = 0.0,
                   crop_y0_pt: float = 0.0,
                   page_width_pt: float = 0.0) -> Affine:
    """PDF points -> raster pixels, by COMPOSITION (G1).

    Built as: translate the crop origin to zero, flip y (PDF grows up,
    raster grows down), scale by dpi/72, then rotate. Never as one closed
    formula -- that is what U1 exists for, and it is what lets `/Rotate`
    and a crop box arrive later without rederiving anything.
    """
    if dpi <= 0:
        raise ValueError(f"dpi must be positive, got {dpi}")
    if rotate % 90 != 0:
        raise ValueError(f"/Rotate must be a multiple of 90, got {rotate}")

    scale = dpi / 72.0
    steps = [
        # 1. crop origin to zero
        Affine.translate(-crop_x0_pt, -crop_y0_pt),
        # 2. y-UP to y-DOWN over the (cropped) page height
        Affine.flip_y(page_height_pt - crop_y0_pt),
        # 3. points to pixels
        Affine.scale(scale),
    ]
    r = rotate % 360
    if r:
        w = (page_width_pt - crop_x0_pt) * scale
        h = (page_height_pt - crop_y0_pt) * scale
        # rotate about the origin, then translate the box back into
        # positive coordinates -- again composed, not written out
        steps.append(Affine.rotate(math.radians(r)))
        if r == 90:
            steps.append(Affine.translate(h, 0))
        elif r == 180:
            steps.append(Affine.translate(w, h))
        else:                                    # 270
            steps.append(Affine.translate(0, w))
    return Affine.chain(steps)


@dataclass(slots=True)
class MatchReport:
    """Every component and every glyph in exactly one class (G2), with
    members (G3)."""
    gold: list[GoldGlyph] = field(default_factory=list)
    by_kind: dict[MatchKind, list[int]] = field(default_factory=dict)
    component_count: int = 0
    glyph_count: int = 0

    def count(self, kind: MatchKind) -> int:
        return len(self.by_kind.get(kind, ()))

    @property
    def assignments(self) -> int:
        return sum(len(v) for v in self.by_kind.values())

    def fraction(self, kind: MatchKind) -> float:
        n = self.assignments
        return self.count(kind) / n if n else 0.0

    @property
    def glyphs_without_ink(self) -> float:
        """The resolution signal. Measured 1.11% at 400 dpi, 9.20% at
        200, 58.78% at 100 -- a better guide than the N-to-1 rate, which
        falls at low dpi because components merge while glyphs vanish."""
        return (self.count(MatchKind.MISSING_INK) / self.glyph_count
                if self.glyph_count else 0.0)

    def report(self) -> str:
        n = self.assignments
        if not n:
            return "no components and no glyphs"
        lines = [f"{self.component_count} components, {self.glyph_count} "
                 f"glyphs, {n} assignments"]
        for k in MatchKind:
            c = self.count(k)
            # presentational only: a zero-count class is omitted from the
            # printed summary. `by_kind` and `count()` are unaffected, so
            # nothing downstream depends on this branch.
            if c:
                lines.append(f"  {c:7} ({c/n:6.2%})  {k.value}")
        return "\n".join(lines)


def match(components: Sequence[Component], glyphs: Sequence[Glyph], *,
          to_pixels: Affine | None = None) -> MatchReport:
    """Assign ink components to glyph boxes and classify the residual.

    A component matches a glyph when its CENTRE lies inside the glyph box
    (G4). Centres rather than overlap, because pdfminer's box is the
    ADVANCE box, not the ink box -- overlap against it is systematically
    wrong, which is the failure that wasted the first U4 premise check.

    `to_pixels` transforms glyph boxes from PDF points into the
    component's raster space; pass the `page_transform` result. Without
    it, glyphs are assumed already in pixel space.
    """
    boxes: list[tuple[float, float, float, float]] = []
    for g in glyphs:
        if to_pixels is None:
            x0, y0, x1, y1 = g.x0, g.y0, g.x1, g.y1
        else:
            ax, ay = to_pixels.point(g.x0, g.y0)
            bx, by = to_pixels.point(g.x1, g.y1)
            x0, x1 = (ax, bx) if ax <= bx else (bx, ax)
            y0, y1 = (ay, by) if ay <= by else (by, ay)
        boxes.append((x0, y0, x1, y1))

    # deterministic and order-independent (G6)
    comps = sorted(components, key=lambda c: (c.y0, c.x0, c.id))

    hits: list[list[int]] = []
    per_glyph: list[list[int]] = [[] for _ in boxes]
    for ci, c in enumerate(comps):
        cx, cy = c.centre
        found = [j for j, (x0, y0, x1, y1) in enumerate(boxes)
                 if x0 <= cx <= x1 and y0 <= cy <= y1]
        hits.append(found)
        for j in found:
            per_glyph[j].append(ci)

    rep = MatchReport(component_count=len(comps), glyph_count=len(glyphs))
    rep.by_kind = {k: [] for k in MatchKind}

    for ci, found in enumerate(hits):
        c = comps[ci]
        if not found:
            rep.by_kind[MatchKind.IMAGE_ONLY].append(c.id)
        elif len(found) > 1:
            rep.by_kind[MatchKind.MERGED].append(c.id)
        elif len(per_glyph[found[0]]) > 1:
            rep.by_kind[MatchKind.SPLIT].append(c.id)
        else:
            rep.by_kind[MatchKind.ONE_TO_ONE].append(c.id)

    for j, members in enumerate(per_glyph):
        g = glyphs[j]
        x0, y0, x1, y1 = boxes[j]
        if not members:
            rep.by_kind[MatchKind.MISSING_INK].append(j)
            kind = MatchKind.MISSING_INK
        elif len(members) > 1:
            kind = MatchKind.SPLIT
        elif len(hits[members[0]]) > 1:
            kind = MatchKind.MERGED
        else:
            kind = MatchKind.ONE_TO_ONE
        rep.gold.append(GoldGlyph(
            g.text, g.fontname, kind,
            tuple(comps[m].id for m in members), x0, y0, x1, y1))

    rep.by_kind = {k: v for k, v in rep.by_kind.items() if v}
    return rep


def to_coco(report: MatchReport, *, image_id: int = 1,
            image_name: str = "page.png",
            width: int = 0, height: int = 0) -> dict:
    """Export the gold glyphs in COCO form (G5).

    Every annotation carries its match class and component ids, so an
    export can be filtered to the 1:1 subset or audited for the residual
    rather than silently averaging them together.
    """
    cats: dict[str, int] = {}
    anns = []
    for i, g in enumerate(report.gold):
        cid = cats.setdefault(g.text, len(cats) + 1)
        x, y, w, h = g.bbox_xywh
        anns.append({
            "id": i + 1,
            "image_id": image_id,
            "category_id": cid,
            "bbox": [x, y, w, h],
            "area": w * h,
            "iscrowd": 0,
            "match_kind": g.kind.value,
            "components": list(g.components),
            "fontname": g.fontname,
        })
    return {
        "images": [{"id": image_id, "file_name": image_name,
                    "width": width, "height": height}],
        "annotations": anns,
        "categories": [{"id": v, "name": k} for k, v in
                       sorted(cats.items(), key=lambda kv: kv[1])],
    }
