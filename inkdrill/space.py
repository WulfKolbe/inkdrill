"""space.py — affine transforms, named coordinate spaces, CTM decomposition.

CONTRACT (written before implementation; see docs/units.md U1)
=============================================================

Matrix convention
-----------------
`Affine(a, b, c, d, e, f)` is the PostScript/PDF matrix, ROW-VECTOR
convention, identical to the operand order of the PDF `cm` and `Tm`
operators:

        | a  b  0 |
        | c  d  0 |          [x' y' 1] = [x y 1] x M
        | e  f  1 |

    x' = a*x + c*y + e
    y' = b*x + d*y + f

Consequences that the rest of the package relies on:
  * row 1 (a, b) is the IMAGE OF THE X BASIS VECTOR
  * row 2 (c, d) is the IMAGE OF THE Y BASIS VECTOR
  * (e, f) is the image of the origin
  * `m1.then(m2)` applies m1 first, then m2 == the PDF concatenation order

No angles in the core
---------------------
The core NEVER stores an angle. Directions are unit vectors. Angles exist
only at the reporting boundary via `angle_deg_ccw` / `angle_deg_screen`,
each of which names its convention in its own docstring. This is a
deliberate response to sign-convention drift: a vector cannot silently
disagree with itself about which way is positive.

Pixel geometry
--------------
Raster pixel (i, j) covers the half-open unit square [i, i+1) x [j, j+1).
Its CENTRE is (i + 0.5, j + 0.5). Any transform between a pixel space and
a continuous space must account for this; `pixel_centre` is the only
sanctioned way to obtain it.

Guarantees
----------
G1  identity().then(m) == m.then(identity()) == m               (exact)
G2  m.then(m.inverse()) == identity()                           (to 1e-9)
G3  (m1.then(m2)).then(m3) == m1.then(m2.then(m3))              (to 1e-9)
G4  decompose(m).recompose() == m                               (to 1e-9)
G5  det < 0  <=>  decompose(m).flip is True  <=>  orientation reversed
G6  SpaceGraph.transform(A, B) == inverse of transform(B, A)    (to 1e-9)
G7  SpaceGraph.transform(A, A) == identity()                    (exact)

Non-guarantees (explicitly out of scope for U1)
-----------------------------------------------
  * degenerate matrices (det == 0) raise `DegenerateAffine`; they are not
    silently regularised
  * no perspective / projective transforms
  * SpaceGraph does not verify that two different paths between the same
    pair of spaces agree; see `check_consistency` (opt-in, O(paths))
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Iterable

__all__ = [
    "Affine", "Decomposition", "SpaceGraph",
    "DegenerateAffine", "SpaceNotFound", "NoPath",
    "angle_deg_ccw", "angle_deg_screen", "pixel_centre",
]

EPS = 1e-12


class DegenerateAffine(ValueError):
    """The 2x2 part has determinant 0: not invertible, not decomposable."""


class SpaceNotFound(KeyError):
    """A space name was used that has not been declared."""


class NoPath(LookupError):
    """No chain of declared edges connects two spaces."""


# --------------------------------------------------------------------------
# Affine
# --------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Affine:
    """A 2-D affine map in PDF row-vector order. Immutable."""

    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    e: float = 0.0
    f: float = 0.0

    # -- constructors ------------------------------------------------------

    @staticmethod
    def identity() -> "Affine":
        return Affine()

    @staticmethod
    def translate(tx: float, ty: float) -> "Affine":
        return Affine(1.0, 0.0, 0.0, 1.0, tx, ty)

    @staticmethod
    def scale(sx: float, sy: float | None = None) -> "Affine":
        if sy is None:
            sy = sx
        return Affine(sx, 0.0, 0.0, sy, 0.0, 0.0)

    @staticmethod
    def rotate(rad: float) -> "Affine":
        """Rotation taking the x basis vector to (cos, sin).

        In a y-UP space this is counter-clockwise; in a y-DOWN space the
        same matrix appears clockwise on screen. The matrix is the same
        object either way — which is precisely why the core stores no
        angle and the interpretation lives at the reporting boundary.
        """
        cs, sn = math.cos(rad), math.sin(rad)
        return Affine(cs, sn, -sn, cs, 0.0, 0.0)

    @staticmethod
    def skew_x(k: float) -> "Affine":
        """Shear the y basis vector towards +x by k (the italic shear)."""
        return Affine(1.0, 0.0, k, 1.0, 0.0, 0.0)

    @staticmethod
    def flip_y(height: float) -> "Affine":
        """y-UP <-> y-DOWN over a span of `height`. Self-inverse."""
        return Affine(1.0, 0.0, 0.0, -1.0, 0.0, height)

    # -- algebra -----------------------------------------------------------

    def then(self, other: "Affine") -> "Affine":
        """Apply self FIRST, then `other`. Matches PDF concatenation."""
        return Affine(
            self.a * other.a + self.b * other.c,
            self.a * other.b + self.b * other.d,
            self.c * other.a + self.d * other.c,
            self.c * other.b + self.d * other.d,
            self.e * other.a + self.f * other.c + other.e,
            self.e * other.b + self.f * other.d + other.f,
        )

    @staticmethod
    def chain(mats: Iterable["Affine"]) -> "Affine":
        """Compose in application order: chain([m1, m2, m3]) applies m1 first."""
        out = Affine.identity()
        for m in mats:
            out = out.then(m)
        return out

    @property
    def det(self) -> float:
        return self.a * self.d - self.b * self.c

    def inverse(self) -> "Affine":
        det = self.det
        if abs(det) < EPS:
            raise DegenerateAffine(f"determinant {det!r} is zero")
        ia, ib = self.d / det, -self.b / det
        ic, id_ = -self.c / det, self.a / det
        return Affine(ia, ib, ic, id_,
                      -(self.e * ia + self.f * ic),
                      -(self.e * ib + self.f * id_))

    # -- application -------------------------------------------------------

    def point(self, x: float, y: float) -> tuple[float, float]:
        """Map a POINT (translation applies)."""
        return (self.a * x + self.c * y + self.e,
                self.b * x + self.d * y + self.f)

    def vector(self, x: float, y: float) -> tuple[float, float]:
        """Map a VECTOR / direction (translation does NOT apply)."""
        return (self.a * x + self.c * y, self.b * x + self.d * y)

    @property
    def x_axis(self) -> tuple[float, float]:
        """Image of the x basis vector — the baseline direction for text."""
        return (self.a, self.b)

    @property
    def y_axis(self) -> tuple[float, float]:
        """Image of the y basis vector — the 'up' direction for text."""
        return (self.c, self.d)

    @property
    def origin(self) -> tuple[float, float]:
        return (self.e, self.f)

    def approx_eq(self, other: "Affine", tol: float = 1e-9) -> bool:
        return all(abs(u - v) <= tol for u, v in
                   zip((self.a, self.b, self.c, self.d, self.e, self.f),
                       (other.a, other.b, other.c, other.d, other.e, other.f)))

    # -- decomposition -----------------------------------------------------

    def decompose(self) -> "Decomposition":
        """Factor the 2x2 part as  M = S x R  with

               S = | sx   0 |        R = |  cos  sin |
                   | k   sy |            | -sin  cos |

        `sy` carries the sign of the determinant, so `sy < 0` means the map
        reverses orientation (mirrored text). `k` is the raw shear of the
        y basis vector towards the rotated x direction.
        """
        sx = math.hypot(self.a, self.b)
        if sx < EPS:
            raise DegenerateAffine("x basis vector has zero length")
        det = self.det
        if abs(det) < EPS:
            raise DegenerateAffine(f"determinant {det!r} is zero")
        ux, uy = self.a / sx, self.b / sx
        k = self.c * ux + self.d * uy
        sy = det / sx
        return Decomposition(sx=sx, sy=sy, shear=k, ux=ux, uy=uy,
                             tx=self.e, ty=self.f)


@dataclass(frozen=True, slots=True)
class Decomposition:
    """Result of `Affine.decompose`. See that docstring for the factoring."""

    sx: float          # scale along the rotated x axis; always > 0
    sy: float          # signed scale along the rotated y axis; < 0 == mirrored
    shear: float       # raw shear of the y basis towards the rotated x axis
    ux: float          # unit x-axis image, component 0
    uy: float          # unit x-axis image, component 1
    tx: float
    ty: float

    @property
    def flip(self) -> bool:
        """True when the map reverses orientation."""
        return self.sy < 0.0

    @property
    def italic_shear(self) -> float:
        """tan of the y-axis tilt. 0 for upright, > 0 for a typical italic."""
        return self.shear / abs(self.sy) if abs(self.sy) > EPS else 0.0

    def recompose(self) -> Affine:
        return Affine(
            self.sx * self.ux,
            self.sx * self.uy,
            self.shear * self.ux - self.sy * self.uy,
            self.shear * self.uy + self.sy * self.ux,
            self.tx, self.ty,
        )


# --------------------------------------------------------------------------
# Reporting boundary — the ONLY place angles are produced
# --------------------------------------------------------------------------

def angle_deg_ccw(v: tuple[float, float]) -> float:
    """Angle of `v` in degrees, counter-clockwise positive, in a y-UP frame.

    Range (-180, 180]. Use for PDF user space, glyph space, and anything
    else with y pointing up.
    """
    return math.degrees(math.atan2(v[1], v[0]))


def angle_deg_screen(v: tuple[float, float]) -> float:
    """Angle of `v` in degrees, counter-clockwise-ON-SCREEN positive, in a
    y-DOWN raster frame.

    Range (-180, 180]. This is the PIL/deskew convention: a page rotated
    anticlockwise as a reader sees it reports a positive value. Equal to
    `-angle_deg_ccw(v)` because the y axis is inverted.
    """
    return math.degrees(math.atan2(-v[1], v[0]))


def pixel_centre(i: int, j: int) -> tuple[float, float]:
    """Continuous coordinates of the centre of raster pixel (i, j)."""
    return (i + 0.5, j + 0.5)


# --------------------------------------------------------------------------
# SpaceGraph
# --------------------------------------------------------------------------

class SpaceGraph:
    """Named coordinate spaces connected by affine edges.

    Every geometric quantity in the package names the space it lives in;
    conversion is composition along a declared path, never a hand-written
    formula. Edges are stored one way and traversed both ways via
    `Affine.inverse`, so declaring `glyph -> text` also gives `text -> glyph`.
    """

    __slots__ = ("_edges", "_cache")

    def __init__(self) -> None:
        self._edges: dict[str, dict[str, Affine]] = {}
        self._cache: dict[tuple[str, str], Affine] = {}

    # -- construction ------------------------------------------------------

    def declare(self, name: str) -> None:
        self._edges.setdefault(name, {})

    def connect(self, src: str, dst: str, m: Affine) -> None:
        """Declare that a point in `src` maps to `dst` under `m`.

        Overwrites any existing edge between the same pair and invalidates
        the whole path cache (edges are declared during setup, not in the
        hot loop, so a full flush is the safe choice).
        """
        m.inverse()          # fail fast on a degenerate edge
        self.declare(src)
        self.declare(dst)
        self._edges[src][dst] = m
        self._edges[dst][src] = m.inverse()
        self._cache.clear()

    # -- query -------------------------------------------------------------

    @property
    def spaces(self) -> frozenset[str]:
        return frozenset(self._edges)

    def path(self, src: str, dst: str) -> list[str]:
        """Shortest chain of space names from `src` to `dst`, inclusive.

        Breadth-first over the declared edges, so the result is the path
        with the fewest compositions — which is also the one with the
        least accumulated floating-point error.
        """
        if src not in self._edges:
            raise SpaceNotFound(src)
        if dst not in self._edges:
            raise SpaceNotFound(dst)
        if src == dst:
            return [src]
        prev: dict[str, str] = {src: src}
        q = deque([src])
        while q:
            cur = q.popleft()
            for nxt in self._edges[cur]:
                if nxt in prev:
                    continue
                prev[nxt] = cur
                if nxt == dst:
                    out = [dst]
                    while out[-1] != src:
                        out.append(prev[out[-1]])
                    out.reverse()
                    return out
                q.append(nxt)
        raise NoPath(f"{src} -> {dst}")

    def transform(self, src: str, dst: str) -> Affine:
        """The composed map from `src` to `dst`. Cached per pair."""
        key = (src, dst)
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        names = self.path(src, dst)
        out = Affine.identity()
        for u, v in zip(names, names[1:]):
            out = out.then(self._edges[u][v])
        self._cache[key] = out
        return out

    def point(self, src: str, dst: str, x: float, y: float) -> tuple[float, float]:
        return self.transform(src, dst).point(x, y)

    # -- diagnostics -------------------------------------------------------

    def check_consistency(self, src: str, dst: str, tol: float = 1e-6) -> list[list[str]]:
        """Return every simple path `src`->`dst` whose composition disagrees
        with the shortest one by more than `tol`.

        Opt-in and exponential in the worst case: a diagnostic for a
        misdeclared edge, not something to call per page.
        """
        ref = self.transform(src, dst)
        bad: list[list[str]] = []

        def walk(cur: str, seen: list[str]) -> None:
            if cur == dst:
                m = Affine.identity()
                for u, v in zip(seen, seen[1:]):
                    m = m.then(self._edges[u][v])
                if not m.approx_eq(ref, tol):
                    bad.append(list(seen))
                return
            for nxt in self._edges[cur]:
                if nxt in seen:
                    continue
                seen.append(nxt)
                walk(nxt, seen)
                seen.pop()

        if src not in self._edges:
            raise SpaceNotFound(src)
        if dst not in self._edges:
            raise SpaceNotFound(dst)
        walk(src, [src])
        return bad
