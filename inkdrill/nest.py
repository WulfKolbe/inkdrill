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

from bisect import bisect_right
from collections import defaultdict

from .raster import BG, INK, InkMask, Rect
from .sweep import Capture, sweep

__all__ = ["Kind", "Region", "Nesting", "nest", "ink_only",
           "InvalidConnectivity"]


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


def _regions_via_sweeps(padded: InkMask, fgres=None):
    """Regions, extents and parents from TWO SWEEPS instead of a
    per-pixel flood fill.

    `_label` is retained below as the reference implementation and the
    tests hold the two to byte-identical output. This is the fast path
    and it is not a different algorithm -- the ink components of
    `sweep(m, conn=8)` and the background components of
    `sweep(m.inverted(), conn=4)` are the same partition the flood fill
    produces, because the connectivity pair is the same.

    Two things have to be reproduced exactly rather than merely
    computed, and both are about identity rather than geometry:

    * **Ids are assigned in raster order of each region's first pixel**,
      because that is what the flood fill's `for s in range(w * h)` does
      and `Nesting.roots` is sorted by id. Sorting components by
      (topmost line, then leftmost start) reproduces it.
    * **The parent is the region directly above a region's topmost-
      leftmost pixel.** The flood fill reads that from the label array;
      here a per-line index of runs is binary-searched instead. Runs are
      the unit this package works in -- a glyph is ~190 px and ~9 runs
      -- so the lookup is over a far smaller set.
    """
    w = padded.width
    if fgres is None:
        fgres = sweep(padded, axis="row", conn=8, capture=Capture.NONE)
    bgres = sweep(padded.inverted(), axis="row", conn=4, capture=Capture.NONE)

    per_line: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
    box: dict[int, list[int]] = {}
    area: dict[int, int] = {}
    top: dict[int, tuple[int, int]] = {}

    for res, is_ink in ((fgres, True), (bgres, False)):
        by_id = {n.id: n for n in res.nodes}
        for comp in res.components:
            runs = [by_id[i] for i in comp.nodes]
            y0 = min(r.line for r in runs)
            x0 = min(r.lo for r in runs if r.line == y0)
            a = 0
            bx = [min(r.lo for r in runs), y0,
                  max(r.hi for r in runs), max(r.line for r in runs)]
            for r in runs:
                a += r.hi - r.lo + 1
                per_line[r.line].append((r.lo, r.hi, (is_ink, comp.root)))
            box[(is_ink, comp.root)] = bx
            area[(is_ink, comp.root)] = a
            top[(is_ink, comp.root)] = (y0, x0)

    # Raster order of the first pixel, ink before background exactly as
    # the flood fill numbered them: all ink 0..n_fg-1, then background.
    ink = sorted((k for k in box if k[0]), key=lambda k: top[k])
    bg = sorted((k for k in box if not k[0]), key=lambda k: top[k])
    ident = {k: i for i, k in enumerate(ink)}
    ident.update({k: len(ink) + i for i, k in enumerate(bg)})

    for line in per_line:
        per_line[line].sort()

    def region_at(line: int, x: int) -> int:
        row = per_line.get(line)
        if not row:
            raise KeyError(f"no run covers ({line}, {x})")
        i = bisect_right(row, (x, w, (True, -1))) - 1
        if i < 0 or not (row[i][0] <= x <= row[i][1]):
            raise KeyError(f"no run covers ({line}, {x})")
        return ident[row[i][2]]

    return ident, box, area, top, region_at, len(ink)


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


