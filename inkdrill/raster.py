"""raster.py — ink masks and maximal run extraction.

CONTRACT (written before implementation; see docs/units.md U2)
=============================================================

Mask encoding — ONE encoding, package-wide
------------------------------------------
`InkMask.data` is a `bytes` of length `width * height`, row-major, with

        0xFF = ink (foreground)          0x00 = background

and nothing else. This is chosen over 1/0 so that `bytes.translate`
does binarization and `bytes.find` does run extraction, both at C speed
without numpy. Any buffer entering the package is converted at the
boundary; no other encoding is accepted or produced.

Run geometry
------------
A `Run` is `(line, lo, hi)` in SCAN space, with `lo` and `hi` INCLUSIVE:

        axis "row":  line = y,  lo..hi = x       (a horizontal run)
        axis "col":  line = x,  lo..hi = y       (a vertical run)

`Run.image_span(axis)` converts to image (x, y) without the caller having
to remember which is which. Nothing downstream should index a Run tuple
positionally to get an image coordinate.

Guarantees
----------
G1  runs are MAXIMAL: no two runs are adjacent within the same line
G2  runs never span a line boundary
G3  runs are yielded in scan order: `line` ascending, then `lo` ascending
G4  the pixel set covered by `iter_runs(m, "row")` equals the pixel set
    covered by `iter_runs(m, "col")` -- the foundation of axis invariance
G5  sum of run lengths == the count of 0xFF bytes in the mask
G6  binarize is exact at the threshold: `ink_is_dark=True` means ink iff
    `gray < threshold` (strict), so `threshold=0` yields an empty mask
G7  crop and clear_regions produce a mask whose runs are the restriction
    of the original runs to the rectangle

Non-guarantees (out of scope for U2)
------------------------------------
  * no adaptive/local thresholding -- a single global threshold only
  * no denoising, no morphology
  * no image file I/O; callers supply a grayscale byte buffer
"""

from __future__ import annotations

from typing import Iterable, Iterator, NamedTuple

__all__ = ["InkMask", "Run", "Rect", "AXES", "binarize", "iter_runs",
           "InvalidAxis"]

INK = 0xFF
BG = 0x00
AXES = ("row", "col")


class InvalidAxis(ValueError):
    """axis must be exactly 'row' or 'col'."""


class Rect(NamedTuple):
    """Half-open pixel rectangle [x0, x1) x [y0, y1) in mask space."""
    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def width(self) -> int:
        return max(0, self.x1 - self.x0)

    @property
    def height(self) -> int:
        return max(0, self.y1 - self.y0)

    @property
    def empty(self) -> bool:
        return self.width == 0 or self.height == 0

    def clipped_to(self, w: int, h: int) -> "Rect":
        return Rect(max(0, min(self.x0, w)), max(0, min(self.y0, h)),
                    max(0, min(self.x1, w)), max(0, min(self.y1, h)))

    def padded(self, pad: int) -> "Rect":
        return Rect(self.x0 - pad, self.y0 - pad, self.x1 + pad, self.y1 + pad)


class Run(NamedTuple):
    """A maximal ink run in SCAN space. `lo` and `hi` are inclusive."""
    line: int
    lo: int
    hi: int

    @property
    def length(self) -> int:
        return self.hi - self.lo + 1

    def image_span(self, axis: str) -> tuple[int, int, int, int]:
        """(x0, y0, x1, y1) in IMAGE space, inclusive, for this run."""
        if axis == "row":
            return (self.lo, self.line, self.hi, self.line)
        if axis == "col":
            return (self.line, self.lo, self.line, self.hi)
        raise InvalidAxis(axis)

    def image_pixels(self, axis: str) -> Iterator[tuple[int, int]]:
        """Every pixel of this run as image (x, y)."""
        if axis == "row":
            y = self.line
            for x in range(self.lo, self.hi + 1):
                yield x, y
        elif axis == "col":
            x = self.line
            for y in range(self.lo, self.hi + 1):
                yield x, y
        else:
            raise InvalidAxis(axis)


