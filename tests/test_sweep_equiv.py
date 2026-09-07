"""test_sweep_equiv.py -- `sweep` against `_sweep_reference`, field by field.

THE CONTRACT UNDER TEST
=======================
For every mask, every `axis`, every `conn` and every `capture` level,
`sweep` must return a `SweepResult` FIELD-BY-FRIELD equal to
`_sweep_reference`: same nodes in the same order with the same
id/line/lo/hi/up/down, same components in the same order with the same
`root`, `nodes`, `edge_count`, `cycle_count`, `first_line`, `last_line`,
and same events in the same order with the same kind/line/node/
partners/roots_before/root_after.

Equality of COUNTS is not the bar. `_UF.union` breaks a size tie by
leaving the NEWER node as root, so any reordering of the unions
renumbers `Component.root` while V, E, C and the cycle count all stay
right -- and eight modules (`aggregate`, `band`, `emit`, `nest`, `reeb`,
`skeleton`, `trace`, `qc`) key on that root. `test_root_identity_trap`
is the minimal mask where that happens.

Same precedent as `nest._label`: the pre-fast-path implementation is
retained as the oracle rather than deleted.
"""

from __future__ import annotations

import random
import unittest

from inkdrill import sweep as sweepmod
from inkdrill.raster import InkMask
from inkdrill.sweep import Capture, sweep, _sweep_reference

_BASE = sweepmod._UF

AXES = ("row", "col")
CONNS = (4, 8)
CAPTURES = (Capture.NONE, Capture.EVENTS, Capture.GRAPH)


def _node_tuple(n):
    return (n.id, n.line, n.lo, n.hi, tuple(n.up), tuple(n.down))


def _comp_tuple(c):
    return (c.root, tuple(c.nodes), c.edge_count, c.cycle_count,
            c.first_line, c.last_line)


def _event_tuple(e):
    return (e.kind, e.line, e.node, tuple(e.partners),
            tuple(e.roots_before), e.root_after)


class _SameMixin:

    def assert_same(self, mask, axis, conn, capture, label=""):
        """The contract, for one (mask, axis, conn, capture)."""
        got = sweep(mask, axis=axis, conn=conn, capture=capture)
        ref = _sweep_reference(mask, axis=axis, conn=conn, capture=capture)
        where = f"{label} axis={axis} conn={conn} capture={capture.value}"

        self.assertEqual([_node_tuple(n) for n in got.nodes],
                         [_node_tuple(n) for n in ref.nodes],
                         f"nodes differ: {where}")
        self.assertEqual([_comp_tuple(c) for c in got.components],
                         [_comp_tuple(c) for c in ref.components],
                         f"components differ: {where}")
        self.assertEqual([_event_tuple(e) for e in got.events],
                         [_event_tuple(e) for e in ref.events],
                         f"events differ: {where}")
        # T8: an invariant derived independently of the oracle, so it
        # still says something if the oracle itself is edited by mistake.
        self.assertTrue(got.check_cycle_rank(), f"cycle rank: {where}")
        return got

    def assert_same_all(self, mask, label=""):
        n = 0
        for axis in AXES:
            for conn in CONNS:
                for capture in CAPTURES:
                    self.assert_same(mask, axis, conn, capture, label)
                    n += 1
        return n


# --------------------------------------------------------------------------
# T4 -- hand-written adversarial fixtures
# --------------------------------------------------------------------------