@dataclass(slots=True)
class InkPass:
    """The ink half of `nest`, with the background half deferred.

    `regions` are the ink regions `nest(mask)` would produce, ids
    included -- not merely equivalent. That holds because `nest`
    numbers ink 0..n_fg-1 from the ink sweep alone and offsets the
    background afterwards, so an ink region's identity never depended
    on the background sweep.

    `cycles[i]` is that region's hole COUNT from the cycle rank, which
    equals `len(nest(mask).holes_of(id))` on every page measured. What
    is missing is hole GEOMETRY -- where the holes are and what sits
    inside them -- and `complete()` computes it, REUSING this ink pass
    rather than sweeping the ink again.

    The reuse is the point. A gate that costs a third sweep whenever it
    guesses wrong is not a saving, and the first version of this was
    exactly that: text pages 40% faster, table pages 30% slower, a net
    loss on a figure-heavy document.
    """
    regions: list
    cycles: list
    _padded: InkMask
    _fgres: object

    def pairs(self):
        return list(zip(self.regions, self.cycles))

    def complete(self) -> "Nesting":
        """The full `Nesting`, without repeating the ink sweep."""
        return _build(self._padded, self._fgres)


def ink_only(mask: InkMask, *, conn: int = 8) -> InkPass:
    """The ink regions `nest()` would produce, without the second sweep.

    Exists so a caller that needs no hole GEOMETRY can skip it and
    still speak the same id space. Emitting ids from two different
    spaces depending on what happened to be on the page is the trap
    this package has paid for twice; returning the same ids is what
    makes the saving safe to take.

    `parent`, `depth` and `children` are NOT filled in -- there is no
    forest without the background -- and stay at their defaults.
    """
    if conn != 8:
        raise InvalidConnectivity(
            f"foreground connectivity must be 8 (background 4); got {conn}")
    padded = _pad(mask)
    res = sweep(padded, axis="row", conn=8, capture=Capture.GRAPH)
    by_id = {n.id: n for n in res.nodes}
    rows = []
    for comp in res.components:
        runs = [by_id[i] for i in comp.nodes]
        y0 = min(r.line for r in runs)
        rows.append((y0, min(r.lo for r in runs if r.line == y0), comp, runs))
    rows.sort(key=lambda t: (t[0], t[1]))
    regions, cycles = [], []
    for rid, (y0, _x, comp, runs) in enumerate(rows):
        regions.append(Region(rid, Kind.INK, -1,
                              sum(r.hi - r.lo + 1 for r in runs),
                              min(r.lo for r in runs) - 1, y0 - 1,
                              max(r.hi for r in runs) - 1,
                              max(r.line for r in runs) - 1))
        cycles.append(comp.cycle_count)
    return InkPass(regions, cycles, padded, res)


def _pad(mask: InkMask) -> InkMask:
    """One-pixel border, so the outside is a single region."""
    w, h = mask.width + 2, mask.height + 2
    buf = bytearray(w * h)
    for y in range(mask.height):
        src = y * mask.width
        buf[(y + 1) * w + 1:(y + 1) * w + 1 + mask.width] = \
            mask.data[src:src + mask.width]
    return InkMask(bytes(buf), w, h)


def nest(mask: InkMask, *, conn: int = 8) -> Nesting:
    """Holes, the containment forest and the four relations.

    `conn` is the FOREGROUND connectivity and must be 8; the background
    is then 4. The pair is constrained -- see the module docstring.
    """
    if conn != 8:
        raise InvalidConnectivity(
            f"foreground connectivity must be 8 (background 4); got {conn}")
    return _build(_pad(mask), None)


def _build(padded: InkMask, fgres) -> Nesting:
    """The forest, given the padded mask and optionally its ink sweep."""
    ident, box, area, top, region_at, n_fg = _regions_via_sweeps(padded, fgres)

    regions: dict[int, Region] = {}
    # Extents are shifted back to ORIGINAL (unpadded) coordinates here;
    # the sweeps ran on the padded grid.
    for key, rid in ident.items():
        bx = box[key]
        regions[rid] = Region(rid, Kind.INK if key[0] else Kind.HOLE, -1,
                              area[key],
                              bx[0] - 1, bx[1] - 1, bx[2] - 1, bx[3] - 1)

    outside = region_at(0, 0)         # the pad ring, by construction
    regions[outside].kind = Kind.OUTSIDE

    # Parent of every region: the region directly above its topmost
    # pixel. Exact, not heuristic -- see the module docstring.
    for key, rid in ident.items():
        if rid == outside:
            continue
        y0, x0 = top[key]
        parent = region_at(y0 - 1, x0)
        regions[rid].parent = parent
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
