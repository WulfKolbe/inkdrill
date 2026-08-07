"""Unit 0 tests. Every test name is quoted verbatim in the status report."""

import random
import struct
import unittest
import zlib

from inkdrill.io import CorruptPNG, UnsupportedPNG, _chunks, _parse_ihdr, _parse_phys, _is_neutral, _decode_gray_neutral, _decode_gray_colour
from inkdrill.io import PngImage, read_png, load_mask
from inkdrill.raster import INK, BG

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

    def test_zero_height_rejected(self):
        """test_zero_dimension_rejected only exercises w == 0; the guard is
        `w == 0 or h == 0` and a mutant narrowing it to `w == 0` alone
        would still pass every other test without this."""
        with self.assertRaises(CorruptPNG):
            _parse_ihdr(struct.pack(">IIBBBBB", 5, 0, 8, 2, 0, 0, 0))

    def test_ihdr_wrong_length_rejected(self):
        """Without this guard a short/long IHDR payload would escape as a
        bare struct.error, not the module's declared CorruptPNG/ValueError
        contract."""
        with self.assertRaises(CorruptPNG):
            _parse_ihdr(b"\x00" * 10)

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

    def test_phys_wrong_length_rejected(self):
        """Without this guard a short/long pHYs payload would escape as a
        bare struct.error, not the module's declared CorruptPNG/ValueError
        contract."""
        with self.assertRaises(CorruptPNG):
            _parse_phys(b"\x00" * 5)


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

    def test_blue_only_difference_breaks_neutrality(self):
        """The existing off-channel fixture (7,8,7) differs in G, which
        trips the FIRST slice comparison (R vs G) on its own. A pixel
        where only BLUE differs from an equal R/G exercises the SECOND
        comparison (G vs B) instead -- without this, `or` silently
        mutating to `and`, or the second comparison being deleted
        entirely, both still pass every other test."""
        rows = [[(7, 7, 7)] * 9 for _ in range(9)]
        rows[4][4] = (7, 7, 8)          # R == G, only blue differs
        for ft in range(5):
            with self.subTest(filter=ft):
                dec = raw_scanlines(build_png(rows, filters=[ft] * 9))
                self.assertFalse(_is_neutral(dec, 9, 9))

    def test_red_only_difference_breaks_neutrality(self):
        """Companion to test_blue_only_difference_breaks_neutrality: only
        RED differs from an equal G/B."""
        rows = [[(7, 7, 7)] * 9 for _ in range(9)]
        rows[4][4] = (8, 7, 7)          # G == B, only red differs
        for ft in range(5):
            with self.subTest(filter=ft):
                dec = raw_scanlines(build_png(rows, filters=[ft] * 9))
                self.assertFalse(_is_neutral(dec, 9, 9))

    def test_undersized_buffer_does_not_raise(self):
        """_is_neutral does not itself validate dec's length -- bytes
        slicing silently truncates on a short buffer rather than raising.
        This is why read_png must check the inflated length first."""
        dec = raw_scanlines(build_png(GRAD, filters=[2] * len(GRAD)))
        short = dec[:5]          # far shorter than h * (w*3+1)
        _is_neutral(short, 9, len(GRAD))          # must not raise


