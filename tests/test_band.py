"""Unit 7 tests. Every test name is quoted verbatim in the status report."""

import random
import unittest

from inkdrill.aggregate import Moments, moments_of_mask, moments_per_component
from inkdrill.band import (Band, InvalidBandCount, canonical, split, stitch,
                           sweep_banded, sweep_bands)
from inkdrill.raster import BG, INK, InkMask
from inkdrill.sweep import Capture, InvalidConnectivity, sweep

# The fixture the plan asks for: a blob crossing every seam, at every K
# under test. A full-height stroke does that by construction, and the
# comb hangs structure off it so the crossings are not trivial.
# 70 rows, so K=64 -- the largest the plan names -- is a legal split.
CROSSER = (["#" + "." * 9] * 3
           + ["#" + "#" * 7 + ".."]
           + ["#" + "." * 9] * 3) * 10

RING = ["#####", "#...#", "#...#", "#...#", "#####"]
NESTED = ["#######", "#.....#", "#.###.#", "#.#.#.#",
          "#.###.#", "#.....#", "#######"]


def m(rows):
    return InkMask.from_rows(rows)


def random_mask(rng, w, h, density=0.4):
    return InkMask(bytes(INK if rng.random() < density else BG
                         for _ in range(w * h)), w, h)


def whole(mask, conn=8):
    return sweep(mask, axis="row", conn=conn, capture=Capture.GRAPH)


class T7_1_SplittingNeverSplitsARun(unittest.TestCase):
    """G1. U2's G2 says a run never spans a line boundary, and a band
    boundary IS a line boundary -- so V needs no repair at all."""

    def test_node_count_is_invariant_for_every_k(self):
        mask = m(CROSSER)
        want = whole(mask).node_count
        for k in (1, 2, 3, 7, 64):
            with self.subTest(k=k):
                self.assertEqual(sweep_banded(mask, k).node_count, want)

    def test_node_count_is_invariant_on_random_masks(self):
        rng = random.Random(20260807)
        for trial in range(40):
            mask = random_mask(rng, rng.randint(2, 20), rng.randint(4, 20))
            want = whole(mask).node_count
            for k in (2, 3, mask.height):
                with self.subTest(trial=trial, k=k):
                    self.assertEqual(sweep_banded(mask, k).node_count, want)

    def test_bands_tile_the_mask_exactly(self):
        mask = m(CROSSER)
        for k in (1, 2, 3, 7, 63):
            with self.subTest(k=k):
                parts = split(mask, k)
                self.assertEqual(sum(b.height for _, b in parts),
                                 mask.height)
                self.assertEqual([y for y, _ in parts],
                                 sorted(y for y, _ in parts))
                joined = b"".join(b.data for _, b in parts)
                self.assertEqual(joined, mask.data)

    def test_band_heights_differ_by_at_most_one(self):
        mask = m(CROSSER)
        for k in (2, 3, 7, 11):
            heights = [b.height for _, b in split(mask, k)]
            with self.subTest(k=k):
                self.assertLessEqual(max(heights) - min(heights), 1)

    def test_bad_band_count_is_refused(self):
        mask = m(RING)
        for k in (0, -1, mask.height + 1):
            with self.subTest(k=k):
                with self.assertRaises(InvalidBandCount):
                    split(mask, k)


class T7_2_IndistinguishableFromASingleSweep(unittest.TestCase):
    """G2, the whole contract."""

    def test_output_is_identical_to_k_equals_one_for_every_k(self):
        """The plan's own fixture list: K in {1,2,3,7,64} on a mask with
        a blob crossing every seam."""
        mask = m(CROSSER)
        want = canonical(whole(mask))
        for k in (1, 2, 3, 7, 64):
            with self.subTest(k=k):
                self.assertEqual(canonical(sweep_banded(mask, k)), want)

    def test_output_is_identical_on_the_topology_fixtures(self):
        for rows in (RING, NESTED):
            mask = m(rows)
            want = canonical(whole(mask))
            for k in (2, 3, mask.height):
                with self.subTest(rows[0], k=k):
                    self.assertEqual(canonical(sweep_banded(mask, k)), want)

    def test_output_is_identical_on_random_masks_at_every_k(self):
        rng = random.Random(4242)
        for trial in range(60):
            w = rng.randint(2, 18)
            h = rng.randint(4, 18)
            mask = random_mask(rng, w, h, density=rng.choice((0.3, 0.5)))
            want = canonical(whole(mask))
            for k in (2, 3, 5, h):
                if k > h:
                    continue
                with self.subTest(trial=trial, k=k, w=w, h=h):
                    self.assertEqual(canonical(sweep_banded(mask, k)), want)

    def test_identical_at_connectivity_four_as_well(self):
        rng = random.Random(77)
        for trial in range(30):
            mask = random_mask(rng, rng.randint(2, 14), rng.randint(4, 14))
            want = canonical(whole(mask, conn=4))
            for k in (2, 3, mask.height):
                with self.subTest(trial=trial, k=k):
                    self.assertEqual(
                        canonical(sweep_banded(mask, k, conn=4)), want)

    def test_a_blob_crossing_every_seam_stays_one_component(self):
        """A full-height stroke must never be cut into pieces."""
        mask = m(["#" + "." * 5] * 40)
        for k in (2, 3, 7, 40):
            with self.subTest(k=k):
                res = sweep_banded(mask, k)
                self.assertEqual(res.component_count, 1)
                self.assertEqual(res.node_count, 40)

    def test_bad_connectivity_is_refused(self):
        with self.assertRaises(InvalidConnectivity):
            stitch(sweep_bands(m(RING), 2), conn=6)


