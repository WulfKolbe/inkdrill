"""Unit 3 tests. Every test name is quoted verbatim in the status report."""

import random
import unittest

from inkdrill.raster import InkMask, InvalidAxis
from inkdrill.sweep import (Capture, EventKind, InvalidConnectivity,
                            SweepResult, sweep)

# --------------------------------------------------------------------------
# Hand-checked fixtures. Each is annotated with the topology it must yield.
# --------------------------------------------------------------------------

RING = [                       # one component, one hole
    ".###.",
    "#...#",
    "#...#",
    "#...#",
    ".###.",
]

FIGURE_8 = [                   # one component, two holes
    ".###.",
    "#...#",
    "#...#",
    ".###.",
    "#...#",
    "#...#",
    ".###.",
]

LETTER_A = [                   # one component, one hole, one fork
    "..###..",
    ".#...#.",
    "#.....#",
    "#######",
    "#.....#",
    "#.....#",
]

LETTER_H = [                   # one component, no hole; merge then split
    "#.....#",
    "#.....#",
    "#######",
    "#.....#",
    "#.....#",
]

TWO_DOTS = [                   # two components, no holes
    "#...#",
    "#...#",
]

DIAGONAL = [                   # 8-conn: one component; 4-conn: three
    "#..",
    ".#.",
    "..#",
]

NESTED = [                     # frame inside a frame: 2 components, 1 hole each
    "#######",
    "#.....#",
    "#.###.#",
    "#.#.#.#",
    "#.###.#",
    "#.....#",
    "#######",
]


def m(rows):
    return InkMask.from_rows(rows)


def random_mask(rng, w, h, density=0.4):
    return InkMask.from_rows(
        ["".join("#" if rng.random() < density else "." for _ in range(w))
         for _ in range(h)])


def brute_components(mask, conn):
    """Reference flood fill -- deliberately a different algorithm from the
    one under test, so agreement is evidence rather than tautology."""
    if conn == 8:
        nbr = [(-1, -1), (0, -1), (1, -1), (-1, 0),
               (1, 0), (-1, 1), (0, 1), (1, 1)]
    else:
        nbr = [(0, -1), (-1, 0), (1, 0), (0, 1)]
    seen = set()
    comps = []
    for y in range(mask.height):
        for x in range(mask.width):
            if not mask.at(x, y) or (x, y) in seen:
                continue
            stack, group = [(x, y)], set()
            seen.add((x, y))
            while stack:
                cx, cy = stack.pop()
                group.add((cx, cy))
                for dx, dy in nbr:
                    q = (cx + dx, cy + dy)
                    if q not in seen and mask.at(*q):
                        seen.add(q)
                        stack.append(q)
            comps.append(group)
    return comps


def comp_pixels(res: SweepResult, comp):
    out = set()
    for nid in comp.nodes:
        n = res.nodes[nid]
        out.update(n.as_run().image_pixels(res.axis))
    return out


