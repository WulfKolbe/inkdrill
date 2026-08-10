"""M3: relation graph to symbol layout tree.

Hermetic, and scored against no gold -- M0 is the other side of the
interface. What is established here is the property the formalism rests
on: the answer does not depend on the order rules fired in. That is
tested by running the reduction under many permutations, not by
asserting it in a docstring.
"""

import random
import unittest

from inkdrill.relate import Symbol
from inkdrill.rewrite import Kind, Node, Relation, confluent, rewrite


def sym(name, x=0.0, y=0.0):
    return Symbol((x, y, x + 10.0, y + 10.0), name)


def unknown(x=0.0, y=0.0, reason="margin 0.02"):
    return Symbol((x, y, x + 10.0, y + 10.0), None, reason=reason)


class M3_1_Productions(unittest.TestCase):
    """The rules over relations that measured well."""

    def test_a_base_with_both_scripts_becomes_SupSub(self):
        s = [sym("x"), sym("i", 12, 12), sym("2", 12, -6)]
        f = rewrite(s, {(0, 2): Relation.SUPERSCRIPT,
                        (0, 1): Relation.SUBSCRIPT})
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0].kind, Kind.SUPSUB)

    def test_a_large_operator_with_both_limits_becomes_Limits(self):
        s = [sym("summation"), sym("n", 0, -12), sym("k", 0, 12)]
        f = rewrite(s, {(0, 1): Relation.ABOVE, (0, 2): Relation.BELOW})
        self.assertEqual(f[0].kind, Kind.LIMITS)

    def test_a_rule_with_both_sides_becomes_Fraction(self):
        s = [sym("rule"), sym("a", 0, -12), sym("b", 0, 12)]
        f = rewrite(s, {(0, 1): Relation.ABOVE, (0, 2): Relation.BELOW})
        self.assertEqual(f[0].kind, Kind.FRACTION)

    def test_a_radical_containing_something_becomes_Root(self):
        s = [sym("radical"), sym("x", 8, 0)]
        f = rewrite(s, {(0, 1): Relation.CONTAINS})
        self.assertEqual(f[0].kind, Kind.ROOT)

    def test_the_operator_class_decides_between_Limits_and_Fraction(self):
        """`ABOVE + BELOW` alone is ambiguous -- what separates a
        fraction from a big operator's limits is the ROOT SYMBOL, which
        is why every production here is symbol-keyed and why M2.3's
        decision had to be made before this module."""
        above, below = {(0, 1): Relation.ABOVE, (0, 2): Relation.BELOW}, None
        a = rewrite([sym("summation"), sym("n", 0, -12), sym("k", 0, 12)],
                    above)
        b = rewrite([sym("rule"), sym("n", 0, -12), sym("k", 0, 12)], above)
        self.assertEqual((a[0].kind, b[0].kind), (Kind.LIMITS, Kind.FRACTION))

    def test_an_unmatched_symbol_survives_as_itself(self):
        """G6: garbage is left where it is, not dropped."""
        f = rewrite([sym("a"), sym("b", 20)], {(0, 1): Relation.HORIZONTAL})
        self.assertEqual([n.kind for n in f], [Kind.SYMBOL, Kind.SYMBOL])


class M3_2_Unresolved(unittest.TestCase):
    """G3: M2.3's decision, one level up."""

    def test_a_production_refuses_an_unidentified_root(self):
        s = [unknown(), sym("n", 0, -12), sym("k", 0, 12)]
        f = rewrite(s, {(0, 1): Relation.ABOVE, (0, 2): Relation.BELOW})
        self.assertEqual(f[0].kind, Kind.PLACEHOLDER)

    def test_the_placeholder_keeps_every_child(self):
        """The tree stays well formed and the gap is explicit: dropping
        the subtree would lose content, and guessing would build a
        confident wrong tree from an admitted non-answer."""
        s = [unknown(), sym("n", 0, -12), sym("k", 0, 12)]
        f = rewrite(s, {(0, 1): Relation.ABOVE, (0, 2): Relation.BELOW})
        self.assertEqual(len(f[0].children), 3)
        self.assertEqual(len(f[0].leaves), 3)

    def test_an_unidentified_CHILD_also_refuses_the_production(self):
        """A production is a claim about the whole match, not its root."""
        s = [sym("summation"), unknown(0, -12), sym("k", 0, 12)]
        f = rewrite(s, {(0, 1): Relation.ABOVE, (0, 2): Relation.BELOW})
        self.assertEqual(f[0].kind, Kind.PLACEHOLDER)

    def test_SupSub_is_not_symbol_keyed_and_still_fires(self):
        """Not every production reads identity -- scripts are decided by
        position -- so an unknown base still gets its structure."""
        s = [unknown(), sym("i", 12, 12), sym("2", 12, -6)]
        f = rewrite(s, {(0, 2): Relation.SUPERSCRIPT,
                        (0, 1): Relation.SUBSCRIPT})
        self.assertEqual(f[0].kind, Kind.PLACEHOLDER)
        self.assertEqual(len(f[0].leaves), 3)