class T0_6_NeutralFastPath(unittest.TestCase):
    """G4: byte-identical to the oracle."""

    def test_matches_oracle_for_every_filter(self):
        for ft in range(5):
            with self.subTest(filter=ft):
                dec = raw_scanlines(build_png(GRAD, filters=[ft] * len(GRAD)))
                got = _decode_gray_neutral(dec, 9, len(GRAD))
                self.assertEqual(got, reference_decode(dec, 9, len(GRAD))[0::3])

    def test_matches_oracle_on_random_masks_mixed_filters(self):
        rng = random.Random(20260807)
        for trial in range(20):
            w = rng.randint(1, 17)
            h = rng.randint(1, 17)
            rows = [[(v, v, v) for v in
                     (rng.randrange(256) for _ in range(w))] for _ in range(h)]
            fts = [rng.randrange(5) for _ in range(h)]
            dec = raw_scanlines(build_png(rows, filters=fts))
            with self.subTest(trial=trial, w=w, h=h):
                self.assertEqual(_decode_gray_neutral(dec, w, h),
                                 reference_decode(dec, w, h)[0::3])

    def test_output_length_is_exactly_w_times_h(self):
        dec = raw_scanlines(build_png(GRAD, filters=[2] * len(GRAD)))
        self.assertEqual(len(_decode_gray_neutral(dec, 9, len(GRAD))),
                         9 * len(GRAD))

    def test_single_pixel_and_single_row_and_single_column(self):
        cases = {"1x1": ([[(9, 9, 9)]], 1, 1),
                 "1 wide": ([[(v, v, v)] for v in (3, 40, 200, 7)], 1, 4),
                 "1 tall": ([[(v, v, v) for v in (3, 40, 200, 7)]], 4, 1)}
        for label, (rows, w, h) in cases.items():
            for ft in range(5):
                dec = raw_scanlines(build_png(rows, filters=[ft] * h))
                with self.subTest(label, filter=ft):
                    self.assertEqual(_decode_gray_neutral(dec, w, h),
                                     reference_decode(dec, w, h)[0::3])

    def test_even_and_odd_widths(self):
        """The SWAR masks are built from `width`; a parity error there
        would corrupt exactly one edge column."""
        for w in (2, 3, 8, 9, 16, 17):
            rows = [[(x * 13 % 256,) * 3 for x in range(w)] for _ in range(6)]
            dec = raw_scanlines(build_png(rows, filters=[2, 1, 4, 3, 0, 2]))
            with self.subTest(width=w):
                self.assertEqual(_decode_gray_neutral(dec, w, 6),
                                 reference_decode(dec, w, 6)[0::3])

    def test_unknown_filter_type_rejected(self):
        """A filter byte outside 0-4 must raise, not silently decode as
        filter 0 (a silently wrong image)."""
        dec = bytes([5, 0, 0, 0])          # filter byte 5, one 1x1 row
        with self.assertRaises(CorruptPNG):
            _decode_gray_neutral(dec, 1, 1)


