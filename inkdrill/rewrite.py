"""rewrite.py -- a relation graph to a symbol layout tree.

CONTRACT (written before implementation; see docs/units.md M3)
=============================================================

`relate.py` produces candidate edges and labels none of them. Given
those edges LABELLED with relations, this reduces the graph to a tree by
repeated application of productions.

Scored against nothing yet, and that is deliberate
--------------------------------------------------
The gold set (M0) lives on the other side of the interface, so this is
built and tested against SYNTHETIC graphs. What can be established
without gold is the property the whole formalism rests on -- that the
answer does not depend on the order rules were applied in -- and that is
what is tested here, by construction rather than by assertion.

Confluence, and what is actually guaranteed
-------------------------------------------
A rewriting system is confluent when every order of application reaches
the same normal form. That is not free: two productions can match
overlapping node sets, and applying one destroys the other.

**The guarantee here is confluence, enforced structurally rather than
proved.** A production consumes a ROOT and its immediate relation
neighbours, and `rewrite` applies at each step only matches whose node
sets are pairwise DISJOINT, ranked by an order intrinsic to the graph.
Overlapping matches are resolved by that rank, not by which was found
first, so the sequence of steps is a function of the graph alone.

**That order is GEOMETRIC, and getting it wrong is the easy mistake.**
The first attempt ranked by node index, which makes the reduction
deterministic for one labelling and is not confluence at all --
`confluent()` relabels, and rejected it. The rank is now the bounding
box of the match's leaves: it survives relabelling because the page
does.

`confluent()` is exported so a caller can check a graph rather than
trust this: it runs the reduction under many permutations and reports
whether they agree. The test suite uses it over random graphs, which is
the closest thing to a proof available without a formal argument.

"Modulo garbage" is the honest qualifier: nodes matching no production
are left where they are, and two runs agree on the reduced structure
and on that residue. A node that never reduces is not an error -- an
UNRESOLVED symbol is exactly such a node, by M2.3's decision.

UNRESOLVED, one level up (M2.3's consequence)
---------------------------------------------
Every production below is keyed on symbol identity -- `largeop`,
`rule`, `radical`. `relate.needs_identity` refuses a match touching an
unidentified node, and at the measured 14.4% abstention that is a large
share of matches.

The decision mirrors M2.3: **a refused match becomes a typed
placeholder that keeps its children and refuses its operator.** The
tree stays well formed and the gap is explicit, rather than the
subtree being dropped (which loses content) or guessed (which produces
a confident wrong tree from an admitted non-answer).

Guarantees
----------
G1  pure -- symbols and labelled relations in, a forest out
G2  the result is independent of the order productions are applied in,
    for any graph on which `confluent()` returns True
G3  STRUCTURE decides whether a production matches, IDENTITY only what
    it becomes: a match containing an unresolved symbol yields a
    `PLACEHOLDER` retaining every child, never the typed node
G4  every input symbol appears exactly once in the output forest --
    reduction rearranges, it never drops or duplicates
G5  reduction terminates: each step strictly decreases the node count
G6  a node matching no production is returned as it stands, and two
    runs agree on that residue as well as on the reduced structure
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum

from .relate import Symbol, needs_identity

__all__ = ["Relation", "Kind", "Node", "rewrite", "confluent", "chained",
           "PRODUCTIONS"]


class Relation(Enum):
    HORIZONTAL = "HORIZONTAL"
    SUPERSCRIPT = "SUPERSCRIPT"
    SUBSCRIPT = "SUBSCRIPT"
    ABOVE = "ABOVE"
    BELOW = "BELOW"
    CONTAINS = "CONTAINS"


class Kind(Enum):
    SYMBOL = "Symbol"
    SUPSUB = "SupSub"
    LIMITS = "Limits"
    FRACTION = "Fraction"
    ROOT = "Root"
    PLACEHOLDER = "Placeholder"      # G3: identity refused, children kept


@dataclass(frozen=True, slots=True)
class Node:
    """A tree node. Leaves carry a `Symbol`; composites carry children."""
    kind: Kind
    symbol: Symbol | None = None
    children: tuple = ()

    @property
    def leaves(self) -> tuple:
        if self.kind is Kind.SYMBOL:
            return (self.symbol,)
        out = []
        for c in self.children:
            out.extend(c.leaves)
        return tuple(out)

    def shape(self):
        """A hashable structural summary, for comparing two reductions
        without depending on object identity."""
        if self.kind is Kind.SYMBOL:
            # `name` may be None (unresolved), which is unsortable
            # against a string; "" stands for it and cannot collide
            # with a real glyph name.
            return (self.kind.value, self.symbol.name or "", self.symbol.box)
        return (self.kind.value, tuple(c.shape() for c in self.children))


# A production is (name, required relations, node kind, predicate on the
# root symbol). The root is consumed together with one neighbour per
# required relation -- rooted rules, so matching is local (M3.2).
def _is(*names):
    def test(sym):
        return sym.resolved and sym.name in names
    return test


PRODUCTIONS = (
    ("SupSub", (Relation.SUPERSCRIPT, Relation.SUBSCRIPT), Kind.SUPSUB,
     lambda s: True),
    ("Limits", (Relation.ABOVE, Relation.BELOW), Kind.LIMITS,
     _is("summation", "product", "integral", "coproduct", "largeop")),
    ("Fraction", (Relation.ABOVE, Relation.BELOW), Kind.FRACTION,
     _is("rule", "fractionbar")),
    ("Root", (Relation.CONTAINS,), Kind.ROOT,
     _is("radical", "surd")),
)


def _anchor(nodes, members):
    """A rank key intrinsic to the GEOMETRY, not to list position.

    Ranking by node index was the first attempt and it is not
    confluence: it makes the reduction deterministic for one labelling
    of the graph, and `confluent()` -- which relabels -- rejected it.
    An order derived from where the symbols actually are on the page
    survives relabelling, because the page does.
    """
    boxes = []
    for m in members:
        boxes.extend(s.box for s in nodes[m].leaves)
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def _matches(nodes, edges):
    """Every applicable production, as (rank, name, kind, members).

    STRUCTURE decides whether a production matches; IDENTITY decides
    only what it becomes. Gating the match on the identity predicate
    was the first attempt, and it meant an unresolved root simply had
    no match -- so no placeholder was ever built and M2.3's decision
    was silently not implemented (G3).
    """
    out = []
    for i, node in enumerate(nodes):
        if node is None or node.kind is not Kind.SYMBOL:
            continue
        by_rel = {}
        for (a, b), rel in edges.items():
            if a == i and nodes[b] is not None:
                by_rel.setdefault(rel, []).append(b)
        for name, need, kind, pred in PRODUCTIONS:
            if not all(r in by_rel and len(by_rel[r]) == 1 for r in need):
                continue
            members = (i,) + tuple(by_rel[r][0] for r in need)
            if len(set(members)) != len(members):
                continue
            syms = [s for m in members for s in nodes[m].leaves]
            if needs_identity(syms) and not pred(node.symbol):
                continue          # identified, and not this production
            out.append((_anchor(nodes, members), name, kind, members))
    # Rank by geometry then production name -- both intrinsic, so two
    # labellings of one graph rank identically (G2).
    out.sort(key=lambda t: (t[0], t[1]))
    return out


def _reduce_once(nodes, edges, matches):
    """Apply every pairwise-disjoint match in rank order (G2, G5)."""
    used = set()
    fired = False
    for _, name, kind, members in matches:
        if used.intersection(members):
            continue
        syms = [s for m in members for s in nodes[m].leaves]
        root = members[0]
        kids = tuple(nodes[m] for m in members)
        # G3: a production keyed on identity never fires on an
        # unidentified node; it becomes a placeholder that keeps them.
        use = kind if needs_identity(syms) else Kind.PLACEHOLDER
        nodes[root] = Node(use, None, kids)
        for m in members[1:]:
            nodes[m] = None
        used.update(members)
        fired = True
    if fired:
        for key in [k for k in edges if nodes[k[0]] is None
                    or nodes[k[1]] is None]:
            del edges[key]
    return fired


def rewrite(symbols, relations):
    """Reduce a labelled relation graph to a forest of `Node` (G1).

    `relations` maps `(i, j)` to a `Relation`, directed from the parent
    to the child -- `(base, sup): SUPERSCRIPT`.
    """
    nodes = [Node(Kind.SYMBOL, s) for s in symbols]
    edges = dict(relations)
    # A defensive bound only, and provably redundant: every firing step
    # nils at least one node, so the node count strictly decreases and
    # the loop terminates without it (G5). Kept because the cost is one
    # comparison and the failure it guards against -- a production that
    # consumed nothing -- would otherwise hang rather than raise. No
    # test can kill it; none should be written to try.
    guard = len(nodes) + 1
    while guard > 0:
        matches = _matches(nodes, edges)
        if not matches or not _reduce_once(nodes, edges, matches):
            break
        guard -= 1
    return [n for n in nodes if n is not None]


def chained(relations):
    """Same-root scripts rewritten as a CHAIN, for gold comparison.

    Two conventions describe one page and they disagree about what a
    superscript hangs from:

        same-root   x -> 2 (Sup),  x -> i (Sub)      inkdrill
        chained     x -> i (Sub),  i -> 2 (Sup)      pdfdrill's SLT

    Inkdrill produces same-root because that is what the GEOMETRY says:
    `relate.candidates` sees both scripts beside the same base, and
    neither script occludes the other. The chained form is closer to
    LaTeX's own parse, where `x_i^2` binds the scripts in sequence.

    Neither is wrong, and scoring one against the other without
    converting reports EVERY sub-and-superscript pair as an error for a
    reason unconnected to the labeller. The conversion lives here rather
    than in the gold because the gold is the fixed point: it is easier to
    move what this package emits than what 21,240 recorded SLTs say.

    A base carrying BOTH scripts is rewritten; one carrying a single
    script is already identical in the two conventions and is left
    alone.
    """
    out = dict(relations)
    subs = {a: b for (a, b), r in relations.items()
            if r is Relation.SUBSCRIPT}
    sups = {a: b for (a, b), r in relations.items()
            if r is Relation.SUPERSCRIPT}
    for base, sub in subs.items():
        sup = sups.get(base)
        if sup is None or sup == sub:
            continue
        del out[(base, sup)]
        out[(sub, sup)] = Relation.SUPERSCRIPT
    return out


def confluent(symbols, relations, *, trials: int = 24) -> bool:
    """Does every application order reach the same forest? (G2)

    Checked rather than asserted: the node list and edge dict are
    permuted `trials` ways and the reductions compared structurally.
    A caller with an unusual graph can ask instead of trusting.

    The permutations are a SEEDED RANDOM SAMPLE, not the first `trials`
    of `itertools.permutations`. That distinction is not cosmetic: the
    lexicographic prefix fixes the leading positions, so at n=6 the
    first 24 permutations never relabel symbols 0 and 1 at all, and a
    graph whose ambiguity lives among them would be declared confluent
    without ever having been relabelled where it matters. Seeded, so
    two runs still agree.
    """
    base = None
    n = len(symbols)
    rng = random.Random(20260810 + n)
    for _ in range(trials):
        order = list(range(n))
        rng.shuffle(order)
        syms = [symbols[i] for i in order]
        where = {old: new for new, old in enumerate(order)}
        rel = {(where[a], where[b]): r for (a, b), r in relations.items()}
        got = sorted(node.shape() for node in rewrite(syms, rel))
        if base is None:
            base = got
        elif got != base:
            return False
    return True
