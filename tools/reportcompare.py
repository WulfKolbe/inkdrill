"""Compare the Rendered and Scan columns of formula reports.

Usage: python3 tools/reportcompare.py [list.txt] [library]
  The list is pdfdrill's report roster (lines ending
  "-> ~/pdfdrill-library/<dir>/report.pdf"). Renders cache under
  $INKDRILL_WORK; each document gets <dir>/report.compare.tsv. An
  input yielding zero rows is REPORTED with its reason and sets a
  nonzero exit (P16) -- an empty result is a defect, not a silence.

Per report: 150 dpi probe -> LEADING RUN of 5-col pages (gap <= 3) =
the display section; render those at 300+600; `inkdrill compare` per
page; aggregate with the sliver filter (lattice rows < 40 px @300 are
inter-row strips, not table rows) into <dir>/report.compare.tsv.
"""
import concurrent.futures as cf
import os, pathlib, re, subprocess, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from inkdrill.pnmio import read_pnm_stream
from inkdrill.pngio import read_png, auto_mask
from inkdrill.__main__ import _table_cells

import argparse, datetime, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import corpusgate

_ap = argparse.ArgumentParser(
    prog="tools/reportcompare.py",
    description=__doc__.strip().splitlines()[0])
_ap.add_argument("list", nargs="?", default=None,
                 help="report roster (default: <library>/P13-arxiv-reports.txt)")
_ap.add_argument("library", nargs="?", default="~/pdfdrill-library")
_ap.add_argument("--columns", type=int, default=None,
                 help="override the display-table column count; by "
                      "default it is read PER DOCUMENT from its own "
                      "report.tex, because the corpus holds both the "
                      "pre-099 5-column and post-099 6-column form")
corpusgate.add_arguments(_ap)
ARGS = _ap.parse_args()

LIB = pathlib.Path(ARGS.library).expanduser()
COLUMNS = ARGS.columns
LIST = pathlib.Path(ARGS.list) if ARGS.list else \
    LIB / "P13-arxiv-reports.txt"
S = pathlib.Path(os.environ.get("INKDRILL_WORK") or
                 (tempfile.gettempdir() + "/inkdrill-reportcompare"))
S.mkdir(parents=True, exist_ok=True)
RESULTS = pathlib.Path(__file__).resolve().parent.parent / "results"
if not LIST.is_file():
    raise SystemExit(__doc__.strip().splitlines()[2] +
                     f"\n  no such list: {LIST}")
ALL_DIRS = re.findall(r"-> ~/pdfdrill-library/(\S+)/report\.pdf",
                      LIST.read_text())
if not ALL_DIRS:
    raise SystemExit(f"{LIST}: no '-> ~/pdfdrill-library/<dir>/report.pdf' "
                     f"lines found")

def check_fresh(name, pdf):
    """Refuse a report.pdf older than its own report.tex.

    The harness already clears its render cache against the pdf's
    mtime. Nothing checked the pdf against its SOURCE, and on
    2026-08-21 exactly that gap put a stale artifact into a
    measurement: 0902.0431's tex was regenerated and the pdf was not
    recompiled, so a 230-page build of an older tex was measured as
    current and produced a 22-cell population difference that took
    two sessions and three hypotheses to trace. One mtime comparison
    would have caught it at the door.

    Refused rather than warned: a warning in a two-hour batch scrolls
    past, and the whole point of P16 is that a defect must not read
    as an absence.
    """
    if not pdf.is_file():
        # named, not a raw FileNotFoundError three frames later: an
        # absence has to say which file and for which document (P16).
        raise SystemExit(f"{name}: no report.pdf at {pdf}")
    tex = pdf.with_suffix(".tex")
    if tex.is_file() and pdf.stat().st_mtime < tex.stat().st_mtime:
        raise SystemExit(
            f"{name}: report.pdf is OLDER than report.tex "
            f"({pdf.stat().st_mtime:.0f} < {tex.stat().st_mtime:.0f}) -- "
            f"the pdf is a build of a superseded source. Recompile it "
            f"(`pdfdrill reporttex <pdf> --compile`) before measuring, "
            f"or the measurement describes an artifact that no longer "
            f"corresponds to its own tex.")


def npages(pdf):
    out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True,
                         text=True).stdout
    return int(re.search(r"^Pages:\s+(\d+)", out, re.M).group(1))

