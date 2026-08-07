"""Unit 6 tests. Every test name is quoted verbatim in the status report."""

import random
import unittest

from inkdrill.nest import InvalidConnectivity, Kind, nest
from inkdrill.raster import BG, INK, InkMask
from inkdrill.sweep import Capture, sweep

RING = ["#####",
        "#...#",
        "#...#",
        "#...#",
        "#####"]
FIGURE_8 = ["#####",
            "#...#",
            "#####",
            "#...#",
            "#####"]
LETTER_A = ["..#..",
            ".#.#.",
            "#####",
            "#...#",
            "#...#"]
LETTER_H = ["#...#",
            "#...#",
            "#####",
            "#...#",
            "#...#"]
NESTED = ["#######",
          "#.....#",
          "#.###.#",
          "#.#.#.#",
          "#.###.#",
          "#.....#",
          "#######"]
# A frame with a separate glyph floating inside it -- the \fbox case.
FBOX = ["#########",
        "#.......#",
        "#..###..#",
        "#..#.#..#",
        "#..###..#",
        "#.......#",
        "#########"]


def m(rows):
    return InkMask.from_rows(rows)


def random_mask(rng, w, h, density=0.4):
    return InkMask(bytes(INK if rng.random() < density else BG
                         for _ in range(w * h)), w, h)


