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

A rule that NO emitted object encloses -- the booktabs case, where the
table draws no frame and the rules are the only evidence it exists --
appears at `page["ink"]["rules"]` on the page record, same entry shape
as the per-line array. **A consumer must read both keys**; the split is
structural, not stylistic, because an unenclosed rule has no line to
carry it. This paragraph exists because the page-level key shipped
undocumented and the consumer, contractually correct, never looked for
it.

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
from .nest import Kind, Region, ink_only, nest
from .raster import InkMask, iter_runs
from .version import resolve as resolve_version
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


def because(*facts) -> list:
    """The measured facts that produced a semantic type (S4).

    A type without its evidence is an assertion; with it, a consumer
    can disagree on the threshold without re-deriving the measurement.
    Each fact is `name value test threshold` -- e.g. `holes 14 >= 2`,
    `fill 0.06 < 0.35` -- so it reads as a sentence and parses on
    whitespace. The facts are exactly the quantities the branch
    tested: change a threshold and this list changes with it, because
    both come from the same call site.
    """
    return [f for f in facts if f]


def _fact(name, value, test, threshold) -> str:
    v = f"{value:.3g}" if isinstance(value, float) else str(value)
    t = f"{threshold:.3g}" if isinstance(threshold, float) else str(threshold)
    return f"{name} {v} {test} {t}"


def lattice_holes(n, region_id, min_cell: float = 0.0):
    """(holes passing the cell floor, holes before it).

    ONE definition, because two callers depend on the same quantity:
    `table_lines` tests it (>= 2 makes a lattice) and `page_lines`
    reports it as the diagram's evidence. The first version recomputed
    nothing and the diagram simply printed the RAW hole count, so a
    region with ten glyph-sized counters emitted `holes 10 < 2` -- a
    false statement in the evidence field, which is worse than no
    evidence at all.
    """
    holes = [n.regions[h] for h in n.holes_of(region_id)]
    raw = len(holes)
    if min_cell > 0.0:
        holes = [h for h in holes
                 if (h.x1 - h.x0 + 1) >= min_cell
                 and (h.y1 - h.y0 + 1) >= min_cell]
    return holes, raw


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
    holes, n_holes_raw = lattice_holes(n, region_id, min_cell)
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
    w = moments.x1 - moments.x0 + 1
    h = moments.y1 - moments.y0 + 1
    fill = moments.area / max(1, w * h)
    rule_w = sorted({min(r.x1 - r.x0 + 1, r.y1 - r.y0 + 1)
                     for r in n.regions.values()
                     if r.kind is Kind.INK and is_rule(r)
                     and r.x0 >= moments.x0 and r.x1 <= moments.x1
                     and r.y0 >= moments.y0 and r.y1 <= moments.y1})
    why = because(
        _fact("holes", len(holes), ">=", 2),
        _fact("holes_before_cell_floor", n_holes_raw, ">=", len(holes)),
        _fact("cell_floor_px", min_cell, "applied_to", n_holes_raw)
        if min_cell > 0.0 else "",
        f"fill {fill:.3g}",
        f"rule_widths_px {','.join(map(str, rule_w))}" if rule_w else
        "rule_widths_px none",
        f"lattice {rows}x{cols}")
    out = [_line("table", (moments.x0, moments.y0,
                           moments.x1 + 1, moments.y1 + 1), pt,
                 cell_row=None, cell_column=None,
                 ink={"region_id": region_id,
                      "holes": len(holes), "rows": rows, "columns": cols,
                      "because": why})]
    for box, (r, c, rs, cs) in zip(boxes, grid):
        cw, ch = box[2] - box[0], box[3] - box[1]
        held = len(n.ink_in_hole(
            next(hh.id for hh in holes
                 if (hh.x0, hh.y0) == (box[0], box[1]))))
        out.append(_line("simple_cell", box, pt,
                         cell_row=r, cell_column=c,
                         cell_row_span=rs, cell_col_span=cs,
                         ink={"because": because(
                             _fact("width_px", cw, ">=", min_cell)
                             if min_cell > 0.0 else f"width_px {cw}",
                             _fact("height_px", ch, ">=", min_cell)
                             if min_cell > 0.0 else f"height_px {ch}",
                             f"contains {held}",
                             f"hole_of_table {region_id}")}))
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


def _overlaps(a, b) -> bool:
    """Boxes intersect at all. Used to decide whether the two routes
    are looking at the same object, so it is deliberately generous --
    a partial overlap means one report, not two."""
    return not (a.x1 < b.x0 or b.x1 < a.x0 or a.y1 < b.y0 or b.y1 < a.y0)


def _contains(outer, inner) -> bool:
    return (outer.x0 <= inner.x0 and outer.y0 <= inner.y0
            and outer.x1 >= inner.x1 and outer.y1 >= inner.y1)


