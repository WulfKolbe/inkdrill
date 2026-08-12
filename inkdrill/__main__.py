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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python3 -m inkdrill",
        description="A rendered page to a MathPix-shaped lines.json.")
    ap.add_argument("page", type=pathlib.Path,
                    help="a ghostscript png16m .png or pgmraw .pgm")
    ap.add_argument("-o", "--out", type=pathlib.Path,
                    help="output file; stdout if omitted")
    ap.add_argument("--dpi", type=float, default=None,
                    help="required for PGM, which cannot carry it; "
                         "refused for PNG, which can")
    ap.add_argument("--threshold", type=int, default=200,
                    help="ink threshold, 0-255 (default 200)")
    ap.add_argument("--page-number", type=int, default=1)
    ap.add_argument("--tol", type=float, default=2.0,
                    help="cell-lattice clustering tolerance, px")
    ap.add_argument("--stats", action="store_true",
                    help="print a summary to stderr instead of timing "
                         "nothing")
    args = ap.parse_args(argv)

    from .emit import lines_json, page_lines, page_record

    suffix = args.page.suffix.lower()
    t0 = time.perf_counter()
    if suffix in (".pgm", ".pnm"):
        if args.dpi is None:
            ap.error("--dpi is required for a PGM: the format cannot "
                     "record it, and guessing is wrong by 0.071 pt on the "
                     "e12s39 fixture")
        from .pnmio import load_mask
        mask = load_mask(args.page, dpi=args.dpi, threshold=args.threshold)
        dpi = (args.dpi, args.dpi)
    elif suffix == ".png":
        if args.dpi is not None:
            ap.error("--dpi is refused for a PNG: the file declares its "
                     "own pHYs and a supplied value could silently "
                     "disagree with it")
        from .pngio import load_mask, read_png
        img = read_png(args.page)
        if not img.dpi or not img.dpi[0]:
            ap.error(f"{args.page} declares no pHYs resolution; points "
                     f"cannot be derived from it")
        mask = load_mask(args.page, threshold=args.threshold)
        dpi = img.dpi
    else:
        ap.error(f"unsupported input {suffix!r}; this reads .png (png16m) "
                 f"and .pgm (pgmraw)")

    t_load = time.perf_counter() - t0
    t0 = time.perf_counter()
    pt = 72.0 / dpi[0]
    lines = page_lines(mask, pt=pt, tol=args.tol)
    doc = lines_json([page_record(page=args.page_number,
                                  width_px=mask.width, height_px=mask.height,
                                  dpi=dpi, lines=lines)],
                     render_dpi=dpi[0])
    t_emit = time.perf_counter() - t0

    text = json.dumps(doc, indent=1)
    if args.out:
        args.out.write_text(text)
    else:
        sys.stdout.write(text)

    if args.stats:
        from collections import Counter
        kinds = Counter(l["type"] for l in lines)
        print(f"{args.page.name}  {mask.width}x{mask.height} @ {dpi[0]:.0f} dpi",
              file=sys.stderr)
        print(f"  load {t_load:6.2f}s   emit {t_emit:6.2f}s   "
              f"{len(text)/1024:.0f} KB", file=sys.stderr)
        print(f"  lines {len(lines)}: "
              f"{dict(kinds.most_common())}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
