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


def _table_cells(mask, tol):
    """The page's table as {(row, col): hole bbox}. The table is the
    ink region with the most holes. A lattice slot whose hole is
    FRAGMENTED (cell content touching a rule splits the background
    region, so no single hole matches the cell) is filled from the
    intersection of its row's y-span and its column's x-span -- on the
    bh2 report page 1, two of eight scan cells were lost exactly this
    way before the fill existed."""
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
    rowy = {r: (median(cells[k][1] for k in cells if k[0] == r),
                median(cells[k][3] for k in cells if k[0] == r))
            for r in range(nrows)}
    return {(r, c): (int(colx[c][0]), int(rowy[r][0]),
                     int(colx[c][1]), int(rowy[r][1]))
            for r in range(nrows) for c in range(ncols)}


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
    ap.add_argument("-o", "--out", type=pathlib.Path)
    args = ap.parse_args(argv)

    from .mathstruct import pair_stats
    from .pngio import read_png, auto_mask
    from .warp import resample

    def load(path):
        img = read_png(path)
        return auto_mask(img.gray, img.width, img.height,
                         args.threshold)[0]

    masks = {"A": load(args.a), "B": load(args.b)}
    cells = {k: _table_cells(m, args.tol) for k, m in masks.items()}
    for k, c in cells.items():
        if c is None:
            print(f"{k}: no table found (no ink region with >= 2 holes)",
                  file=sys.stderr)
            return 1
    nrows = {k: max(r for r, _ in c) + 1 for k, c in cells.items()}
    ncols = {k: max(cc for _, cc in c) + 1 for k, c in cells.items()}
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
              + ["A=B", "B stable"])
    rows_out = []
    mismatch = unstable = 0
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
        for col in (0, 1):
            fa = feats_of("A", r, col)
            fb = feats_of("B", r, col)
            sta = fa[0] if fa else {}
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
