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
from inkdrill.aggregate import moments_per_component
from inkdrill.raster import InkMask
from inkdrill.sweep import (Capture, EventKind, sweep,
                            _sweep_reference)

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

    # ---- B1: in-loop moments against the second-pass oracle ----------

    #: The ten fields of `Moments`, in the order `_accumulate` builds
    #: them. Step 1 asserts the first six (area and the four extents,
    #: plus area's position here); step 2 asserts all ten. Named rather
    #: than positional so a failure says WHICH integer is wrong.
    MOMENT_FIELDS = ("area", "sx", "sy", "sxx", "syy", "sxy",
                     "x0", "y0", "x1", "y1")
    EXTENT_FIELDS = ("area", "x0", "y0", "x1", "y1")

    def assert_moments(self, mask, axis, conn, *, fields=None, label=""):
        """`sweep(moments=True).moments` against `moments_per_component`.

        `aggregate._accumulate` is the oracle here, exactly as
        `_sweep_reference` is the oracle for the sweep itself: a second,
        independent computation that is not being changed.

        EXACT INTEGER EQUALITY, never a tolerance. Every one of these
        ten values is an integer by construction -- that is
        `aggregate`'s own G2, and it is the property that makes moving
        the accumulation into the loop a MOVE rather than a rewrite.
        An `assertAlmostEqual` anywhere in here would be a category
        error and would hide precisely the reassociation bug the move
        could introduce.
        """
        fields = self.MOMENT_FIELDS if fields is None else fields
        got = sweep(mask, axis=axis, conn=conn, moments=True)
        want = moments_per_component(
            sweep(mask, axis=axis, conn=conn, capture=Capture.GRAPH))
        where = f"{label} axis={axis} conn={conn}"

        self.assertIsNotNone(got.moments, f"moments not populated: {where}")
        self.assertEqual(sorted(got.moments), sorted(want),
                         f"component roots differ: {where}")
        for root in sorted(want):
            g, w = got.moments[root], want[root]
            for f in fields:
                self.assertEqual(getattr(g, f), getattr(w, f),
                                 f"{f} for root {root}: {where}")
        return len(want)

    def assert_moments_all(self, mask, *, fields=None, label=""):
        n = 0
        for axis in AXES:
            for conn in CONNS:
                self.assert_moments(mask, axis, conn, fields=fields,
                                    label=label)
                n += 1
        return n


# --------------------------------------------------------------------------
# T4 -- hand-written adversarial fixtures
# --------------------------------------------------------------------------

FIXTURES = {
    # -- B1 step 1: the merge branch of the extent accumulator ---------
    # A merge only exercises `min`/`max` if the LOSING component reaches
    # PAST the survivor. It usually does not: the first parent is the
    # leftmost run on the previous line, and the joining run itself has
    # already been folded into the survivor, so the survivor normally
    # holds the extreme already. Measured on the fixture set as it stood
    # before these two: only three (fixture, axis) pairs contained a
    # merge AT ALL, and in none of them did the loser extend past the
    # survivor -- so both merge mutants the CR names survived.
    #
    # Both shapes are the same idea: a component that reaches wide up
    # top, narrows to a single column, and is met lower down by a second
    # component that is nearer the joining run.
    #
    #   left:  the loser's x0 (1) is left of the survivor's (2)
    "merge_loser_reaches_left": [
        ".####.",
        "....#.",
        "..#.#.",
        "..#.#.",
        "..####",
    ],
    #   right: the loser's x1 (5) is right of the survivor's (2)
    "merge_loser_reaches_right": [
        "..####",
        "..#...",
        "#.#...",
        "#.#...",
        "###...",
    ],
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

    # -- the RETIRE cases -------------------------------------------------
    # An external review flagged that nothing advances the previous-line
    # pointer on a line with no runs, so everything pending must be
    # flushed explicitly. A missing flush loses CLOSE events SILENTLY:
    # no exception, and the G2 cycle-rank identity still balances,
    # because CLOSE is an event and not a count.
    "leading_blank_lines": [
        ".....",
        ".....",
        "..##.",
        "..##.",
    ],
    "trailing_blank_lines": [
        ".##..",
        ".##..",
        ".....",
        ".....",
    ],
    "two_blank_lines_between_components": [
        "##...",
        "##...",
        ".....",
        ".....",
        "...##",
        "...##",
    ],
    "full_width_line_between_regions": [
        "#...#",
        ".....",
        "#####",
        ".....",
        "#...#",
    ],
    # Nothing follows the last ink line, so the final flush is the only
    # thing that can close this component.
    "open_at_eof": [
        "..#..",
        ".###.",
        "#####",
    ],
    "single_column": [
        "#",
        "#",
        ".",
        "#",
        "#",
    ],
    "single_row": ["##.###"],
}


