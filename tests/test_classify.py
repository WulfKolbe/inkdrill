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


class T13_9_ConjunctionVerifier(unittest.TestCase):
    """`agrees(extents_tol=...)`: signature AND extents.

    The signature is scale-invariant by construction, so `o` and `O`
    carry the identical one at every size and no amount of signature
    resolution separates them. Extents is the channel that can, which is
    why the verifier is a conjunction rather than a finer single check.
    """

    def _clf(self):
        clf = Classifier()
        # Same signature, very different size -- the o/O shape.
        clf.add(Template("O", 0b1111, (1, 1, 1, 1, 1, 1), (1.0, 40.0, 40.0, 1.0)))
        return clf

    def test_signature_only_accepts_a_size_mismatch(self):
        q = Template("o", 0b1111, (1, 1, 1, 1, 1, 1), (1.0, 12.0, 12.0, 1.0))
        self.assertTrue(self._clf().agrees(q, "O"))

    def test_the_conjunction_rejects_it(self):
        q = Template("o", 0b1111, (1, 1, 1, 1, 1, 1), (1.0, 12.0, 12.0, 1.0))
        self.assertFalse(self._clf().agrees(q, "O", extents_tol=0.4))

    def test_the_conjunction_still_accepts_a_true_match(self):
        q = Template("O", 0b1111, (1, 1, 1, 1, 1, 1), (1.0, 40.0, 41.0, 1.0))
        self.assertTrue(self._clf().agrees(q, "O", extents_tol=0.4))

    def test_a_signature_mismatch_is_rejected_whatever_the_tolerance(self):
        q = Template("x", 0b1111, (2, 0, 3, 3, 1, 1), (1.0, 40.0, 40.0, 1.0))
        self.assertFalse(self._clf().agrees(q, "O", extents_tol=1e9))

    def test_the_default_is_unchanged(self):
        # Every recorded figure was measured signature-only.
        q = Template("o", 0b1111, (1, 1, 1, 1, 1, 1), (1.0, 12.0, 12.0, 1.0))
        self.assertEqual(self._clf().agrees(q, "O"),
                         self._clf().agrees(q, "O", extents_tol=None))


if __name__ == "__main__":
    unittest.main()


class T13_9_RankedCandidates(unittest.TestCase):
    """C1: `classify` always built the ranking and threw it away."""

    @staticmethod
    def _clf(n=6):
        c = Classifier(channels=Channels(1.0, 0.0, 0.0))
        for i in range(n):
            c.add(Template(f"l{i}", (1 << (i + 1)) - 1))
        return c

    def test_a_query_returns_several_candidates_with_monotone_distances(self):
        got = self._clf().classify(Template("?", 0b111))
        self.assertGreaterEqual(len(got.candidates), 2)
        self.assertEqual([d for _, d in got.candidates],
                         sorted(d for _, d in got.candidates))

    def test_label_and_runner_up_are_VIEWS_onto_the_list(self):
        got = self._clf().classify(Template("?", 0b111))
        self.assertEqual(got.label, got.candidates[0][0])
        self.assertEqual(got.distance, got.candidates[0][1])
        self.assertEqual(got.runner_up, got.candidates[1][0])
        self.assertEqual(got.runner_up_distance, got.candidates[1][1])

    def test_top_k_truncates_the_REPORT_not_the_SEARCH(self):
        """The winner must be the same one the full search finds, so a
        small `top_k` cannot change the answer -- only the tail."""
        q = Template("?", 0b1011)
        full = self._clf(6).classify(q, top_k=0)
        cut = self._clf(6).classify(q, top_k=2)
        self.assertEqual(len(full.candidates), 6)
        self.assertEqual(len(cut.candidates), 2)
        self.assertEqual(cut.candidates, full.candidates[:2])

    def test_one_label_leaves_the_runner_up_None_and_the_margin_infinite(self):
        c = Classifier(channels=Channels(1.0, 0.0, 0.0))
        c.add(Template("only", 0b1))
        got = c.classify(Template("?", 0b1))
        self.assertIsNone(got.runner_up)
        self.assertEqual(got.margin, float("inf"))

    def test_an_empty_prediction_is_refused(self):
        """`classify` raises `NoTemplates` rather than returning one, so
        the guard exists to stop a caller constructing a Prediction whose
        `.label` would raise IndexError instead."""
        with self.assertRaises(ValueError):
            Prediction(())
        self.assertEqual(Prediction((("a", 1.0),)).label, "a")

    def test_a_negative_top_k_is_refused_and_zero_accepted(self):
        with self.assertRaises(ValueError):
            self._clf().classify(Template("?", 0b1), top_k=-1)
        self.assertEqual(len(self._clf(4).classify(Template("?", 0b1),
                                                  top_k=0).candidates), 4)


