"""The finding vocabulary shared by the compare harnesses (P19, S5).

One definition, because a flag that means different things in two
files is worse than no flag. The cuts are MEASURED, not chosen -- and
the first measurement was of the WRONG COMPARISON.

`tools/noisefloor.py` renders one page through two RASTERIZERS
(ghostscript, poppler) and gave distance p95 6, component delta max
2. That bounds rasterizer choice and nothing else. But this channel
compares a LaTeX RENDER against a SCAN of a printed page: different
typeface, different hinting, print and scan noise -- none of which a
rasterizer swap can produce. Measuring the noise of one comparison
and applying it to another is the population error this project
keeps catching, and it was mine.

The floor is now measured on the comparison it gates. pdfdrill
supplied the SELECTION -- 810 rows whose MathPix LaTeX matches the
author's LaTeX at SLT distance 0, so content agreement is guaranteed
by construction -- and this channel supplied the MEASUREMENT, its own
distance and component delta on those same rows with demoted rows
excluded (n = 804):

    distance         p50 2  p90 15  p95 23  p99 46
    component delta  p50 0  p90  1  p95  2  p99  6

Hence `NOISE_DISTANCE = 23`. The old floor of 6 falsely flagged
21.1% of content-identical rows -- one row in five. An independent
route (pdfdrill rendering the AUTHOR's LaTeX standalone at 400 dpi
rather than reading the report cell at 300) gives p95 22 on the same
selection, so two different renders converge.

`NOISE_COMP_DELTA` stays at 2: the better control CONFIRMS it, with
only 2.7% of content-identical rows above the ceiling. The channel
the findings are ranked on was the correctly calibrated one; the
distance floor was not.
"""

from __future__ import annotations

NOISE_DISTANCE = 23         # p95 of RENDER-vs-SCAN on identical content
NOISE_COMP_DELTA = 2        # p95 of the same control -- unchanged

FLAGS = ("clean", "noise", "weak", "stable", "component")


def flag_of(distance: int, comp_delta: int, scale_stable: bool,
            noise_distance: int = NOISE_DISTANCE,
            noise_comp_delta: int = NOISE_COMP_DELTA) -> str:
    """The finding class of one compared row, ordered by evidence.

    component  the component count differs by MORE than rasterizer
               noise can produce. The scale-invariant channel, 98.6%
               exact between renderers; the strongest class.
    stable     within the component band, but the disagreement is
               above the distance floor AND survives 300->600 dpi.
    weak       above the distance floor in the threshold-sensitive
               channels only, and not scale-stable.
    noise      inside both measured bands -- NOT a finding.
    clean      distance 0.

    The floors are arguments so a caller measuring its own corpus can
    pass its own numbers; the defaults are this corpus's, measured.
    """
    if distance == 0:
        return "clean"
    if comp_delta > noise_comp_delta:
        return "component"
    if distance <= noise_distance:
        return "noise"
    return "stable" if scale_stable else "weak"
