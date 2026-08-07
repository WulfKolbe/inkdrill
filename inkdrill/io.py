"""io.py — Ghostscript png16m ingest.

CONTRACT (written before implementation; see docs/units.md U0)
=============================================================

Scope limit, stated up front
----------------------------
This unit reads the output of ONE producer: the Ghostscript `png16m`
device. That is IHDR exactly

        (bit depth, colour type, compression, filter, interlace)
        = (8, 2, 0, 0, 0)

8-bit truecolor RGB, deflate, adaptive filtering, non-interlaced.

Anything else raises `UnsupportedPNG` naming the tuple found. 16-bit,
palette, greyscale, alpha and Adam7 interlacing are all refused. Refusing
GREYSCALE input while PRODUCING greyscale output looks backwards and is
deliberate: accepting an untested input path is how a decoder quietly
returns a wrong image. Widening this contract is a decision to make with
evidence, not a convenience to slip in.

All five scanline filters are implemented regardless of what the sampled
corpus contains, because libpng's adaptive heuristic may select None or
Average on content not yet seen.

Output
------
`read_png` returns GREYSCALE BYTES, not an `InkMask`. That composes with
`raster.binarize(gray, width, height, ...)` rather than duplicating it,
and leaves the threshold decision where U2 already owns it.

Guarantees
----------
G1  all IDAT chunks are concatenated before a single inflate
G2  every chunk's CRC-32 is verified; a mismatch raises CorruptPNG
G3  len(gray) == width * height, exactly
G4  both decode paths are byte-identical to the naive per-byte reference
    decoder, for every filter type
G5  neutrality of the FILTERED stream == neutrality of the DECODED image;
    this is what makes the two-path decode exact rather than heuristic
G6  an IHDR outside the stated scope raises UnsupportedPNG naming the
    tuple found; it never returns a mis-decoded image
G7  dpi comes from pHYs with unit specifier 1 (pixels per metre) as
    ppm * 0.0254, and is None when pHYs is absent or carries unit 0;
    it is never silently defaulted

Non-guarantees (out of scope for U0)
------------------------------------
  * no PNG writing -- read-only unit
  * no colour output -- colour input is reduced to luma
  * no PDF rendering -- pdftoppm and Ghostscript are external tools
"""

from __future__ import annotations

import struct
import zlib
from typing import Iterator

__all__ = ["CorruptPNG", "UnsupportedPNG", "PngImage", "read_png", "load_mask"]


class CorruptPNG(ValueError):
    """The file is not a well-formed PNG."""


class UnsupportedPNG(ValueError):
    """Well-formed PNG, but outside this unit's stated scope."""


_SIG = b"\x89PNG\r\n\x1a\n"

# (bit depth, colour type, compression, filter, interlace) -- png16m
_SUPPORTED_IHDR = (8, 2, 0, 0, 0)

_BPP = 3           # bytes per pixel for colour type 2 at depth 8
_INCH_PER_METRE = 0.0254


def _chunks(raw: bytes) -> Iterator[tuple[bytes, bytes]]:
    """Yield (type, payload) for every chunk, verifying each CRC (G2)."""
    if raw[:8] != _SIG:
        raise CorruptPNG("bad PNG signature")
    i, n = 8, len(raw)
    while i < n:
        if i + 8 > n:
            raise CorruptPNG("truncated chunk header")
        length, typ = struct.unpack(">I4s", raw[i:i + 8])
        end = i + 12 + length
        if end > n:
            raise CorruptPNG(f"chunk {typ.decode('latin-1')} truncated")
        data = raw[i + 8:i + 8 + length]
        want = struct.unpack(">I", raw[i + 8 + length:end])[0]
        if zlib.crc32(typ + data) & 0xFFFFFFFF != want:
            raise CorruptPNG(f"CRC mismatch in chunk {typ.decode('latin-1')}")
        yield typ, data
        i = end


def _parse_ihdr(data: bytes) -> tuple[int, int]:
    """(width, height), or raise if outside scope (G6)."""
    if len(data) != 13:
        raise CorruptPNG(f"IHDR payload is {len(data)} bytes, expected 13")
    w, h, depth, ctype, comp, filt, inter = struct.unpack(">IIBBBBB", data)
    if w == 0 or h == 0:
        raise CorruptPNG(f"degenerate dimensions {w}x{h}")
    got = (depth, ctype, comp, filt, inter)
    if got != _SUPPORTED_IHDR:
        raise UnsupportedPNG(
            f"IHDR (depth, colour, compression, filter, interlace) = {got}; "
            f"this unit reads ghostscript png16m only, which is "
            f"{_SUPPORTED_IHDR}")
    return w, h


def _parse_phys(data: bytes) -> tuple[float, float] | None:
    """dpi from pHYs, or None when there is no physical scale (G7)."""
    if len(data) != 9:
        raise CorruptPNG(f"pHYs payload is {len(data)} bytes, expected 9")
    ppux, ppuy, unit = struct.unpack(">IIB", data)
    if unit != 1:                      # 0 == aspect ratio only, no scale
        return None
    return (ppux * _INCH_PER_METRE, ppuy * _INCH_PER_METRE)
