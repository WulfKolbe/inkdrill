"""U0's second input route: `pgmraw` ingest. Hermetic.

Fixtures are built as bytes here, so each test names the header
situation it checks. `tests/test_pnmio_corpus.py` compares the two
routes on real ghostscript output.
"""

import unittest

from inkdrill.pnmio import (CorruptPNM, NoResolution, PnmImage,
                            UnsupportedPNM, load_mask, load_masks,
                            read_pnm, read_pnm_stream)


def p5(w, h, data, *, maxval=255, header_extra=b""):
    return (b"P5\n" + header_extra + b"%d %d\n%d\n" % (w, h, maxval)
            + bytes(data))


class T0_10_Resolution(unittest.TestCase):
    """G5: PNM cannot carry dpi, so it must be supplied."""

    def test_omitting_dpi_raises(self):
        with self.assertRaises(NoResolution):
            read_pnm(p5(2, 2, [0, 1, 2, 3]))

    def test_a_scalar_dpi_becomes_a_pair(self):
        self.assertEqual(read_pnm(p5(2, 2, [0, 1, 2, 3]), dpi=400).dpi,
                         (400.0, 400.0))

    def test_an_anisotropic_pair_is_kept(self):
        self.assertEqual(read_pnm(p5(2, 2, [0] * 4), dpi=(300, 600)).dpi,
                         (300.0, 600.0))

    def test_a_non_positive_dpi_raises(self):
        for bad in (0, -1, (400, 0)):
            with self.subTest(dpi=bad):
                with self.assertRaises(NoResolution):
                    read_pnm(p5(2, 2, [0] * 4), dpi=bad)


class T0_11_Header(unittest.TestCase):
    """G3, G4: the parts of the format that bite."""

    def test_comments_are_skipped_between_any_two_tokens(self):
        raw = (b"P5\n# rendered by ghostscript\n2 "
               b"# between width and height\n2\n255\n" + bytes([1, 2, 3, 4]))
        img = read_pnm(raw, dpi=400)
        self.assertEqual((img.width, img.height), (2, 2))
        self.assertEqual(img.gray, bytes([1, 2, 3, 4]))

    def test_exactly_one_whitespace_byte_precedes_the_raster(self):
        """G4, and the classic PNM bug. A second whitespace byte is
        DATA -- skipping it shifts every sample by one and silently
        produces a plausible image of the wrong content."""
        raw = b"P5\n1 2\n255\n" + bytes([32, 9])     # both samples ARE ws
        self.assertEqual(read_pnm(raw, dpi=400).gray, bytes([32, 9]))

    def test_a_truncated_raster_raises(self):
        with self.assertRaises(CorruptPNM):
            read_pnm(p5(4, 4, [0] * 10), dpi=400)

    def test_trailing_bytes_after_the_raster_raise(self):
        with self.assertRaises(CorruptPNM):
            read_pnm(p5(2, 2, [0] * 4) + b"\x00" * 8, dpi=400)

    def test_a_non_positive_extent_raises(self):
        with self.assertRaises(CorruptPNM):
            read_pnm(b"P5\n0 4\n255\n", dpi=400)

    def test_a_malformed_header_raises(self):
        with self.assertRaises(CorruptPNM):
            read_pnm(b"P5\nwide tall\n255\n\x00", dpi=400)


class T0_12_Scope(unittest.TestCase):
    """G2: everything outside the stated scope fails loudly."""

    def test_P6_is_refused_and_says_why(self):
        with self.assertRaises(UnsupportedPNM) as cm:
            read_pnm(b"P6\n1 1\n255\n\x00\x00\x00", dpi=400)
        self.assertIn("luma", str(cm.exception))

    def test_P4_is_refused_as_a_different_unpacking(self):
        with self.assertRaises(UnsupportedPNM) as cm:
            read_pnm(b"P4\n8 1\n\xff", dpi=400)
        self.assertIn("bit per pixel", str(cm.exception))

    def test_a_16_bit_pgm_is_refused_rather_than_halving_the_width(self):
        with self.assertRaises(UnsupportedPNM):
            read_pnm(p5(2, 2, [0] * 8, maxval=65535), dpi=400)

    def test_a_non_pnm_file_is_refused(self):
        with self.assertRaises(UnsupportedPNM):
            read_pnm(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40, dpi=400)

    def test_an_empty_file_raises(self):
        with self.assertRaises(CorruptPNM):
            read_pnm(b"", dpi=400)


class T0_13_Mask(unittest.TestCase):
    """G6: the same mask U2 would build, via U2."""

    def test_the_threshold_is_u2s_and_strict(self):
        raw = p5(4, 1, [0, 127, 128, 255])
        m = load_mask(raw, dpi=400, threshold=128)
        self.assertEqual(list(m.data), [0xFF, 0xFF, 0x00, 0x00])

    def test_P2_and_P5_agree_on_the_same_image(self):
        """The ASCII form exists so a fixture is readable; it must not
        be a second decoder."""
        a = read_pnm(p5(2, 2, [0, 64, 192, 255]), dpi=400)
        b = read_pnm(b"P2\n2 2\n255\n0 64 192 255\n", dpi=400)
        self.assertEqual(a.gray, b.gray)

    def test_a_P2_with_the_wrong_sample_count_raises(self):
        with self.assertRaises(CorruptPNM):
            read_pnm(b"P2\n2 2\n255\n0 64 192\n", dpi=400)


if __name__ == "__main__":
    unittest.main()


