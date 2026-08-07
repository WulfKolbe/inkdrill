"""aggregate.py — moment aggregates per component.

CONTRACT (written before implementation; see docs/units.md U5)
=============================================================

What this unit produces
-----------------------
For each component of a U3 sweep: area, extents, and the raw moment sums

        A   Sx   Sy   Sxx   Syy   Sxy

accumulated from runs in CLOSED FORM -- a run of length n contributes its
whole span through the arithmetic-series identities, never a per-pixel
loop. From those: centroid, central moments, the principal axis as a unit
vector, and elongation.

Integer accumulation is a contract, not an implementation detail
----------------------------------------------------------------
Every raw sum is a Python int and no float enters until a ratio is taken.

This is what makes G2 true. docs/units.md assumption 4 warned that
axis-invariant moments "do not follow automatically, since the
accumulation order differs" -- and it is right that it does not follow
from U2's pixel-set agreement alone. It follows from EXACTNESS: a row
sweep and a column sweep visit the same pixels grouped into different
runs and summed in a different order, so the result is order-independent
precisely because integer addition is associative and exact. In floating
point the same code would drift, and G2 would hold only approximately.

Measured before implementation: 400/400 random masks agree on whole-mask
moments and 300/300 agree per component, exactly.

Pixel geometry
--------------
Pixel (i, j) covers `[i, i+1) x [j, j+1)` with centre `(i+.5, j+.5)`, per
the package convention. The raw sums are over integer INDICES; the
centroid adds the half-pixel so it lands at the centre of mass of the
covered area rather than half a pixel up and to the left. Central moments
are unaffected -- a constant shift cancels -- which is why they can be
computed from the index sums directly.

No angles
---------
`principal_axis` returns a UNIT VECTOR, never an angle, per the
convention locked in U1-U3. `space.angle_deg_ccw` and
`space.angle_deg_screen` are the only sanctioned producers of a number in
degrees, and each names its convention. A vector cannot disagree with
itself about sign.

The sign of an eigenvector is arbitrary, so it is canonicalised: `x > 0`,
or `x == 0 and y > 0`. Without that, two runs over the same shape could
return opposite vectors and every downstream comparison would be a
coin flip.

The lambda-2 floor
------------------
A 1-pixel-wide stroke has ZERO variance across its width, so the smaller
eigenvalue is exactly 0 and elongation would be infinite. The floor is
`1/12`, the variance of a unit pixel about its own centre -- the amount
of spread a single pixel already has by virtue of covering an area rather
than being a point.

It engages exactly at 1-px width and not at 2: a 2-px-wide stroke has
variance 1/4 > 1/12. That boundary is under test, because a floor that
engaged at 2 px would quietly flatten every thin stroke in the corpus.

Guarantees
----------
G1  raw moments accumulate in exact integer arithmetic, in closed form
    over runs; no float enters before a ratio is taken
G2  row-sweep and col-sweep moments are IDENTICAL, per component and in
    total -- docs/units.md assumption 4
G3  the centroid uses pixel centres, `Sx/A + 0.5`
G4  central moments are exactly translation invariant
G5  `principal_axis` is a unit vector with a canonical sign, never an
    angle
G6  the lambda-2 floor of 1/12 engages exactly at 1-px width, so
    elongation is finite for every non-empty component
G7  moments ADD: the aggregate of disjoint components equals the sum of
    their aggregates. This is what U7 band stitching relies on, and it is
    exact because the sums are integers

Non-guarantees (out of scope for U5)
------------------------------------
  * no holes or containment -- that is U6
  * no band stitching -- that is U7; G7 is the algebra it will use
  * no orientation of the shape as a whole beyond the principal axis
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from .raster import InkMask, Rect, Run, iter_runs
from .sweep import Capture, SweepResult, sweep

__all__ = ["Moments", "moments_of_runs", "moments_of_mask",
           "moments_per_component", "PIXEL_VARIANCE"]

# The variance of a unit pixel about its own centre: the integral of x^2
# over [-1/2, 1/2]. The floor on the smaller eigenvalue.
PIXEL_VARIANCE = 1.0 / 12.0


def _sum_i(lo: int, hi: int) -> int:
    """sum(i for i in lo..hi), inclusive, in closed form."""
    return (hi * (hi + 1)) // 2 - ((lo - 1) * lo) // 2


def _sum_ii(lo: int, hi: int) -> int:
    """sum(i*i for i in lo..hi), inclusive, in closed form."""
    return ((hi * (hi + 1) * (2 * hi + 1)) // 6
            - ((lo - 1) * lo * (2 * lo - 1)) // 6)


@dataclass(frozen=True, slots=True)
class Moments:
    """Raw moment sums over integer pixel indices, plus extents.

    Every field is an exact integer. Derived quantities are properties so
    that nothing float is ever stored and later summed.
    """
    area: int
    sx: int
    sy: int
    sxx: int
    syy: int
    sxy: int
    x0: int
    y0: int
    x1: int
    y1: int

    # ---- extents -------------------------------------------------------

    @property
    def bbox(self) -> Rect:
        """Half-open, per the package's Rect convention."""
        return Rect(self.x0, self.y0, self.x1 + 1, self.y1 + 1)

    @property
    def width(self) -> int:
        return self.x1 - self.x0 + 1

    @property
    def height(self) -> int:
        return self.y1 - self.y0 + 1

    # ---- first order ---------------------------------------------------

    @property
    def centroid(self) -> tuple[float, float]:
        """G3: pixel centres, not indices."""
        if self.area == 0:
            raise ValueError("centroid of an empty component")
        return (self.sx / self.area + 0.5, self.sy / self.area + 0.5)

    # ---- second order --------------------------------------------------

    @property
    def central(self) -> tuple[float, float, float]:
        """(mu20, mu02, mu11). G4: a constant shift cancels, so these are
        the same whether computed from indices or from centres."""
        if self.area == 0:
            raise ValueError("central moments of an empty component")
        a = self.area
        mx = self.sx / a
        my = self.sy / a
        return (self.sxx / a - mx * mx,
                self.syy / a - my * my,
                self.sxy / a - mx * my)

    @property
    def eigenvalues(self) -> tuple[float, float]:
        """(lambda1, lambda2) with lambda1 >= lambda2, lambda2 floored at
        PIXEL_VARIANCE (G6)."""
        mu20, mu02, mu11 = self.central
        half = (mu20 + mu02) / 2.0
        diff = (mu20 - mu02) / 2.0
        root = math.sqrt(diff * diff + mu11 * mu11)
        l1 = half + root
        l2 = half - root
        return (max(l1, PIXEL_VARIANCE), max(l2, PIXEL_VARIANCE))

    @property
    def principal_axis(self) -> tuple[float, float]:
        """G5: a unit vector along the major axis, canonical sign.

        Never an angle. Feed it to `space.angle_deg_screen` (y-down, image
        space) or `space.angle_deg_ccw` (y-up) when a number in degrees is
        genuinely wanted; each names its convention.
        """
        mu20, mu02, mu11 = self.central
        l1, _ = self.eigenvalues
        # (mu20 - l1) * x + mu11 * y = 0  ->  direction (mu11, l1 - mu20)
        vx, vy = mu11, l1 - mu20
        if abs(vx) < 1e-12 and abs(vy) < 1e-12:
            # isotropic: no major axis is distinguishable
            vx, vy = 1.0, 0.0
        n = math.hypot(vx, vy)
        vx, vy = vx / n, vy / n
        if vx < 0 or (vx == 0.0 and vy < 0):
            vx, vy = -vx, -vy
        return (vx, vy)

    @property
    def elongation(self) -> float:
        """sqrt(lambda1 / lambda2), finite for every non-empty component
        thanks to the floor (G6)."""
        l1, l2 = self.eigenvalues
        return math.sqrt(l1 / l2)

    # ---- algebra -------------------------------------------------------

    def __add__(self, other: "Moments") -> "Moments":
        """G7: aggregates add. Exact, because the sums are integers.

        This is the algebra U7 stitches bands with. It assumes the two
        components are disjoint -- adding a component to itself doubles
        its area, which is arithmetic working as specified, not a bug.
        """
        if not isinstance(other, Moments):
            return NotImplemented
        if self.area == 0:
            return other
        if other.area == 0:
            return self
        return Moments(
            self.area + other.area,
            self.sx + other.sx, self.sy + other.sy,
            self.sxx + other.sxx, self.syy + other.syy,
            self.sxy + other.sxy,
            min(self.x0, other.x0), min(self.y0, other.y0),
            max(self.x1, other.x1), max(self.y1, other.y1),
        )

    def translated(self, dx: int, dy: int) -> "Moments":
        """Exact integer translation, for testing G4 without resampling."""
        a = self.area
        return Moments(
            a,
            self.sx + a * dx,
            self.sy + a * dy,
            self.sxx + 2 * dx * self.sx + a * dx * dx,
            self.syy + 2 * dy * self.sy + a * dy * dy,
            self.sxy + dx * self.sy + dy * self.sx + a * dx * dy,
            self.x0 + dx, self.y0 + dy, self.x1 + dx, self.y1 + dy,
        )


