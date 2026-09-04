"""602 -- the cell rect, checked against the lattice before it is emitted to.

EVERY NUMBER BELOW IS MEASURED. The column rules and row rules are the
ones `mutool trace` reports out of Geometric_topology's report.pdf page
20 -- the PDF's own vector content, an independent source from the
raster the lattice is built on -- and the expected rects are the cells
`_table_cells` finds on that page at 300 dpi. The two agreed on 493
cells across five pages of two documents, all four edges median 0 and
every cell within 1 px, which is what these pin.
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from inkdrill.cellrect import (ARRAYRULE_BP, Rect, cell_rect,   # noqa: E402
                               row_rects)

#: Geometric_topology report.pdf p20, the seven vertical rules
COLS = [53.648, 122.694, 154.890, 204.094, 477.236, 767.384, 1136.904]
#: the horizontal rules bounding its rows 0 and 1
R0 = (790.667, 778.313)
R1 = (778.313, 744.499)
PAGE_H = 841.89                       #: a3 landscape, which the reports are
DPI = 300


#: what `_table_cells` finds for those rows at 300 dpi
LAT0 = [(225, 215, 510, 264), (513, 215, 644, 264), (647, 215, 849, 264),
        (852, 215, 1987, 264), (1990, 215, 3196, 264),
        (3199, 215, 4736, 264)]
LAT1 = [(225, 266, 510, 405), (513, 266, 644, 405), (647, 266, 849, 405),
        (852, 266, 1987, 405), (1990, 266, 3196, 405),
        (3199, 266, 4736, 405)]


class T602_1_AgainstTheLattice(unittest.TestCase):
    """The measured agreement, and it is a TOLERANCE not an identity.

    Over 493 cells on five pages of two documents every edge had
    median 0 and every cell was within 1 px; x0 and x1 were exactly 0
    on all of them, y0 and y1 were 0 or -1. So the x edges are pinned
    exactly and the y edges to the measured 1 px -- asserting equality
    on y would be asserting something the measurement did not show,
    and the first draft of this file did exactly that and failed.
    """

    def _pairs(self, rules, lattice):
        got = row_rects(COLS, *rules, page_height_bp=PAGE_H, dpi=DPI)
        self.assertEqual(len(got), len(lattice))
        return list(zip(got, lattice))

    def test_the_x_edges_are_exact_on_every_column(self):
        for rules, lat in ((R0, LAT0), (R1, LAT1)):
            for e, (lx0, _ly0, lx1, _ly1) in self._pairs(rules, lat):
                self.assertEqual((e.x0, e.x1), (lx0, lx1))

    def test_the_y_edges_are_within_one_pixel(self):
        for rules, lat in ((R0, LAT0), (R1, LAT1)):
            for e, (_lx0, ly0, _lx1, ly1) in self._pairs(rules, lat):
                self.assertLessEqual(abs(e.y0 - ly0), 1)
                self.assertLessEqual(abs(e.y1 - ly1), 1)

    def test_the_y_residual_is_never_positive(self):
        """It is 0 or -1 and never +1: the emitted rect ends at or
        inside the lattice cell, never past it. A rect that overran
        would crop a neighbouring row's ink."""
        for rules, lat in ((R0, LAT0), (R1, LAT1)):
            for e, (_x0, ly0, _x1, ly1) in self._pairs(rules, lat):
                self.assertIn(e.y0 - ly0, (0, -1))
                self.assertIn(e.y1 - ly1, (0, -1))

    def test_row_0_is_pinned_exactly_as_a_regression(self):
        """Behaviour pin, separate from the agreement claim above."""
        self.assertEqual(
            [tuple(r) for r in row_rects(COLS, *R0, page_height_bp=PAGE_H,
                                         dpi=DPI)], LAT0)

    def test_the_high_bound_is_floor_not_floor_minus_one(self):
        """The off-by-one the checker caught before anything was
        emitted: `floor(x)` is already the last pixel at or inside x,
        and subtracting a further 1 put x1 short on EVERY cell of
        EVERY row -- a constant -1 over 60 cells."""
        r = cell_rect(COLS, *R0, 0, page_height_bp=PAGE_H, dpi=DPI)
        self.assertEqual(r.x1, 510)
        self.assertEqual(r.width, 286)


