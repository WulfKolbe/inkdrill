"""A3: the curved-gutter seam, and the line helpers. Hermetic."""

import unittest

from inkdrill.raster import InkMask
from inkdrill.seam import (Seam, approximate_line, cost_grid, find_seam,
                           is_border_line, is_horizontal_line, resample_line)


def two_columns(w=64, h=64, gutter=28, bend=0):
    """Ink in two columns with a gap. `bend` curves the gap sinusoidally,
    which is the case a straight stripe cannot fit."""
    buf = bytearray(w * h)
    for y in range(h):
        off = int(bend * (y / max(1, h - 1) - 0.5) * 2)
        g = gutter + off
        for x in range(w):
            if abs(x - g) > 5:
                buf[y * w + x] = 0xFF
    return InkMask(bytes(buf), w, h)


class A3_1_Convergence(unittest.TestCase):
    """G2: budget=0 must reduce to the rigid stripe."""

    def test_zero_budget_gives_a_straight_line(self):
        s = find_seam(two_columns(), budget=0, block=4)
        self.assertEqual(len(set(s.xs)), 1)

    def test_zero_budget_picks_the_column_of_LEAST_INK(self):
        """A wrong recurrence still returns a path; only the degenerate
        case shows whether it is the right one."""
        m = two_columns()
        s = find_seam(m, budget=0, block=4)
        grid, gw, gh = cost_grid(m, 4)
        totals = [sum(grid[y][x] for y in range(gh)) for x in range(gw)]
        self.assertEqual(s.xs[0], min(range(gw), key=lambda x: (totals[x], x)))
        self.assertEqual(s.cost, min(totals))

    def test_a_straight_gutter_needs_no_budget_at_all(self):
        """Which is why a flat page does not need this module: budget 0
        and budget 2 find the same seam."""
        m = two_columns(bend=0)
        a = find_seam(m, budget=0, block=4)
        b = find_seam(m, budget=2, block=4)
        self.assertEqual(a.cost, b.cost)


class A3_2_CurvedGutter(unittest.TestCase):
    """The case the module exists for."""

    def test_a_bent_gutter_beats_the_best_straight_line(self):
        m = two_columns(bend=24)
        straight = find_seam(m, budget=0, block=4)
        curved = find_seam(m, budget=2, block=4)
        self.assertLess(curved.cost, straight.cost)

    def test_the_seam_follows_the_bend(self):
        m = two_columns(bend=24)
        s = find_seam(m, budget=2, block=4)
        self.assertGreater(max(s.xs) - min(s.xs), 2,
                           "the seam stayed straight through a bend")

    def test_a_clean_gutter_costs_nothing(self):
        m = two_columns(bend=24)
        self.assertEqual(find_seam(m, budget=2, block=4).cost, 0)


class A3_3_Shape(unittest.TestCase):
    """G3-G6."""

    def test_the_path_never_steps_further_than_the_budget(self):
        for budget in (0, 1, 3):
            s = find_seam(two_columns(bend=30), budget=budget, block=4)
            with self.subTest(budget=budget):
                for a, b in zip(s.xs, s.xs[1:]):
                    self.assertLessEqual(abs(b - a), budget)

    def test_one_x_per_block_row(self):
        m = two_columns()
        _, _, gh = cost_grid(m, 4)
        self.assertEqual(len(find_seam(m, budget=1, block=4).xs), gh)

    def test_a_page_of_solid_ink_still_returns_a_path(self):
        """G5: a page with no gutter has a least-bad seam, and the COST
        is what says there was nothing to find."""
        m = InkMask(b"\xff" * (32 * 32), 32, 32)
        s = find_seam(m, budget=1, block=4)
        self.assertEqual(len(s.xs), 8)
        self.assertGreater(s.cost, 0)

    def test_pixel_xs_carries_the_block_size(self):
        s = Seam((0, 1, 2), 0, 8)
        self.assertEqual(s.pixel_xs(), (4, 12, 20))

    def test_a_negative_budget_raises(self):
        with self.assertRaises(ValueError):
            find_seam(two_columns(), budget=-1)

    def test_a_non_positive_block_raises(self):
        with self.assertRaises(ValueError):
            cost_grid(two_columns(), 0)


class A3_4_LineHelpers(unittest.TestCase):

    def test_approximate_line_fits_a_horizontal_run(self):
        x0, y0, x1, y1 = approximate_line([(0, 10), (5, 10), (10, 10)])
        self.assertAlmostEqual(y0, 10.0)
        self.assertAlmostEqual(y1, 10.0)

    def test_a_near_vertical_line_is_fitted_on_the_other_axis(self):
        """Fitting y-on-x here would divide by a near-zero spread."""
        got = approximate_line([(10, 0), (10, 5), (11, 40)])
        self.assertAlmostEqual(got[1], 0.0)
        self.assertAlmostEqual(got[3], 40.0)

    def test_a_line_needs_two_points(self):
        with self.assertRaises(ValueError):
            approximate_line([(1, 1)])

    def test_horizontal_and_vertical_are_decided_by_extent(self):
        self.assertTrue(is_horizontal_line((0, 0, 10, 2)))
        self.assertFalse(is_horizontal_line((0, 0, 2, 10)))

    def test_a_diagonal_counts_as_horizontal_rather_than_neither(self):
        self.assertTrue(is_horizontal_line((0, 0, 10, 10)))

    def test_a_border_line_is_within_the_margin(self):
        self.assertTrue(is_border_line((0, 1, 100, 1), 100, 100))
        self.assertTrue(is_border_line((99, 0, 99, 100), 100, 100))
        self.assertFalse(is_border_line((40, 40, 60, 60), 100, 100))

    def test_the_border_margin_is_a_fraction_of_the_page(self):
        # Must not touch the x edges, or it is a border line on that
        # axis whatever the margin -- which the first fixture did.
        line = (40, 4, 60, 4)
        self.assertFalse(is_border_line(line, 100, 100, margin=0.01))
        self.assertTrue(is_border_line(line, 100, 100, margin=0.10))

    def test_resample_spaces_by_ARC_LENGTH_not_by_index(self):
        """A long segment and a short one: index spacing would put half
        the samples on the short one."""
        got = resample_line([(0, 0), (10, 0), (11, 0)], 3)
        self.assertAlmostEqual(got[0][0], 0.0)
        self.assertAlmostEqual(got[1][0], 5.5)
        self.assertAlmostEqual(got[2][0], 11.0)

    def test_resample_returns_the_requested_count(self):
        self.assertEqual(len(resample_line([(0, 0), (3, 4)], 7)), 7)

    def test_a_degenerate_polyline_resamples_to_one_point(self):
        self.assertEqual(resample_line([(2, 2), (2, 2)], 3), [(2, 2)] * 3)

    def test_resampling_below_two_points_raises(self):
        with self.assertRaises(ValueError):
            resample_line([(0, 0), (1, 1)], 1)


if __name__ == "__main__":
    unittest.main()