FIXTURES = {
    # Two singleton components joined from below. Both sides have size 1
    # at the union, so the tie-break decides the root. Every count is
    # right whichever way it goes; only the root distinguishes them.
    "root_identity_trap": [
        "#.#",
        "###",
    ],
    "comb": [
        "#######",
        "#.#.#.#",
        "#.#.#.#",
        "#.#.#.#",
    ],
    "ring": [
        ".###.",
        ".#.#.",
        ".###.",
    ],
    "ring_grid": [
        "###.###",
        "#.#.#.#",
        "###.###",
        ".......",
        "###.###",
        "#.#.#.#",
        "###.###",
    ],
    "diagonal_chain": [
        "#....",
        ".#...",
        "..#..",
        "...#.",
        "....#",
    ],
    "checkerboard": [
        "#.#.#",
        ".#.#.",
        "#.#.#",
        ".#.#.",
    ],
    "single_pixel": [
        ".....",
        "..#..",
        ".....",
    ],
    "blank_line_inside": [
        "###",
        "...",
        "###",
    ],
    "full_width": [
        "#####",
        "#####",
    ],
    "one_run_per_line": [
        "#....",
        "#....",
        "#....",
    ],
    "spans_first_and_last": [
        "..#..",
        "..#..",
        "..#..",
    ],
    "nested_rings": [
        "#######",
        "#.....#",
        "#.###.#",
        "#.#.#.#",
        "#.###.#",
        "#.....#",
        "#######",
    ],
    "split_then_merge": [
        "#####",
        "#...#",
        "#####",
    ],
    "all_blank": [
        ".....",
        ".....",
    ],
    "one_by_one_ink": ["#"],
    "one_by_one_blank": ["."],
}


class TestFixtures(_SameMixin, unittest.TestCase):

    def test_fixtures(self):
        n = 0
        for name, rows in FIXTURES.items():
            mask = InkMask.from_rows(rows)
            n += self.assert_same_all(mask, label=name)
        self.assertGreater(n, 0)

    def test_empty_mask(self):
        self.assert_same_all(InkMask(b"", 0, 0), label="empty")

    def test_root_identity_trap(self):
        """The named trap, asserted on its own so a failure says which
        property broke rather than 'a fixture differs'."""
        mask = InkMask.from_rows(FIXTURES["root_identity_trap"])
        got = sweep(mask, axis="row", conn=8, capture=Capture.GRAPH)
        ref = _sweep_reference(mask, axis="row", conn=8,
                               capture=Capture.GRAPH)
        self.assertEqual(len(got.components), 1)
        self.assertEqual([c.root for c in got.components],
                         [c.root for c in ref.components])
        # The property that makes this a trap: the root is NOT nodes[0],
        # so a run that merely preserved counts could not be detected.
        c = got.components[0]
        self.assertNotEqual(c.root, c.nodes[0])


# --------------------------------------------------------------------------
# T2 -- random differential fuzz across a DENSITY ladder
# --------------------------------------------------------------------------

def _random_mask(rng, w, h, density):
    rows = ["".join("#" if rng.random() < density else "."
                    for _ in range(w))
            for _ in range(h)]
    return InkMask.from_rows(rows)


class TestFuzz(_SameMixin, unittest.TestCase):
    """Density is the axis that matters, not size: a sparse mask is
    almost all single-parent runs and exercises the fast path, a dense
    mask is few large components and exercises merges and cycles. A fuzz
    run at one density tests half the change."""

    DENSITIES = (0.01, 0.05, 0.20, 0.50)
    SIZES = ((7, 7), (23, 17), (41, 39))
    SEEDS = (1, 2, 3, 4)

    def test_fuzz(self):
        checked = 0
        for density in self.DENSITIES:
            for (w, h) in self.SIZES:
                for seed in self.SEEDS:
                    rng = random.Random((seed, w, h, density).__hash__())
                    mask = _random_mask(rng, w, h, density)
                    checked += self.assert_same_all(
                        mask, label=f"d={density} {w}x{h} s={seed}")
        self.assertGreaterEqual(checked, 500)


# --------------------------------------------------------------------------
# T2b -- stripe/structured randoms: long runs, many continues
# --------------------------------------------------------------------------

class TestStructuredRandom(_SameMixin, unittest.TestCase):

    def test_glyph_like(self):
        """Rings on a grid: the shape the fast path is aimed at, where
        ~90% of runs have exactly one parent with exactly one child."""
        rng = random.Random(11)
        for trial in range(4):
            w, h = 60, 44
            buf = bytearray(w * h)
            for gy in range(0, h - 12, 12):
                for gx in range(0, w - 10, 10):
                    if rng.random() < 0.3:
                        continue
                    for y in range(gy, gy + 10):
                        for x in range(gx, gx + 8):
                            edge = (y in (gy, gy + 9)
                                    or x in (gx, gx + 7))
                            if edge:
                                buf[y * w + x] = 0xFF
            self.assert_same_all(InkMask(bytes(buf), w, h),
                                 label=f"glyphlike{trial}")


