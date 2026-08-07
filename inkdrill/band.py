"""band.py — band splitting and seam stitching.

CONTRACT (written before implementation; see docs/units.md U7)
=============================================================

Why bands
---------
A page is swept in horizontal bands so U8 can hand them to separate
workers. Each band is swept independently, in its own label space, and
the results are stitched by applying U3's adjacency predicate across each
seam. The stitched result must be INDISTINGUISHABLE from a single sweep
of the whole mask -- that is the whole contract, and every other
guarantee here exists to hold it up.

One invariant does the heavy lifting
------------------------------------
**A band split never splits a run.** U2's G2 says a run never spans a
line boundary, and a band boundary IS a line boundary, so every run lies
wholly inside exactly one band. Measured on real page ink: the node count
is bit-identical from K=1 to K=64.

So V needs no repair at all. Only E, C and the cycle counts do, and they
are repaired by the seams. What the naive un-stitched split gets wrong,
measured on a real 600-row page band at K=64: 1,068 missing edges, 949
over-counted components, 119 missing cycles.

The latent bug this unit exists to avoid
----------------------------------------
docs/units.md names it: **runs and RAG nodes must be re-sorted after
concatenation.** The failure is not hypothetical arithmetic -- it is what
happens when a scheduler appends each band's result AS THE WORKER
FINISHES rather than in band order. U8 will do exactly that
("results ordered by `(page, first_line, node)` not by completion"), so
this unit must not care what order bands arrive in.

`stitch()` therefore sorts by band offset on entry and re-sorts every run
into global scan order on exit, and G3/G7 test it by shuffling the input.
A stitcher that merely concatenated would pass every in-order test and
fail in production.

Cycle counting across a seam
----------------------------
Exactly U3's rule, because it is the same situation. Each seam edge
either joins two components that were distinct on arrival -- a merge,
which lowers the component count and creates no cycle -- or joins a
component to itself, which closes a loop and raises the cycle count by
one. Union-find decides which, and roots are read BEFORE any union, so a
merge is defined by what was distinct on arrival rather than after the
fact.

Guarantees
----------
G1  node count is invariant under banding: a split never splits a run,
    so V is identical to the unbanded sweep for every K
G2  the stitched result is INDISTINGUISHABLE from a single sweep --
    same component partition, same V, E, C and cycle counts -- for every
    K, including a blob that crosses every seam
G3  runs and nodes come out sorted by `(line, lo)`, whatever order the
    bands were supplied in; this is the latent bug named above
G4  the cycle-rank identity `cycles == E - V + C` survives stitching,
    per component and in total
G5  moment aggregates add across bands, exactly, using U5's algebra
G6  seam adjacency uses U3's predicate unchanged, at the same
    connectivity, so nothing crossing a seam is treated specially
G7  stitching is order-independent: shuffling the band list changes
    nothing about the result

Non-guarantees (out of scope for U7)
------------------------------------
  * **scan events are NOT stitched.** A band boundary manufactures
    spurious births at its top and closes at its bottom, and repairing
    that needs the bounded-memory closure stream, which is a later unit.
    `stitch()` returns an empty event list and says so rather than
    returning events that look right and are not.
  * no scheduling, no processes, no shared memory -- that is U8
  * bands are horizontal only; a column-axis sweep of a banded mask is
    not the same computation and is refused
"""

from __future__ import annotations

from dataclasses import dataclass

from .raster import InkMask, Run
from .sweep import (Capture, Component, InvalidConnectivity, RunNode,
                    SweepResult, sweep)

__all__ = ["Band", "split", "sweep_bands", "stitch", "sweep_banded",
           "InvalidBandCount"]


class InvalidBandCount(ValueError):
    """k must be at least 1 and at most the mask height."""


@dataclass(slots=True)
class Band:
    """One band's sweep, plus where it sits in the whole mask."""
    y0: int                 # global line of this band's first row
    height: int
    result: SweepResult

    @property
    def y1(self) -> int:
        """One past the last global line."""
        return self.y0 + self.height


def split(mask: InkMask, k: int) -> list[tuple[int, InkMask]]:
    """Cut a mask into k horizontal bands as (y0, band) pairs.

    Cuts fall on line boundaries, so no run is ever split (G1). Bands
    differ in height by at most one row.
    """
    if k < 1 or k > max(1, mask.height):
        raise InvalidBandCount(
            f"k={k} outside 1..{max(1, mask.height)} for a mask of height "
            f"{mask.height}")
    w, h = mask.width, mask.height
    out = []
    base, extra = divmod(h, k)
    y = 0
    for i in range(k):
        rows = base + (1 if i < extra else 0)
        if rows == 0:
            continue
        out.append((y, InkMask(mask.data[y * w:(y + rows) * w], w, rows)))
        y += rows
    return out


def sweep_bands(mask: InkMask, k: int, *, conn: int = 8) -> list[Band]:
    """Split and sweep each band independently, in its own label space."""
    return [Band(y0, sub.height,
                 sweep(sub, axis="row", conn=conn, capture=Capture.GRAPH))
            for y0, sub in split(mask, k)]


class _UF:
    __slots__ = ("parent", "size")

    def __init__(self, n: int) -> None:
        self.parent = list(range(n))
        self.size = [1] * n

    def find(self, i: int) -> int:
        p = self.parent
        while p[i] != i:
            p[i] = p[p[i]]
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