def _transposed(rows):
    """Swap the two axes of a fixture."""
    return ["".join(r[i] for r in rows) for i in range(len(rows[0]))]


# The fixture set is row-shaped by history, and three of the four merge
# min/max branches are axis-asymmetric: on a ROW sweep the survivor's
# y1 is always the current line, which is the largest line seen, so
# `w[9] > v[9]` cannot fire there at all. It fires on a COLUMN sweep,
# where y comes from the run's `lo..hi` instead. Transposing the two
# merge fixtures reaches those branches without hand-designing a second
# shape, and by construction rather than by inspection.
for _name in ("merge_loser_reaches_left", "merge_loser_reaches_right"):
    FIXTURES[_name + "_transposed"] = _transposed(FIXTURES[_name])
del _name


class TestFixtures(_SameMixin, unittest.TestCase):

    def test_fixtures(self):
        n = 0
        for name, rows in FIXTURES.items():
            mask = InkMask.from_rows(rows)
            n += self.assert_same_all(mask, label=name)
        # Pinned rather than `> 0`, so a fixture deleted or a capture
        # level dropped from the product shows up as a failure here
        # rather than as a quietly smaller run.
        self.assertEqual(n, len(FIXTURES) * len(AXES) * len(CONNS)
                         * len(CAPTURES))
        self.assertEqual(n, 324)

    def test_empty_mask(self):
        self.assert_same_all(InkMask(b"", 0, 0), label="empty")

    def test_every_component_closes_exactly_once(self):
        """The retire cases, checked WITHOUT the oracle.

        `assert_same` compares two implementations, and both carry their
        own copy of the flush -- the loop over `open_roots` after the
        last line. A flush lost from BOTH would be invisible to it, and
        invisible to G2 as well, because CLOSE is an event and not a
        count. Every component is closed exactly once, at a blank line
        (G7) or at EOF, so the CLOSE count must equal the component
        count. That is the assertion a lost flush actually trips.
        """
        for name, rows in FIXTURES.items():
            mask = InkMask.from_rows(rows)
            for axis in AXES:
                for conn in CONNS:
                    for capture in (Capture.EVENTS, Capture.GRAPH):
                        res = sweep(mask, axis=axis, conn=conn,
                                    capture=capture)
                        closes = res.events_of_kind(EventKind.CLOSE)
                        self.assertEqual(
                            len(closes), res.component_count,
                            f"{name} axis={axis} conn={conn} "
                            f"{capture.value}: {len(closes)} CLOSE events "
                            f"for {res.component_count} components")
                        self.assertEqual(
                            len({e.node for e in closes}), len(closes),
                            f"{name} axis={axis}: a component closed twice")

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


# --------------------------------------------------------------------------
# B1 -- in-loop moment and extent accumulators
# --------------------------------------------------------------------------