if __name__ == "__main__":
    unittest.main()


# --------------------------------------------------------------------------
# T5 -- the find budget: what this change is actually about
# --------------------------------------------------------------------------

class _CountingUF(sweepmod._UF):
    """Counts calls without changing behaviour. `_BASE` is captured at
    class-creation time so rebinding `sweep._UF` cannot make the
    delegation recursive.

    `unions` counts UNIONS PERFORMED, not calls made -- one increment
    per pair of distinct roots actually merged, wherever in the `_UF`
    surface the merge happens. The whole surface is overridden so a new
    entry point cannot make merges invisible: `union` delegates and is
    counted by the `union_roots` it calls on this same instance, and
    `attach` is counted here only on its fast path, which merges without
    going through `union_roots`.
    """

    __slots__ = ()
    finds = [0]
    unions = [0]

    def find(self, i):
        _CountingUF.finds[0] += 1
        return _BASE.find(self, i)

    def union(self, a, b):
        # No increment: `_BASE.union` calls `self.union_roots`, which is
        # the override below, so counting here would double-count.
        return _BASE.union(self, a, b)

    def union_roots(self, a, b):
        if a != b:
            _CountingUF.unions[0] += 1
        return _BASE.union_roots(self, a, b)

    def attach(self, a, b):
        if self.size[b] > 1:
            # The fast path merges directly and never reaches
            # `union_roots`; below it, `_BASE.attach` delegates there.
            _CountingUF.unions[0] += 1
        return _BASE.attach(self, a, b)


def _glyph_page(w=240, h=176):
    """Ring glyphs on a grid: mostly single-parent runs, the shape the
    case dispatch is aimed at."""
    buf = bytearray(w * h)
    for gy in range(2, h - 12, 12):
        for gx in range(2, w - 10, 10):
            for y in range(gy, gy + 10):
                for x in range(gx, gx + 8):
                    if y in (gy, gy + 9) or x in (gx, gx + 7):
                        buf[y * w + x] = 0xFF
    return InkMask(bytes(buf), w, h)


class TestFindBudget(unittest.TestCase):
    """A wall-clock assertion would be flaky and would not say WHAT
    regressed. The find count is deterministic, machine-independent, and
    is the quantity the change is about."""

    # Measured on this fixture after the case dispatch: 2.00 at NONE and
    # 4.57 at GRAPH, against 6.95 and 7.52 for the reference. The bounds
    # sit above the measurement and below the reference, so they catch a
    # regression toward the old behaviour without pinning an exact count
    # that a legitimate refactor could move.
    BUDGET = {Capture.NONE: 2.5, Capture.GRAPH: 5.0}

    def _count(self, fn, mask, capture):
        _CountingUF.finds[0] = 0
        _CountingUF.unions[0] = 0
        orig = sweepmod._UF
        sweepmod._UF = _CountingUF
        try:
            res = fn(mask, capture=capture)
        finally:
            sweepmod._UF = orig
        return res, _CountingUF.finds[0], _CountingUF.unions[0]

    def test_find_budget(self):
        mask = _glyph_page()
        for capture, budget in self.BUDGET.items():
            got, gf, gu = self._count(sweep, mask, capture)
            ref, rf, ru = self._count(_sweep_reference, mask, capture)
            v = got.node_count
            self.assertEqual(v, ref.node_count)
            self.assertLessEqual(
                gf / v, budget,
                f"{capture.value}: {gf/v:.2f} finds/run exceeds the "
                f"budget of {budget}; reference is {rf/v:.2f}")
            self.assertLess(gf, rf,
                            f"{capture.value}: no reduction against the "
                            f"reference ({gf} vs {rf})")

    def test_union_count_unchanged(self):
        """The unions are the real work and must not move: a change that
        cut them would be computing something else.

        Asserted as a TOPOLOGICAL IDENTITY rather than against the
        reference's tally. Every union merges two distinct components,
        so V singletons reaching C components took exactly V - C of
        them; that number is a property of the partition, not of how
        many `_UF` methods a run happens to call. Counting calls at the
        boundary would instead have been an instrumentation detail, and
        `attach`'s fast path -- which merges by writing `parent`
        directly -- would have moved it without changing any answer.
        """
        masks = [("glyph_page", _glyph_page()),
                 ("nested_rings",
                  InkMask.from_rows(FIXTURES["nested_rings"])),
                 ("checkerboard",
                  InkMask.from_rows(FIXTURES["checkerboard"])),
                 ("all_blank", InkMask.from_rows(FIXTURES["all_blank"]))]
        for label, mask in masks:
            for capture in (Capture.NONE, Capture.GRAPH):
                got, _, gu = self._count(sweep, mask, capture)
                ref, _, ru = self._count(_sweep_reference, mask, capture)
                want = got.node_count - got.component_count
                self.assertEqual(
                    gu, want,
                    f"{label} {capture.value}: {gu} unions performed, "
                    f"V - C = {want}")
                self.assertEqual(
                    ru, ref.node_count - ref.component_count,
                    f"{label} {capture.value}: reference off the identity")
                self.assertEqual(gu, ru, f"{label} {capture.value}")


