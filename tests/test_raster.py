"""Unit 2 tests. Every test name is quoted verbatim in the status report."""

import random
import unittest

from inkdrill.raster import (BG, INK, InkMask, InvalidAxis, Rect, Run,
                             binarize, iter_runs,
                             profile, stroke_mode)


def pixels_from_runs(mask, axis):
    """Every pixel covered by the runs, as an image-space set."""
    out = set()
    for r in iter_runs(mask, axis):
        out.update(r.image_pixels(axis))
    return out


def pixels_from_mask(mask):
    return {(x, y)
            for y in range(mask.height)
            for x in range(mask.width)
            if mask.at(x, y)}


def random_mask(rng, w, h, density=0.35):
    buf = bytes(INK if rng.random() < density else BG for _ in range(w * h))
    return InkMask(buf, w, h)


class T2_1_MaskConstruction(unittest.TestCase):

    def test_from_rows_round_trip(self):
        rows = ["..#..", ".###.", "#####", ".#.#."]
        m = InkMask.from_rows(rows)
        self.assertEqual(m.width, 5)
        self.assertEqual(m.height, 4)
        self.assertEqual(m.to_rows(), rows)

    def test_ink_count(self):
        m = InkMask.from_rows(["#.#", ".#.", "#.#"])
        self.assertEqual(m.ink_count, 5)

    def test_length_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            InkMask(b"\xff\x00", 3, 3)

    def test_ragged_rows_rejected(self):
        with self.assertRaises(ValueError):
            InkMask.from_rows(["##", "###"])

    def test_at_is_false_outside(self):
        m = InkMask.from_rows(["#"])
        self.assertTrue(m.at(0, 0))
        self.assertFalse(m.at(-1, 0))
        self.assertFalse(m.at(0, 1))

    def test_inverted_is_involution(self):
        rng = random.Random(11)
        m = random_mask(rng, 9, 7)
        self.assertEqual(m.inverted().inverted(), m)
        self.assertEqual(m.inverted().ink_count, 9 * 7 - m.ink_count)

    def test_empty_mask(self):
        m = InkMask.empty(4, 3)
        self.assertEqual(m.ink_count, 0)
        self.assertEqual(list(iter_runs(m, "row")), [])


class T2_2_Binarize(unittest.TestCase):
    """G6: threshold comparison is strict, and the polarity flag is honoured."""

    def test_strict_less_than(self):
        gray = bytes([126, 127, 128, 129])
        m = binarize(gray, 4, 1, threshold=128)
        self.assertEqual(m.to_rows(), ["##.."])

    def test_threshold_zero_gives_empty(self):
        gray = bytes(range(256))
        m = binarize(gray, 256, 1, threshold=0)
        self.assertEqual(m.ink_count, 0)

    def test_threshold_256_gives_full(self):
        gray = bytes(range(256))
        m = binarize(gray, 256, 1, threshold=256)
        self.assertEqual(m.ink_count, 256)

    def test_ink_is_light_polarity(self):
        gray = bytes([126, 127, 128, 129])
        m = binarize(gray, 4, 1, threshold=128, ink_is_dark=False)
        self.assertEqual(m.to_rows(), ["..##"])

    def test_encoding_is_only_ff_and_00(self):
        rng = random.Random(12)
        gray = bytes(rng.randrange(256) for _ in range(64))
        m = binarize(gray, 8, 8, threshold=200)
        self.assertEqual(set(m.data) - {INK, BG}, set())

    def test_size_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            binarize(b"\x00" * 10, 4, 4)

    def test_out_of_range_threshold_rejected(self):
        with self.assertRaises(ValueError):
            binarize(b"\x00" * 4, 2, 2, threshold=-1)