DIRS = corpusgate.gate(
    "reportcompare", ALL_DIRS, ARGS.limit, ARGS.yes,
    count_pages=lambda n: npages(LIB / n / "report.pdf"))


def demoted_idents(name):
    """Identifiers whose Rendered cell is the string '(not rendered)'.

    A demoted row has NO rendering: `renderable()` refused the LaTeX
    at generation time and the report printed a placeholder. Comparing
    that placeholder against a scan of real mathematics measures
    nothing -- the ink of '(not rendered)' is 13 components and 6
    holes whatever the equation was -- and it produced 63 of this
    channel's 401 component-class findings, including its largest
    (dist 922). Found by pdfdrill failing to reproduce three of them
    from the content; the content was never on the page.

    Read from the report's own tex, which is the artifact, rather
    than from the model: the model-side label missed two of the four
    demoted rows in 0707.4470.
    """
    tex = LIB / name / "report.tex"
    if not tex.is_file():
        return set()
    return {m.group(1).replace("\\", "").replace("allowbreak{}", "")
            for m in re.finditer(
                r"\\ident\{([^&\n]*?EQ\d+)\}(.*?)\\\\ \\hline",
                tex.read_text(), re.S)
            if "emph{(not rendered)}" in m.group(2)}


def idents_for(name):
    """[(identifier, source page), ...] in display-table order.

    Read from the report's own .tex, which is the only place the
    identifier lives -- inkdrill reads no text. Row i of the compare
    output is equation i, and a COUNT MISMATCH means that assumption
    broke, so ids are withheld rather than guessed (see run_rows).
    """
    tex = LIB / name / "report.tex"
    if not tex.is_file():
        return []
    # The identifier may carry an equation number before the column
    # break (`\ident{bh2\_EQ0001} \eqnum{(30)} & 020 &`) and, since
    # the overprint fix, break opportunities INSIDE the braces
    # (`0803.\allowbreak{}2924\_\allowbreak{}EQ0001`) -- so the
    # capture cannot stop at the first `}`.
    def _clean(t):
        return t.replace("\\allowbreak{}", "").replace("\\", "")
    return [(_clean(m.group(1)), m.group(2)) for m in
            re.finditer(r"\\ident\{([^&\n]*?EQ\d+)\}[^&\n]*& *(\d+) *&",
                        tex.read_text())]


