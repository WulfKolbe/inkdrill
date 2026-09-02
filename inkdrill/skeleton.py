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
    Zhang-Suen conditions and a junction by a neighbour count, so
    there is no constant here that a dpi change silently retunes.

    THAT IS NOT THE SAME AS THE COUNT BEING INVARIANT, and the first
    wording of this guarantee said "nothing that moves with dpi",
    which reads as the second. It is false: 497 measured the junction
    count moving with glyph size on 25% of 104 rendered glyphs, and
    496 measured it on real pages. A 2-px stroke thins to a staircase
    and the staircase has branches. The guarantee is about the
    DEFINITION carrying no tunable; the VALUE is a measurement with a
    known instability, and a caller comparing two counts must know
    which of the two it is relying on.
G6  a stroke END has one neighbour and a stroke INTERIOR has two, so
    `>= 3` is the whole definition of a branch point. Ends are
    reported separately by `endpoints` because the pair together
    characterises a shape better than either alone -- an L has two
    ends and no junction, an L-slash has three ends and one junction.
G7  `parts(mask)` splits a mask into its 8-connected components and
    reports each one's box and counts. A CROP OF A PAGE IS NOT A
    GLYPH -- it holds a whole line -- so every caller that wants a
    per-glyph reading out of real ink has to split first, and doing
    it here keeps that one step beside the count it feeds rather
    than in each caller. It reports; it names nothing and classifies
    nothing, because naming a component needs symbol identity, which
    this project does not have.
"""
from __future__ import annotations

from typing import NamedTuple

from .raster import InkMask

__all__ = ["skeleton", "junctions", "junction_sites", "endpoints",
           "Part", "parts"]

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


class Part(NamedTuple):
    """One 8-connected component of a mask, with its shape counts.

    `x0, y0, x1, y1` are IMAGE-space and inclusive, in the coordinates
    of the mask handed to `parts`.
    """
    x0: int
    y0: int
    x1: int
    y1: int
    ink: int
    holes: int
    junctions: int
    ends: int

    @property
    def width(self) -> int:
        return self.x1 - self.x0 + 1

    @property
    def height(self) -> int:
        return self.y1 - self.y0 + 1


def parts(mask: InkMask, *, min_ink: int = 1) -> list[Part]:
    """G7. The mask's 8-connected components, left to right.

    `min_ink` drops specks below a pixel count; the default keeps
    everything, because what counts as a speck depends on the dpi the
    caller rendered at and this module is not told it.

    Foreground connectivity is 8 and background 4, package-wide, so
    the holes here are the same holes `nest` and `sweep` report.
    """
    from .nest import ink_only
    from .sweep import sweep as _sweep

    res = _sweep(mask, conn=8)
    node = {n.id: n for n in res.nodes}
    out = []
    for comp in res.components:
        ns = [node[i] for i in comp.nodes]
        # `image_span` is the sanctioned converter; for the row axis
        # this sweep uses, lo..hi is x and line is y, but going
        # through it is what keeps that true if the axis ever moves.
        spans = [n.as_run().image_span("row") for n in ns]
        x0 = min(s[0] for s in spans)
        y0 = min(s[1] for s in spans)
        x1 = max(s[2] for s in spans)
        y1 = max(s[3] for s in spans)
        w = x1 - x0 + 1
        buf = bytearray(w * (y1 - y0 + 1))
        for (a, b, c, _d) in spans:
            off = (b - y0) * w
            for x in range(a, c + 1):
                buf[off + x - x0] = 0xFF
        sub = InkMask(bytes(buf), w, y1 - y0 + 1)
        ink = sub.data.count(0xFF)
        if ink < min_ink:
            continue
        out.append(Part(x0, y0, x1, y1, ink, sum(ink_only(sub).cycles),
                        junction_sites(sub), endpoints(sub)))
    out.sort(key=lambda p: (p.x0, p.y0))
    return out