# --------------------------------------------------------------------------
# T7 -- orthogonality: band stitching runs the same union logic twice
# --------------------------------------------------------------------------

class TestBandRegression(unittest.TestCase):
    """`band.stitch` re-applies U3's adjacency predicate across seams
    with its own union-find, and its G2 is 'indistinguishable from
    sweep()'. It is the strongest single regression check on this
    change, because it exercises the same partition through a second
    implementation."""

    def test_banded_matches_sweep(self):
        from inkdrill import band
        masks = [InkMask.from_rows(FIXTURES["nested_rings"]),
                 InkMask.from_rows(FIXTURES["ring_grid"]),
                 _glyph_page(120, 96)]
        for i, mask in enumerate(masks):
            whole = sweep(mask, axis="row", conn=8, capture=Capture.GRAPH)
            want = {frozenset(c.nodes) for c in whole.components}
            for k in (1, 2, 3, 5, 8):
                if k > max(1, mask.height):
                    continue
                got = band.sweep_banded(mask, k)
                self.assertEqual(got.node_count, whole.node_count,
                                 f"mask{i} k={k} V")
                self.assertEqual(got.edge_count, whole.edge_count,
                                 f"mask{i} k={k} E")
                self.assertEqual(got.component_count, whole.component_count,
                                 f"mask{i} k={k} C")
                self.assertEqual(got.cycle_count, whole.cycle_count,
                                 f"mask{i} k={k} cycles")
                self.assertEqual({frozenset(c.nodes) for c in got.components},
                                 want, f"mask{i} k={k} partition")
                self.assertTrue(got.check_cycle_rank())


# --------------------------------------------------------------------------
# G8 -- node ids are dense and equal their index in `nodes`
# --------------------------------------------------------------------------