_EMPTY = Moments(0, 0, 0, 0, 0, 0, 0, 0, -1, -1)


def _accumulate(runs: Iterable[Run], axis: str) -> Moments:
    a = sx = sy = sxx = syy = sxy = 0
    x0 = y0 = None
    x1 = y1 = None
    for r in runs:
        n = r.hi - r.lo + 1
        s1 = _sum_i(r.lo, r.hi)
        s2 = _sum_ii(r.lo, r.hi)
        if axis == "row":
            y = r.line
            a += n
            sx += s1
            sy += n * y
            sxx += s2
            syy += n * y * y
            sxy += y * s1
            rx0, rx1, ry0, ry1 = r.lo, r.hi, y, y
        else:
            x = r.line
            a += n
            sx += n * x
            sy += s1
            sxx += n * x * x
            syy += s2
            sxy += x * s1
            rx0, rx1, ry0, ry1 = x, x, r.lo, r.hi
        x0 = rx0 if x0 is None else min(x0, rx0)
        x1 = rx1 if x1 is None else max(x1, rx1)
        y0 = ry0 if y0 is None else min(y0, ry0)
        y1 = ry1 if y1 is None else max(y1, ry1)
    if a == 0:
        return _EMPTY
    return Moments(a, sx, sy, sxx, syy, sxy, x0, y0, x1, y1)


