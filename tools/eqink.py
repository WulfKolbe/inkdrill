"""What the ink says about an equation list's declared regions.

    python3 tools/eqink.py --list <eqlist.json> [--floor PX] [--out F]
    python3 tools/eqink.py --list <eqlist.json> --distribution

A list row gives a rectangle and a LaTeX. This reads the ink inside that
rectangle on the 400 dpi render and reports what is actually there:

    ink_box      the tight bounding box of ink inside the region
    widest_gap   the longest interior blank column run, and where it ends
    body_box     ink left of that gap, when it exceeds the floor
    number_box   the remainder -- a right-set equation number
    ink_rows     inked scan-line runs, so a two-line equation reads as two

NOT A MARK. A mark places an INLINE formula inside its host line; a
display equation is alone on its line and its rectangle is given, so a
"mark" there would be the caller's own region handed back with a
confidence attached. There is no confidence here: ink is not an opinion.
A region with no ink is reported as that and gets no boxes.

THE FLOOR IS AN ARGUMENT, NOT A CONSTANT. It separates two populations
-- the gaps BETWEEN symbols of one equation, and the gap before a
number set at the right margin -- and `--distribution` prints both so
the cut can be placed between them instead of on an edge. A threshold
chosen by looking at the data it then classifies is the mistake this
project keeps recording; see out/683 §5 and the two-column gutter.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from inkdrill import pnmio                                   # noqa: E402
from tools.formulafind import frame_rect, page_frames        # noqa: E402

LIB = pathlib.Path.home() / "pdfdrill-library"


def column_runs(mask):
    """(inked columns, inked scan-line runs) of a mask."""
    data, w, h = mask.data, mask.width, mask.height
    cols = [i for i in range(w) if any(data[y * w + i] for y in range(h))]
    rows, start = [], None
    for y in range(h + 1):
        hot = y < h and data[y * w:(y + 1) * w].count(255) > 0
        if hot and start is None:
            start = y
        elif not hot and start is not None:
            rows.append((start, y))
            start = None
    return cols, rows


def widest_interior_gap(cols):
    """(length, end) of the longest blank run BETWEEN the first and last
    inked column. Interior: a margin is not a gap."""
    if len(cols) < 2:
        return 0, 0
    inked = set(cols)
    best, end, run = 0, 0, 0
    for i in range(cols[0], cols[-1] + 1):
        run = 0 if i in inked else run + 1
        if run > best:
            best, end = run, i
    return best, end


def measure(mask, floor):
    """The boxes, or `ink: False` when the region holds no ink at all."""
    cols, rows = column_runs(mask)
    if not cols or not rows:
        return {"ink": False}
    gap, end = widest_interior_gap(cols)
    out = {"ink": True,
           "ink_box": [cols[0], rows[0][0], cols[-1] + 1, rows[-1][1]],
           "widest_gap": gap, "gap_end": end,
           "ink_rows": rows,
           "region": [mask.width, mask.height]}
    if floor and gap >= floor:
        left = [c for c in cols if c <= end - gap]
        right = [c for c in cols if c > end]
        if left and right:
            out["body_box"] = [left[0], rows[0][0], left[-1] + 1, rows[-1][1]]
            out["number_box"] = [right[0], rows[0][0], right[-1] + 1, rows[-1][1]]
    return out


def _mask_of(png: pathlib.Path, x, y, w, h):
    with tempfile.TemporaryDirectory() as td:
        pgm = pathlib.Path(td) / "c.pgm"
        r = subprocess.run(["magick", str(png), "-crop",
                            f"{int(w)}x{int(h)}+{int(x)}+{int(y)}", "+repage",
                            "-colorspace", "Gray", "-depth", "8", str(pgm)],
                           capture_output=True)
        if r.returncode:
            return None
        return pnmio.load_mask(str(pgm), dpi=400)


def run(listfile: pathlib.Path, library: pathlib.Path, floor: float):
    data = json.loads(listfile.read_text(encoding="utf-8"))
    frames = {}
    out, refused = [], []
    for r in data.get("rows") or []:
        doc = r.get("document")
        idy = r.get("identity") or {}
        reg = idy.get("region")
        page = idy.get("page")
        if not (doc and reg and page):
            refused.append((r.get("label"), "no region: not a pdf-lane row"))
            continue
        if doc not in frames:
            frames[doc] = page_frames(library, doc)[0]
        fr = frames[doc].get(page)
        png = library / doc / "inspect" / "pages" / f"p{page}.png"
        if not fr or not png.exists():
            refused.append((r.get("label"), "no rendered page"))
            continue
        x, y, w, h = frame_rect(reg, fr)
        m = _mask_of(png, x, y, w, h)
        if m is None:
            refused.append((r.get("label"), "the page would not crop"))
            continue
        rec = measure(m, floor)
        rec.update(document=doc, label=r.get("label"), page=page,
                   identity=idy, latex_sha16=r.get("latex_sha16"))
        out.append(rec)
    return out, refused


def distribution(rows):
    """The two populations the floor has to separate."""
    gaps = sorted(r["widest_gap"] for r in rows if r.get("ink"))
    if not gaps:
        return
    print(f"widest interior gap, {len(gaps)} rows with ink:")
    for q in (0, 5, 25, 50, 75, 90, 95, 99, 100):
        i = min(len(gaps) - 1, q * len(gaps) // 100)
        print(f"   p{q:<3} {gaps[i]:>6} px")
    big = [g for g in gaps if g > 0]
    print(f"   rows with no interior gap at all: {len(gaps) - len(big)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--list", type=pathlib.Path, required=True)
    ap.add_argument("--library", type=pathlib.Path, default=LIB)
    ap.add_argument("--floor", type=float, default=0.0,
                    help="least interior gap counted as a NUMBER separation, "
                         "in 400 dpi px. 0 measures without splitting. Place "
                         "it between the two populations --distribution shows.")
    ap.add_argument("--distribution", action="store_true")
    ap.add_argument("--out", type=pathlib.Path, default=None)
    args = ap.parse_args()
    rows, refused = run(args.list, args.library, args.floor)
    print(f"{len(rows)} rows measured, {len(refused)} refused, "
          f"{sum(1 for r in rows if not r['ink'])} with NO ink in their region")
    for lbl, why in refused[:8]:
        print(f"   refused {lbl}: {why}")
    if args.distribution:
        distribution(rows)
    if args.floor:
        split = [r for r in rows if r.get("number_box")]
        print(f"number separated at floor {args.floor}: {len(split)} of {len(rows)}")
    if args.out:
        args.out.write_text(json.dumps({"list": str(args.list),
                                        "floor": args.floor,
                                        "rows": rows,
                                        "refused": refused}, indent=1))
        print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
