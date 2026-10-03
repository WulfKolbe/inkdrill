"""`tools/eqink.py` -- ink inside an equation list's declared regions.

The tool exists because a display row's declared region conflates the
equation with its right-set NUMBER: on 200 rows of pdfdrill's first
subset, 18% held a wide interior gap, median 897 px and up to 1,946.
pdfdrill then found the cause in their own builder and fixed 13 of 21
on one document -- so this measurement is the external check on that
fix, which makes its own correctness load bearing.

Every fixture is a hand-built mask, so the geometry is known exactly
rather than asserted against whatever a page happens to contain.
"""
import importlib.util
import pathlib
import sys
import unittest

from inkdrill.raster import InkMask


def _tool():
    p = (pathlib.Path(__file__).resolve().parent.parent / "tools" / "eqink.py")
    spec = importlib.util.spec_from_file_location("_eqink", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_eqink"] = mod
    spec.loader.exec_module(mod)
    return mod


E = _tool()


def mask(rows):
    return InkMask.from_rows(rows)


class TE_1_Geometry(unittest.TestCase):
    def test_the_ink_box_is_tight(self):
        m = mask(["........",
                  "..##....",
                  "..##....",
                  "........"])
        r = E.measure(m, 0)
        self.assertTrue(r["ink"])
        self.assertEqual(r["ink_box"], [2, 1, 4, 3])

    def test_a_region_with_no_ink_says_so_and_gets_no_boxes(self):
        r = E.measure(mask(["....", "...."]), 10)
        self.assertFalse(r["ink"])
        self.assertNotIn("ink_box", r)
        self.assertNotIn("body_box", r)

    def test_inked_rows_make_a_two_line_equation_visible(self):
        m = mask(["##..",
                  "....",
                  "....",
                  "##.."])
        self.assertEqual(E.measure(m, 0)["ink_rows"], [(0, 1), (3, 4)])


class TE_2_TheInteriorGap(unittest.TestCase):
    """A MARGIN IS NOT A GAP. The blank either side of the ink is not a
    separation; only a run BETWEEN inked columns is."""

    BODY_THEN_NUMBER = ["..###.........##..",
                        "..###.........##.."]

    def test_the_widest_interior_gap_is_measured(self):
        gap, end = E.widest_interior_gap(
            [i for i in range(18) if i in (2, 3, 4, 14, 15)])
        self.assertEqual(gap, 9)          # columns 5..13
        self.assertEqual(end, 13)

    def test_leading_and_trailing_blank_is_not_a_gap(self):
        gap, _ = E.widest_interior_gap([5, 6, 7])
        self.assertEqual(gap, 0)

    def test_a_single_inked_column_has_no_gap(self):
        self.assertEqual(E.widest_interior_gap([4]), (0, 0))

    def test_the_number_is_split_out_above_the_floor(self):
        r = E.measure(mask(self.BODY_THEN_NUMBER), floor=5)
        self.assertEqual(r["body_box"][0], 2)
        self.assertEqual(r["body_box"][2], 5)
        self.assertEqual(r["number_box"][0], 14)
        self.assertEqual(r["number_box"][2], 16)

    def test_below_the_floor_nothing_is_split(self):
        """The other side of the rule: an ordinary inter-symbol gap must
        NOT be read as a number separation."""
        r = E.measure(mask(self.BODY_THEN_NUMBER), floor=12)
        self.assertEqual(r["widest_gap"], 9)
        self.assertNotIn("body_box", r)
        self.assertNotIn("number_box", r)

    def test_floor_zero_measures_without_splitting(self):
        r = E.measure(mask(self.BODY_THEN_NUMBER), floor=0)
        self.assertEqual(r["widest_gap"], 9)
        self.assertNotIn("body_box", r)

    def test_a_gap_with_nothing_to_its_right_does_not_split(self):
        """Degenerate: everything is left of the gap, so there is no
        number. Splitting here would emit an empty number_box."""
        m = mask(["###.......", "###......."])
        r = E.measure(m, floor=2)
        self.assertNotIn("number_box", r)


if __name__ == "__main__":
    unittest.main()
