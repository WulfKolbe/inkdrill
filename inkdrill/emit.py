"""emit.py -- inkdrill findings as a MathPix-shaped `lines.json`.

CONTRACT (written before implementation; see docs/units.md T1)
=============================================================

The one place in this package that produces an interchange format, so
that the format lives in one file rather than being reconstructed at
each call site. `ocr_lines.py` on the pdfdrill side is the precedent: a
non-MathPix producer emitting the same shape the docmodel already
ingests, with its own information under namespaced additive keys.

No file is written here. `pngio` only reads and this only builds a
dict; the caller decides where it goes.

Coordinates: from `pHYs`, or not at all
---------------------------------------
Every `region` is in POINTS, converted with `72 / dpi` where dpi comes
from the PNG's own `pHYs` chunk. Deriving it from a nominal page size
instead is the error this project measured on the `e12s39` fixture: its
MediaBox is `0 0 595 842`, not A4's nominal 595.32 x 841.92, and the
nominal derivation gives 175.391 pt where the answer is 175.320 -- an
error of 0.071 pt, exactly the size of the residual being measured at
the time.

**A missing `pHYs` raises.** Not a fallback to 72, not a guess from the
page size: a file whose coordinates are silently in the wrong space is
the failure mode this project keeps finding, and it is worse than no
file because a consumer cannot detect it.

What is a line, and what is not
-------------------------------
A `lines` entry is something a document consumer can act on -- a table,
a cell, a figure region. **Rules, ticks and bare glyph components are
not.** They are geometry of a parent object and live under `ink.*` on
the enclosing line. One arXiv plot page carries 140 ticks; a consumer
expecting readable regions would drown in them.

`text` and `text_display` are `""` on every line. **inkdrill does not
read text and must not appear to.**

Measurements, never classifications
-----------------------------------
`ink.rules[].width_pt` is emitted; `"kind": "toprule"` is not. The
absolute stroke width runs about 12% high because of rasteriser
coverage, and the ratio between two rules is unstable under pixel
quantisation -- so `\\toprule` versus `\\midrule` is decidable only by
RELATIVE ranking within one table, plus position. That call belongs to
the side holding the table's context. Sending a classification would
move the decision to the side with less of it.

Guarantees
----------
G1  every `region` is in pt, converted from `pHYs`; a missing `pHYs`
    raises `NoResolution`
G2  `page_width`/`page_height` are in the same space as every region on
    that page -- asserted, because a mixed-unit file is the failure that
    hides
G3  every `simple_cell` carries `cell_row` and `cell_column`, and the
    pairs on one table are exactly `[0, rows) x [0, cols)` -- no gaps,
    no duplicates
G4  no `lines` entry is a rule, a tick or a bare glyph component
G5  the dict round-trips through `json.dumps`/`loads` unchanged
G6  `text` is `""` on every line
G8  a hole covering more than one band reports `cell_row_span` /
    `cell_col_span` accordingly -- a grid with an undrawn internal rule
    must not be reduced to the smaller grid its holes happen to tile,
    which G3 alone cannot detect because the reduction is still an
    exact rectangle
G7  `ink.rules[]` carries a MEASURED `width_pt`, never a rule name --
    the `\\toprule` / `\\midrule` call is relative ranking within one
    table and belongs to the side holding that context
"""

from __future__ import annotations

from .aggregate import moments_per_component
from .classify import NoTemplates, template_of
from .nest import Kind, ink_only, nest
from .raster import InkMask
from .sweep import Capture, sweep

__all__ = ["NoResolution", "lines_json", "page_record", "page_lines",
           "text_scale",
           "cell_grid", "diagram_line", "ink_regions", "is_rule",
           "rule_record", "rule_width_pt", "table_lines", "SOURCE"]

SOURCE = "inkdrill"


class NoResolution(ValueError):
    """The PNG carries no `pHYs`, so points cannot be derived (G1)."""


def _pt_per_px(dpi) -> float:
    if not dpi or not dpi[0]:
        raise NoResolution(
            "the PNG declares no pHYs resolution; points cannot be derived. "
            "Deriving dpi from a nominal page size is wrong by 0.071 pt on "
            "the e12s39 fixture -- emit nothing rather than the wrong space")
    return 72.0 / float(dpi[0])


def _region(box, pt: float) -> dict:
    """A MathPix `region`, in pt (G1)."""
    x0, y0, x1, y1 = box
    return {"top_left_x": x0 * pt, "top_left_y": y0 * pt,
            "width": (x1 - x0) * pt, "height": (y1 - y0) * pt}


