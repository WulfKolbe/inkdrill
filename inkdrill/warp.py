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

FIXED: `transport` used to hatch solid regions
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

The fix is here: a run is transported as its pixel AREA -- the
quadrilateral `[lo, hi+1) x [line, line+1)` mapped and scanline-filled
-- rather than as a centre line. Neighbouring runs then still touch
after the map.

Guarantees
----------
G1  pure -- a mask and a transform in, masks out; no file access
G2  `transport` moves each run as an AREA, so connectivity BETWEEN
    adjacent runs survives the map as well as connectivity along one.
    The weaker form -- along a run only -- was true, insufficient, and
    the reason solid regions came back hatched
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


def _fill_quad(buf, w, h, pts):
    """Scanline-fill a convex quadrilateral (G2).

    A run is an AREA -- the pixels `[lo, hi+1) x [line, line+1)` -- and
    transporting it as a centre line is what hatched solid regions and
    multiplied holes by an order of magnitude on real ink. Filling the
    mapped quadrilateral keeps neighbouring runs touching, which is
    what a solid region is made of.
    """
    ys = [p[1] for p in pts]
    y0 = max(0, int(min(ys)))
    y1 = min(h - 1, int(max(ys)) + 1)
    n = len(pts)
    for y in range(y0, y1 + 1):
        yc = y + 0.5
        xs = []
        for i in range(n):
            (ax, ay), (bx, by) = pts[i], pts[(i + 1) % n]
            if (ay <= yc < by) or (by <= yc < ay):
                xs.append(ax + (yc - ay) * (bx - ax) / (by - ay))
        if len(xs) < 2:
            continue
        lo, hi = min(xs), max(xs)
        a = max(0, int(lo + 0.5))
        b = min(w, int(hi + 0.5))
        if b > a:
            buf[y * w + a:y * w + b] = b"\xff" * (b - a)


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
        # The run's PIXEL AREA, not its centre line: a row run covers
        # [lo, hi+1) x [line, line+1).
        if axis == "row":
            box = ((r.lo, r.line), (r.hi + 1, r.line),
                   (r.hi + 1, r.line + 1), (r.lo, r.line + 1))
        else:
            box = ((r.line, r.lo), (r.line + 1, r.lo),
                   (r.line + 1, r.hi + 1), (r.line, r.hi + 1))
        _fill_quad(buf, w, h, [_apply(m, x, y) for x, y in box])
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
