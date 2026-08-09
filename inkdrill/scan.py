"""scan.py -- contours to an ink mask.

CONTRACT (written before implementation; see docs/units.md U9)
=============================================================

The last third of U9's rasterizer. `type1.py` gets charstring bytes from
a font, `charstring.py` runs them into closed contours in font units,
and this converts those contours to an `InkMask` at a chosen pixel size.
With this, `font -> glyph bitmap` is complete and maths templates are
reachable.

The oracle closes a loop rather than checking a number
------------------------------------------------------
Every other unit here needed an oracle invented for it. This one has one
already, and it is the strongest in the project: **`charstring` and
`sweep` must agree about the same glyph without sharing any code.**

    charstring says `o` has 2 contours
    scan + sweep + cycle rank must say 1 component with 1 hole

Those are two independent computations -- one from Bezier control points
in font units, one from run adjacency on a bitmap -- and they agree only
if the fill rule, the winding direction, the y-flip and the sampling
convention are all right. A sign error in any of them breaks it. That is
why `raster`'s conventions are followed exactly rather than
approximately.

Sampling, and why it is the project's convention and not a new one
------------------------------------------------------------------
`raster` fixes pixel (i, j) as covering `[i, i+1) x [j, j+1)` with
centre `(i+.5, j+.5)`. So a scanline is taken at `y = j + 0.5` and a
span is filled from the crossing at `x` to the crossing at `x'` by the
same rule -- a pixel is ink when its CENTRE is inside the outline. No
anti-aliasing, because the package's mask is `0xFF`/`0x00` package-wide
and a grey pixel has nowhere to live.

Non-zero winding, because Type 1 says so
----------------------------------------
Type 1 fills by the non-zero winding rule, not even-odd. For a letter
`o` drawn with an outer contour one way and a counter the other, both
rules agree. For a glyph whose contours wind the same way -- which
happens in real fonts -- they do not, and even-odd punches a hole that
should not be there. The direction of each crossing is therefore
tracked, not just its position.

Guarantees
----------
G1  pure -- contours in, `InkMask` out; no font access, no file access
G2  the mask uses `0xFF` ink / `0x00` background, package-wide (`raster`)
G3  a pixel is ink iff its CENTRE lies inside the outline under the
    non-zero winding rule
G4  the y axis is flipped exactly once: font units are y-up, masks are
    y-down, and `bounds` are honoured so a glyph is never clipped
G5  curves are flattened to a stated tolerance in DEVICE pixels, so the
    same glyph at 20 px and at 2000 px is equally smooth relative to
    its size
G6  rasterizing at size 0, or an empty glyph, returns an empty mask
    rather than raising -- `.notdef` and `space` are 3,287 of 119,800
    real glyphs and are not errors
G7  the result satisfies the topological identity above: contour count
    from `charstring` and component/hole counts from `sweep` agree
"""

from __future__ import annotations

from .raster import BG, INK, InkMask

__all__ = ["flatten", "rasterize", "render"]

# Flatness tolerance in device pixels (G5). A quarter pixel is below the
# sampling grid, so tightening it cannot change which pixels are ink.
TOLERANCE = 0.25
MAX_SPLITS = 16


def _flatten_cubic(p0, p1, p2, p3, out, depth=0):
    """Adaptive subdivision to `TOLERANCE`, appending on-curve points.

    Flatness is measured as the control points' distance from the chord,
    which bounds the true deviation and needs no square roots.
    """
    d1 = abs(p1[0] - p0[0] - (p3[0] - p0[0]) / 3) + \
        abs(p1[1] - p0[1] - (p3[1] - p0[1]) / 3)
    d2 = abs(p2[0] - p3[0] + (p3[0] - p0[0]) / 3) + \
        abs(p2[1] - p3[1] + (p3[1] - p0[1]) / 3)
    if depth >= MAX_SPLITS or d1 + d2 <= TOLERANCE:
        out.append(p3)
        return
    # de Casteljau at t = 1/2
    ab = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
    bc = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
    cd = ((p2[0] + p3[0]) / 2, (p2[1] + p3[1]) / 2)
    abc = ((ab[0] + bc[0]) / 2, (ab[1] + bc[1]) / 2)
    bcd = ((bc[0] + cd[0]) / 2, (bc[1] + cd[1]) / 2)
    mid = ((abc[0] + bcd[0]) / 2, (abc[1] + bcd[1]) / 2)
    _flatten_cubic(p0, ab, abc, mid, out, depth + 1)
    _flatten_cubic(mid, bcd, cd, p3, out, depth + 1)


