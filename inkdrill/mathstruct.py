"""mathstruct.py — rows, reference lines, and script detection.

CONTRACT (written before implementation; see docs/units.md U14)
==============================================================

What this unit is, and what it is not
-------------------------------------
The plan asks for five things: reference-line estimation per row,
sub/superscript from geometry, big operators and their ranges, fence
matching, and a structure tree exported as LaTeX.

**The first two are built. The last three are not**, and the reason is
the same in each case: they need a reliable symbol identity for `sum`,
`integral`, `(`, `[`, and U13's measurement says that identity is not
available yet for the population that matters. U13 reached 94% within a
document and 61.5% across fonts, and its measured population contained
**no mathematics symbols at all** -- the class filter excluded every one
of them as too rare. Fence matching built on a classifier that has never
been measured on a fence would be a structure tree resting on nothing.

So this unit delivers the geometry, which is measurable now, and names
the rest.

Component grouping comes first, because U13 needs it
-----------------------------------------------------
U13's confusion matrix at 94% contained one dominant family: `i . : 1 l`
-- multi-component glyphs of which a per-component classifier sees half.
U4 and U10 hit the same thing from their own directions. `group()` joins
components that share a column span and sit within a line, which is what
turns a dot and a stem back into an `i` before anything tries to name it.

Script detection is high precision and unknown recall
------------------------------------------------------
Measured on 37,759 glyphs over 12 pages, against a label taken from
pdfminer's `size` -- the PDF's own font metric, which the geometry side
never sees, so the test is not circular:

        precision  100.0%     (0 false positives in 37,759)
        recall      13.5%
        positives    2.04% of the population

**The precision figure is trustworthy and the recall figure is not.**
When the geometry says "script", the font metric agreed every single
time. But the label is a proxy: "smaller than the row's modal size"
catches any smaller-font run -- captions, footnote text, a mixed-size
heading -- not only sub- and superscripts. So most of the 667 misses are
probably not scripts at all, and 13.5% is a lower bound on recall against
an over-inclusive label rather than a measurement of missed scripts.

`units.md` specified "against pdfminer's `role` as label". **There is no
`role` field in the corpus's `chars.json`.** Until a real label exists,
`detect_scripts` is documented as a high-precision detector and not as a
classifier, and `Script.confident` exists so a caller can use it that
way.

Guarantees
----------
G1  `rows()` partitions its input: every glyph lands in exactly one row,
    none dropped or duplicated
G2  row assignment is deterministic and independent of input order
G3  reference lines are estimated from the ink's modal extremes, not its
    mean, so one descender or one tall bracket cannot drag a baseline
G4  `detect_scripts` requires BOTH a height reduction and a vertical
    offset; either alone is not evidence, which is what makes it
    high-precision
G5  script detection is relative to its own row, so a page with two body
    sizes does not report one of them as scripts throughout
G6  `group()` joins only STACKED components -- horizontal overlap plus
    vertical separation. Horizontal overlap alone merges a narrow letter
    sitting inside a wide one
G7  every threshold is a named argument with its measured default, not a
    literal buried in a comparison

Non-guarantees (out of scope for U14 as built)
----------------------------------------------
  * **no big-operator ranges, no fence matching, no structure tree, no
    LaTeX.** All need symbol identity that U13 has not been measured to
    provide for maths -- see above. Building them now would be
    unfalsifiable.
  * no reading order across columns
  * no baseline for rotated or curved text; `rows()` assumes horizontal
    lines, which is what a deskewed page gives
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Sequence

__all__ = ["Glyph", "Row", "ReferenceLines", "Script", "ScriptKind",
           "rows", "reference_lines", "detect_scripts", "group",
           "pair_stats", "pair_counts", "region_overrun"]


@dataclass(frozen=True, slots=True)
class Glyph:
    """One ink component in page space, y growing DOWNWARD."""
    id: int
    x0: float
    top: float
    x1: float
    bottom: float

    @property
    def height(self) -> float:
        return self.bottom - self.top

    @property
    def width(self) -> float:
        return self.x1 - self.x0


@dataclass(slots=True)
class Row:
    """One text line."""
    members: list[Glyph]
    top: float
    bottom: float

    @property
    def height(self) -> float:
        return self.bottom - self.top

    def sorted_members(self) -> list[Glyph]:
        return sorted(self.members, key=lambda g: (g.x0, g.id))


@dataclass(frozen=True, slots=True)
class ReferenceLines:
    """Estimated from the ink's MODAL extremes, not its mean (G3).

    A mean baseline is dragged down by every descender and up by nothing;
    a single tall bracket moves it further still. The mode is what the
    majority of the row actually sits on.
    """
    baseline: float
    x_height: float
    top: float

    @property
    def body_height(self) -> float:
        return self.baseline - self.top


class ScriptKind:
    SUPER = "superscript"
    SUB = "subscript"


@dataclass(frozen=True, slots=True)
class Script:
    glyph_id: int
    kind: str
    offset: float
    height_ratio: float

    @property
    def confident(self) -> bool:
        """Both signals well clear of their thresholds.

        Exists because the measurement supports a DETECTOR and not a
        classifier: precision was 100% and recall is not interpretable
        against the available label.
        """
        return self.height_ratio < 0.7 and abs(self.offset) > 0.35


def rows(glyphs: Iterable[Glyph], *, overlap: float = 0.4) -> list[Row]:
    r"""Group glyphs into text lines by vertical overlap.

    A glyph joins a row when it shares more than `overlap` of ITS OWN
    height with the row -- not of the smaller of the two heights.

    That distinction is not cosmetic. A superscript is short and sits
    high, so it overlaps a body line by only a third of the line's
    height; a rule measured against the line excludes exactly the glyphs
    this unit exists to find, and `detect_scripts` would then never see
    them. Measured against the glyph's own height, a superscript joins
    and a genuinely separate line still does not.

    Glyphs are considered NEAREST THE MODAL HEIGHT FIRST, so body text
    seeds the rows and everything else joins them.

    Two failures shaped this rule. Processing in READING ORDER lets a
    superscript -- which sits higher than the line it belongs to -- open a
    row of its own before that line exists. Processing TALLEST FIRST fixes
    that and introduces a worse one: a 50 px `\left\{` spanning three
    body lines seeds before any of them, opens a row across the whole
    span, and every body glyph's own-height overlap then clears the
    threshold -- three lines collapse into one. Measured: `[8, 8, 8]`
    becomes `[25]`.

    "Tallest first" is not "body text first". The modal height is.
    Neither failure is caught by a determinism test, because both wrong
    answers were perfectly deterministic.

    G1: every glyph lands in exactly one row. G2: deterministic, because
    the order is fully specified by the sort key.
    """
    if not 0.0 < overlap < 1.0:
        raise ValueError(f"overlap must be in (0, 1), got {overlap}")
    items = list(glyphs)
    if not items:
        return []
    modal_h = _mode([g.height for g in items])
    out: list[Row] = []
    for g in sorted(items, key=lambda g: (abs(g.height - modal_h),
                                          g.top, g.x0, g.id)):
        for r in out:
            share = min(r.bottom, g.bottom) - max(r.top, g.top)
            if share > overlap * (g.height or 1.0):
                r.members.append(g)
                r.top = min(r.top, g.top)
                r.bottom = max(r.bottom, g.bottom)
                break
        else:
            out.append(Row([g], g.top, g.bottom))
    out.sort(key=lambda r: (r.top, r.bottom))
    return out


def _mode(values: Sequence[float], quantum: float = 1.0) -> float:
    """Modal value, rounded to `quantum`. Falls back to the median when
    every value is distinct, so a row of 3 glyphs still gets an answer."""
    if not values:
        return 0.0
    counts = Counter(round(v / quantum) * quantum for v in values)
    top, n = counts.most_common(1)[0]
    if n > 1:
        return top
    return sorted(values)[len(values) // 2]


def reference_lines(row: Row, *, quantum: float = 1.0) -> ReferenceLines:
    """Baseline, x-height and top for one row, from modal extremes (G3)."""
    if not row.members:
        raise ValueError("cannot estimate reference lines for an empty row")
    baseline = _mode([g.bottom for g in row.members], quantum)
    top = _mode([g.top for g in row.members], quantum)
    heights = sorted(g.height for g in row.members)
    return ReferenceLines(baseline, heights[len(heights) // 2], top)


def detect_scripts(row: Row, *, max_height_ratio: float = 0.80,
                   min_offset: float = 0.25,
                   quantum: float = 1.0) -> list[Script]:
    """Sub- and superscripts in one row, from geometry alone.

    Requires BOTH a height reduction and a vertical offset (G4). Either
    alone is not evidence: a small glyph on the baseline is a comma, and
    a full-height glyph raised slightly is a rendering artefact. Demanding
    both is what produced 0 false positives in 37,759 glyphs.

    Thresholds are the measured defaults and are named arguments (G7).
    Everything is relative to this row (G5), so a page carrying two body
    sizes does not report one of them as scripts throughout.
    """
    ref = reference_lines(row, quantum=quantum)
    xh = ref.x_height or 1.0
    out: list[Script] = []
    for g in row.sorted_members():
        ratio = g.height / xh
        if ratio >= max_height_ratio:
            continue
        rise = (ref.baseline - g.bottom) / xh
        if rise > min_offset:
            out.append(Script(g.id, ScriptKind.SUPER, rise, ratio))
        elif -rise > min_offset:
            out.append(Script(g.id, ScriptKind.SUB, rise, ratio))
    return out


_partition_rows = rows          # `group` takes a `rows=` argument, which
                                # would otherwise shadow the function it
                                # needs when the argument is omitted.


def group(glyphs: Sequence[Glyph], *, share: float = 0.5,
          max_gap: float = 2.5, stack: float = 0.5,
          rows: Sequence["Row"] | None = None) -> list[list[int]]:
    r"""Join components that belong to one glyph -- `i`, `j`, `:`, `=`.

    U13's confusion matrix is dominated by these: a per-component
    classifier sees a dot or a stem and names it `.` or `l`.

    Two components join when all three hold:
      * their horizontal spans overlap by more than `share` of the
        narrower one;
      * they are STACKED -- their vertical spans overlap by less than
        `stack` of the shorter one;
      * the vertical gap between them is under `max_gap` times the taller
        one's height.

    G7: **components in DIFFERENT ROWS are never joined**, and without
    that bound the three tests above are not enough. Measured on a
    600 dpi scan: `max_gap=2.5` on a 43 px glyph permits a 108 px
    vertical gap, and body leading on that page is about 108 px -- so a
    letter and the x-aligned letter on the NEXT LINE passed gap, share
    and stack together, and union-find chained 114 components down 80%
    of the page. 2,125 components became 380 clusters where roughly
    2,125 were wanted.

    Each of the three conditions was individually right; what was
    missing was that a rule written for `i` + tittle had the whole page
    to walk. `rows()` costs 0.01 s on that page and every multi-part
    glyph -- the tittle, the umlaut, the two dots of `:`, an inline
    accent -- is within one row by construction.

    Pass `rows` to reuse a partition already computed; otherwise it is
    computed here.

    G6: **the stacking test is what separates one glyph from two.** An
    earlier version used only horizontal overlap and vertical distance,
    and joined a narrow letter sitting inside a wide letter's span --
    they were side by side, not stacked, and the rule could not tell.
    Parts of one glyph sit ABOVE each other; adjacent letters sit BESIDE
    each other, and that is the whole distinction.

    KNOWN DEFECT, measured and not fixed: **a display big operator's
    limits are absorbed into the operator.** A `sum` with limits above and
    below groups as one glyph -- the limits x-overlap it almost totally,
    are stacked, and sit close relative to its height, so all three
    conditions hold. `i` + dot, an accent and an inline `x^2` are all
    handled correctly; only the display-operator case fails.

    It is not fixed here because the obvious fix does not work. Excluding
    what `detect_scripts` found would close it if the limits were in the
    operator's row -- but a display limit does not vertically overlap its
    operator at all, so `rows()` separates them and nothing classifies
    them as scripts. Distinguishing an accent from a limit geometrically
    is the same problem as knowing the operator is an operator, which is
    symbol identity, which is the thing with no measurement behind it.
    Recorded rather than papered over.
    """
    if not 0.0 < share <= 1.0:
        raise ValueError(f"share must be in (0, 1], got {share}")
    everything = list(glyphs)
    parent = {g.id: g.id for g in everything}

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    if rows is None:
        rows = _partition_rows(everything)
    by_id = {g.id: g for g in everything}
    # One row at a time. This also drops the pairwise loop from the
    # whole page to a line: n falls from 2,125 to about 45, and the
    # loop is quadratic in the worst case.
    bands = [[by_id[g.id] for g in r.members if g.id in by_id] for r in rows]
    # A glyph in no row needs no band of its own: `parent` is seeded
    # from every glyph and the cluster assembly below walks `everything`,
    # so an untouched glyph is already its own root. Adding a band for
    # it was dead code -- removing it kills no test, which is how it was
    # found.

    for band in bands:
        order = sorted(band, key=lambda g: (g.x0, g.top, g.id))
        _join_within(order, parent, find, share, max_gap, stack)

    clusters: dict[int, list[int]] = {}
    for g in everything:
        clusters.setdefault(find(g.id), []).append(g.id)
    return sorted((sorted(v) for v in clusters.values()),
                  key=lambda ids: ids[0])


def _join_within(order, parent, find, share, max_gap, stack) -> None:
    """The pairwise join, over ONE row's glyphs.

    The `break` on `gb.x0 > ga.x1` relies on the x-sort, which still
    holds within a row -- the sort is done by the caller per band.
    """
    for a in range(len(order)):
        ga = order[a]
        for b in range(a + 1, len(order)):
            gb = order[b]
            if gb.x0 > ga.x1:
                break
            overlap = min(ga.x1, gb.x1) - max(ga.x0, gb.x0)
            narrow = min(ga.width, gb.width) or 1.0
            if overlap < share * narrow:
                continue
            v_overlap = min(ga.bottom, gb.bottom) - max(ga.top, gb.top)
            if v_overlap > stack * min(ga.height, gb.height, 1.0):
                continue                      # side by side, not stacked
            gap = max(ga.top, gb.top) - min(ga.bottom, gb.bottom)
            if gap > max_gap * max(ga.height, gb.height, 1.0):
                continue
            ra, rb = find(ga.id), find(gb.id)
            if ra != rb:
                parent[rb] = ra


def pair_stats(mask) -> dict:
    """(components, holes, stacked, centred, offset) of one mask (I1).

    The structural five-tuple the expression-compare loop runs on,
    moved here from `tools/mathshape.py` so the CLI and the tool share
    ONE definition -- the feature vector drifted at two call sites
    once before (`classify.signature_features`), and this is the same
    prevention.

    Stacked: two components, x-overlap >= 0.5 of the narrower, one
    strictly above the other, vertical gap <= 1.5x the MEDIAN component
    height, nothing between them except possibly a RULE (`is_rule`); a
    rule between makes the pair a Fraction, counted in `stacked` and in
    neither split. Centred: x-centres within 15% of the wider width;
    else offset. Rules stay in the pair population -- excluding them
    made the features scale-dependent (measured: stacked flapped
    6,5,6,6,5,6 across 200-800 dpi).

    The gap bound is I5: without it the count measures LINE SPACING,
    not structure -- on bh2 EQ0007 (an aligned two-line block) the raw
    pair loop reads 53 vs 36 stacked (rendered vs scan, 300 dpi) and
    bounded reads 8 vs 7, on visually identical content. Bounded is
    also the steadier instrument across dpi (8->9 vs 7->7 at 600).
    """
    from .nest import ink_only
    ik = ink_only(mask)
    regs = list(ik.regions)
    holes = sum(ik.cycles)
    stacked, centred, offset = pair_counts(regs)
    return {"components": len(regs), "holes": holes, "stacked": stacked,
            "centred": centred, "offset": offset}


def pair_counts(comps):
    """(stacked, centred, offset) over box-like items with id, x0, y0,
    x1, y1 and area -- the pure-geometry core of `pair_stats`, split
    out for T29/T30: `locate` runs it on CACHED components with no
    pixel access, and the two callers sharing one body is what keeps
    the window score and the compare five-tuple the same measurement.
    """
    import statistics
    from .emit import is_rule
    rids = {r.id for r in comps
            if is_rule(r) and (r.x1 - r.x0) >= (r.y1 - r.y0)}
    med_h = (statistics.median(c.y1 - c.y0 + 1 for c in comps)
             if comps else 0)
    stacked = centred = offset = 0
    for i, a in enumerate(comps):
        for b in comps[i + 1:]:
            top, bot = ((a, b) if a.y1 < b.y0 else
                        ((b, a) if b.y1 < a.y0 else (None, None)))
            if top is None:
                continue
            ov = min(top.x1, bot.x1) - max(top.x0, bot.x0) + 1
            wa, wb = top.x1 - top.x0 + 1, bot.x1 - bot.x0 + 1
            if ov < 0.5 * min(wa, wb):
                continue
            if bot.y0 - top.y1 - 1 > 1.5 * med_h:
                continue
            bx0, bx1 = min(top.x0, bot.x0), max(top.x1, bot.x1)
            between = [c for c in comps if c is not top and c is not bot
                       and c.y0 > top.y1 and c.y1 < bot.y0
                       and c.x1 >= bx0 and c.x0 <= bx1]
            if any(c.id not in rids for c in between):
                continue
            stacked += 1
            if between:
                continue                          # only a rule: Fraction
            ca = (top.x0 + top.x1) / 2
            cb = (bot.x0 + bot.x1) / 2
            if abs(ca - cb) <= 0.15 * max(wa, wb):
                centred += 1
            else:
                offset += 1
    return stacked, centred, offset


def _box_gap(a, b) -> int:
    """Separation between two boxes, in pixels, 0 when they overlap.

    `max` of the two axis separations rather than a Euclidean
    distance: for a diagonal pair `max` is the SMALLER number, so a
    component is called separated only when it clears the bound on the
    axis it is furthest along. Under-reporting separation
    under-reports overrun, which is the direction a cross-check should
    err in.
    """
    dx = max(a.x0 - b.x1, b.x0 - a.x1) - 1
    dy = max(a.y0 - b.y1, b.y0 - a.y1) - 1
    return max(0, dx, dy)


def region_overrun(mask, *, gap_scale: float = 1.0, edge_tol: int = 0,
                   anchor: str = "edge", comps=None) -> dict:
    """Which of this crop's components came from OUTSIDE its region.

    A crop cut to a table cell or a detected region does not always
    stop at the region: a neighbouring line's descender, the row rule
    above, or the next column's ink can cross the boundary and land
    in the crop. Downstream that reads as a component the other tool
    failed to produce -- a conversion defect -- when it is a
    CROPPING defect, and the two want opposite fixes.

    The two conditions, both required, are what separate the classes:

      SEPARATED  the component is not in the main ink's
                 single-linkage cluster at `gap_scale` x the crop's
                 median component WIDTH. Real mathematics is spaced
                 in fractions of a glyph; ink from the next region
                 is a whole glyph or more away, because the region
                 boundary sits between them.
      ANCHORED  where the cluster sits. Two readings, chosen by
                 `anchor`, and they are DIFFERENT STATEMENTS rather
                 than one statement at two tolerances:

                 `edge`     some member reaches within `edge_tol` px
                            of a crop BORDER. Ink that entered across
                            the boundary was cut by it, so it
                            touches -- but only where it was cut, and
                            the rest of the intruding mark sits just
                            inside, so the condition is on the
                            CLUSTER, not on each component.
                 `extreme`  the cluster is the OUTERMOST one in some
                            direction -- no cluster reaches further
                            left, right, up or down. Measures the
                            position of the INK rather than of the
                            rectangle, so a uniform inset between the
                            region border and its content cannot
                            defeat it.

                 `edge` is the stricter statement and the right one
                 when the crop really is cut at the region boundary.
                 It fails outright when the producer insets its
                 crops: measured on four report crops from two
                 documents, the rightmost ink stopped 6, 6, 6 and 7
                 px short of the border regardless of what the row
                 contained, so `edge` at any tolerance below the
                 inset reports nothing on every row and above it
                 reports every row. A constant margin across
                 differently sized crops is the tell.

    Either alone is common and neither alone is evidence: a display
    limit is separated and interior; the first glyph of the
    expression is at an edge and joined. Both together are the
    signature of ink the crop should not contain.

    `comps` accepts an already-computed region list so a caller that
    has run `pair_stats` on the same crop does not sweep it twice;
    it must be that same list, from the SAME mask.

    Returns `overrun` (the ids, under the chosen `anchor`),
    `separated`, `edged` and `extreme` (the two anchor sets, both
    computed whichever is selected, so a caller comparing them reads
    one sweep), `at_edge` (the DIAGNOSTIC set: every component
    touching a border, main ink included), `med_width`, and `kept` -- the
    components that survive, so the caller can recompute the
    five-tuple on the crop's own ink rather than guessing what
    removing them would do. BOTH anchor sets are returned whichever
    is selected, so a caller comparing the two reads one sweep.

    Thresholds are named arguments with measured defaults (G7); the
    defaults come from `tools/overrun.py`, which prints the
    distribution of both conditions over the flagged corpus.
    """
    if comps is None:
        from .nest import ink_only
        comps = list(ink_only(mask).regions)
    if not comps:
        return {"overrun": [], "separated": [], "at_edge": [],
                "edged": [], "extreme": [], "med_width": 0.0,
                "kept": []}
    import statistics
    med_w = statistics.median(c.x1 - c.x0 + 1 for c in comps)
    bound = gap_scale * med_w

    # Single linkage at `bound`, then the MAIN ink is the cluster
    # carrying the most ink -- not the largest single component and
    # not the first id. Seeding from one component made the answer
    # depend on which of several equal-area glyphs happened to be
    # first in raster order, which is exactly the
    # `Component.root` vs `nodes[0]` mistake in another costume.
    parent = {c.id: c.id for c in comps}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(comps):
        for b in comps[i + 1:]:
            if _box_gap(a, b) <= bound:
                ra, rb = find(a.id), find(b.id)
                if ra != rb:
                    parent[ra] = rb
    groups = {}
    for c in comps:
        groups.setdefault(find(c.id), []).append(c)
    main_key = max(groups,
                   key=lambda k: (sum(c.area for c in groups[k]),
                                  len(groups[k]), -k))
    main = groups[main_key]
    rest = [c for k, g in groups.items() if k != main_key for c in g]
    w, h = mask.width, mask.height

    def at_edge(c):
        return (c.x0 <= edge_tol or c.y0 <= edge_tol
                or c.x1 >= w - 1 - edge_tol or c.y1 >= h - 1 - edge_tol)

    # Per CLUSTER, not per component. Ink that crossed the boundary
    # is cut by it and usually arrives in pieces -- a descender leaves
    # a blob touching the border and a second one just inside. Judging
    # each piece alone keeps the interior halves and still reports a
    # surplus, which is the finding this test exists to remove.
    xs0 = min(c.x0 for c in comps); xs1 = max(c.x1 for c in comps)
    ys0 = min(c.y0 for c in comps); ys1 = max(c.y1 for c in comps)

    def is_extreme(g):
        return (min(c.x0 for c in g) == xs0 or max(c.x1 for c in g) == xs1
                or min(c.y0 for c in g) == ys0
                or max(c.y1 for c in g) == ys1)

    edged, extreme = set(), set()
    for k, g in groups.items():
        if k == main_key:
            continue
        if any(at_edge(c) for c in g):
            edged.update(c.id for c in g)
        if is_extreme(g):
            extreme.update(c.id for c in g)
    if anchor == "edge":
        ids = edged
    elif anchor == "extreme":
        ids = extreme
    else:
        raise ValueError(f"anchor must be 'edge' or 'extreme', "
                         f"not {anchor!r}")
    return {"overrun": sorted(ids),
            "separated": sorted(c.id for c in rest),
            # the DIAGNOSTIC set is every component touching a border,
            # main ink included -- a row whose expression starts at the
            # crop edge is what tells you the crop is cut tight, and
            # that is exactly what the decision set hides.
            "at_edge": sorted(c.id for c in comps if at_edge(c)),
            "edged": sorted(edged),
            "extreme": sorted(extreme),
            "med_width": float(med_w),
            "kept": [c for c in comps if c.id not in ids]}
