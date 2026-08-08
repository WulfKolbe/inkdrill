"""Unit 13 tests. Every test name is quoted verbatim in the status report."""

import random
import unittest

from inkdrill.classify import (GRID, Channels, Classifier, NoTemplates,
                               Prediction, Template, bitmap_distance,
                               confusion, extents_distance, normalise,
                               signature_distance)
from inkdrill.raster import BG, INK, InkMask

BOX = ["#####", "#...#", "#...#", "#...#", "#####"]
BAR = ["#", "#", "#", "#", "#"]
BLOCK = ["####", "####", "####", "####"]


def m(rows):
    return InkMask.from_rows(rows)


def t(label, rows, sig=(), ext=()):
    return Template(label, normalise(m(rows)), sig, ext)


class T13_1_NormalisationIsScaleInvariant(unittest.TestCase):
    """G1. A classifier whose templates depend on render size would need
    one template per point size."""

    def test_the_same_shape_at_two_scales_gives_the_same_bits(self):
        small = ["##", "##"]
        big = ["####", "####", "####", "####"]
        self.assertEqual(normalise(m(small)), normalise(m(big)))

    def test_a_bar_and_a_box_differ(self):
        self.assertNotEqual(normalise(m(BAR)), normalise(m(BOX)))

    def test_normalisation_is_deterministic(self):
        self.assertEqual(normalise(m(BOX)), normalise(m(BOX)))

    def test_a_solid_block_sets_every_bit(self):
        self.assertEqual(normalise(m(BLOCK)).bit_count(), GRID * GRID)

    def test_an_empty_mask_sets_no_bits(self):
        self.assertEqual(normalise(m(["..", ".."])), 0)

    def test_a_thin_stroke_survives_downsampling(self):
        """A cell is ink when ANY source pixel under it is ink -- the
        generous rule, so a failure elsewhere is not an artefact of
        dropping hairlines."""
        rows = ["." * 40 for _ in range(20)]
        rows[10] = "#" * 40
        self.assertGreater(normalise(m(rows)).bit_count(), 0)


class T13_2_DistancesAreMetrics(unittest.TestCase):
    """G2. Nearest neighbour only means something if 'nearest' does."""

    def test_bitmap_distance_to_itself_is_zero(self):
        for rows in (BOX, BAR, BLOCK):
            with self.subTest(rows[0]):
                v = normalise(m(rows))
                self.assertEqual(bitmap_distance(v, v), 0)

    def test_bitmap_distance_is_symmetric_and_non_negative(self):
        a, b = normalise(m(BOX)), normalise(m(BAR))
        self.assertEqual(bitmap_distance(a, b), bitmap_distance(b, a))
        self.assertGreater(bitmap_distance(a, b), 0)

    def test_bitmap_distance_is_a_popcount_of_the_xor(self):
        a, b = normalise(m(BOX)), normalise(m(BAR))
        self.assertEqual(bitmap_distance(a, b), (a ^ b).bit_count())

    def test_signature_distance_is_zero_only_when_equal(self):
        self.assertEqual(signature_distance((1, 2, 0, 1), (1, 2, 0, 1)), 0)
        self.assertEqual(signature_distance((1, 2, 0, 1), (1, 2, 0, 2)), 1)

    def test_extents_distance_scales_channels_to_comparable_units(self):
        """Aspect is O(1) and pixel dimensions are O(10-100); unscaled,
        the sum would be a pixel count with an aspect rounding error
        attached."""
        aspect_only = extents_distance((1.0, 20, 20, 2.0), (2.0, 20, 20, 2.0))
        height_only = extents_distance((1.0, 20, 20, 2.0), (1.0, 60, 20, 2.0))
        self.assertAlmostEqual(aspect_only, 4.0, places=9)
        self.assertAlmostEqual(height_only, 1.0, places=9)