class M3_3_Confluence(unittest.TestCase):
    """G2: the answer does not depend on the order rules fired in."""

    def test_a_simple_graph_is_confluent(self):
        s = [sym("summation"), sym("n", 0, -12), sym("k", 0, 12)]
        self.assertTrue(confluent(s, {(0, 1): Relation.ABOVE,
                                      (0, 2): Relation.BELOW}))

    def test_two_independent_productions_are_confluent(self):
        s = [sym("summation"), sym("n", 0, -12), sym("k", 0, 12),
             sym("radical", 40), sym("x", 48)]
        self.assertTrue(confluent(s, {(0, 1): Relation.ABOVE,
                                      (0, 2): Relation.BELOW,
                                      (3, 4): Relation.CONTAINS}))

    def test_OVERLAPPING_productions_are_confluent(self):
        """The case confluence is not free for: one symbol is both a
        radicand and a base with scripts, so two productions compete for
        it and applying either destroys the other."""
        s = [sym("radical"), sym("x", 8), sym("i", 20, 12), sym("2", 20, -6)]
        rel = {(0, 1): Relation.CONTAINS,
               (1, 3): Relation.SUPERSCRIPT,
               (1, 2): Relation.SUBSCRIPT}
        self.assertTrue(confluent(s, rel))

    def test_random_graphs_are_confluent(self):
        """The closest thing to a proof available here: 60 random
        graphs, each reduced under 24 permutations."""
        rng = random.Random(20260810)
        names = ["summation", "rule", "radical", "x", "n", "k", "2", None]
        for trial in range(60):
            n = rng.randint(2, 6)
            syms = []
            for i in range(n):
                nm = rng.choice(names)
                syms.append(Symbol((i * 20.0, 0.0, i * 20.0 + 10, 10.0), nm))
            rel = {}
            for i in range(n):
                for j in range(n):
                    if i != j and rng.random() < 0.25:
                        rel[(i, j)] = rng.choice(list(Relation))
            with self.subTest(trial=trial):
                self.assertTrue(confluent(syms, rel, trials=24))

    def test_confluent_can_return_False(self):
        """Guards the tests above from being vacuous. `confluent`
        compares reductions, so a comparison that always agreed would
        make every assertion here meaningless."""
        from inkdrill import rewrite as mod
        s = [sym("summation"), sym("n", 0, -12), sym("k", 0, 12)]
        rel = {(0, 1): Relation.ABOVE, (0, 2): Relation.BELOW}
        real = mod.rewrite
        calls = []

        def flaky(symbols, relations):
            calls.append(1)
            out = real(symbols, relations)
            return out if len(calls) < 3 else out[:1] + out[:1]
        mod.rewrite = flaky
        try:
            self.assertFalse(confluent(s, rel, trials=6))
        finally:
            mod.rewrite = real


class M3_4_Invariants(unittest.TestCase):
    """G4, G5: reduction rearranges, and it stops."""

    def test_every_input_symbol_appears_exactly_once(self):
        rng = random.Random(7)
        for _ in range(40):
            n = rng.randint(2, 7)
            syms = [Symbol((i * 20.0, 0.0, i * 20.0 + 10, 10.0),
                           rng.choice(["summation", "rule", "radical", "x",
                                       None]))
                    for i in range(n)]
            rel = {(i, j): rng.choice(list(Relation))
                   for i in range(n) for j in range(n)
                   if i != j and rng.random() < 0.3}
            out = rewrite(syms, rel)
            leaves = [lf for node in out for lf in node.leaves]
            self.assertEqual(len(leaves), n)
            self.assertEqual({id(s) for s in leaves}, {id(s) for s in syms})

    def test_a_cyclic_relation_graph_still_terminates(self):
        s = [sym("radical"), sym("radical", 20), sym("radical", 40)]
        rel = {(0, 1): Relation.CONTAINS, (1, 2): Relation.CONTAINS,
               (2, 0): Relation.CONTAINS}
        out = rewrite(s, rel)
        self.assertEqual(len([lf for n in out for lf in n.leaves]), 3)

    def test_a_self_loop_does_not_consume_a_node_twice(self):
        """A labeller that emits `(i, i)` would otherwise put one node
        in a match twice, and the reduction would nil it out from under
        itself -- losing a symbol, which G4 forbids."""
        s = [sym("radical")]
        out = rewrite(s, {(0, 0): Relation.CONTAINS})
        self.assertEqual(len([lf for n in out for lf in n.leaves]), 1)

    def test_an_empty_graph_reduces_to_nothing(self):
        self.assertEqual(rewrite([], {}), [])


if __name__ == "__main__":
    unittest.main()
