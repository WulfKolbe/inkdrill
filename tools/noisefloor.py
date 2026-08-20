"""S5: the noise floor of the compare distance.

Nothing below this floor is a finding. The same expression, on the
same page, at the same dpi, rasterized by two DIFFERENT renderers
(ghostscript and poppler's pdftoppm) must be identical content -- any
distance the compare loop reports between those two renditions is
instrument noise, not a disagreement between a conversion and a scan.

Population: display-equation rows of formula reports, the same rows
the findings file is built from, measured through the same
`pair_stats` five-tuple. Both renderers are run at the SAME dpi; the
only variable is the rasterizer.

Usage: python3 tools/noisefloor.py <report.pdf> [more.pdf ...]
       [--limit N] [--yes] [--dpi 300] [--expressions 200]
Writes results/noisefloor-<stamp>.tsv (document, page, line, distance,
comp_delta) and prints the distribution.
"""

from __future__ import annotations

import argparse
import datetime
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import corpusgate                                          # noqa: E402
from inkdrill.__main__ import _cell_crop, _table_cells     # noqa: E402
from inkdrill.mathstruct import pair_stats                 # noqa: E402
from inkdrill.pngio import auto_mask, read_png             # noqa: E402

RESULTS = pathlib.Path(__file__).resolve().parent.parent / "results"


def render(pdf, page, dpi, out, renderer):
    """One page, one renderer, an exact output path."""
    if renderer == "gs":
        subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH",
                        "-sDEVICE=png16m", f"-r{dpi}",
                        f"-dFirstPage={page}", f"-dLastPage={page}",
                        f"-sOutputFile={out}", str(pdf)], check=True)
    else:
        stem = out.with_suffix("")
        subprocess.run(["pdftoppm", "-png", "-r", str(dpi),
                        "-f", str(page), "-l", str(page),
                        "-singlefile", str(pdf), str(stem)], check=True)
    return out


def rows_of(png, tol=6.0):
    """(line -> (rendered five-tuple, scan five-tuple)) for one page."""
    img = read_png(png)
    m = auto_mask(img.gray, img.width, img.height, 200)[0]
    cells = _table_cells(m, tol)
    if not cells:
        return {}
    nr = max(r for r, _ in cells) + 1
    nc = max(c for _, c in cells) + 1
    if nc < 4:
        return {}
    out = {}
    for r in range(1, nr):
        b0 = cells[(r, 0)]
        if b0[3] - b0[1] < 40:                 # sliver row
            continue
        cell = cells[(r, nc - 2)]              # the RENDERED column
        crop = _cell_crop(m, cell[0], cell[1], cell[2] - 1, cell[3] - 1)
        st = pair_stats(crop)
        out[r] = tuple(st[k] for k in ("components", "holes", "stacked",
                                       "centred", "offset"))
    return out


def main():
    ap = argparse.ArgumentParser(prog="tools/noisefloor.py",
                                 description=__doc__.splitlines()[0])
    ap.add_argument("pdf", nargs="+")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--expressions", type=int, default=200,
                    help="stop once this many expressions are compared")
    corpusgate.add_arguments(ap)
    args = ap.parse_args()

    def pages_of(p):
        import re
        out = subprocess.run(["pdfinfo", str(p)], capture_output=True,
                             text=True).stdout
        return int(re.search(r"^Pages:\s+(\d+)", out, re.M).group(1))

    chosen = corpusgate.gate("noisefloor", args.pdf, args.limit, args.yes,
                             count_pages=lambda a: pages_of(a))
    rows = []
    work = pathlib.Path(tempfile.mkdtemp())
    for pdf in chosen:
        pdf = pathlib.Path(pdf)
        for page in range(1, pages_of(pdf) + 1):
            if len(rows) >= args.expressions:
                break
            a = render(pdf, page, args.dpi, work / "a.png", "gs")
            b = render(pdf, page, args.dpi, work / "b.png", "pdftoppm")
            ra, rb = rows_of(a), rows_of(b)
            for ln in sorted(set(ra) & set(rb)):
                va, vb = ra[ln], rb[ln]
                rows.append((pdf.parent.name, page, ln,
                             sum(abs(x - y) for x, y in zip(va, vb)),
                             abs(va[0] - vb[0])))
            print(f"{pdf.parent.name} p{page}: {len(ra)} vs {len(rb)} rows, "
                  f"{len(rows)} expressions compared", flush=True)
        if len(rows) >= args.expressions:
            break

    RESULTS.mkdir(exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    f = RESULTS / f"noisefloor-{stamp}.tsv"
    f.write_text("\n".join(
        ["document\tpage\tline\tdistance\tcomp_delta"]
        + ["\t".join(map(str, r)) for r in rows]) + "\n")
    d = sorted(r[3] for r in rows)
    cd = [r[4] for r in rows]
    if not d:
        raise SystemExit("no expressions compared -- nothing to report")
    import statistics
    print(f"\nNOISE FLOOR over {len(d)} expressions, {args.dpi} dpi, "
          f"ghostscript vs pdftoppm:")
    print(f"  distance: zero {d.count(0)}/{len(d)}, median "
          f"{statistics.median(d)}, p95 {d[int(.95*len(d))-1]}, max {max(d)}")
    print(f"  component delta: zero {cd.count(0)}/{len(cd)}, max {max(cd)}")
    print(f"  -> {f}")


if __name__ == "__main__":
    main()
