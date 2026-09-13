"""pagetables.py -- table and frame rectangles for a WHOLE PAGE, from ink.

WHY A PAGE-WIDE ENTRY POINT. `emit.table_lines` already finds a ruled
grid, but it must be handed a `nest` region id: the caller has to know
where the table is before asking where the table is. Nothing walks a
page and answers "what boxes are on it". That is what this does.

WHAT IT IS FOR. Not the tables MathPix already labels -- those come free
from `lines.json` and cost no raster at all (`table-rows.json`). The
question is the RESIDUAL: boxes on pages where MathPix labelled none.
pdfdrill's census gives that question an oracle for free -- 13,129
`figure_label` lines sit on pages with no table rect at all, and a
caption with no box is where a box is likely to have been missed.

THREE ROUTES, because a table comes in three shapes (measured on
kohlhase-omdoc p150 and gilmore p26/p30/p62, out/663):

  grid    a CLOSED ruled table. The cells are holes, so `nest` finds
          them and `emit.table_lines` returns the grid and its cells.
          omdoc p150: one table, 12 cells.
  rules   rules that do NOT touch (booktabs). `emit.free_rules` finds
          them -- gilmore p62 has 10 inside its two tables -- and they
          are clustered here into a box.
  frame   rules that TOUCH but close no cell. Neither route above sees
          them: gilmore p26's header rule and column rule join into one
          component of 1115 x 313 px holding 1.3% ink in its bounding
          box, too sparse to be a cell and too bent to pass as a rule.
          That sparsity IS the signal: a glyph reads 0.14.

WHAT IT DOES NOT DO. Captions. A `figure_label` is free-standing text
below or above the box (table captions above, figure captions below --
pdfdrill measured 7,474 above and 2,383 below, median gap 30 px at 250
dpi), and attaching one is a `lines.json` job that needs no ink. 662
settled the other half: bounding-box containment is a TEXT-LAYER
property and does not survive rasterisation.

CONSTANTS. Only `FRAME_MAX_INK` has a measurement behind it (0.012-0.013
for a touching-rule frame against 0.14 for a glyph). The rest are first
guesses, and calibrating them is what the run this tool exists for is
for. Do not quote them as decided.

    python3 tools/pagetables.py document <bibkey> --pages with-table
    python3 tools/pagetables.py document <bibkey> --pages caption-no-table
    python3 tools/pagetables.py page <bibkey> 150
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from inkdrill import emit, nest as nestmod, pngio                 # noqa: E402
from inkdrill.sweep import sweep                                  # noqa: E402
from tools.formulafind import frame_rect, page_frames             # noqa: E402

#: the page images are 400 dpi; `emit` speaks points, at `pt` per pixel
DPI = 400.0
PT = 72.0 / DPI
K = DPI / 72.0
#: ink over bounding box, above which a component is TEXT, not a frame.
#: Measured: gilmore p26 0.013, p30 0.012; a glyph 0.14 (out/663).
FRAME_MAX_INK = 0.05
#: a frame must span this share of the page width -- first guess
FRAME_MIN_WIDTH = 0.20
#: a rule cluster needs at least this many rules -- first guess
RULES_MIN = 2
#: two rules belong to one table when they overlap this much in x and
#: sit within this share of the page height of each other -- first guess
RULE_X_OVERLAP = 0.5
RULE_Y_GAP = 0.08
#: ink regions offered to `table_lines`, largest first -- cost control
GRID_REGIONS = 12
#: a match against MathPix's own rect counts from here -- first guess
IOU_HIT = 0.5


def _px(r):
    """an `emit` region (points) -> (x0, y0, x1, y1) in page pixels"""
    return (round(r["top_left_x"] * K), round(r["top_left_y"] * K),
            round((r["top_left_x"] + r["width"]) * K),
            round((r["top_left_y"] + r["height"]) * K))


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = ((a[2]-a[0]) * (a[3]-a[1]) + (b[2]-b[0]) * (b[3]-b[1]) - inter)
    return inter / union if union > 0 else 0.0


def grid_rects(mask, nesting):
    """Closed ruled grids: the cells are holes (`emit.table_lines`)."""
    out = []
    regions = sorted(emit.ink_regions(nesting),
                     key=lambda r: -(r.x1 - r.x0) * (r.y1 - r.y0))
    for r in regions[:GRID_REGIONS]:
        try:
            lines = emit.table_lines(mask, r.id, pt=PT, nesting=nesting)
        except Exception:
            continue
        cells = sum(1 for x in lines if x.get("type") == "simple_cell")
        for x in lines:
            if x.get("type") == "table":
                out.append(dict(route="grid", rect=_px(x["region"]), cells=cells))
    return out


def rule_rects(mask, page_h):
    """Rules that do not touch: cluster them into a box (booktabs)."""
    rules = [r for r in emit.free_rules(mask, pt=PT) if r.get("orient") == "h"]
    box = [(round(r["x0"] * K), round(r["y0"] * K),
            round(r["x1"] * K), round(r["y1"] * K)) for r in rules]
    box.sort(key=lambda b: b[1])
    out, used = [], [False] * len(box)
    for i, a in enumerate(box):
        if used[i]:
            continue
        group = [a]
        used[i] = True
        for j in range(i + 1, len(box)):
            if used[j]:
                continue
            b = box[j]
            ox = min(a[2], b[2]) - max(a[0], b[0])
            if ox <= 0:
                continue
            if ox / min(a[2] - a[0], b[2] - b[0]) < RULE_X_OVERLAP:
                continue
            if b[1] - group[-1][3] > RULE_Y_GAP * page_h:
                continue
            group.append(b)
            used[j] = True
        if len(group) >= RULES_MIN:
            out.append(dict(route="rules", rules=len(group),
                            rect=(min(g[0] for g in group), group[0][1],
                                  max(g[2] for g in group), group[-1][3])))
    return out


def frame_rects(result, page_w):
    """Rules that TOUCH: one sprawling component with almost no ink."""
    out = []
    for mo in result.moments.values():
        w, h = mo.x1 - mo.x0 + 1, mo.y1 - mo.y0 + 1
        if w < FRAME_MIN_WIDTH * page_w or h < 8:
            continue
        if mo.area / (w * h) > FRAME_MAX_INK:
            continue
        out.append(dict(route="frame", rect=(mo.x0, mo.y0, mo.x1, mo.y1),
                        ink=round(mo.area / (w * h), 4)))
    return out


def mathpix_boxes(page_record, frame):
    """MathPix's own rects on this page, in page pixels, by kind."""
    out = []
    for ln in page_record.get("lines") or []:
        kind = ln.get("type")
        if kind not in ("table", "diagram", "figure_label"):
            continue
        x, y, w, h = frame_rect(ln["region"], frame)
        out.append(dict(kind=kind, rect=(x, y, x + w, y + h)))
    return out


