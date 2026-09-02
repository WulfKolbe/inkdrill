"""skeleton.py -- Zhang-Suen thinning, and the junction count (491).

A hole says a stroke came back to itself. A JUNCTION says three
strokes meet, which a hole cannot see: the bar of an L-slash touches
the stem and stops, enclosing nothing, so `nest` counts no hole and
`sweep` emits no merge -- the crossing survives only as an edge in
the run adjacency graph (see out/490.txt).

CONTRACT

G1  `skeleton(mask)` returns a mask of the same size whose ink is a
    1-px-wide medial set of the input's ink, by Zhang-Suen. Ink is
    0xFF and background 0x00, package-wide.
G2  thinning is IDEMPOTENT at the fixed point: a second call on a
    skeleton returns it unchanged.
G3  `junctions(mask)` counts skeleton pixels whose CROSSING NUMBER
    is three or more. It thins first unless told the input is
    already thin.

    NOT the raw 8-neighbour count. An 8-connected CORNER has two
    pixels of degree 3 -- on an `L` drawn 1 px wide, the pixel above
    the corner sees up, down AND the corner's right-hand neighbour
    diagonally -- so a degree test reports two junctions on a letter
    that has none. Measured on the first version of this file. The
    crossing number, half the sum of |n[i] - n[i+1]| around the
    cyclic neighbourhood, gives 2 at that corner and 4 at the centre
    of a `+`, which is the distinction wanted.
G4  the count is of PIXELS, not of junction sites. A Y meeting at one
    place can present two or three adjacent qualifying pixels
    depending on the rasterisation, so `junction_sites` clusters them
    by 8-connectivity and is the figure to compare across sizes.
G5  neither function needs a threshold. Thinning is defined by the
    Zhang-Suen conditions and a junction by a neighbour count; there
    is nothing to tune and nothing that moves with dpi.
G6  a stroke END has one neighbour and a stroke INTERIOR has two, so
    `>= 3` is the whole definition of a branch point. Ends are
    reported separately by `endpoints` because the pair together
    characterises a shape better than either alone -- an L has two
    ends and no junction, an L-slash has three ends and one junction.
"""
from __future__ import annotations

from .raster import InkMask

__all__ = ["skeleton", "junctions", "junction_sites", "endpoints"]

_N8 = ((-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1))


def _neighbours(buf, w, h, x, y):
    """P2..P9 clockwise from north, as 0/1 -- Zhang-Suen's ordering."""
    return [1 if (0 <= y + dy < h and 0 <= x + dx < w
                  and buf[(y + dy) * w + (x + dx)]) else 0
            for dy, dx in _N8]


def _transitions(n):
    return sum(1 for i in range(8)
               if n[i] == 0 and n[(i + 1) % 8] == 1)


def skeleton(mask: InkMask) -> InkMask:
    """G1, G2. Zhang-Suen thinning to a 1-px medial set."""
    w, h = mask.width, mask.height
    buf = bytearray(1 if b else 0 for b in mask.data)
    changed = True
    while changed:
        changed = False
        for step in (0, 1):
            doomed = []
            for y in range(1, h - 1):
                row = y * w
                for x in range(1, w - 1):
                    if not buf[row + x]:
                        continue
                    n = _neighbours(buf, w, h, x, y)
                    b = sum(n)
                    if not (2 <= b <= 6):
                        continue
                    if _transitions(n) != 1:
                        continue
                    p2, p3, p4, p5, p6, p7, p8, p9 = n
                    if step == 0:
                        if p2 * p4 * p6 or p4 * p6 * p8:
                            continue
                    else:
                        if p2 * p4 * p8 or p2 * p6 * p8:
                            continue
                    doomed.append(row + x)
            if doomed:
                changed = True
                for i in doomed:
                    buf[i] = 0
    return InkMask(bytes(0xFF if v else 0 for v in buf), w, h)


def _crossing(n) -> int:
    """Half the cyclic total variation of the 8-neighbourhood.

    1 at a stroke end, 2 along a stroke OR AT A CORNER, 3+ at a
    branch. The corner case is why this exists -- see G3.
    """
    return sum(abs(n[i] - n[(i + 1) % 8]) for i in range(8)) // 2


def _degrees(skel: InkMask):
    w, h = skel.width, skel.height
    d = {}
    for y in range(h):
        row = y * w
        for x in range(w):
            if not skel.data[row + x]:
                continue
            n = [1 if (0 <= y + dy < h and 0 <= x + dx < w
                       and skel.data[(y + dy) * w + (x + dx)]) else 0
                 for dy, dx in _N8]
            d[(x, y)] = (_crossing(n), sum(n))
    return d


def junctions(mask: InkMask, *, thin: bool = True) -> int:
    """G3. Skeleton pixels with three or more skeleton neighbours."""
    skel = skeleton(mask) if thin else mask
    return sum(1 for cn, _ in _degrees(skel).values() if cn >= 3)


def junction_sites(mask: InkMask, *, thin: bool = True) -> int:
    """G4. Those pixels clustered by 8-connectivity -- one Y is one
    site however many pixels the rasteriser gave its centre."""
    skel = skeleton(mask) if thin else mask
    pts = {p for p, (cn, _) in _degrees(skel).items() if cn >= 3}
    seen, sites = set(), 0
    for p in pts:
        if p in seen:
            continue
        sites += 1
        stack = [p]
        seen.add(p)
        while stack:
            x, y = stack.pop()
            for dy, dx in _N8:
                q = (x + dx, y + dy)
                if q in pts and q not in seen:
                    seen.add(q)
                    stack.append(q)
    return sites


def endpoints(mask: InkMask, *, thin: bool = True) -> int:
    """G6. Skeleton pixels with exactly one neighbour."""
    skel = skeleton(mask) if thin else mask
    return sum(1 for cn, deg in _degrees(skel).values()
               if cn == 1 or deg == 1)
