"""pngio.py — Ghostscript png16m ingest.

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

import os
import struct
import zlib
from dataclasses import dataclass
from itertools import accumulate
from typing import Iterator

from .raster import InkMask, binarize, looks_inverted

__all__ = ["auto_mask",
           "CorruptPNG", "UnsupportedPNG", "PngImage", "read_png", "load_mask"]


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


def _is_neutral(dec: bytes, w: int, h: int) -> bool:
    """True iff the decoded image would satisfy R == G == B everywhere.

    Decided on the FILTERED bytes, with no unfiltering (G5). The iff holds
    by two symmetric arguments:

    Forward (neutral raw ⟹ neutral filtered): Every PNG filter references
    bytes at `bpp` stride within its own channel. If source rows satisfy
    R == G == B, then filtered rows satisfy R == G == B too, for every
    filter type, by induction on rows.

    Converse (non-neutral raw ⟹ non-neutral filtered): the INVERSE filter
    also references bytes at `bpp` stride within its own channel:
    recon[i] = filt[i] + pred(a, b, c) with a = recon[i-3], b = prev[i],
    c = prev[i-3], for every filter type. So if prev is channel-identical
    and filt is channel-identical, induction on i gives recon
    channel-identical -- the same induction as the forward direction, run
    on the inverse filter instead. Read contrapositively at the first row
    where recon departs from neutrality (prev is still channel-identical
    there, by minimality of that row): filt must depart from neutrality
    too. That is the converse, directly.

    Safety-critical use: this converse direction prevents a colour image
    being silently decoded as a grey image (e.g., red channel alone).

    The two-comparison form (s[0::3] != s[1::3] or s[1::3] != s[2::3])
    is complete by transitivity: if R, G, B are not all equal at some
    pixel, then either R≠G or G≠B must hold there; no third comparison
    is needed.

    Two C-speed slice comparisons per row; measured at 1.3% of decode cost.

    Precondition -- not itself validated: `dec` must be exactly
    `h * (w*3+1)` bytes. Python bytes slicing never raises on an
    out-of-range bound, it silently truncates, so a short buffer would
    return a meaningless answer instead of an error. The caller (`read_png`)
    validates the length before this runs.
    """
    stride = w * 3 + 1
    for base in range(1, h * stride + 1, stride):
        s = dec[base:base + stride - 1]
        if s[0::3] != s[1::3] or s[1::3] != s[2::3]:
            return False
    return True


def _decode_gray_neutral(dec: bytes, w: int, h: int) -> bytes:
    """Unfilter ONE channel of a neutral image.

    Every PNG filter references bytes at `bpp` stride within its own
    channel, so the three channels are independent chains and `row[0::3]`
    -- a C-speed slice -- isolates one. In the sliced domain `bpp`
    collapses to 1.

    The Up filter, 76% of rows in the sampled corpus, is done with SWAR
    big-integer arithmetic: elementwise (a + b) mod 256 across a whole
    scanline as three CPython big-int operations at C speed, replacing
    ~2400 interpreted iterations.

            low  = (A & 0x7f7f..) + (B & 0x7f7f..)   # no carry crosses a byte
            high = (A ^ B) & 0x8080..
            out  = low ^ high

    Measured throughput and the corpus filter mix are recorded in
    docs/units.md Section 3 ("U0 decode throughput") rather than duplicated
    here, so a re-measurement is one edit instead of two. Headline: a
    13.3x speedup over the naive per-byte path. Throughput varies
    significantly with filter mix -- a Paeth-heavy page runs several times
    slower, because Paeth's predictor depends on bytes just produced and
    cannot be vectorised.
    """
    stride = w * 3 + 1
    lo_mask = int.from_bytes(b"\x7f" * w, "big")
    hi_mask = int.from_bytes(b"\x80" * w, "big")
    prev = bytes(w)
    out: list[bytes] = []
    for r in range(h):
        base = r * stride
        ft = dec[base]
        line = dec[base + 1:base + stride][0::3]
        if ft == 0:
            cur = line
        elif ft == 2:                                    # Up -- SWAR
            a = int.from_bytes(line, "big")
            b = int.from_bytes(prev, "big")
            cur = (((a & lo_mask) + (b & lo_mask))
                   ^ ((a ^ b) & hi_mask)).to_bytes(w, "big")
        elif ft == 1:                                    # Sub -- prefix sum
            cur = bytes(accumulate(line, lambda x, y: (x + y) & 0xFF))
        elif ft == 3:                                    # Average
            c = bytearray(line)
            for i in range(w):
                c[i] = (c[i] + (((c[i - 1] if i else 0) + prev[i]) >> 1)) & 0xFF
            cur = bytes(c)
        elif ft == 4:                                    # Paeth -- sequential
            c = bytearray(line)
            for i in range(w):
                a = c[i - 1] if i else 0
                bb = prev[i]
                cc = prev[i - 1] if i else 0
                p = a + bb - cc
                pa, pb, pc = abs(p - a), abs(p - bb), abs(p - cc)
                pred = a if (pa <= pb and pa <= pc) else (bb if pb <= pc else cc)
                c[i] = (c[i] + pred) & 0xFF
            cur = bytes(c)
        else:
            raise CorruptPNG(f"unknown filter type {ft} on row {r}")
        out.append(cur)
        prev = cur
    return b"".join(out)


def _decode_gray_colour(dec: bytes, w: int, h: int) -> bytes:
    """Unfilter all three channels, then reduce to luma.

    Runs when `_is_neutral` is False -- the MAJORITY path, not an edge case.
    See docs/units.md Section 3 ("U0 decode throughput") for the measured
    share of colour pages, rather than duplicating that figure here where
    it can drift out of sync again. Taking one channel there would render
    red ink near-white and blue ink near-black. Neutrality is *almost
    always* a per-document property, consistent with it tracking a render
    setting rather than page content -- but not always: a small number of
    sampled documents mix neutral and non-neutral pages, so a decoder must
    not assume a document's first page predicts the rest.

    Rec.601, integer, round-half-up. On a neutral pixel this is exactly
    the identity, so the two paths agree wherever both are valid.
    """
    stride = w * 3 + 1
    row_len = w * 3
    prev = bytearray(row_len)
    out: list[bytes] = []
    for r in range(h):
        base = r * stride
        ft = dec[base]
        line = bytearray(dec[base + 1:base + stride])
        if ft == 1:
            for i in range(_BPP, row_len):
                line[i] = (line[i] + line[i - _BPP]) & 0xFF
        elif ft == 2:
            for i in range(row_len):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ft == 3:
            for i in range(row_len):
                a = line[i - _BPP] if i >= _BPP else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif ft == 4:
            for i in range(row_len):
                a = line[i - _BPP] if i >= _BPP else 0
                b = prev[i]
                c = prev[i - _BPP] if i >= _BPP else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pred) & 0xFF
        elif ft != 0:
            raise CorruptPNG(f"unknown filter type {ft} on row {r}")
        prev = line
        out.append(bytes(
            (line[i] * 299 + line[i + 1] * 587 + line[i + 2] * 114 + 500) // 1000
            for i in range(0, row_len, _BPP)))
    return b"".join(out)


@dataclass(frozen=True, slots=True)
class PngImage:
    """A decoded page. `gray` is row-major, length width * height."""
    width: int
    height: int
    gray: bytes
    dpi: tuple[float, float] | None
    neutral: bool

    def __repr__(self) -> str:
        return (f"PngImage({self.width}x{self.height}, "
                f"dpi={self.dpi}, neutral={self.neutral})")


def read_png(src: bytes | bytearray | str | os.PathLike) -> PngImage:
    """Decode a ghostscript png16m PNG to greyscale.

    `src` is raw PNG bytes or a path. Raises UnsupportedPNG outside the
    stated scope, CorruptPNG for a malformed file.
    """
    if isinstance(src, (bytes, bytearray)):
        raw = bytes(src)
    else:
        with open(src, "rb") as fh:
            raw = fh.read()

    width = height = None
    dpi: tuple[float, float] | None = None
    idat: list[bytes] = []
    for typ, data in _chunks(raw):
        if typ == b"IHDR":
            if width is not None:
                raise CorruptPNG("multiple IHDR chunks")
            width, height = _parse_ihdr(data)
        elif typ == b"pHYs":
            dpi = _parse_phys(data)
        elif typ == b"IDAT":
            idat.append(data)
        elif typ == b"IEND":
            break

    if width is None:
        raise CorruptPNG("no IHDR chunk")
    if not idat:
        raise CorruptPNG("no IDAT chunk")

    try:
        dec = zlib.decompress(b"".join(idat))        # G1
    except zlib.error as exc:
        raise CorruptPNG(f"inflate failed: {exc}") from None

    expect = height * (width * 3 + 1)
    if len(dec) != expect:
        raise CorruptPNG(
            f"inflated to {len(dec)} bytes, expected {expect} "
            f"for {width}x{height}")

    neutral = _is_neutral(dec, width, height)
    gray = (_decode_gray_neutral(dec, width, height) if neutral
            else _decode_gray_colour(dec, width, height))
    return PngImage(width, height, gray, dpi, neutral)


def load_mask(src: bytes | bytearray | str | os.PathLike, *,
              threshold: int = 128,
              ink_is_dark: bool | str = True) -> InkMask:
    """read_png then U2's binarize. The only place this unit crosses into
    mask space, and it does so by calling U2 rather than duplicating it.

    `ink_is_dark="auto"` detects polarity: binarize dark-as-ink, and if
    ink exceeds half the page, flip. The cut is measured, not chosen --
    the densest legitimate pages observed are ~8-15% ink while
    light-on-dark video frames run 68-100% dark -- and no page has more
    ink than background. "auto" is OPT-IN, never the default: flipping
    silently under an existing caller would re-polarity every measurement
    harness in the repository.
    """
    img = read_png(src)
    return _auto_binarize(img.gray, img.width, img.height,
                          threshold, ink_is_dark)


def auto_mask(gray, width, height, threshold):
    """The polarity decision, in ONE place: `(mask, flipped)`.

    Two conditions, and the second exists because the first alone was
    REFUTED by a measured page. The fraction gate (`looks_inverted`,
    more ink than background) fires on true inverted slides -- but also
    on a magazine page whose top 60% is a nebula photograph over normal
    dark-on-light text (62.2% dark, `discovered-012018` p30). Flipping
    that page turns its body text into holes. The component comparison
    separates the cases in every measured instance:

        Typography deck p5    76.5% dark    5 -> 14 comps   FLIP
        Typography deck p120  73.0% dark   20 -> 145        FLIP
        chalkboard frame      77.7% dark  109 -> 223        FLIP
        magazine + photo p30  62.2% dark 1825 -> 769        KEEP
        stage photo p167      94.5% dark   34 -> 24         KEEP

    A true inverted page GAINS components when read light-on-dark (the
    letters separate from the merged background); a photo-dark page
    LOSES them (the real text merges away). A photograph has no
    document polarity at all, and keeping the default there is the
    conservative harmless call.
    """
    dark = binarize(gray, width, height, threshold=threshold,
                    ink_is_dark=True)
    if not looks_inverted(dark):
        return dark, False
    from .sweep import Capture, sweep
    light = binarize(gray, width, height, threshold=threshold,
                     ink_is_dark=False)
    n_dark = len(sweep(dark, conn=8, capture=Capture.NONE).components)
    n_light = len(sweep(light, conn=8, capture=Capture.NONE).components)
    if n_light > n_dark:
        return light, True
    return dark, False


def _auto_binarize(gray, width, height, threshold, ink_is_dark):
    """Shared by the PNG and PNM readers, so the rule lives once."""
    if ink_is_dark == "auto":
        return auto_mask(gray, width, height, threshold)[0]
    return binarize(gray, width, height,
                    threshold=threshold, ink_is_dark=ink_is_dark)
