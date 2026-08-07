"""nest.py — holes, the containment forest, and the ordering relations.

CONTRACT (written before implementation; see docs/units.md U6)
=============================================================

Holes, computed a second way on purpose
---------------------------------------
U3 already reports a hole count per component, as the cycle rank
`E - V + C` of the run adjacency graph. This unit computes holes a
completely different way -- as background components of the inverted
local mask at `conn=4` -- and the two must agree.

That is the point. `cycle_count` counting *holes* rather than merely
counting cycles was, until now, supported by the duality argument plus
six fixtures. Here it gets an independent oracle, and the oracle shares
no code with the thing it checks. Measured before implementation:
113 of 113 real components from rendered corpus pages agree exactly.

Connectivity is paired, always
------------------------------
8-connected foreground implies 4-connected background. The pair is
constrained, not two independent settings -- an 8-connected background
would let a hole leak diagonally through a 1-px wall, and the counts
would stop agreeing with U3.

The mask is padded by one pixel before inverting, so the outside is
always a single border-touching background region and excludes itself
from the hole count without a special case.

Finding the enclosing region
----------------------------
For any region, the pixel directly ABOVE its topmost-leftmost pixel
identifies its parent, and this is exact rather than a heuristic:

  * above a foreground pixel, a 4-adjacent foreground pixel would be in
    the SAME component (8-connectivity includes 4), and the pixel is
    topmost, so the pixel above must be background;
  * above a background pixel, a 4-adjacent background pixel would be in
    the same background component, so the pixel above must be foreground.

So one lookup per region gives the containment forest, with no
point-in-polygon test and no bbox guessing.

The four relations, which are NOT the same thing
------------------------------------------------
docs/units.md is explicit that these must be distinguished:

  `hole_of(h, c)`        h is a hole enclosed by component c's own ink
  `ink_in_hole(d, h)`    d is a separate ink component sitting inside
                         hole h -- it is NOT part of c and NOT a hole
  `bbox_contains(a, b)`  purely geometric; the weakest, and true in many
                         cases where neither of the above is
  `nesting_chain(x)`     the full path from a top-level figure inward

A `\\fbox` is the case that forces the distinction: the box has one hole,
and the text inside is `ink_in_hole` of that hole -- emphatically not
`hole_of` the box. A unit that conflated them would count the text as
part of the frame's topology.

Depth, and figure/ground parity
-------------------------------
Depth alternates figure, ground, figure: a top-level component is 0, its
holes are 1, ink inside those holes is 2, holes of that ink are 3. So
EVEN depth is always ink and ODD depth is always background -- the parity
is a check, not a convention, and `NestForest.check_parity()` asserts it.
Nested frames give 0 / 1 / 2 exactly as the plan specifies.

Guarantees
----------
G1  the hole count per component equals U3's `Component.cycle_count`,
    computed with no shared code -- each is the other's oracle
G2  the outside is never counted as a hole, at any mask size, including
    a mask that is entirely ink or entirely background
G3  every region has exactly one parent; the forest is a forest, with no
    cycles and no orphans below the roots
G4  depth parity holds: even depth is ink, odd depth is background
G5  `hole_of` and `ink_in_hole` are disjoint -- no pair satisfies both --
    and `bbox_contains` is implied by either but implies neither
G6  a connected m x n table frame yields exactly m*n holes
G7  holes recurse: a hole of ink that itself sits in a hole is found, to
    any depth

Non-guarantees (out of scope for U6)
------------------------------------
  * no moment aggregates -- that is U5; `Nesting` carries ids, and the
    caller joins to `aggregate.moments_per_component` if it wants area
  * no collinear rule grouping for DISCONNECTED table frames -- that is
    the counterpart case named in the plan and it needs U5's geometry;
    this unit handles the connected frame
  * no reading order
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .raster import BG, INK, InkMask, Rect
from .sweep import Capture, sweep

__all__ = ["Kind", "Region", "Nesting", "nest", "InvalidConnectivity"]


class InvalidConnectivity(ValueError):
    """foreground connectivity must be 8, with background 4."""


class Kind(Enum):
    INK = "ink"
    HOLE = "hole"
    OUTSIDE = "outside"


@dataclass(slots=True)
class Region:
    """One node of the containment forest."""
    id: int
    kind: Kind
    depth: int                      # -1 for the outside
    area: int
    x0: int
    y0: int
    x1: int
    y1: int
    parent: int | None = None
    children: list[int] = field(default_factory=list)

    @property
    def bbox(self) -> Rect:
        """Half-open, per the package's Rect convention."""
        return Rect(self.x0, self.y0, self.x1 + 1, self.y1 + 1)

    def bbox_contains(self, other: "Region") -> bool:
        """The weakest of the four relations, and the only purely
        geometric one. True in many cases where nothing is nested."""
        return (self.x0 <= other.x0 and self.y0 <= other.y0
                and self.x1 >= other.x1 and self.y1 >= other.y1)


