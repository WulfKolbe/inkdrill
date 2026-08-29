"""Where a report's table is, and which rows it has (286).

ONE implementation of the page detection, imported by
`reportcompare.py` and by `reportpages.py`. Two copies of this would
drift, and the second copy is always the one that goes wrong -- so
the probe, the contiguous-run rule and the sliver filter live here
and nowhere else.

WHY THIS IS IN tools/ AND NOT A PACKAGE SUBCOMMAND. It shells out to
ghostscript. The `inkdrill` package invokes exactly one external
binary -- `pdffonts`, in `font.py`, fenced off behind a documented
guarantee that the parser itself runs no subprocess -- and adding
ghostscript to it would widen that for a convenience. Every gs-using
entry point in this project already lives in `tools/`. A consumer
calling `python3 tools/reportpages.py` gets the same subprocess
interface it would have got from a subcommand.

THE HEADER RULE IS AN ARGUMENT, NOT A CONSTANT, and that is the whole
reason this file exists rather than a copied function. `reportcompare`
skips lattice row 0 on EVERY page, which is right for a table using
`\\endhead` -- LaTeX reprints the header on each page. A table whose
header prints ONCE has a data row at index 0 on every page after the
first, and the unconditional skip would drop one row per page,
silently, leaving every identifier after page one paired with the
wrong equation. Pass what the table does; do not infer it.
"""
import subprocess
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from inkdrill.pnmio import read_pnm_stream                     # noqa: E402
from inkdrill.pngio import auto_mask                           # noqa: E402
from inkdrill.__main__ import _table_cells                     # noqa: E402

SLIVER_PX = 40          # at 300 dpi; see `row_bands`


def npages(pdf) -> int:
    out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True,
                         text=True).stdout
    import re
    m = re.search(r"^Pages:\s+(\d+)", out, re.M)
    if m is None:
        raise SystemExit(f"{pdf}: pdfinfo reported no page count")
    return int(m.group(1))


def probe(pdf, n, columns, dpi=150, tol=4.0, gap=3):
    """(pages, census). The LEADING CONTIGUOUS RUN of pages whose
    lattice has `columns` columns, and a census of every count seen.

    The run stops at the first gap wider than `gap`, so a table
    interrupted by a differently-shaped page is reported short rather
    than stitched across the interruption. That is a real limit and
    the census is returned so a caller can see what was skipped
    instead of inferring it from a small number.
    """
    hits, seen = [], {}
    for lo in range(1, n + 1, 25):
        hi = min(lo + 24, n)
        out = subprocess.run(
            ["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=pgmraw",
             f"-r{dpi}", f"-dFirstPage={lo}", f"-dLastPage={hi}",
             "-sOutputFile=%stdout", str(pdf)],
            capture_output=True, check=True).stdout
        for i, img in enumerate(read_pnm_stream(out, dpi=(float(dpi),
                                                          float(dpi)))):
            mask, _ = auto_mask(img.gray, img.width, img.height, 200)
            cells = _table_cells(mask, tol)
            nc = max(c for _, c in cells) + 1 if cells else 0
            seen[nc] = seen.get(nc, 0) + 1
            if nc == columns:
                hits.append(lo + i)
    run, last = [], 0
    for p in hits:
        if not run and p <= 3:
            run.append(p); last = p
        elif run and p - last <= gap:
            run.extend(range(last + 1, p + 1)); last = p
        elif run:
            break
    return run, seen


def row_bands(mask, tol=4.0, header="every", first_page=False,
              sliver=SLIVER_PX):
    """The table's data rows on ONE page, in printed order.

    Returns `(bands, ncols, reason)`. `bands` is [(row, y0, y1)] with
    the header and the inter-row slivers removed; `reason` is None
    when the page was read and a string when it was not.

    A row under `sliver` px tall is an inter-row strip, not a row --
    measured at 300 dpi, where a real body row is 100 px and up. It
    is also what removes a longtable's page-break continuation footer
    on the reports that have one.

    `header` is `every` (LaTeX `\\endhead` reprints it on each page)
    or `first` (printed once). With `first`, row 0 is dropped ONLY on
    the first page of the table; on every other page row 0 is DATA.
    """
    cells = _table_cells(mask, tol)
    if cells is None:
        return [], 0, "no ink region with two or more holes -- no table"
    if not cells:
        return [], 0, "a table region was found but no cell survived"
    nrows = max(r for r, _ in cells) + 1
    ncols = max(c for _, c in cells) + 1
    skip0 = header == "every" or (header == "first" and first_page)
    out = []
    for r in range(nrows):
        if r == 0 and skip0:
            continue
        b = cells.get((r, 0))
        if b is None:
            continue
        if b[3] - b[1] < sliver:
            continue
        out.append((r, b[1], b[3]))
    if not out:
        return [], ncols, (f"{nrows} lattice row(s), none survived the "
                           f"header rule and the {sliver} px sliver floor")
    return out, ncols, None