class T3_1_Components(unittest.TestCase):
    """G6 plus agreement with an independent flood fill."""

    def test_matches_brute_force_conn8(self):
        rng = random.Random(31)
        for _ in range(60):
            w, h = rng.randrange(1, 16), rng.randrange(1, 16)
            mk = random_mask(rng, w, h, rng.uniform(0.15, 0.75))
            res = sweep(mk, conn=8)
            got = sorted(sorted(comp_pixels(res, c)) for c in res.components)
            want = sorted(sorted(g) for g in brute_components(mk, 8))
            self.assertEqual(got, want)

    def test_matches_brute_force_conn4(self):
        rng = random.Random(32)
        for _ in range(60):
            w, h = rng.randrange(1, 16), rng.randrange(1, 16)
            mk = random_mask(rng, w, h, rng.uniform(0.15, 0.75))
            res = sweep(mk, conn=4)
            got = sorted(sorted(comp_pixels(res, c)) for c in res.components)
            want = sorted(sorted(g) for g in brute_components(mk, 4))
            self.assertEqual(got, want)

    def test_row_and_col_agree_on_partition(self):
        """G6: the component partition must not depend on the sweep axis."""
        rng = random.Random(33)
        for _ in range(60):
            w, h = rng.randrange(1, 16), rng.randrange(1, 16)
            mk = random_mask(rng, w, h, rng.uniform(0.15, 0.75))
            for conn in (4, 8):
                a = sweep(mk, axis="row", conn=conn)
                b = sweep(mk, axis="col", conn=conn)
                pa = sorted(sorted(comp_pixels(a, c)) for c in a.components)
                pb = sorted(sorted(comp_pixels(b, c)) for c in b.components)
                self.assertEqual(pa, pb, f"axis disagreement at conn={conn}")

    def test_diagonal_connectivity_difference(self):
        self.assertEqual(sweep(m(DIAGONAL), conn=8).component_count, 1)
        self.assertEqual(sweep(m(DIAGONAL), conn=4).component_count, 3)

    def test_two_dots(self):
        self.assertEqual(sweep(m(TWO_DOTS)).component_count, 2)

    def test_empty_mask(self):
        res = sweep(InkMask.empty(5, 5))
        self.assertEqual(res.component_count, 0)
        self.assertEqual(res.node_count, 0)
        self.assertEqual(res.events, [])


class T3_2_CycleRank(unittest.TestCase):
    """G2/G3: holes from the cycle rank of the RAG."""

    def test_identity_holds_on_fixtures(self):
        for rows in (RING, FIGURE_8, LETTER_A, LETTER_H, TWO_DOTS, NESTED):
            for axis in ("row", "col"):
                res = sweep(m(rows), axis=axis, capture=Capture.GRAPH)
                self.assertTrue(res.check_cycle_rank(),
                                f"cycle rank identity failed on {rows[0]!r}")

    def test_identity_holds_on_random(self):
        rng = random.Random(34)
        for _ in range(80):
            mk = random_mask(rng, rng.randrange(1, 18), rng.randrange(1, 18),
                             rng.uniform(0.2, 0.8))
            for axis in ("row", "col"):
                self.assertTrue(sweep(mk, axis=axis).check_cycle_rank())

    def test_ring_has_one_hole(self):
        for axis in ("row", "col"):
            res = sweep(m(RING), axis=axis)
            self.assertEqual(res.component_count, 1)
            self.assertEqual(res.components[0].holes, 1)

    def test_figure_8_has_two_holes(self):
        for axis in ("row", "col"):
            res = sweep(m(FIGURE_8), axis=axis)
            self.assertEqual(res.components[0].holes, 2)

    def test_letter_a_has_one_hole(self):
        for axis in ("row", "col"):
            self.assertEqual(sweep(m(LETTER_A), axis=axis).components[0].holes, 1)

    def test_letter_h_has_no_hole(self):
        for axis in ("row", "col"):
            self.assertEqual(sweep(m(LETTER_H), axis=axis).components[0].holes, 0)

    def test_nested_frames_one_hole_each(self):
        for axis in ("row", "col"):
            res = sweep(m(NESTED), axis=axis)
            self.assertEqual(res.component_count, 2)
            self.assertEqual(sorted(c.holes for c in res.components), [1, 1])

    def test_solid_block_has_no_holes(self):
        res = sweep(m(["####"] * 4))
        self.assertEqual(res.components[0].holes, 0)