# --------------------------------------------------------------------------
# Threshold lookup tables, cached per (threshold, polarity)
# --------------------------------------------------------------------------

_LUTS: dict[tuple[int, bool], bytes] = {}


def _lut(threshold: int, ink_is_dark: bool) -> bytes:
    key = (threshold, ink_is_dark)
    t = _LUTS.get(key)
    if t is None:
        if ink_is_dark:
            t = bytes(INK if v < threshold else BG for v in range(256))
        else:
            t = bytes(INK if v >= threshold else BG for v in range(256))
        _LUTS[key] = t
    return t


# --------------------------------------------------------------------------
# InkMask
# --------------------------------------------------------------------------

class InkMask:
    """A binary ink mask. `data` is 0xFF/0x00, row-major, len == w*h."""

    __slots__ = ("data", "width", "height")

    def __init__(self, data: bytes, width: int, height: int) -> None:
        if width < 0 or height < 0:
            raise ValueError(f"negative extent {width}x{height}")
        if len(data) != width * height:
            raise ValueError(
                f"buffer length {len(data)} != {width}*{height}={width*height}")
        self.data = bytes(data)
        self.width = width
        self.height = height

    # -- factories ---------------------------------------------------------

    @staticmethod
    def empty(width: int, height: int) -> "InkMask":
        return InkMask(bytes(width * height), width, height)

    @staticmethod
    def from_rows(rows: Iterable[str], ink: str = "#") -> "InkMask":
        """Build from an ASCII picture -- the fixture format for tests.

        Every row must have the same length. Characters equal to `ink`
        become 0xFF; everything else becomes 0x00.
        """
        rs = list(rows)
        if not rs:
            return InkMask(b"", 0, 0)
        w = len(rs[0])
        for i, r in enumerate(rs):
            if len(r) != w:
                raise ValueError(f"row {i} has length {len(r)}, expected {w}")
        buf = bytearray(w * len(rs))
        for y, r in enumerate(rs):
            base = y * w
            for x, ch in enumerate(r):
                if ch == ink:
                    buf[base + x] = INK
        return InkMask(bytes(buf), w, len(rs))

    # -- queries -----------------------------------------------------------

    @property
    def ink_count(self) -> int:
        return self.data.count(INK)

    def at(self, x: int, y: int) -> bool:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return False
        return self.data[y * self.width + x] == INK

    def line_length(self, axis: str) -> int:
        """Number of positions within one scan line."""
        if axis == "row":
            return self.width
        if axis == "col":
            return self.height
        raise InvalidAxis(axis)

    def line_count(self, axis: str) -> int:
        """Number of scan lines along `axis`."""
        if axis == "row":
            return self.height
        if axis == "col":
            return self.width
        raise InvalidAxis(axis)

    def to_rows(self, ink: str = "#", bg: str = ".") -> list[str]:
        """Inverse of `from_rows`, for readable assertion failures."""
        w = self.width
        return ["".join(ink if self.data[y * w + x] == INK else bg
                        for x in range(w))
                for y in range(self.height)]

    # -- derivation --------------------------------------------------------

    def crop(self, rect: Rect) -> tuple["InkMask", int, int]:
        """Return (sub-mask, ox, oy) where (ox, oy) is the position of the
        sub-mask's (0, 0) in this mask. `rect` is clipped to the mask."""
        r = rect.clipped_to(self.width, self.height)
        if r.empty:
            return InkMask(b"", 0, 0), r.x0, r.y0
        w = self.width
        out = bytearray(r.width * r.height)
        for j, y in enumerate(range(r.y0, r.y1)):
            src = y * w + r.x0
            out[j * r.width:(j + 1) * r.width] = self.data[src:src + r.width]
        return InkMask(bytes(out), r.width, r.height), r.x0, r.y0

    def clear_regions(self, rects: Iterable[Rect]) -> "InkMask":
        """A copy with every rectangle forced to background.

        The exclusion half of ROI handling. Kept as a pure derivation so
        the core scan never learns why a region was excluded.
        """
        buf = bytearray(self.data)
        w = self.width
        for rect in rects:
            r = rect.clipped_to(self.width, self.height)
            if r.empty:
                continue
            zero = bytes(r.width)
            for y in range(r.y0, r.y1):
                base = y * w + r.x0
                buf[base:base + r.width] = zero
        return InkMask(bytes(buf), self.width, self.height)

    def keep_regions(self, rects: Iterable[Rect]) -> "InkMask":
        """A copy with everything OUTSIDE every rectangle forced to background.

        The inclusion half. `clear_regions` and `keep_regions` are the two
        polarities of one ROI parameter -- the math pipeline needs the
        complement of what the text pipeline needs, and neither should be
        a separate code path.
        """
        buf = bytearray(self.width * self.height)
        w = self.width
        for rect in rects:
            r = rect.clipped_to(self.width, self.height)
            if r.empty:
                continue
            for y in range(r.y0, r.y1):
                base = y * w + r.x0
                buf[base:base + r.width] = self.data[base:base + r.width]
        return InkMask(bytes(buf), self.width, self.height)

    def inverted(self) -> "InkMask":
        """Ink and background exchanged. Used for hole finding."""
        return InkMask(self.data.translate(_INVERT), self.width, self.height)

    def __eq__(self, other: object) -> bool:
        return (isinstance(other, InkMask) and other.width == self.width
                and other.height == self.height and other.data == self.data)

    def __repr__(self) -> str:
        return (f"InkMask({self.width}x{self.height}, "
                f"{self.ink_count} ink px)")