class T602_2_Contract(unittest.TestCase):
    def test_g2_dpi_scales_the_rect(self):
        a = cell_rect(COLS, *R0, 0, page_height_bp=PAGE_H, dpi=DPI)
        b = cell_rect(COLS, *R0, 0, page_height_bp=PAGE_H, dpi=600)
        self.assertAlmostEqual(b.x0 / a.x0, 2.0, places=2)
        self.assertAlmostEqual(b.width / a.width, 2.0, places=2)

    def test_g3_the_page_height_sets_the_y_flip(self):
        """A4-portrait's height on an a3-landscape report moves every
        row by the difference -- 0 px is not a plausible error here."""
        a = cell_rect(COLS, *R0, 0, page_height_bp=PAGE_H, dpi=DPI)
        b = cell_rect(COLS, *R0, 0, page_height_bp=1190.55, dpi=DPI)
        self.assertNotEqual(a.y0, b.y0)
        self.assertEqual(b.y0 - a.y0,
                         round((1190.55 - PAGE_H) * DPI / 72.0))

    def test_g4_the_inset_is_half_a_rule_on_each_side(self):
        wide = cell_rect(COLS, *R0, 0, page_height_bp=PAGE_H, dpi=DPI,
                         rule_bp=0.0)
        got = cell_rect(COLS, *R0, 0, page_height_bp=PAGE_H, dpi=DPI)
        self.assertGreater(wide.width, got.width)
        self.assertEqual(ARRAYRULE_BP, 0.4)

    def test_g5_columns_must_ascend(self):
        with self.assertRaises(ValueError):
            cell_rect([100.0, 50.0], *R0, 0, page_height_bp=PAGE_H, dpi=DPI)

    def test_g5_ascending_columns_are_accepted(self):
        """The positive side of the same guard -- asserted so the
        check cannot be made unconditional without the suite noticing."""
        r = cell_rect([50.0, 100.0], *R0, 0, page_height_bp=PAGE_H, dpi=DPI)
        self.assertFalse(r.is_empty)

    def test_g5_above_must_be_above_below_in_user_space(self):
        with self.assertRaises(ValueError):
            cell_rect(COLS, R0[1], R0[0], 0, page_height_bp=PAGE_H, dpi=DPI)

    def test_g5_a_column_out_of_range_is_an_indexerror(self):
        with self.assertRaises(IndexError):
            cell_rect(COLS, *R0, len(COLS) - 1,
                      page_height_bp=PAGE_H, dpi=DPI)

    def test_g7_a_page_break_row_is_refused_by_name(self):
        """608: `0049_DIA_0006` carries above 87.082 and below 614.998
        -- rules on two different pages, which is not a rectangle. The
        ordering guard refuses it incidentally; this refuses it for the
        stated reason, which keeps working when the numbers line up."""
        with self.assertRaises(ValueError) as cm:
            cell_rect(COLS, 693.051, 624.906, 0, page_height_bp=PAGE_H,
                      dpi=DPI, rules_on_one_page=False)
        self.assertIn("different pages", str(cm.exception))

    def test_g7_the_default_computes_as_before(self):
        """Both sides: the flag defaults to True, so every existing
        caller is unaffected."""
        a = cell_rect(COLS, *R0, 0, page_height_bp=PAGE_H, dpi=DPI)
        b = cell_rect(COLS, *R0, 0, page_height_bp=PAGE_H, dpi=DPI,
                      rules_on_one_page=True)
        self.assertEqual(a, b)

    def test_g6_an_empty_cell_is_returned_not_clamped(self):
        """Rules closer together than a rule is wide. A zero-width cell
        is a finding about the emission; clamping it to one pixel would
        hide it."""
        r = cell_rect([100.0, 100.2], *R0, 0,
                      page_height_bp=PAGE_H, dpi=DPI)
        self.assertTrue(r.is_empty)

    def test_g1_the_same_numbers_give_the_same_rect(self):
        self.assertEqual(
            cell_rect(COLS, *R0, 3, page_height_bp=PAGE_H, dpi=DPI),
            cell_rect(COLS, *R0, 3, page_height_bp=PAGE_H, dpi=DPI))

    def test_a_rect_is_inclusive_on_both_bounds(self):
        r = Rect(10, 20, 12, 23)
        self.assertEqual((r.width, r.height), (3, 4))