class T3_3_Events(unittest.TestCase):
    """The event stream on shapes whose critical points are known by hand."""

    def _kinds(self, rows, axis="row"):
        res = sweep(m(rows), axis=axis, capture=Capture.EVENTS)
        return res, {k: len(res.events_of_kind(k)) for k in EventKind}

    def test_ring_events(self):
        """Down-sweep of a ring: 1 birth, 1 split (top opens), 1 merge and
        1 cycle (bottom closes the loop), 1 close."""
        res, n = self._kinds(RING)
        self.assertEqual(n[EventKind.BIRTH], 1)
        self.assertEqual(n[EventKind.SPLIT], 1)
        self.assertEqual(n[EventKind.CYCLE], 1)
        self.assertEqual(n[EventKind.CLOSE], 1)

    def test_letter_h_has_merge_and_split_but_no_cycle(self):
        """The crossbar joins the stems (merge) and they part again
        (split). A merge log alone would miss the split entirely."""
        res, n = self._kinds(LETTER_H)
        self.assertEqual(n[EventKind.BIRTH], 2)
        self.assertGreaterEqual(n[EventKind.MERGE], 1)
        self.assertGreaterEqual(n[EventKind.SPLIT], 1)
        self.assertEqual(n[EventKind.CYCLE], 0)

    def test_letter_a_cycle_count_matches_holes(self):
        res, n = self._kinds(LETTER_A)
        self.assertEqual(n[EventKind.CYCLE], res.components[0].holes)

    def test_two_dots_births_and_closes(self):
        res, n = self._kinds(TWO_DOTS)
        self.assertEqual(n[EventKind.BIRTH], 2)
        self.assertEqual(n[EventKind.CLOSE], 2)
        self.assertEqual(n[EventKind.MERGE], 0)

    def test_cycle_events_equal_total_holes(self):
        rng = random.Random(35)
        for _ in range(60):
            mk = random_mask(rng, rng.randrange(1, 15), rng.randrange(1, 15),
                             rng.uniform(0.3, 0.8))
            res = sweep(mk, capture=Capture.EVENTS)
            self.assertEqual(len(res.events_of_kind(EventKind.CYCLE)),
                             res.cycle_count)

    def test_births_equal_component_count_when_no_merges(self):
        res = sweep(m(TWO_DOTS), capture=Capture.EVENTS)
        self.assertEqual(len(res.events_of_kind(EventKind.BIRTH)),
                         res.component_count)

    def test_every_component_closes_exactly_once(self):
        rng = random.Random(36)
        for _ in range(40):
            mk = random_mask(rng, rng.randrange(1, 14), rng.randrange(1, 14),
                             rng.uniform(0.2, 0.7))
            res = sweep(mk, capture=Capture.EVENTS)
            self.assertEqual(len(res.events_of_kind(EventKind.CLOSE)),
                             res.component_count)

    def test_blank_line_closes_everything(self):
        """G7."""
        res = sweep(m(["###", "...", "###"]), capture=Capture.EVENTS)
        self.assertEqual(res.component_count, 2)
        closes = res.events_of_kind(EventKind.CLOSE)
        self.assertEqual(len(closes), 2)
        self.assertEqual(closes[0].line, 2)

    def test_events_are_sorted(self):
        """G5: deterministic order."""
        rng = random.Random(37)
        mk = random_mask(rng, 13, 13, 0.5)
        res = sweep(mk, capture=Capture.EVENTS)
        keys = [(e.line, e.node) for e in res.events]
        self.assertEqual([k[0] for k in keys], sorted(k[0] for k in keys))

    def test_merge_roots_before_are_distinct(self):
        rng = random.Random(38)
        for _ in range(40):
            mk = random_mask(rng, rng.randrange(2, 14), rng.randrange(2, 14),
                             rng.uniform(0.3, 0.7))
            res = sweep(mk, capture=Capture.EVENTS)
            for e in res.events_of_kind(EventKind.MERGE):
                self.assertGreaterEqual(len(set(e.roots_before)), 2)


