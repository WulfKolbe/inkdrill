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
    axis: str
    conn: int
    capture: Capture
    nodes: list[RunNode]
    components: list[Component]
    events: list[Event]

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
        for c in self.components:
            if node_id in c.nodes:
                return c
        raise KeyError(node_id)


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
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return ra
        if self.size[ra] < self.size[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.size[ra] += self.size[rb]
        return ra


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


def sweep(mask: InkMask, *, axis: str = "row", conn: int = 8,
          capture: Capture = Capture.NONE) -> SweepResult:
    """Sweep `mask` along `axis`, returning components and scan events.

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

        for r in runs:
            nid = uf.make()
            node = RunNode(nid, r.line, r.lo, r.hi)
            nodes.append(node)
            edges_of[nid] = 0
            cycles_of[nid] = 0

            # -- adjacency: two-pointer sweep over the previous line -------
            adj: list[int] = []
            while pi < len(prevline) and prevline[pi][1] < r.lo - slack:
                pi += 1
            pj = pi
            while pj < len(prevline) and prevline[pj][0] <= r.hi + slack:
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