class T0_7_ColourPath(unittest.TestCase):

    def test_matches_oracle_luma_for_every_filter(self):
        for ft in range(5):
            with self.subTest(filter=ft):
                dec = raw_scanlines(build_png(COLOUR, filters=[ft] * len(COLOUR)))
                self.assertEqual(_decode_gray_colour(dec, 9, len(COLOUR)),
                                 luma(reference_decode(dec, 9, len(COLOUR))))

    def test_matches_oracle_luma_on_random_colour_mixed_filters(self):
        rng = random.Random(8072026)
        for trial in range(20):
            w = rng.randint(1, 17)
            h = rng.randint(1, 17)
            rows = [[(rng.randrange(256), rng.randrange(256), rng.randrange(256))
                     for _ in range(w)] for _ in range(h)]
            fts = [rng.randrange(5) for _ in range(h)]
            dec = raw_scanlines(build_png(rows, filters=fts))
            with self.subTest(trial=trial, w=w, h=h):
                self.assertEqual(_decode_gray_colour(dec, w, h),
                                 luma(reference_decode(dec, w, h)))

    def test_both_paths_agree_on_neutral_input(self):
        """A neutral image must decode identically whichever path runs --
        luma of (v, v, v) is exactly v."""
        for ft in range(5):
            dec = raw_scanlines(build_png(GRAD, filters=[ft] * len(GRAD)))
            with self.subTest(filter=ft):
                self.assertEqual(_decode_gray_colour(dec, 9, len(GRAD)),
                                 _decode_gray_neutral(dec, 9, len(GRAD)))

    def test_unknown_filter_type_rejected(self):
        """A filter byte outside 0-4 must raise, not silently decode as
        filter 0 (a silently wrong image)."""
        dec = bytes([5, 0, 0, 0, 0, 0, 0])   # filter byte 5, one 2px row
        with self.assertRaises(CorruptPNG):
            _decode_gray_colour(dec, 2, 1)

    def test_luma_coefficients_are_pinned_by_hand_computed_values(self):
        """`luma()` above is a SHARED definition with `_decode_gray_colour`,
        not an independent oracle: swapping 299 and 114 in BOTH `io.py` and
        `luma()` here leaves every other test in this file passing, because
        the two sides still agree with each other. The values below are
        computed by hand, outside both implementations, so a shared swap
        has something to disagree with:

            red   (255, 0, 0): (255*299 + 500) // 1000 = 76
            green (0, 255, 0): (255*587 + 500) // 1000 = 150
            blue  (0, 0, 255): (255*114 + 500) // 1000 = 29

        Checked against the test helper `luma()` directly, and against
        `_decode_gray_colour` through a built PNG -- so a coefficient swap
        shared by both implementations is caught on both sides."""
        cases = [((255, 0, 0), 76), ((0, 255, 0), 150), ((0, 0, 255), 29)]
        for rgb, want in cases:
            with self.subTest(rgb=rgb):
                self.assertEqual(luma(bytes(rgb)), bytes([want]))
                rows = [[rgb] * 9 for _ in range(9)]
                dec = raw_scanlines(build_png(rows, filters=[0] * 9))
                self.assertEqual(_decode_gray_colour(dec, 9, 9), bytes([want]) * 81)

    def test_luma_round_half_up_term_is_pinned(self):
        """test_luma_is_identity_on_neutral_pixels cannot pin the `+ 500`
        round-half-up term: on a neutral pixel (v, v, v) the weighted sum
        is always exactly v*1000, so its remainder mod 1000 is always 0 and
        rounding never has anything to do. This pixel's weighted sum has
        remainder exactly 500 mod 1000, computed by hand:

            (0, 0, 250): 0*299 + 0*587 + 250*114 = 28500
            28500 % 1000 == 500
            (28500 + 500) // 1000 = 29     -- floor alone would give 28

        so a decoder that truncated instead of rounding half up would
        disagree with this value."""
        rgb = (0, 0, 250)
        self.assertEqual(luma(bytes(rgb)), bytes([29]))
        rows = [[rgb] * 9 for _ in range(9)]
        dec = raw_scanlines(build_png(rows, filters=[0] * 9))
        self.assertEqual(_decode_gray_colour(dec, 9, 9), bytes([29]) * 81)