class T7_3_OrderIndependence(unittest.TestCase):
    """G3 and G7 -- the latent bug this unit exists to avoid. A stitcher
    that merely concatenated would pass every in-order test above and
    fail here, which is exactly how it would reach production."""

    def test_runs_come_out_sorted_whatever_order_the_bands_arrive_in(self):
        mask = m(CROSSER)
        rng = random.Random(9)
        for k in (2, 3, 7, 64):
            bands = sweep_bands(mask, k)
            for shuffle in range(4):
                shuffled = bands[:]
                rng.shuffle(shuffled)
                res = stitch(shuffled)
                with self.subTest(k=k, shuffle=shuffle):
                    keys = [(n.line, n.lo) for n in res.nodes]
                    self.assertEqual(keys, sorted(keys))

    def test_node_ids_follow_scan_order(self):
        """U3's G5: nodes in scan order. Banding must not break it."""
        res = sweep_banded(m(CROSSER), 7)
        for i, n in enumerate(res.nodes):
            self.assertEqual(n.id, i)

    def test_shuffling_the_bands_changes_nothing(self):
        mask = m(CROSSER)
        rng = random.Random(31)
        for k in (2, 3, 7, 64):
            bands = sweep_bands(mask, k)
            want = canonical(stitch(bands))
            for shuffle in range(4):
                shuffled = bands[:]
                rng.shuffle(shuffled)
                with self.subTest(k=k, shuffle=shuffle):
                    self.assertEqual(canonical(stitch(shuffled)), want)

    def test_reversed_band_order_matches_the_unbanded_sweep(self):
        mask = m(CROSSER)
        want = canonical(whole(mask))
        for k in (2, 3, 7):
            with self.subTest(k=k):
                self.assertEqual(
                    canonical(stitch(list(reversed(sweep_bands(mask, k))))),
                    want)

    def test_nodes_unsorted_WITHIN_a_band_are_still_sorted_on_output(self):
        """Sorting the band LIST is not enough. U8 may append a band's
        own nodes in completion order too, so the global re-sort must be
        reachable and not merely defensive -- without this test, deleting
        the re-sort passes the whole suite."""
        mask = m(CROSSER)
        rng = random.Random(1234)
        want = canonical(whole(mask))
        for k in (2, 3, 7):
            bands = sweep_bands(mask, k)
            for b in bands:
                rng.shuffle(b.result.nodes)
            with self.subTest(k=k):
                res = stitch(bands)
                keys = [(n.line, n.lo) for n in res.nodes]
                self.assertEqual(keys, sorted(keys))
                self.assertEqual([n.id for n in res.nodes],
                                 list(range(len(res.nodes))))
                self.assertEqual(canonical(res), want)

    def test_stitching_no_bands_gives_an_empty_result(self):
        res = stitch([])
        self.assertEqual(res.node_count, 0)
        self.assertEqual(res.component_count, 0)


