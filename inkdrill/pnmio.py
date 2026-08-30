"""pnmio.py -- ghostscript `pgmraw` ingest. U0's second input route.

CONTRACT (written before implementation; see docs/units.md U0)
=============================================================

`pngio` reads what `png16m` writes. This reads what `pgmraw` writes, and
exists because the decode is the pipeline's waiting time:

    route      gs        into a mask       total
    png16m     2,224 ms   11,799 ms       14,023 ms
    pgmraw       304 ms        14 ms          318 ms
                              847x             44x

A PGM read is a header parse and a `memoryview`. There is nothing to
decode -- no filtering, no deflate, no per-scanline predictor -- which
is the entire difference. Same page, same mask.

The resolution problem, which is the whole risk
-----------------------------------------------
**PNM has no `pHYs`.** The format has nowhere to record dpi, so the
points conversion `emit.py` depends on has no source in the file.

`read_pnm` therefore takes `dpi` and **raises without it**. Not a
default of 72, not an inference from a nominal page size: that
inference cost 0.071 pt on the `e12s39` fixture, which was the size of
the residual being measured at the time, and a mask whose coordinates
are silently in the wrong space cannot be detected downstream.

`pngio` gets this right for free because `pHYs` is in the file.
Here the caller must supply it -- it knows, it just invoked `gs -r400`.
The failure mode is identical either way, which is the point.

The two routes are not byte-identical
-------------------------------------
Measured on `e12s39` at 400 dpi: **259 of 15,465,468 samples differ,
16.7 per million**, and topology is identical at every threshold from
100 to 240 -- 910 components and 1,011 holes both ways.

**Every one of those 259 differs by exactly 255.** Not a rounding
difference and not an anti-aliasing one: both of those would leave
intermediate greys and would move as the threshold moves. A pixel that
is 0 in one route and 255 in the other is a **scan-conversion**
disagreement -- whether a pixel centre falls inside the shape -- which
is why the count is the same 259 at every threshold and why it will not
grow if the threshold changes.

The consequence for a caller: components, holes, nesting and the Reeb
signature are route-invariant; `Moments` are not, because they are exact
integer sums and 259 pixels show. The recorded `e12s39` geometry is
route-invariant too -- the authored 175.248 pt reads 175.320 through
both, residual 0.072 pt, identical to three decimals.

Scope, and why it is narrow
---------------------------
**P5 only** -- binary greyscale, which is what `pgmraw` writes. P2
(ASCII greyscale) is accepted because it costs three lines and makes a
hermetic fixture readable. **P6 and P4 are refused**, loudly:

- P6 (`ppmraw`) would need the same luma reduction `pngio` performs, and
  adding it silently would give two code paths for one decision
- P4 (`pbmraw`) is one bit per pixel with rows padded to a byte
  boundary -- a different unpacking, not a variant of P5, and treating
  it as one produces a plausible mask of the wrong width

Guarantees
----------
G1  pure bytes in, `PnmImage` out; no I/O beyond reading the named file
G2  P5 and P2 are read; every other magic raises `UnsupportedPNM`
G3  comments (`#` to end of line) are skipped between ANY two header
    tokens, including between maxval and the data
G4  exactly one whitespace byte separates the maxval from binary data,
    and a second one is DATA -- not skipped
G5  `dpi` is required and has no default; omitting it raises
    `NoResolution` rather than assuming one
G6  a page's TOPOLOGY is route-invariant -- same components, holes,
    nesting and signature as `png16m`. The pixel sets are NOT equal and
    cannot be, so `Moments` differ; see above
G7  a truncated or over-long raster raises rather than padding or
    silently cropping
"""

from __future__ import annotations

from dataclasses import dataclass

from .raster import InkMask, binarize

__all__ = ["CorruptPNM", "NoResolution", "PnmImage", "UnsupportedPNM",
           "load_mask", "load_masks", "read_pnm", "read_pnm_stream"]


class CorruptPNM(ValueError):
    """The file is malformed."""


class UnsupportedPNM(ValueError):
    """Outside the stated scope -- see the module contract."""


class NoResolution(ValueError):
    """PNM cannot carry dpi, and none was supplied (G5)."""


@dataclass(frozen=True, slots=True)
class PnmImage:
    """A decoded page. `gray` is row-major, length width * height."""
    width: int
    height: int
    gray: bytes
    dpi: tuple[float, float]

    def __repr__(self) -> str:
        return f"PnmImage({self.width}x{self.height}, dpi={self.dpi})"


_WS = b" \t\r\n\v\f"


def _token(raw: bytes, i: int) -> tuple[bytes, int]:
    """The next header token, skipping whitespace and comments (G3)."""
    n = len(raw)
    while i < n:
        c = raw[i:i + 1]
        if c in _WS:
            i += 1
        elif c == b"#":
            while i < n and raw[i:i + 1] not in b"\r\n":
                i += 1
        else:
            break
    start = i
    while i < n and raw[i:i + 1] not in _WS and raw[i:i + 1] != b"#":
        i += 1
    if start == i:
        raise CorruptPNM("truncated header")
    return raw[start:i], i