_INVERT = bytes(BG if v == INK else INK for v in range(256))


# --------------------------------------------------------------------------
# Binarization
# --------------------------------------------------------------------------

def binarize(gray, width: int, height: int, *, threshold: int = 128,
             ink_is_dark: bool = True) -> InkMask:
    """Grayscale byte buffer -> InkMask via a cached 256-entry LUT.

    `ink_is_dark=True` (the default, and the case for every rendered page)
    marks a pixel as ink iff `gray < threshold`, STRICTLY. A pixel exactly
    equal to the threshold is background.
    """
    if not 0 <= threshold <= 256:
        raise ValueError(f"threshold {threshold} outside 0..256")
    buf = bytes(gray)
    if len(buf) != width * height:
        raise ValueError(
            f"buffer length {len(buf)} != {width}*{height}={width*height}")
    return InkMask(buf.translate(_lut(threshold, ink_is_dark)), width, height)


# --------------------------------------------------------------------------
# Run extraction
# --------------------------------------------------------------------------

def _iter_runs_row(mask: InkMask) -> Iterator[Run]:
    data, w, h = mask.data, mask.width, mask.height
    find = data.find
    ink, bg = b"\xff", b"\x00"
    for y in range(h):
        base = y * w
        end = base + w
        pos = base
        while True:
            s = find(ink, pos, end)
            if s < 0:
                break
            e = find(bg, s + 1, end)
            if e < 0:
                e = end
            yield Run(y, s - base, e - base - 1)
            pos = e + 1


def _iter_runs_col(mask: InkMask) -> Iterator[Run]:
    data, w, h = mask.data, mask.width, mask.height
    ink, bg = b"\xff", b"\x00"
    for x in range(w):
        col = data[x::w]              # C-speed step slice
        find = col.find
        pos = 0
        while True:
            s = find(ink, pos)
            if s < 0:
                break
            e = find(bg, s + 1)
            if e < 0:
                e = h
            yield Run(x, s, e - 1)
            pos = e + 1


def iter_runs(mask: InkMask, axis: str = "row") -> Iterator[Run]:
    """Maximal ink runs in scan order. See the module contract for G1-G5."""
    if axis == "row":
        return _iter_runs_row(mask)
    if axis == "col":
        return _iter_runs_col(mask)
    raise InvalidAxis(axis)
