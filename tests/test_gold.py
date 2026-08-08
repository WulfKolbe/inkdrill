"""Unit 10 tests. Every test name is quoted verbatim in the status report."""

import math
import random
import unittest

from inkdrill.gold import (Component, Glyph, GoldGlyph, MatchKind,
                           MatchReport, match, page_transform, to_coco)
from inkdrill.space import Affine


def g(text, x0, y0, x1, y1, font="F"):
    return Glyph(text, x0, y0, x1, y1, font)


def c(i, x0, y0, x1, y1):
    return Component(i, x0, y0, x1, y1, (x1 - x0 + 1) * (y1 - y0 + 1))


class T10_1_PageTransformIsComposed(unittest.TestCase):
    """G1. Composition, not a formula -- which is the whole reason U1
    exists, and what lets /Rotate and a crop arrive later."""

    def test_a_page_maps_corner_to_corner(self):
        t = page_transform(792.0, 400.0)
        self.assertEqual(t.point(0, 792), (0.0, 0.0))
        x, y = t.point(612, 0)
        self.assertAlmostEqual(x, 3400.0, places=6)
        self.assertAlmostEqual(y, 4400.0, places=6)

    def test_the_y_flip_is_present(self):
        """PDF y grows up, raster y grows down. Getting this wrong gives
        a vertically mirrored match that still looks plausible in
        aggregate, because text lines are roughly symmetric."""
        t = page_transform(100.0, 72.0)
        top = t.point(0, 100)[1]
        bottom = t.point(0, 0)[1]
        self.assertLess(top, bottom)
        self.assertAlmostEqual(top, 0.0, places=9)
        self.assertAlmostEqual(bottom, 100.0, places=9)

    def test_the_result_is_an_affine_and_stays_invertible(self):
        t = page_transform(792.0, 300.0)
        self.assertIsInstance(t, Affine)
        back = t.inverse()
        x, y = back.point(*t.point(100.0, 200.0))
        self.assertAlmostEqual(x, 100.0, places=6)
        self.assertAlmostEqual(y, 200.0, places=6)

    def test_the_result_composes_further(self):
        """A caller must be able to keep composing -- that is the point
        of returning an Affine rather than a tuple of numbers."""
        t = page_transform(792.0, 72.0)
        shifted = t.then(Affine.translate(10, 20))
        self.assertEqual(shifted.point(0, 792), (10.0, 20.0))

    def test_dpi_scales_linearly(self):
        for dpi in (72.0, 150.0, 300.0, 600.0):
            with self.subTest(dpi=dpi):
                t = page_transform(792.0, dpi)
                self.assertAlmostEqual(t.point(72, 792)[0], dpi, places=6)

    def test_a_crop_box_moves_the_origin(self):
        t = page_transform(792.0, 72.0, crop_x0_pt=10.0, crop_y0_pt=20.0)
        x, y = t.point(10.0, 792.0)
        self.assertAlmostEqual(x, 0.0, places=9)
        self.assertAlmostEqual(y, 0.0, places=9)

    def test_rotation_keeps_the_page_in_positive_coordinates(self):
        for r in (90, 180, 270):
            with self.subTest(rotate=r):
                t = page_transform(792.0, 72.0, rotate=r,
                                   page_width_pt=612.0)
                corners = [t.point(x, y) for x in (0, 612)
                           for y in (0, 792)]
                for x, y in corners:
                    self.assertGreaterEqual(x, -1e-6)
                    self.assertGreaterEqual(y, -1e-6)

    def test_a_bad_rotation_is_refused(self):
        with self.assertRaises(ValueError):
            page_transform(792.0, 72.0, rotate=45)

    def test_a_non_positive_dpi_is_refused(self):
        for dpi in (0.0, -72.0):
            with self.subTest(dpi=dpi):
                with self.assertRaises(ValueError):
                    page_transform(792.0, dpi)


