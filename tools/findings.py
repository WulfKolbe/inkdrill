"""The finding vocabulary shared by the compare harnesses (P19, S5).

One definition, because a flag that means different things in two
files is worse than no flag. The cuts are MEASURED, not chosen:
`tools/noisefloor.py` renders the same 208 expressions at the same dpi
through two rasterizers (ghostscript and poppler), so every distance
between them is instrument noise:

    distance        zero 79/208, median 1, p95 6, max 19
    component delta zero 205/208 (98.6%), max 2

Hence `NOISE_DISTANCE = 6` (the p95 of pure noise) and
`NOISE_COMP_DELTA = 2` (its measured ceiling). A row inside both
bands is not a finding, and saying so is the whole point: before this
measurement the harness reported 2,313 rows at distance 1-5 that it
could not distinguish from a change of rasterizer.
"""

from __future__ import annotations

NOISE_DISTANCE = 6          # p95 of ghostscript-vs-poppler distance
NOISE_COMP_DELTA = 2        # its measured maximum

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
