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

FLAGS = ("absent", "clean", "noise", "weak", "stable", "component")

# `absent` is NEW and it is a sixth value in a vocabulary two other
# sessions consume: pdfdrill-7b's refine metric and the
# pdfdrill.github.io deploy gate, whose legend defines these names
# once for a published table. The gate is built to FAIL BY NAME on an
# unknown flag rather than render it, which is the outcome both sides
# asked for -- see HANDOVER, "Two sessions consume this project's
# output format". The legend needs the new row in the same change.


def flag_of(distance: int, comp_delta: int, scale_stable: bool,
            noise_distance: int = NOISE_DISTANCE,
            noise_comp_delta: int = NOISE_COMP_DELTA,
            empty: bool = False) -> str:
    """The finding class of one compared row, ordered by evidence.

    absent     NEITHER cell has ink. Not a comparison at all, and
               distinguished from `clean` because both score 0.
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
    # ABSENT BEFORE CLEAN, and the order is the whole point. A row
    # with no ink on either side scores distance 0 and comp_delta 0 --
    # arithmetically a perfect match, from a comparison that did not
    # happen. Reading it as `clean` reports an absence as the best
    # possible result, which is the shape this project has now been
    # caught by three times. One predicate separates them: `empty` is
    # true when NEITHER side has ink, and it is decided by the caller
    # that holds the two five-tuples.
    if empty:
        return "absent"
    if distance == 0:
        return "clean"
    if comp_delta > noise_comp_delta:
        return "component"
    if distance <= noise_distance:
        return "noise"
    return "stable" if scale_stable else "weak"