class T10_2_TheFourResidualClasses(unittest.TestCase):
    """G2 and G3. units.md is explicit that these are REPORTED rather
    than discarded, and the premise check says why: only 66.93% of real
    assignments are 1:1."""

    def test_a_clean_page_is_all_one_to_one(self):
        comps = [c(0, 0, 0, 9, 9), c(1, 20, 0, 29, 9)]
        glyphs = [g("a", 0, 0, 10, 10), g("b", 20, 0, 30, 10)]
        rep = match(comps, glyphs)
        self.assertEqual(rep.count(MatchKind.ONE_TO_ONE), 2)
        self.assertEqual(rep.assignments, 2)

    def test_ink_with_no_glyph_is_reported(self):
        """Overwhelmingly figures and rules. A diagram correctly has no
        glyph -- this is the signal, not a failure."""
        comps = [c(0, 0, 0, 9, 9), c(1, 500, 500, 599, 599)]
        rep = match(comps, [g("a", 0, 0, 10, 10)])
        self.assertEqual(rep.by_kind[MatchKind.IMAGE_ONLY], [1])

    def test_n_ink_to_one_glyph_is_reported(self):
        """`i`, `j`, `:` and accents -- the multi-component glyphs U4
        already had to accommodate."""
        comps = [c(0, 2, 0, 4, 2), c(1, 2, 5, 4, 12)]      # dot and stem
        rep = match(comps, [g("i", 0, 0, 8, 14)])
        self.assertEqual(sorted(rep.by_kind[MatchKind.SPLIT]), [0, 1])
        self.assertEqual(rep.gold[0].kind, MatchKind.SPLIT)
        self.assertEqual(sorted(rep.gold[0].components), [0, 1])

    def test_glyph_with_no_ink_is_reported(self):
        rep = match([c(0, 0, 0, 9, 9)],
                    [g("a", 0, 0, 10, 10), g("b", 90, 90, 100, 100)])
        self.assertEqual(rep.count(MatchKind.MISSING_INK), 1)
        self.assertEqual(rep.gold[1].kind, MatchKind.MISSING_INK)
        self.assertEqual(rep.gold[1].components, ())

    def test_one_ink_to_n_glyphs_is_reported_not_split(self):
        """Measured at 0.02% of assignments, so the matcher reports it
        and lets a caller decide. Building a splitter would have been
        effort spent on two thousandths of the data."""
        comps = [c(0, 0, 0, 19, 9)]
        rep = match(comps, [g("f", 0, 0, 10, 10), g("i", 10, 0, 20, 10)])
        self.assertEqual(rep.by_kind[MatchKind.MERGED], [0])
        self.assertEqual(rep.component_count, 1)
        # and BOTH sides must agree. Found by branch mutation: the
        # component side was asserted and the glyph side was not, so the
        # gold records could have read 1:1 while the component read
        # MERGED -- a report contradicting itself.
        self.assertEqual([x.kind for x in rep.gold],
                         [MatchKind.MERGED, MatchKind.MERGED])
        self.assertEqual([x.components for x in rep.gold], [(0,), (0,)])

    def test_the_two_sides_of_the_report_never_contradict(self):
        """Components are classified in one pass and glyphs in another,
        so the two can drift. A glyph with EXACTLY ONE member that is
        itself merged must read MERGED.

        The invariant is deliberately not stronger than that. A glyph
        with several members, one of which is also claimed by another
        glyph, is genuinely both split and merged; the code gives SPLIT
        precedence, and asserting MERGED there was wrong -- my first
        version of this test failed for that reason, and the code was
        right."""
        rng = random.Random(31337)
        for trial in range(50):
            comps = [c(i, rng.randint(0, 40), rng.randint(0, 40),
                       rng.randint(0, 40) + 6, rng.randint(0, 40) + 6)
                     for i in range(rng.randint(1, 7))]
            glyphs = [g(chr(97 + j), rng.randint(0, 40), rng.randint(0, 40),
                        rng.randint(0, 40) + 9, rng.randint(0, 40) + 9)
                      for j in range(rng.randint(1, 5))]
            rep = match(comps, glyphs)
            merged = set(rep.by_kind.get(MatchKind.MERGED, ()))
            with self.subTest(trial=trial):
                for rec in rep.gold:
                    if len(rec.components) == 1 and rec.components[0] in merged:
                        self.assertEqual(rec.kind, MatchKind.MERGED)
                    if len(rec.components) > 1:
                        self.assertEqual(rec.kind, MatchKind.SPLIT)

    def test_split_takes_precedence_over_merged_when_both_apply(self):
        """One glyph with two components, one of which also belongs to a
        neighbour. Both descriptions are true; SPLIT wins, and that is a
        choice rather than an accident."""
        comps = [c(0, 0, 0, 4, 9), c(1, 6, 0, 14, 9)]
        glyphs = [g("a", 0, 0, 12, 10), g("b", 12, 0, 20, 10)]
        rep = match(comps, glyphs)
        self.assertEqual(rep.gold[0].kind, MatchKind.SPLIT)
        self.assertEqual(len(rep.gold[0].components), 2)

    def test_every_component_lands_in_exactly_one_class(self):
        """G2: a partition. Nothing dropped, nothing double-counted."""
        rng = random.Random(20260808)
        for trial in range(60):
            comps = [c(i, rng.randint(0, 90), rng.randint(0, 90),
                       rng.randint(0, 90) + 5, rng.randint(0, 90) + 5)
                     for i in range(rng.randint(0, 12))]
            glyphs = [g(chr(97 + j), rng.randint(0, 90), rng.randint(0, 90),
                        rng.randint(0, 90) + 8, rng.randint(0, 90) + 8)
                      for j in range(rng.randint(0, 8))]
            rep = match(comps, glyphs)
            comp_classes = [MatchKind.ONE_TO_ONE, MatchKind.IMAGE_ONLY,
                            MatchKind.SPLIT, MatchKind.MERGED]
            seen = [i for k in comp_classes for i in rep.by_kind.get(k, ())]
            with self.subTest(trial=trial):
                self.assertEqual(sorted(seen),
                                 sorted(x.id for x in comps))
                self.assertEqual(len(seen), len(set(seen)))

    def test_every_glyph_gets_exactly_one_gold_record(self):
        rng = random.Random(4242)
        for trial in range(40):
            comps = [c(i, rng.randint(0, 50), rng.randint(0, 50),
                       rng.randint(0, 50) + 4, rng.randint(0, 50) + 4)
                     for i in range(rng.randint(0, 8))]
            glyphs = [g(chr(97 + j), rng.randint(0, 50), rng.randint(0, 50),
                        rng.randint(0, 50) + 6, rng.randint(0, 50) + 6)
                      for j in range(rng.randint(0, 6))]
            rep = match(comps, glyphs)
            with self.subTest(trial=trial):
                self.assertEqual(len(rep.gold), len(glyphs))

    def test_the_report_names_every_class_present(self):
        comps = [c(0, 0, 0, 9, 9), c(1, 500, 500, 509, 509)]
        rep = match(comps, [g("a", 0, 0, 10, 10), g("z", 90, 90, 99, 99)])
        text = rep.report()
        self.assertIn("ink with no glyph", text)
        self.assertIn("glyph with no ink", text)