def read_pnm(src, *, dpi=None) -> PnmImage:
    """Decode a `pgmraw` (P5) or ASCII (P2) PGM.

    `dpi` is REQUIRED (G5): the format cannot carry it, and guessing is
    the failure this contract exists to prevent. Pass a float or a
    `(x, y)` pair -- whatever `gs -r` was given.
    """
    if dpi is None:
        raise NoResolution(
            "PNM carries no resolution, so `dpi` must be supplied; the "
            "caller invoked ghostscript and knows it. Defaulting to 72 or "
            "inferring from a nominal page size is wrong by 0.071 pt on the "
            "e12s39 fixture -- see the module contract")
    res = (float(dpi), float(dpi)) if isinstance(dpi, (int, float)) \
        else (float(dpi[0]), float(dpi[1]))
    if res[0] <= 0 or res[1] <= 0:
        raise NoResolution(f"dpi must be positive, got {res}")

    raw = _bytes_of(src)
    if len(raw) < 2:
        raise CorruptPNM("file too short to hold a magic number")
    img, end = _decode_one(raw, 0, res)
    if end != len(raw):
        raise CorruptPNM(
            f"{len(raw) - end} trailing bytes after the raster")
    return img


def _bytes_of(src) -> bytes:
    if isinstance(src, (bytes, bytearray, memoryview)):
        return bytes(src)
    if hasattr(src, "read"):
        return src.read()
    with open(src, "rb") as fh:
        return fh.read()


def _decode_one(raw: bytes, i: int, res):
    """One PNM image starting at `i`; returns `(image, end_index)`.

    Split out so a CONCATENATED stream can be walked without relaxing
    `read_pnm`'s refusal of trailing bytes. A single file with extra
    data at the end is still an error -- it means the caller passed
    something other than what it thinks it did -- while a stream of
    them is a stream, and the difference is which function is called.
    """
    magic, i = _token(raw, i)
    if magic in (b"P4", b"P6", b"P1", b"P3", b"P7"):
        raise UnsupportedPNM(
            f"{magic.decode()} is out of scope; this reads P5 (pgmraw) and "
            f"P2. P6 needs the luma reduction pngio already performs, and "
            f"P4 is one bit per pixel with byte-padded rows -- a different "
            f"unpacking, not a variant of P5")
    if magic not in (b"P5", b"P2"):
        raise UnsupportedPNM(f"not a PNM: magic {magic!r}")

    try:
        w_tok, i = _token(raw, i)
        h_tok, i = _token(raw, i)
        m_tok, i = _token(raw, i)
        width, height, maxval = int(w_tok), int(h_tok), int(m_tok)
    except ValueError as exc:
        raise CorruptPNM(f"malformed header: {exc}") from None
    if width <= 0 or height <= 0:
        raise CorruptPNM(f"non-positive extent {width}x{height}")
    if maxval != 255:
        raise UnsupportedPNM(
            f"maxval {maxval}; only 8-bit (255) is read, because a 16-bit "
            f"PGM is two bytes per sample and would silently halve the width")

    want = width * height
    if magic == b"P2":
        vals = raw[i:].split()
        if len(vals) != want:
            raise CorruptPNM(f"P2 holds {len(vals)} samples, expected {want}")
        gray = bytes(int(v) for v in vals)
        return PnmImage(width, height, gray, res), len(raw)
    else:
        # Exactly ONE whitespace byte after maxval; a second is DATA (G4).
        if i >= len(raw) or raw[i:i + 1] not in _WS:
            raise CorruptPNM("no whitespace between maxval and raster")
        start = i + 1
        gray = raw[start:start + want]
        if len(gray) != want:
            raise CorruptPNM(
                f"raster holds {len(gray)} bytes, expected {want}")
    return PnmImage(width, height, gray, res), start + want


def read_pnm_stream(src, *, dpi=None):
    """Every image in a CONCATENATED PNM stream, in order (T3).

    `gs -sDEVICE=pgmraw -sOutputFile=%stdout` writes one PNM per page
    back to back, so a multi-page render is one stream and not one
    file. This walks it. Ghostscript also emits a `#` comment line
    after the magic, which `_token` already skips.

    `dpi` is required for the same reason it is required of `read_pnm`,
    and it applies to every page: one `gs -r` produced them all.
    """
    if dpi is None:
        raise NoResolution(
            "PNM carries no resolution, so `dpi` must be supplied; the "
            "caller invoked ghostscript and knows it")
    res = (float(dpi), float(dpi)) if isinstance(dpi, (int, float)) \
        else (float(dpi[0]), float(dpi[1]))
    if res[0] <= 0 or res[1] <= 0:
        raise NoResolution(f"dpi must be positive, got {res}")
    raw = _bytes_of(src)
    i, n = 0, len(raw)
    while i < n:
        # Trailing whitespace between images is not a further image.
        while i < n and raw[i:i + 1] in _WS:
            i += 1
        if i >= n:
            return
        img, i = _decode_one(raw, i, res)
        yield img