def stitch(bands: list[Band], *, conn: int = 8) -> SweepResult:
    """Merge independently swept bands into one result.

    The band list may arrive in ANY order -- it is sorted on entry. See
    the module docstring on why that is the point rather than a
    politeness.
    """
    if conn not in (4, 8):
        raise InvalidConnectivity(conn)
    if not bands:
        return SweepResult("row", conn, Capture.GRAPH, [], [], [])

    ordered = sorted(bands, key=lambda b: b.y0)
    slack = 1 if conn == 8 else 0

    # ---- concatenate, lifting every run into global coordinates -------
    nodes: list[RunNode] = []
    owner: list[int] = []            # new node id -> band index
    local_to_global: list[dict[int, int]] = []
    for bi, band in enumerate(ordered):
        mapping: dict[int, int] = {}
        for n in band.result.nodes:
            gid = len(nodes)
            mapping[n.id] = gid
            nodes.append(RunNode(gid, n.line + band.y0, n.lo, n.hi))
            owner.append(bi)
        local_to_global.append(mapping)

    # G3: global scan order, whatever order the bands arrived in.
    order = sorted(range(len(nodes)),
                   key=lambda i: (nodes[i].line, nodes[i].lo))
    renumber = {old: new for new, old in enumerate(order)}
    nodes = [RunNode(renumber[nodes[i].id], nodes[i].line,
                     nodes[i].lo, nodes[i].hi) for i in order]
    owner = [owner[i] for i in order]

    # ---- carry the within-band adjacency across, renumbered ----------
    for bi, band in enumerate(ordered):
        mapping = local_to_global[bi]
        for n in band.result.nodes:
            a = renumber[mapping[n.id]]
            for d in n.down:
                b = renumber[mapping[d]]
                nodes[a].down.append(b)
                nodes[b].up.append(a)

    # ---- component bookkeeping, one slot per band-component ----------
    comp_slot: dict[tuple[int, int], int] = {}
    slot_cycles: list[int] = []
    slot_edges: list[int] = []
    for bi, band in enumerate(ordered):
        for c in band.result.components:
            comp_slot[(bi, c.root)] = len(slot_cycles)
            slot_cycles.append(c.cycle_count)
            slot_edges.append(c.edge_count)
    uf = _UF(len(slot_cycles))

    slot_of_node: list[int] = [0] * len(nodes)
    for bi, band in enumerate(ordered):
        mapping = local_to_global[bi]
        for c in band.result.components:
            s = comp_slot[(bi, c.root)]
            for nid in c.nodes:
                slot_of_node[renumber[mapping[nid]]] = s

    # ---- seam edges, using U3's predicate unchanged (G6) -------------
    by_line: dict[int, list[int]] = {}
    for n in nodes:
        by_line.setdefault(n.line, []).append(n.id)

    seam_edges = 0
    for bi in range(len(ordered) - 1):
        seam = ordered[bi + 1].y0
        above = by_line.get(seam - 1, [])
        below = by_line.get(seam, [])
        if not above or not below:
            continue
        for a in above:
            na = nodes[a]
            for b in below:
                nb = nodes[b]
                if na.hi >= nb.lo - slack and na.lo <= nb.hi + slack:
                    nodes[a].down.append(b)
                    nodes[b].up.append(a)
                    seam_edges += 1
                    ra = uf.find(slot_of_node[a])
                    rb = uf.find(slot_of_node[b])
                    if ra == rb:
                        slot_cycles[ra] += 1        # a loop closed
                    else:
                        r = uf.union(ra, rb)
                        slot_cycles[r] = slot_cycles[ra] + slot_cycles[rb]
                        slot_edges[r] = slot_edges[ra] + slot_edges[rb]
                    root = uf.find(ra)
                    slot_edges[root] += 1

    for n in nodes:
        n.up.sort()
        n.down.sort()

    # ---- rebuild components, keyed by lowest node id (U3's G5) -------
    members: dict[int, list[int]] = {}
    for n in nodes:
        members.setdefault(uf.find(slot_of_node[n.id]), []).append(n.id)

    components: list[Component] = []
    for root_slot, ids in members.items():
        ids.sort()
        lines = [nodes[i].line for i in ids]
        components.append(Component(
            root=ids[0], nodes=ids,
            edge_count=slot_edges[root_slot],
            cycle_count=slot_cycles[root_slot],
            first_line=min(lines), last_line=max(lines)))
    components.sort(key=lambda c: c.root)

    return SweepResult("row", conn, Capture.GRAPH, nodes, components, [])


def sweep_banded(mask: InkMask, k: int, *, conn: int = 8) -> SweepResult:
    """Split, sweep and stitch. G2: indistinguishable from `sweep()`."""
    return stitch(sweep_bands(mask, k, conn=conn), conn=conn)


def canonical(result: SweepResult) -> tuple:
    """A label-free form for comparing two sweeps of the same mask.

    Node ids and component roots depend on how the work was divided, so
    they cannot be compared directly; the pixel sets and the counts can.
    """
    by_id = {n.id: n for n in result.nodes}
    comps = []
    for c in result.components:
        runs = tuple(sorted((by_id[i].line, by_id[i].lo, by_id[i].hi)
                            for i in c.nodes))
        comps.append((runs, c.edge_count, c.cycle_count,
                      c.first_line, c.last_line))
    comps.sort()
    return (result.node_count, result.edge_count, result.cycle_count,
            result.component_count, tuple(comps))