class T13_3_NearestNeighbour(unittest.TestCase):

    def test_an_exact_template_is_recovered(self):
        c = Classifier([t("box", BOX), t("bar", BAR), t("block", BLOCK)])
        got = c.classify(t("?", BOX))
        self.assertEqual(got.label, "box")
        self.assertEqual(got.distance, 0.0)

    def test_a_prediction_carries_its_runner_up_and_margin(self):
        """G4: a caller must be able to reject rather than being forced
        to accept."""
        c = Classifier([t("box", BOX), t("bar", BAR)])
        got = c.classify(t("?", BOX))
        self.assertEqual(got.runner_up, "bar")
        self.assertGreater(got.margin, 0.0)

    def test_the_margin_is_finite_when_a_runner_up_exists(self):
        """`margin > 0` is satisfied by infinity, so it does not prove a
        runner-up was found. Branch mutation: forcing the margin to
        always return inf passed the suite."""
        c = Classifier([t("box", BOX), t("bar", BAR)])
        got = c.classify(t("?", BOX))
        self.assertNotEqual(got.margin, float("inf"))
        self.assertEqual(got.margin,
                         got.runner_up_distance - got.distance)

    def test_a_single_template_gives_an_infinite_margin(self):
        c = Classifier([t("only", BOX)])
        self.assertEqual(c.classify(t("?", BAR)).margin, float("inf"))

    def test_ties_break_deterministically_by_label(self):
        """G5: two runs must agree, or comparing them means nothing."""
        c = Classifier([Template("zeta", 0), Template("alpha", 0)])
        for _ in range(5):
            self.assertEqual(c.classify(Template("?", 0)).label, "alpha")

    def test_classifying_without_templates_raises(self):
        """G6: never invent a label."""
        with self.assertRaises(NoTemplates):
            Classifier().classify(t("?", BOX))

    def test_adding_a_template_changes_the_answer(self):
        c = Classifier([t("bar", BAR)])
        self.assertEqual(c.classify(t("?", BOX)).label, "bar")
        c.add(t("box", BOX))
        self.assertEqual(c.classify(t("?", BOX)).label, "box")

    def test_the_nearest_of_several_same_label_templates_is_used(self):
        """The matching template must be found wherever it sits in the
        list. With it LAST, keeping the last-seen distance also passes --
        so the exact match goes first here."""
        c = Classifier([t("x", BOX), t("x", BAR), t("y", BLOCK)])
        self.assertEqual(c.classify(t("?", BOX)).distance, 0.0)
        c2 = Classifier([t("x", BAR), t("x", BOX), t("y", BLOCK)])
        self.assertEqual(c2.classify(t("?", BOX)).distance, 0.0)


class T13_4_ChannelsAreSeparable(unittest.TestCase):
    """G3. Weights are explicit arguments so any single channel can be
    measured alone -- which is how the premise check produced 99.1%
    bitmap-only against 30.7% signature-only."""

    def test_a_channel_can_be_disabled_by_weight(self):
        a = Template("a", normalise(m(BOX)), (1, 2, 1, 1), (1.0, 5, 5, 2.0))
        b = Template("b", normalise(m(BOX)), (9, 9, 9, 9), (9.0, 90, 90, 9.0))
        bitmap_only = Classifier([a, b], Channels(1.0, 0.0, 0.0))
        self.assertEqual(bitmap_only.distance(a, b), 0.0)
        with_sig = Classifier([a, b], Channels(1.0, 3.0, 0.0))
        self.assertGreater(with_sig.distance(a, b), 0.0)

    def test_each_channel_alone_can_separate_something(self):
        base = normalise(m(BOX))
        a = Template("a", base, (1, 1, 1, 1), (1.0, 10, 10, 1.0))
        b = Template("b", base, (5, 5, 5, 5), (3.0, 30, 30, 4.0))
        for ch in (Channels(0, 1, 0), Channels(0, 0, 1)):
            with self.subTest(ch):
                self.assertGreater(Classifier([a, b], ch).distance(a, b), 0)

    def test_a_missing_channel_is_skipped_not_treated_as_zero(self):
        """A template with no signature must not be scored as having a
        signature of all zeros -- that would make it spuriously close to
        simple shapes."""
        no_sig = Template("a", normalise(m(BOX)))
        has_sig = Template("b", normalise(m(BOX)), (5, 5, 5, 5))
        c = Classifier([no_sig, has_sig])
        self.assertEqual(c.distance(no_sig, has_sig), 0.0)

    def test_default_weights_favour_the_measured_channel_order(self):
        """The bitmap dominates at 99.1% alone, so it is not
        down-weighted relative to channels worth tenths of a point."""
        ch = Channels()
        self.assertGreater(ch.extents, ch.signature)
        self.assertTrue(ch.any_enabled)