class T10_3_CentresNotOverlap(unittest.TestCase):
    """G4. pdfminer's box is the ADVANCE box, not the ink box. Overlap
    against it is systematically wrong -- the failure that wasted the
    first U4 premise check."""

    def test_a_component_overlapping_two_boxes_belongs_to_one(self):
        """Its centre decides. Overlap alone would claim both."""
        comps = [c(0, 8, 0, 12, 9)]        # centre x = 10.5
        rep = match(comps, [g("a", 0, 0, 10, 10), g("b", 10, 0, 20, 10)])
        self.assertEqual(rep.count(MatchKind.MERGED), 0)
        self.assertEqual(rep.count(MatchKind.ONE_TO_ONE), 1)
        self.assertEqual(rep.gold[1].components, (0,))

    def test_a_narrow_glyph_in_a_wide_advance_box_still_matches(self):
        """Side bearings make the advance box much wider than the ink.
        A centre test is unaffected; an overlap threshold would not be."""
        comps = [c(0, 45, 2, 55, 18)]
        rep = match(comps, [g("l", 0, 0, 100, 20)])
        self.assertEqual(rep.count(MatchKind.ONE_TO_ONE), 1)

    def test_a_component_just_outside_a_box_is_image_only(self):
        comps = [c(0, 20, 20, 29, 29)]
        rep = match(comps, [g("a", 0, 0, 10, 10)])
        self.assertEqual(rep.by_kind[MatchKind.IMAGE_ONLY], [0])


class T10_4_GlyphsArriveInPoints(unittest.TestCase):

    def test_glyphs_are_transformed_before_matching(self):
        """The realistic call: components in pixels, glyphs in points."""
        t = page_transform(100.0, 72.0)          # 1 pt == 1 px, y flipped
        # glyph occupying the top-left 10x10 pt of the page
        glyph = g("a", 0.0, 90.0, 10.0, 100.0)
        comps = [c(0, 2, 2, 8, 8)]               # pixels, near the top-left
        rep = match(comps, [glyph], to_pixels=t)
        self.assertEqual(rep.count(MatchKind.ONE_TO_ONE), 1)

    def test_without_the_transform_the_same_glyph_misses(self):
        """The y flip is not cosmetic: unflipped, this glyph sits at the
        bottom of the page and matches nothing."""
        glyph = g("a", 0.0, 90.0, 10.0, 100.0)
        comps = [c(0, 2, 2, 8, 8)]
        rep = match(comps, [glyph])
        self.assertEqual(rep.count(MatchKind.IMAGE_ONLY), 1)

    def test_a_transform_that_reverses_an_axis_still_gives_sane_boxes(self):
        """`page_transform` can map x1 below x0; the matcher must not
        produce an empty box from that."""
        t = page_transform(100.0, 72.0, rotate=180, page_width_pt=100.0)
        rep = match([c(0, 48, 48, 52, 52)],
                    [g("a", 45.0, 45.0, 55.0, 55.0)], to_pixels=t)
        self.assertEqual(rep.count(MatchKind.ONE_TO_ONE), 1)