def table_frame(cols, rows, cell=3):
    """A connected m x n table frame: continuous rules both ways."""
    w = cols * (cell + 1) + 1
    h = rows * (cell + 1) + 1
    grid = [["."] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            if y % (cell + 1) == 0 or x % (cell + 1) == 0:
                grid[y][x] = "#"
    return ["".join(r) for r in grid]


class T6_1_HoleCountAgreesWithU3(unittest.TestCase):
    """G1. U3 counts holes as the cycle rank of the run adjacency graph;
    this unit counts them as background components of the inverted mask.
    The two share no code, so each is the other's oracle."""

    def test_hole_counts_agree_on_the_u3_fixtures(self):
        for rows in (RING, FIGURE_8, LETTER_A, LETTER_H, NESTED, FBOX):
            with self.subTest(rows[0]):
                res = sweep(m(rows), axis="row", conn=8,
                            capture=Capture.GRAPH)
                self.assertEqual(nest(m(rows)).hole_count, res.cycle_count)

    def test_hole_counts_agree_on_random_masks(self):
        rng = random.Random(20260807)
        for trial in range(120):
            w = rng.randint(1, 16)
            h = rng.randint(1, 16)
            mask = random_mask(rng, w, h, density=rng.choice((0.3, 0.45, 0.6)))
            res = sweep(mask, axis="row", conn=8, capture=Capture.GRAPH)
            with self.subTest(trial=trial, w=w, h=h):
                self.assertEqual(nest(mask).hole_count, res.cycle_count)

    def test_hole_counts_agree_under_both_sweep_axes(self):
        rng = random.Random(4242)
        for trial in range(60):
            mask = random_mask(rng, rng.randint(2, 14), rng.randint(2, 14))
            n = nest(mask).hole_count
            with self.subTest(trial=trial):
                for axis in ("row", "col"):
                    self.assertEqual(
                        n, sweep(mask, axis=axis, conn=8,
                                 capture=Capture.GRAPH).cycle_count)

    def test_ring_has_one_hole_and_figure_eight_has_two(self):
        self.assertEqual(nest(m(RING)).hole_count, 1)
        self.assertEqual(nest(m(FIGURE_8)).hole_count, 2)

    def test_letter_h_has_no_hole(self):
        self.assertEqual(nest(m(LETTER_H)).hole_count, 0)


class T6_2_TheOutsideIsNeverAHole(unittest.TestCase):
    """G2."""

    def test_a_solid_block_has_no_hole(self):
        self.assertEqual(nest(m(["###", "###", "###"])).hole_count, 0)

    def test_an_empty_mask_has_no_hole_and_no_roots(self):
        n = nest(m(["...", "..."]))
        self.assertEqual(n.hole_count, 0)
        self.assertEqual(n.roots, [])

    def test_a_fully_inked_mask_has_no_hole(self):
        self.assertEqual(nest(m(["####", "####"])).hole_count, 0)

    def test_a_single_pixel_has_no_hole(self):
        self.assertEqual(nest(m(["#"])).hole_count, 0)

    def test_ink_touching_every_border_still_reports_no_outer_hole(self):
        rows = ["#####",
                "#...#",
                "#...#",
                "#####"]
        self.assertEqual(nest(m(rows)).hole_count, 1)

    def test_background_reaching_the_border_is_not_a_hole(self):
        # A C shape: the gap opens to the right, so it is not enclosed.
        rows = ["###",
                "#..",
                "###"]
        self.assertEqual(nest(m(rows)).hole_count, 0)


class T6_3_ContainmentForest(unittest.TestCase):

    def test_nested_frames_give_depth_zero_one_two(self):
        """The plan's own numbering: figure 0, its hole 1, the figure
        inside that hole 2."""
        n = nest(m(NESTED))
        depths = sorted(r.depth for r in n.regions.values()
                        if r.kind is not Kind.OUTSIDE)
        self.assertEqual(depths[:3], [0, 1, 2])
        outer = n.roots[0]
        self.assertEqual(n.regions[outer].depth, 0)
        hole = n.holes_of(outer)[0]
        self.assertEqual(n.regions[hole].depth, 1)
        inner = n.ink_in_hole(hole)[0]
        self.assertEqual(n.regions[inner].depth, 2)

    def test_depth_parity_holds(self):
        """G4: even is ink, odd is background. A check, not a
        convention."""
        rng = random.Random(7)
        for rows in (RING, FIGURE_8, LETTER_A, NESTED, FBOX):
            with self.subTest(rows[0]):
                self.assertTrue(nest(m(rows)).check_parity())
        for trial in range(60):
            mask = random_mask(rng, rng.randint(2, 14), rng.randint(2, 14))
            with self.subTest(trial=trial):
                self.assertTrue(nest(mask).check_parity())

    def test_the_forest_is_a_forest(self):
        """G3: one parent each, no cycles, no orphans."""
        rng = random.Random(99)
        for trial in range(80):
            mask = random_mask(rng, rng.randint(2, 15), rng.randint(2, 15))
            with self.subTest(trial=trial):
                self.assertTrue(nest(mask).check_forest())

    def test_nesting_chain_runs_outermost_to_innermost(self):
        n = nest(m(NESTED))
        outer = n.roots[0]
        hole = n.holes_of(outer)[0]
        inner = n.ink_in_hole(hole)[0]
        self.assertEqual(n.nesting_chain(inner), [outer, hole, inner])
        self.assertEqual(n.nesting_chain(outer), [outer])

    def test_every_non_outside_region_has_a_parent(self):
        rng = random.Random(3)
        for trial in range(40):
            n = nest(random_mask(rng, rng.randint(2, 12), rng.randint(2, 12)))
            with self.subTest(trial=trial):
                for r in n.regions.values():
                    if r.kind is not Kind.OUTSIDE:
                        self.assertIsNotNone(r.parent)


class T6_4_TheFourRelationsAreDistinct(unittest.TestCase):
    """G5. docs/units.md is explicit that these must not be conflated."""

    def test_fbox_yields_ink_in_hole_and_not_hole_of(self):
        """The case that forces the distinction: the glyph inside the box
        is NOT part of the frame's topology."""
        n = nest(m(FBOX))
        frame = n.roots[0]
        holes = n.holes_of(frame)
        self.assertEqual(len(holes), 1)

        inner = n.ink_in_hole(holes[0])
        self.assertEqual(len(inner), 1)

        # the glyph is ink_in_hole of the hole ...
        self.assertIn(inner[0], n.ink_in_hole(holes[0]))
        # ... and emphatically NOT a hole of the frame
        self.assertNotIn(inner[0], n.holes_of(frame))
        self.assertEqual(n.regions[inner[0]].kind, Kind.INK)

    def test_hole_of_and_ink_in_hole_are_disjoint(self):
        n = nest(m(FBOX))
        for rid in n.regions:
            holes = set(n.holes_of(rid))
            inks = set(n.ink_in_hole(rid))
            with self.subTest(rid=rid):
                self.assertEqual(holes & inks, set())

    def test_hole_of_points_back_at_the_enclosing_component(self):
        n = nest(m(FBOX))
        frame = n.roots[0]
        hole = n.holes_of(frame)[0]
        self.assertEqual(n.hole_of(hole), frame)

    def test_bbox_contains_is_weaker_than_nesting(self):
        """Two disjoint blobs where one bbox contains the other's, with
        no containment relation at all."""
        rows = ["#####",
                "#...#",
                "#.#..",
                "#....",
                "....."]
        n = nest(m(rows))
        ink = [r for r in n.regions.values() if r.kind is Kind.INK]
        self.assertEqual(len(ink), 2)
        big, small = (ink[0], ink[1]) if ink[0].area > ink[1].area \
            else (ink[1], ink[0])
        self.assertTrue(big.bbox_contains(small))       # geometry says yes
        self.assertEqual(n.holes_of(big.id), [])        # topology says no
        self.assertNotIn(small.id, n.holes_of(big.id))

    def test_hole_of_returns_none_for_an_ink_region(self):
        n = nest(m(RING))
        self.assertIsNone(n.hole_of(n.roots[0]))

    def test_ink_in_hole_returns_empty_for_an_ink_region(self):
        n = nest(m(RING))
        self.assertEqual(n.ink_in_hole(n.roots[0]), [])


class T6_5_TableFrame(unittest.TestCase):
    """G6: a connected frame's hole lattice."""

    def test_a_connected_table_frame_yields_an_m_by_n_hole_lattice(self):
        for cols, rows_ in ((2, 2), (3, 2), (4, 5), (1, 7)):
            with self.subTest(cols=cols, rows=rows_):
                n = nest(m(table_frame(cols, rows_)))
                self.assertEqual(n.hole_count, cols * rows_)

    def test_the_table_hole_count_agrees_with_u3(self):
        for cols, rows_ in ((2, 2), (3, 4)):
            rows = table_frame(cols, rows_)
            with self.subTest(cols=cols, rows=rows_):
                res = sweep(m(rows), axis="row", conn=8,
                            capture=Capture.GRAPH)
                self.assertEqual(nest(m(rows)).hole_count, res.cycle_count)

    def test_all_table_cells_are_holes_of_the_one_frame(self):
        rows = table_frame(3, 2)
        n = nest(m(rows))
        self.assertEqual(len(n.roots), 1)
        self.assertEqual(len(n.holes_of(n.roots[0])), 6)


class T6_6_Recursion(unittest.TestCase):
    """G7: holes recurse to any depth."""

    def test_a_hole_inside_ink_inside_a_hole_is_found(self):
        n = nest(m(NESTED))
        outer = n.roots[0]
        hole = n.holes_of(outer)[0]
        inner = n.ink_in_hole(hole)[0]
        self.assertEqual(len(n.holes_of(inner)), 1)
        deepest = n.holes_of(inner)[0]
        self.assertEqual(n.regions[deepest].depth, 3)
        self.assertEqual(n.nesting_chain(deepest),
                         [outer, hole, inner, deepest])

    def test_total_hole_count_includes_the_recursed_ones(self):
        """NESTED is a frame inside a frame: two holes, at depths 1
        and 3."""
        n = nest(m(NESTED))
        self.assertEqual(n.hole_count, 2)
        res = sweep(m(NESTED), axis="row", conn=8, capture=Capture.GRAPH)
        self.assertEqual(n.hole_count, res.cycle_count)


class T6_7_ConnectivityIsPaired(unittest.TestCase):

    def test_foreground_connectivity_must_be_eight(self):
        with self.assertRaises(InvalidConnectivity):
            nest(m(RING), conn=4)

    def test_a_diagonal_wall_does_not_leak(self):
        """8-connected ink implies 4-connected background. With an
        8-connected background this diagonal ring's hole would leak out
        and the count would disagree with U3."""
        rows = [".#.",
                "#.#",
                ".#."]
        res = sweep(m(rows), axis="row", conn=8, capture=Capture.GRAPH)
        self.assertEqual(nest(m(rows)).hole_count, res.cycle_count)
        self.assertEqual(nest(m(rows)).hole_count, 1)


if __name__ == "__main__":
    unittest.main()