class T13_5_TheSignatureIsAVerifier(unittest.TestCase):
    """U12 measured the topological dimensions as narrow but highly
    efficient and 98.7-100% stable within a class, and the premise check
    put the signature at 30.7% alone. That profile is a verifier: good at
    rejecting a wrong answer, poor at generating one."""

    def test_agrees_accepts_a_matching_signature(self):
        c = Classifier([Template("o", normalise(m(BOX)), (1, 1, 0, 1))])
        self.assertTrue(c.agrees(Template("?", 0, (1, 1, 0, 1)), "o"))

    def test_agrees_rejects_a_mismatching_signature(self):
        c = Classifier([Template("o", normalise(m(BOX)), (1, 1, 0, 1))])
        self.assertFalse(c.agrees(Template("?", 0, (0, 2, 1, 1)), "o"))

    def test_agrees_rejects_a_label_with_no_signature_evidence(self):
        c = Classifier([Template("o", normalise(m(BOX)))])
        self.assertFalse(c.agrees(Template("?", 0, (1, 1, 0, 1)), "o"))

    def test_a_query_without_a_signature_is_not_rejected(self):
        """No evidence is not counter-evidence -- including when the
        label has no signature evidence either. Branch mutation found
        that the second half was untested."""
        with_peer = Classifier([Template("o", normalise(m(BOX)),
                                         (1, 1, 0, 1))])
        self.assertTrue(with_peer.agrees(Template("?", 0), "o"))
        no_peer = Classifier([Template("o", normalise(m(BOX)))])
        self.assertTrue(no_peer.agrees(Template("?", 0), "o"))


class T13_6_ConfusionReportsPairs(unittest.TestCase):
    """G7. At 99.3% an accuracy alone would have hidden that every
    remaining error is a multi-component punctuation glyph or a case
    pair, neither of which a better model fixes."""

    def test_a_perfect_classifier_reports_no_pairs(self):
        c = Classifier([t("box", BOX), t("bar", BAR)])
        acc, pairs = confusion(c, [("box", t("?", BOX)),
                                   ("bar", t("?", BAR))])
        self.assertEqual(acc, 1.0)
        self.assertEqual(pairs, {})

    def test_the_offending_pair_is_named(self):
        c = Classifier([t("bar", BAR)])
        acc, pairs = confusion(c, [("box", t("?", BOX))])
        self.assertEqual(acc, 0.0)
        self.assertEqual(pairs, {("box", "bar"): 1})

    def test_accuracy_and_pairs_agree(self):
        rng = random.Random(3)
        c = Classifier([t("box", BOX), t("bar", BAR)])
        queries = [(rng.choice(("box", "bar")),
                    t("?", rng.choice((BOX, BAR)))) for _ in range(40)]
        acc, pairs = confusion(c, queries)
        self.assertAlmostEqual(acc, 1 - sum(pairs.values()) / len(queries),
                               places=9)

    def test_an_empty_query_set_is_not_a_division_by_zero(self):
        acc, pairs = confusion(Classifier([t("box", BOX)]), [])
        self.assertEqual(acc, 0.0)
        self.assertEqual(pairs, {})


if __name__ == "__main__":
    unittest.main()
