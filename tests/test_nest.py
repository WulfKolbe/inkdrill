"""Unit 6 tests. Every test name is quoted verbatim in the status report."""

import random
import unittest

from inkdrill.nest import (InvalidConnectivity, Kind, _label,  # noqa: F401
                           ink_only, nest)
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


class T6_8_TwoSweepsEqualTheFloodFill(unittest.TestCase):
    """`nest` labels via two sweeps; `_label` is the flood fill it
    replaced, kept as the REFERENCE ORACLE and exercised only here.

    This is the project's usual shape -- a second independent
    computation rather than a golden file -- and it is what licenses
    the replacement. The two share no code: one walks pixels with a
    stack, the other unions runs.

    The equality asserted is not "the same holes" but the WHOLE
    structure, ids included. Ids are assigned in raster order of each
    region's first pixel precisely so this can be an equality rather
    than an isomorphism, because `Nesting.roots` is ordered by id and a
    caller can key on it.
    """

    @staticmethod
    def _flood(mask):
        """The old implementation's body, over `_label`."""
        w, h = mask.width + 2, mask.height + 2
        buf = bytearray(w * h)
        for y in range(mask.height):
            src = y * mask.width
            buf[(y + 1) * w + 1:(y + 1) * w + 1 + mask.width] = \
                mask.data[src:src + mask.width]
        padded = InkMask(bytes(buf), w, h)
        fg, n_fg = _label(padded, True, 8)
        bg, _ = _label(padded, False, 4)
        box, area, top = {}, {}, {}
        for p in range(w * h):
            f, b = fg[p], bg[p]
            rid = f if f != -1 else n_fg + b
            x, y = p % w - 1, p // w - 1
            if rid not in box:
                box[rid] = [x, y, x, y]
                top[rid] = p
                area[rid] = 0
            else:
                bb = box[rid]
                bb[0] = min(bb[0], x)
                bb[1] = min(bb[1], y)
                bb[2] = max(bb[2], x)
                bb[3] = max(bb[3], y)
            area[rid] += 1
        outside = n_fg + bg[0]
        parent = {}
        for rid in box:
            if rid == outside:
                continue
            up = top[rid] - w
            f, b = fg[up], bg[up]
            parent[rid] = f if f != -1 else n_fg + b
        return outside, box, area, parent

    @staticmethod
    def _dump(n):
        return (n.outside, sorted(n.roots),
                sorted((r.id, r.kind.value, r.area,
                        r.x0, r.y0, r.x1, r.y1, r.parent)
                       for r in n.regions.values()))

    def _compare(self, mask):
        outside, box, area, parent = self._flood(mask)
        want = sorted((rid, area[rid], *box[rid], parent.get(rid))
                      for rid in box)
        got = sorted((r.id, r.area, r.x0, r.y0, r.x1, r.y1, r.parent)
                     for r in nest(mask).regions.values())
        self.assertEqual(got, want)
        n = nest(mask)
        self.assertEqual(n.outside, outside)
        self.assertEqual(sorted(n.roots),
                         sorted(r for r, pa in parent.items() if pa == outside))

    def test_the_two_agree_on_random_masks(self):
        rng = random.Random(20260813)
        for _ in range(60):
            w, h = rng.randint(3, 26), rng.randint(3, 26)
            data = bytes(INK if rng.random() < rng.choice((0.2, 0.45, 0.7))
                         else BG for _ in range(w * h))
            self._compare(InkMask(data, w, h))

    def test_the_two_agree_on_a_nested_frame(self):
        """A structured case, not only noise: a box inside a box with
        ink in the innermost hole exercises depth and the `fbox`
        relation, which random masks reach only by luck."""
        w = h = 30
        buf = bytearray(w * h)
        for x in range(2, 28):
            buf[2 * w + x] = INK
            buf[27 * w + x] = INK
        for y in range(2, 28):
            buf[y * w + 2] = INK
            buf[y * w + 27] = INK
        for x in range(8, 22):
            buf[8 * w + x] = INK
            buf[21 * w + x] = INK
        for y in range(8, 22):
            buf[y * w + 8] = INK
            buf[y * w + 21] = INK
        buf[15 * w + 15] = INK
        self._compare(InkMask(bytes(buf), w, h))

    def test_an_all_ink_and_an_all_background_mask_agree(self):
        """The degenerate ends, where the outside region is the only
        one or the ink is one blob touching every edge."""
        for fill in (INK, BG):
            self._compare(InkMask(bytes([fill]) * (12 * 9), 12, 9))