class T2_3_RunExtraction(unittest.TestCase):
    """G1-G3 on hand-checked fixtures."""

    FIX = [
        "#.###",
        ".....",
        "#####",
        "##..#",
        "....#",
    ]

    def test_row_runs_exact(self):
        m = InkMask.from_rows(self.FIX)
        self.assertEqual(list(iter_runs(m, "row")), [
            Run(0, 0, 0), Run(0, 2, 4),
            Run(2, 0, 4),
            Run(3, 0, 1), Run(3, 4, 4),
            Run(4, 4, 4),
        ])

    def test_col_runs_exact(self):
        m = InkMask.from_rows(self.FIX)
        self.assertEqual(list(iter_runs(m, "col")), [
            Run(0, 0, 0), Run(0, 2, 3),
            Run(1, 2, 3),
            Run(2, 0, 0), Run(2, 2, 2),
            Run(3, 0, 0), Run(3, 2, 2),
            Run(4, 0, 0), Run(4, 2, 4),
        ])

    def test_runs_are_maximal(self):
        """G1: no two runs in a line are adjacent or overlapping."""
        rng = random.Random(13)
        for axis in ("row", "col"):
            m = random_mask(rng, 17, 13)
            prev = None
            for r in iter_runs(m, axis):
                self.assertLessEqual(r.lo, r.hi)
                if prev is not None and prev.line == r.line:
                    self.assertGreater(r.lo, prev.hi + 1,
                                       "adjacent runs were not merged")
                prev = r

    def test_runs_never_span_lines(self):
        """G2: a full-width block must give one run per line, not one run."""
        m = InkMask.from_rows(["###", "###", "###"])
        rows = list(iter_runs(m, "row"))
        self.assertEqual(rows, [Run(0, 0, 2), Run(1, 0, 2), Run(2, 0, 2)])
        cols = list(iter_runs(m, "col"))
        self.assertEqual(cols, [Run(0, 0, 2), Run(1, 0, 2), Run(2, 0, 2)])

    def test_scan_order(self):
        """G3: line ascending, then lo ascending."""
        rng = random.Random(14)
        for axis in ("row", "col"):
            m = random_mask(rng, 21, 19)
            keys = [(r.line, r.lo) for r in iter_runs(m, axis)]
            self.assertEqual(keys, sorted(keys))

    def test_run_touching_both_edges(self):
        m = InkMask.from_rows(["#####"])
        self.assertEqual(list(iter_runs(m, "row")), [Run(0, 0, 4)])

    def test_bad_axis_rejected(self):
        m = InkMask.from_rows(["#"])
        with self.assertRaises(InvalidAxis):
            list(iter_runs(m, "diagonal"))


class T2_4_AxisEquivalence(unittest.TestCase):
    """G4/G5 -- the foundation every later axis-invariance claim rests on."""

    def test_row_and_col_cover_identical_pixels(self):
        rng = random.Random(15)
        for _ in range(50):
            w, h = rng.randrange(1, 24), rng.randrange(1, 24)
            m = random_mask(rng, w, h, density=rng.uniform(0.05, 0.9))
            truth = pixels_from_mask(m)
            self.assertEqual(pixels_from_runs(m, "row"), truth)
            self.assertEqual(pixels_from_runs(m, "col"), truth)

    def test_run_lengths_sum_to_ink_count(self):
        rng = random.Random(16)
        for _ in range(50):
            w, h = rng.randrange(1, 20), rng.randrange(1, 20)
            m = random_mask(rng, w, h)
            for axis in ("row", "col"):
                total = sum(r.length for r in iter_runs(m, axis))
                self.assertEqual(total, m.ink_count)

    def test_image_span_matches_pixels(self):
        m = InkMask.from_rows(["..##.", "#....."[:5]])
        for axis in ("row", "col"):
            for r in iter_runs(m, axis):
                px = list(r.image_pixels(axis))
                x0, y0, x1, y1 = r.image_span(axis)
                self.assertEqual(px[0], (x0, y0))
                self.assertEqual(px[-1], (x1, y1))


class T2_5_RegionOfInterest(unittest.TestCase):
    """G7 -- ROI is a mask derivation, invisible to the scan."""

    FIX = ["#####", "#...#", "#.#.#", "#...#", "#####"]

    def test_crop_offsets(self):
        m = InkMask.from_rows(self.FIX)
        sub, ox, oy = m.crop(Rect(1, 1, 4, 4))
        self.assertEqual((ox, oy), (1, 1))
        self.assertEqual(sub.to_rows(), ["...", ".#.", "..."])

    def test_crop_is_clipped(self):
        m = InkMask.from_rows(self.FIX)
        sub, ox, oy = m.crop(Rect(-3, -3, 99, 99))
        self.assertEqual((ox, oy), (0, 0))
        self.assertEqual(sub.to_rows(), self.FIX)

    def test_crop_empty_rect(self):
        m = InkMask.from_rows(self.FIX)
        sub, _, _ = m.crop(Rect(2, 2, 2, 2))
        self.assertEqual(sub.width, 0)
        self.assertEqual(list(iter_runs(sub, "row")), [])

    def test_clear_regions(self):
        m = InkMask.from_rows(self.FIX)
        out = m.clear_regions([Rect(0, 0, 5, 1)])
        self.assertEqual(out.to_rows(),
                         [".....", "#...#", "#.#.#", "#...#", "#####"])

    def test_keep_regions_is_complement_of_clear(self):
        rng = random.Random(17)
        m = random_mask(rng, 13, 11)
        rects = [Rect(2, 1, 7, 5), Rect(8, 6, 12, 10)]
        kept, cleared = m.keep_regions(rects), m.clear_regions(rects)
        self.assertEqual(kept.ink_count + cleared.ink_count, m.ink_count)
        for y in range(m.height):
            for x in range(m.width):
                self.assertFalse(kept.at(x, y) and cleared.at(x, y))
                self.assertEqual(kept.at(x, y) or cleared.at(x, y), m.at(x, y))

    def test_roi_runs_are_restriction_of_full_runs(self):
        rng = random.Random(18)
        m = random_mask(rng, 15, 15)
        rect = Rect(3, 2, 11, 9)
        kept = m.keep_regions([rect])
        full = pixels_from_runs(m, "row")
        inside = {(x, y) for (x, y) in full
                  if rect.x0 <= x < rect.x1 and rect.y0 <= y < rect.y1}
        self.assertEqual(pixels_from_runs(kept, "row"), inside)

    def test_rect_helpers(self):
        r = Rect(2, 3, 8, 10)
        self.assertEqual((r.width, r.height), (6, 7))
        self.assertFalse(r.empty)
        self.assertTrue(Rect(5, 5, 5, 9).empty)
        self.assertEqual(r.padded(2), Rect(0, 1, 10, 12))