def stream_masks(fh, *, dpi=None, threshold: int = 128,
                 ink_is_dark: bool = True):
    """388 — one `InkMask` per page, read A ROW AT A TIME, storing no image.

    `read_pnm_stream` is a stream in name only: it calls `_bytes_of(src)` and
    walks a buffer holding EVERY page. A 34-page A3 render at 600 dpi is
    2.2 GB that way, and one page alone costs the 66 MB raster plus the two
    copies `binarize` makes of it (`bytes(gray)`, then `.translate`).

    `pgmraw` is raster order: a small ASCII header, then width*height bytes,
    row by row, top to bottom. That is a line-scan feed, which is what this
    measurement was originally built to read, and nothing downstream of the
    threshold needs the grey values. So each row is thresholded as it
    arrives, through the same cached LUT `binarize` uses, and only the mask
    is kept: peak is one mask plus one row, and the grey page never exists
    as an object at all.

    IDENTICAL, NOT MERELY EQUIVALENT. The LUT is `raster._lut`, so the
    threshold rule cannot drift from `binarize`'s -- the defect this file's
    header already warns about for the two routes. Asserted on real pages by
    tests/test_pnm_stream.py, mask bytes compared whole.

    POLARITY. `auto_mask` needs a second, light-on-dark mask, and only when
    the dark one `looks_inverted` -- which needs `ink_count` alone. The two
    LUTs are exact complements (`v < t` against `v >= t`), so the light mask
    is the dark one's byte-wise complement and no second pass over the input
    is required. A stream cannot be rewound; this is why that matters.
    """
    from .raster import _lut
    if dpi is None:
        raise NoResolution(
            "PNM carries no resolution, so `dpi` must be supplied; the "
            "caller invoked ghostscript and knows it")
    res = (float(dpi), float(dpi)) if isinstance(dpi, (int, float)) \
        else (float(dpi[0]), float(dpi[1]))
    if res[0] <= 0 or res[1] <= 0:
        raise NoResolution(f"dpi must be positive, got {res}")
    lut = _lut(threshold, ink_is_dark)
    while True:
        hdr = _read_header(fh)
        if hdr is None:
            return
        width, height = hdr
        out = bytearray()
        remaining = width * height
        row = width
        while remaining > 0:
            chunk = fh.read(min(row, remaining))
            if not chunk:
                raise CorruptPNM(
                    f"raster ended {remaining} byte(s) short of "
                    f"{width}x{height}")
            out += chunk.translate(lut)
            remaining -= len(chunk)
        yield InkMask(bytes(out), width, height)


def _read_header(fh):
    """(width, height) for the next P5 image, or None at end of stream.

    Read BYTE AT A TIME. The header is ~20 bytes and is followed immediately
    by raster data, so any read-ahead would swallow pixels -- and a stream
    from a pipe cannot be rewound to give them back.
    """
    toks, cur, seen_magic = [], b"", False
    while len(toks) < 4:
        c = fh.read(1)
        if not c:
            if not toks and not cur:
                return None
            raise CorruptPNM("stream ended inside the header")
        if c == b"#":                       # ghostscript writes a comment
            while c and c != b"\n":
                c = fh.read(1)
            continue
        if c in _WS:
            if cur:
                toks.append(cur)
                cur = b""
                if len(toks) == 1:
                    seen_magic = True
            # Exactly ONE whitespace byte closes the header (G4); a second
            # would be raster data.
            if len(toks) == 4:
                break
            continue
        cur += c
    if toks[0] != b"P5":
        raise UnsupportedPNM(
            f"{toks[0]!r}: only P5 (pgmraw) can be streamed; P2 is ASCII "
            f"and has no fixed row length")
    try:
        width, height, maxval = int(toks[1]), int(toks[2]), int(toks[3])
    except ValueError as exc:
        raise CorruptPNM(f"malformed header: {exc}") from None
    if width <= 0 or height <= 0:
        raise CorruptPNM(f"non-positive extent {width}x{height}")
    if maxval != 255:
        raise UnsupportedPNM(
            f"maxval {maxval}; only 8-bit (255) is read, because a 16-bit "
            f"PGM is two bytes per sample and would silently halve the width")
    return width, height


def load_masks(src, *, dpi=None, threshold: int = 128,
               ink_is_dark: bool = True):
    """`read_pnm_stream` straight to masks, one per page."""
    for img in read_pnm_stream(src, dpi=dpi):
        yield binarize(img.gray, img.width, img.height,
                       threshold=threshold, ink_is_dark=ink_is_dark)


def load_mask(src, *, dpi=None, threshold: int = 128,
              ink_is_dark: bool | str = True) -> InkMask:
    """A PGM straight to an `InkMask` (G6).

    Mirrors `pngio.load_mask` -- including `ink_is_dark="auto"`, whose
    cut lives in ONE place (`pngio._auto_binarize`) so the two routes
    cannot drift on it, exactly as they cannot drift on the threshold.
    """
    from .pngio import _auto_binarize
    img = read_pnm(src, dpi=dpi)
    return _auto_binarize(img.gray, img.width, img.height,
                          threshold, ink_is_dark)