class T6_9_InkPassIsTheSameIdSpace(unittest.TestCase):
    """T4: the ink half alone, with the background sweep deferred.

    The saving is only safe because the ids are IDENTICAL. Emitting
    `region_id` from two different spaces depending on what happened to
    be on the page is the trap this package has paid for twice, so the
    equality is asserted rather than argued.
    """

    @staticmethod
    def _page():
        """Letters, a framed box with a hole, and a rule -- so ink
        regions differ in every way the two paths could disagree on."""
        w, h = 120, 90
        buf = bytearray(w * h)
        for i in range(4):                       # hollow rings
            ox = 4 + i * 14
            for x in range(ox, ox + 9):
                buf[10 * w + x] = INK
                buf[24 * w + x] = INK
            for y in range(10, 25):
                buf[y * w + ox] = INK
                buf[y * w + ox + 8] = INK
        for x in range(70, 115):                 # a frame
            buf[40 * w + x] = INK
            buf[80 * w + x] = INK
        for y in range(40, 81):
            buf[y * w + 70] = INK
            buf[y * w + 114] = INK
        buf[60 * w + 90] = INK                   # loose ink inside it
        for x in range(5, 60):                   # a rule
            buf[85 * w + x] = INK
        return InkMask(bytes(buf), w, h)

    def test_ids_boxes_and_areas_match_nest_exactly(self):
        m = self._page()
        got = sorted((r.id, r.area, r.x0, r.y0, r.x1, r.y1)
                     for r in ink_only(m).regions)
        want = sorted((r.id, r.area, r.x0, r.y0, r.x1, r.y1)
                      for r in nest(m).regions.values() if r.kind is Kind.INK)
        self.assertEqual(got, want)

    def test_the_cycle_rank_IS_the_hole_count(self):
        """What lets the cheap path report holes at all. Asserted with a
        fixture that has both holed and hole-free components, so a
        constant zero or a constant one would fail."""
        m = self._page()
        n = nest(m)
        pairs = ink_only(m).pairs()
        self.assertEqual([c for _, c in pairs],
                         [len(n.holes_of(r.id)) for r, _ in pairs])
        self.assertEqual(sorted({c for _, c in pairs}), [0, 1])

    def test_complete_equals_a_fresh_nest(self):
        """`complete()` reuses the ink sweep. If the reuse were wrong
        the forest would differ, so the whole structure is compared."""
        m = self._page()
        a, b = ink_only(m).complete(), nest(m)
        self.assertEqual(a.outside, b.outside)
        self.assertEqual(sorted(a.roots), sorted(b.roots))
        self.assertEqual(
            sorted((r.id, r.kind.value, r.depth, r.area, r.parent,
                    tuple(r.children)) for r in a.regions.values()),
            sorted((r.id, r.kind.value, r.depth, r.area, r.parent,
                    tuple(r.children)) for r in b.regions.values()))

    def test_the_forest_fields_are_NOT_filled_in(self):
        """Stated in the contract, so asserted: there is no forest
        without the background sweep, and a caller must not read one."""
        for r in ink_only(self._page()).regions:
            self.assertIsNone(r.parent)
            self.assertEqual(r.children, [])
            self.assertEqual(r.depth, -1)

    def test_complete_does_ONE_further_sweep_not_two(self):
        """The reuse itself, asserted by counting.

        `complete()` returning `_build(padded, None)` is behaviourally
        EQUIVALENT -- it recomputes the ink sweep and gets the same
        answer -- so no output test can catch it. That is the signature
        of an optimisation: the only killable mutant is the one that
        skips work it needed. The mechanism therefore has to be
        measured rather than inferred.
        """
        import unittest.mock as mock
        import inkdrill.nest as N
        m = self._page()
        ik = ink_only(m)
        with mock.patch.object(N, "sweep", wraps=N.sweep) as spy:
            ik.complete()
        self.assertEqual(spy.call_count, 1, "the ink sweep was repeated")

    def test_connectivity_is_refused_and_accepted(self):
        m = self._page()
        with self.assertRaises(InvalidConnectivity):
            ink_only(m, conn=4)
        self.assertTrue(ink_only(m, conn=8).regions)


if __name__ == "__main__":
    unittest.main()
