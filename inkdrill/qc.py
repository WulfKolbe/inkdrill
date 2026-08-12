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

    real corpus pages, 40 of them, threshold 200:
    min 0.0000   median 0.0067   MAX 0.0153

`cycle_count` is kept as a SECOND channel because it is genuine evidence
at midtone and above, and a conjunction of two independent signals is
the shape that has worked elsewhere here. It must not be the gate.

The margin is 3x, not 10x, and px/run does not close it
-------------------------------------------------------
The bands above are synthetic. Measured over 40 real corpus pages at
threshold 200, runs-per-area spans **0.0000 to 0.0153**, median 0.0067,
the densest being a page of dense typeset mathematics. Against the
lightest synthetic screen at 0.0469 that is **3.1x of headroom** -- not
the order of magnitude the synthetic figures suggest.

And **`px/run` overlaps**. Real pages span 4.1 to 217.4, and the five
densest sit at **4.1 to 5.3** -- inside a screen's 1.0-6.2. So px/run
separates a screen from a PHOTOGRAPH (217 against 6) and does NOT
separate a screen from dense text. Quoting it as a second discriminator
without that qualifier overstates it; the conjunction that works is
runs-per-area with cycles, and px/run only excludes smooth tone.

Any TAU must therefore be validated against the densest real page
available, not against a comfortable one, and 3.1x is the margin it has
to live inside.

A third channel, reported and NOT a separator
---------------------------------------------
`run_length_cv` was proposed on the reasoning that a screen is a regular
lattice, so its runs are near-constant, against CV 8.4-9.5 for real
text -- a 21x separation on exactly the pair `runs_per_area` and
`px/run` overlap.

**Measured here, it does not reproduce.** CV over every run of a page:

    light synthetic screen      0.566 - 0.576
    REAL corpus pages           min 0.603, median 0.753, max 10.19

The lightest screen and the least-varied real page are **6% apart**, not
21x. The published figures are presumably a different denominator --
per component, or over a selected run set -- and on this one there is no
separation to use.

It is computed because it is one pass over runs already enumerated and
costs nothing, and it is REPORTED rather than used. Nothing in this
module claims it discriminates.

One direction worth noting, because it is the opposite of the proposal's
intuition: a denser screen has MORE varied runs, not fewer -- as dots
merge, lengths spread. CV rises from 0.57 to 2.7 between a highlight and
a shadow lattice.

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
    caller applies a cut. Three channels, and no one of them separates
    all three of screen/text/photo alone
G4  `topology_preserved` compares component AND cycle counts, exactly --
    a transform that changes either has changed the page.
    `topology_within` is the same check at a stated tolerance, for
    inputs where exact equality cannot hold; its `tol` has no default
G5  an empty mask is answered, not raised: no runs, no components, and
    two empty masks are trivially topology-preserving
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .raster import InkMask, iter_runs
from .sweep import Capture, sweep

__all__ = ["ScreenSignals", "runs_per_area", "px_per_run", "screen_signals",
           "topology_preserved", "topology_of", "topology_within"]


@dataclass(frozen=True, slots=True)
class ScreenSignals:
    """Measurements, not a verdict (G3)."""
    runs: int
    ink_px: int
    area_px: int
    cycles: int
    components: int
    run_len_sq: int = 0

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
    def run_length_cv(self) -> float:
        """Coefficient of variation of run LENGTH -- the third channel.

        A screen is a regular lattice, so its runs are near-uniform; text
        is not, so its runs vary wildly. This is the signal that
        separates the pair the other two do not: the densest real page
        measured sits 3.1x from a screen on `runs_per_area` and **21x**
        on this.

            screen tone 0.05    CV 0.045
            screen tone 0.50    CV 0.298
            screen tone 0.80    CV 3.188
            photo mosaic        CV 2.639
            arXiv text          CV 8.398
            dense vector page   CV 9.499

        Zero when there are no runs, and zero for a perfectly uniform
        lattice -- which is the correct answer, not a missing one.
        """
        if self.runs == 0:
            return 0.0
        mean = self.ink_px / self.runs
        if mean <= 0.0:
            return 0.0
        var = self.run_len_sq / self.runs - mean * mean
        return math.sqrt(var) / mean if var > 0.0 else 0.0

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
    runs = ink = sq = 0
    for r in iter_runs(mask, axis):
        n = r.hi - r.lo + 1
        runs += 1
        ink += n
        sq += n * n
    res = result if result is not None else sweep(
        mask, axis=axis, conn=8, capture=Capture.GRAPH)
    return ScreenSignals(
        runs=runs, ink_px=ink, area_px=mask.width * mask.height,
        cycles=sum(c.cycle_count for c in res.components),
        components=len(res.components), run_len_sq=sq)


def topology_of(mask: InkMask, *, conn: int = 8) -> tuple[int, int]:
    """`(components, cycles)` -- the pair a transform must not change."""
    res = sweep(mask, conn=conn, capture=Capture.GRAPH)
    return (len(res.components),
            sum(c.cycle_count for c in res.components))


def topology_within(before: InkMask, after: InkMask, *, tol: float,
                    conn: int = 8) -> bool:
    """A TOLERANCE gate, for inputs where exact equality cannot hold.

    `topology_preserved` demands exact counts, which works on rendered
    pages -- 0% drift across thresholds 128 to 240 -- and fails on every
    scan tried, because a scan's greys are continuous and a nudge moves
    boundary pixels.

    Measured on DocReal flatbed scans, both counts as a relative change:

        baseline, same page at threshold +/-2    median 6.0%, MAX 11.9%
        floor, distorted page with no dewarp     median 95.6%, max 1158%

    **16x apart**, so a tolerance separates them where equality cannot.

    `tol` has no default, deliberately. It is the whole content of the
    gate, it must be justified against the WORST page rather than the
    median -- 11.9% against 6.0% on that sample, and half the pages
    violate the median -- and it must be declared before a dewarp result
    is seen or it gets fitted to one.

    Caveat, and it may shrink these numbers: those figures come from
    binarising at 128, which is NOT in the histogram valley. Measured,
    DocReal's scans peak at ink ~70 and paper 255 with the valley at
    **165-186**, so 128 sits on the ink-side shoulder where mass is
    still falling. A gate calibrated at the valley would see less drift.
    """
    if tol < 0.0:
        raise ValueError(f"tol must be non-negative, got {tol}")
    a = topology_of(before, conn=conn)
    b = topology_of(after, conn=conn)
    for x, y in zip(a, b):
        # Provably redundant: with both zero the test reads 0 > 0, which
        # is already False. Kept for intent -- "no counts, nothing to
        # compare" -- and recorded so a sweep does not re-raise it.
        if x == 0 and y == 0:
            continue
        if abs(x - y) > tol * max(abs(x), abs(y)):
            return False
    return True


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