class T10_5_DeterminismAndEdges(unittest.TestCase):

    def test_matching_is_independent_of_input_order(self):
        """G6."""
        comps = [c(i, i * 20, 0, i * 20 + 9, 9) for i in range(6)]
        glyphs = [g(chr(97 + i), i * 20, 0, i * 20 + 10, 10)
                  for i in range(6)]
        want = match(comps, glyphs)
        rng = random.Random(7)
        for trial in range(6):
            cs, gs = comps[:], glyphs[:]
            rng.shuffle(cs)
            with self.subTest(trial=trial):
                got = match(cs, gs)
                self.assertEqual(got.by_kind, want.by_kind)
                self.assertEqual([x.components for x in got.gold],
                                 [x.components for x in want.gold])

    def test_an_empty_page_is_not_a_division_by_zero(self):
        """G7."""
        rep = match([], [])
        self.assertEqual(rep.assignments, 0)
        self.assertEqual(rep.fraction(MatchKind.ONE_TO_ONE), 0.0)
        self.assertEqual(rep.glyphs_without_ink, 0.0)
        self.assertEqual(rep.report(), "no components and no glyphs")

    def test_glyphs_without_ink_is_the_resolution_signal(self):
        """Measured 1.11% at 400 dpi, 9.20% at 200, 58.78% at 100."""
        rep = match([c(0, 0, 0, 9, 9)],
                    [g("a", 0, 0, 10, 10)] +
                    [g("z", 500 + i, 500, 509 + i, 509) for i in range(9)])
        self.assertAlmostEqual(rep.glyphs_without_ink, 0.9, places=9)

    def test_a_page_of_only_ink_reports_all_image_only(self):
        rep = match([c(i, i * 20, 0, i * 20 + 9, 9) for i in range(5)], [])
        self.assertEqual(rep.count(MatchKind.IMAGE_ONLY), 5)
        self.assertEqual(rep.glyph_count, 0)


class T10_6_CocoExport(unittest.TestCase):
    """G5: lossless with respect to the match."""

    def test_every_gold_glyph_becomes_an_annotation(self):
        rep = match([c(0, 0, 0, 9, 9)],
                    [g("a", 0, 0, 10, 10), g("b", 90, 90, 99, 99)])
        doc = to_coco(rep, image_name="p1.png", width=100, height=100)
        self.assertEqual(len(doc["annotations"]), 2)
        self.assertEqual(doc["images"][0]["file_name"], "p1.png")

    def test_annotations_carry_their_match_class(self):
        """Without this an export silently averages the residual into
        the clean data, which is the thing units.md forbids."""
        rep = match([c(0, 0, 0, 9, 9)],
                    [g("a", 0, 0, 10, 10), g("b", 90, 90, 99, 99)])
        kinds = {a["match_kind"] for a in to_coco(rep)["annotations"]}
        self.assertIn("1:1", kinds)
        self.assertIn("glyph with no ink", kinds)

    def test_annotations_carry_their_component_ids(self):
        comps = [c(0, 2, 0, 4, 2), c(1, 2, 5, 4, 12)]
        rep = match(comps, [g("i", 0, 0, 8, 14)])
        ann = to_coco(rep)["annotations"][0]
        self.assertEqual(sorted(ann["components"]), [0, 1])

    def test_categories_are_one_per_distinct_character(self):
        rep = match([], [g("a", 0, 0, 1, 1), g("b", 2, 0, 3, 1),
                         g("a", 4, 0, 5, 1)])
        doc = to_coco(rep)
        self.assertEqual(sorted(c["name"] for c in doc["categories"]),
                         ["a", "b"])

    def test_bboxes_are_x_y_width_height(self):
        rep = match([], [g("a", 10, 20, 30, 50)])
        self.assertEqual(to_coco(rep)["annotations"][0]["bbox"],
                         [10, 20, 20, 30])

    def test_the_export_is_json_serialisable(self):
        import json
        rep = match([c(0, 0, 0, 9, 9)], [g("a", 0, 0, 10, 10)])
        self.assertIn('"match_kind"', json.dumps(to_coco(rep)))


if __name__ == "__main__":
    unittest.main()
