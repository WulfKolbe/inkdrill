"""602 -- the rule geometry a `\\zsavepos` emitter would produce.

Stands in for 580 stage 2 so the CONSUMER can be checked before the
emitter exists. It reads the rules out of the PDF's own vector content
via `mutool trace`, which is an INDEPENDENT source from the raster
lattice `_table_cells` builds -- that independence is the whole point,
since comparing the lattice against something derived from the lattice
would agree by construction and prove nothing.

Output is PDF user space (bp), y UP from the bottom of the page, which
is the convention 601 measured `\\zsavepos` to use.
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import re
import subprocess

_PATH = re.compile(r'<stroke_path[^>]*transform="([^"]+)"[^>]*>(.*?)</stroke_path>',
                   re.S)
_PT = re.compile(r'<(moveto|lineto) x="([-\d.]+)" y="([-\d.]+)"/>')


def rules(pdf: pathlib.Path, page: int, page_h_bp: float):
    """(horizontal, vertical) rule positions in bp, y up from bottom.

    horizontal -> {y: (x_min, x_max)}    vertical -> {x: (y_min, y_max)}
    """
    xml = subprocess.run(["mutool", "trace", str(pdf), str(page)],
                         capture_output=True, text=True, timeout=300).stdout
    horiz, vert = {}, {}
    for tf, body in _PATH.findall(xml):
        a, b, c, d, e, f = (float(v) for v in tf.split())
        pts = [(float(x), float(y)) for _k, x, y in _PT.findall(body)]
        if len(pts) != 2:
            continue
        # apply the CTM, then flip mutool's y-down device space into
        # PDF user space (y up from the bottom of the page)
        dev = [(a * x + c * y + e, b * x + d * y + f) for x, y in pts]
        usr = [(dx, page_h_bp - dy) for dx, dy in dev]
        (x0, y0), (x1, y1) = usr
        if abs(y0 - y1) < 0.05:
            k = round((y0 + y1) / 2, 3)
            lo, hi = sorted((x0, x1))
            got = horiz.get(k)
            horiz[k] = (min(lo, got[0]), max(hi, got[1])) if got else (lo, hi)
        elif abs(x0 - x1) < 0.05:
            k = round((x0 + x1) / 2, 3)
            lo, hi = sorted((y0, y1))
            got = vert.get(k)
            vert[k] = (min(lo, got[0]), max(hi, got[1])) if got else (lo, hi)
    return horiz, vert


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=pathlib.Path)
    ap.add_argument("page", type=int)
    ap.add_argument("--page-height", type=float, default=841.89)
    args = ap.parse_args()
    h, v = rules(args.pdf, args.page, args.page_height)
    print(f"page {args.page}: {len(h)} horizontal, {len(v)} vertical rules "
          f"(bp, y up from bottom)")
    print("\nvertical rules (column boundaries), x:")
    for x in sorted(v):
        y0, y1 = v[x]
        print(f"   x {x:9.3f}   spans y {y0:8.3f} .. {y1:8.3f}")
    print("\nhorizontal rules (row boundaries), y, longest first:")
    wide = sorted(h.items(), key=lambda kv: kv[1][0] - kv[1][1])
    for y, (x0, x1) in sorted(h.items(), reverse=True)[:30]:
        print(f"   y {y:9.3f}   spans x {x0:8.3f} .. {x1:8.3f}"
              f"   width {x1-x0:8.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