def target_columns(name):
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

    Returns None when no such header exists -- the document's
    equations table has no scan column, so there is nothing in it to
    compare, and that is a REASON rather than a zero. Reading the
    .tex is not a violation of emit's G6: G6 forbids inkdrill reading
    text off a RASTER, which is what would make it agree with the
    tool it cross-checks. A column count taken from a source file
    never touches the ink measurement.
    """
    tex = LIB / name / "report.tex"
    if not tex.is_file():
        return None
    for line in tex.read_text().splitlines():
        if "textbf{Rendered}" in line and "textbf{Scan image}" in line:
            return line.count("&") + 1
    return None


def probe(pdf, n, columns=None):
    """The leading contiguous run of DISPLAY-EQUATION pages, by column
    count, plus a census of every count seen.

    The count comes from `target_columns` -- the document's own tex --
    and is verified against the raster here, so a tex that says six
    and a PDF that renders five is caught rather than averaged.

    The census is returned because a zero must not read as an
    absence (P16). A document with 5-column pages and no 6-column
    ones has a display table WITHOUT CROPS -- nothing to measure, and
    a different fact from a document with no display table at all.
    """
    want = columns or COLUMNS
    hits = []
    seen = {}
    for lo in range(1, n + 1, 25):
        hi = min(lo + 24, n)
        gs = subprocess.run(
            ["gs","-q","-dNOPAUSE","-dBATCH","-sDEVICE=pgmraw","-r150",
             f"-dFirstPage={lo}",f"-dLastPage={hi}",
             "-sOutputFile=%stdout",str(pdf)],
            capture_output=True, check=True).stdout
        for i, img in enumerate(read_pnm_stream(gs, dpi=(150.0,150.0))):
            mask,_ = auto_mask(img.gray, img.width, img.height, 200)
            cells = _table_cells(mask, 4.0)
            nc = max(c for _, c in cells) + 1 if cells else 0
            seen[nc] = seen.get(nc, 0) + 1
            if nc == want:
                hits.append(lo + i)
    run, last = [], 0
    for p in hits:
        if not run and p <= 3: run.append(p); last = p
        elif run and p - last <= 3:
            run.extend(range(last + 1, p + 1)); last = p
        elif run: break
    return run, seen

jobs = []
display_count = {}
census_of = {}
want_of = {}
# declared here, not at the aggregation step: the probe loop below
# reports a document with no scan column, and that is a zero-row
# reason like any other (P16).
zero_rows = []
for name in DIRS:
    pdf = LIB / name / "report.pdf"
    d = S / name; d.mkdir(exist_ok=True)
    # the regeneration rolled through while the first pass ran: any
    # scratch older than the pdf is from a superseded build
    pm = pdf.stat().st_mtime
    stale = [f for f in d.iterdir() if f.stat().st_mtime < pm]
    if stale:
        for f in d.iterdir(): f.unlink()
        print(f"{name}: cleared {len(stale)} stale files", flush=True)
    check_fresh(name, pdf)
    want = ARGS.columns or target_columns(name)
    if want is None:
        zero_rows.append(
            (name, "report.tex has no header carrying both Rendered "
                   "and Scan image -- the equations table has no scan "
                   "column, so there is nothing in it to compare"))
        print(f"{name}: NO SCAN COLUMN in report.tex", flush=True)
        continue
    try:
        disp, census = probe(pdf, npages(pdf), want)
    except Exception as e:
        print(f"{name}: probe FAILED {e}", flush=True); continue
    display_count[name] = len(disp)
    census_of[name] = census
    want_of[name] = want
    # the census is printed WITH the count, not instead of it: a zero
    # that says "but 40 pages read 5 columns" is a different finding
    # from a zero that says "no table anywhere" (P16).
    shape = "  ".join(f"{k}col x{v}" for k, v in sorted(census.items())
                      if k)
    print(f"{name}: display pages {len(disp)} (tex says {want} cols)"
          f"{'  [' + shape + ']' if not disp else ''}", flush=True)
    for p in disp:
        jobs.append((name, pdf, p, d))

def one(job):
    name, pdf, p, d = job
    a = d / f"p{p:03d}_r300.png"; b = d / f"p{p:03d}_r600.png"
    for dpi, out in ((300, a), (600, b)):
        if not out.exists():
            subprocess.run(["gs","-q","-dNOPAUSE","-dBATCH",
                            "-sDEVICE=png16m",f"-r{dpi}",
                            f"-dFirstPage={p}",f"-dLastPage={p}",
                            f"-sOutputFile={out}",str(pdf)], check=True)
    md = d / f"p{p:03d}.md"
    if not md.exists():
        subprocess.run([sys.executable,"-m","inkdrill","compare",
                        str(a),str(b),"-o",str(md)],
                       capture_output=True, cwd=str(pathlib.Path(__file__).resolve().parent.parent))
    return name, p

with cf.ThreadPoolExecutor(max_workers=4) as ex:
    n = 0
    for name, p in ex.map(one, jobs):
        n += 1
        if n % 25 == 0: print(f"compared {n}/{len(jobs)}", flush=True)

from findings import flag_of        # one definition (P19)


run_rows = []
demoted_rows = []
id_mismatch = []
for name in DIRS:
    d = S / name
    hdr = ("report_page\tline\tdis\tA_eq_B\tL_comp\tL_holes\tL_stk"
           "\tL_cen\tL_off\tR_comp\tR_holes\tR_stk\tR_cen\tR_off")
    rows = []
    recs = []
    for md in sorted(d.glob("p*.md")):
        p = int(md.stem[1:])
        png = d / f"p{p:03d}_r300.png"
        img = read_png(png)
        m = auto_mask(img.gray, img.width, img.height, 200)[0]
        cells = _table_cells(m, 4.0)
        if not cells: continue
        nr = max(r for r, _ in cells) + 1
        hts = {r: cells[(r, 0)][3] - cells[(r, 0)][1] for r in range(nr)}
        for line in md.read_text().splitlines()[2:]:
            c = [x.strip() for x in line.split("|")[1:-1]]
            ln = int(c[1])
            if ln == 0 or hts.get(ln, 999) < 40: continue
            L = [int(x) for x in c[3:8]]; R = [int(x) for x in c[8:13]]
            dis = sum(abs(x - y) for x, y in zip(L, R))
            rows.append("\t".join(map(str, [p, ln, dis, c[13]] + L + R)))
            recs.append((dis, abs(L[0] - R[0]), c[13] == "yes"))
    # P19: identifiers come from the report's own tex, in table order.
    # A count mismatch means the row<->equation correspondence broke;
    # ids are then withheld ("?") and the document is named in the
    # summary -- a wrong identifier is worse than none.
    idents = idents_for(name)
    # The harness compares the LEADING contiguous run of display
    # pages, so its rows are a PREFIX of the equation list -- valid
    # only while the compared pages are themselves contiguous and
    # there are at least as many equations as rows. More rows than
    # equations means the population is not display equations alone
    # (a 5-column-reading inline table shares the page), and the ids
    # are withheld: a wrong identifier is worse than none.
    pages = sorted(int(md.stem[1:]) for md in d.glob("p*.md"))
    contiguous = pages == list(range(pages[0], pages[0] + len(pages))) \
        if pages else False
    if len(idents) >= len(recs) and contiguous:
        dem = demoted_idents(name)
        for (ident, srcpage), (dis, cd, stable) in zip(idents, recs):
            if ident in dem:
                demoted_rows.append(name)
                continue
            run_rows.append((name, ident, srcpage, dis, cd,
                             flag_of(dis, cd, stable)))
    else:
        # MORE ROWS THAN EQUATIONS means the compared population is
        # not display equations alone -- on 0803.2924 the inline
        # formula table (94 rows) shares the leading page run with the
        # 23 display equations, and an inline row compares LaTeX
        # source against a rendering, with no scan in it at all. Those
        # rows are excluded from the findings file entirely rather
        # than emitted with a "?" identifier: an unusable row in a
        # findings file is worse than a named absence (P16/Q3's
        # no-partial-inclusion, applied to rows).
        why = ("more rows than equations -- population is not display "
               "equations alone" if len(idents) < len(recs)
               else "compared pages are not contiguous")
        id_mismatch.append((name, len(recs), len(idents), why))
    (LIB / name / "report.compare.tsv").write_text(
        "\n".join([hdr] + rows) + "\n")
    print(f"{name}: {len(rows)} rows -> report.compare.tsv", flush=True)
    if not rows:
        zero_rows.append(
            (name, f"probe found no {want_of.get(name)}-column display pages"
                    f" [{'  '.join(f'{k}col x{v}' for k, v in sorted(census_of.get(name, {}).items()) if k) or 'no table on any page'}]"
             if not display_count.get(name)
             else f"{display_count[name]} display pages compared but "
                  f"every row was filtered"))
# P19: one machine-readable file per corpus RUN, so a finding is a
# file a consumer can sort and filter, not prose in a commit message.
RESULTS.mkdir(exist_ok=True)
stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
run_file = RESULTS / f"compare-{LIST.stem}-{stamp}.tsv"
run_file.write_text(
    "\n".join(["bibkey\tid\tpage\tdistance\tcomp_delta\tflag"] +
              ["\t".join(map(str, r)) for r in run_rows]) + "\n")
_by = {}
for r in run_rows:
    _by[r[5]] = _by.get(r[5], 0) + 1
print(f"{len(run_rows)} rows -> {run_file}", flush=True)
if demoted_rows:
    import collections as _c
    by = _c.Counter(demoted_rows)
    print(f"  excluded {len(demoted_rows)} DEMOTED rows (no rendering to "
          f"compare) across {len(by)} documents; worst: "
          f"{', '.join(f'{k} {v}' for k, v in by.most_common(3))}",
          flush=True)
print("  flags: " + ", ".join(f"{k} {v}" for k, v in sorted(_by.items())),
      flush=True)
if id_mismatch:
    print(f"  EXCLUDED from the findings file: {len(id_mismatch)} "
          f"document(s), {sum(m[1] for m in id_mismatch)} row(s) "
          f"(row/equation count mismatch):", flush=True)
    for name, nrows, nids, why in id_mismatch:
        print(f"    {name}: {nrows} rows vs {nids} equations "
              f"in the tex -- {why}", flush=True)

# P16: an empty result is an error, not a silence -- every zero-row
# input is listed with its reason, and the exit code says so
if zero_rows:
    print(f"ZERO-ROW INPUTS ({len(zero_rows)} of {len(DIRS)}):",
          flush=True)
    for name, why in zero_rows:
        print(f"  ZERO {name}: {why}", flush=True)
print("ALL DONE", flush=True)
import sys
sys.exit(1 if zero_rows else 0)
