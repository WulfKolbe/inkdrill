"""Unit 11 tests. Every test name is quoted verbatim in the status report."""

import random
import unittest

from inkdrill.coverage import (Box, CoverageClass, CoverageReport, Region,
                               check)
from inkdrill.space import Affine


def b(i, x0, y0, x1, y1):
    return Box(i, x0, y0, x1, y1)


def r(i, x0, y0, x1, y1, label=""):
    return Region(i, x0, y0, x1, y1, label)


class T11_1_ContainmentNotCentres(unittest.TestCase):
    """G2, and the inversion of U10's rule. U10 matches on centres
    because pdfminer gives an ADVANCE box; here a region is a real
    boundary another tool drew, and a blob crossing it IS the finding."""

    def test_a_contained_component_is_inside(self):
        rep = check([b(0, 10, 10, 20, 20)], [r(0, 0, 0, 100, 100)])
        self.assertEqual(rep.by_class[CoverageClass.INSIDE], [0])

    def test_a_component_crossing_the_top_edge_straddles(self):
        """The tall-integral case: the region was fitted to the body of a
        line and the glyph extends above it."""
        rep = check([b(0, 10, -5, 20, 30)], [r(0, 0, 0, 100, 100)])
        self.assertEqual(rep.by_class[CoverageClass.STRADDLE], [0])

    def test_a_component_crossing_the_bottom_edge_straddles(self):
        rep = check([b(0, 10, 90, 20, 130)], [r(0, 0, 0, 100, 100)])
        self.assertEqual(rep.by_class[CoverageClass.STRADDLE], [0])

    def test_centres_would_have_called_the_straddler_inside(self):
        """The whole reason the rule is inverted. This component's centre
        sits comfortably in the region; only containment sees the
        overflow."""
        box = b(0, 10, -20, 20, 60)
        reg = r(0, 0, 0, 100, 100)
        cx, cy = (box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2
        self.assertTrue(reg.x0 <= cx <= reg.x1 and reg.y0 <= cy <= reg.y1)
        rep = check([box], [reg])
        self.assertEqual(rep.by_class[CoverageClass.STRADDLE], [0])
        self.assertEqual(rep.count(CoverageClass.INSIDE), 0)

    def test_a_component_touching_an_edge_from_inside_is_inside(self):
        rep = check([b(0, 0, 0, 100, 100)], [r(0, 0, 0, 100, 100)])
        self.assertEqual(rep.by_class[CoverageClass.INSIDE], [0])

    def test_a_component_far_from_every_region_is_missed(self):
        rep = check([b(0, 500, 500, 510, 510)], [r(0, 0, 0, 100, 100)])
        self.assertEqual(rep.by_class[CoverageClass.MISSED], [0])


class T11_2_TheResidualIsTheProduct(unittest.TestCase):
    """G3. Ink with no region is content the other tool did not see --
    the deliverable, not the leftovers."""

    def test_missed_ink_is_reported_with_its_members(self):
        boxes = [b(0, 10, 10, 20, 20), b(1, 500, 500, 520, 520),
                 b(2, 600, 600, 620, 620)]
        rep = check(boxes, [r(0, 0, 0, 100, 100)])
        self.assertEqual(sorted(rep.members(CoverageClass.MISSED)), [1, 2])

    def test_the_missed_fraction_is_of_ink_not_of_regions(self):
        boxes = [b(0, 10, 10, 20, 20), b(1, 500, 500, 520, 520)]
        rep = check(boxes, [r(0, 0, 0, 100, 100)])
        self.assertAlmostEqual(rep.missed_fraction, 0.5, places=9)

    def test_an_empty_region_is_reported_even_though_it_measured_zero(self):
        """"This tool never hallucinates an empty region" is a finding
        about the tool, and a different tool will not share it."""
        rep = check([b(0, 10, 10, 20, 20)],
                    [r(0, 0, 0, 100, 100), r(7, 500, 500, 600, 600)])
        self.assertEqual(rep.by_class[CoverageClass.EMPTY_REGION], [7])

    def test_empty_region_fraction_is_of_regions_not_of_ink(self):
        """Mixing the denominators would make the numbers
        incomparable."""
        rep = check([b(0, 10, 10, 20, 20)],
                    [r(0, 0, 0, 100, 100), r(1, 500, 500, 600, 600)])
        self.assertAlmostEqual(rep.fraction(CoverageClass.EMPTY_REGION),
                               0.5, places=9)

    def test_overlapping_regions_are_their_own_class(self):
        """G7: a component inside two regions is not silently assigned
        to whichever came first."""
        rep = check([b(0, 40, 40, 60, 60)],
                    [r(0, 0, 0, 100, 100), r(1, 20, 20, 120, 120)])
        self.assertEqual(rep.by_class[CoverageClass.OVERLAPPING], [0])

    def test_the_regions_a_component_touches_are_recorded(self):
        rep = check([b(0, 40, 40, 60, 60)],
                    [r(5, 0, 0, 100, 100), r(9, 20, 20, 120, 120)])
        self.assertEqual(sorted(rep.regions_of[0]), [5, 9])

    def test_the_report_names_every_class_present(self):
        rep = check([b(0, 10, 10, 20, 20), b(1, 900, 900, 910, 910)],
                    [r(0, 0, 0, 100, 100), r(1, 500, 500, 600, 600)])
        text = rep.report()
        self.assertIn("ink inside one region", text)
        self.assertIn("ink with no region", text)
        self.assertIn("region with no ink", text)


class T11_3_PartitionAndDeterminism(unittest.TestCase):

    def test_every_component_lands_in_exactly_one_class(self):
        """G1."""
        rng = random.Random(20260808)
        ink_classes = [CoverageClass.INSIDE, CoverageClass.MISSED,
                       CoverageClass.STRADDLE, CoverageClass.OVERLAPPING]
        for trial in range(80):
            boxes = []
            for i in range(rng.randint(0, 12)):
                x0, y0 = rng.randint(0, 90), rng.randint(0, 90)
                boxes.append(b(i, x0, y0, x0 + rng.randint(0, 20),
                               y0 + rng.randint(0, 20)))
            regs = []
            for j in range(rng.randint(0, 5)):
                x0, y0 = rng.randint(0, 80), rng.randint(0, 80)
                regs.append(r(j, x0, y0, x0 + rng.randint(5, 40),
                              y0 + rng.randint(5, 40)))
            rep = check(boxes, regs)
            seen = [i for k in ink_classes for i in rep.members(k)]
            with self.subTest(trial=trial):
                self.assertEqual(sorted(seen), sorted(x.id for x in boxes))
                self.assertEqual(len(seen), len(set(seen)))

    def test_every_region_is_classified_too(self):
        """G4: an empty region must be visible."""
        rng = random.Random(99)
        for trial in range(40):
            boxes = []
            for i in range(rng.randint(0, 6)):
                x0, y0 = rng.randint(0, 50), rng.randint(0, 50)
                boxes.append(b(i, x0, y0, x0 + rng.randint(0, 12),
                               y0 + rng.randint(0, 12)))
            regs = []
            for j in range(rng.randint(1, 5)):
                x0, y0 = rng.randint(0, 50), rng.randint(0, 50)
                regs.append(r(j, x0, y0, x0 + rng.randint(5, 25),
                              y0 + rng.randint(5, 25)))
            rep = check(boxes, regs)
            empty = set(rep.members(CoverageClass.EMPTY_REGION))
            touched = {rid for ids in rep.regions_of.values() for rid in ids}
            with self.subTest(trial=trial):
                self.assertEqual(empty & touched, set())
                self.assertEqual(len(empty) + len(touched), len(regs))

    def test_classification_is_independent_of_input_order(self):
        """G5."""
        boxes = [b(i, i * 30, 0, i * 30 + 10, 10) for i in range(8)]
        regs = [r(j, j * 60, -5, j * 60 + 45, 15) for j in range(4)]
        want = check(boxes, regs)
        rng = random.Random(7)
        for trial in range(6):
            bs, rs = boxes[:], regs[:]
            rng.shuffle(bs)
            rng.shuffle(rs)
            with self.subTest(trial=trial):
                self.assertEqual(check(bs, rs).by_class, want.by_class)

    def test_an_empty_page_is_not_a_division_by_zero(self):
        """G6."""
        rep = check([], [])
        self.assertEqual(rep.report(), "no ink and no regions")
        self.assertEqual(rep.missed_fraction, 0.0)
        self.assertEqual(rep.fraction(CoverageClass.EMPTY_REGION), 0.0)

    def test_a_page_with_no_regions_reports_all_ink_missed(self):
        """The degenerate but important case: a tool that returned
        nothing missed everything."""
        rep = check([b(i, i * 20, 0, i * 20 + 9, 9) for i in range(5)], [])
        self.assertEqual(rep.count(CoverageClass.MISSED), 5)
        self.assertEqual(rep.missed_fraction, 1.0)

    def test_a_degenerate_box_is_dropped_and_the_count_shows_it(self):
        """x1 < x0 has no positive pixel count. Dropping it silently
        would break the partition guarantee without saying so -- found by
        a random fixture that happened to generate one."""
        boxes = [b(0, 90, 10, 10, 20), b(1, 10, 10, 20, 20)]
        rep = check(boxes, [r(0, 0, 0, 100, 100)])
        self.assertEqual(rep.box_count, 1)
        self.assertEqual(rep.members(CoverageClass.INSIDE), [1])

    def test_specks_below_the_threshold_are_dropped(self):
        """A 1-px speck reported as missed content is noise a caller has
        to filter anyway."""
        boxes = [b(0, 500, 500, 500, 500), b(1, 500, 400, 520, 420)]
        rep = check(boxes, [r(0, 0, 0, 100, 100)], min_pixels=9)
        self.assertEqual(rep.members(CoverageClass.MISSED), [1])
        self.assertEqual(rep.box_count, 1)


class T11_4_RegionsArriveInAnotherSpace(unittest.TestCase):

    def test_regions_are_transformed_before_comparison(self):
        """OCR gives points; components are pixels. Same discipline as
        U10: compose an affine, do not write out a formula."""
        t = Affine.scale(2.0)
        rep = check([b(0, 20, 20, 40, 40)], [r(0, 5, 5, 25, 25)],
                    to_pixels=t)
        self.assertEqual(rep.by_class[CoverageClass.INSIDE], [0])

    def test_without_the_transform_the_same_region_misses(self):
        rep = check([b(0, 20, 20, 40, 40)], [r(0, 5, 5, 25, 25)])
        self.assertEqual(rep.by_class[CoverageClass.STRADDLE], [0])

    def test_a_transform_that_reverses_an_axis_still_gives_sane_regions(self):
        flip = Affine.flip_y(100.0)
        reg = r(0, 10, 10, 30, 30).scaled(flip)
        self.assertLess(reg.x0, reg.x1)
        self.assertLess(reg.y0, reg.y1)
        self.assertEqual((reg.y0, reg.y1), (70.0, 90.0))

    def test_scaling_preserves_the_region_id_and_label(self):
        reg = r(3, 1, 1, 2, 2, "text").scaled(Affine.scale(10.0))
        self.assertEqual(reg.id, 3)
        self.assertEqual(reg.label, "text")


if __name__ == "__main__":
    unittest.main()
