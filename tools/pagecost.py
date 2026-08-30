#!/usr/bin/env python3
"""380 — where the ~60 s per page goes: rasterise, lattice, five-tuple.

    python3 tools/pagecost.py --pdf report.pdf --page N [--columns 6]

The table path costs about a minute a page and 382's pair comparator does the
same measurement in a tenth of a second. Before optimising either, the minute
has to be attributed: a saving is only worth what the stage it removes costs.
"""
import argparse
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from inkdrill.pngio import read_png, auto_mask                  # noqa: E402
from inkdrill.mathstruct import pair_stats                      # noqa: E402
from inkdrill.__main__ import _table_cells, _cell_crop                      # noqa: E402


def rasterise(pdf, page, dpi, out):
    t = time.time()
    subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=png16m",
                    f"-r{dpi}", f"-dFirstPage={page}", f"-dLastPage={page}",
                    f"-sOutputFile={out}", str(pdf)], capture_output=True)
    return time.time() - t


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True, type=pathlib.Path)
    ap.add_argument("--page", type=int, default=2)
    ap.add_argument("--columns", type=int, default=6)
    ap.add_argument("--tol", type=float, default=4.0)
    a = ap.parse_args()
    import tempfile
    w = pathlib.Path(tempfile.mkdtemp())

    total = time.time()
    stages = {}
    # the table path compares ONE page at TWO resolutions
    stages["rasterise 300dpi"] = rasterise(a.pdf, a.page, 300, w / "a.png")
    stages["rasterise 600dpi"] = rasterise(a.pdf, a.page, 600, w / "b.png")

    masks = {}
    t = time.time()
    for k, f in (("A", w / "a.png"), ("B", w / "b.png")):
        img = read_png(f)
        masks[k], _ = auto_mask(img.gray, img.width, img.height, 200)
    stages["decode + auto_mask"] = time.time() - t

    cells = {}
    t = time.time()
    for k in ("A", "B"):
        cells[k] = _table_cells(masks[k], a.tol)
    stages["lattice (_table_cells)"] = time.time() - t

    # the five-tuple, on the two compared columns of every row
    t = time.time()
    n = 0
    for k in ("A", "B"):
        c = cells[k]
        if not c:
            continue
        nc = max(x for _, x in c) + 1
        nr = max(y for y, _ in c) + 1
        for r in range(nr):
            for col in (nc - 2, nc - 1):
                box = c.get((r, col))
                if box is None:
                    continue
                y0, x0, y1, x1 = box
                sub = _cell_crop(masks[k], y0, x0, y1 - 1, x1 - 1)
                pair_stats(sub)
                n += 1
    stages["five-tuple x %d cells" % n] = time.time() - t

    el = time.time() - total
    print("  page %d of %s" % (a.page, a.pdf.name))
    for k, v in stages.items():
        print("    %-28s %6.1f s   %4.1f%%" % (k, v, 100 * v / el))
    print("    %-28s %6.1f s" % ("TOTAL", el))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
