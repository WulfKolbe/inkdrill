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

from .raster import looks_inverted
import time


def _apply_polarity(args, mask, reload_light):
    """The guard. `auto` flips a page the cut calls inverted; a forced
    `--ink` is never second-guessed -- never guess also means never
    overrule a statement."""
    if args.ink == "light":
        return mask, "light-on-dark"
    if args.ink == "dark":
        return mask, None
    if looks_inverted(mask):
        frac = mask.ink_count / (mask.width * mask.height)
        print(f"polarity: {frac:.0%} of the page is dark at this "
              f"threshold; reading as light-on-dark (--ink dark to "
              f"override)", file=sys.stderr)
        return reload_light(), "light-on-dark"
    return mask, None


def main(argv=None) -> int:
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
        mask, polarity = _apply_polarity(
            args, mask, lambda: load_mask(args.page, dpi=args.dpi,
                                          threshold=args.threshold,
                                          ink_is_dark=False))
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
        mask, polarity = _apply_polarity(
            args, mask, lambda: load_mask(args.page,
                                          threshold=args.threshold,
                                          ink_is_dark=False))
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
