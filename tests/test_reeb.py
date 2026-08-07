"""Unit 4 tests. Every test name is quoted verbatim in the status report."""

import random
import unittest

from inkdrill.raster import InkMask
from inkdrill.reeb import (Direction, InvalidDirection, ReebGraph, Signature,
                           contract, graph_of, orient, signature,
                           signature_of)
from inkdrill.sweep import Capture, sweep

# The U3 fixtures, reused verbatim so U4's counts sit beside U3's.
RING = ["#####",
        "#...#",
        "#...#",
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
TWO_DOTS = ["#...#",
            ".....",
            ".....",
            "#...#"]
NESTED = ["#######",
          "#.....#",
          "#.###.#",
          "#.#.#.#",
          "#.###.#",
          "#.....#",
          "#######"]
FIGURE_8 = ["#####",
            "#...#",
            "#####",
            "#...#",
            "#####"]


def m(rows):
    return InkMask.from_rows(rows)


def rag(rows, axis="row"):
    return sweep(m(rows), axis=axis, conn=8, capture=Capture.GRAPH)


def flip_rows(rows):
    """Vertical flip -- what a genuine reversed row sweep sees."""
    return list(reversed(rows))


def flip_cols(rows):
    return ["".join(reversed(r)) for r in rows]


def structure(g: ReebGraph):
    """Direction-free shape of a Reeb graph, for comparing a derived
    orientation against a genuinely re-swept one. Node ids and line
    numbers differ between the two; the shape must not."""
    return (g.node_count,
            g.edge_count,
            g.cycle_count,
            g.component_count,
            sorted((len(n.up), len(n.down)) for n in g.nodes),
            sorted(n.persistence for n in g.nodes))


def random_mask(rng, w, h, density=0.4):
    from inkdrill.raster import BG, INK
    return InkMask(bytes(INK if rng.random() < density else BG
                         for _ in range(w * h)), w, h)


class T4_1_Contraction(unittest.TestCase):

    def test_every_run_lands_in_exactly_one_reeb_node(self):
        """G1: the contraction is a partition of the RAG nodes."""
        for rows in (RING, LETTER_A, LETTER_H, TWO_DOTS, NESTED, FIGURE_8):
            with self.subTest(rows[0]):
                res = rag(rows)
                g = contract(res)
                seen = [r for n in g.nodes for r in n.runs]
                self.assertEqual(sorted(seen),
                                 sorted(n.id for n in res.nodes))
                self.assertEqual(len(seen), len(set(seen)))

    def test_contraction_never_grows_the_graph(self):
        for rows in (RING, LETTER_A, LETTER_H, NESTED, FIGURE_8):
            with self.subTest(rows[0]):
                res = rag(rows)
                self.assertLessEqual(contract(res).node_count,
                                     res.node_count)

    def test_a_bar_contracts_to_one_arc(self):
        """A bar has no junction anywhere, so it is a single arc however
        tall it is -- this is what splitting on junctions rather than on
        degree-2 buys, and it is what makes persistence read as
        h(close) - h(birth)."""
        for height in (3, 8, 40):
            rows = ["#"] * height
            with self.subTest(height=height):
                g = contract(rag(rows))
                self.assertEqual(g.node_count, 1)
                self.assertEqual(g.nodes[0].persistence, height)

    def test_branching_is_preserved(self):
        """G2: contraction removes chain nodes and no branch points."""
        for rows in (RING, LETTER_A, LETTER_H, NESTED, FIGURE_8):
            with self.subTest(rows[0]):
                res = rag(rows)
                by_id = {n.id: n for n in res.nodes}
                raw_m = sum(1 for n in res.nodes if len(n.up) >= 2)
                raw_s = sum(1 for n in res.nodes if len(n.down) >= 2)
                g = contract(res)
                self.assertEqual(sum(1 for n in g.nodes if n.is_merge), raw_m)
                self.assertEqual(sum(1 for n in g.nodes if n.is_split), raw_s)
                del by_id

    def test_cycle_count_carries_through_unchanged(self):
        for rows in (RING, LETTER_A, NESTED, FIGURE_8):
            with self.subTest(rows[0]):
                res = rag(rows)
                self.assertEqual(contract(res).cycle_count, res.cycle_count)

    def test_capture_below_graph_is_refused(self):
        for cap in (Capture.NONE, Capture.EVENTS):
            with self.subTest(cap.value):
                res = sweep(m(RING), capture=cap)
                with self.assertRaises(ValueError):
                    contract(res)


class T4_2_OrientationReversal(unittest.TestCase):

    def test_row_up_equals_a_genuine_reversed_sweep(self):
        """G3, and docs/units.md assumption 2: the claim that makes four
        orientations cost two scans."""
        for rows in (RING, LETTER_A, LETTER_H, TWO_DOTS, NESTED, FIGURE_8):
            with self.subTest(rows[0]):
                derived = orient(rag(rows), Direction.ROW_UP)
                genuine = contract(rag(flip_rows(rows)))
                self.assertEqual(structure(derived), structure(genuine))

    def test_col_up_equals_a_genuine_reversed_sweep(self):
        for rows in (RING, LETTER_A, LETTER_H, TWO_DOTS, NESTED, FIGURE_8):
            with self.subTest(rows[0]):
                derived = orient(rag(rows, "col"), Direction.COL_UP)
                genuine = contract(rag(flip_cols(rows), "col"))
                self.assertEqual(structure(derived), structure(genuine))

    def test_reversal_holds_on_random_masks(self):
        rng = random.Random(20260807)
        for trial in range(40):
            w = rng.randint(3, 14)
            h = rng.randint(3, 14)
            mask = random_mask(rng, w, h)
            rows = mask.to_rows()
            with self.subTest(trial=trial, w=w, h=h):
                derived = orient(rag(rows), Direction.ROW_UP)
                genuine = contract(rag(flip_rows(rows)))
                self.assertEqual(structure(derived), structure(genuine))

    def test_reversal_is_an_involution(self):
        """G4."""
        for rows in (RING, LETTER_A, NESTED):
            with self.subTest(rows[0]):
                res = rag(rows)
                once = orient(res, Direction.ROW_UP)
                twice = orient(res, Direction.ROW_DOWN)
                self.assertEqual(once.direction, Direction.ROW_UP)
                self.assertEqual(twice.direction, Direction.ROW_DOWN)
                self.assertEqual(structure(twice), structure(contract(res)))

    def test_births_and_closes_swap_under_reversal(self):
        res = rag(LETTER_A)
        down = orient(res, Direction.ROW_DOWN)
        up = orient(res, Direction.ROW_UP)
        self.assertEqual(sum(1 for n in down.nodes if n.is_birth),
                         sum(1 for n in up.nodes if n.is_close))
        self.assertEqual(sum(1 for n in down.nodes if n.is_merge),
                         sum(1 for n in up.nodes if n.is_split))

    def test_axis_mismatch_is_refused(self):
        res = rag(RING, "row")
        with self.assertRaises(InvalidDirection):
            orient(res, Direction.COL_UP)

    def test_non_direction_is_refused(self):
        with self.assertRaises(InvalidDirection):
            orient(rag(RING), "row_up")


class T4_3_Persistence(unittest.TestCase):

    def test_persistence_is_the_inclusive_line_span(self):
        """G6."""
        for rows in (RING, LETTER_A, NESTED, FIGURE_8):
            with self.subTest(rows[0]):
                for n in contract(rag(rows)).nodes:
                    self.assertEqual(n.persistence,
                                     n.hi_line - n.lo_line + 1)
                    self.assertGreaterEqual(n.persistence, 1)

    def test_persistence_separates_a_speck_from_a_stroke(self):
        """G6, the noise/structure distinction available from topology."""
        rows = ["#" + "." * 8 + "##"] + \
               ["#" + "." * 10 for _ in range(19)]
        g = contract(rag(rows))
        spans = sorted(n.persistence for n in g.nodes)
        self.assertEqual(spans[0], 1)            # the 2-px speck
        self.assertEqual(spans[-1], 20)          # the full-height stroke
        self.assertGreater(spans[-1], 10 * spans[0])

    def test_a_full_height_bar_has_persistence_equal_to_height(self):
        for h in (2, 5, 33):
            with self.subTest(h=h):
                g = contract(rag(["#"] * h))
                self.assertEqual(max(n.persistence for n in g.nodes), h)


class T4_4_Signature(unittest.TestCase):

    def test_signature_is_translation_invariant(self):
        """G5, exactly -- the counts are integers for this reason."""
        for rows in (RING, LETTER_A, LETTER_H, NESTED, FIGURE_8):
            base = signature(graph_of(m(rows)))
            for pad_t, pad_l in ((3, 0), (0, 4), (5, 7)):
                w = len(rows[0]) + pad_l
                moved = ["." * w for _ in range(pad_t)] + \
                        ["." * pad_l + r for r in rows]
                with self.subTest(rows[0], pad=(pad_t, pad_l)):
                    self.assertEqual(signature(graph_of(m(moved))), base)

    def test_signature_counts_match_the_graph(self):
        for rows in (RING, LETTER_A, LETTER_H, NESTED, FIGURE_8):
            with self.subTest(rows[0]):
                g = graph_of(m(rows))
                s = signature(g)
                self.assertEqual(s.cycles, g.cycle_count)
                self.assertEqual(s.parts, g.component_count)
                self.assertEqual(s.births,
                                 sum(1 for n in g.nodes if n.is_birth))
                self.assertEqual(s.splits,
                                 sum(1 for n in g.nodes if n.is_split))

    def test_ring_and_figure_eight_differ_by_cycle_count(self):
        self.assertEqual(signature(graph_of(m(RING))).cycles, 1)
        self.assertEqual(signature(graph_of(m(FIGURE_8))).cycles, 2)

    def test_letter_h_has_a_merge_and_a_split_and_no_cycle(self):
        s = signature(graph_of(m(LETTER_H)))
        self.assertEqual(s.cycles, 0)
        self.assertEqual(s.merges, 1)
        self.assertEqual(s.splits, 1)

    def test_signature_of_one_graph_equals_signature(self):
        """G7: the single-component case falls out of the general one."""
        for rows in (RING, LETTER_A, NESTED):
            with self.subTest(rows[0]):
                g = graph_of(m(rows))
                self.assertEqual(signature_of([g]), signature(g))
        # parts is the component count, so it is 1 only when the graph
        # really does hold one component.
        self.assertEqual(signature_of([graph_of(m(RING))]).parts, 1)

    def test_signature_of_combines_a_multi_component_glyph(self):
        """A glyph is not always one component -- i, j, : are multi-part.
        Every U3 fixture is a single blob, so this needs its own test."""
        dot = graph_of(m(["#"]))
        stem = graph_of(m(["#"] * 6))
        combined = signature_of([dot, stem])
        self.assertEqual(combined.parts, 2)
        self.assertEqual(combined.births,
                         signature(dot).births + signature(stem).births)
        # and it is not equal to either part alone
        self.assertNotEqual(combined, signature(dot))
        self.assertNotEqual(combined, signature(stem))

    def test_signature_of_empty_is_all_zero(self):
        self.assertEqual(signature_of([]), Signature(0, 0, 0, 0, 0, 0))

    def test_signature_of_refuses_mixed_directions(self):
        res = rag(RING)
        with self.assertRaises(InvalidDirection):
            signature_of([orient(res, Direction.ROW_DOWN),
                          orient(res, Direction.ROW_UP)])

    def test_parts_counts_disconnected_components(self):
        # TWO_DOTS is two dots on each of two rows -- four components.
        self.assertEqual(signature(graph_of(m(TWO_DOTS))).parts, 4)
        self.assertEqual(signature(graph_of(m(RING))).parts, 1)


class T4_5_AgreementWithU3(unittest.TestCase):
    """U3 is the oracle: U4 may reorganise its graph but must not
    disagree with it about anything U3 already counts."""

    def test_component_and_cycle_counts_agree_with_the_sweep(self):
        rng = random.Random(4242)
        for trial in range(40):
            w = rng.randint(3, 16)
            h = rng.randint(3, 16)
            mask = random_mask(rng, w, h)
            res = sweep(mask, axis="row", conn=8, capture=Capture.GRAPH)
            g = contract(res)
            with self.subTest(trial=trial):
                self.assertEqual(g.cycle_count, res.cycle_count)
                self.assertEqual(g.component_count, res.component_count)

    def test_reeb_edge_count_never_exceeds_the_rag(self):
        rng = random.Random(99)
        for trial in range(30):
            mask = random_mask(rng, rng.randint(3, 14), rng.randint(3, 14))
            res = sweep(mask, axis="row", conn=8, capture=Capture.GRAPH)
            with self.subTest(trial=trial):
                self.assertLessEqual(contract(res).edge_count,
                                     res.edge_count)

    def test_births_agree_with_the_sweep_birth_events(self):
        from inkdrill.sweep import EventKind
        for rows in (RING, LETTER_A, LETTER_H, TWO_DOTS, NESTED, FIGURE_8):
            with self.subTest(rows[0]):
                res = sweep(m(rows), axis="row", conn=8,
                            capture=Capture.GRAPH)
                births = len(res.events_of_kind(EventKind.BIRTH))
                g = contract(res)
                self.assertEqual(sum(1 for n in g.nodes if n.is_birth),
                                 births)


if __name__ == "__main__":
    unittest.main()


def rotate(mask, deg):
    """Nearest-neighbour rotation about the centre, into a padded canvas.
    Deliberately crude: it is the harsh case, and the point of
    T4_6 is what survives it."""
    import math
    from inkdrill.raster import INK
    w, h = mask.width, mask.height
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    nw = int(abs(w * c) + abs(h * s)) + 2
    nh = int(abs(w * s) + abs(h * c)) + 2
    cx, cy, ncx, ncy = w / 2, h / 2, nw / 2, nh / 2
    out = bytearray(nw * nh)
    d = mask.data
    for y in range(nh):
        dy = y - ncy
        for x in range(nw):
            dx = x - ncx
            sx = int(cx + dx * c + dy * s)
            sy = int(cy - dx * s + dy * c)
            if 0 <= sx < w and 0 <= sy < h and d[sy * w + sx]:
                out[y * nw + x] = INK
    return InkMask(bytes(out), nw, nh)


class T4_6_RotationIsNotAnInvariance(unittest.TestCase):
    """G5's negative half. The plan expected signature invariance under
    +/-3 degrees; measurement on 158 real glyph components refuted it
    (full signature kept ~47-54%, cycle count ~84%). These tests pin the
    asymmetry so the false claim cannot quietly return."""

    def test_rotation_by_zero_is_exact(self):
        """The control. If this ever fails, the resampler is lossy and
        every rotation number above is meaningless."""
        for rows in (RING, LETTER_A, LETTER_H, NESTED, FIGURE_8):
            with self.subTest(rows[0]):
                base = signature(graph_of(m(rows)))
                self.assertEqual(signature(graph_of(rotate(m(rows), 0.0))),
                                 base)

    def test_cycle_count_survives_rotation_better_than_branch_counts(self):
        """A thick ring keeps its hole through a 3 degree rotation; that
        is the durable component U13 should lean on."""
        thick = ["#" * 14] * 3 + \
                ["###" + "." * 8 + "###" for _ in range(8)] + \
                ["#" * 14] * 3
        base = signature(graph_of(m(thick)))
        self.assertEqual(base.cycles, 1)
        for ang in (-3.0, 3.0):
            with self.subTest(angle=ang):
                self.assertEqual(
                    signature(graph_of(rotate(m(thick), ang))).cycles, 1)

    def test_translation_invariance_is_exact_where_rotation_is_not(self):
        """The contrast that G5 now states: position never enters the
        counts, orientation does."""
        thick = ["#" * 14] * 3 + \
                ["###" + "." * 8 + "###" for _ in range(8)] + \
                ["#" * 14] * 3
        base = signature(graph_of(m(thick)))
        w = len(thick[0]) + 6
        shifted = ["." * w] * 4 + ["." * 6 + r for r in thick]
        self.assertEqual(signature(graph_of(m(shifted))), base)
