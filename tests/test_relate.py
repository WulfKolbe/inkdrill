"""M2.1: candidate edges for a symbol relation graph.

Hermetic. Boxes are laid out by hand so each test names the geometric
situation it checks -- occlusion, collinearity, containment -- rather
than asserting a recorded edge list.
"""

import unittest

from inkdrill.relate import (MAX_SYMBOLS, Symbol, TooManySymbols, Unresolved,
                             blocked, candidates, clip, needs_identity,
                             partition)


def box(x, y, w=10.0, h=10.0):
    return (x, y, x + w, y + h)


class M2_1_Occlusion(unittest.TestCase):
    """G2: the property line-of-sight exists for."""

    def test_a_symbol_between_two_others_blocks_them(self):
        a, b, c = box(0, 0), box(50, 0), box(100, 0)
        self.assertTrue(blocked(a, c, [b]))

    def test_a_symbol_beside_the_segment_does_not_block(self):
        a, c = box(0, 0), box(100, 0)
        aside = box(50, 200)
        self.assertFalse(blocked(a, c, [aside]))

    def test_three_collinear_symbols_give_two_edges_not_three(self):
        """The measured failure of kNN: 6NN connected 40,706 pairs with
        a third symbol between them."""
        e = candidates([box(0, 0), box(50, 0), box(100, 0)])
        self.assertEqual(e, [(0, 1), (1, 2)])

    def test_an_endpoint_does_not_occlude_its_own_edge(self):
        """G4. Without this every adjacent pair blocks itself and the
        graph comes back empty."""
        a, b = box(0, 0), box(20, 0)
        self.assertFalse(blocked(a, b, []))
        self.assertEqual(candidates([a, b]), [(0, 1)])

    def test_a_blocker_grazing_an_endpoint_does_not_occlude(self):
        """G4's tolerance, and the case that pins it.

        A symbol whose box overlaps its neighbour's CENTRE by a hair --
        a tight kern, an accent, a subscript tucked under a base --
        clips the segment at t just above 0. Without the `_NEAR`
        tolerance that counts as occlusion and disconnects two symbols
        that plainly see each other, which is a graph missing its most
        obvious edges. With it, the crossing must lie genuinely
        between.
        """
        a, b = (0.0, 0.0, 20.0, 20.0), (40.0, 0.0, 60.0, 20.0)
        graze = (8.0, 0.0, 10.5, 20.0)          # crosses at t = 0.0125
        self.assertFalse(blocked(a, b, [graze]))
        # (1, 2) is correctly ABSENT: `a` lies between `b` and the
        # grazing box, so that pair really is occluded. The edge under
        # test is (0, 1), which the tolerance is what preserves.
        self.assertEqual(candidates([a, b, graze]), [(0, 1), (0, 2)])

    def test_a_blocker_genuinely_between_still_occludes(self):
        """The other side of that tolerance: it must not swallow a real
        occlusion just past the threshold."""
        a, b = (0.0, 0.0, 20.0, 20.0), (40.0, 0.0, 60.0, 20.0)
        mid = (24.0, 0.0, 30.0, 20.0)
        self.assertTrue(blocked(a, b, [mid]))


