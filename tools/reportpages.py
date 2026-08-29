"""Which pages hold a report's table, and which rows are on them (286).

    python3 tools/reportpages.py --pdf report.pdf --columns 6 \
        [--header first|every] [--dpi 300]

JSON on stdout. Written for pdfdrill's `regionink`, which needs the
page detection `reportcompare` already has and should not reimplement
it -- two implementations drift and the second is the worse one. The
detection itself lives in `pagedetect.py`; this is the interface.

    {
      "pdf": "...", "columns": 6, "header": "first",
      "pages": [3, 4],
      "census": {"6": 2, "0": 11},
      "rows": {"3": [{"row": 1, "y0": 220, "y1": 460}, ...]},
      "unreadable": [{"page": 4, "reason": "..."}],
      "totals": {"pages": 2, "readable": 1, "rows": 4}
    }

A page that was DETECTED but could not be read appears in
`unreadable` with a reason and contributes no rows. That distinction
is the point: a consumer joining against a manifest can tell "one row
expected, none measurable, and here is why" from "one row short",
and only the first is safe to carry as a gap.
"""
import argparse
import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from pagedetect import probe, row_bands, npages          # noqa: E402
from inkdrill.pngio import read_png, auto_mask           # noqa: E402

ap = argparse.ArgumentParser(prog="tools/reportpages.py",
                             description=__doc__.strip().splitlines()[0])
ap.add_argument("--pdf", required=True, type=pathlib.Path)
ap.add_argument("--columns", required=True, type=int,
                help="the table's column count, from the producer's "
                     "own source -- never guessed here")
ap.add_argument("--header", choices=("first", "every"), default="every",
                help="`every` when the table uses \\endhead so LaTeX "
                     "reprints the header per page; `first` when it "
                     "prints once. Getting this wrong drops one DATA "
                     "row per page and offsets every identifier after "
                     "the first page, silently.")
ap.add_argument("--dpi", type=int, default=300,
                help="render dpi for the row pass; the 40 px sliver "
                     "floor is calibrated at 300")
ap.add_argument("--probe-dpi", type=int, default=150)
ap.add_argument("--tol", type=float, default=4.0)
A = ap.parse_args()

if not A.pdf.is_file():
    raise SystemExit(f"{A.pdf}: no such file")

pages, census = probe(A.pdf, npages(A.pdf), A.columns,
                      dpi=A.probe_dpi, tol=A.tol)
rows, unreadable = {}, []
import tempfile
tmp = pathlib.Path(tempfile.mkdtemp())
for k, p in enumerate(pages):
    out = tmp / f"p{p}.png"
    r = subprocess.run(
        ["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=png16m",
         f"-r{A.dpi}", f"-dFirstPage={p}", f"-dLastPage={p}",
         f"-sOutputFile={out}", str(A.pdf)], capture_output=True)
    if r.returncode or not out.is_file():
        unreadable.append({"page": p, "reason": "ghostscript failed"})
        continue
    img = read_png(out)
    mask, _ = auto_mask(img.gray, img.width, img.height, 200)
    bands, ncols, why = row_bands(mask, tol=A.tol, header=A.header,
                                  first_page=(k == 0))
    out.unlink(missing_ok=True)
    if why:
        unreadable.append({"page": p, "reason": why, "columns": ncols})
        continue
    rows[str(p)] = [{"row": r_, "y0": y0, "y1": y1}
                    for r_, y0, y1 in bands]

json.dump({"pdf": str(A.pdf), "columns": A.columns, "header": A.header,
           "dpi": A.dpi,
           "pages": pages,
           "census": {str(k): v for k, v in sorted(census.items())},
           "rows": rows,
           "unreadable": unreadable,
           "totals": {"pages": len(pages), "readable": len(rows),
                      "rows": sum(len(v) for v in rows.values())}},
          sys.stdout, indent=1)
print()