def _line(kind: str, box, pt: float, **extra) -> dict:
    out = {"type": kind, "region": _region(box, pt),
           "text": "", "text_display": ""}          # G6
    out.update(extra)
    return out


def cell_grid(holes, *, tol: float = 0.0):
    """`(row, column, row_span, col_span)` per hole (G3, G8).

    A hole's cluster index IS its row or column: sort the bboxes on each
    axis and start a new cluster when the gap exceeds `tol`. Verified on
    a Word-produced handbook page -- one component, 52 holes, recovering
    13 rows x 4 columns.

    **Spans are not optional.** A grid whose internal rules are not all
    drawn -- `\\cline`, a partial border, any merged cell -- has holes
    covering more than one band, and reporting only the index reduces
    the table to whatever grid the holes happen to tile. That reduced
    grid is still an exact rectangle, so G3 PASSES on it and the wrong
    shape is emitted silently. A hole's span is the number of band
    starts it covers, which is the information already in the lattice.

    `tol` defaults to 0 and should be set from the ink: cells of one
    table share an edge to within the rule's own thickness, so the
    natural tolerance is that thickness rather than a constant.
    """
    def bands(values):
        index, order, starts = {}, sorted(set(values)), []
        k = 0
        for i, v in enumerate(order):
            if i and v - order[i - 1] > tol:
                k += 1
                starts.append(v)
            elif not i:
                starts.append(v)
            index[v] = k
        return index, starts

    rows, row_starts = bands([h[1] for h in holes])
    cols, col_starts = bands([h[0] for h in holes])

    def span(starts, lo, hi):
        # Bands whose START lies inside [lo, hi) -- the first is the
        # hole's own, each further one is a band it swallowed.
        return max(1, sum(1 for s in starts if lo <= s < hi))

    return [(rows[h[1]], cols[h[0]],
             span(row_starts, h[1], h[3]), span(col_starts, h[0], h[2]))
            for h in holes]


def rule_width_pt(area: int, width: int, height: int, pt: float) -> float:
    """A solid rule's stroke width, in pt.

    `area / max(w, h)` -- the long side divides out, leaving the short
    one. Measured on real pages this lands on exact integers at the
    pixel level: 3.0, 4.0, 6.0 px at 400 dpi.
    """
    longest = max(width, height)
    if longest <= 0:
        raise ValueError("a rule with no extent has no width")
    return area / longest * pt


def ink_regions(nesting):
    """The ink regions of a `Nesting`, outermost first.

    Exists so a caller never has to invent a region id. `nest` numbers
    its regions in its OWN space, which is not the sweep's: a component
    from `moments_per_component` is keyed by `Component.root` and has
    no relation to a `Region.id`. Passing one where the other is
    expected returns an empty hole list and an empty table -- no
    exception, just a silently missing lattice.

    That is the same two-id-spaces trap as `Component.root` versus
    `Component.nodes[0]`, which cost 1,293 of 1,310 components on a real
    page. Here the signature makes it unrepresentable instead.
    """
    return [r for r in nesting.regions.values() if r.kind is Kind.INK]