class M2_5_Clip(unittest.TestCase):
    """The interval itself, not the boolean downstream of it.

    An audit found six branches of this loop unfalsifiable from outside:
    `blocked` returns only True/False, so a wrong interval with the
    right sign is indistinguishable from a right one. The cause is
    geometric -- an AXIS-ALIGNED segment leaves one slab pair
    degenerate, so `t0` and `t1` are each set by a single candidate and
    the max/min refinements never compete. Only a DIAGONAL segment
    makes them compete, and only asserting `(t0, t1)` shows which won.
    """

    def test_a_horizontal_segment_clips_on_x_alone(self):
        # Ray (0,5) + t*(100,0); box spans x 20..40, y 0..10.
        self.assertEqual(clip(0.0, 5.0, 100.0, 0.0, (20.0, 0.0, 40.0, 10.0)),
                         (0.2, 0.4))

    def test_a_box_the_parallel_segment_misses_returns_None(self):
        """The `p == 0 and q < 0` branch: parallel to the y slabs and
        outside them."""
        self.assertIsNone(
            clip(0.0, 5.0, 100.0, 0.0, (20.0, 50.0, 40.0, 60.0)))

    def test_a_diagonal_segment_makes_BOTH_slabs_compete(self):
        """t0 is the max of the two entry parameters and t1 the min of
        the two exits. Here x gives (0.2, 0.4) and y gives (0.3, 0.5),
        so the answer is (0.3, 0.4) -- a value neither slab produced
        alone, which is what pins both refinements.
        """
        got = clip(0.0, 0.0, 100.0, 100.0, (20.0, 30.0, 40.0, 50.0))
        self.assertIsNotNone(got)
        self.assertAlmostEqual(got[0], 0.3)
        self.assertAlmostEqual(got[1], 0.4)

    def test_a_diagonal_segment_that_passes_the_corner_returns_None(self):
        """x admits (0.6, 0.8) and y admits (0.1, 0.3): disjoint, so the
        ray misses the box despite crossing both slabs. This is the
        early-out, and a mutant that drops it returns an inverted
        interval instead of None."""
        self.assertIsNone(
            clip(0.0, 0.0, 100.0, 100.0, (60.0, 10.0, 80.0, 30.0)))

    def test_the_interval_is_clamped_to_the_segment(self):
        """A box containing the whole ray gives exactly (0, 1) -- the
        initial values survive when no slab tightens them."""
        self.assertEqual(clip(10.0, 10.0, 5.0, 5.0, (0.0, 0.0, 100.0, 100.0)),
                         (0.0, 1.0))

    def test_a_box_entirely_behind_the_start_returns_None(self):
        self.assertIsNone(clip(50.0, 5.0, 50.0, 0.0, (0.0, 0.0, 10.0, 10.0)))

    def test_a_degenerate_box_touches_without_crossing(self):
        """The final `t1 > t0` guard, and the only thing that reaches it.

        A zero-width box gives both x slabs the same parameter, so
        `t0 == t1` exactly: the ray touches without ever being inside.
        The early-outs cannot catch it -- they only fire on an INVERTED
        interval -- so without this guard a degenerate box occludes
        everything behind it.
        """
        self.assertIsNone(clip(0.0, 5.0, 100.0, 0.0, (20.0, 0.0, 20.0, 10.0)))
        a, b = (0.0, 0.0, 10.0, 10.0), (90.0, 0.0, 100.0, 10.0)
        self.assertFalse(blocked(a, b, [(50.0, 0.0, 50.0, 10.0)]))

    def test_a_negative_direction_clips_the_same_interval(self):
        """`p < 0` is the mirror of `p > 0`; running the same box from
        the far end must give the mirrored parameters."""
        fwd = clip(0.0, 5.0, 100.0, 0.0, (20.0, 0.0, 40.0, 10.0))
        rev = clip(100.0, 5.0, -100.0, 0.0, (20.0, 0.0, 40.0, 10.0))
        self.assertEqual(fwd, (0.2, 0.4))
        self.assertAlmostEqual(rev[0], 0.6)
        self.assertAlmostEqual(rev[1], 0.8)


class M2_2_Shape(unittest.TestCase):
    """G3, G5, G6: the shape of the answer."""

    def test_edges_are_sorted_undirected_pairs(self):
        e = candidates([box(0, 0), box(0, 40), box(40, 0)])
        self.assertEqual(e, sorted(e))
        for i, j in e:
            self.assertLess(i, j)
        self.assertEqual(len(e), len(set(e)))

    def test_no_self_edges(self):
        for i, j in candidates([box(0, 0), box(30, 0), box(60, 30)]):
            self.assertNotEqual(i, j)

    def test_fewer_than_two_boxes_gives_no_edges(self):
        self.assertEqual(candidates([]), [])
        self.assertEqual(candidates([box(0, 0)]), [])

    def test_too_many_symbols_raises_rather_than_truncating(self):
        many = [box(i * 20.0, 0.0) for i in range(MAX_SYMBOLS + 1)]
        with self.assertRaises(TooManySymbols):
            candidates(many)

    def test_the_limit_is_an_argument(self):
        with self.assertRaises(TooManySymbols):
            candidates([box(0, 0), box(20, 0), box(40, 0)], max_symbols=2)