if __name__ == "__main__":
    unittest.main(verbosity=2)


class T2_9_Profile(unittest.TestCase):
    """T13: per-line (coverage, extent, run_count), one iter_runs pass."""

    def test_coverage_extent_and_count_differ_on_a_gapped_line(self):
        """The three numbers are distinct exactly when a line has gaps
        -- a fixture without a gap could not tell them apart."""
        m = InkMask(bytes([0xFF] * 2 + [0] * 3 + [0xFF] * 3), 8, 1)
        self.assertEqual(profile(m), [(5, 8, 2)])

    def test_an_empty_line_is_data_not_a_hole(self):
        m = InkMask(bytes([0xFF] * 4 + [0] * 4 + [0xFF] * 4), 4, 3)
        self.assertEqual(profile(m), [(4, 4, 1), (0, 0, 0), (4, 4, 1)])

    def test_the_column_axis_profiles_columns(self):
        m = InkMask(bytes([0xFF, 0,
                           0xFF, 0,
                           0, 0xFF]), 2, 3)
        self.assertEqual(profile(m, "col"), [(2, 2, 1), (1, 1, 1)])

    def test_row_and_col_totals_agree(self):
        """Axis invariance at the profile level: total coverage is the
        ink count on both axes, the package's standing oracle shape."""
        import random
        rng = random.Random(20260817)
        d = bytes(0xFF if rng.random() < 0.4 else 0 for _ in range(15 * 11))
        m = InkMask(d, 15, 11)
        for axis in ("row", "col"):
            self.assertEqual(sum(c for c, _, _ in profile(m, axis)),
                             m.ink_count)

    def test_a_bad_axis_raises(self):
        with self.assertRaises(InvalidAxis):
            profile(InkMask(b"\xff", 1, 1), "diag")


class T2_10_StrokeMode(unittest.TestCase):
    """T14/T15 hermetic side; the TeX Gyre pins are in the gated class."""

    def test_the_mode_and_sample_size(self):
        m = InkMask(bytes([0xFF, 0xFF, 0, 0xFF, 0xFF,
                           0xFF, 0xFF, 0, 0xFF, 0,
                           0, 0, 0, 0, 0]), 5, 3)
        self.assertEqual(stroke_mode(m), (2, 4))

    def test_a_tie_breaks_toward_the_SMALLER_length(self):
        m = InkMask(bytes([0xFF, 0, 0xFF, 0xFF, 0]), 5, 1)
        self.assertEqual(stroke_mode(m), (1, 2))

    def test_an_empty_mask_is_zero_zero(self):
        self.assertEqual(stroke_mode(InkMask(b"\x00" * 6, 3, 2)), (0, 0))

    def test_the_INTEGER_COLLAPSE_inverts_height_normalised_order(self):
        """T15's mechanism, demonstrated rather than cited: at 2 vs 3 px
        the stems are one integer apart, and dividing by glyph height
        can invert which face reads heavier. Regular 2 px / 38 px tall
        gives ratio 0.0526; bold 3 px / 60 px gives 0.0500 -- the BOLD
        ratio is smaller. Why the docstring floor is 5 px."""
        reg = 2 / 38
        bold = 3 / 60
        self.assertLess(bold, reg)