class T0_8_ReadPng(unittest.TestCase):

    def test_dimensions_and_length(self):
        img = read_png(build_png(GRAD, filters=[2] * len(GRAD)))
        self.assertEqual((img.width, img.height), (9, len(GRAD)))
        self.assertEqual(len(img.gray), 9 * len(GRAD))       # G3

    def test_neutral_flag_reports_the_path_taken(self):
        self.assertTrue(read_png(build_png(GRAD)).neutral)
        self.assertFalse(read_png(build_png(COLOUR)).neutral)

    def test_decode_paths_are_distinct_functions(self):
        """Nothing else asserts the fast path is actually TAKEN: mutating
        read_png to dispatch _decode_gray_colour on both branches would
        pass every other test, silently erasing the unit's headline
        13.3x speedup with no regression guard."""
        self.assertIsNot(_decode_gray_neutral, _decode_gray_colour)

    def test_gray_matches_oracle_luma_either_path(self):
        for rows, label in ((GRAD, "neutral"), (COLOUR, "colour")):
            fts = [i % 5 for i in range(len(rows))]
            png = build_png(rows, filters=fts)
            with self.subTest(label):
                self.assertEqual(read_png(png).gray,
                                 luma(reference_decode(raw_scanlines(png), 9,
                                                       len(rows))))

    def test_multi_idat_is_concatenated_before_inflate(self):
        """G1. A decoder that inflates each IDAT separately fails here."""
        one = read_png(build_png(GRAD, filters=[4] * len(GRAD), idat_split=1))
        many = read_png(build_png(GRAD, filters=[4] * len(GRAD), idat_split=7))
        self.assertEqual(one.gray, many.gray)

    def test_dpi_from_phys(self):
        img = read_png(build_png(GRAD, phys=(11811, 11811, 1)))
        self.assertAlmostEqual(img.dpi[0], 300.0, places=1)

    def test_dpi_none_when_phys_absent(self):
        self.assertIsNone(read_png(build_png(GRAD)).dpi)

    def test_missing_ihdr_rejected(self):
        raw = SIG + _chunk(b"IEND", b"")
        with self.assertRaises(CorruptPNG):
            read_png(raw)

    def test_missing_idat_rejected(self):
        """Must fail via the explicit `no IDAT chunk` guard, not merely by
        `zlib.decompress(b"")` raising further down -- both paths raise
        CorruptPNG, so without checking the message this test cannot tell
        the guard was ever reached."""
        raw = SIG + ihdr(4, 4) + _chunk(b"IEND", b"")
        with self.assertRaises(CorruptPNG) as cm:
            read_png(raw)
        self.assertIn("no IDAT", str(cm.exception))

    def test_duplicate_ihdr_rejected(self):
        """A second IHDR must not silently overwrite width/height -- that
        is how a byte-length collision (e.g. 1x4 vs 5x1, both 16 bytes)
        could mis-decode the pixel data of one shape as another. The IDAT
        below is valid filter-0 data sized for the SECOND shape (5x1);
        with no IDAT at all the pre-existing `if not idat` guard would
        raise first and the duplicate-IHDR guard would never be
        exercised, so a real payload is required to make the guard's
        removal genuinely mis-decode rather than merely raise elsewhere."""
        pixels = bytes(range(15))                    # 5 RGB pixels
        scanline = bytes([0]) + pixels                # filter 0
        idat = _chunk(b"IDAT", zlib.compress(scanline))
        raw = SIG + ihdr(1, 4) + ihdr(5, 1) + idat + _chunk(b"IEND", b"")
        with self.assertRaises(CorruptPNG):
            read_png(raw)

    def test_inflated_length_mismatch_rejected(self):
        """IDAT that inflates to the wrong number of bytes must raise, not
        silently produce a short image."""
        raw = SIG + ihdr(9, 9) + _chunk(b"IDAT", zlib.compress(b"\x00" * 10)) \
            + _chunk(b"IEND", b"")
        with self.assertRaises(CorruptPNG):
            read_png(raw)

    def test_bad_deflate_stream_rejected(self):
        raw = SIG + ihdr(4, 4) + _chunk(b"IDAT", b"not deflate") \
            + _chunk(b"IEND", b"")
        with self.assertRaises(CorruptPNG):
            read_png(raw)

    def test_reads_from_path(self):
        import pathlib
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "page.png"
            p.write_bytes(build_png(GRAD, filters=[2] * len(GRAD)))
            self.assertEqual(read_png(p).gray, read_png(p.read_bytes()).gray)


class T0_9_LoadMask(unittest.TestCase):

    def test_threshold_is_applied_by_u2(self):
        rows = [[(10, 10, 10), (250, 250, 250)]]
        mask = load_mask(build_png(rows), threshold=128)
        self.assertEqual(mask.width, 2)
        self.assertEqual(mask.height, 1)
        self.assertEqual(mask.data, bytes([INK, BG]))

    def test_polarity_flag_reaches_binarize(self):
        rows = [[(10, 10, 10), (250, 250, 250)]]
        mask = load_mask(build_png(rows), threshold=128, ink_is_dark=False)
        self.assertEqual(mask.data, bytes([BG, INK]))
