"""Unit 12 tests. Every test name is quoted verbatim in the status report."""

import random
import unittest

from inkdrill.domains import (DIMENSIONS, ConvexityResult, Dimension, Domain,
                              Point, UnknownDimension, convexity, describe,
                              dimensions_of, efficiency,
                              joint_mutual_information, mi_ceiling,
                              mutual_information)

FEATURES = {"width": 20, "height": 40, "area": 300,
            "elongation": 3.5, "cycles": 1, "births": 2, "merges": 1,
            "splits": 1, "depth": 0, "x": 100, "y": 250}


class T12_1_DomainsAreSeparable(unittest.TestCase):
    """G1. units.md asks for TRANSFORM as its own domain "so rotation and
    shear stop contaminating shape" -- that separation is why this is a
    set of domains rather than one flat vector."""

    def test_every_dimension_declares_exactly_one_domain(self):
        for d in DIMENSIONS:
            with self.subTest(d.name):
                self.assertIsInstance(d.domain, Domain)
        names = [d.name for d in DIMENSIONS]
        self.assertEqual(len(names), len(set(names)))

    def test_a_point_is_partitioned_by_domain(self):
        p = describe(FEATURES)
        for dom, vals in p.values.items():
            for name in vals:
                with self.subTest(name):
                    self.assertEqual(
                        next(d for d in DIMENSIONS if d.name == name).domain,
                        dom)

    def test_shape_and_size_do_not_share_a_bucket(self):
        p = describe(FEATURES)
        self.assertIn("elongation", p.domain(Domain.SHAPE))
        self.assertIn("aspect", p.domain(Domain.SIZE))
        self.assertNotIn("aspect", p.domain(Domain.SHAPE))
        self.assertNotIn("elongation", p.domain(Domain.SIZE))

    def test_the_typographic_domain_is_declared_and_empty(self):
        """G5: it needs U9's reference lines, which are not built. An
        empty domain is reported empty rather than silently omitted."""
        self.assertIn(Domain.TYPOGRAPHIC, list(Domain))
        self.assertEqual(dimensions_of(Domain.TYPOGRAPHIC), ())

    def test_the_transform_domain_is_declared_and_empty(self):
        """Needs a per-character CTM from U10. Named rather than guessed
        at."""
        self.assertEqual(dimensions_of(Domain.TRANSFORM), ())

    def test_an_unknown_dimension_name_is_refused(self):
        with self.assertRaises(UnknownDimension):
            describe(FEATURES).get("nonexistent")


class T12_2_DescribeIsTotalAndPure(unittest.TestCase):

    def test_a_missing_input_leaves_the_dimension_absent(self):
        """G6: absent, never a wrong value."""
        p = describe({"width": 10})
        self.assertIsNone(p.get("height"))
        self.assertIsNone(p.get("aspect"))
        self.assertEqual(p.get("width"), 10.0)

    def test_a_zero_height_does_not_divide_by_zero(self):
        p = describe({"width": 10, "height": 0})
        self.assertIsNone(p.get("aspect"))

    def test_an_empty_feature_dict_yields_an_empty_point(self):
        self.assertEqual(describe({}).present, ())

    def test_derived_dimensions_are_computed(self):
        p = describe(FEATURES)
        self.assertAlmostEqual(p.get("aspect"), 20 / 40, places=9)
        self.assertAlmostEqual(p.get("fill"), 300 / (20 * 40), places=9)

    def test_describe_does_not_mutate_its_input(self):
        """G7: pure."""
        before = dict(FEATURES)
        describe(FEATURES)
        self.assertEqual(FEATURES, before)

    def test_describe_is_deterministic(self):
        self.assertEqual(describe(FEATURES).values,
                         describe(FEATURES).values)


