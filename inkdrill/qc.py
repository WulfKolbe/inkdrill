"""qc.py -- what a mask says about how it was made.

CONTRACT (written before implementation; see docs/units.md)
==========================================================

Two checks that share an input and nothing else: whether a region is a
halftone SCREEN, and whether a transform preserved a page's TOPOLOGY.
Both read a mask and neither modifies one.

Why not `cycle_count` for the screen (the whole point)
------------------------------------------------------
The obvious detector is "many holes means a mesh". It is **blind in
highlights**, measured on a 600 dpi / 150 lpi synthetic screen:

    tone   max cycle_count      a cycles gate fires?
    0.05                 0      no -- missed
    0.15                 0      no -- missed
    0.25                 0      no -- missed
    0.35                 1      no -- missed
    0.50               242      yes
    0.65             9,445      yes

Below about half tone the dots do not touch, so there is no mesh and no
cycle at all. A pale screened region -- sky, paper stock, a light tint
-- reports "not a halftone", and that is more than half the tone range.

**Runs per unit area is tone-independent**, an order of magnitude away
from both text and photographs, and available from `iter_runs` before a
sweep runs:

    body text                     0.0085 runs/px
    photo mosaic                  0.0097
    halftone, tone 0.05-0.80      0.05 - 0.20

`cycle_count` is kept as a SECOND channel because it is genuine evidence
at midtone and above, and a conjunction of two independent signals is
the shape that has worked elsewhere here. It must not be the gate.

TAU is an argument, and has no default
--------------------------------------
The thresholds above come from a SYNTHETIC screen. A real one is
resampled and JPEG'd, so its lattice is smeared, and no threshold
measured on a generated screen should be frozen into this module before
it has been checked against printed pages. `screen_signals` therefore
returns the numbers and classifies nothing; the caller supplies the
cut, and `docs/units.md` records what population any published cut was
measured over.

The denominator is part of the number
-------------------------------------
`runs_per_area` over a whole PAGE and over one COMPONENT are different
quantities and differ by about 8x: measured on real pages, glyph
components read 0.071 runs per component-bbox pixel, which sits inside
the 0.05-0.20 band quoted for a screen per PAGE pixel. A cut calibrated
on one denominator and applied to the other calls every letter a
halftone. Both are offered, named, and never mixed.

Guarantees
----------
G1  pure -- a mask in, numbers out; nothing is modified and no file is
    read
G2  `runs_per_area` counts maximal runs on ONE axis, so it is a property
    of the ink and not of the sweep's capture level
G3  `screen_signals` classifies nothing; it returns measurements and the
    caller applies a cut
G4  `topology_preserved` compares component AND cycle counts, exactly --
    a transform that changes either has changed the page
G5  an empty mask is answered, not raised: no runs, no components, and
    two empty masks are trivially topology-preserving
"""

from __future__ import annotations

from dataclasses import dataclass

from .raster import InkMask, iter_runs
from .sweep import Capture, sweep

__all__ = ["ScreenSignals", "runs_per_area", "px_per_run", "screen_signals",
           "topology_preserved", "topology_of"]


@dataclass(frozen=True, slots=True)
class ScreenSignals:
    """Measurements, not a verdict (G3)."""
    runs: int
    ink_px: int
    area_px: int
    cycles: int
    components: int

    @property
    def runs_per_area(self) -> float:
        """Runs per pixel of the region's extent -- the tone-independent
        channel. Zero for an empty region."""
        return self.runs / self.area_px if self.area_px else 0.0

    @property
    def px_per_run(self) -> float:
        """Mean run length. About 1-6 for a screen, ~33 for a photo, so
        it separates a dot lattice from a smooth tone."""
        return self.ink_px / self.runs if self.runs else 0.0

    @property
    def cycles_per_area(self) -> float:
        """The SECOND channel. Real evidence at midtone and above, and
        exactly zero below about half tone -- see the module contract."""
        return self.cycles / self.area_px if self.area_px else 0.0


def runs_per_area(mask: InkMask, axis: str = "row") -> float:
    """Maximal ink runs per pixel of the mask's extent (G2).

    Counted from `iter_runs` directly, so this is available BEFORE a
    sweep and costs one pass.
    """
    n = mask.width * mask.height
    if n == 0:
        return 0.0
    return sum(1 for _ in iter_runs(mask, axis)) / n


def px_per_run(mask: InkMask, axis: str = "row") -> float:
    """Mean run length in pixels; 0.0 when there is no ink."""
    runs = ink = 0
    for r in iter_runs(mask, axis):
        runs += 1
        ink += r.hi - r.lo + 1
    return ink / runs if runs else 0.0


def screen_signals(mask: InkMask, *, axis: str = "row",
                   result=None) -> ScreenSignals:
    """Every channel at once, from one sweep (G1, G3).

    `result` accepts a `SweepResult` the caller already has, so this
    never sweeps a page twice.
    """
    runs = ink = 0
    for r in iter_runs(mask, axis):
        runs += 1
        ink += r.hi - r.lo + 1
    res = result if result is not None else sweep(
        mask, axis=axis, conn=8, capture=Capture.GRAPH)
    return ScreenSignals(
        runs=runs, ink_px=ink, area_px=mask.width * mask.height,
        cycles=sum(c.cycle_count for c in res.components),
        components=len(res.components))


def topology_of(mask: InkMask, *, conn: int = 8) -> tuple[int, int]:
    """`(components, cycles)` -- the pair a transform must not change."""
    res = sweep(mask, conn=conn, capture=Capture.GRAPH)
    return (len(res.components),
            sum(c.cycle_count for c in res.components))


def topology_preserved(before: InkMask, after: InkMask, *,
                       conn: int = 8) -> bool:
    """Did a transform leave the page's topology alone? (G4, G5)

    Both counts, exactly. Measured, this is tight enough to catch
    resampling damage -- a 2 degree rotate-and-rebin breaks it -- and
    loose enough not to fire on differences that do not matter: the same
    page through `png16m` and `pgmraw` passes (910/1011 either way,
    despite 259 differing pixels), as does a threshold nudge of +/-2.

    That combination is what makes it a usable acceptance gate rather
    than a checksum.
    """
    return topology_of(before, conn=conn) == topology_of(after, conn=conn)
