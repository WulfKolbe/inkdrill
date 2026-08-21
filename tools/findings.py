"""The finding vocabulary shared by the compare harnesses (P19, S5).

One definition, because a flag that means different things in two
files is worse than no flag. The cuts are MEASURED, and the history
of getting them wrong is kept because each error had a different
shape.

**6** came from `tools/noisefloor.py`: one page through two
RASTERIZERS. That bounds rasterizer choice, and this channel
compares a LaTeX RENDER against a SCAN -- different typeface,
different hinting, print and scan noise. Right method, wrong
comparison.

**23** came from re-measuring on 1,484 rows selected as SLT-distance
zero, i.e. content identical by construction. It survived a doubled
sample and an independent render route (22). It was still wrong,
because the SELECTION was broken: pdfdrill's SLT parser collapses
`\begin{aligned}` to a single UNRESOLVED node, so two multi-line
equations with different content compared EQUAL. 45% of the
"content-identical" rows were nothing of the kind -- on
1408.0838_EQ0011 MathPix had dropped three summations and a whole
line, and the metric called it a perfect match.

**7** is the p95 over the 813 rows of that selection carrying no
multi-line or array environment -- the part where content really is
identical. Split independently of pdfdrill's fix, by testing each
row's latex here rather than trusting their column. Their published
`degenerate` flag is a strict SUBSET of this filter: 664 rows, all
of which this side also flags, against 677 here. The 13 extra are
`matrix`/`pmatrix`/`cases` blocks their parser may handle and this
filter refuses; keeping the stricter filter puts the floor at 7
rather than the 8 their column gives. One unit, and the more
conservative one is the one that does not hide findings.

    genuine     n=813   distance p50 1  p95  7   comp delta p95 1
    degenerate  n=671   distance p50 7  p95 30   comp delta p95 4

False-positive rate on the genuine control:

    distance floor  6 -> 5.4%     component ceiling 1 -> 2.6%
    distance floor  7 -> 4.7%     component ceiling 2 -> 1.6%
    distance floor 23 -> 1.0%     component ceiling 3 -> 1.2%

So the original 6 was right to within one unit, and 23 would have
thrown real findings away -- worse than the false positives it was
adopted to prevent, because it hides defects instead of inventing
them. `NOISE_COMP_DELTA` stays 2: on the clean control it costs
1.6%, and the earlier alarm at 5.7% was the same degenerate rows.

The lesson is not "measure the floor" -- I did that three times.
It is that a control group is only as good as the rule that built
it, and "content is identical" was an assumption inherited from
another tool's metric rather than a property this channel checked.
"""

from __future__ import annotations

NOISE_DISTANCE = 7          # p95 of RENDER-vs-SCAN, GENUINELY identical
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
