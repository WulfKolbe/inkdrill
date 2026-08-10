"""relate.py -- candidate edges for a symbol relation graph.

CONTRACT (written before implementation; see docs/units.md M2.1)
===============================================================

Given symbol boxes, decide which PAIRS are worth asking a relation
about. This is the Build stage's first half: it produces candidates, and
labels none of them. What a candidate edge means -- `SUPERSCRIPT`,
`ABOVE`, `CONTAINS` -- is M2.2 and is not here.

Why line-of-sight, measured rather than assumed
-----------------------------------------------
The published comparison (2NN, 6NN, COM, LOS) was made on a
handwriting-heavy benchmark. This corpus is printed arXiv maths, so
`measure.py edges` re-took it here first, over 608 maths lines and
17,473 symbols:

    strategy   reading-order recall   edges/node   occluded edges
    2NN                     98.07%         1.09             2,525
    6NN                     99.83%         3.29            40,706
    LOS                     99.95%         0.96      0 by construction

**LOS wins on all three axes at once**, which is not the usual shape of
such a comparison: it has the best recall AND the fewest edges, 3.4x
fewer than 6NN. So there is no trade-off to tune here, and the
recommendation survives the change of population.

The oracle, and what it cannot say
----------------------------------
There is no relation gold set on this side yet, so recall is measured
against a NECESSARY condition: two characters adjacent in reading order
must be connected, or no relation between them is expressible at all.
**A complete graph scores 100% on that.** Recall is therefore only
meaningful beside edges-per-node, and both are reported together --
which is why LOS's 0.96 is the interesting half of its result, not the
99.95%.

Occlusion is the one claim testable with no gold at all, and it is the
reason LOS exists: 6NN connected 40,706 pairs with a third symbol
between them. Around a fraction bar or a large operator that is exactly
the wrong edge.

Cost, and the bound on it
-------------------------
The test is O(n^2) pairs each against O(n) blockers. At a line's 29
symbols that is nothing; at a page's thousands it is not, so
`candidates` takes `max_symbols` and RAISES rather than quietly
degrading -- a silently truncated graph would lose edges without saying
which. A segment-bbox prefilter removes most blocker tests before the
clipping arithmetic runs.

UNRESOLVED nodes: geometry yes, rewriting no (M2.3)
----------------------------------------------------
The glyph classifier abstains. Measured, `agrees(extents_tol=0.4)`
rejects **14.4%** of even its CORRECT answers -- the price of cutting
silently-wrong from 11.90% to 0.31%. A relation graph therefore has to
say what a node with no identity is.

The decision, and it is a decision rather than a measurement:

    an unresolved node KEEPS ITS GEOMETRY and takes part in relations;
    it is refused only by rules keyed on WHAT SYMBOL IT IS.

Both halves matter. Dropping the node would break the graph around it --
its neighbours would see through a hole that is not there, and
`candidates` would connect symbols that a real glyph separates, which
is precisely the occlusion error line-of-sight exists to avoid. And
treating it as a symbol would let `largeop + ABOVE + BELOW -> Limits`
fire on something never identified as a large operator, producing a
confident wrong tree from an admitted non-answer.

So `Symbol.label` RAISES on an unresolved node instead of returning a
placeholder. That follows `sweep.Component.area`, which raises rather
than guessing at a value belonging to another unit: a caller that needs
identity must handle its absence at the point of use, and cannot
receive a plausible default by accident. A rule that only needs
position never touches `label` and is unaffected.

Guarantees
----------
G1  pure -- boxes in, index pairs out; no I/O and no global state
G2  an edge is emitted iff NO other box crosses the open segment
    between the two centres, so occlusion is zero by construction
G3  edges are undirected and returned once, as `(i, j)` with `i < j`,
    sorted -- so two runs are comparable and a diff means something
G4  a box never occludes an edge it is an endpoint of, and touching a
    segment endpoint is not occlusion; otherwise adjacent symbols would
    block themselves
G5  degenerate input is answered, not raised: fewer than two boxes
    gives no edges
G6  `max_symbols` is enforced with an exception, never by truncation
G7  an UNRESOLVED symbol keeps its geometry and its edges; only
    `label` is refused, and refusing raises rather than returning a
    sentinel that could be compared against a real name
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Box", "Symbol", "Unresolved", "blocked", "candidates", "clip",
           "needs_identity", "partition", "TooManySymbols"]

# A box is (x0, y0, x1, y1) with y increasing DOWNWARD, matching the
# page convention pdfminer and `raster` both use.
Box = tuple[float, float, float, float]

# Fractions of the segment within which a crossing does not count as
# occlusion -- a blocker must genuinely lie BETWEEN, not merely touch an
# endpoint, or every symbol would occlude its own neighbours (G4).
_NEAR = 0.02

MAX_SYMBOLS = 400


class TooManySymbols(ValueError):
    """More symbols than `candidates` will consider (G6)."""


class Unresolved(LookupError):
    """A symbol-keyed rule asked an unidentified node what it is (G7)."""


@dataclass(frozen=True, slots=True)
class Symbol:
    """A node: geometry always, identity sometimes.

    `reason` records WHY identity is absent -- the abstention is a
    finding, not a gap, and a QC surface wants to show which glyphs a
    human must adjudicate rather than merely how many.
    """
    box: Box
    name: str | None = None
    margin: float = 0.0
    reason: str = ""

    @property
    def resolved(self) -> bool:
        return self.name is not None

    @property
    def label(self) -> str:
        """The symbol's identity, or `Unresolved` (G7).

        Deliberately not a sentinel: `"UNKNOWN"` would compare equal to
        itself, so two unidentified glyphs would look like the same
        symbol and a rule keyed on equality would fire between them.
        """
        if self.name is None:
            raise Unresolved(
                f"symbol at {self.box} was not identified"
                + (f" ({self.reason})" if self.reason else "")
                + "; it keeps its geometry and its edges, but no rule "
                  "keyed on symbol identity may fire on it")
        return self.name

    @property
    def centre(self) -> tuple[float, float]:
        return _centre(self.box)


def needs_identity(symbols) -> bool:
    """May a symbol-keyed production be attempted over these? (G7)

    The guard a rewriter calls before matching a rule that reads
    `label`. Returns False if ANY participant is unresolved, because a
    production is a claim about the whole match.
    """
    return all(s.resolved for s in symbols)


def partition(symbols):
    """`(resolved, unresolved)`, as two lists.

    The residual is the product here as everywhere: the unresolved list
    is the QC surface -- exactly the glyphs a human must adjudicate --
    and is returned rather than counted so a caller can show them.
    """
    keep, drop = [], []
    for s in symbols:
        (keep if s.resolved else drop).append(s)
    return keep, drop


def _centre(b: Box) -> tuple[float, float]:
    return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)


def clip(ax: float, ay: float, dx: float, dy: float, c: Box):
    """The parametric interval where the ray `(ax,ay) + t*(dx,dy)` is
    inside box `c`, or None if it never is (Liang-Barsky).

    Returned rather than folded into a boolean because it is the
    computation M2.1's headline rests on -- the 40,706 occluded pairs
    are what this produced -- and a caller that only sees `True/False`
    cannot tell a correct interval from a wrong one that happens to
    have the same sign. An audit found six branches here unfalsifiable
    from outside for exactly that reason.

    The interval is clamped to `[0, 1]`, so t=0 is the segment start
    and t=1 its end.

    **The two `return None` early-outs are provably equivalent to their
    own absence** and are kept only as an optimisation. Removing either
    lets `t0` and `t1` cross, and the final `t1 > t0` test then rejects
    the interval identically -- the invariant `t0 <= t1` is maintained
    by the refinements themselves, since `t0` is only raised after
    checking it stays under `t1` and vice versa. They save two
    divisions per blocker in an O(n^2 * n) loop, which is why they are
    here; no test can kill them and none should be written to try.

    The final guard is NOT equivalent, and reaching it needs a
    degenerate box: a zero-width blocker gives both x slabs the same
    parameter, so `t0 == t1` exactly and the ray touches without ever
    being inside. The early-outs cannot see that -- they fire only on
    an INVERTED interval -- so without the guard a zero-width box
    occludes everything behind it.
    """
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, ax - c[0]), (dx, c[2] - ax),
                 (-dy, ay - c[1]), (dy, c[3] - ay)):
        if p == 0.0:
            # Parallel to this slab: inside it for all t, or for none.
            if q < 0.0:
                return None
            continue
        r = q / p
        if p < 0.0:
            if r > t1:
                return None
            if r > t0:
                t0 = r
        else:
            if r < t0:
                return None
            if r < t1:
                t1 = r
    return (t0, t1) if t1 > t0 else None


def blocked(a: Box, b: Box, others) -> bool:
    """Does any box in `others` cross the open segment `a`->`b` (G2)?

    Liang-Barsky clipping of the centre-to-centre segment against each
    candidate blocker. The parametric interval is required to overlap
    the segment's interior, which is what implements G4.
    """
    ax, ay = _centre(a)
    bx, by = _centre(b)
    dx, dy = bx - ax, by - ay
    lo_x, hi_x = (ax, bx) if ax <= bx else (bx, ax)
    lo_y, hi_y = (ay, by) if ay <= by else (by, ay)
    for c in others:
        # Prefilter: a box disjoint from the segment's bounding box
        # cannot cross it, and this removes most blockers before any
        # division happens.
        if c[2] < lo_x or c[0] > hi_x or c[3] < lo_y or c[1] > hi_y:
            continue
        span = clip(ax, ay, dx, dy, c)
        if span is None:
            continue
        t0, t1 = span
        if t1 > _NEAR and t0 < 1.0 - _NEAR:
            return True
    return False


def candidates(boxes, *, max_symbols: int = MAX_SYMBOLS):
    """Candidate edges as sorted `(i, j)` pairs with `i < j` (G3).

    `boxes` is a sequence of `(x0, y0, x1, y1)`. Raises
    `TooManySymbols` past `max_symbols` rather than truncating (G6):
    a graph missing edges it does not name is worse than no graph.
    """
    boxes = list(boxes)
    if len(boxes) > max_symbols:
        raise TooManySymbols(
            f"{len(boxes)} symbols exceeds max_symbols={max_symbols}; "
            f"segment the region first rather than accepting a partial graph")
    n = len(boxes)
    if n < 2:
        return []                                            # G5
    out = []
    for i in range(n):
        for j in range(i + 1, n):
            others = [boxes[k] for k in range(n) if k != i and k != j]
            if not blocked(boxes[i], boxes[j], others):
                out.append((i, j))
    return out