class T3_4_CaptureLevels(unittest.TestCase):
    """G4: capture level changes what is recorded, never what is computed."""

    def test_counts_identical_across_capture_levels(self):
        rng = random.Random(39)
        for _ in range(60):
            mk = random_mask(rng, rng.randrange(1, 16), rng.randrange(1, 16),
                             rng.uniform(0.2, 0.8))
            a = sweep(mk, capture=Capture.NONE)
            b = sweep(mk, capture=Capture.EVENTS)
            c = sweep(mk, capture=Capture.GRAPH)
            for x in (b, c):
                self.assertEqual(a.node_count, x.node_count)
                self.assertEqual(a.edge_count, x.edge_count)
                self.assertEqual(a.cycle_count, x.cycle_count)
                self.assertEqual(a.component_count, x.component_count)
                self.assertEqual([cc.nodes for cc in a.components],
                                 [cc.nodes for cc in x.components])

    def test_none_stores_no_edges_or_events(self):
        res = sweep(m(LETTER_A), capture=Capture.NONE)
        self.assertEqual(res.events, [])
        self.assertTrue(all(not n.up and not n.down for n in res.nodes))

    def test_events_level_stores_no_adjacency_lists(self):
        res = sweep(m(LETTER_A), capture=Capture.EVENTS)
        self.assertTrue(res.events)
        self.assertTrue(all(not n.up and not n.down for n in res.nodes))

    def test_graph_level_stores_symmetric_adjacency(self):
        """G1: every edge appears once as `up` and once as `down`."""
        rng = random.Random(40)
        for _ in range(40):
            mk = random_mask(rng, rng.randrange(1, 15), rng.randrange(1, 15),
                             rng.uniform(0.2, 0.8))
            res = sweep(mk, capture=Capture.GRAPH)
            up = {(p, n.id) for n in res.nodes for p in n.up}
            down = {(n.id, ch) for n in res.nodes for ch in n.down}
            self.assertEqual(up, down)
            self.assertEqual(len(up), res.edge_count)

    def test_events_identical_at_events_and_graph_levels(self):
        rng = random.Random(41)
        for _ in range(40):
            mk = random_mask(rng, rng.randrange(1, 15), rng.randrange(1, 15),
                             rng.uniform(0.2, 0.8))
            self.assertEqual(sweep(mk, capture=Capture.EVENTS).events,
                             sweep(mk, capture=Capture.GRAPH).events)

    def test_edges_only_between_consecutive_lines(self):
        rng = random.Random(42)
        mk = random_mask(rng, 15, 15, 0.45)
        res = sweep(mk, capture=Capture.GRAPH)
        for n in res.nodes:
            for p in n.up:
                self.assertEqual(res.nodes[p].line, n.line - 1)


class T3_5_Determinism(unittest.TestCase):

    def test_repeated_runs_identical(self):
        rng = random.Random(43)
        mk = random_mask(rng, 17, 17, 0.5)
        a = sweep(mk, capture=Capture.GRAPH)
        b = sweep(mk, capture=Capture.GRAPH)
        self.assertEqual(a.events, b.events)
        self.assertEqual([c.nodes for c in a.components],
                         [c.nodes for c in b.components])

    def test_nodes_in_scan_order(self):
        rng = random.Random(44)
        for axis in ("row", "col"):
            mk = random_mask(rng, 13, 11, 0.5)
            res = sweep(mk, axis=axis)
            keys = [(n.line, n.lo) for n in res.nodes]
            self.assertEqual(keys, sorted(keys))
            self.assertEqual([n.id for n in res.nodes],
                             list(range(res.node_count)))

    def test_components_keyed_by_lowest_node(self):
        rng = random.Random(45)
        mk = random_mask(rng, 13, 11, 0.4)
        res = sweep(mk)
        firsts = [c.nodes[0] for c in res.components]
        self.assertEqual(firsts, sorted(firsts))


class T3_6_Rejections(unittest.TestCase):

    def test_bad_axis(self):
        with self.assertRaises(InvalidAxis):
            sweep(m(["#"]), axis="diag")

    def test_bad_connectivity(self):
        with self.assertRaises(InvalidConnectivity):
            sweep(m(["#"]), conn=6)

    def test_area_is_not_a_u3_concept(self):
        res = sweep(m(["##"]))
        with self.assertRaises(NotImplementedError):
            res.components[0].area


if __name__ == "__main__":
    unittest.main(verbosity=2)