def text_scale(nesting) -> float:
    """The page's own text height, as the median ink-region height.

    A page is mostly letters, so the median component is a letter. This
    is what a cell has to be bigger than -- and it is RELATIVE, so a
    dpi change cannot silently retune it, unlike a floor in points.
    """
    hs = sorted(r.y1 - r.y0 + 1 for r in ink_regions(nesting))
    return float(hs[len(hs) // 2]) if hs else 0.0


def table_lines(mask, region_id=None, *, pt: float, tol: float = 0.0,
                nesting=None, min_cell: float = 0.0):
    """A `table` and its `simple_cell`s from one ink region's holes (G3).

    `region_id` is a **`nest` region id**, not a sweep component id --
    see `ink_regions`. Omitted, the largest ink region is used.

    Returns `[]` when the region encloses nothing: a frame with no
    lattice is a `diagram`, and deciding that here rather than emitting
    an empty table keeps the caller from having to unpick it.
    """
    n = nesting if nesting is not None else nest(mask)
    if region_id is None:
        inks = ink_regions(n)
        if not inks:
            return []
        region_id = max(inks, key=lambda r: r.area).id
    region = n.regions[region_id]
    if region.kind is not Kind.INK:
        raise ValueError(
            f"region {region_id} is {region.kind.value}, not ink; "
            f"`table_lines` takes a nest region id, not a sweep "
            f"component id -- see `ink_regions`")
    holes = [n.regions[h] for h in n.holes_of(region_id)]
    # A CELL IS BIGGER THAN THE TEXT IT CONTAINS; a glyph counter is
    # smaller than the glyph around it. Without this, every `a`, `e` and
    # `o` on a page emits a `simple_cell` -- 1,161 of 1,611 on one real
    # figure page, at 0.18 pt each, one pixel at 400 dpi -- and every
    # `B`, `8` and `%` emits a two-cell `table`.
    #
    # The earlier argument against a size floor was about RECTANGLES
    # (hollow, fill < 0.35) and was right for those: a real depth-2 box
    # can be smaller than body text. A cell is the opposite object -- a
    # hole that CONTAINS content -- so it is bounded below by the text
    # inside it. Different object, opposite bound.
    if min_cell > 0.0:
        holes = [h for h in holes
                 if (h.x1 - h.x0 + 1) >= min_cell
                 and (h.y1 - h.y0 + 1) >= min_cell]
    # A LATTICE, not merely a hole. Every hollow rectangle encloses its
    # interior, so `holes >= 1` would make a plot frame a 1x1 table --
    # which is true and useless, and would hand the consumer a table
    # with one cell where it expected a figure. Two holes is the
    # smallest thing that can carry a row or a column index.
    if len(holes) < 2:
        return []
    moments = region
    boxes = [(h.x0, h.y0, h.x1 + 1, h.y1 + 1) for h in holes]
    grid = cell_grid(boxes, tol=tol)
    # `max(index) + 1` is provably the same number: bands are DEFINED
    # by hole starts, so every band has a hole starting in it. Written
    # with the span because that is what the quantity means, and a
    # future band inference not derived from starts would break the
    # equivalence silently.
    rows = max(r + rs for r, _, rs, _ in grid)
    cols = max(c + cs for _, c, _, cs in grid)
    out = [_line("table", (moments.x0, moments.y0,
                           moments.x1 + 1, moments.y1 + 1), pt,
                 cell_row=None, cell_column=None,
                 ink={"region_id": region_id,
                      "holes": len(holes), "rows": rows, "columns": cols})]
    for box, (r, c, rs, cs) in zip(boxes, grid):
        out.append(_line("simple_cell", box, pt,
                         cell_row=r, cell_column=c,
                         cell_row_span=rs, cell_col_span=cs))
    return out


def is_rule(region, *, min_fill: float = 0.8, min_aspect: float = 20.0):
    """Is this region a drawn rule -- solid, and far longer than thick?

    Two conditions, and both are needed. `fill` alone admits any solid
    blob; aspect alone admits a hairline that is mostly gaps. A rule is
    the conjunction: nearly all ink inside its box, and a long side at
    least `min_aspect` times the short one.
    """
    w, h = region.x1 - region.x0 + 1, region.y1 - region.y0 + 1
    if w <= 0 or h <= 0:
        return False
    if region.area / (w * h) <= min_fill:
        return False
    return max(w, h) >= min_aspect * max(1, min(w, h))


def rule_record(region, pt: float) -> dict:
    """One rule as a measurement (G7).

    `width_pt` and an orientation, and deliberately NOT a name. Whether
    this is a `\\toprule` or a `\\midrule` is decided by relative
    ranking within one table plus position -- the absolute width runs
    about 12% high from rasteriser coverage and the ratio is unstable
    under pixel quantisation. Sending `"kind": "toprule"` would move
    that call to the side with less context.
    """
    w = region.x1 - region.x0 + 1
    h = region.y1 - region.y0 + 1
    return {"x0": region.x0 * pt, "y0": region.y0 * pt,
            "x1": (region.x1 + 1) * pt, "y1": (region.y1 + 1) * pt,
            "width_pt": rule_width_pt(region.area, w, h, pt),
            "orient": "h" if w >= h else "v"}


def _contains(outer, inner) -> bool:
    return (outer.x0 <= inner.x0 and outer.y0 <= inner.y0
            and outer.x1 >= inner.x1 and outer.y1 >= inner.y1)


def diagram_line(region, pt: float, *, ground: str | None = None,
                 contains: int | None = None) -> dict:
    """A hollow rectangle that is not a table, or a textured region.

    `contains` is the number of separate ink components sitting inside
    this region's holes -- the evidence for the call, not a summary of
    it. A consumer that wants a stricter rule than "at least one" can
    apply its own cut without re-running `nest`.
    """
    ink = {"region_id": region.id,
           "fill": region.area / max(
               1, (region.x1 - region.x0 + 1) * (region.y1 - region.y0 + 1))}
    if contains is not None:
        ink["contains"] = contains
    if ground is not None:
        ink["border_ground"] = ground
    return _line("diagram", (region.x0, region.y0,
                             region.x1 + 1, region.y1 + 1), pt,
                 cell_row=None, cell_column=None, ink=ink)


def glyph_line(region, pt: float, *, holes: int = 0, axis=None,
               components: int = 1, candidates=None) -> dict:
    """One ink component, described and NOT named (T2).

    The blobs exist and nothing emitted them, so a page of text emitted
    nothing at all. This makes the first pass visible: a bbox in
    points, the ink area, the hole count, and the principal axis. There
    is no classification here and no glyph name -- that needs symbol
    identity, which this project does not have and records as a gap.

    NO SIZE FILTER, and that is measured rather than assumed. On a
    scanned page 1,161 of 1,164 components fall inside any reasonable
    size bound, so a bound would be a threshold that changes nothing
    except what a future dpi silently retunes. A consumer filters on
    the emitted `area` and box.

    `axis` is absent rather than null when the moments could not be
    matched to this region -- a key present with a null value would say
    the axis was measured and found to be nothing.

    `candidates` is `[[label, distance], ...]`, RANKED and never
    reduced. There is no argmax anywhere in this module: the consumer
    holds the lexicon and inkdrill deliberately does not, so a single
    label chosen here would be a decision taken by the party with less
    information. Absent when no classifier was supplied; **empty when
    one was and nothing matched**, and those two are different
    statements.

    `components` is 1 for a single-component line. It is emitted so the
    topology pair `(components, holes)` reads uniformly and so a future
    grouped line has the field, not because it was measured to be 1.
    """
    ink = {"region_id": region.id, "area": region.area, "holes": holes,
           "components": components}
    if axis is not None:
        ink["axis"] = [round(axis[0], 6), round(axis[1], 6)]
    if candidates is not None:
        # A LIST, and possibly an empty one (C3, C4). Empty says every
        # candidate the classifier knows is inconsistent with this ink,
        # which is the finding rather than a failure -- it is how the
        # unrecognised fraction is transmitted instead of hidden behind
        # a best guess.
        ink["candidates"] = [[lab, round(float(d), 4)]
                             for lab, d in candidates]
    return _line("glyph", (region.x0, region.y0, region.x1 + 1,
                           region.y1 + 1), pt, cell_row=None,
                 cell_column=None, ink=ink)


def _crop(mask, region):
    """The region's bounding box as a standalone mask.

    A crop, NOT the isolated component: neighbouring ink inside
    the same box stays, because that is what a page hands a
    classifier and stripping it would measure a cleaner problem
    than the real one.
    """
    w = region.x1 - region.x0 + 1
    h = region.y1 - region.y0 + 1
    buf = bytearray(w * h)
    for j in range(h):
        src = (region.y0 + j) * mask.width + region.x0
        buf[j * w:(j + 1) * w] = mask.data[src:src + w]
    return InkMask(bytes(buf), w, h)


def _candidates_for(mask, region, classifier, top_k):
    """The ranked candidate list for one region, or None.

    Returns a LIST and never a label (C4). An empty list is a
    real answer.
    """
    if classifier is None:
        return None
    q = template_of(_crop(mask, region), "?")
    if q is None:
        return ()
    try:
        return classifier.classify(q, top_k=top_k).candidates
    except NoTemplates:
        return ()


def _glyphs_only(mask, pairs, pt: float, classifier=None,
                 top_k: int = 8):
    """The no-structure path: glyphs, with holes from the cycle rank.

    Reached when no component could be a table or a diagram, which is
    every page of plain text. It skips the background sweep -- roughly
    half of `nest` -- and returns the SAME ids, because an ink region's
    identity never depended on that sweep.
    """
    by_geom = {}
    for c in moments_per_component(
            sweep(mask, conn=8, capture=Capture.GRAPH)).values():
        key = (c.x0, c.y0, c.x1, c.y1, c.area)
        by_geom[key] = None if key in by_geom else c
    out = []
    for region, cycles in sorted(pairs, key=lambda t: (t[0].y0, t[0].x0)):
        if is_rule(region):
            continue
        c = by_geom.get((region.x0, region.y0, region.x1, region.y1,
                         region.area))
        out.append(glyph_line(
            region, pt, holes=cycles,
            axis=c.principal_axis if c is not None else None,
            candidates=_candidates_for(mask, region, classifier, top_k)))
    return out


def page_lines(mask, *, pt: float, tol: float = 0.0, grounds=None,
               max_fill: float = 0.35, cell_scale: float = 3.0,
               diagram_scale: float = 3.0, require_content: bool = True,
               glyphs: bool = False, classifier=None,
               top_k: int = 8):
    """Every emittable object on one page, with rules attached.

    A region becomes a `table` when it encloses a LATTICE (>= 2 holes),
    a `diagram` when it is hollow but not, and nothing when it is
    neither -- a bare glyph is not a line (G4).

    Rules are never lines of their own. Each is attached to the
    innermost emitted object containing it, so a consumer reading
    `lines` sees objects and reads geometry from `ink.rules` (G4).

    **A rule is found only when it is a SEPARATE component.** In a
    `|l|l|` table the rules ARE the frame -- one connected component --
    so none of them is a region and none is reported. A booktabs table
    draws disjoint rules and they are all found, which is also the only
    place `\\toprule` versus `\\midrule` is a question. Extracting
    rules from inside a connected frame means reading the run structure
    near the bbox edge, and is separate work; it is the same shape as
    ticks drawn as part of an axis path rather than as free objects.
    """
    grounds = grounds or {}
    # T4: the hole GEOMETRY is only needed if something on this page
    # could be a table or a diagram. `ink_only` is the ink half of the
    # same computation -- same ids, same boxes -- so the cheap path and
    # the full one speak one id space and a consumer cannot tell which
    # ran except by what is absent.
    ink = ink_only(mask)
    pairs = ink.pairs()
    heights = sorted(r.y1 - r.y0 + 1 for r, _ in pairs)
    scale = float(heights[len(heights) // 2]) if heights else 0.0
    bar = min(scale * cell_scale, scale * diagram_scale)
    if not any(cyc and max(r.x1 - r.x0 + 1, r.y1 - r.y0 + 1) >= bar
               for r, cyc in pairs):
        # Nothing structural is possible. Holes come from the cycle
        # rank, which IS the per-component hole count -- checked
        # against `nest` on every page measured.
        if not glyphs:
            return []
        return _glyphs_only(mask, pairs, pt, classifier, top_k)

    n = ink.complete()          # reuses the ink sweep above
    inks = ink_regions(n)
    # `cell_scale` multiplies the page's own text height. The default
    # is 3.0, and it is chosen by an INVARIANCE rather than by fit:
    #
    #   cell_scale   figure page (no tables)   real 13x4 grid
    #          1.0     73 tables, 284 cells      1 table, 52 cells
    #          1.5     54, 195                   1, 52
    #          2.0     21,  57                   1, 52
    #          3.0      2,   4                   1, 52
    #
    # The real grid is COMPLETELY INSENSITIVE across a 3x range while
    # the false positives collapse by 70x. That is the signature of a
    # separation rather than a tuned threshold: any value in the range
    # is safe for the true positive, so the highest one is free.
    min_cell = scale * cell_scale
    # A FIGURE IS NOT LETTER-SIZED, and `diagram` had no floor at all --
    # so a hollow glyph with fewer than two holes fell through the table
    # branch straight into it. A scanned German page emitted 319 lines,
    # every one a `diagram`, median 5.3 x 7.4 pt against a page text
    # scale of the same order: every `o`, `e`, `a`, `ue`.
    #
    # Same rule as the cell floor and for the same reason, but note the
    # bound runs the other way. A CELL is bounded below because it
    # CONTAINS text. A DIAGRAM is bounded below because it REPLACES
    # text -- a figure occupies space a paragraph would have. Different
    # arguments, same threshold shape.
    min_diagram = scale * diagram_scale
    # CONTAINMENT, which is the real test; the size floor above is only
    # a cheap pre-filter for it. A table cell holds text and the
    # counter of an `o` holds nothing, so "does a hole of this region
    # contain a SEPARATE ink component" separates structure from a
    # glyph exactly, with no threshold and nothing to retune per
    # corpus. `nest` has computed it already -- `ink_in_hole` is the
    # relation, deliberately distinct from `hole_of`.
    #
    # Measured on the Infineon handbook against MathPix's own page
    # labels, six pages of each kind:
    #
    #   MathPix says      pages fired          objects emitted
    #                   size   containment   size   containment
    #   HAS figure       6/6       5/6         548        12
    #   HAS table        6/6       6/6          18         6
    #   NEITHER          6/6       1/6        1549         1
    #
    # The size floor fires on every page that has nothing and emits
    # 1549 objects there. Containment emits one.
    #
    # THE COST IS REAL AND IS ONE PAGE IN SIX. p10's figure is a single
    # connected component -- the plot data touches the frame -- so
    # nothing is loose inside it and containment cannot see it. That is
    # the honest residual, not an argument against the rule: an
    # unenclosed figure is what the white-run gap analysis finds, and
    # that half is built and not yet wired in here.
    rules = [r for r in inks if is_rule(r)]
    rule_ids = {r.id for r in rules}

    out = []
    for region in sorted(inks, key=lambda r: -r.area):
        # Provably redundant, and kept for intent: a rule has fill > 0.8
        # by definition, so it fails the diagram test (< 0.35) and has
        # too few holes for the table test, and emits nothing either
        # way. No test can kill this line; none should be written to try.
        if region.id in rule_ids:
            continue
        w = region.x1 - region.x0 + 1
        h = region.y1 - region.y0 + 1
        ground = grounds.get(region.id)
        lines = table_lines(mask, region.id, pt=pt, tol=tol, nesting=n,
                            min_cell=min_cell)
        if lines:
            out.append((region, lines))
            continue
        held = sum(len(n.ink_in_hole(h)) for h in n.holes_of(region.id))
        if ((ground == "textured"
             or region.area / max(1, w * h) < max_fill)
                and max(w, h) >= min_diagram
                and (held or not require_content)):
            out.append((region, [diagram_line(region, pt, ground=ground,
                                              contains=held)]))

    if glyphs:
        # The moments come from `sweep`, whose ids are `Component.root`
        # and are NOT `Region.id`. Rather than carry two id spaces into
        # one file, they are joined on exact geometry -- the two are the
        # same partition, since `nest` labels with this very sweep --
        # and a region with no unique match keeps its geometry and
        # loses only the axis.
        by_geom = {}
        for c in moments_per_component(
                sweep(mask, conn=8, capture=Capture.GRAPH)).values():
            key = (c.x0, c.y0, c.x1, c.y1, c.area)
            # DEFENSIVE and unasserted: two 8-connected components
            # sharing an exact box AND area is possible in principle
            # and no fixture here reaches it -- removing this line
            # kills no test. It is kept because the failure it prevents
            # is attaching one component's axis to another, which is a
            # silently wrong value rather than an error. Recorded as a
            # surviving mutant rather than defended by a contrived
            # fixture.
            by_geom[key] = None if key in by_geom else c
        done = {r.id for r, _ in out}
        for region in sorted(inks, key=lambda r: (r.y0, r.x0)):
            if region.id in done or region.id in rule_ids:
                continue
            c = by_geom.get((region.x0, region.y0, region.x1, region.y1,
                             region.area))
            out.append((region, [glyph_line(
                region, pt, holes=len(n.holes_of(region.id)),
                axis=c.principal_axis if c is not None else None,
                candidates=_candidates_for(mask, region, classifier,
                                           top_k))]))

    for region, lines in out:
        mine = [r for r in rules if _contains(region, r)]
        if mine:
            lines[0].setdefault("ink", {})["rules"] = [
                rule_record(r, pt) for r in
                sorted(mine, key=lambda r: (r.y0, r.x0))]
    return [ln for _, lines in out for ln in lines]


def page_record(*, page: int, width_px: int, height_px: int, dpi,
                lines=()) -> dict:
    """One page, with every coordinate in pt (G1, G2)."""
    pt = _pt_per_px(dpi)
    return {"page": page, "image_id": None,
            "page_width": width_px * pt, "page_height": height_px * pt,
            "lines": list(lines)}


def lines_json(pages, *, source: str = SOURCE, render_dpi: float) -> dict:
    """The document wrapper.

    `ocr.units` is `pt` and every region obeys it. MathPix emits its own
    pixel space and the consumer rescales; declaring the space removes
    the guess, and mixing the two conventions in one file is how a scale
    error hides.
    """
    return {"source": source,
            "ocr": {"units": "pt", "render_dpi": float(render_dpi)},
            "pages": list(pages)}
