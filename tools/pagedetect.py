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


def target_columns(tex):
    """How many columns THIS document's display-equation table has,
    read from its own report.tex.

    Not a constant, and the reason is that a constant was wrong twice
    in one day. The count was 5; pdfdrill's task 099 added a
    Confidence column and made it 6. The corpus now holds BOTH eras
    -- 1101.4542 was built 08-21 with no `confcell` and reads 5,
    bh2 and 0902.0431 were rebuilt 08-22 and read 6 -- so any single
    number skips one era entirely and reports it as "no display
    pages", which is the BH1org_OCR failure spread across a thousand
    documents.

    The header row carrying BOTH `Rendered` and `Scan image` is the
    display-equation table with crops, and only that table has both.
    Counting its cells is exact, independent of the era, and
    self-correcting if the format changes again:

        6   ...\textbf{Conf.} & \textbf{LaTeX source}
                & \textbf{Rendered} & \textbf{Scan image}
        5   the same without Conf. (pre-099)

    Takes the path to the document's report.tex. Lives here, not in
    the harness that first needed it, because two harnesses now read
    the column count and a second copy is how the constant got wrong
    twice in the first place.

    Returns None when no such header exists -- the document's
    equations table has no scan column, so there is nothing in it to
    compare, and that is a REASON rather than a zero. Reading the
    .tex is not a violation of emit's G6: G6 forbids inkdrill reading
    text off a RASTER, which is what would make it agree with the
    tool it cross-checks. A column count taken from a source file
    never touches the ink measurement.
    """
    tex = pathlib.Path(tex)
    if not tex.is_file():
        return None
    for line in tex.read_text().splitlines():
        if "textbf{Rendered}" in line and "textbf{Scan image}" in line:
            return line.count("&") + 1
    return None

def npages(pdf) -> int:
    out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True,
                         text=True).stdout
    import re
    m = re.search(r"^Pages:\s+(\d+)", out, re.M)
    if m is None:
        raise SystemExit(f"{pdf}: pdfinfo reported no page count")
    return int(m.group(1))


def scan_columns(pdf, n, dpi=150, tol=4.0):
    """[(page, lattice column count)] for every page, in order.

    The one place a page is rendered and counted. `probe` and `tables`
    both read this, so the two selections can never disagree about what
    is on a page -- only about which pages they want.

    G1: every page 1..n appears exactly once, in order.
    G2: a page with no lattice reports 0 columns, not absence.
    """
    out = []
    for lo in range(1, n + 1, 25):
        hi = min(lo + 24, n)
        raw = subprocess.run(
            ["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=pgmraw",
             f"-r{dpi}", f"-dFirstPage={lo}", f"-dLastPage={hi}",
             "-sOutputFile=%stdout", str(pdf)],
            capture_output=True, check=True).stdout
        for i, img in enumerate(read_pnm_stream(raw, dpi=(float(dpi),
                                                          float(dpi)))):
            mask, _ = auto_mask(img.gray, img.width, img.height, 200)
            cells = _table_cells(mask, tol)
            out.append((lo + i, max(c for _, c in cells) + 1 if cells else 0))
    return out


def group_tables(per_page):
    """Maximal contiguous runs of pages sharing a column count (320).

    A column COUNT cannot identify a table when two tables in one
    document share one. pdfdrill's report has four longtables --
    equations, formulas, tables, image regions -- and the first and last
    are both six columns wide, so `--columns 6` matched both and
    returned 69 rows against 6 identifiers. Their ORDER, however, is
    fixed by the builder, so an ordinal identifies them and a column
    count cross-checks it.

    G1: a run is contiguous in page number AND constant in column count.
    G2: a page with no lattice (0 columns) belongs to no table, and
        ENDS the run it follows -- two tables separated by prose are two
        tables, not one stitched across the gap. `probe`'s gap tolerance
        of 3 is what stitched pages 1 and 4 of 2208.09292 into a single
        selection spanning all four tables.
    G3: ordinals are 1-based in page order.
    """
    runs = []
    for page, ncols in per_page:
        if not ncols:
            continue
        if (runs and runs[-1]["columns"] == ncols
                and runs[-1]["pages"][-1] == page - 1):
            runs[-1]["pages"].append(page)
        else:
            runs.append({"columns": ncols, "pages": [page]})
    for i, r in enumerate(runs, 1):
        r["ordinal"] = i
    return runs


def tables(pdf, n, dpi=150, tol=4.0):
    """Every table in the report, in page order, with its ordinal."""
    return group_tables(scan_columns(pdf, n, dpi=dpi, tol=tol))


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
    for page, nc in scan_columns(pdf, n, dpi=dpi, tol=tol):
        seen[nc] = seen.get(nc, 0) + 1
        if nc == columns:
            hits.append(page)
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