@dataclass(slots=True)
class Nesting:
    regions: dict[int, Region]
    roots: list[int]
    outside: int

    # ---- the four relations -------------------------------------------

    def holes_of(self, region_id: int) -> list[int]:
        """The holes enclosed by this ink component's own ink."""
        r = self.regions[region_id]
        if r.kind is not Kind.INK:
            return []
        return [c for c in r.children
                if self.regions[c].kind is Kind.HOLE]

    def ink_in_hole(self, hole_id: int) -> list[int]:
        """Separate ink components sitting inside this hole. NOT part of
        the enclosing component -- the `\\fbox` case."""
        h = self.regions[hole_id]
        if h.kind is not Kind.HOLE:
            return []
        return [c for c in h.children
                if self.regions[c].kind is Kind.INK]

    def hole_of(self, hole_id: int) -> int | None:
        """The component whose ink encloses this hole."""
        h = self.regions[hole_id]
        if h.kind is not Kind.HOLE:
            return None
        return h.parent

    def nesting_chain(self, region_id: int) -> list[int]:
        """Outermost to innermost, ending at this region."""
        chain = []
        cur: int | None = region_id
        while cur is not None and cur != self.outside:
            chain.append(cur)
            cur = self.regions[cur].parent
        chain.reverse()
        return chain

    # ---- counts and checks ---------------------------------------------

    @property
    def hole_count(self) -> int:
        return sum(1 for r in self.regions.values() if r.kind is Kind.HOLE)

    def hole_counts_by_component(self) -> dict[int, int]:
        """Keyed by this unit's own ink-region ids, for comparison with
        U3 after matching components by bounding box."""
        return {r.id: len(self.holes_of(r.id))
                for r in self.regions.values() if r.kind is Kind.INK}

    def check_parity(self) -> bool:
        """G4: even depth is ink, odd depth is background."""
        for r in self.regions.values():
            if r.kind is Kind.OUTSIDE:
                continue
            want = Kind.INK if r.depth % 2 == 0 else Kind.HOLE
            if r.kind is not want:
                return False
        return True

    def check_forest(self) -> bool:
        """G3: one parent each, no cycles, no orphans below the roots."""
        for r in self.regions.values():
            if r.kind is Kind.OUTSIDE:
                continue
            seen = set()
            cur: int | None = r.id
            while cur is not None and cur != self.outside:
                if cur in seen:
                    return False
                seen.add(cur)
                cur = self.regions[cur].parent
            if cur != self.outside:
                return False
        return True


def _label(mask: InkMask, want_ink: bool, conn: int) -> tuple[list[int], int]:
    """Flood-fill labelling over the padded grid. Returns (labels, count)
    with -1 where the pixel is not of the wanted polarity."""
    w, h = mask.width, mask.height
    data = mask.data
    target = INK if want_ink else BG
    lab = [-1] * (w * h)
    nxt = 0
    if conn == 8:
        steps = ((1, 0), (-1, 0), (0, 1), (0, -1),
                 (1, 1), (1, -1), (-1, 1), (-1, -1))
    else:
        steps = ((1, 0), (-1, 0), (0, 1), (0, -1))
    for s in range(w * h):
        if data[s] != target or lab[s] != -1:
            continue
        lab[s] = nxt
        stack = [s]
        while stack:
            p = stack.pop()
            px, py = p % w, p // w
            for dx, dy in steps:
                qx, qy = px + dx, py + dy
                if 0 <= qx < w and 0 <= qy < h:
                    q = qy * w + qx
                    if data[q] == target and lab[q] == -1:
                        lab[q] = nxt
                        stack.append(q)
        nxt += 1
    return lab, nxt


def nest(mask: InkMask, *, conn: int = 8) -> Nesting:
    """Holes, the containment forest and the four relations.

    `conn` is the FOREGROUND connectivity and must be 8; the background
    is then 4. The pair is constrained -- see the module docstring.
    """
    if conn != 8:
        raise InvalidConnectivity(
            f"foreground connectivity must be 8 (background 4); got {conn}")

    # Pad by one so the outside is a single border-touching region.
    w, h = mask.width + 2, mask.height + 2
    buf = bytearray(w * h)
    for y in range(mask.height):
        src = y * mask.width
        buf[(y + 1) * w + 1:(y + 1) * w + 1 + mask.width] = \
            mask.data[src:src + mask.width]
    padded = InkMask(bytes(buf), w, h)

    fg, n_fg = _label(padded, True, 8)
    bg, n_bg = _label(padded, False, 4)

    regions: dict[int, Region] = {}
    # ids: ink regions 0..n_fg-1, background regions n_fg..n_fg+n_bg-1
    def bg_id(b: int) -> int:
        return n_fg + b

    # extents and areas, in ORIGINAL (unpadded) coordinates
    box: dict[int, list[int]] = {}
    area: dict[int, int] = {}
    top: dict[int, int] = {}          # first (topmost, then leftmost) pixel
    for p in range(w * h):
        f, b = fg[p], bg[p]
        rid = f if f != -1 else bg_id(b)
        x, y = p % w - 1, p // w - 1
        if rid not in box:
            box[rid] = [x, y, x, y]
            top[rid] = p
            area[rid] = 0
        else:
            bb = box[rid]
            if x < bb[0]:
                bb[0] = x
            if y < bb[1]:
                bb[1] = y
            if x > bb[2]:
                bb[2] = x
            if y > bb[3]:
                bb[3] = y
        area[rid] += 1

    outside = bg_id(bg[0])            # the pad ring, by construction

    for rid, bb in box.items():
        kind = (Kind.INK if rid < n_fg
                else (Kind.OUTSIDE if rid == outside else Kind.HOLE))
        regions[rid] = Region(rid, kind, -1, area[rid], *bb)

    # Parent of every region: the label directly above its topmost pixel.
    # Exact, not heuristic -- see the module docstring.
    for rid, r in regions.items():
        if rid == outside:
            continue
        p = top[rid]
        up = p - w
        f, b = fg[up], bg[up]
        parent = f if f != -1 else bg_id(b)
        r.parent = parent
        regions[parent].children.append(rid)

    # Depth: alternates from every top-level ink component.
    for rid in regions[outside].children:
        stack = [(rid, 0)]
        while stack:
            cur, d = stack.pop()
            regions[cur].depth = d
            for ch in regions[cur].children:
                stack.append((ch, d + 1))

    for r in regions.values():
        r.children.sort()

    roots = sorted(regions[outside].children)
    return Nesting(regions, roots, outside)