def flatten(contours, transform):
    """Contours of `Segment` to polygons in device space (G4, G5).

    `transform` maps a font-unit point to a device point and is where
    the single y flip lives -- doing it here rather than per segment is
    what makes "exactly once" checkable.
    """
    polys = []
    for c in contours:
        if len(c) < 2:
            continue
        pts = [transform(c[0].x, c[0].y)]
        for seg in c[1:]:
            end = transform(seg.x, seg.y)
            if seg.c1 is None:
                pts.append(end)
            else:
                _flatten_cubic(pts[-1], transform(*seg.c1),
                               transform(*seg.c2), end, pts)
        polys.append(pts)
    return polys


def rasterize(polys, width, height):
    """Fill device-space polygons into an `InkMask` (G2, G3).

    Non-zero winding: each edge crossing a scanline contributes +1 or -1
    by direction, and a span is ink while the running total is non-zero.
    """
    if width <= 0 or height <= 0:
        return InkMask(b"", max(width, 0), max(height, 0))
    buf = bytearray(width * height)
    edges = []
    for pts in polys:
        n = len(pts)
        for i in range(n):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % n]
            if y0 != y1:
                edges.append((y0, y1, x0, x1))
    if not edges:
        return InkMask(bytes(buf), width, height)
    row = b"\xff"
    for j in range(height):
        yc = j + 0.5
        xs = []
        for y0, y1, x0, x1 in edges:
            if (y0 <= yc < y1) or (y1 <= yc < y0):
                t = (yc - y0) / (y1 - y0)
                xs.append((x0 + t * (x1 - x0), 1 if y1 > y0 else -1))
        if not xs:
            continue
        xs.sort()
        wind = 0
        base = j * width
        start = 0.0
        for x, d in xs:
            if wind == 0:
                start = x
            wind += d
            if wind == 0:
                # Centre sampling: the first pixel whose centre is >=
                # start, up to the last whose centre is < x.
                a = int(start + 0.5)
                b = int(x + 0.5)
                if b > a:
                    a = max(a, 0)
                    b = min(b, width)
                    if b > a:
                        buf[base + a:base + b] = row * (b - a)
    return InkMask(bytes(buf), width, height)


def render(glyph, units_per_em, size_px, *, pad=1):
    """A glyph as an `InkMask` at `size_px` pixels per em (G4, G6).

    Returns `(mask, origin)` where `origin` is the device-space position
    of the glyph's font-unit (0, 0), so a caller can place the bitmap on
    a baseline without re-deriving it.
    """
    if size_px <= 0 or glyph.is_empty:
        return InkMask(b"", 0, 0), (0.0, 0.0)
    scale = size_px / float(units_per_em)
    x0, y0, x1, y1 = glyph.bounds()
    # Device box, y flipped: font-space y1 (top) becomes the smaller
    # device y. G4 -- this is the ONLY place the flip happens.
    dx = -x0 * scale + pad
    dy = y1 * scale + pad

    def to_device(fx, fy):
        return (fx * scale + dx, -fy * scale + dy)

    w = int((x1 - x0) * scale + 0.5) + 2 * pad
    h = int((y1 - y0) * scale + 0.5) + 2 * pad
    if w <= 0 or h <= 0:
        return InkMask(b"", 0, 0), (0.0, 0.0)
    return rasterize(flatten(glyph.contours, to_device), w, h), (dx, dy)
