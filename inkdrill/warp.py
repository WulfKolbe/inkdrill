"""warp.py -- move ink under a transform, two ways, and compare them.

CONTRACT (written before implementation; see docs/units.md S4)
=============================================================

The thesis this exists to test: **a transform applied to the INK
preserves topology, and the same transform applied to the PIXELS does
not.** Everything downstream of a dewarp depends on which is true, and
until now it has been argued rather than measured.

The two paths, and why the comparison is fair
---------------------------------------------
    transport   map each RUN's endpoints, redraw the run
    resample    interpolate the GREY, then binarise

They differ in *where* binarisation sits -- before transport, after
resample -- and that is the real-world difference rather than a
handicap. A resampling pipeline binarises last because it must: it has
continuous tone to carry through the interpolation. A transport pipeline
binarises first because it must: it moves runs, and a run only exists
after a threshold.

**Neither path touches an undistorted reference.** Both operate on the
same mask and the same transform, so a threshold that is wrong for the
page is wrong for both, identically. That is what makes this runnable on
input where the absolute topology is unstable -- the instability makes
the count arbitrary, not the comparison.

What is measured, and what is not
---------------------------------
`compare()` reports each path's topology beside the input's. The claim
it can support is an **ordering** -- transport nearer the input than
resample -- and not "the count is preserved", which no transform of a
discrete grid guarantees.

**It does not measure whether the transform is CORRECT.** A crude phi
that dewarps badly still answers the question, because both paths get
the same crude phi. Separating "our warp model is accurate" from "any
warp is safer applied to ink than to pixels" is the whole reason a
crude phi is sufficient here, and the second is the claim.

KNOWN DEFECT: `transport` hatches solid regions
-----------------------------------------------
Measured on real DocReal ink, 900x900 crops at the valley threshold,
7 degree rotation:

    id   source        transport       resample
     1   (436, 180)    (408, 2238)     (337, 188)
     3   (317, 1878)   (311, 22674)    (276, 2174)
     6   (1640, 7239)  (1319, 36964)   (1264, 6386)

**Transport loses 0 of 6**, and the cycle counts say why: it multiplies
holes by an order of magnitude while the control tracks the source.

The cause is in `transport` and not in the thesis. Each run is drawn as
an INDEPENDENT line, so two runs that were adjacent before the rotation
land as two 1-pixel lines that no longer touch. A solid region becomes a
**hatched** one, and every gap between neighbouring lines is a new hole.

G2 is still true and was never enough: connectivity ALONG a run is
preserved, and connectivity BETWEEN runs is what a solid region is made
of. The synthetic fixtures hid it because a thin ring has almost no
adjacent runs; real text is nearly all adjacent runs.

Fixing it means transporting the run as an area -- a quadrilateral
between consecutive scan positions -- rather than as a centre line. The
thesis is untested until then; this measurement says nothing about
resampling and everything about this module.

Guarantees
----------
G1  pure -- a mask and a transform in, masks out; no file access
G2  `transport` moves runs, so a run of length n maps to a drawn line
    and never to n independent samples; connectivity along a run cannot
    be lost to sampling
G3  `resample` is the control and is deliberately the naive thing a
    resampling pipeline does -- sample the source, then threshold
G4  both paths receive the SAME transform and the same output extent,
    so nothing but the method differs
G5  the identity transform is a fixed point of `transport`: the mask
    comes back unchanged, which is the check that the mapping is not
    quietly resampling
G6  `compare` reports both topologies and the input's; it draws no
    conclusion, because the ordering is the finding and a caller with a
    population should be the one to state it
"""

from __future__ import annotations

from dataclasses import dataclass

from .raster import INK, InkMask, iter_runs
from .qc import topology_of

__all__ = ["Comparison", "transport", "resample", "compare", "corner_affine"]


def corner_affine(src, dst):
    """A crude phi: the affine that best maps four source corners to
    four destination corners, least squares.

    Deliberately crude. The bench asks whether transport beats
    resampling, and both paths get whatever this returns -- an accurate
    field would change both answers together and would not change their
    ORDER, which is what is being measured.
    """
    if len(src) != len(dst) or len(src) < 3:
        raise ValueError("need at least three matched point pairs")
    n = len(src)
    sx = sum(p[0] for p in src) / n
    sy = sum(p[1] for p in src) / n
    dx = sum(p[0] for p in dst) / n
    dy = sum(p[1] for p in dst) / n
    sxx = sum((p[0] - sx) ** 2 for p in src)
    syy = sum((p[1] - sy) ** 2 for p in src)
    if sxx <= 0 or syy <= 0:
        raise ValueError("source points are degenerate")
    a = sum((s[0] - sx) * (d[0] - dx) for s, d in zip(src, dst)) / sxx
    b = sum((s[1] - sy) * (d[0] - dx) for s, d in zip(src, dst)) / syy
    c = sum((s[0] - sx) * (d[1] - dy) for s, d in zip(src, dst)) / sxx
    d_ = sum((s[1] - sy) * (d[1] - dy) for s, d in zip(src, dst)) / syy
    return (a, b, c, d_, dx - a * sx - b * sy, dy - c * sx - d_ * sy)