def measure_page(library, bib, page, frames, page_record):
    doc = library / bib
    png = doc / "inspect" / "pages" / f"p{page}.png"
    if page not in frames or not png.exists():
        return dict(page=page, refused="no page frame or no page image")
    mask = pngio.load_mask(str(png))
    nesting = nestmod.nest(mask)
    result = sweep(mask, conn=8, moments=True)
    found = (grid_rects(mask, nesting) + rule_rects(mask, mask.height)
             + frame_rects(result, mask.width))
    want = mathpix_boxes(page_record, frames[page])
    for w in want:
        best = max((iou(w["rect"], f["rect"]), f["route"]) for f in found) \
            if found else (0.0, None)
        w["best_iou"], w["by"] = round(best[0], 3), best[1]
    for f in found:
        best = max((iou(f["rect"], w["rect"]) for w in want), default=0.0)
        f["best_iou"] = round(best, 3)
    return dict(page=page, size=(mask.width, mask.height), found=found,
                mathpix=want)


def select(lj, how):
    """Which pages to measure. `caption-no-table` is the RESIDUAL set:
    a caption with no box is where a box was likely missed."""
    pages = []
    for i, pg in enumerate(lj.get("pages") or [], 1):
        kinds = {ln.get("type") for ln in (pg.get("lines") or [])}
        if how == "all":
            pages.append(i)
        elif how == "with-table" and ("table" in kinds or "diagram" in kinds):
            pages.append(i)
        elif how == "caption-no-table" and "figure_label" in kinds \
                and not ({"table", "diagram"} & kinds):
            pages.append(i)
    return pages


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("document", "page"):
        a = sub.add_parser(name)
        a.add_argument("bibkey")
        a.add_argument("--library", type=pathlib.Path,
                       default=pathlib.Path.home() / "pdfdrill-library")
        if name == "page":
            a.add_argument("pages")
        else:
            a.add_argument("--pages", default="with-table",
                           help="with-table | caption-no-table | all | 3,7,9")
            a.add_argument("--limit", type=int, default=0)
        a.add_argument("--out", type=pathlib.Path)
    args = ap.parse_args()
    lj = json.loads((args.library / args.bibkey /
                     f"{args.bibkey}.lines.json").read_text())
    frames, _ = page_frames(args.library, args.bibkey)
    if args.cmd == "page":
        pages = [int(p) for p in args.pages.split(",")]
    elif args.pages[0].isdigit():
        pages = [int(p) for p in args.pages.split(",")]
    else:
        pages = select(lj, args.pages)
        if args.limit:
            pages = pages[:args.limit]
    by_page = {i: pg for i, pg in enumerate(lj.get("pages") or [], 1)}
    out, tally = [], collections.Counter()
    for p in pages:
        rec = measure_page(args.library, args.bibkey, p, frames,
                           by_page.get(p, {}))
        out.append(rec)
        if rec.get("refused"):
            tally["refused"] += 1
            continue
        for f in rec["found"]:
            tally[f"found {f['route']}"] += 1
            if f["best_iou"] < IOU_HIT:
                tally[f"unmatched {f['route']}"] += 1
        for w in rec["mathpix"]:
            if w["kind"] == "figure_label":
                continue
            tally[f"mathpix {w['kind']}"] += 1
            if w["best_iou"] >= IOU_HIT:
                tally[f"covered by {w['by']}"] += 1
            else:
                tally[f"missed {w['kind']}"] += 1
    print(f"{args.bibkey[:40]}: {len(pages)} pages -> {dict(tally)}")
    if args.out:
        args.out.write_text(json.dumps(dict(bibkey=args.bibkey, pages=out,
                                            tally=dict(tally)), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
