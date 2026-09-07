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
    delegation recursive."""

    __slots__ = ()
    finds = [0]
    unions = [0]

    def find(self, i):
        _CountingUF.finds[0] += 1
        return _BASE.find(self, i)

    def union(self, a, b):
        _CountingUF.unions[0] += 1
        return _BASE.union(self, a, b)

    def union_roots(self, a, b):
        _CountingUF.unions[0] += 1
        return _BASE.union_roots(self, a, b)


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
        cut them would be computing something else."""
        mask = _glyph_page()
        _, _, gu = self._count(sweep, mask, Capture.NONE)
        _, _, ru = self._count(_sweep_reference, mask, Capture.NONE)
        # The reference's union() now delegates to union_roots, so the
        # wrapper sees each of its unions twice.
        self.assertEqual(gu, ru // 2)


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