class T7_4_CycleRankSurvivesStitching(unittest.TestCase):
    """G4."""

    def test_the_identity_holds_after_stitching(self):
        mask = m(CROSSER)
        for k in (1, 2, 3, 7, 64):
            with self.subTest(k=k):
                self.assertTrue(sweep_banded(mask, k).check_cycle_rank())

    def test_the_identity_holds_on_random_masks(self):
        rng = random.Random(555)
        for trial in range(60):
            mask = random_mask(rng, rng.randint(2, 16), rng.randint(4, 16))
            for k in (2, 3, mask.height):
                with self.subTest(trial=trial, k=k):
                    self.assertTrue(sweep_banded(mask, k).check_cycle_rank())

    def test_holes_survive_a_seam_cut_straight_through_them(self):
        """A ring split exactly at its middle row: the hole is created by
        seam edges alone, and must still be counted once."""
        mask = m(RING)
        want = whole(mask).cycle_count
        self.assertEqual(want, 1)
        for k in (2, 3, 5):
            with self.subTest(k=k):
                self.assertEqual(sweep_banded(mask, k).cycle_count, want)

    def test_nested_frames_keep_both_holes_under_banding(self):
        mask = m(NESTED)
        for k in (2, 3, 7):
            with self.subTest(k=k):
                self.assertEqual(sweep_banded(mask, k).cycle_count, 2)

    def test_per_component_cycle_counts_match_the_unbanded_sweep(self):
        rng = random.Random(818)
        for trial in range(40):
            mask = random_mask(rng, rng.randint(3, 15), rng.randint(4, 15))
            want = sorted(c.cycle_count for c in whole(mask).components)
            for k in (2, 3, mask.height):
                with self.subTest(trial=trial, k=k):
                    self.assertEqual(
                        sorted(c.cycle_count
                               for c in sweep_banded(mask, k).components),
                        want)


class T7_5_MomentsAddAcrossBands(unittest.TestCase):
    """G5, using U5's algebra."""

    def test_band_moments_sum_to_the_whole_mask(self):
        rng = random.Random(1010)
        for trial in range(30):
            w = rng.randint(3, 16)
            h = rng.randint(4, 16)
            mask = random_mask(rng, w, h)
            total = moments_of_mask(mask)
            for k in (2, 3, h):
                acc = Moments(0, 0, 0, 0, 0, 0, 0, 0, -1, -1)
                for y0, sub in split(mask, k):
                    acc = acc + moments_of_mask(sub).translated(0, y0)
                with self.subTest(trial=trial, k=k):
                    self.assertEqual(
                        (acc.area, acc.sx, acc.sy, acc.sxx, acc.syy, acc.sxy),
                        (total.area, total.sx, total.sy,
                         total.sxx, total.syy, total.sxy))

    def test_per_component_moments_survive_stitching(self):
        rng = random.Random(2020)
        for trial in range(30):
            mask = random_mask(rng, rng.randint(3, 14), rng.randint(4, 14))
            raw = lambda mo: (mo.area, mo.sx, mo.sy, mo.sxx, mo.syy, mo.sxy)
            want = sorted(raw(x)
                          for x in moments_per_component(whole(mask)).values())
            for k in (2, 3, mask.height):
                with self.subTest(trial=trial, k=k):
                    got = sorted(raw(x) for x in moments_per_component(
                        sweep_banded(mask, k)).values())
                    self.assertEqual(got, want)


class T7_6_SeamAdjacencyUsesTheU3Predicate(unittest.TestCase):
    """G6: nothing crossing a seam is treated specially."""

    def test_a_diagonal_touch_across_a_seam_joins_at_conn_eight(self):
        mask = m(["#.", ".#"])
        self.assertEqual(sweep_banded(mask, 2, conn=8).component_count, 1)

    def test_a_diagonal_touch_across_a_seam_separates_at_conn_four(self):
        mask = m(["#.", ".#"])
        self.assertEqual(sweep_banded(mask, 2, conn=4).component_count, 2)

    def test_a_blank_seam_line_joins_nothing(self):
        mask = m(["##", "..", "##"])
        for k in (2, 3):
            with self.subTest(k=k):
                self.assertEqual(sweep_banded(mask, k).component_count, 2)

    def test_edge_count_matches_the_unbanded_sweep(self):
        rng = random.Random(6161)
        for trial in range(40):
            mask = random_mask(rng, rng.randint(3, 15), rng.randint(4, 15))
            want = whole(mask).edge_count
            for k in (2, 3, mask.height):
                with self.subTest(trial=trial, k=k):
                    self.assertEqual(sweep_banded(mask, k).edge_count, want)


class T7_7_StatedNonGuarantees(unittest.TestCase):

    def test_events_are_not_stitched_and_the_list_is_empty(self):
        """A band boundary manufactures spurious births and closes.
        Returning an empty list is honest; returning events that look
        right and are not would be worse than useless."""
        res = sweep_banded(m(CROSSER), 7)
        self.assertEqual(res.events, [])
        self.assertEqual(res.capture, Capture.GRAPH)


if __name__ == "__main__":
    unittest.main()
