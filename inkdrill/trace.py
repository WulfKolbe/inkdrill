"""trace.py -- ordered boundary contours from an `InkMask`.

CONTRACT (written before implementation)
========================================

The inverse of `scan.py`: that unit turns closed contours into a mask;
this one walks a mask's boundaries back out as closed, ordered loops.
Per component: the OUTER contour first, then one contour per hole.

The walk follows pixel-edge CRACKS -- the unit-length edges between an
ink pixel and a background pixel -- with **ink on the left of travel**.
Corners are integer points on the pixel grid (pixel (i, j) covers
[i, i+1) x [j, j+1), the package convention), so the polygon is exact:
no rounding, no smoothing, and the shoelace area of a loop is an
integer count of pixels.

Winding is a CONSEQUENCE, not a decoration: with ink kept left, an
outer boundary comes out with positive shoelace area in raster
coordinates (y down) and a hole boundary negative. `O` gives two loops
of opposite sign; `8` gives three, the two holes agreeing with each
other and opposing the outer.

The saddle rule is where the connectivity pairing lives. At a corner
where two ink pixels meet diagonally, the walker must decide whether
they are one region pinched (foreground 8-connectivity: yes) or two
regions touching (4: they would be). This package's pairing is fixed --
8 for ink, 4 for background -- so the walker takes the turn that keeps
diagonal ink connected: a checkerboard pair is ONE component and must
yield ONE outer loop, visiting the shared corner twice.

Guarantees
----------
G1  pure -- a mask in, contours out; the mask is not modified
G2  every contour is CLOSED: it returns to its first corner, and every
    boundary crack of the mask is used exactly once across all contours
G3  per component, exactly `1 + cycle_count` contours -- the oracle is
    `sweep`, which shares no code with this walk
G4  winding: the outer contour of every component has positive signed
    area, every hole negative
G5  the signed areas over a component sum to its EXACT pixel count,
    and over the mask to `ink_count` -- holes subtract, which is what
    signed area is for
G6  ordering: outer first, then holes in raster order of their topmost
    boundary corner
"""

from __future__ import annotations

from dataclasses import dataclass

from .raster import InkMask
from .sweep import Capture, sweep

__all__ = ["Contour", "contours", "signed_area"]

# Directions as (dx, dy), y growing downward.
_E, _S, _W, _N = (1, 0), (0, 1), (-1, 0), (0, -1)


def signed_area(points) -> float:
    """Shoelace over corner points; integer-valued for crack polygons.

    Sign convention MEASURED, not derived: with ink on the left of
    travel and y growing downward, an outer boundary yields positive
    `sum(x0*y1 - x1*y0) / 2`. The first draft negated it and the ring
    oracle (outer +20, hole -6, sum = 14 ink pixels) caught the flip
    immediately -- which is what G5 is for.
    """
    a = 0
    n = len(points)
    for i in range(n):
        x0, y0 = points[i]
        x1, y1 = points[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    return a / 2.0


@dataclass(frozen=True, slots=True)
class Contour:
    """One closed boundary loop. `points` are grid corners, ordered,
    first point not repeated at the end."""
    points: tuple[tuple[int, int], ...]
    area: float                    # signed; >0 outer, <0 hole (G4)

    @property
    def is_outer(self) -> bool:
        return self.area > 0


def _ink(mask: InkMask, x: int, y: int) -> bool:
    if 0 <= x < mask.width and 0 <= y < mask.height:
        return mask.data[y * mask.width + x] == 0xFF
    return False


def contours(mask: InkMask, *, conn: int = 8) -> list[list[Contour]]:
    """All boundary loops, grouped per component (G1-G6).

    Returns one list per component, ordered like
    `sweep(mask).components`; each inner list is `[outer, hole, ...]`.
    """
    if conn != 8:
        raise ValueError(
            f"foreground connectivity must be 8 (background 4); got {conn}")
    w, h = mask.width, mask.height

    # Directed boundary cracks, ink on the LEFT of travel:
    #   heading E along a pixel's TOP edge    (ink below,  bg above)
    #   heading S along a pixel's RIGHT edge  (ink left,   bg right)
    #   heading W along a pixel's BOTTOM edge (ink above,  bg below)
    #   heading N along a pixel's LEFT edge   (ink right,  bg left)
    edges: set[tuple[int, int, int, int]] = set()
    for y in range(h):
        base = y * w
        for x in range(w):
            if mask.data[base + x] != 0xFF:
                continue
            if not _ink(mask, x, y - 1):
                edges.add((x, y, *_E))
            if not _ink(mask, x + 1, y):
                edges.add((x + 1, y, *_S))
            if not _ink(mask, x, y + 1):
                edges.add((x + 1, y + 1, *_W))
            if not _ink(mask, x - 1, y):
                edges.add((x, y + 1, *_N))

    def next_dir(cx: int, cy: int, dx: int, dy: int):
        """The outgoing direction at corner (cx, cy) arriving with
        (dx, dy). Left turn first: hugging the ink keeps a diagonal
        pair connected, which is the 8-connectivity saddle rule."""
        left = (dy, -dx)
        straight = (dx, dy)
        right = (-dy, dx)
        for cand in (left, straight, right):
            if (cx, cy, *cand) in edges:
                return cand
        return None

    loops: list[tuple[tuple[int, int], ...]] = []
    while edges:
        sx, sy, dx, dy = min(edges)          # deterministic start
        pts = []
        cx, cy = sx, sy
        cdx, cdy = dx, dy
        while True:
            pts.append((cx, cy))
            edges.discard((cx, cy, cdx, cdy))
            cx, cy = cx + cdx, cy + cdy
            if (cx, cy, cdx, cdy) == (sx, sy, dx, dy):
                break
            if (cx, cy) == (sx, sy) and (cx, cy, cdx, cdy) not in edges:
                nd = next_dir(cx, cy, cdx, cdy)
                if nd is None or (cx, cy, *nd) == (sx, sy, dx, dy):
                    break
                cdx, cdy = nd
                continue
            nd = next_dir(cx, cy, cdx, cdy)
            if nd is None:
                break
            cdx, cdy = nd
        loops.append(tuple(pts))

    # Ownership: the ink pixel each loop's first crack borders. The
    # first crack is the minimal directed edge of the loop, which for
    # an E-heading top edge borders pixel (x, y); for the other
    # headings the bordering pixel follows from the ink-on-left rule.
    res = sweep(mask, conn=8, capture=Capture.GRAPH)
    by_node = {n.id: n for n in res.nodes}
    comp_of_pixel: dict[tuple[int, int], int] = {}
    for ci, comp in enumerate(res.components):
        for nid in comp.nodes:
            n = by_node[nid]
            for x in range(n.lo, n.hi + 1):
                comp_of_pixel[(x, n.line)] = ci

    def owner(loop) -> int:
        (x, y) = loop[0]
        (nx, ny) = loop[1]
        dx, dy = nx - x, ny - y
        if (dx, dy) == _E:
            px, py = x, y
        elif (dx, dy) == _S:
            px, py = x - 1, y
        elif (dx, dy) == _W:
            px, py = x - 1, y - 1
        else:
            px, py = x, y - 1
        return comp_of_pixel[(px, py)]

    grouped: list[list[Contour]] = [[] for _ in res.components]
    for loop in loops:
        c = Contour(loop, signed_area(loop))
        grouped[owner(loop)].append(c)
    for lst in grouped:
        lst.sort(key=lambda c: (not c.is_outer, min(c.points)))
    return grouped