class T12_3_TheDesignTestIsShipped(unittest.TestCase):
    """G2 and G3. units.md sets one rule -- a dimension earns its place
    when the concepts become convex in it -- so the unit ships the test
    rather than describing it."""

    def test_a_perfectly_separating_dimension_scores_one(self):
        values = [1, 1, 1, 10, 10, 10, 20, 20, 20]
        labels = ["a"] * 3 + ["b"] * 3 + ["c"] * 3
        self.assertAlmostEqual(convexity(values, labels).score, 1.0,
                               places=9)

    def test_a_useless_dimension_scores_near_the_baseline(self):
        rng = random.Random(7)
        labels = [rng.choice("abcde") for _ in range(500)]
        values = [rng.random() for _ in range(500)]
        got = convexity(values, labels)
        self.assertLess(got.lift, 2.0)

    def test_the_baseline_is_reported_beside_the_score(self):
        """G3: a score means nothing without the class count."""
        got = convexity([1, 2, 3, 4], ["a", "a", "b", "b"])
        self.assertEqual(got.classes, 2)
        self.assertAlmostEqual(got.baseline, 0.5, places=9)
        self.assertGreater(got.lift, 1.0)

    def test_an_outlier_does_not_destroy_the_score(self):
        """G2, and the reason the interval is inter-percentile. On the
        first attempt at this measurement a min/max interval dragged all
        eleven dimensions to the baseline and made them look worthless."""
        values = [1, 1, 1, 1, 1, 1, 1, 1, 1, 999] + [500] * 10
        labels = ["a"] * 10 + ["b"] * 10
        robust = convexity(values, labels).score
        wide = convexity(values, labels, low=0.0, high=1.0).score
        self.assertGreater(robust, wide)
        self.assertGreater(robust, 0.9)

    def test_convexity_needs_matching_lengths(self):
        with self.assertRaises(ValueError):
            convexity([1, 2, 3], ["a", "b"])

    def test_empty_input_is_not_a_division_by_zero(self):
        got = convexity([], [])
        self.assertEqual(got.score, 0.0)
        self.assertEqual(got.lift, 0.0)

    def test_no_class_meeting_the_minimum_is_not_a_crash(self):
        """Values present but every class too small. Reachable only when
        the empty-input guard does not fire first, which is why branch
        mutation found it and the empty-input test did not."""
        got = convexity([1, 2, 3], ["a", "b", "c"], min_per_class=2)
        self.assertEqual(got.classes, 0)
        self.assertEqual(got.score, 0.0)
        self.assertEqual(got.lift, 0.0)
        self.assertEqual(got.samples, 3)

    def test_the_extractors_do_not_raise_when_called_directly(self):
        """describe() catches, but an extractor used on its own must not
        raise -- the guards inside them are redundant with describe and
        exist for that reason.

        A DERIVED dimension returns None on a zero denominator; a plain
        one returns the zero, because 0 is a legitimate width. My first
        version of this test demanded None from both and was wrong."""
        degenerate = {"width": 0, "height": 0, "area": 0}
        derived = {"aspect", "fill"}
        for d in DIMENSIONS:
            with self.subTest(d.name):
                self.assertIsNone(d.extract({}))
                got = d.extract(degenerate)          # must not raise
                if d.name in derived:
                    self.assertIsNone(got)
                elif got is not None:
                    self.assertEqual(got, 0.0)

    def test_classes_below_the_minimum_are_ignored(self):
        got = convexity([1, 2, 3, 99], ["a", "a", "a", "b"],
                        min_per_class=2)
        self.assertEqual(got.classes, 1)


class T12_4_MutualInformation(unittest.TestCase):

    def test_a_determining_dimension_scores_near_one(self):
        values = [1] * 50 + [100] * 50
        labels = ["a"] * 50 + ["b"] * 50
        self.assertGreater(mutual_information(values, labels), 0.9)

    def test_a_random_dimension_scores_near_zero(self):
        rng = random.Random(11)
        labels = [rng.choice("abcd") for _ in range(800)]
        values = [rng.random() for _ in range(800)]
        self.assertLess(mutual_information(values, labels), 0.15)

    def test_a_single_label_carries_no_information(self):
        self.assertEqual(mutual_information([1, 2, 3], ["a", "a", "a"]), 0.0)

    def test_empty_input_scores_zero(self):
        self.assertEqual(mutual_information([], []), 0.0)

    def test_mutual_information_needs_matching_lengths(self):
        with self.assertRaises(ValueError):
            mutual_information([1, 2], ["a"])