class T13_10_Prune(unittest.TestCase):
    """C2: `agrees` over a list. Every outcome asserted to fire."""

    @staticmethod
    def _clf():
        c = Classifier(channels=Channels(1.0, 1.0, 0.0))
        c.add(Template("ring", 0b1, (1, 1, 1, 1, 0, 0)))
        c.add(Template("bar", 0b11, (1, 0, 1, 1, 0, 0)))
        c.add(Template("two", 0b111, (2, 0, 2, 2, 0, 0)))
        return c

    def test_only_topology_consistent_candidates_survive(self):
        c = self._clf()
        q = Template("?", 0b1, (1, 1, 1, 1, 0, 0))
        kept = c.prune(q, (("bar", 1.0), ("ring", 2.0), ("two", 3.0)))
        self.assertEqual(kept, (("ring", 2.0),))

    def test_order_and_distances_are_PRESERVED(self):
        """Pruning composes with ranking rather than replacing it."""
        c = self._clf()
        q = Template("?", 0b1, (1, 1, 1, 1, 0, 0))
        c.add(Template("ring2", 0b1, (1, 1, 1, 1, 0, 0)))
        kept = c.prune(q, (("ring2", 0.5), ("bar", 1.0), ("ring", 2.0)))
        self.assertEqual(kept, (("ring2", 0.5), ("ring", 2.0)))

    def test_an_EMPTY_result_is_a_legitimate_value(self):
        c = self._clf()
        q = Template("?", 0b1, (9, 9, 9, 9, 9, 9))
        self.assertEqual(c.prune(q, (("ring", 1.0), ("bar", 2.0))), ())

    def test_a_query_with_no_signature_prunes_NOTHING(self):
        """The verifier abstains rather than rejecting when it has no
        channel to judge on -- the same rule `agrees` follows.

        The fixture includes a label whose templates carry NO signature.
        Without that, dropping the abstain still returns everything --
        the loop's `<= sig_tol` is satisfied by an empty signature -- so
        a fixture where every label has one cannot tell the two apart.
        That was the first version of this test, and the mutant lived.
        """
        c = self._clf()
        c.add(Template("plain", 0b1010))          # no signature at all
        cands = (("ring", 1.0), ("bar", 2.0), ("plain", 3.0))
        self.assertEqual(c.prune(Template("?", 0b1), cands), cands)
        # and the same query WITH a signature does drop it, so the
        # abstain is doing the work rather than the fixture being inert
        q = Template("?", 0b1, (1, 1, 1, 1, 0, 0))
        self.assertNotIn("plain", [l for l, _ in c.prune(q, cands)])

    def test_prune_equals_agrees_applied_one_by_one(self):
        """The fast path's oracle. `prune` indexes templates by label in
        one pass; `agrees` rescans them per call. They must not diverge."""
        c = self._clf()
        for bits in (0b1, 0b11, 0b111):
            for sig in ((1, 1, 1, 1, 0, 0), (1, 0, 1, 1, 0, 0),
                        (2, 0, 2, 2, 0, 0)):
                q = Template("?", bits, sig)
                cands = tuple((t.label, 1.0) for t in c.templates)
                self.assertEqual(
                    c.prune(q, cands),
                    tuple((l, d) for l, d in cands if c.agrees(q, l)))

    def test_sig_tol_widens_the_filter(self):
        """Measured, not assumed: on the 647-class maths set widening
        the signature buys survival slowly (92.7% to 95.8%) while the
        median survivor count explodes (33 to 102). Here it only has to
        be shown to DO something, so the parameter cannot be inert."""
        c = self._clf()
        q = Template("?", 0b1, (1, 1, 1, 1, 0, 0))
        cands = (("ring", 1.0), ("bar", 2.0), ("two", 3.0))
        self.assertEqual(len(c.prune(q, cands, sig_tol=0)), 1)
        self.assertGreater(len(c.prune(q, cands, sig_tol=2)), 1)
