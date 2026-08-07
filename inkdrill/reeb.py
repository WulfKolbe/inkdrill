"""reeb.py — Reeb contraction, orientation reversal, persistence, signature.

CONTRACT (written before implementation; see docs/units.md U4)
=============================================================

The Reeb graph of a scan sweep
------------------------------
U3 leaves a run adjacency graph whose nodes are maximal runs and whose
height function is the scan line. Most of those nodes carry no
information: a straight vertical stroke is a long chain of runs each with
exactly one predecessor and one successor. Contracting those chains
leaves only where the shape does something -- starts, ends, forks, joins
-- which is the Reeb graph.

A run node is a JUNCTION when the shape forks or joins at it:

        len(up) >= 2   (a merge)      or      len(down) >= 2   (a split)

`up` points to the previous scan line, `down` to the next, so with
h = line the sweep runs in increasing h. Junctions each become their own
`ReebNode`; every maximal chain of non-junction runs becomes one. A
`ReebNode` is therefore an ARC, and that is deliberate: it is what makes
`persistence` below equal `h(close) - h(birth)` as specified, rather than
the span of some interior fragment.

Splitting on junctions rather than on "degree 2" matters at the ends. A
birth has `len(up) == 0` and a close has `len(down) == 0`, so neither is
degree-2 -- but neither is a branch point either, and cutting there would
chop every arc into three pieces and leave a plain vertical bar as three
nodes instead of one. No branching is created or destroyed either way,
which is why a signature computed here says the same thing about shape
that the full RAG does, in far fewer nodes.

Orientation, and why two scans give four
----------------------------------------
Regularity is SYMMETRIC: swapping `up` and `down` leaves `len(up) == 1
and len(down) == 1` unchanged. So the contracted node set does not depend
on the direction of sweep -- only the LABELS do, with births becoming
closes and merges becoming splits. `orient()` therefore derives ROW_UP
from the row RAG and COL_UP from the column RAG by relabelling, with no
second scan. This is docs/units.md assumption 2, and G3 is its test.

Persistence
-----------
A `ReebNode` is an arc of the Reeb graph -- a branch -- and its
persistence is the span of scan lines it covers, `h(close) - h(birth)`.
A 2-px speck has persistence 2; a stroke down the page has hundreds.
That is the whole of the noise/structure distinction available from
topology alone.

Signature -- what it is, and what it is NOT
-------------------------------------------
`signature()` reduces one Reeb graph to a comparable integer vector;
`signature_of()` does the same for a SET of graphs, because a glyph is
not always one component -- `i j : ; = %` are multi-part, and every U3
fixture is a single blob, so this is invisible from fixtures alone.

**A signature is a partition, not a classifier.** Measured 2026-08-07 on
8,453 real glyph components (docs/units.md §3, "U4 premise check"): the
modal signature of a character class holds 98-100% for most letters, so
it is stable; but only 26.9% of glyphs get a signature unique to one
character, with `n h 3 N`, `i . / : j ; ?` and `e 6` colliding. It earns
its place as ONE CHANNEL, exactly as U13 specifies alongside the
normalised bitmap and absolute extents. Nothing here should be read as
identifying a glyph.

The counts are integers and deliberately so: they are EXACTLY invariant
under translation, because nothing in them refers to position.

**They are NOT rotation invariant, and the plan's expectation that they
would be is refuted.** Measured 2026-08-07 on real glyph components
lifted from rendered corpus pages and rotated by nearest-neighbour
resampling:

        at +-3 deg      full signature kept     cycle count kept
        four samples        41 - 78%                80 - 99%
        0.0 (control)         100%                    100%

Four independent 120-component samples. The control is exact every time,
so the loss is rotation and not the resampler being lossy in general.
Thin strokes gain and lose junctions under resampling, and the
birth/merge/split counts move with them.

The SPREAD is wide and page-dependent, so no point estimate here is
meaningful -- an earlier revision of this docstring quoted 47-54% from a
single sample and that figure does not reproduce. What DOES reproduce, on
every sample taken, is the ordering: the cycle count survives rotation by
20-40 percentage points more than the full signature. That ordering is
the claim; the percentages are context.

Re-run it with:  python3 tools/premise/measure.py --corpus <dir> rotation

The load-bearing consequence for U13: **`cycles` is the durable
component of this vector and the branch counts are the fragile one.** A
consumer comparing signatures across a skewed page should weight them
accordingly, or deskew first.

**That durability has one exception, and it is the math population.**
For NEAR-HORIZONTAL SEPARATED STROKES rotation can merge components and
CREATE cycles, so there `cycles` is the least durable part:

        two 40-wide bars, 1-row gap      0 deg: parts=2 cycles=0
                                        +-3 deg: parts=1 cycles=1
        three 50-wide bars, 1-row gaps   0 deg: parts=3 cycles=0
                                        +-3 deg: parts=1 cycles=4

At 3 degrees a 50-px-wide bar rises ~2.6 px across its width, so a 1-px
gap closes and the bars genuinely become one component. The rotated image
really is connected -- this is finite resolution, not a resampler
artefact. The affected shapes are `=`, `≡`, `÷`, fraction bars, `\\hline`
and the radical overbar, which is exactly what U14 depends on and what
U13 will lean on hardest. A consumer must not treat a cycle count on
separated horizontal strokes as stable under skew.

Note also that clean synthetic ink is mostly rotation-STABLE -- rings at
14/20/32/48 px with 1-3 px strokes, a 40-row H, a 48-row figure-8 and a
comb are all bit-stable under +-3 degrees. The fragility is a property
of real glyph ink under resampling, not of the signature in general --
which is why the fixtures in T4_6 had to be found by search. Whether a genuine re-render at 3 degrees -- antialiased, then
thresholded -- is gentler than nearest-neighbour resampling is untested,
and is now the single load-bearing measurement for this guarantee rather
than a caveat on it.

Guarantees
----------
G1  every RAG node appears in exactly one ReebNode; the contraction is a
    partition of the nodes, losing none and duplicating none
G2  contraction preserves branching: the number of critical nodes of each
    kind is the same before and after
G3  `orient(rag, ROW_UP)` is structurally equal to a genuine sweep of the
    vertically flipped mask -- assumption 2, tested rather than argued
G4  reversal is an involution: orienting twice returns the original
    labelling
G5  `signature()` is invariant under translation, EXACTLY. It is NOT
    claimed to be invariant under rotation. `cycles` survives rotation
    far better than the branch counts on CLOSED forms; on near-horizontal
    separated strokes that inverts and rotation creates cycles. Both
    halves are under test, and both fixtures fail if the rotation is
    turned into a no-op
G6  persistence separates a 2-px speck from a stroke, and equals
    `hi_line - lo_line + 1` for every node
G7  `signature_of()` on a single graph equals `signature()` on it, with
    `parts == 1`; the multi-component case is the general one and the
    single-component case falls out of it

Non-guarantees (out of scope for U4)
------------------------------------
  * no moment aggregates -- that is U5
  * no hole/containment forest -- that is U6
  * no glyph identification -- see the signature note above; U13 owns
    classification, and it needs channels this unit does not provide
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, NamedTuple

from .raster import InkMask
from .sweep import Capture, SweepResult, sweep

__all__ = ["Direction", "ReebNode", "ReebGraph", "Signature",
           "contract", "orient", "signature", "signature_of",
           "InvalidDirection"]


class InvalidDirection(ValueError):
    """direction must be a Direction member."""


class Direction(Enum):
    """Sweep direction. The two DOWN directions are native to a sweep of
    the corresponding axis; the two UP directions are derived from the
    same RAG by reversal, with no second scan."""
    ROW_DOWN = "row_down"
    ROW_UP = "row_up"
    COL_DOWN = "col_down"
    COL_UP = "col_up"

    @property
    def axis(self) -> str:
        return "row" if self in (Direction.ROW_DOWN, Direction.ROW_UP) else "col"

    @property
    def reversed_(self) -> bool:
        return self in (Direction.ROW_UP, Direction.COL_UP)

    def flipped(self) -> "Direction":
        return {Direction.ROW_DOWN: Direction.ROW_UP,
                Direction.ROW_UP: Direction.ROW_DOWN,
                Direction.COL_DOWN: Direction.COL_UP,
                Direction.COL_UP: Direction.COL_DOWN}[self]


@dataclass(slots=True)
class ReebNode:
    """One arc of the Reeb graph: a critical run, or a contracted chain
    of regular ones."""
    id: int
    runs: list[int]                       # RAG node ids, in sweep order
    lo_line: int
    hi_line: int
    up: list[int] = field(default_factory=list)     # toward lower h
    down: list[int] = field(default_factory=list)   # toward higher h

    @property
    def persistence(self) -> int:
        """G6: scan lines spanned, inclusive."""
        return self.hi_line - self.lo_line + 1

    @property
    def is_birth(self) -> bool:
        return not self.up

    @property
    def is_close(self) -> bool:
        return not self.down

    @property
    def is_merge(self) -> bool:
        return len(self.up) >= 2

    @property
    def is_split(self) -> bool:
        return len(self.down) >= 2


@dataclass(slots=True)
class ReebGraph:
    direction: Direction
    nodes: list[ReebNode]
    cycle_count: int
    component_count: int

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return sum(len(n.down) for n in self.nodes)

    def node_of_run(self, run_id: int) -> ReebNode:
        for n in self.nodes:
            if run_id in n.runs:
                return n
        raise KeyError(run_id)


class Signature(NamedTuple):
    """A comparable integer vector. NOT an identifier -- see the module
    docstring."""
    parts: int          # number of components combined
    cycles: int
    births: int
    closes: int
    merges: int
    splits: int

    def __repr__(self) -> str:
        return (f"Signature(parts={self.parts}, cycles={self.cycles}, "
                f"b={self.births}, c={self.closes}, "
                f"m={self.merges}, s={self.splits})")


# --------------------------------------------------------------------------
# Contraction
# --------------------------------------------------------------------------

def _junction(node) -> bool:
    """The shape forks or joins here, so an arc must end."""
    return len(node.up) >= 2 or len(node.down) >= 2


def contract(result: SweepResult,
             direction: Direction | None = None) -> ReebGraph:
    """Contract a Capture.GRAPH sweep into its Reeb graph.

    Maximal chains of regular runs collapse to one ReebNode each (G1);
    critical runs each become their own. Branching is untouched (G2).
    """
    if result.capture is not Capture.GRAPH:
        raise ValueError(
            f"contract needs Capture.GRAPH; got {result.capture.value}. "
            "Only the GRAPH level retains the up/down adjacency.")
    if direction is None:
        direction = (Direction.ROW_DOWN if result.axis == "row"
                     else Direction.COL_DOWN)

    by_id = {n.id: n for n in result.nodes}

    # A run continues its predecessor's arc only when neither is a
    # junction and the predecessor leads here and nowhere else.
    owner: dict[int, int] = {}          # run id -> ReebNode id
    nodes: list[ReebNode] = []

    for run in result.nodes:
        if not _junction(run) and len(run.up) == 1:
            up = by_id[run.up[0]]
            if not _junction(up) and up.down == [run.id]:
                rn = nodes[owner[up.id]]
                rn.runs.append(run.id)
                rn.hi_line = run.line
                owner[run.id] = rn.id
                continue
        rn = ReebNode(len(nodes), [run.id], run.line, run.line)
        nodes.append(rn)
        owner[run.id] = rn.id

    # Edges between ReebNodes, from the RAG edges that cross a boundary.
    for run in result.nodes:
        a = owner[run.id]
        for nxt in run.down:
            b = owner[nxt]
            if a != b:
                nodes[a].down.append(b)
                nodes[b].up.append(a)

    for n in nodes:
        n.down.sort()
        n.up.sort()

    g = ReebGraph(direction, nodes, result.cycle_count,
                  result.component_count)
    if direction.reversed_:
        return _reverse(g)
    return g


def _reverse(g: ReebGraph) -> ReebGraph:
    """Swap the height direction. Regularity is symmetric, so only the
    labels move -- the node set is untouched (G3, G4)."""
    out = []
    for n in g.nodes:
        out.append(ReebNode(n.id, list(reversed(n.runs)),
                            n.lo_line, n.hi_line,
                            up=list(n.down), down=list(n.up)))
    return ReebGraph(g.direction.flipped(), out, g.cycle_count,
                     g.component_count)


def orient(result: SweepResult, direction: Direction) -> ReebGraph:
    """The Reeb graph for any of the four directions, from the RAG of the
    matching axis. The UP directions cost a relabelling, not a scan.
    """
    if not isinstance(direction, Direction):
        raise InvalidDirection(direction)
    if direction.axis != result.axis:
        raise InvalidDirection(
            f"{direction.value} needs an axis={direction.axis!r} sweep; "
            f"this result is axis={result.axis!r}")
    base = (Direction.ROW_DOWN if direction.axis == "row"
            else Direction.COL_DOWN)
    g = contract(result, base)
    return _reverse(g) if direction.reversed_ else g


# --------------------------------------------------------------------------
# Signature
# --------------------------------------------------------------------------

def signature(g: ReebGraph) -> Signature:
    """Reduce one Reeb graph to a comparable integer vector."""
    return Signature(
        parts=g.component_count,
        cycles=g.cycle_count,
        births=sum(1 for n in g.nodes if n.is_birth),
        closes=sum(1 for n in g.nodes if n.is_close),
        merges=sum(1 for n in g.nodes if n.is_merge),
        splits=sum(1 for n in g.nodes if n.is_split),
    )


def signature_of(graphs: Iterable[ReebGraph]) -> Signature:
    """Combine several graphs into one signature.

    G7: a single graph gives exactly `signature()` of it. A glyph made of
    several components -- `i`, `j`, `:` -- is the general case, and the
    single-component case falls out of it.
    """
    gs = list(graphs)
    if not gs:
        return Signature(0, 0, 0, 0, 0, 0)
    dirs = {g.direction for g in gs}
    if len(dirs) != 1:
        raise InvalidDirection(
            f"cannot combine graphs of differing directions: "
            f"{sorted(d.value for d in dirs)}")
    sigs = [signature(g) for g in gs]
    return Signature(
        parts=sum(s.parts for s in sigs),
        cycles=sum(s.cycles for s in sigs),
        births=sum(s.births for s in sigs),
        closes=sum(s.closes for s in sigs),
        merges=sum(s.merges for s in sigs),
        splits=sum(s.splits for s in sigs),
    )


def graph_of(mask: InkMask, direction: Direction = Direction.ROW_DOWN,
             *, conn: int = 8) -> ReebGraph:
    """Convenience: mask -> Reeb graph, running the sweep for you."""
    if not isinstance(direction, Direction):
        raise InvalidDirection(direction)
    res = sweep(mask, axis=direction.axis, conn=conn, capture=Capture.GRAPH)
    return orient(res, direction)