class M2_3_Layouts(unittest.TestCase):
    """Situations a maths line actually contains."""

    def test_a_superscript_sees_its_base(self):
        base, sup = box(0, 20, 12, 12), box(12, 12, 7, 7)
        self.assertIn((0, 1), candidates([base, sup]))

    def test_a_fraction_bar_does_not_hide_numerator_from_denominator(self):
        """They ARE occluded by the rule, and that is correct -- the
        relation runs through the bar, not around it. Both halves must
        still reach the bar itself."""
        num, bar, den = box(10, 0, 20, 8), box(0, 12, 40, 2), box(10, 20, 20, 8)
        e = candidates([num, bar, den])
        self.assertIn((0, 1), e)
        self.assertIn((1, 2), e)
        self.assertNotIn((0, 2), e)

    def test_a_large_operator_blocks_across_itself(self):
        left, op, right = box(0, 10, 8, 8), box(20, 0, 16, 40), box(50, 10, 8, 8)
        e = candidates([left, op, right])
        self.assertNotIn((0, 2), e)

    def test_a_row_of_symbols_is_a_path_not_a_clique(self):
        row = [box(i * 20.0, 0.0, 10.0, 10.0) for i in range(6)]
        e = candidates(row)
        self.assertEqual(e, [(i, i + 1) for i in range(5)])

    def test_two_stacked_columns_connect_within_and_across(self):
        col = [box(0, 0), box(0, 30), box(40, 0), box(40, 30)]
        e = set(candidates(col))
        self.assertIn((0, 1), e)
        self.assertIn((2, 3), e)
        self.assertIn((0, 2), e)

    def test_edges_per_node_stays_near_one_on_a_row(self):
        """The measured headline: LOS gave 0.96 edges/node against
        6NN's 3.29. A row must not come back dense."""
        row = [box(i * 20.0, 0.0, 10.0, 10.0) for i in range(20)]
        self.assertLess(len(candidates(row)) / len(row), 1.2)


class M2_4_Unresolved(unittest.TestCase):
    """G7: geometry yes, symbol-keyed rewriting no.

    The classifier abstains on 14.4% of even its correct answers. This
    is the decision about what those nodes are, and both halves of it
    are load-bearing.
    """

    def test_an_unresolved_symbol_still_has_geometry(self):
        u = Symbol(box(0, 0))
        self.assertEqual(u.centre, (5.0, 5.0))
        self.assertFalse(u.resolved)

    def test_a_resolved_symbol_returns_its_name(self):
        """The other side of G7, and it was missing.

        Every `.label` reference in this module sat inside an
        `assertRaises`, so `label` could be made to raise
        unconditionally and the whole suite still passed. The refusal
        was tested and the non-refusal was not -- the same one-sided
        shape as U4's rotation guard and U8's dispatch sort.
        """
        s = Symbol(box(0, 0), "summation")
        self.assertTrue(s.resolved)
        self.assertEqual(s.label, "summation")

    def test_reading_the_label_raises_rather_than_returning_a_sentinel(self):
        with self.assertRaises(Unresolved):
            Symbol(box(0, 0), reason="margin 0.02").label

    def test_the_reason_travels_with_the_refusal(self):
        """The abstention is a finding, not a gap: a QC surface needs to
        show WHICH glyphs a human must adjudicate, and why."""
        with self.assertRaises(Unresolved) as cm:
            Symbol(box(0, 0), reason="margin 0.02").label
        self.assertIn("margin 0.02", str(cm.exception))

    def test_two_unresolved_symbols_are_not_the_same_symbol(self):
        """Why a sentinel was refused. `"UNKNOWN"` compares equal to
        itself, so a rule keyed on equality would fire between two
        glyphs that were merely both unidentified."""
        a, b = Symbol(box(0, 0)), Symbol(box(50, 0))
        for s in (a, b):
            with self.assertRaises(Unresolved):
                s.label

    def test_an_unresolved_node_is_still_an_occluder(self):
        """The half that dropping the node would break: its neighbours
        would see through a hole that is not there, and `candidates`
        would connect symbols a real glyph separates."""
        boxes = [box(0, 0), box(50, 0), box(100, 0)]
        self.assertNotIn((0, 2), candidates(boxes))

    def test_an_unresolved_node_still_takes_edges(self):
        boxes = [s.box for s in (Symbol(box(0, 0), "x"),
                                 Symbol(box(30, 0)),
                                 Symbol(box(60, 0), "y"))]
        e = candidates(boxes)
        self.assertIn((0, 1), e)
        self.assertIn((1, 2), e)

    def test_a_symbol_keyed_rule_is_refused_when_any_participant_is_unknown(self):
        known = Symbol(box(0, 0), "summation")
        unknown = Symbol(box(0, 30))
        self.assertTrue(needs_identity([known, Symbol(box(9, 9), "i")]))
        self.assertFalse(needs_identity([known, unknown]))

    def test_partition_returns_the_unresolved_rather_than_counting_them(self):
        syms = [Symbol(box(0, 0), "a"), Symbol(box(20, 0)),
                Symbol(box(40, 0), "b")]
        keep, drop = partition(syms)
        self.assertEqual([s.name for s in keep], ["a", "b"])
        self.assertEqual(len(drop), 1)
        self.assertEqual(drop[0].box, box(20, 0))


if __name__ == "__main__":
    unittest.main()