class TestNodeIdsAreDense(unittest.TestCase):
    """G8, asserted for both producers of a `SweepResult`.

    It held as an accident of construction -- `_UF.make` returns the
    pre-append length and `nodes.append` follows immediately -- and
    seven call sites in six modules rebuilt `{n.id: n for n in nodes}`
    from it anyway. Before those maps go, the accident has to become a
    guarantee, which means a test that fails when a producer breaks it.

    `band` is the one that could break it, because stitching renumbers.
    """

    def _assert_dense(self, res, where):
        for i, n in enumerate(res.nodes):
            self.assertEqual(n.id, i, f"{where}: nodes[{i}].id == {n.id}")
        # Dense means the ids are exactly range(V), which is what makes
        # `nodes[i]` a total lookup rather than one that happens to work.
        self.assertEqual({n.id for n in res.nodes}, set(range(len(res.nodes))),
                         f"{where}: ids are not 0..V-1")
        # Everything that keys on a node id must land inside that range.
        for c in res.components:
            for i in c.nodes:
                self.assertTrue(0 <= i < len(res.nodes),
                                f"{where}: component node id {i} out of range")
            self.assertTrue(0 <= c.root < len(res.nodes),
                            f"{where}: root {c.root} out of range")

    def test_node_ids_are_dense(self):
        """`sweep`, over the whole fixture set at every axis, conn and
        capture."""
        n = 0
        for name, rows in FIXTURES.items():
            mask = InkMask.from_rows(rows)
            for axis in AXES:
                for conn in CONNS:
                    for capture in CAPTURES:
                        res = sweep(mask, axis=axis, conn=conn,
                                    capture=capture)
                        self._assert_dense(
                            res, f"{name} {axis} conn={conn} "
                                 f"{capture.value}")
                        n += 1
        self._assert_dense(sweep(InkMask(b"", 0, 0)), "empty")
        self._assert_dense(sweep(_glyph_page(80, 64)), "glyph_page")
        rng = random.Random(23)
        for d in (0.02, 0.2, 0.6):
            self._assert_dense(_sweep_of_random(rng, d), f"random d={d}")
        self.assertGreater(n, 0)

    def test_node_ids_are_dense_after_stitching(self):
        """`band.sweep_banded`, which renumbers across seams and is the
        producer that could plausibly break G8."""
        from inkdrill import band
        masks = [("nested_rings",
                  InkMask.from_rows(FIXTURES["nested_rings"])),
                 ("ring_grid", InkMask.from_rows(FIXTURES["ring_grid"])),
                 ("comb", InkMask.from_rows(FIXTURES["comb"])),
                 ("all_blank", InkMask.from_rows(FIXTURES["all_blank"])),
                 ("glyph_page", _glyph_page(120, 96))]
        for label, mask in masks:
            for k in (1, 2, 3, 5, 8, 13):
                if k > max(1, mask.height):
                    continue
                res = band.sweep_banded(mask, k)
                self._assert_dense(res, f"banded {label} k={k}")


def _sweep_of_random(rng, density):
    return sweep(_random_mask(rng, 33, 27, density), capture=Capture.GRAPH)


# --------------------------------------------------------------------------
# component_of -- the index must answer exactly what the scan answered
# --------------------------------------------------------------------------

class TestComponentOf(unittest.TestCase):
    """`component_of` was a linear scan and is now a lazy index. The
    index is checked against the scan for EVERY node, not sampled: a
    lookup table that is right for most ids and wrong for a few is the
    failure mode worth excluding."""

    @staticmethod
    def _by_scan(res, node_id):
        for c in res.components:
            if node_id in c.nodes:
                return c
        raise KeyError(node_id)

    def _check(self, mask, label):
        for capture in (Capture.NONE, Capture.EVENTS, Capture.GRAPH):
            res = sweep(mask, axis="row", conn=8, capture=capture)
            for n in res.nodes:
                self.assertIs(res.component_of(n.id),
                              self._by_scan(res, n.id),
                              f"{label} capture={capture.value} node={n.id}")

    def test_matches_the_scan(self):
        for name in ("nested_rings", "ring_grid", "comb", "checkerboard",
                     "root_identity_trap", "diagonal_chain"):
            self._check(InkMask.from_rows(FIXTURES[name]), name)
        self._check(_glyph_page(80, 64), "glyph_page")
        rng = random.Random(97)
        for d in (0.05, 0.5):
            self._check(_random_mask(rng, 31, 29, d), f"random d={d}")

    def test_unknown_id_raises(self):
        res = sweep(InkMask.from_rows(FIXTURES["ring"]), capture=Capture.NONE)
        with self.assertRaises(KeyError):
            res.component_of(10 ** 6)
        with self.assertRaises(KeyError):
            res.component_of(-1)

    def test_index_does_not_affect_equality(self):
        """Building the index must not make two identical results
        compare unequal -- the field is compare=False."""
        mask = InkMask.from_rows(FIXTURES["ring_grid"])
        a = sweep(mask, capture=Capture.GRAPH)
        b = sweep(mask, capture=Capture.GRAPH)
        a.component_of(0)                      # a has an index, b has none
        self.assertEqual(a.components, b.components)
        self.assertEqual(a.nodes, b.nodes)
        self.assertEqual(a, b)

    def test_empty_result(self):
        res = sweep(InkMask(b"", 0, 0), capture=Capture.NONE)
        with self.assertRaises(KeyError):
            res.component_of(0)