def diagram_line(region, pt: float, *, ground: str | None = None,
                 contains: int | None = None, max_fill: float | None = None,
                 min_diagram: float | None = None,
                 holes: int | None = None) -> dict:
    """A hollow rectangle that is not a table, or a textured region.

    `contains` is the number of separate ink components sitting inside
    this region's holes -- the evidence for the call, not a summary of
    it. A consumer that wants a stricter rule than "at least one" can
    apply its own cut without re-running `nest`.

    `route` says WHICH route found it: `"ink"` for white enclosed by one
    component (`nest`), `"white"` for content between ink (the gap
    route). Neither subsumes the other and both run, so a consumer
    seeing two lines over one object -- page 7 of 2409.18839 is that
    case, the grey frame from the ink and its interior from the white --
    can tell they are two views rather than a duplicate.
    """
    # `route` is "ink" by construction -- a `diagram` is only ever
    # produced by the nest path. It was briefly a parameter with one
    # possible value, which no test could distinguish from a constant.
    ink = {"region_id": region.id, "route": "ink",
           "fill": region.area / max(
               1, (region.x1 - region.x0 + 1) * (region.y1 - region.y0 + 1))}
    if contains is not None:
        ink["contains"] = contains
    if ground is not None:
        ink["border_ground"] = ground
    # S4: the branch's own quantities, so the call can be disagreed
    # with on the threshold instead of re-derived. `max_fill` and
    # `min_diagram` are the caller's cuts; passing them makes the
    # evidence follow a retuned threshold automatically.
    w = region.x1 - region.x0 + 1
    h = region.y1 - region.y0 + 1
    ink["because"] = because(
        (f"border_ground {ground} is textured" if ground == "textured"
         else (_fact("fill", ink["fill"], "<", max_fill)
               if max_fill is not None else f"fill {ink['fill']:.3g}")),
        (_fact("longest_side_px", max(w, h), ">=", min_diagram)
         if min_diagram is not None else f"longest_side_px {max(w, h)}"),
        (_fact("contains", contains, ">=", 1)
         if contains is not None else ""),
        (_fact("holes", holes, "<", 2) if holes is not None else ""))
    return _line("diagram", (region.x0, region.y0,
                             region.x1 + 1, region.y1 + 1), pt,
                 cell_row=None, cell_column=None, ink=ink)


def gap_mask(mask, *, min_gap: float):
    """White runs that look like GAPS rather than margins.

    Two rules, and the first is the whole trick: a white run touching
    the scan-line edge is a MARGIN -- white connects around every object
    through the page border, so keeping those gives one page-sized blob.
    Discarding them disconnects the page into layout.

    `min_gap` is in PIXELS; the caller converts from points, because a
    constant here would be retuned by a dpi change.
    """
    W, H = mask.width, mask.height
    inv = mask.inverted()
    buf = bytearray(W * H)
    for axis in ("row", "col"):
        limit = W if axis == "row" else H
        for r in iter_runs(inv, axis):
            n = r.hi - r.lo + 1
            if r.lo == 0 or r.hi == limit - 1 or n < min_gap:
                continue
            if axis == "row":
                b = r.line * W
                buf[b + r.lo:b + r.hi + 1] = b"\xff" * n
            else:
                buf[r.lo * W + r.line:r.hi * W + r.line + 1:W] = b"\xff" * n
    return InkMask(bytes(buf), W, H)


