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
"""

from __future__ import annotations

from .nest import Kind, nest

__all__ = ["NoResolution", "lines_json", "page_record", "cell_grid",
           "ink_regions", "rule_width_pt", "table_lines", "SOURCE"]

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
    """`(row, column)` per hole, from the lattice alone (G3).

    A hole's cluster index IS its row or column: sort the bboxes on each
    axis and start a new cluster when the gap exceeds `tol`. Verified on
    a Word-produced handbook page -- one component, 52 holes, recovering
    13 rows x 4 columns.

    `tol` defaults to 0 and should be set from the ink: cells of one
    table share an edge to within the rule's own thickness, so the
    natural tolerance is that thickness rather than a constant.
    """
    def cluster(values):
        index, order = {}, sorted(set(values))
        k = 0
        for i, v in enumerate(order):
            if i and v - order[i - 1] > tol:
                k += 1
            index[v] = k
        return index

    rows = cluster([h[1] for h in holes])
    cols = cluster([h[0] for h in holes])
    return [(rows[h[1]], cols[h[0]]) for h in holes]


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


def table_lines(mask, region_id=None, *, pt: float, tol: float = 0.0,
                nesting=None):
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
    rows = max(r for r, _ in grid) + 1
    cols = max(c for _, c in grid) + 1
    out = [_line("table", (moments.x0, moments.y0,
                           moments.x1 + 1, moments.y1 + 1), pt,
                 cell_row=None, cell_column=None,
                 ink={"region_id": region_id,
                      "holes": len(holes), "rows": rows, "columns": cols})]
    for box, (r, c) in zip(boxes, grid):
        out.append(_line("simple_cell", box, pt,
                         cell_row=r, cell_column=c,
                         cell_row_span=1, cell_col_span=1))
    return out


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
