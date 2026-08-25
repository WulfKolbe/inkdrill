"""inkdrill CLI -- a rendered page in, a `lines.json` out.

    python3 -m inkdrill page.png  -o page.lines.json
    python3 -m inkdrill page.pgm --dpi 400 -o page.lines.json
    python3 -m inkdrill page.pgm --dpi 400 --stats

This is the handover point. Until it existed, the only way to consume
inkdrill was to import it, which couples a caller to a stdlib-only
package it does not otherwise need. `lines.json` with namespaced `ink.*`
keys is the agreed interface; this writes it.

PNG carries its resolution in `pHYs` and PGM cannot, so `--dpi` is
required for a PGM and refused for a PNG -- the same discipline in both
directions, and a page whose points cannot be derived is an error rather
than a guess.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import time


def _cell_crop(mask, x0, y0, x1, y1):
    from .raster import InkMask
    w = x1 - x0 + 1
    h = y1 - y0 + 1
    buf = bytearray(w * h)
    for j in range(h):
        src = (y0 + j) * mask.width + x0
        buf[j * w:(j + 1) * w] = mask.data[src:src + w]
    return InkMask(bytes(buf), w, h)


def _table_cells(mask, tol, debug=None):
    """The page's table as {(row, col): hole bbox}. The table is the
    ink region with the most holes. A lattice slot whose hole is
    FRAGMENTED (cell content touching a rule splits the background
    region, so no single hole matches the cell) is filled from the
    intersection of its row's y-span and its column's x-span -- on the
    bh2 report page 1, two of eight scan cells were lost exactly this
    way before the fill existed.

    `debug` (T28), when a dict, receives `holes` (hole count of the
    table region), `shape` (nrows, ncols) and `backed` (the lattice
    slots a conforming hole was assigned to; every other emitted slot
    exists only because the median spans say so)."""
    from .emit import cell_grid
    from .nest import nest
    n = nest(mask)
    best, holes = None, []
    for r in n.regions.values():
        if r.kind.value != "ink":
            continue
        hs = n.holes_of(r.id)
        if len(hs) > len(holes):
            best, holes = r, hs
    if best is None or len(holes) < 2:
        return None
    if debug is not None:
        # the table region's own height, so a caller can ask what
        # fraction of it the detected rows actually cover
        debug["span"] = best.y1 - best.y0 + 1
    boxes = [(n.regions[h].x0, n.regions[h].y0,
              n.regions[h].x1 + 1, n.regions[h].y1 + 1) for h in holes]
    grid = cell_grid(boxes, tol=tol)
    cells = {(r, c): boxes[i] for i, (r, c, _, _) in enumerate(grid)}
    nrows = max(r for r, _ in cells) + 1
    ncols = max(c for _, c in cells) + 1
    # Every cell is defined by the lattice's MEDIAN row/col spans, not
    # by its own hole bbox. A cell whose content touches a rule merges
    # its hole with a neighbour's (bh2 report p1: the row-1 scan JPEG
    # crossed the header rule, so the header cell's hole spanned both
    # rows and read 42 components for the two words "Scan image"), and
    # a median over the conforming cells is immune to the merged one.
    from statistics import median
    colx = {c: (median(cells[k][0] for k in cells if k[1] == c),
                median(cells[k][2] for k in cells if k[1] == c))
            for c in range(ncols)}
    # PHANTOM COLUMNS (P15): a tall stroke touching both rules splits
    # a cell's hole, and the fragment clusters as its own column -- on
    # 0803.2924's report a 1 mm "column" sat inside the Rendered
    # column and shifted "last two columns" onto garbage. The DECIDER
    # is content: a lattice column is real when at least one
    # glyph-sized ink region (area >= 4 px, both dims >= 2 px) has its
    # centre inside the column's span within the table -- a fragment
    # of background contains none. The 2% width floor stays as a
    # cheap PRE-FILTER only: the measured margin (1.2% phantom vs
    # 2.8% narrowest real) is 0.8 points either side, too thin to
    # decide on, and a fragment can be arbitrarily wide (a 4.4% one
    # existed before the content test did).
    span = max(v[1] for v in colx.values()) - min(v[0] for v in colx.values())
    ty0, ty1 = best.y0, best.y1
    # CONTAINMENT: real columns are DISJOINT and tile the table width,
    # so a column whose x-span lies inside another's is not a column.
    # Measured on 1602.07462 p4 (the inline-formula page, declared with
    # four columns): the raw lattice has EIGHT, four of them nested in
    # col3's span, because short variable-width cells leave long white
    # tails that cluster into extra groups over 56 dense rows. The
    # width floor and the content test remove three; the fourth has
    # real ink in it and survives them both, and only containment
    # catches it. Needs no tolerance and leaves a real page untouched
    # (p1 of the same report: five disjoint spans, none contained).
    def _contained(c):
        for o in range(ncols):
            if o == c:
                continue
            wider = ((colx[o][1] - colx[o][0]) > (colx[c][1] - colx[c][0])
                     or ((colx[o][1] - colx[o][0])
                         == (colx[c][1] - colx[c][0]) and o < c))
            if wider and colx[o][0] <= colx[c][0] and colx[c][1] <= colx[o][1]:
                return True
        return False

    keep = [c for c in range(ncols)
            if colx[c][1] - colx[c][0] >= 0.02 * span
            and not _contained(c)
            and _column_has_content(n, best, colx[c][0], colx[c][1],
                                    ty0, ty1)]
    colx = {i: colx[c] for i, c in enumerate(keep)}
    remap = {c: i for i, c in enumerate(keep)}
    cells = {(r, remap[c]): v for (r, c), v in cells.items()
             if c in remap}
    ncols = len(keep)
    # a row whose only hole sat in a dropped column vanishes with it
    live = sorted({r for r, _ in cells})
    rremap = {r: i for i, r in enumerate(live)}
    cells = {(rremap[r], c): v for (r, c), v in cells.items()}
    nrows = len(live)
    rowy = {r: (median(cells[k][1] for k in cells if k[0] == r),
                median(cells[k][3] for k in cells if k[0] == r))
            for r in range(nrows)}
    if debug is not None:
        debug["holes"] = len(holes)
        debug["shape"] = (nrows, ncols)
        debug["backed"] = set(cells)
    return {(r, c): (int(colx[c][0]), int(rowy[r][0]),
                     int(colx[c][1]), int(rowy[r][1]))
            for r in range(nrows) for c in range(ncols)}


def _page_components(page: pathlib.Path, threshold: int, dpi_key):
    """The page's components as [(id, x0, y0, x1, y1, area, holes)],
    through a sidecar cache (T30).

    `locate` over 4,871 formulas must not re-sweep 300 pages 4,871
    times. The sidecar `<page>.inkcache.json` holds one entry per
    (threshold, dpi) key -- the page path is the file's own location
    -- and an entry is valid only while the page's (mtime, size) both
    match; a re-rendered page invalidates it. Corrupt or unreadable
    caches are recomputed, never trusted.
    """
    import json
    from .aggregate import moments_per_component
    from .pngio import read_png, auto_mask
    from .sweep import Capture, sweep

    side = page.with_name(page.name + ".inkcache.json")
    key = f"t{threshold}:d{dpi_key}"
    st = page.stat()
    try:
        store = json.loads(side.read_text())
        e = store.get(key)
        if e and e["mtime"] == st.st_mtime and e["size"] == st.st_size:
            return [tuple(c) for c in e["components"]]
    except (OSError, ValueError, KeyError, TypeError):
        store = {}
    if not isinstance(store, dict):
        store = {}

    img = read_png(page)
    mask, _ = auto_mask(img.gray, img.width, img.height, threshold)
    res = sweep(mask, axis="row", conn=8, capture=Capture.GRAPH)
    moms = moments_per_component(res)
    comps = [(c.root, moms[c.root].x0, moms[c.root].y0,
              moms[c.root].x1, moms[c.root].y1, moms[c.root].area,
              c.holes) for c in res.components]
    store[key] = {"mtime": st.st_mtime, "size": st.st_size,
                  "components": [list(c) for c in comps]}
    try:
        side.write_text(json.dumps(store))
    except OSError:
        pass                       # a read-only page dir still locates
    return comps


def cmd_locate(argv) -> int:
    """`locate --page P.png --candidate C.png` (T29).

    One page sweep (cached, T30), restricted to text rows; windows of
    the candidate's component count +-2 slide along each row and are
    scored by L1 distance over the structural five-tuple (components,
    holes, stacked, centred, offset) -- `pair_counts` on the cached
    boxes, the same measurement `compare` makes on pixels. The best
    window's rectangle is reported in POINTS plus the distance.

    NO MATCH is an explicit answer with exit code 1: when no row
    holds a window within +-2 components, nothing is returned rather
    than a best-of-bad -- the gate is the count, and reporting the
    least-bad wrong window would be a confident wrong answer.
    """
    import argparse
    import collections
    import json
    ap = argparse.ArgumentParser(prog="python3 -m inkdrill locate")
    ap.add_argument("--page", type=pathlib.Path, required=True)
    ap.add_argument("--candidate", type=pathlib.Path, required=True)
    ap.add_argument("--threshold", type=int, default=200)
    ap.add_argument("--dpi", type=float, default=None,
                    help="points conversion when the page has no pHYs")
    args = ap.parse_args(argv)

    from .mathstruct import Glyph, pair_counts, pair_stats, rows
    from .pngio import read_png, auto_mask

    img = read_png(args.candidate)
    cmask, _ = auto_mask(img.gray, img.width, img.height, args.threshold)
    cand = pair_stats(cmask)
    n = cand["components"]
    cvec = (n, cand["holes"], cand["stacked"], cand["centred"],
            cand["offset"])

    pimg = read_png(args.page)
    dpi = (pimg.dpi[0] if pimg.dpi else None) or args.dpi
    if dpi is None:
        print("no pHYs in page and no --dpi: points are required",
              file=sys.stderr)
        return 2
    comps = _page_components(args.page, args.threshold,
                             round(dpi, 3))
    C = collections.namedtuple("C", "id x0 y0 x1 y1 area holes")
    comps = [C(*c) for c in comps]
    by_id = {c.id: c for c in comps}

    best = None
    for row in rows([Glyph(c.id, float(c.x0), float(c.y0),
                           float(c.x1), float(c.y1)) for c in comps]):
        members = sorted((by_id[g.id] for g in row.members),
                         key=lambda c: (c.x0, c.id))
        for k in range(max(1, n - 2), n + 3):
            for i in range(len(members) - k + 1):
                win = members[i:i + k]
                st, ce, of = pair_counts(win)
                vec = (k, sum(c.holes for c in win), st, ce, of)
                d = sum(abs(a - b) for a, b in zip(vec, cvec))
                if best is None or d < best[0]:
                    box = (min(c.x0 for c in win), min(c.y0 for c in win),
                           max(c.x1 for c in win), max(c.y1 for c in win))
                    best = (d, box, k)
    if best is None:
        print("NO MATCH: no text-row window within +-2 of "
              f"{n} components")
        return 1
    d, (x0, y0, x1, y1), k = best
    sc = 72.0 / dpi
    doc = {"rect_pt": [round(x0 * sc, 2), round(y0 * sc, 2),
                       round((x1 + 1) * sc, 2), round((y1 + 1) * sc, 2)],
           "rect_px": [x0, y0, x1, y1],
           "distance": d, "components": k,
           "candidate": list(cvec)}
    sys.stdout.write(json.dumps(doc) + "\n")
    return 0


def _regions_from_lines_json(path, page, mask_w, mask_h):
    """MathPix `lines.json` regions for one page, scaled to mask pixels.

    The only region format this reads, and it is read STRICTLY: a page
    that is absent raises rather than yielding an empty region list,
    because "no regions" and "page not in this file" are different
    findings and the second one silently reads as 100% missed ink.
    """
    import ast
    import json
    from .coverage import Region
    doc = json.loads(pathlib.Path(path).read_text())
    pages = {p["page"]: p for p in doc["pages"]}
    if page not in pages:
        raise SystemExit(f"{path}: no page {page} "
                         f"(pages {min(pages)}..{max(pages)})")
    meta = pages[page]
    sx = mask_w / meta["page_width"]
    sy = mask_h / meta["page_height"]
    out = []
    for j, ln in enumerate(meta.get("lines", [])):
        r = ln.get("region")
        if isinstance(r, str):
            r = ast.literal_eval(r)
        if not r:
            continue
        out.append(Region(j, r["top_left_x"] * sx, r["top_left_y"] * sy,
                          (r["top_left_x"] + r["width"]) * sx,
                          (r["top_left_y"] + r["height"]) * sy,
                          ln.get("type", "")))
    return out


_RESIDUAL_COLOURS = {
    "inside": (170, 170, 170),        # ink another tool accounted for
    "missed": (220, 30, 30),          # ink with NO region -- the finding
    "straddle": (230, 150, 20),       # ink crossing a region edge
    "overlapping": (40, 90, 220),     # ink under overlapping regions
}


def _write_png(path, width, height, rgb_rows):
    """Minimal RGB PNG writer (stdlib zlib only -- no dependency)."""
    import struct
    import zlib
    raw = b"".join(b"\x00" + bytes(row) for row in rgb_rows)

    def chunk(tag, data):
        c = tag + data
        return (struct.pack(">I", len(data)) + c
                + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF))
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height,
                                        8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 6))
           + chunk(b"IEND", b""))
    pathlib.Path(path).write_bytes(png)


def cmd_residual(argv) -> int:
    """`residual page.png --regions lines.json --region-page N` (S3).

    Cross-checks another tool's regions against the real ink and emits
    the FOUR coverage classes with their component ids -- the residual
    is the product, so `missed` ink is named component by component
    rather than summarised into a rate. `--png` paints the same
    classes so a human can see where the tool stopped looking.

    Containment, not centres: a component crossing a region edge is
    `straddle`, which is a finding of its own and never silently
    counted as covered.
    """
    import argparse
    import json
    ap = argparse.ArgumentParser(prog="python3 -m inkdrill residual")
    ap.add_argument("page", type=pathlib.Path)
    ap.add_argument("--regions", type=pathlib.Path, required=True,
                    help="MathPix lines.json holding the other tool's "
                         "regions")
    # NOT --page: that dest collides with the positional page image
    # and argparse silently overwrites the path with an int
    ap.add_argument("--region-page", type=int, default=1, dest="rpage",
                    help="page number WITHIN the regions file")
    ap.add_argument("--threshold", type=int, default=200)
    ap.add_argument("--min-pixels", type=int, default=4,
                    help="speck floor: a 1-px speck reported as missed "
                         "content is noise the caller must filter anyway")
    ap.add_argument("--png", type=pathlib.Path,
                    help="write a coloured overlay of the classes")
    ap.add_argument("-o", "--out", type=pathlib.Path)
    args = ap.parse_args(argv)

    from .aggregate import moments_per_component
    from .coverage import Box, CoverageClass, check
    from .pngio import auto_mask, read_png
    from .sweep import Capture, sweep

    img = read_png(args.page)
    mask, flipped = auto_mask(img.gray, img.width, img.height,
                              args.threshold)
    res = sweep(mask, axis="row", conn=8, capture=Capture.GRAPH)
    moms = moments_per_component(res)
    boxes = [Box(c.root, moms[c.root].x0, moms[c.root].y0,
                 moms[c.root].x1, moms[c.root].y1, moms[c.root].area)
             for c in res.components]
    # the helper scales with the page dimensions the regions were
    # measured in, which only it has read
    regions = _regions_from_lines_json(args.regions, args.rpage,
                                       mask.width, mask.height)

    rep = check(boxes, regions, min_pixels=args.min_pixels)
    by = {}
    for k in CoverageClass:
        by[k.name.lower()] = sorted(rep.members(k))
    doc = {
        "page": str(args.page), "regions_file": str(args.regions),
        "region_page": args.rpage,
        "width": mask.width, "height": mask.height,
        "polarity": "light-on-dark" if flipped else "dark-on-light",
        "boxes": rep.box_count, "regions": rep.region_count,
        "classes": {k: len(v) for k, v in by.items()},
        "missed_pixels": sum(moms[b].area for b in by["missed"]
                             if b in moms),
        "members": by,
    }
    text = json.dumps(doc, indent=1) + "\n"
    if args.out:
        args.out.write_text(text)
        print(f"{doc['classes']} -> {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)

    if args.png:
        klass = {}
        for name, ids in by.items():
            if name in _RESIDUAL_COLOURS:
                for i in ids:
                    klass[i] = _RESIDUAL_COLOURS[name]
        owner = {}
        for comp in res.components:
            for nid in comp.nodes:
                owner[nid] = comp.root
        rows = [bytearray(b"\xff" * (mask.width * 3))
                for _ in range(mask.height)]
        for nid, n in enumerate(res.nodes):
            col = klass.get(owner.get(nid))
            if col is None:
                continue
            row = rows[n.line]
            for x in range(n.lo, n.hi + 1):
                row[x * 3:x * 3 + 3] = bytes(col)
        _write_png(args.png, mask.width, mask.height, rows)
        print(f"overlay -> {args.png} "
              f"(grey inside, red missed, orange straddle, blue "
              f"overlapping)", file=sys.stderr)
    return 0


def cmd_template(argv) -> int:
    """`template --font f.pfb --glyph name -o out.pgm` (T27).

    The existing chain, from the shell: `type1.load` (a FILE, never a
    search) -> `charstring.outline` -> `scan.render`. The mask goes
    out as a P5 PGM with ink BLACK, which is the polarity
    `pnmio.load_mask` reads back by default, so a written template
    round-trips. The glyph's per-component topology prints to stdout
    so a classification experiment is reproducible from the shell
    without a driver script.
    """
    import argparse
    import json
    ap = argparse.ArgumentParser(prog="python3 -m inkdrill template")
    ap.add_argument("--font", type=pathlib.Path, required=True,
                    help="path to a Type 1 .pfb/.pfa file")
    ap.add_argument("--glyph", required=True)
    ap.add_argument("--px-em", type=float, default=96.0)
    ap.add_argument("-o", "--out", type=pathlib.Path)
    args = ap.parse_args(argv)

    from .charstring import outline
    from .emit import component_topology
    from .scan import render
    from .type1 import load

    font = load(args.font)
    mask, _ = render(outline(font, args.glyph), font.units_per_em,
                     args.px_em)
    if args.out:
        args.out.write_bytes(b"P5\n%d %d\n255\n"
                             % (mask.width, mask.height)
                             + bytes(255 - v for v in mask.data))
        print(f"{mask.width}x{mask.height} -> {args.out}",
              file=sys.stderr)
    doc = {"font": args.font.name, "glyph": args.glyph,
           "px_em": args.px_em,
           "width": mask.width, "height": mask.height,
           "components": component_topology(mask)}
    sys.stdout.write(json.dumps(doc, indent=1) + "\n")
    return 0


def _column_has_content(n, table, x0, x1, y0, y1) -> bool:
    """P15's decider: does any glyph-sized ink region centre inside
    this column's span within the table? Background fragments hold
    none. Glyph-sized = area >= 4 px and both dimensions >= 2 px, so
    isolated dust cannot vouch for a phantom."""
    for r in n.regions.values():
        if r.kind.value != "ink" or r.id == table.id:
            continue
        if r.area < 4 or r.x1 - r.x0 < 1 or r.y1 - r.y0 < 1:
            continue
        cx = (r.x0 + r.x1) / 2
        cy = (r.y0 + r.y1) / 2
        if x0 <= cx <= x1 and y0 <= cy <= y1:
            return True
    return False


def cmd_topology(argv) -> int:
    """`topology page.png [--dpi N]` -- the per-component record as
    JSON (T24). `--dpi` is accepted for parity with the main CLI and
    recorded; every coordinate here is in PIXELS."""
    import argparse
    import json
    ap = argparse.ArgumentParser(prog="python3 -m inkdrill topology")
    ap.add_argument("page", type=pathlib.Path)
    ap.add_argument("--dpi", type=float, default=None)
    ap.add_argument("--threshold", type=int, default=200)
    ap.add_argument("-o", "--out", type=pathlib.Path)
    args = ap.parse_args(argv)

    from .emit import component_topology
    from .pngio import read_png, auto_mask
    img = read_png(args.page)
    mask, flipped = auto_mask(img.gray, img.width, img.height,
                              args.threshold)
    doc = {
        "page": str(args.page),
        "width": mask.width, "height": mask.height,
        "dpi": args.dpi if args.dpi else (img.dpi if img.dpi else None),
        "polarity": "light-on-dark" if flipped else "dark-on-light",
        "components": component_topology(mask),
    }
    text = json.dumps(doc, indent=1) + "\n"
    if args.out:
        args.out.write_text(text)
        print(f"{len(doc['components'])} components -> {args.out}",
              file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


def cmd_compare(argv) -> int:
    """`compare A.png B.png` -- per table row, the structural five-tuple
    (components, holes, stacked, centred, offset) of TWO columns,
    reported side by side (I1).

    `--cols i j` names the columns; the default is the last two. A and
    B are the SAME page at two resolutions, and the `A=B` column is
    the scale-invariance assertion -- rows where the two computations
    disagree are reported, never averaged. `B stable` additionally
    checks B against its own half-scale resample.

    The label column reads no text (emit G6): with `-o` the
    first-column cells are saved as crops beside the output and
    referenced by filename; without it the label is the row index.
    No dpi is required -- the five numbers are counts.

    The last column is the REGION-OVERRUN test (102). When the right
    column has MORE components than the left, the naive reading is
    that the left one is missing ink -- a conversion defect. The
    other cause is that the right crop overran its region and
    captured a neighbour's, and `mathstruct.region_overrun`
    separates them: every surplus component both outside the main
    ink's cluster and cut by a crop border makes the row
    REGION-OVERRUN. It is APPENDED, so a consumer indexing the
    earlier columns positionally is unaffected, and the five-tuple
    is never edited -- the count stays the measured one and the
    caller decides what the label is worth.
    """
    import argparse
    ap = argparse.ArgumentParser(prog="python3 -m inkdrill compare")
    ap.add_argument("a", type=pathlib.Path)
    ap.add_argument("b", type=pathlib.Path)
    ap.add_argument("--threshold", type=int, default=200)
    ap.add_argument("--tol", type=float, default=4.0,
                    help="cell-lattice clustering tolerance, px")
    ap.add_argument("--cols", type=int, nargs=2, default=None,
                    help="the two columns to compare (default: last two)")
    ap.add_argument("--page-number", type=int, default=1)
    ap.add_argument("--gap-scale", type=float, default=1.0,
                    help="region-overrun separation, x median glyph width")
    ap.add_argument("--edge-tol", type=int, default=0,
                    help="region-overrun edge contact, px "
                         "(--anchor edge only)")
    ap.add_argument("--anchor", choices=("edge", "extreme"),
                    default="extreme",
                    help="where a surplus cluster must sit to count as "
                         "overrun: at a crop BORDER, or at an end of "
                         "the INK")
    ap.add_argument("--table-debug", action="store_true",
                    help="dump lattice + per-cell stats to stderr")
    ap.add_argument("-o", "--out", type=pathlib.Path)
    args = ap.parse_args(argv)

    from .mathstruct import pair_stats, region_overrun
    from .pngio import read_png, auto_mask
    from .warp import resample

    def load(path):
        img = read_png(path)
        return auto_mask(img.gray, img.width, img.height,
                         args.threshold)[0]

    masks = {"A": load(args.a), "B": load(args.b)}
    dbg = {k: {} for k in masks} if args.table_debug else \
        {k: None for k in masks}
    _table_span = {}
    cells = {}
    for k, m in masks.items():
        if dbg[k] is None:
            dbg[k] = {}
        cells[k] = _table_cells(m, args.tol, debug=dbg[k])
        _table_span[k] = dbg[k].get("span", 0)
    for k, c in cells.items():
        # `_table_cells` has TWO empty answers and they mean different
        # things: None is "no ink region has >= 2 holes, so there is no
        # table region at all", and an empty dict is "a table region was
        # found and no cell survived the filters". Only the first was
        # guarded, so the second reached `max()` on an empty generator
        # and raised ValueError from four frames down -- reported from
        # page 9 of 1605.05775/report.pdf, the "Unrecovered image
        # regions" page. A page with no cells is a NORMAL condition in
        # these reports: every document with unrecovered regions has
        # one, which was 6 of 7 documents in the run that hit this.
        if c is None or not c:
            why = ("no ink region with >= 2 holes -- no table on this "
                   "page" if c is None else
                   "a table region was found but no cell survived the "
                   "lattice filters")
            print(f"{k}: no cells ({why})", file=sys.stderr)
            return 1
    if args.table_debug:
        from .nest import ink_only
        for k in masks:
            d = dbg[k]
            nr, nc = d["shape"]
            print(f"{k}: table region holes {d['holes']}, "
                  f"lattice {nr} rows x {nc} cols, "
                  f"{len(d['backed'])} hole-backed, "
                  f"{nr * nc - len(d['backed'])} median-filled",
                  file=sys.stderr)
            for r in range(nr):
                for c in range(nc):
                    b = cells[k][(r, c)]
                    ik = ink_only(_cell_crop(masks[k], b[0], b[1],
                                             b[2] - 1, b[3] - 1))
                    comps = len(ik.regions)
                    hs = sum(ik.cycles)
                    src = ("hole-backed" if (r, c) in d["backed"]
                           else "MEDIAN-FILLED")
                    print(f"{k} cell ({r},{c}) {src}: "
                          f"components {comps} holes {hs} "
                          f"chi {comps - hs}", file=sys.stderr)
    nrows = {k: max(r for r, _ in c) + 1 for k, c in cells.items()}
    ncols = {k: max(cc for _, cc in c) + 1 for k, c in cells.items()}
    # Two columns are the minimum this subcommand can mean anything
    # with: it compares the LAST TWO, and `--cols` defaults to
    # `(nc - 2, nc - 1)`, which at nc == 1 is `(-1, 0)` -- a NEGATIVE
    # index that silently wraps to the last column and compares it
    # against the first. Page 8 of the same report is a 1-column
    # lattice and produced a full table of rows whose left five-tuple
    # was 0,0,0,0,0 and whose `A=B` said NO for every row: a
    # confident, complete-looking, meaningless answer. A crash is a
    # better failure than that, and a named refusal is better still.
    # ROW COVERAGE: the detected rows' heights against the table
    # region's own height. A row whose content touches the rules on
    # both sides stops being an enclosed hole and is not detected at
    # all -- 0902.0431 p13 and p19 are a single oversized aligned
    # block beside a 113 mm crop, and the lattice finds ONLY the 49 px
    # header, covering 1.5% of a 3,296 px table.
    #
    # That is worse than a crash and worse than a false clean: a row
    # missing MID-SEQUENCE does not truncate the pairing, it SHIFTS
    # it, so every row after it is attached to the following equation
    # and nothing downstream can see it. It shipped, and a peer's
    # audit misattributed the displacement to a different defect of
    # mine before measurement separated them.
    #
    # The floor is a separation, not a tuned constant: over 50 corpus
    # pages the minimum coverage is 0.891 and the median 0.986,
    # against 0.015 on the failing page. Two orders of magnitude, so
    # any value in the gap is safe and the strictest is free.
    for k, c in cells.items():
        nr = nrows[k]
        got = sum(c[(r, 0)][3] - c[(r, 0)][1] for r in range(nr)
                  if (r, 0) in c)
        span = _table_span[k]
        cov = got / span if span else 0.0
        print(f"{k}: lattice {nr} rows x {ncols[k]} cols, row coverage "
              f"{cov:.3f} of the table region", file=sys.stderr)
        if cov < 0.5:
            print(f"{k}: row coverage {cov:.3f} -- the detected rows "
                  f"cover less than half the table region, so rows are "
                  f"MISSING. A missing row shifts every row after it "
                  f"onto the wrong equation, which no downstream check "
                  f"can see. Nothing was compared.", file=sys.stderr)
            return 1
    for k, nc in ncols.items():
        if nc < 2:
            print(f"{k}: lattice has {nc} column(s); compare needs at "
                  f"least 2 (it reads the last two). Nothing was "
                  f"compared.", file=sys.stderr)
            return 1
    if nrows["A"] != nrows["B"]:
        print(f"row counts differ: A {nrows['A']} vs B {nrows['B']}; "
              f"comparing the first {min(nrows.values())}",
              file=sys.stderr)

    keys = ("components", "holes", "stacked", "centred", "offset")

    def feats_of(k, r, col):
        nc = ncols[k]
        pick = tuple(args.cols) if args.cols else (nc - 2, nc - 1)
        cell = cells[k].get((r, pick[col]))
        if cell is None:
            return None
        crop = _cell_crop(masks[k], cell[0], cell[1],
                          cell[2] - 1, cell[3] - 1)
        return pair_stats(crop), crop

    header = (["page", "line", "label"]
              + [f"L {k}" for k in keys] + [f"R {k}" for k in keys]
              + ["A=B", "B stable", "overrun", "empty"])
    rows_out = []
    mismatch = unstable = overruns = empties = 0
    for r in range(min(nrows.values())):
        row = [str(args.page_number), str(r)]
        lab = cells["A"].get((r, 0))
        if lab and args.out:
            crop = _cell_crop(masks["A"], lab[0], lab[1],
                              lab[2] - 1, lab[3] - 1)
            f = args.out.with_name(f"{args.out.stem}_row{r}_label.pgm")
            f.write_bytes(b"P5\n%d %d\n255\n"
                          % (crop.width, crop.height) + crop.data)
            row.append(f.name)
        else:
            row.append(f"row {r}")
        agree, stable = True, True
        ncomp = {}
        right_crop = None
        for col in (0, 1):
            fa = feats_of("A", r, col)
            fb = feats_of("B", r, col)
            sta = fa[0] if fa else {}
            ncomp[col] = sta.get("components", 0)
            if col == 1 and fa:
                right_crop = fa[1]
            row.extend(str(sta.get(kk, 0)) for kk in keys)
            if (sta or {}) != ((fb[0] if fb else {}) or {}):
                agree = False
            if fb:
                crop = fb[1]
                hw = max(1, crop.width // 2)
                hh = max(1, crop.height // 2)
                half = resample(crop, (0.5, 0.0, 0.0, 0.5, 0.0, 0.0),
                                width=hw, height=hh)
                if pair_stats(half) != fb[0]:
                    stable = False
        row.append("yes" if agree else "NO")
        row.append("yes" if stable else "NO")
        # The right column's SURPLUS components, when every one of them
        # is both separated from the main ink and cut by a crop border,
        # is ink the crop should not contain -- a cropping defect, not
        # the missing-symbol finding the count would otherwise read as.
        # Reported, never subtracted: the five-tuple stays the measured
        # one and the caller decides (102).
        over = ""
        surplus = ncomp[1] - ncomp[0]
        if surplus > 0 and right_crop is not None:
            ro = region_overrun(right_crop, gap_scale=args.gap_scale,
                                edge_tol=args.edge_tol,
                                anchor=args.anchor)
            if ro["overrun"] and len(ro["overrun"]) >= surplus:
                over = f"REGION-OVERRUN {len(ro['overrun'])}"
                overruns += 1
        row.append(over)
        # BOTH CELLS EMPTY is not a clean row, it is an ABSENT one, and
        # the difference is invisible in the five-tuple: 0,0,0,0,0
        # against 0,0,0,0,0 is distance 0, component delta 0, and every
        # downstream flag reads CLEAN -- the best possible score, from a
        # comparison that did not happen.
        #
        # It is a real lattice row, not a phantom: a longtable's
        # page-break CONTINUATION FOOTER is 49 px tall at 300 dpi on
        # 1605.05775, which clears the 40 px sliver floor, so it
        # survives every filter and lands N-of-N on every page except
        # the last. Six unrelated documents showed exactly one per
        # page.
        #
        # MARKED, NEVER DROPPED. Callers pair rows to identifiers by
        # POSITION, so removing a row here shifts every row after it --
        # the same defect that put 501 phantom changes in a peer's
        # output and 320 mislabelled rows in this project's own
        # overrun harness. The row keeps its slot and says what it is.
        both_empty = (ncomp[0] == 0 and ncomp[1] == 0)
        row.append("BOTH-EMPTY" if both_empty else "")
        empties += both_empty
        mismatch += not agree
        unstable += not stable
        rows_out.append(row)

    lines = ["| " + " | ".join(header) + " |",
             "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows_out]
    text = "\n".join(lines) + "\n"
    if args.out:
        args.out.write_text(text)
        print(f"{len(rows_out)} rows -> {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    if mismatch:
        print(f"WARNING: {mismatch} of {len(rows_out)} rows differ "
              f"between A and B", file=sys.stderr)
    if unstable:
        print(f"WARNING: {unstable} of {len(rows_out)} rows change "
              f"features at half scale", file=sys.stderr)
    if empties:
        print(f"WARNING: {empties} of {len(rows_out)} rows have NO INK "
              f"in either compared cell. They score distance 0 and read "
              f"as CLEAN; they are marked BOTH-EMPTY in the last column "
              f"and a consumer must exclude them from any clean count.",
              file=sys.stderr)
    if overruns:
        print(f"{overruns} of {len(rows_out)} rows: the right column's "
              f"surplus components are REGION OVERRUN (separated from "
              f"the main ink and cut by a crop border) -- a cropping "
              f"defect, not a missing symbol", file=sys.stderr)
    return 0


def _apply_polarity(args, mask, auto):
    """The guard. `auto` defers to `pngio.auto_mask` -- the ONE
    definition of the decision, fraction gate plus component
    comparison; a forced `--ink` is never second-guessed, because never
    guess also means never overrule a statement."""
    if args.ink == "light":
        return mask, "light-on-dark"
    if args.ink == "dark":
        return mask, None
    new_mask, flipped = auto()
    if flipped:
        frac = mask.ink_count / (mask.width * mask.height)
        print(f"polarity: {frac:.0%} of the page is dark at this "
              f"threshold and the light reading has more components; "
              f"reading as light-on-dark (--ink dark to override)",
              file=sys.stderr)
        return new_mask, "light-on-dark"
    return mask, None


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == "compare":
        return cmd_compare(argv[1:])
    if argv and argv[0] == "topology":
        return cmd_topology(argv[1:])
    if argv and argv[0] == "residual":
        return cmd_residual(argv[1:])
    if argv and argv[0] == "template":
        return cmd_template(argv[1:])
    if argv and argv[0] == "locate":
        return cmd_locate(argv[1:])
    ap = argparse.ArgumentParser(
        prog="python3 -m inkdrill",
        description="A rendered page to a MathPix-shaped lines.json.")
    ap.add_argument("page", type=pathlib.Path,
                    help="a ghostscript png16m .png or pgmraw .pgm, or `-` "
                         "for a PNM stream on stdin (one record per page)")
    ap.add_argument("-o", "--out", type=pathlib.Path,
                    help="output file; stdout if omitted")
    ap.add_argument("--dpi", type=float, default=None,
                    help="required for a PGM, and for a PNG with no pHYs; "
                         "refused for a PNG that declares one")
    ap.add_argument("--threshold", type=int, default=200,
                    help="ink threshold, 0-255 (default 200)")
    ap.add_argument("--page-number", type=int, default=1)
    ap.add_argument("--tol", type=float, default=2.0,
                    help="cell-lattice clustering tolerance, px")
    ap.add_argument("--ink", choices=("auto", "dark", "light"),
                    default="auto",
                    help="which tone is ink. `dark` is the print "
                         "convention, `light` a slide/chalkboard. "
                         "`auto` measures: a page whose dark fraction "
                         "exceeds half is read as light-on-dark, "
                         "because no measured document page comes "
                         "near that and every measured inverted frame "
                         "exceeds it.")
    ap.add_argument("--glyphs", action="store_true",
                    help="also emit one `glyph` line per ink component -- "
                         "bbox, area, holes and principal axis, with no "
                         "classification. A text page emits nothing "
                         "without this.")
    ap.add_argument("--stats", action="store_true",
                    help="print a summary to stderr instead of timing "
                         "nothing")
    args = ap.parse_args(argv)

    from .emit import free_rules, lines_json, page_lines, page_record

    suffix = args.page.suffix.lower()
    t0 = time.perf_counter()
    if str(args.page) == "-":
        # `gs -sOutputFile=%stdout | python3 -m inkdrill - --dpi 400`
        # needs no temp file, and a multi-page render arrives as one
        # CONCATENATED stream rather than one image. Page numbers count
        # from `--page-number`, so a caller rendering pages 7-9 can say
        # so and the records carry the document's own numbering.
        if args.dpi is None:
            ap.error("--dpi is required for a PNM stream: the format "
                     "cannot record it, and guessing is wrong by 0.071 pt "
                     "on the e12s39 fixture")
        from .pnmio import load_masks
        masks = list(load_masks(sys.stdin.buffer, dpi=args.dpi,
                                threshold=args.threshold))
        if not masks:
            ap.error("stdin held no PNM image")
        dpi = (args.dpi, args.dpi)
        t_load = time.perf_counter() - t0
        t0 = time.perf_counter()
        pt = 72.0 / dpi[0]
        records, lines = [], []
        for k, m in enumerate(masks):
            page_ln = page_lines(m, pt=pt, tol=args.tol, glyphs=args.glyphs)
            lines.extend(page_ln)
            records.append(page_record(
                page=args.page_number + k, width_px=m.width,
                height_px=m.height, dpi=dpi, lines=page_ln,
                rules=free_rules(m, pt=pt)))
        doc = lines_json(records, render_dpi=dpi[0])
        t_emit = time.perf_counter() - t0
        _write(args, doc, lines, t_load, t_emit,
               f"<stdin>  {len(masks)} pages @ {args.dpi:.0f} dpi")
        return 0
    if suffix in (".pgm", ".pnm"):
        if args.dpi is None:
            ap.error("--dpi is required for a PGM: the format cannot "
                     "record it, and guessing is wrong by 0.071 pt on the "
                     "e12s39 fixture")
        from .pnmio import load_mask
        mask = load_mask(args.page, dpi=args.dpi, threshold=args.threshold,
                         ink_is_dark=args.ink != "light")
        from .pngio import auto_mask
        from .pnmio import read_pnm
        img = read_pnm(args.page, dpi=args.dpi)
        mask, polarity = _apply_polarity(
            args, mask, lambda: auto_mask(img.gray, img.width, img.height,
                                          args.threshold))
        dpi = (args.dpi, args.dpi)
    elif suffix == ".png":
        from .pngio import load_mask, read_png
        img = read_png(args.page)
        declared = bool(img.dpi and img.dpi[0])
        # The rule is NEVER GUESS, not never accept. A PNG that declares
        # `pHYs` is authoritative and a supplied value could silently
        # disagree with it, so `--dpi` is refused there. A PNG WITHOUT
        # `pHYs` -- which real scanner output often is -- has nothing to
        # disagree with, so `--dpi` is required and accepted, exactly as
        # for a PGM.
        if declared and args.dpi is not None:
            ap.error(f"{args.page.name} declares {img.dpi[0]:.0f} dpi in its "
                     f"pHYs chunk; --dpi is refused because a supplied "
                     f"value could silently disagree with it")
        if not declared and args.dpi is None:
            ap.error(f"{args.page.name} declares no pHYs resolution, so "
                     f"--dpi is required. Guessing 72, or deriving it from "
                     f"a nominal page size, is wrong by 0.071 pt on the "
                     f"e12s39 fixture")
        mask = load_mask(args.page, threshold=args.threshold,
                         ink_is_dark=args.ink != "light")
        from .pngio import auto_mask
        mask, polarity = _apply_polarity(
            args, mask, lambda: auto_mask(img.gray, img.width, img.height,
                                          args.threshold))
        dpi = img.dpi if declared else (args.dpi, args.dpi)
    else:
        ap.error(f"unsupported input {suffix!r}; this reads .png (png16m) "
                 f"and .pgm (pgmraw)")

    t_load = time.perf_counter() - t0
    t0 = time.perf_counter()
    pt = 72.0 / dpi[0]
    lines = page_lines(mask, pt=pt, tol=args.tol, glyphs=args.glyphs)
    doc = lines_json([page_record(page=args.page_number,
                                  width_px=mask.width,
                                  height_px=mask.height, dpi=dpi,
                                  polarity=polarity,
                                  lines=lines,
                                  rules=free_rules(mask, pt=pt))],
                     render_dpi=dpi[0])
    t_emit = time.perf_counter() - t0

    _write(args, doc, lines, t_load, t_emit,
           f"{args.page.name}  {mask.width}x{mask.height} @ {dpi[0]:.0f} dpi")
    return 0


def _write(args, doc, lines, t_load, t_emit, banner):
    text = json.dumps(doc, indent=1)
    if args.out:
        args.out.write_text(text)
    else:
        sys.stdout.write(text)
    if args.stats:
        from collections import Counter
        kinds = Counter(l["type"] for l in lines)
        print(banner, file=sys.stderr)
        print(f"  load {t_load:6.2f}s   emit {t_emit:6.2f}s   "
              f"{len(text) / 1024:.0f} KB", file=sys.stderr)
        print(f"  lines {len(lines)}: {dict(kinds.most_common())}",
              file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