def merge_boxes(boxes, tol: float):
    """Union boxes whose rectangles touch or overlap within `tol`, to a
    fixed point.

    Runs BEFORE any size filter: dropping small pieces first would
    discard exactly the fragments that need joining. Measured on 14
    labelled figures, this moves `fragmented` from 7 to 5 and `matched`
    from 6 to 8 -- which is what took fragmented off the top and made
    the route worth wiring.
    """
    if tol < 0:
        raise ValueError(f"tol must be non-negative, got {tol}")
    cur = list(boxes)
    while True:
        parent = list(range(len(cur)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        order = sorted(range(len(cur)), key=lambda i: cur[i][0])
        merged = False
        for a in range(len(order)):
            ia = order[a]
            for b in range(a + 1, len(order)):
                ib = order[b]
                if cur[ib][0] > cur[ia][2] + tol:
                    break
                if (cur[ia][0] - tol <= cur[ib][2]
                        and cur[ib][0] - tol <= cur[ia][2]
                        and cur[ia][1] - tol <= cur[ib][3]
                        and cur[ib][1] - tol <= cur[ia][3]):
                    ra, rb = find(ia), find(ib)
                    if ra != rb:
                        parent[ra] = rb
                        merged = True
        if not merged:
            return cur
        groups = {}
        for i in range(len(cur)):
            r = find(i)
            g = groups.get(r)
            groups[r] = cur[i] if g is None else (
                min(g[0], cur[i][0]), min(g[1], cur[i][1]),
                max(g[2], cur[i][2]), max(g[3], cur[i][3]))
        cur = list(groups.values())


def content_blocks(mask, *, pt: float, min_gap_pt: float = 10.8,
                   min_block_pt: float = 36.0, merge_tol_pt: float = 1.5):
    """Content blocks: the COMPLEMENT of the gap mask (the white route).

    `nest` finds white ENCLOSED BY ONE COMPONENT; this finds white
    BETWEEN ink. Neither subsumes the other, which is why both run --
    a plot whose data touches its own frame encloses nothing and is
    invisible to `nest`, while a `\fbox` is invisible here.

    Defaults are the measured ones expressed in POINTS: 10.8 pt is the
    60 px gap floor at 400 dpi, 36 pt the 200 px block floor, 1.5 pt the
    8 px merge tolerance. In page pixels they would be retuned by a dpi
    change.

    A PAGE-SPANNING block is dropped before merging, not after. It
    touches every other box, so merging with it in the list swallows the
    whole page -- 13 boxes became 1 at a tolerance of one pixel.
    """
    area = mask.width * mask.height
    if not area:
        return []
    mo = moments_per_component(
        sweep(gap_mask(mask, min_gap=min_gap_pt / pt).inverted(),
              conn=8, capture=Capture.NONE))
    floor = min_block_pt / pt
    raw = [(c.x0, c.y0, c.x1 + 1, c.y1 + 1) for c in mo.values()
           if c.width >= floor / 4 and c.height >= floor / 4
           and c.width * c.height < 0.8 * area]
    if merge_tol_pt:
        raw = merge_boxes(raw, merge_tol_pt / pt)
    return [b for b in raw
            if b[2] - b[0] >= floor and b[3] - b[1] >= floor
            and (b[2] - b[0]) * (b[3] - b[1]) < 0.8 * area]


def _box_of(line, pt: float):
    """A `Region` recovering the pixel box of an emitted line, so a rule
    can be attached to it like any other object."""
    r = line["region"]
    x0 = int(round(r["top_left_x"] / pt))
    y0 = int(round(r["top_left_y"] / pt))
    return Region(-1, Kind.INK, -1, 0, x0, y0,
                  x0 + int(round(r["width"] / pt)) - 1,
                  y0 + int(round(r["height"] / pt)) - 1)


def _white_lines(mask, pt: float, known, enabled: bool):
    """THE SECOND ROUTE, as lines.

    `nest` finds white ENCLOSED BY ONE COMPONENT; this finds content
    BETWEEN ink. Neither subsumes the other, so both run -- a plot whose
    data touches its own frame encloses nothing and is invisible to
    `nest`, while an `\fbox` is invisible here.

    Measured over 14 labelled figures with the fragments merged:
    matched 8, fragmented 5, missed 1. Fragmented is no longer the
    largest class, which is what made this worth wiring. On a text page
    it emits 0-2 blocks, so it does not flood.

    THE TYPE IS `block`, NOT `diagram`, and that is a measurement rather
    than a decision. On a scanned text page this route returns the
    paragraph blocks -- 33 and 113 components at exactly the page's text
    scale -- and calling those `diagram` is the F1 defect again. But a
    gate on content profile cannot fix it either: Infineon p10, the
    connected plot this route exists for, profiles at 0.91x the text
    scale against the text blocks' 1.00x, so ANY text-block filter tight
    enough to reject the text would reject the motivating case. Measured
    rather than assumed.

    So the line says what was found -- a region of content bounded by
    white on every side -- and leaves "is it a figure" to the consumer,
    which is the same call as emitting a rule's width instead of
    `\toprule`.

    NO OVERLAP SUPPRESSION. Both routes contribute; page 7 of
    2409.18839 is the case where they fire on one object from opposite
    sides, the grey frame from the ink and its interior from the white,
    and suppressing either loses half the evidence.
    """
    if not enabled:
        return []
    out = []
    for x0, y0, x1, y1 in content_blocks(mask, pt=pt):
        box = Region(-1, Kind.INK, -1, (x1 - x0) * (y1 - y0),
                     x0, y0, x1 - 1, y1 - 1)
        out.append(_line("block", (x0, y0, x1, y1), pt,
                         cell_row=None, cell_column=None,
                         ink={"route": "white"}))
    return out


def component_topology(mask):
    """Per ink component: identity, geometry, and every topological
    channel the units provide (T24). Read-only -- shares nothing with
    the emit path.

    `id` is `Component.root` (the ONE identity; `nodes[0]` is not it).
    `holes` is the sweep's cycle rank; chi = 1 - holes for a single
    component. Events are attributed via `component_of`. The Reeb
    6-tuple and the termini 4-tuple are computed on a crop painted
    from the component's OWN runs, so a neighbour overlapping the
    bbox cannot leak in. `principal_axis` is a unit vector -- the
    core stores no angles.
    """
    from .reeb import graph_of, signature
    from .sweep import termini

    res = sweep(mask, axis="row", conn=8, capture=Capture.GRAPH)
    moms = moments_per_component(res)
    ev = {}
    for e in res.events:
        root = res.component_of(e.node).root
        ev.setdefault(root, {})[e.kind.value] =             ev.setdefault(root, {}).get(e.kind.value, 0) + 1
    out = []
    for comp in res.components:
        m = moms[comp.root]
        x0, y0, x1, y1 = m.x0, m.y0, m.x1, m.y1
        w, h = x1 - x0 + 1, y1 - y0 + 1
        buf = bytearray(w * h)
        for nid in comp.nodes:
            n = res.nodes[nid]
            row = n.line - y0
            buf[row * w + n.lo - x0:row * w + n.hi - x0 + 1] =                 b"\xff" * (n.hi - n.lo + 1)
        crop = InkMask(bytes(buf), w, h)
        rt = termini(sweep(crop, axis="row", conn=8,
                           capture=Capture.GRAPH))
        ct = termini(sweep(crop, axis="col", conn=8,
                           capture=Capture.GRAPH))
        sig = signature(graph_of(crop))
        out.append({
            "id": comp.root,
            "bbox": [x0, y0, x1, y1],
            "area": m.area,
            "centroid": list(m.centroid),
            "principal_axis": list(m.principal_axis),
            "holes": comp.holes,
            "chi": 1 - comp.holes,
            "events": ev.get(comp.root, {}),
            "reeb": list(sig),
            "termini": [rt[0], rt[1], ct[0], ct[1]],
        })
    return out



def glyph_line(region, pt: float, *, holes: int = 0, axis=None,
               components: int = 1, candidates=None, parts=None,
               topology=None) -> dict:
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

    `components` is the number of ink components this glyph is made of
    -- 2 for `i`, `j` and an umlaut, 3 for a dotted umlaut, 1 for most
    letters. `mathstruct.group()` decides; `emit` only reports it.

    `parts` lists the member region ids and is ABSENT for a
    single-component glyph, where it would repeat `region_id` on every
    line of a page. `region_id` is the lowest member id, so it remains
    a stable handle for the glyph as a whole.

    `topology` (T26) is the per-cluster {holes, chi, reeb, termini}
    from `component_topology`, present only on the `--glyphs` route --
    the default path is pinned byte-identical by the T23 oracle. Its
    `holes` comes from the SWEEP cycle rank where the sibling
    `ink.holes` comes from `nest`; equal values are the two routes
    checking each other in every emitted line, and a difference is a
    finding, which is why the duplication is kept.
    """
    ink = {"region_id": region.id, "area": region.area, "holes": holes,
           "components": components}
    if topology is not None:
        ink["topology"] = topology
    if parts is not None and len(parts) > 1:
        ink["parts"] = list(parts)
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


def _clustered(mask, pairs, pt, classifier, top_k, topology=False):
    """Ink regions -> GLYPH lines, one per `group()` cluster (A1).

    A glyph is not a component: `i`, `j`, `:` and every umlaut are two
    or three, and a per-component line hands a classifier half a letter.
    `mathstruct.group()` joins them, bounded to a text row.

    A cluster's box is the union of its members' and its axis comes
    from the SUM of their moments -- exact, because raw moment sums are
    integers and moments add. Taking the largest member's axis would be
    a proxy where an exact value is available.
    """
    from .mathstruct import Glyph as _G, group as _group
    keep = [(r, h) for r, h in pairs if not is_rule(r)]
    if not keep:
        return []
    by_id = {r.id: (r, h) for r, h in keep}
    clusters = _group([_G(r.id, float(r.x0), float(r.y0),
                          float(r.x1), float(r.y1)) for r, _ in keep])

    moms = {}
    for c in moments_per_component(
            sweep(mask, conn=8, capture=Capture.GRAPH)).values():
        key = (c.x0, c.y0, c.x1, c.y1, c.area)
        moms[key] = None if key in moms else c

    out = []
    for ids in clusters:
        members = [by_id[i] for i in ids if i in by_id]
        if not members:
            continue
        regs = [r for r, _ in members]
        box = Region(min(r.id for r in regs), Kind.INK, -1,
                     sum(r.area for r in regs),
                     min(r.x0 for r in regs), min(r.y0 for r in regs),
                     max(r.x1 for r in regs), max(r.y1 for r in regs))
        total = None
        for r in regs:
            m = moms.get((r.x0, r.y0, r.x1, r.y1, r.area))
            if m is None:
                total = None
                break
            total = m if total is None else total + m
        topo = _cluster_topology(mask, box, regs) if topology else None
        out.append((box, glyph_line(
            box, pt, holes=sum(h for _, h in members),
            components=len(regs), parts=sorted(r.id for r in regs),
            axis=total.principal_axis if total is not None else None,
            candidates=_candidates_for(mask, box, classifier, top_k),
            topology=topo)))
    return out


def _cluster_topology(mask, box, regs):
    """The cluster's {holes, chi, reeb, termini} (T26).

    Runs `component_topology` on the bbox crop and keeps ONLY the
    components whose offset bbox and area match a member region --
    the crop deliberately contains neighbouring ink (`_crop`'s
    convention, kept for the classifier), and a neighbour's topology
    in this cluster's record would be the leak T24's dot-in-a-ring
    test exists to forbid. Counts add over a disjoint union, so the
    member sums ARE the cluster values."""
    want = {}
    for r in regs:
        k = (r.x0, r.y0, r.x1, r.y1, r.area)
        want[k] = want.get(k, 0) + 1
    holes = chi = 0
    reeb = [0] * 6
    term = [0] * 4
    for c in component_topology(_crop(mask, box)):
        k = (c["bbox"][0] + box.x0, c["bbox"][1] + box.y0,
             c["bbox"][2] + box.x0, c["bbox"][3] + box.y0, c["area"])
        if not want.get(k):
            continue
        want[k] -= 1
        holes += c["holes"]
        chi += c["chi"]
        reeb = [a + b for a, b in zip(reeb, c["reeb"])]
        term = [a + b for a, b in zip(term, c["termini"])]
    return {"holes": holes, "chi": chi, "reeb": reeb, "termini": term}


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
    return [ln for _, ln in _clustered(mask, pairs, pt, classifier,
                                       top_k, topology=True)]


def page_lines(mask, *, pt: float, tol: float = 0.0, grounds=None,
               max_fill: float = 0.35, cell_scale: float = 3.0,
               diagram_scale: float = 3.0, require_content: bool = True,
               glyphs: bool = False, classifier=None,
               top_k: int = 8, white_route: bool = True):
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
        # Nothing structural is possible for the INK route. Holes come
        # from the cycle rank, which IS the per-component hole count --
        # checked against `nest` on every page measured.
        #
        # The WHITE route still runs: it finds content between ink and
        # owes nothing to enclosure, so a page with no enclosing
        # component is exactly where it is the only route there is.
        # Returning early here was the first version and it made the
        # second route unreachable on every text page -- the same
        # "built but not wired" failure it was added to fix.
        head = (_glyphs_only(mask, pairs, pt, classifier, top_k)
                if glyphs else [])
        return head + _white_lines(mask, pt, [], white_route)

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
            out.append((region, [diagram_line(
                region, pt, ground=ground, contains=held,
                max_fill=max_fill, min_diagram=min_diagram,
                holes=len(lattice_holes(n, region.id, min_cell)[0]))]))

    if glyphs:
        # One line per CLUSTER, not per component (A1). `_clustered`
        # holds the id-space join and the moment sum; both paths use it
        # so a page with a table and a page without cannot describe a
        # glyph differently.
        done = {r.id for r, _ in out}
        rest = [(r, len(n.holes_of(r.id))) for r in inks
                if r.id not in done and r.id not in rule_ids]
        out.extend((box, [ln]) for box, ln in
                   _clustered(mask, rest, pt, classifier, top_k))

    white = _white_lines(mask, pt, [r for r, _ in out], white_route)
    out.extend((_box_of(l, pt), [l]) for l in white)

    # Each rule attaches to the INNERMOST containing TABLE or DIAGRAM
    # line only. Two decisions, both audited:
    #
    # * innermost, because the first form attached to every container
    #   and a rule inside a frame inside a frame arrived three times;
    # * table/diagram only, because `block` and `glyph` boxes come from
    #   OTHER partitions (the white route, the cluster union) and can
    #   share a box with a diagram -- the nested fixture had a diagram
    #   and a block both at the same size, decided by iteration order.
    #   "Ties cannot arise" was claimed of the first fix and was wrong;
    #   restricting the target types is what actually removes them,
    #   since one component cannot be two ink regions.
    owner: dict[int, tuple] = {}
    for region, lines in out:
        if lines[0]["type"] not in ("table", "diagram"):
            continue
        size = ((region.x1 - region.x0 + 1) * (region.y1 - region.y0 + 1))
        for r in rules:
            if _contains(region, r):
                cur = owner.get(r.id)
                if cur is None or size < cur[0]:
                    owner[r.id] = (size, lines)
    by_target: dict[int, list] = {}
    for r in rules:
        if r.id in owner:
            by_target.setdefault(id(owner[r.id][1]), []).append(r)
    for region, lines in out:
        mine = by_target.get(id(lines))
        if mine:
            lines[0].setdefault("ink", {})["rules"] = [
                rule_record(r, pt) for r in
                sorted(mine, key=lambda r: (r.y0, r.x0))]
    return [ln for _, lines in out for ln in lines]


def free_rules(mask, *, pt: float, regions=None) -> list[dict]:
    """Rules bound for `page["ink"]["rules"]` -- enclosed by nothing (A4).

    Name the KEY, not this function, when talking to a consumer: a
    report that said "the free_rules array" sent the consumer looking
    for a JSON key that does not exist.

    A `|l|l|` table's rules ARE the frame -- one connected component --
    so they are not regions and never appear here. **A booktabs table
    draws disjoint rules and encloses nothing**, so its rules are
    free-standing components that no emitted object contains, and
    `page_lines` therefore attaches them to nothing. Measured across
    seven corpus pages: 33 rules found, **0 reaching the file**.

    They are reported on the PAGE rather than as lines of their own,
    which keeps `emit`'s standing rule -- a rule is a measurement
    attached to an object, not an object -- while not silently dropping
    the only evidence a booktabs table leaves.

    "Free" is decided by geometry alone: a rule inside a frame is
    enclosed by that frame's region and is excluded, so this does not
    duplicate what `page_lines` already attaches. It says nothing about
    which rule is a `\toprule`; that needs the table's context and
    belongs to the consumer.
    """
    # A plain list of ink regions, so a caller can hand in either
    # `ink_only(mask).regions` or `ink_regions(nest(mask))` without this
    # function having to know which shape it was given -- guessing
    # between a list and a dict by `hasattr` was the first version and
    # it raised on the second caller.
    if regions is None:
        regions = ink_only(mask).regions
    inks = [r for r in regions if r.kind is Kind.INK]
    rules = [r for r in inks if is_rule(r)]
    others = [r for r in inks if not is_rule(r)]
    out = []
    for r in rules:
        if any(o is not r and _contains(o, r) for o in others):
            continue
        out.append(rule_record(r, pt))
    return sorted(out, key=lambda d: (d["y0"], d["x0"]))


def _full_bands(counts, total, span):
    """Contiguous runs of lines whose ink reaches `span` x `total`.

    Returns [(lo, hi)] in index space, inclusive.
    """
    need = span * total
    out, run = [], None
    for i, c in enumerate(counts):
        if c >= need:
            run = (run[0], i) if run else (i, i)
        elif run:
            out.append(run)
            run = None
    if run:
        out.append(run)
    return out


def is_delimiter(mask, region, *, span: float = 0.9, end: float = 0.1,
                 band: float = 0.25, min_aspect: float = 3.0) -> bool:
    """Is this component a bracket -- a stem with a serif at each end?

    The other half of 200's measurement. `crossing_rules` answers "is
    this two rules fused"; this answers "is this a delimiter", and the
    two are decided by the SAME structure read the opposite way:

        stem      exactly one full-height vertical band, thin
        serifs    full-width horizontal bands, ALL of them at an END
                  -- measured at normalised 0.005 and 0.985

    A rule crossing has an INTERIOR band and is refused here; a
    delimiter has none and is refused by `crossing_rules`. Neither
    function can claim a component the other claims, which is the
    property that makes them safe to run over the same page.

    `min_aspect` is 3 rather than 10: a delimiter is bounded by the
    expression it encloses and a two-row matrix's bracket is squat.
    It exists only to refuse a solid blob, which the band tests
    already largely do.

    A parenthesis has no straight stem and is NOT detected. That is a
    stated limit, not an oversight -- this reads `[`, `]` and `|`,
    which is what the corpus's matrices use.
    """
    x0, y0, x1, y1 = region.x0, region.y0, region.x1, region.y1
    w, h = x1 - x0 + 1, y1 - y0 + 1
    if w < 2 or h < min_aspect * w:
        return False
    data, W = mask.data, mask.width
    cols = [sum(1 for y in range(y0, y1 + 1) if data[y * W + x])
            for x in range(x0, x1 + 1)]
    rows_ = [sum(1 for x in range(x0, x1 + 1) if data[y * W + x])
             for y in range(y0, y1 + 1)]
    vb = _full_bands(cols, h, span)
    if len(vb) != 1 or (vb[0][1] - vb[0][0] + 1) > band * w:
        return False
    hb = _full_bands(rows_, w, span)
    if not hb:
        return False

    def interior(b):
        c = (b[0] + b[1]) / 2.0 / max(1, h - 1)
        return end < c < 1.0 - end
    return not any(interior(b) for b in hb)


def crossing_rules(mask, region, *, span: float = 0.9,
                   end: float = 0.1, band: float = 0.25,
                   min_aspect: float = 10.0) -> list:
    """Split one component into the rules it fuses, or refuse.

    A `{c|c}` array's column rule and its horizontal rule
    INTERSECT, so
    8-connectivity merges them into a single component -- a cross,
    fill about 0.02-0.06, aspect near 1. `is_rule` refuses it on both
    counts and `ink.rules[]` reports neither rule. Measured on
    Mielke's report: three 2x2 arrays (196) and one 4x4 (200), six
    rules in all, none of them found.

    THE DISCRIMINATOR IS MEASURED, and it is what separates a rule
    crossing from a BRACKET -- both are tall, thin-inked components
    with a full-height vertical band, so the vertical band alone
    cannot tell them apart:

      a DELIMITER has full-width horizontal bands at BOTH ENDS of
      its stem -- a stem with two serifs. Measured: bands at
      y-offsets 0-2 and 197 of 200, i.e. 0.005 and 0.985 normalised.
      a CROSSING has ONE, in the middle. Measured: 0.50 on the 2x2
      arrays, 0.743 on the 4x4.

    The separation is two orders of magnitude wide in normalised
    position -- 0.005/0.985 against 0.50/0.74 -- so `end` at 0.1 is
    free rather than tuned. `span` is likewise not delicate: every
    measured band reached 100% of its axis, not 90%.

    Returns a list of rule records, one per constituent rule, or an
    EMPTY LIST when the component is not a crossing. Refusing is the
    common case and must stay cheap: this is called on every low-fill
    component on a page.
    """
    x0, y0, x1, y1 = region.x0, region.y0, region.x1, region.y1
    w, h = x1 - x0 + 1, y1 - y0 + 1
    if w < 3 or h < 3:
        return []
    data, W = mask.data, mask.width
    cols = [sum(1 for y in range(y0, y1 + 1) if data[y * W + x])
            for x in range(x0, x1 + 1)]
    rows_ = [sum(1 for x in range(x0, x1 + 1) if data[y * W + x])
             for y in range(y0, y1 + 1)]
    vb = _full_bands(cols, h, span)
    hb = _full_bands(rows_, w, span)
    if len(vb) != 1 or not hb:
        return []
    # A RULE IS THIN. Without this, any SOLID blob qualifies: every
    # column of a 28x3 bar is full-height and every row full-width, so
    # it presents exactly one vertical band and one horizontal band
    # whose centre sits at 0.5 -- arithmetically identical to a
    # crossing. Ten such components split on the first run, including
    # three equals signs and five 4x4 dots.
    #
    # Measured band thickness as a fraction of the perpendicular
    # extent: the real crossings are 3/548 = 0.005 and 3/202 = 0.015;
    # a solid bar is 1.000. Two orders of magnitude, so 0.25 is free.
    if (vb[0][1] - vb[0][0] + 1) > band * w:
        return []
    hb = [b for b in hb if (b[1] - b[0] + 1) <= band * h]
    if not hb:
        return []
    # a band whose CENTRE sits within `end` of either extreme is a
    # serif, not a rule: that is the bracket's signature.
    def interior(b):
        c = (b[0] + b[1]) / 2.0 / max(1, h - 1)
        return end < c < 1.0 - end
    inner = [b for b in hb if interior(b)]   # [] means a delimiter
    # EVERY PIECE THE SPLIT EMITS MUST ITSELF BE RULE-SHAPED. Without
    # this a 5x5 dot with one 1 px column and one 1 px row satisfies
    # every band condition -- it has a full-height vertical band, a
    # full-width horizontal band, and the band is thin relative to a
    # 5 px extent. Measured aspects of the real crossings' arms: 27,
    # 34, 34, 67 and 183. The false positives sit at 5.
    #
    # The floor is 10 rather than `is_rule`'s 20 because a crossing's
    # arm is bounded by the MATRIX, not by the page: a 2x2 array's
    # rule is legitimately short. 10 is below every measured real arm
    # and above every measured false one.
    vt = vb[0][1] - vb[0][0] + 1
    if h < min_aspect * vt:
        return []
    inner = [b for b in inner if w >= min_aspect * (b[1] - b[0] + 1)]
    if not inner:
        return []
    out = [{"orientation": "vertical",
            "x0": x0 + vb[0][0], "x1": x0 + vb[0][1],
            "y0": y0, "y1": y1}]
    for b in inner:
        out.append({"orientation": "horizontal",
                    "x0": x0, "x1": x1,
                    "y0": y0 + b[0], "y1": y0 + b[1]})
    return out


def rule_context(mask, rule, *, pt: float, reach: float = 1.0) -> dict:
    """Ink above and below one rule, within `reach` x its own length.

    A rule alone says nothing about what it does. The same 2 px
    horizontal bar is a fraction bar, an overline, an underline or a
    booktabs separator, and the four are told apart by WHAT SITS
    AROUND IT -- which is ink, and therefore measurable here without
    knowing a single symbol.

    The band is the rule's own x-span by `reach` x its length in y,
    clipped to the page. Scaling the band to the RULE rather than to
    a page constant is the point: a fraction bar under a 12 pt
    numerator and a booktabs rule spanning a 400 pt table need the
    same test, and any band expressed in pixels or points fits one
    and not the other.

    Returns the two coverages as ink fraction of band area, the band
    heights actually used after clipping, and the rule's length --
    NOT a class. `qc` sets the precedent and the reason is the same:
    the cut between "ink above" and "no ink above" is a threshold on
    a continuum, the caller has the page's own statistics, and a
    classifier buried here would fix that cut for every caller. The
    four names in 116 -- fraction, overline, underline, separator --
    are `above and below`, `above only`, `below only`, `neither`,
    and the caller supplies the presence test.

    A vertical rule returns zero coverage in both bands rather than
    being refused: the bands are defined off the long axis, and for a
    vertical rule they lie beside it, not above and below. Callers
    filtering to horizontal rules should do so on `horizontal` in the
    rule record; this function does not silently reinterpret one
    orientation as the other.
    """
    x0 = int(round(rule["x0"] / pt)); x1 = int(round(rule["x1"] / pt))
    y0 = int(round(rule["y0"] / pt)); y1 = int(round(rule["y1"] / pt))
    w, h = x1 - x0, y1 - y0
    length = max(w, h)
    band = max(1, int(round(reach * length)))
    if h >= w:                       # vertical: no above/below to read
        return {"above": 0.0, "below": 0.0, "band_above_px": 0,
                "band_below_px": 0, "length_px": length,
                "vertical": True}

    def cover(ya, yb):
        ya = max(0, ya); yb = min(mask.height, yb)
        xa = max(0, x0); xb = min(mask.width, x1)
        if yb <= ya or xb <= xa:
            return 0.0, 0
        n = 0
        data = mask.data
        for y in range(ya, yb):
            row = data[y * mask.width + xa: y * mask.width + xb]
            n += len(row) - row.count(0)
        return n / float((yb - ya) * (xb - xa)), yb - ya

    above, ha = cover(y0 - band, y0)
    below, hb = cover(y1, y1 + band)
    return {"above": above, "below": below, "band_above_px": ha,
            "band_below_px": hb, "length_px": length, "vertical": False}


def page_record(*, page: int, width_px: int, height_px: int, dpi,
                lines=(), rules=(), polarity=None) -> dict:
    """One page, with every coordinate in pt (G1, G2).

    `ink.rules` holds rules no emitted object encloses -- the booktabs
    case, where the table draws no frame and the rules are the only
    evidence it exists. Absent when there are none, so a page with no
    rules does not carry an empty array claiming they were looked for
    and found to be zero... which they were, so it is emitted whenever
    the caller passes the list, and omitted when it passes nothing.
    """
    pt = _pt_per_px(dpi)
    rec = {"page": page, "image_id": None,
           "page_width": width_px * pt, "page_height": height_px * pt,
           "lines": list(lines)}
    ink = {}
    if rules:
        ink["rules"] = list(rules)
    if polarity is not None:
        # `page["ink"]["polarity"]` -- present ONLY when the page was
        # read light-on-dark, absent for the print convention. A
        # consumer that maps coordinates back to the source image needs
        # to know the mask was inverted; the contract-gap lesson says
        # name the key, so: page["ink"]["polarity"] == "light-on-dark".
        ink["polarity"] = polarity
    if ink:
        rec["ink"] = ink
    return rec


def lines_json(pages, *, source: str = SOURCE, render_dpi: float) -> dict:
    """The document wrapper.

    `ocr.units` is `pt` and every region obeys it. MathPix emits its own
    pixel space and the consumer rescales; declaring the space removes
    the guess, and mixing the two conventions in one file is how a scale
    error hides.

    `ocr.producer` and `ocr.version` say WHAT WROTE THIS (A2). Without
    them, a consumer re-running inkdrill and getting identical bytes
    cannot tell "nothing changed" from "the change could not reach this
    path" -- and the second is not hypothetical: `group()` was fixed
    while unreachable from the CLI, so a downstream re-run was
    byte-identical and correctly so. `version` is the git commit, or
    `"unknown"` outside a checkout; see `version.py` for why that is
    not a fabricated constant.
    """
    return {"source": source,
            "ocr": {"units": "pt", "render_dpi": float(render_dpi),
                    "producer": source, "version": resolve_version()},
            "pages": list(pages)}