class T12_5_MeasuredScoresAreRecorded(unittest.TestCase):
    """G4. An unmeasured dimension must be visibly unmeasured, so adding
    a weak one is a decision rather than an accident."""

    def test_every_measured_dimension_carries_all_three_scores(self):
        for d in DIMENSIONS:
            if d.measured:
                with self.subTest(d.name):
                    self.assertIsNotNone(d.convexity)
                    self.assertIsNotNone(d.lift)
                    self.assertIsNotNone(d.nmi)

    def test_unmeasured_dimensions_say_so(self):
        unmeasured = [d for d in DIMENSIONS if not d.measured]
        self.assertTrue(unmeasured)
        for d in unmeasured:
            with self.subTest(d.name):
                self.assertIsNone(d.nmi)
                self.assertIn("unmeasured", d.note)

    def test_raw_nmi_ranks_topology_below_size_and_that_is_an_artefact(self):
        """True of the raw column, and NOT a reason to demote topology.

        Normalised MI is bounded by H(X)/H(class): against 23 classes a
        3-valued dimension cannot exceed 0.350 however perfectly it
        separates. The raw ranking cannot tell "weak" from "narrow"."""
        size = [d.nmi for d in dimensions_of(Domain.SIZE) if d.measured]
        topo = [d.nmi for d in dimensions_of(Domain.TOPOLOGY) if d.measured]
        self.assertGreater(min(size), max(topo))
        # ... and no topological dimension could have reached the TOP of
        # that ranking whatever it measured: its ceiling is below the
        # best size dimension. (Not below the WORST -- splits has ceiling
        # 0.423 against height's actual 0.418, so it could in principle
        # have outscored height. The cap binds at the top, not
        # everywhere, and overstating it would be the same error again.)
        for d in dimensions_of(Domain.TOPOLOGY):
            if d.measured:
                with self.subTest(d.name):
                    self.assertLess(d.ceiling, max(size))

    def test_corrected_for_cardinality_the_ordering_inverts(self):
        """The finding that actually reaches U13. Topology is the MOST
        efficient per available bit, geometry the least -- so the raw
        ranking must not be read as a reason to demote it."""
        size = [d.efficiency for d in dimensions_of(Domain.SIZE)
                if d.measured]
        topo = [d.efficiency for d in dimensions_of(Domain.TOPOLOGY)
                if d.measured]
        self.assertGreater(min(topo), max(size))

    def test_cycles_is_stable_but_weakly_discriminative(self):
        """U4 measured the hole count as the most STABLE feature,
        98.7-100% consistent within a class. Here it is among the weakest
        for DISCRIMINATION, because e a o b d p q all have one hole.
        Both are true and neither implies the other."""
        cycles = next(d for d in DIMENSIONS if d.name == "cycles")
        aspect = next(d for d in DIMENSIONS if d.name == "aspect")
        self.assertLess(cycles.nmi, aspect.nmi / 2)
        self.assertIn("STABLE", cycles.note)

    def test_aspect_is_the_strongest_measured_dimension(self):
        best = max((d for d in DIMENSIONS if d.measured),
                   key=lambda d: d.nmi)
        self.assertEqual(best.name, "aspect")

    def test_every_measured_dimension_beats_the_random_baseline(self):
        for d in DIMENSIONS:
            if d.measured:
                with self.subTest(d.name):
                    self.assertGreater(d.lift, 1.0)


if __name__ == "__main__":
    unittest.main()


class T12_6_CardinalityAndJointInformation(unittest.TestCase):
    """G4 and G8. Both correct a conclusion that outran its instrument:
    a marginal ranking cannot see cardinality or joint information."""

    def test_a_low_cardinality_dimension_is_capped_however_perfect(self):
        """A 3-valued dimension that partitions 23 classes PERFECTLY --
        there is no better 3-valued dimension -- still cannot beat a
        mediocre continuous one on raw NMI."""
        labels = [chr(97 + i % 23) for i in range(2300)]
        perfect3 = [ord(c) % 3 for c in labels]
        ceil = mi_ceiling(perfect3, labels)
        self.assertLess(ceil, 0.36)
        self.assertAlmostEqual(mutual_information(perfect3, labels), ceil,
                               places=6)
        self.assertAlmostEqual(efficiency(perfect3, labels), 1.0, places=6)

    def test_efficiency_separates_narrow_from_weak(self):
        labels = [chr(97 + i % 8) for i in range(800)]
        narrow_good = [ord(c) % 2 for c in labels]          # 2 values, tidy
        rng = random.Random(3)
        wide_noise = [rng.random() for _ in labels]          # many, useless
        self.assertGreater(efficiency(narrow_good, labels),
                           efficiency(wide_noise, labels))

    def test_marginals_cannot_see_joint_information(self):
        """Three 3-valued dimensions that TOGETHER determine the class
        exactly. Each looks weak alone."""
        labels, a, b, c = [], [], [], []
        for i in range(27):
            for _ in range(40):
                labels.append(i)
                a.append(i // 9)
                b.append((i // 3) % 3)
                c.append(i % 3)
        for col in (a, b, c):
            self.assertLess(mutual_information(col, labels), 0.4)
        self.assertGreater(
            joint_mutual_information({"a": a, "b": b, "c": c}, labels), 0.95)

    def test_a_joint_score_is_never_below_its_best_marginal(self):
        rng = random.Random(9)
        labels = [rng.choice("abcdef") for _ in range(600)]
        cols = {"p": [rng.random() for _ in labels],
                "q": [ord(l) % 3 for l in labels]}
        best = max(mutual_information(v, labels) for v in cols.values())
        self.assertGreaterEqual(
            joint_mutual_information(cols, labels) + 1e-9, best)

    def test_joint_information_needs_matching_lengths(self):
        with self.assertRaises(ValueError):
            joint_mutual_information({"a": [1, 2]}, ["x"])

    def test_an_empty_domain_scores_zero_rather_than_raising(self):
        self.assertEqual(joint_mutual_information({}, ["a", "b"]), 0.0)

    def test_every_measured_dimension_records_its_ceiling(self):
        for d in DIMENSIONS:
            if d.measured:
                with self.subTest(d.name):
                    self.assertIsNotNone(d.distinct)
                    self.assertIsNotNone(d.ceiling)
                    self.assertLessEqual(d.nmi, d.ceiling + 1e-9)
