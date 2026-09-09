"""sweep.py — connected components via the run adjacency graph.

CONTRACT (written before implementation; see docs/units.md U3)
=============================================================

The run adjacency graph (RAG)
-----------------------------
Nodes are the maximal runs from `raster.iter_runs`. An edge joins two runs
on CONSECUTIVE scan lines that touch under the active connectivity:

        conn=8:  they touch iff  p.hi >= r.lo - 1  and  p.lo <= r.hi + 1
        conn=4:  the same with the slack term dropped

The RAG is the object this package is built on. Connected components,
hole counts, the join tree, the Reeb graph and the branch skeleton are
all derived from it, and every edge is enumerated exactly once during a
single sweep. A prior implementation enumerated these edges, consumed
them in `union()`, discarded them, and then rebuilt the same graph later
to count holes; this module keeps them instead.

Scan events (Morse theory on the sweep height function)
-------------------------------------------------------
A row-down sweep computes the components of the sublevel sets of
h(x, y) = y. The events are the critical points of h:

    birth   a run with no edge to the previous line -- local minimum
    merge   a run joining >= 2 PREVIOUSLY DISTINCT components -- join saddle
    cycle   an edge whose endpoints were ALREADY in one component: a loop
            closes, i.e. a hole is born
    split   a run on the previous line with >= 2 edges down -- fork saddle
    close   a component with no run on the current line -- local maximum

`split` is the reason the RAG is required and a merge log is not enough:
union-find is monotone and never splits, so a fork is invisible to it.

Connectivity duality
--------------------
8-connected foreground implies 4-connected background. Hole finding runs
this sweep on an inverted mask with conn=4. The pair is constrained; do
not vary one without the other.

Guarantees
----------
G1  every RAG edge is visited exactly once; `edge_count` equals the number
    of adjacent (previous-line, current-line) run pairs
G2  cycle rank identity, per component and in total:
        cycle_count == edge_count - node_count + component_count
G3  `cycle_count` of a component == its number of holes, for conn=8
    foreground (equivalently conn=4 background)
G4  `Capture.NONE` yields the same components, node/edge/cycle counts as
    `Capture.GRAPH`; only `events` and the `up`/`down` lists differ
G5  components, events and nodes are produced in deterministic order:
    nodes in scan order, events in (line, kind-priority, node) order,
    components keyed by their lowest node id
G6  the component partition is identical for axis="row" and axis="col"
G7  a blank scan line closes every open component
G8  node ids are DENSE and equal their index in `nodes`, so
    `result.nodes[i]` is the run with id `i`. Every producer of a
    `SweepResult` must preserve this -- `sweep` does because `_UF.make`
    returns the pre-append length and the `nodes.append` follows
    immediately, and `band.stitch` does because it renumbers into scan
    order and rebuilds the list from the new ids. It is a guarantee to
    consumers, not an accident of construction: seven call sites in six
    modules were rebuilding `{n.id: n for n in result.nodes}` from it.

Non-guarantees (out of scope for U3)
------------------------------------
  * no moment aggregates -- that is U5
  * no Reeb contraction or persistence -- that is U4
  * whole-page, not streaming: the bounded-memory closure stream is a
    later unit; `capture=NONE` bounds the PER-BLOB payload, not the sweep
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterator

from .raster import InkMask, InvalidAxis, Run, iter_runs

__all__ = ["Capture", "Conn", "EventKind", "Event", "RunNode", "Component",
           "termini",
           "SweepResult", "sweep", "InvalidConnectivity"]


class InvalidConnectivity(ValueError):
    """conn must be exactly 4 or 8."""


class Capture(Enum):
    """What the sweep records. Components and all counts are always
    produced; this controls only the retained detail."""
    NONE = "none"      # counts only
    EVENTS = "events"  # + the scan event list
    GRAPH = "graph"    # + per-node up/down adjacency


class Conn(Enum):
    FOUR = 4
    EIGHT = 8


class EventKind(Enum):
    BIRTH = "birth"
    MERGE = "merge"
    CYCLE = "cycle"
    SPLIT = "split"
    CLOSE = "close"


# Ordering priority within one line, for G5 determinism.
_KIND_ORDER = {EventKind.BIRTH: 0, EventKind.MERGE: 1, EventKind.CYCLE: 2,
               EventKind.SPLIT: 3, EventKind.CLOSE: 4}


@dataclass(frozen=True, slots=True)
class Event:
    """One critical point of the sweep height function."""
    kind: EventKind
    line: int
    node: int                        # the run at which it was observed
    partners: tuple[int, ...] = ()   # other runs involved (edge endpoints)
    roots_before: tuple[int, ...] = ()
    root_after: int | None = None

    def __repr__(self) -> str:
        return (f"Event({self.kind.value}, line={self.line}, "
                f"node={self.node}, partners={list(self.partners)})")


@dataclass(slots=True)
class RunNode:
    """A run, plus its RAG adjacency when `Capture.GRAPH` is in force."""
    id: int
    line: int
    lo: int
    hi: int
    up: list[int] = field(default_factory=list)
    down: list[int] = field(default_factory=list)

    @property
    def length(self) -> int:
        return self.hi - self.lo + 1

    def as_run(self) -> Run:
        return Run(self.line, self.lo, self.hi)


@dataclass(slots=True)
class Component:
    """One connected component, as counts plus its node ids."""
    root: int
    nodes: list[int]
    edge_count: int = 0
    cycle_count: int = 0
    first_line: int = 0
    last_line: int = 0

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def area(self) -> int:
        raise NotImplementedError("area is a U5 aggregate, not a U3 count")

    @property
    def holes(self) -> int:
        """Hole count from the cycle rank -- available at every capture
        level, because it is a counter rather than a stored structure."""
        return self.cycle_count


@dataclass(slots=True)
class SweepResult:
    """One sweep of one mask: its runs, its components, its events.

    Guarantees carried by the OBJECT, numbered with the module contract
    at the top of this file:

    G5  `nodes` are in scan order, `events` in (line, kind, node) order,
        `components` keyed by their lowest node id.
    G8  node ids are dense and equal their index in `nodes`, so
        `result.nodes[i]` IS the run with id `i` and no `{n.id: n}` map
        is needed to look one up. Producers of a `SweepResult` must
        preserve this; `sweep` and `band.stitch` both do, and
        `tests/test_sweep_equiv.test_node_ids_are_dense` holds them to
        it.
    G9  `nodes` and `components` -- and the `Component.nodes` lists
        inside them -- are treated as IMMUTABLE once a result is
        constructed. `component_of` builds an index over them on first
        call and never invalidates it, so a later edit would be
        answered from a stale index rather than rejected. Build a new
        `SweepResult` instead; `band.stitch` is the worked example.
    """
    axis: str
    conn: int
    capture: Capture
    nodes: list[RunNode]
    components: list[Component]
    events: list[Event]
    # Per-component moment/extent accumulators, keyed by component ROOT,
    # or None when the caller did not ask for them (B1). `None` and `{}`
    # are different answers: `{}` is a mask with no components, which is
    # a correct and complete result, whereas `None` means nothing was
    # accumulated and a consumer must fall back. Excluded from equality
    # for the same reason as `_index` -- the flag must not be able to
    # make two otherwise identical sweeps compare unequal, which is what
    # keeps the equivalence gate meaningful at `moments=False`.
    #
    # STEP 1 OF B1: `area` and the four extents are accumulated and
    # equal `aggregate.moments_per_component` exactly. THE FIVE MOMENT
    # SUMS -- sx sy sxx syy sxy -- ARE STILL ZERO and arrive in step 2,
    # so `moments=True` is not yet a substitute for that call. The
    # contract is deliberately not written down as a guarantee until
    # all ten hold; `test_moments_match_the_oracle` checks all ten, is
    # marked `expectedFailure`, and will report an unexpected success
    # -- which unittest treats as a suite failure -- the moment step 2
    # makes it true.
    moments: dict | None = field(default=None, compare=False, repr=False)
    # Lazy node -> component index for `component_of`. Excluded from
    # equality and repr, so whether it happens to be built cannot make
    # two otherwise identical results compare unequal.
    _index: dict | None = field(default=None, compare=False, repr=False)

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return sum(c.edge_count for c in self.components)

    @property
    def cycle_count(self) -> int:
        return sum(c.cycle_count for c in self.components)

    @property
    def component_count(self) -> int:
        return len(self.components)

    def check_cycle_rank(self) -> bool:
        """G2: the Euler identity that ties the counts together."""
        return (self.cycle_count ==
                self.edge_count - self.node_count + self.component_count)

    def events_of_kind(self, kind: EventKind) -> list[Event]:
        return [e for e in self.events if e.kind is kind]

    def component_of(self, node_id: int) -> Component:
        """The component holding `node_id`.

        Backed by a node -> component index built on FIRST CALL and kept
        for the rest of this result's life. Nothing new is computed: the
        component-assembly loop in `sweep` already calls `uf.find` on
        every node and groups them, and this is only what that loop
        threw away.

        It was a linear scan over components with a LIST membership test
        per component, so a lookup cost O(V) and its price depended on
        where the node's component sorted -- the last component on a
        page cost ~80x the first. `emit.component_topology` calls this
        once per event. Measured on a dense 400-dpi page (p41 of
        kolbe2018hubbard: V=143,965, C=2,950, 14,640 events) the
        attribution loop cost 11.8 s against a 0.83 s sweep for the same
        page.

        The index costs one dict entry per run and is only paid by
        callers that actually use this method.

        IT IS NEVER INVALIDATED. Mutating `components`, or a
        `Component.nodes` list, after a call to this method would be
        answered from the stale index -- silently, with a plausible
        component. That makes G9 above a rule this method depends on
        rather than an observation: `nodes` and `components` are
        immutable once the result is constructed. Nothing in the
        package edits either today -- `band.stitch` builds a fresh
        `SweepResult` rather than editing one -- which is precisely why
        it needs writing down. A rule that holds by accident is the one
        that stops holding.
        """
        idx = self._index
        if idx is None:
            idx = {}
            for c in self.components:
                for i in c.nodes:
                    idx[i] = c
            self._index = idx
        try:
            return idx[node_id]
        except KeyError:
            raise KeyError(node_id) from None


# --------------------------------------------------------------------------
# Union-find, local to the sweep
# --------------------------------------------------------------------------

class _UF:
    __slots__ = ("parent", "size")

    def __init__(self) -> None:
        self.parent: list[int] = []
        self.size: list[int] = []

    def make(self) -> int:
        i = len(self.parent)
        self.parent.append(i)
        self.size.append(1)
        return i

    def find(self, i: int) -> int:
        p = self.parent
        while p[i] != i:
            p[i] = p[p[i]]       # path halving
            i = p[i]
        return i

    def union(self, a: int, b: int) -> int:
        return self.union_roots(self.find(a), self.find(b))

    def union_roots(self, ra: int, rb: int) -> int:
        """Union two ids that are ALREADY roots.

        The size comparison and its tie-break are those of `union`,
        copied unchanged and not rewritten: with equal sizes `ra` stays
        the root, which is what makes a NEW run the root of the
        component it merges into. `Component.root` is an identity that
        eight modules key on, so flipping `<` to `<=` here renumbers
        every root while every count stays right.
        """
        if ra == rb:
            return ra
        if self.size[ra] < self.size[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.size[ra] += self.size[rb]
        return ra

    def attach(self, new_id: int, root: int) -> int:
        """Add a freshly made singleton `new_id` to the component rooted
        at `root`, returning the surviving root.

        Exactly `union_roots(new_id, root)`. It exists because that call
        is the commonest operation in the sweep and its outcome is
        almost always `root` itself -- a fresh singleton loses the size
        comparison against any component of two runs or more, so from a
        component's third run onward the root does not move. Naming that
        case lets the caller skip moving counters that are not going
        anywhere.

        The `size[root] == 1` case is NOT a special case here: it is
        delegated to `union_roots` precisely so the tie-break that makes
        a new run the root of a two-singleton component stays in one
        place (see `test_root_identity_trap`).

        Precondition: `new_id` is its own root with size 1. Not checked
        -- this is the innermost path in the package, and `sweep` calls
        it only on the id it just made.
        """
        if self.size[root] > 1:
            self.parent[new_id] = root
            self.size[root] += 1
            return root
        return self.union_roots(new_id, root)


# --------------------------------------------------------------------------
# The sweep
# --------------------------------------------------------------------------

def _lines(mask: InkMask, axis: str) -> Iterator[tuple[int, list[Run]]]:
    """Group runs into (line, runs) pairs. Blank lines are not yielded;
    the caller detects a gap from the line numbers."""
    cur_line = -1
    batch: list[Run] = []
    for r in iter_runs(mask, axis):
        if r.line != cur_line:
            if batch:
                yield cur_line, batch
            cur_line, batch = r.line, [r]
        else:
            batch.append(r)
    if batch:
        yield cur_line, batch


# --------------------------------------------------------------------------
# Reference implementation
#
# `_sweep_reference` is the sweep as it stood before the fast-path work,
# kept verbatim and not exported. It is the ONLY definition of what
# `sweep` must return: tests/test_sweep_equiv.py holds the two to
# field-by-field identical output -- same nodes in the same order, same
# components with the SAME `root`, same events. Equality of counts is
# not the bar, because `_UF.union` leaves the NEWER node as root when
# both sides have size 1, so a reordered union renumbers every root
# while every count stays right, and eight downstream modules key on
# `Component.root`.
#
# Same precedent as `nest._label`: the slow path is retained as the
# oracle rather than deleted once the fast path passes.
# --------------------------------------------------------------------------

def _sweep_reference(mask: InkMask, *, axis: str = "row", conn: int = 8,
          capture: Capture = Capture.NONE) -> SweepResult:
    """Pre-fast-path sweep, retained as the equivalence oracle.

    See the module contract for G1-G7. `conn` must be 4 or 8; use 4 when
    sweeping an inverted mask for hole finding.
    """
    if axis not in ("row", "col"):
        raise InvalidAxis(axis)
    if conn == 8:
        slack = 1
    elif conn == 4:
        slack = 0
    else:
        raise InvalidConnectivity(conn)

    keep_graph = capture is Capture.GRAPH
    keep_events = capture in (Capture.EVENTS, Capture.GRAPH)

    uf = _UF()
    nodes: list[RunNode] = []
    events: list[Event] = []
    # per-root counters; migrated on union
    edges_of: dict[int, int] = {}
    cycles_of: dict[int, int] = {}

    prev: list[tuple[int, int, int]] = []   # (lo, hi, node_id), sorted by lo
    prev_line = None
    open_roots: set[int] = set()

    for line, runs in _lines(mask, axis):
        contiguous = prev_line is not None and line == prev_line + 1
        prevline = prev if contiguous else []
        kids_of: dict[int, list[int]] = {}     # prev node -> current nodes
        cur: list[tuple[int, int, int]] = []
        pi = 0
        # Hoisted: `prevline` cannot change inside this loop, and
        # `len()` in the two-pointer conditions is evaluated once per
        # advance of each pointer -- the innermost code in the package.
        nprev = len(prevline)

        for r in runs:
            nid = uf.make()
            node = RunNode(nid, r.line, r.lo, r.hi)
            nodes.append(node)
            edges_of[nid] = 0
            cycles_of[nid] = 0

            # -- adjacency: two-pointer sweep over the previous line -------
            adj: list[int] = []
            while pi < nprev and prevline[pi][1] < r.lo - slack:
                pi += 1
            pj = pi
            while pj < nprev and prevline[pj][0] <= r.hi + slack:
                adj.append(prevline[pj][2])
                pj += 1

            # roots BEFORE any union caused by this run -- a merge is
            # defined by what was distinct on arrival, not after the fact
            roots_before = tuple(sorted({uf.find(p) for p in adj}))

            if not adj:
                if keep_events:
                    events.append(Event(EventKind.BIRTH, line, nid))

            for p in adj:
                kids_of.setdefault(p, []).append(nid)
                if keep_graph:
                    node.up.append(p)
                    nodes[p].down.append(nid)
                rn, rp = uf.find(nid), uf.find(p)
                if rn == rp:
                    # both endpoints already in one component: a loop
                    # closes here, i.e. a hole is born
                    cycles_of[rn] += 1
                    edges_of[rn] += 1
                    if keep_events:
                        events.append(Event(EventKind.CYCLE, line, nid,
                                            (p,), (rp,), rn))
                else:
                    e = edges_of.pop(rn) + edges_of.pop(rp) + 1
                    c = cycles_of.pop(rn) + cycles_of.pop(rp)
                    root = uf.union(rn, rp)
                    edges_of[root] = e
                    cycles_of[root] = c

            if adj and len(roots_before) >= 2 and keep_events:
                events.append(Event(EventKind.MERGE, line, nid, tuple(adj),
                                    roots_before, uf.find(nid)))

            cur.append((r.lo, r.hi, nid))

        # -- splits: a previous-line run with more than one edge down ------
        if keep_events:
            for p in sorted(kids_of):
                kids = kids_of[p]
                if len(kids) >= 2:
                    events.append(Event(EventKind.SPLIT, nodes[p].line, p,
                                        tuple(sorted(kids))))

        # -- closures ------------------------------------------------------
        touched = {uf.find(n) for (_, _, n) in cur}
        if keep_events:
            for r0 in sorted(open_roots):
                if uf.find(r0) not in touched:
                    events.append(Event(EventKind.CLOSE, line, r0, (),
                                        (uf.find(r0),)))
        open_roots = touched

        prev, prev_line = cur, line

    # -- final closures ----------------------------------------------------
    if keep_events and open_roots and prev_line is not None:
        for r0 in sorted(open_roots):
            events.append(Event(EventKind.CLOSE, prev_line + 1, r0, (),
                                (uf.find(r0),)))

    # -- assemble components -----------------------------------------------
    by_root: dict[int, list[int]] = {}
    for n in nodes:
        by_root.setdefault(uf.find(n.id), []).append(n.id)
    comps: list[Component] = []
    for root, ids in by_root.items():
        ids.sort()
        lines_ = [nodes[i].line for i in ids]
        comps.append(Component(root=root, nodes=ids,
                               edge_count=edges_of.get(root, 0),
                               cycle_count=cycles_of.get(root, 0),
                               first_line=min(lines_), last_line=max(lines_)))
    comps.sort(key=lambda c: c.nodes[0])

    events.sort(key=lambda e: (e.line, _KIND_ORDER[e.kind], e.node))
    return SweepResult(axis=axis, conn=conn, capture=capture, nodes=nodes,
                       components=comps, events=events)


def sweep(mask: InkMask, *, axis: str = "row", conn: int = 8,
          capture: Capture = Capture.NONE,
          moments: bool = False) -> SweepResult:
    """Sweep `mask` along `axis`, returning components and scan events.

    See the module contract for G1-G7. `conn` must be 4 or 8; use 4 when
    sweeping an inverted mask for hole finding.

    `moments` (B1) asks for per-component area, moment sums and extents
    to be accumulated DURING the sweep, in `result.moments`, instead of
    by a second pass over every run. It is legal because all ten values
    are commutative monoids over the run set -- integer addition and
    min/max, associative and exact -- which is the same property
    `edges_of` and `cycles_of` already rely on. Order of runs, axis and
    merge sequence cannot change the answer.

    `moments=False` is the default and the output is field-by-field
    what it has always been: a caller that does not ask does not pay.

    STEP 1: `area`, `x0`, `y0`, `x1`, `y1` are accumulated and are
    exact. `sx`, `sy`, `sxx`, `syy`, `sxy` are STILL ZERO and arrive in
    step 2, so a caller wanting a centroid must still use
    `aggregate.moments_per_component`. Nothing in the package passes
    this keyword.
    """
    if axis not in ("row", "col"):
        raise InvalidAxis(axis)
    if conn == 8:
        slack = 1
    elif conn == 4:
        slack = 0
    else:
        raise InvalidConnectivity(conn)

    keep_graph = capture is Capture.GRAPH
    keep_events = capture in (Capture.EVENTS, Capture.GRAPH)

    uf = _UF()
    nodes: list[RunNode] = []
    events: list[Event] = []
    # per-root counters; migrated on union
    edges_of: dict[int, int] = {}
    cycles_of: dict[int, int] = {}
    # per-root moment vectors, same migration discipline as the counter
    # pair: created at BIRTH, migrated when a root moves, merged
    # elementwise when two roots union. Ten slots in `Moments` field
    # order -- area sx sy sxx syy sxy x0 y0 x1 y1 -- as ONE mutable
    # list rather than a `Moments`, which is frozen: accumulating into
    # the frozen type would allocate a new object per run, three
    # million per document. `Moments` is built once per component in
    # the assembly loop. A reviewer who "cleans this up" to the frozen
    # type makes it slower than the pass it replaces.
    moms_of: dict[int, list[int]] | None = {} if moments else None
    # Hoisted: the axis cannot change inside the sweep, and this is the
    # branch that decides whether a run's (lo, hi) is an x-extent or a
    # y-extent. Testing `axis == "row"` per run would put a string
    # comparison in the innermost loop.
    row_axis = axis == "row"

    prev: list[tuple[int, int, int]] = []   # (lo, hi, node_id), sorted by lo
    prev_line = None
    open_roots: set[int] = set()

    for line, runs in _lines(mask, axis):
        contiguous = prev_line is not None and line == prev_line + 1
        prevline = prev if contiguous else []
        kids_of: dict[int, list[int]] = {}     # prev node -> current nodes
        cur: list[tuple[int, int, int]] = []
        pi = 0
        # Hoisted: `prevline` cannot change inside this loop, and
        # `len()` in the two-pointer conditions is evaluated once per
        # advance of each pointer -- the innermost code in the package.
        nprev = len(prevline)

        for r in runs:
            nid = uf.make()
            node = RunNode(nid, r.line, r.lo, r.hi)
            nodes.append(node)

            # -- B1: this run's contribution, computed once ---------------
            # A run is a contiguous span on ONE scan line, so on a row
            # sweep it spans x from lo to hi and occupies a single y,
            # and on a column sweep exactly the reverse. This is the
            # only place the two axes differ, which is why step 1 of
            # the CR isolates it.
            if moms_of is not None:
                rn_area = r.hi - r.lo + 1
                if row_axis:
                    rx0, rx1, ry0, ry1 = r.lo, r.hi, r.line, r.line
                else:
                    rx0, rx1, ry0, ry1 = r.line, r.line, r.lo, r.hi

            # -- adjacency: two-pointer sweep over the previous line -------
            # The touching runs are the slice [pi, pj) of `prevline`.
            # Their ids are read from it by index below, so the common
            # case builds no list at all.
            while pi < nprev and prevline[pi][1] < r.lo - slack:
                pi += 1
            pj = pi
            # `adj` and `roots_before` are read ONLY by the MERGE event,
            # so neither is paid for at Capture.NONE -- the level every
            # topological caller uses, since G4 says NONE already yields
            # all counts. The scan is written out twice rather than
            # branching per step: this is the innermost code in the
            # package, and the ids are read back by index anyway.
            if keep_events:
                adj = []
                while pj < nprev and prevline[pj][0] <= r.hi + slack:
                    adj.append(prevline[pj][2])
                    pj += 1
                # roots BEFORE any union caused by this run -- a merge is
                # defined by what was distinct on arrival, not after the
                # fact.
                roots_before = tuple(sorted({uf.find(q) for q in adj}))
            else:
                adj = ()
                roots_before = ()
                while pj < nprev and prevline[pj][0] <= r.hi + slack:
                    pj += 1
            nadj = pj - pi

            # -- the case dispatch, on the number of parents ---------------
            # Measured on a synthetic page of ring glyphs, 176,000 runs:
            # 2.3% have no parent, 2.3% have more than one, and 95.5%
            # have exactly one. The middle case is the one worth naming.
            if nadj == 0:
                # BIRTH. The only place a counter pair is created: this
                # run is, and stays, its own root.
                edges_of[nid] = 0
                cycles_of[nid] = 0
                if moms_of is not None:
                    # sx sy sxx syy sxy stay 0 until step 2.
                    moms_of[nid] = [rn_area, 0, 0, 0, 0, 0,
                                    rx0, ry0, rx1, ry1]
                if keep_events:
                    events.append(Event(EventKind.BIRTH, line, nid))
            else:
                # FIRST parent. This edge can NEVER close a cycle: `nid`
                # was created this iteration and has not been unioned, so
                # its root cannot already be the parent's. So there is no
                # root comparison here, and `nid`'s counts are 0 by
                # definition rather than by lookup.
                #
                # `rn` is the root of this run's component, TRACKED from
                # here on rather than re-found -- only `union_roots` can
                # change it, and it returns the new one.
                p = prevline[pi][2]
                if keep_events:
                    kids_of.setdefault(p, []).append(nid)
                if keep_graph:
                    node.up.append(p)
                    nodes[p].down.append(nid)
                rp = uf.find(p)
                # ATTACH: `nid` joins `rp`'s component. The root stays
                # `rp` unless that component is a lone run, so the
                # counter pair usually does not move at all -- which is
                # the whole reason `attach` is named separately from
                # `union_roots`.
                rn = uf.attach(nid, rp)
                if rn == rp:
                    edges_of[rp] += 1
                    v = moms_of[rp] if moms_of is not None else None
                else:
                    edges_of[rn] = edges_of.pop(rp) + 1
                    cycles_of[rn] = cycles_of.pop(rp)
                    if moms_of is not None:
                        v = moms_of[rn] = moms_of.pop(rp)
                if moms_of is not None:
                    # `nid` brought no vector of its own -- a run that
                    # attaches is folded into an existing component
                    # here rather than starting one at BIRTH.
                    v[0] += rn_area
                    if rx0 < v[6]:
                        v[6] = rx0
                    if ry0 < v[7]:
                        v[7] = ry0
                    if rx1 > v[8]:
                        v[8] = rx1
                    if ry1 > v[9]:
                        v[9] = ry1

                # FURTHER parents. Only from here can an edge find its
                # two endpoints already in one component.
                for k in range(pi + 1, pj):
                    p = prevline[k][2]
                    if keep_events:
                        kids_of.setdefault(p, []).append(nid)
                    if keep_graph:
                        node.up.append(p)
                        nodes[p].down.append(nid)
                    rp = uf.find(p)
                    if rn == rp:
                        # both endpoints already in one component: a loop
                        # closes here, i.e. a hole is born
                        cycles_of[rn] += 1
                        edges_of[rn] += 1
                        if keep_events:
                            events.append(Event(EventKind.CYCLE, line, nid,
                                                (p,), (rp,), rn))
                    else:
                        e = edges_of.pop(rn) + edges_of.pop(rp) + 1
                        c = cycles_of.pop(rn) + cycles_of.pop(rp)
                        if moms_of is not None:
                            v = moms_of.pop(rn)
                            w = moms_of.pop(rp)
                            v[0] += w[0]
                            if w[6] < v[6]:
                                v[6] = w[6]
                            if w[7] < v[7]:
                                v[7] = w[7]
                            if w[8] > v[8]:
                                v[8] = w[8]
                            if w[9] > v[9]:
                                v[9] = w[9]
                        rn = uf.union_roots(rn, rp)
                        edges_of[rn] = e
                        cycles_of[rn] = c
                        if moms_of is not None:
                            moms_of[rn] = v

                if keep_events and len(roots_before) >= 2:
                    events.append(Event(EventKind.MERGE, line, nid,
                                        tuple(adj), roots_before, rn))

            cur.append((r.lo, r.hi, nid))

        # -- splits: a previous-line run with more than one edge down ------
        if keep_events:
            for p in sorted(kids_of):
                kids = kids_of[p]
                if len(kids) >= 2:
                    events.append(Event(EventKind.SPLIT, nodes[p].line, p,
                                        tuple(sorted(kids))))

        # -- closures ------------------------------------------------------
        # `touched` costs one find per run of the line and `open_roots`
        # is read only here and in the final-closure block, both of
        # which are event-only.
        if keep_events:
            touched = {uf.find(n) for (_, _, n) in cur}
            for r0 in sorted(open_roots):
                if uf.find(r0) not in touched:
                    events.append(Event(EventKind.CLOSE, line, r0, (),
                                        (uf.find(r0),)))
            open_roots = touched

        prev, prev_line = cur, line

    # -- final closures ----------------------------------------------------
    if keep_events and open_roots and prev_line is not None:
        for r0 in sorted(open_roots):
            events.append(Event(EventKind.CLOSE, prev_line + 1, r0, (),
                                (uf.find(r0),)))

    # -- assemble components -----------------------------------------------
    by_root: dict[int, list[int]] = {}
    for n in nodes:
        by_root.setdefault(uf.find(n.id), []).append(n.id)
    comps: list[Component] = []
    for root, ids in by_root.items():
        ids.sort()
        lines_ = [nodes[i].line for i in ids]
        comps.append(Component(root=root, nodes=ids,
                               edge_count=edges_of.get(root, 0),
                               cycle_count=cycles_of.get(root, 0),
                               first_line=min(lines_), last_line=max(lines_)))
    comps.sort(key=lambda c: c.nodes[0])

    events.sort(key=lambda e: (e.line, _KIND_ORDER[e.kind], e.node))

    moments_out = None
    if moms_of is not None:
        # Imported here, not at module scope: `aggregate` imports
        # `SweepResult` from this module, so a top-level import would
        # be circular. `moments_of_runs` does the same with `raster`.
        from .aggregate import Moments
        # Indexed, NOT `.get(root, ...)`. One vector per current root is
        # the invariant the migration maintains, and a default would
        # hand back a component of area zero -- a plausible wrong
        # answer, which is the failure mode CLAUDE.md records for
        # keying by `nodes[0]` instead of `root`.
        moments_out = {c.root: Moments(*moms_of[c.root]) for c in comps}

    return SweepResult(axis=axis, conn=conn, capture=capture, nodes=nodes,
                       components=comps, events=events,
                       moments=moments_out)


def termini(result: SweepResult) -> tuple[int, int]:
    """Runs with no neighbour on the previous line, and on the next.

    A run with an empty `up` list is a local FIRST along the sweep axis
    -- the top of a stroke on a row sweep -- and an empty `down` list a
    local LAST. `m` has three leg ends, `n` two, and `u` is `n` upside
    down, so the pair (first, last) is a cheap stroke-end count that
    (components, cycles) cannot see: all three letters are (1, 0).

    Axis names follow the sweep: on `axis="row"` the pair is
    (top, bottom); on `axis="col"` it is (left, right) -- a column
    sweep IS the transposed-mask sweep, so no transpose is needed to
    get the horizontal pair. Running both gives the 4-tuple
    (top, bottom, left, right).

    Requires `Capture.GRAPH` and raises otherwise, because at lower
    capture the adjacency lists exist and are EMPTY -- every run would
    silently count as both a first and a last, which is a wrong answer
    rather than an error.
    """
    if result.capture is not Capture.GRAPH:
        raise ValueError(
            f"termini needs Capture.GRAPH; got {result.capture.value!r} "
            f"whose empty adjacency would count every run as a terminus")
    first = sum(1 for n in result.nodes if not n.up)
    last = sum(1 for n in result.nodes if not n.down)
    return first, last
