"""Unit 0 tests. Every test name is quoted verbatim in the status report."""

import struct
import unittest
import zlib

from inkdrill.io import CorruptPNG, UnsupportedPNG, _chunks, _parse_ihdr, _parse_phys, _is_neutral

SIG = b"\x89PNG\r\n\x1a\n"


def _chunk(typ, data):
    """Assemble one PNG chunk with a correct CRC."""
    return (struct.pack(">I", len(data)) + typ + data
            + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))


def ihdr(w, h, depth=8, ctype=2, comp=0, filt=0, inter=0):
    return _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, depth, ctype, comp,
                                       filt, inter))


class T0_1_ChunkLayer(unittest.TestCase):

    def test_bad_signature_rejected(self):
        with self.assertRaises(CorruptPNG):
            list(_chunks(b"not a png at all"))

    def test_chunks_yields_type_and_payload(self):
        raw = SIG + ihdr(3, 2) + _chunk(b"IEND", b"")
        got = [(t, len(d)) for t, d in _chunks(raw)]
        self.assertEqual(got, [(b"IHDR", 13), (b"IEND", 0)])

    def test_crc_mismatch_rejected(self):
        good = SIG + ihdr(3, 2) + _chunk(b"IEND", b"")
        bad = bytearray(good)
        bad[-1] ^= 0xFF                      # corrupt the IEND CRC
        with self.assertRaises(CorruptPNG):
            list(_chunks(bytes(bad)))

    def test_truncated_chunk_rejected(self):
        raw = SIG + ihdr(3, 2)
        with self.assertRaises(CorruptPNG):
            list(_chunks(raw[:-4]))


class T0_2_HeaderValidation(unittest.TestCase):

    def test_supported_ihdr_returns_dimensions(self):
        self.assertEqual(_parse_ihdr(struct.pack(">IIBBBBB", 7, 5, 8, 2, 0, 0, 0)),
                         (7, 5))

    def test_zero_dimension_rejected(self):
        with self.assertRaises(CorruptPNG):
            _parse_ihdr(struct.pack(">IIBBBBB", 0, 5, 8, 2, 0, 0, 0))

    def test_unsupported_variants_rejected_by_name(self):
        cases = {
            "16-bit":     (16, 2, 0, 0, 0),
            "palette":    (8, 3, 0, 0, 0),
            "greyscale":  (8, 0, 0, 0, 0),
            "rgba":       (8, 6, 0, 0, 0),
            "interlaced": (8, 2, 0, 0, 1),
        }
        for label, (d, ct, cm, fm, il) in cases.items():
            with self.subTest(label):
                with self.assertRaises(UnsupportedPNG) as cm_:
                    _parse_ihdr(struct.pack(">IIBBBBB", 4, 4, d, ct, cm, fm, il))
                self.assertIn(str((d, ct, cm, fm, il)), str(cm_.exception))


class T0_3_PhysDpi(unittest.TestCase):

    def test_metre_unit_converts_to_dpi(self):
        # 11811 px/m == 300 dpi
        dpi = _parse_phys(struct.pack(">IIB", 11811, 11811, 1))
        self.assertAlmostEqual(dpi[0], 300.0, places=1)
        self.assertAlmostEqual(dpi[1], 300.0, places=1)

    def test_unit_zero_gives_none(self):
        self.assertIsNone(_parse_phys(struct.pack(">IIB", 100, 100, 0)))


def reference_decode(dec, w, h):
    """Deliberately naive per-byte unfilter. Slow, obvious, and the ORACLE
    for every fast path in the unit. Returns RGB bytes."""
    stride = w * 3 + 1
    prev = bytearray(w * 3)
    rows = []
    for r in range(h):
        ft = dec[r * stride]
        line = bytearray(dec[r * stride + 1:(r + 1) * stride])
        for i in range(len(line)):
            a = line[i - 3] if i >= 3 else 0
            b = prev[i]
            c = prev[i - 3] if i >= 3 else 0
            if ft == 0:
                pass
            elif ft == 1:
                line[i] = (line[i] + a) & 0xFF
            elif ft == 2:
                line[i] = (line[i] + b) & 0xFF
            elif ft == 3:
                line[i] = (line[i] + ((a + b) >> 1)) & 0xFF
            elif ft == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pred) & 0xFF
            else:
                raise ValueError(f"filter type {ft}")
        prev = line
        rows.append(bytes(line))
    return b"".join(rows)