def _apply(m, x, y):
    a, b, c, d, e, f = m
    return (a * x + b * y + e, c * x + d * y + f)


def _draw(buf, w, h, x0, y0, x1, y1):
    """Bresenham-ish line, so a transported run stays connected (G2)."""
    x0i, y0i, x1i, y1i = round(x0), round(y0), round(x1), round(y1)
    dx = abs(x1i - x0i)
    dy = abs(y1i - y0i)
    sx = 1 if x0i < x1i else -1
    sy = 1 if y0i < y1i else -1
    err = dx - dy
    while True:
        if 0 <= x0i < w and 0 <= y0i < h:
            buf[y0i * w + x0i] = INK
        if x0i == x1i and y0i == y1i:
            return
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0i += sx
        if e2 < dx:
            err += dx
            y0i += sy


def transport(mask: InkMask, m, *, width=None, height=None,
              axis: str = "row") -> InkMask:
    """Move the INK: map each run's endpoints and redraw it (G2, G5).

    A run is a connected segment before the map and is drawn as a
    connected segment after it, so no amount of sampling can break it
    into pieces. That is the property the whole thesis rests on.
    """
    w = mask.width if width is None else width
    h = mask.height if height is None else height
    buf = bytearray(w * h)
    for r in iter_runs(mask, axis):
        if axis == "row":
            p0, p1 = (r.lo, r.line), (r.hi, r.line)
        else:
            p0, p1 = (r.line, r.lo), (r.line, r.hi)
        a = _apply(m, p0[0], p0[1])
        b = _apply(m, p1[0], p1[1])
        _draw(buf, w, h, a[0], a[1], b[0], b[1])
    return InkMask(bytes(buf), w, h)


def resample(mask: InkMask, m, *, width=None, height=None,
             threshold: float = 0.5) -> InkMask:
    """The CONTROL: sample the source through the inverse map (G3).

    Deliberately the naive thing a resampling pipeline does -- for each
    destination pixel, look up where it came from and take the value
    there. Bilinear, then threshold, which is where thin strokes are
    lost.
    """
    w = mask.width if width is None else width
    h = mask.height if height is None else height
    a, b, c, d, e, f = m
    det = a * d - b * c
    if det == 0:
        raise ValueError("transform is singular; it cannot be inverted")
    ia, ib = d / det, -b / det
    ic, id_ = -c / det, a / det
    ie = -(ia * e + ib * f)
    if_ = -(ic * e + id_ * f)
    src, sw, sh = mask.data, mask.width, mask.height
    buf = bytearray(w * h)
    cut = threshold * 255.0
    for y in range(h):
        row = y * w
        for x in range(w):
            u = ia * x + ib * y + ie
            v = ic * x + id_ * y + if_
            x0, y0 = int(u), int(v)
            if not (0 <= x0 < sw - 1 and 0 <= y0 < sh - 1):
                continue
            fx, fy = u - x0, v - y0
            base = y0 * sw + x0
            val = (src[base] * (1 - fx) * (1 - fy)
                   + src[base + 1] * fx * (1 - fy)
                   + src[base + sw] * (1 - fx) * fy
                   + src[base + sw + 1] * fx * fy)
            if val >= cut:
                buf[row + x] = INK
    return InkMask(bytes(buf), w, h)


@dataclass(frozen=True, slots=True)
class Comparison:
    """Three topologies. No verdict (G6)."""
    source: tuple[int, int]
    transported: tuple[int, int]
    resampled: tuple[int, int]

    def _drift(self, got):
        out = []
        for a, b in zip(self.source, got):
            out.append(0.0 if a == 0 and b == 0
                       else abs(a - b) / max(abs(a), abs(b), 1))
        return tuple(out)

    @property
    def transport_drift(self):
        return self._drift(self.transported)

    @property
    def resample_drift(self):
        return self._drift(self.resampled)

    @property
    def transport_is_nearer(self) -> bool:
        """The ORDERING, which is the claim this bench can support."""
        return max(self.transport_drift) < max(self.resample_drift)


def compare(mask: InkMask, m, *, width=None, height=None) -> Comparison:
    """Both paths, one transform, one input (G4, G6)."""
    return Comparison(
        source=topology_of(mask),
        transported=topology_of(transport(mask, m, width=width,
                                          height=height)),
        resampled=topology_of(resample(mask, m, width=width, height=height)))