def moments_of_runs(runs: Iterable[Run], axis: str) -> Moments:
    """Accumulate moments over an arbitrary run iterable."""
    from .raster import AXES, InvalidAxis
    if axis not in AXES:
        raise InvalidAxis(axis)
    return _accumulate(runs, axis)


def moments_of_mask(mask: InkMask, axis: str = "row") -> Moments:
    """Whole-mask moments. G2: the result does not depend on `axis`."""
    return moments_of_runs(iter_runs(mask, axis), axis)


def moments_per_component(result: SweepResult) -> dict[int, Moments]:
    """Moments keyed by component root.

    Needs `Capture.GRAPH` only for the node list; the runs themselves are
    what is accumulated, so this works at any capture level that retains
    nodes.
    """
    by_id = {n.id: n for n in result.nodes}
    out: dict[int, Moments] = {}
    for comp in result.components:
        runs = (by_id[i].as_run() for i in comp.nodes)
        out[comp.root] = _accumulate(runs, result.axis)
    return out


def component_moments(mask: InkMask, axis: str = "row", *,
                      conn: int = 8) -> list[Moments]:
    """Convenience: mask -> per-component moments, sorted for comparison
    across axes (G2)."""
    res = sweep(mask, axis=axis, conn=conn, capture=Capture.GRAPH)
    vals = list(moments_per_component(res).values())
    return sorted(vals, key=lambda mo: (mo.area, mo.sx, mo.sy,
                                        mo.sxx, mo.syy, mo.sxy))