def luma(rgb):
    """Rec.601, integer, round-half-up. The ONE definition; the unit must
    agree with it byte for byte."""
    return bytes((rgb[i] * 299 + rgb[i + 1] * 587 + rgb[i + 2] * 114 + 500)
                 // 1000 for i in range(0, len(rgb), 3))


def _encode_filter(ft, line, prev, bpp=3):
    out = bytearray(len(line))
    for i in range(len(line)):
        a = line[i - bpp] if i >= bpp else 0
        b = prev[i]
        c = prev[i - bpp] if i >= bpp else 0
        if ft == 0:
            out[i] = line[i]
        elif ft == 1:
            out[i] = (line[i] - a) & 0xFF
        elif ft == 2:
            out[i] = (line[i] - b) & 0xFF
        elif ft == 3:
            out[i] = (line[i] - ((a + b) >> 1)) & 0xFF
        elif ft == 4:
            p = a + b - c
            pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
            pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
            out[i] = (line[i] - pred) & 0xFF
        else:
            raise ValueError(f"filter type {ft}")
    return out


def build_png(rows, *, filters=None, phys=None, idat_split=1):
    """Assemble a png16m-shaped PNG. `rows` is a list of rows, each a list
    of (r, g, b) triples. `filters` is one filter type per row."""
    h = len(rows)
    w = len(rows[0])
    if filters is None:
        filters = [0] * h
    raw = bytearray()
    prev = bytearray(w * 3)
    for r in range(h):
        line = bytearray()
        for px in rows[r]:
            line.extend(px)
        raw.append(filters[r])
        raw.extend(_encode_filter(filters[r], line, prev))
        prev = line
    comp = zlib.compress(bytes(raw))
    parts = [SIG, ihdr(w, h)]
    if phys is not None:
        ppux, ppuy, unit = phys
        parts.append(_chunk(b"pHYs", struct.pack(">IIB", ppux, ppuy, unit)))
    step = max(1, len(comp) // idat_split)
    for i in range(0, len(comp), step):
        parts.append(_chunk(b"IDAT", comp[i:i + step]))
    parts.append(_chunk(b"IEND", b""))
    return b"".join(parts)


def raw_scanlines(png):
    """Inflate a PNG's IDAT stream back to filtered scanlines."""
    idat = b"".join(d for t, d in _chunks(png) if t == b"IDAT")
    return zlib.decompress(idat)


GRAD = [[(v, v, v) for v in range(x, x + 9)] for x in range(0, 60, 7)]
COLOUR = [[(x * 9 % 256, y * 31 % 256, (x + y) * 17 % 256) for x in range(9)]
          for y in range(9)]


class T0_4_TestInfrastructure(unittest.TestCase):

    def test_builder_round_trips_through_reference_all_filters(self):
        for ft in range(5):
            with self.subTest(filter=ft):
                png = build_png(GRAD, filters=[ft] * len(GRAD))
                got = reference_decode(raw_scanlines(png), 9, len(GRAD))
                want = bytes(v for row in GRAD for px in row for v in px)
                self.assertEqual(got, want)

    def test_builder_round_trips_mixed_filters_and_colour(self):
        fts = [i % 5 for i in range(len(COLOUR))]
        png = build_png(COLOUR, filters=fts)
        got = reference_decode(raw_scanlines(png), 9, len(COLOUR))
        want = bytes(v for row in COLOUR for px in row for v in px)
        self.assertEqual(got, want)

    def test_luma_is_identity_on_neutral_pixels(self):
        rgb = bytes(v for v in range(256) for _ in range(3))
        self.assertEqual(luma(rgb), bytes(range(256)))


def decoded_is_neutral(dec, w, h):
    rgb = reference_decode(dec, w, h)
    return rgb[0::3] == rgb[1::3] == rgb[2::3]


class T0_5_NeutralityProbe(unittest.TestCase):
    """G5: neutrality of the FILTERED stream equals neutrality of the
    DECODED image. The two-path decode is only exact if this holds."""

    def test_neutral_image_detected_under_every_filter(self):
        for ft in range(5):
            with self.subTest(filter=ft):
                png = build_png(GRAD, filters=[ft] * len(GRAD))
                dec = raw_scanlines(png)
                self.assertTrue(_is_neutral(dec, 9, len(GRAD)))

    def test_colour_image_detected_under_every_filter(self):
        for ft in range(5):
            with self.subTest(filter=ft):
                png = build_png(COLOUR, filters=[ft] * len(COLOUR))
                dec = raw_scanlines(png)
                self.assertFalse(_is_neutral(dec, 9, len(COLOUR)))

    def test_probe_agrees_with_full_decode_on_mixed_filters(self):
        for rows, label in ((GRAD, "neutral"), (COLOUR, "colour")):
            fts = [i % 5 for i in range(len(rows))]
            png = build_png(rows, filters=fts)
            dec = raw_scanlines(png)
            with self.subTest(label):
                self.assertEqual(_is_neutral(dec, 9, len(rows)),
                                 decoded_is_neutral(dec, 9, len(rows)))

    def test_single_off_channel_pixel_breaks_neutrality(self):
        rows = [[(7, 7, 7)] * 9 for _ in range(9)]
        rows[4][4] = (7, 8, 7)          # one channel, one pixel, off by one
        for ft in range(5):
            with self.subTest(filter=ft):
                dec = raw_scanlines(build_png(rows, filters=[ft] * 9))
                self.assertFalse(_is_neutral(dec, 9, 9))