class TestMomentsPlumbing(_SameMixin, unittest.TestCase):
    """Step 0: the keyword exists and costs the default caller nothing.

    These three hold at every step of B1 and are not rewritten as the
    accumulation lands -- which is the point of asserting them here
    rather than asserting `moments == {}`, a step-0 detail that would
    have to be deleted in step 1.
    """

    def test_not_asking_yields_None_not_an_empty_dict(self):
        """`None` and `{}` are different answers. `{}` is a mask with no
        components, which is complete and correct; `None` is "nobody
        accumulated anything", which is what step 4's fallback keys on.
        Collapsing them would make a blank page indistinguishable from
        an unasked question."""
        for name, rows in list(FIXTURES.items())[:4]:
            m = InkMask.from_rows(rows)
            self.assertIsNone(sweep(m).moments, name)
            self.assertIsNotNone(sweep(m, moments=True).moments, name)

    def test_an_empty_mask_asked_for_moments_gives_an_empty_dict(self):
        """The `{}` side of the distinction above, so both are pinned."""
        got = sweep(InkMask(b"", 0, 0), moments=True)
        self.assertEqual(got.moments, {})
        self.assertIsNone(sweep(InkMask(b"", 0, 0)).moments)

    def test_the_flag_changes_nothing_else(self):
        """The CR's central promise: a caller that does not ask does not
        pay AND does not notice. Asserted field by field over the whole
        fixture set rather than by `==`, because `moments` is
        `compare=False` and `==` would pass even if the flag corrupted
        the node list."""
        n = 0
        for name, rows in FIXTURES.items():
            mask = InkMask.from_rows(rows)
            for axis in AXES:
                for conn in CONNS:
                    for capture in CAPTURES:
                        a = sweep(mask, axis=axis, conn=conn, capture=capture)
                        b = sweep(mask, axis=axis, conn=conn, capture=capture,
                                  moments=True)
                        where = (f"{name} axis={axis} conn={conn} "
                                 f"capture={capture.value}")
                        self.assertEqual([_node_tuple(x) for x in a.nodes],
                                         [_node_tuple(x) for x in b.nodes],
                                         f"nodes: {where}")
                        self.assertEqual([_comp_tuple(c) for c in a.components],
                                         [_comp_tuple(c) for c in b.components],
                                         f"components: {where}")
                        self.assertEqual([_event_tuple(e) for e in a.events],
                                         [_event_tuple(e) for e in b.events],
                                         f"events: {where}")
                        n += 1
        self.assertEqual(n, len(FIXTURES) * len(AXES) * len(CONNS)
                         * len(CAPTURES))

    @unittest.expectedFailure
    def test_moments_match_the_oracle(self):
        """STEP 0 SHIPS THIS FAILING, ON PURPOSE.

        The accumulation does not exist yet, so `moments=True` yields an
        empty dict and this cannot pass. Marked `expectedFailure` rather
        than omitted so that step 1 cannot land quietly: the moment the
        accumulator is correct, unittest reports an UNEXPECTED SUCCESS
        and the suite fails until the decorator is removed. A test that
        is merely absent gives no such signal, and a test written to
        pass against an empty dict would be a test that asserts nothing.

        The mask is a fixture with several components, not the empty
        mask -- against an empty mask both sides are `{}` and this would
        pass for the wrong reason.
        """
        self.assert_moments(InkMask.from_rows(FIXTURES["comb"]),
                            "row", 8, label="comb")


class TestMomentsExtents(_SameMixin, unittest.TestCase):
    """Step 1: area and the four extents, exact, at both axes.

    Only five of the ten fields. The other five are asserted in step 2;
    checking them here would fail for a reason this step is not
    responsible for.
    """

    def test_extents_match_the_oracle_over_the_fixtures(self):
        """Both axes and both connectivities over the whole fixture set.

        THE AXIS LOOP IS THE POINT OF THIS TEST. A run spans x on a row
        sweep and y on a column sweep, and that swap is the only place
        the two axes differ in the accumulator. Asserting one axis
        would leave the branch half-tested.
        """
        n = 0
        for name, rows in FIXTURES.items():
            n += self.assert_moments_all(InkMask.from_rows(rows),
                                         fields=self.EXTENT_FIELDS,
                                         label=name)
        self.assertEqual(n, len(FIXTURES) * len(AXES) * len(CONNS))

    def test_the_extents_are_asymmetric_somewhere_in_the_fixtures(self):
        """Guards the test above from passing vacuously.

        Swapping x for y is invisible on a mask whose bounding box is
        square, so a fixture set of squares would assert the axis
        branch without being able to fail on it. This asserts that at
        least one fixture has a component whose bbox is NOT square --
        the same discipline as "a fixture built to exercise a rule must
        contain the thing the rule discriminates against".
        """
        found = []
        for name, rows in FIXTURES.items():
            r = sweep(InkMask.from_rows(rows), moments=True)
            for m in r.moments.values():
                if (m.x1 - m.x0) != (m.y1 - m.y0):
                    found.append(name)
                    break
        self.assertTrue(found, "every fixture bbox is square: the axis "
                               "swap could not be detected")
        # Reported so a later fixture edit that flattens the set is
        # visible rather than silent.
        self.assertGreaterEqual(len(found), 5, f"only {found} are asymmetric")

    def test_area_is_the_ink_count(self):
        """An oracle that shares no code with either implementation:
        the areas must sum to the number of ink pixels in the mask."""
        for name, rows in FIXTURES.items():
            mask = InkMask.from_rows(rows)
            ink = mask.data.count(0xFF)
            for axis in AXES:
                r = sweep(mask, axis=axis, moments=True)
                self.assertEqual(sum(m.area for m in r.moments.values()),
                                 ink, f"{name} axis={axis}")


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
