"""M2.1: candidate edges for a symbol relation graph.

Hermetic. Boxes are laid out by hand so each test names the geometric
situation it checks -- occlusion, collinearity, containment -- rather
than asserting a recorded edge list.
"""

import unittest

from inkdrill.relate import (MAX_SYMBOLS, TooManySymbols, blocked,
                             candidates)


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


if __name__ == "__main__":
    unittest.main()
