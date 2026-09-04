"""602 -- does the emitted rect agree with the lattice, and by how much?

601 specified the rect and did not claim the two agree. This compares
them, per edge, on real rows -- with the "emitted" side coming from
the PDF's own vector content (`tools/pdfrules.py`), which is an
independent source from the raster the lattice is built on.

A per-edge delta is reported rather than a pass. A systematic offset
is a spec bug and fixable; a scattered one is a detection difference
and is the finding.
"""

from __future__ import annotations

import argparse
import pathlib
import statistics
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from inkdrill.__main__ import _drop_slivers, _table_cells      # noqa: E402
from inkdrill.cellrect import row_rects                        # noqa: E402
from inkdrill.pnmio import mask_from_pgm                       # noqa: E402
from pdfrules import rules                                     # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("doc")
    ap.add_argument("page", type=int)
    ap.add_argument("--library", type=pathlib.Path,
                    default=pathlib.Path.home() / "pdfdrill-library")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--rows", type=int, default=10)
    ap.add_argument("--work", type=pathlib.Path,
                    default=pathlib.Path("/tmp"))
    args = ap.parse_args()
    pdf = args.library / args.doc / "report.pdf"

    out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True,
                         text=True).stdout
    w_bp, h_bp = 0.0, 0.0
    for line in out.splitlines():
        if line.startswith("Page size:"):
            parts = line.split()
            w_bp, h_bp = float(parts[2]), float(parts[4])
    print(f"{args.doc} p{args.page}   MediaBox {w_bp} x {h_bp} bp   "
          f"{args.dpi} dpi")

    horiz, vert = rules(pdf, args.page, h_bp)
    # the table's rules: the vertical ones that span the table, and the
    # horizontal ones that run its full width
    xs = sorted(vert)
    full = max(x1 - x0 for x0, x1 in horiz.values())
    ys = sorted((y for y, (x0, x1) in horiz.items()
                 if x1 - x0 > full * 0.98), reverse=True)
    print(f"emitted: {len(xs)} column rules, {len(ys)} full-width row "
          f"rules -> {len(ys) - 1} rows, {len(xs) - 1} columns")

    f = args.work / f"cc_{args.doc[:16]}_{args.page}_{args.dpi}.pgm"
    if not f.exists():
        subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH",
                        "-sDEVICE=pgmraw", f"-r{args.dpi}",
                        f"-dFirstPage={args.page}",
                        f"-dLastPage={args.page}",
                        f"-sOutputFile={f}", str(pdf)], check=True)
    m = mask_from_pgm(f, threshold=200)
    lat = _drop_slivers(_table_cells(m, 4.0, debug={}), m.height)
    nr = max(r for r, _ in lat) + 1
    nc = max(c for _, c in lat) + 1
    print(f"lattice: {nr} rows x {nc} columns\n")

    if nc != len(xs) - 1:
        print(f"  COLUMN COUNTS DIFFER: lattice {nc}, emitted {len(xs)-1}")

    d = {k: [] for k in ("x0", "y0", "x1", "y1")}
    print(f"  {'row':>3} {'col':>3} | {'lattice (x0,y0,x1,y1)':>28} | "
          f"{'emitted':>28} | dx0 dy0 dx1 dy1")
    shown = 0
    for r in range(min(nr, len(ys) - 1, args.rows)):
        rects = row_rects(xs, ys[r], ys[r + 1],
                          page_height_bp=h_bp, dpi=args.dpi)
        for c in range(min(nc, len(rects))):
            if (r, c) not in lat:
                continue
            lx0, ly0, lx1, ly1 = lat[(r, c)]
            e = rects[c]
            dd = (e.x0 - lx0, e.y0 - ly0, e.x1 - lx1, e.y1 - ly1)
            for k, v in zip(("x0", "y0", "x1", "y1"), dd):
                d[k].append(v)
            if shown < 24:
                print(f"  {r:>3} {c:>3} | {str((lx0,ly0,lx1,ly1)):>28} | "
                      f"{str(tuple(e)):>28} | "
                      + " ".join(f"{x:+3d}" for x in dd))
                shown += 1
    n = len(d["x0"])
    print(f"\n  {n} cells compared")
    print(f"  {'edge':>5} {'median':>7} {'min':>5} {'max':>5} "
          f"{'|d|<=1':>7} {'|d|<=2':>7}")
    for k in ("x0", "y0", "x1", "y1"):
        v = d[k]
        print(f"  {k:>5} {statistics.median(v):>7.1f} {min(v):>5} {max(v):>5} "
              f"{100*sum(1 for x in v if abs(x)<=1)/n:>6.1f}% "
              f"{100*sum(1 for x in v if abs(x)<=2)/n:>6.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