class T0b_9_ConcatenatedStream(unittest.TestCase):
    """T3: `gs -sOutputFile=%stdout` writes one PNM per page, back to
    back, so a multi-page render is a STREAM and not a file.

    `read_pnm` still refuses trailing bytes -- that refusal is how a
    caller learns it passed something other than what it thought. The
    stream is a different function, not a relaxed flag.
    """

    @staticmethod
    def _pgm(w, h, fill, comment=False):
        head = b"P5\n"
        if comment:
            head += b"# Image generated by GPL Ghostscript (device=pgmraw)\n"
        return head + b"%d %d\n255\n" % (w, h) + bytes([fill]) * (w * h)

    def test_four_images_come_back_as_four(self):
        raw = b"".join(self._pgm(4, 3, v) for v in (10, 20, 30, 40))
        got = list(read_pnm_stream(raw, dpi=400))
        self.assertEqual(len(got), 4)
        self.assertEqual([g.gray[0] for g in got], [10, 20, 30, 40])

    def test_the_ghostscript_comment_line_is_skipped(self):
        """gs writes a `#` line after the magic. Every real stream has
        one, so a fixture without it would not be the thing."""
        raw = b"".join(self._pgm(4, 3, v, comment=True) for v in (7, 9))
        self.assertEqual([g.gray[0] for g in read_pnm_stream(raw, dpi=400)],
                         [7, 9])

    def test_images_of_DIFFERENT_sizes_stream(self):
        """Page sizes vary within a document. A reader that assumed the
        first header applied to all would pass a same-size fixture."""
        raw = self._pgm(4, 3, 1) + self._pgm(7, 2, 2) + self._pgm(2, 5, 3)
        self.assertEqual([(g.width, g.height)
                          for g in read_pnm_stream(raw, dpi=400)],
                         [(4, 3), (7, 2), (2, 5)])

    def test_a_SINGLE_image_still_refuses_trailing_bytes(self):
        """The contract `read_pnm` keeps. Both sides asserted: the
        clean single image decodes, the one with a stray byte raises."""
        one = self._pgm(4, 3, 5)
        self.assertEqual(read_pnm(one, dpi=400).gray[0], 5)
        with self.assertRaises(CorruptPNM):
            read_pnm(one + b"\x00", dpi=400)

    def test_the_stream_ACCEPTS_what_the_single_reader_refuses(self):
        """The other half of the same guard -- otherwise the stream
        could be `read_pnm` with the check deleted and nothing would
        notice."""
        two = self._pgm(4, 3, 5) + self._pgm(4, 3, 6)
        with self.assertRaises(CorruptPNM):
            read_pnm(two, dpi=400)
        self.assertEqual(len(list(read_pnm_stream(two, dpi=400))), 2)

    def test_trailing_whitespace_is_not_another_image(self):
        raw = self._pgm(4, 3, 5) + b"\n\n"
        self.assertEqual(len(list(read_pnm_stream(raw, dpi=400))), 1)

    def test_a_stream_without_dpi_raises_like_a_file(self):
        with self.assertRaises(NoResolution):
            list(read_pnm_stream(self._pgm(4, 3, 5)))

    def test_masks_stream_one_per_page(self):
        raw = self._pgm(4, 3, 0) + self._pgm(4, 3, 255)
        got = list(load_masks(raw, dpi=400, threshold=128))
        self.assertEqual([m.ink_count for m in got], [12, 0])


class T0b_10_AutoPolarity(unittest.TestCase):
    """`ink_is_dark="auto"` (T11): binarize dark-as-ink; more ink than
    background flips. Opt-in, never the default -- a silent flip under
    an existing caller would re-polarity every measurement harness.
    """

    @staticmethod
    def _slide():
        """Light-on-dark: three white marks on a dark ground -- the
        chalkboard shape, where the dark board is one component and the
        marks are many."""
        W, H = 30, 12
        g = bytearray([20] * (W * H))              # dark ground
        for x0 in (4, 14, 24):
            for y in range(3, 9):
                for x in range(x0, x0 + 4):
                    g[y * W + x] = 240             # light marks
        return bytes(b"P5\n30 12\n255\n") + bytes(g)

    def test_a_slide_flips_ink_below_20pc_and_MORE_components(self):
        from inkdrill.sweep import Capture, sweep
        unflipped = load_mask(self._slide(), dpi=72, threshold=128)
        auto = load_mask(self._slide(), dpi=72, threshold=128,
                         ink_is_dark="auto")
        frac = auto.ink_count / (auto.width * auto.height)
        self.assertLessEqual(frac, 0.20)
        n_auto = len(sweep(auto, conn=8).components)
        n_raw = len(sweep(unflipped, conn=8).components)
        self.assertGreater(n_auto, n_raw)
        self.assertEqual(n_auto, 3)

    def test_a_normal_page_is_byte_identical_under_auto(self):
        """The accepting side: auto must be a no-op on the print
        convention, or every harness that adopts it drifts."""
        page = bytes(b"P5\n10 6\n255\n") + bytes(
            [20 if i % 7 == 0 else 240 for i in range(60)])
        self.assertEqual(load_mask(page, dpi=72, threshold=128,
                                   ink_is_dark="auto"),
                         load_mask(page, dpi=72, threshold=128))

    def test_the_png_route_shares_the_same_cut(self):
        """One definition (raster.looks_inverted); the PNG reader must
        flip on the same fixture the PNM reader flips on."""
        from tests.test_pngio import build_png
        from inkdrill.pngio import load_mask as png_load
        rows = [[(20, 20, 20)] * 30 for _ in range(12)]
        for x0 in (4, 14, 24):
            for y in range(3, 9):
                for x in range(x0, x0 + 4):
                    rows[y][x] = (240, 240, 240)
        png = build_png(rows)
        auto = png_load(png, threshold=128, ink_is_dark="auto")
        self.assertLessEqual(auto.ink_count / (30 * 12), 0.20)
