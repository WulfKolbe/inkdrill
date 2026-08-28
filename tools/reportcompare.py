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
# `(\S+)` here silently dropped 18 of 199 documents on 2026-08-22 --
# every one whose directory name contains a SPACE ("Uebungsblatt 01",
# "Geometric algebra for physicists - errata"). The roster pdfdrill
# supplies has none, so the bug was invisible until this side
# generated its own. `(.+?)` anchored at end of line takes the whole
# name; a directory name cannot contain a newline, and "/report.pdf"
# at end of line is the only place the capture can stop.
_LINES = [l for l in LIST.read_text(errors="replace").splitlines()
          if l.strip()]
ALL_DIRS = re.findall(r"-> ~/pdfdrill-library/(.+?)/report\.pdf\s*$",
                      "\n".join(_LINES), re.M)
if not ALL_DIRS:
    raise SystemExit(f"{LIST}: no '-> ~/pdfdrill-library/<dir>/report.pdf' "
                     f"lines found")
# The RECONCILIATION is the guard, not the pattern. A regex that
# matches fewer lines than the file holds is a filter nobody chose,
# and this one read as "199 documents" while running 181. Refused
# rather than warned: the count is the population of every number the
# run produces, and a warning about it scrolls past in a two-hour
# batch.
if len(ALL_DIRS) != len(_LINES):
    missed = [l for l in _LINES
              if not re.search(r"-> ~/pdfdrill-library/(.+?)/report\.pdf\s*$",
                               l)]
    raise SystemExit(
        f"{LIST}: {len(_LINES)} non-empty lines but only "
        f"{len(ALL_DIRS)} parsed as a report path. The population "
        f"would silently be {len(ALL_DIRS)}. Unparsed, first 5:\n  " +
        "\n  ".join(missed[:5]))

def check_phase(name, pdf):
    """Refuse a report built for READING rather than for MEASUREMENT.

    pdfdrill builds each report twice: a `measure` build with the
    legend off and no ink adopted, and a `reading` build carrying the
    residual bullets and legend for publication. The measurement
    belongs against the FIRST. Measuring the second pairs perfectly,
    passes every structural check, and is then refused downstream --
    which is exactly what happened twice on 1510.06699 and once on
    2103.01507, the second time five minutes into a three-hour run.

    The distinction is not visible in the pdf and it is not visible in
    the row counts. It is recorded in `report.build.json`, which the
    producer writes and nothing here was reading. A guard that costs
    one file read removes a class of error that has already cost a
    three-hour run and two round trips, and it removes it from EITHER
    side making the mistake -- the producer pointing at the wrong
    file, or this side being handed it.

    Absent or unreadable build stamp: ACCEPTED, with a warning. Most
    of the corpus predates the stamp and refusing on its absence would
    stop every older document for a property that was never recorded.
    """
    bj = pdf.parent / "report.build.json"
    if not bj.is_file():
        print(f"{name}: no report.build.json -- phase unknown, "
              f"measuring anyway", flush=True)
        return
    try:
        import json
        meta = json.loads(bj.read_text(errors="replace"))
    except Exception as e:
        print(f"{name}: report.build.json unreadable ({e}) -- phase "
              f"unknown, measuring anyway", flush=True)
        return
    phase = meta.get("phase")
    if phase == "reading" or meta.get("legend") or meta.get("ink_adopted"):
        raise SystemExit(
            f"{name}: this is a READING build "
            f"(phase={phase!r}, legend={meta.get('legend')!r}, "
            f"ink_adopted={meta.get('ink_adopted')!r}). The residual "
            f"belongs against a MEASURE build -- legend off, no ink "
            f"adopted -- or the measurement includes the bullets and "
            f"legend it is supposed to produce. Rebuild with "
            f"--no-legend and measure that.")


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
    check_phase(name, pdf)
    want = ARGS.columns or target_columns(name)
    if want is None:
        zero_rows.append(
            (name, "report.tex has no header carrying both Rendered "
                   "and Scan image -- the equations table has no scan "
                   "column, so there is nothing in it to compare"))
        print(f"{name}: NO SCAN COLUMN in report.tex", flush=True)
        continue
    # THE PROBE IS CACHED (239). It re-renders every page of every
    # document at 150 dpi to count lattice columns, and its answer
    # depends on nothing but the pdf and the wanted column count -- so
    # a re-run repeated 5,153 page renders to reach the same numbers.
    # That is most of the wall clock of an eleven-document run and it
    # was paid twice today, because a restart looked cheap when the
    # 300/600 dpi renders were cached and this was not.
    #
    # Keyed by the pdf's mtime and size, so a rebuilt report
    # invalidates it exactly as it invalidates the render cache.
    _pst = pdf.stat()
    _pk = d / f"probe-{want}-{int(_pst.st_mtime)}-{_pst.st_size}.txt"
    try:
        if _pk.is_file():
            _v = _pk.read_text().split()
            disp = [int(x) for x in _v[1:]]
            census = {}
            print(f"{name}: probe from cache, {len(disp)} display pages",
                  flush=True)
        else:
            disp, census = probe(pdf, npages(pdf), want)
            _pk.write_text(" ".join(["ok"] + [str(x) for x in disp]))
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
empty_rows = []
equal_len = {}
footer_rows = 0
id_mismatch = []
for name in DIRS:
    d = S / name
    # BOTH scale channels are carried now (239). `compare` measures
    # two and this file used to keep one:
    #   A_eq_B    the same page at 300 and 600 dpi gives the same
    #             five-tuple. This is the input `flag_of` reads as
    #             `scale_stable`, and it is what separates S from W.
    #   B_stable  B against its own half-scale resample. Measured by
    #             `compare` on every row and, until now, discarded.
    # A legend naming S while the file carries neither column is a
    # claim the output cannot support; carrying the one the flag
    # actually uses is what makes S auditable.
    # B_stable is APPENDED, not inserted. 239 added it and put it
    # after A_eq_B, which shifts every column a positional consumer
    # reads -- and pdfdrill parses this file positionally, by the
    # column list it quoted back. Inserting a column mid-row is the
    # same silent break as dropping one; appending costs nothing and
    # leaves every existing offset where it was. Same rule as
    # `compare`'s own `overrun` and `empty` columns.
    hdr = ("report_page\tline\tdis\tA_eq_B\tL_comp\tL_holes"
           "\tL_stk\tL_cen\tL_off\tR_comp\tR_holes\tR_stk\tR_cen"
           "\tR_off\tB_stable")
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
            rows.append("\t".join(map(str, [p, ln, dis, c[13]]
                                         + L + R + [c[14]])))
            recs.append((p, dis, abs(L[0] - R[0]), c[13] == "yes",
                         not any(L) and not any(R)))
    # P19: identifiers come from the report's own tex, in table order.
    # A count mismatch means the row<->equation correspondence broke;
    # ids are then withheld ("?") and the document is named in the
    # summary -- a wrong identifier is worse than none.
    # DROP THE CONTINUATION FOOTERS BEFORE THE ZIP (238). A longtable
    # emits one at every page break; it has no ink in either compared
    # cell and it is NOT an equation, so leaving it in the sequence
    # shifts every row after it onto the following identifier.
    #
    # 583f3ae kept these rows and skipped them AFTER the zip, on the
    # reasoning that removing a row disturbs positional pairing. That
    # was exactly backwards: keeping a NON-equation row is what
    # disturbs it. The 214 run over eleven rebuilt reports measured
    # rows minus equations EQUAL TO THE DISPLAY PAGE COUNT in all
    # eleven -- 230/230, 32/32, 276/276, 163/163, 228/228, 2/2, 49/49,
    # 2/2, 50/50, 10/10, 190/190 -- which is one footer per page and
    # nothing else.
    #
    # The concern that produced the wrong fix is real and is handled
    # by POSITION rather than by keeping the row: an equation whose
    # render AND scan are both missing produces an identical all-zero
    # row and DOES own an identifier. A continuation footer is always
    # LAST ON ITS PAGE; such an equation generally is not. Only the
    # last-on-page ones are dropped, and any surviving all-zero row
    # keeps its identifier and is flagged `absent`.
    last_on_page = {}
    for i, r in enumerate(recs):
        last_on_page[r[0]] = i
    footers = {i for pg, i in last_on_page.items() if recs[i][4]}
    footer_rows += len(footers)
    recs = [r for i, r in enumerate(recs) if i not in footers]
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
    if len(idents) == len(recs) and contiguous:
        dem = demoted_idents(name)
        # POST-CONDITION (238): after the footers are gone the two
        # sequences must be the SAME LENGTH, not merely compatible.
        # `len(idents) >= len(recs)` admitted a document with more
        # equations than rows, which is the same mis-pairing in the
        # other direction.
        equal_len[name] = (len(recs), len(idents))
        for (ident, srcpage), (pg, dis, cd, stable, empty) in zip(
                idents, recs):
            if empty:
                empty_rows.append(name)
            if ident in dem:
                demoted_rows.append(name)
                continue
            run_rows.append((name, ident, srcpage, dis, cd,
                             "yes" if stable else "no",
                             flag_of(dis, cd, stable, empty=empty)))
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
    # THE THIRD FACE of the empty-row defect: a positional field that
    # outlives the document it indexes. `report_page` and `line` are
    # indices into a specific BUILD of report.pdf; rebuild the pdf and
    # they stay in range, stay plausible, and quietly point at the
    # wrong rows -- observed as ten displacements in a published
    # 0902.0431, one per page-break, after the legend row was added.
    # Nothing in the file can reveal that, so the build is stamped
    # beside it. A sidecar rather than a header line, because the tsv
    # has consumers that would have to change to skip a comment.
    st = pdf.stat()
    (LIB / name / "report.compare.source").write_text(
        f"path\t{pdf}\nmtime\t{int(st.st_mtime)}\n"
        f"size\t{st.st_size}\nrows\t{len(rows)}\n")
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
    "\n".join(["bibkey\tid\tpage\tdistance\tcomp_delta\t"
               "scale_stable\tflag"] +
              ["\t".join(map(str, r)) for r in run_rows]) + "\n")
_by = {}
for r in run_rows:
    _by[r[6]] = _by.get(r[6], 0) + 1
print(f"{len(run_rows)} rows -> {run_file}", flush=True)
# 238's post-condition, ASSERTED rather than hoped. Printed for every
# document and non-zero exit if any fails, because a silent inequality
# is the mis-pairing this whole change exists to remove.
print(f"\n  ROWS == IDENTIFIERS, after dropping {footer_rows} "
      f"continuation footers:", flush=True)
_bad = []
for _n in sorted(equal_len):
    _r, _i = equal_len[_n]
    _ok = _r == _i
    if not _ok:
        _bad.append(_n)
    print(f"    {'OK ' if _ok else 'FAIL'}  rows {_r:6d}  identifiers "
          f"{_i:6d}  {_n[:52]}", flush=True)
if _bad:
    print(f"  {len(_bad)} document(s) FAILED the equality; their rows "
          f"are excluded and the findings file is incomplete",
          flush=True)
if empty_rows:
    import collections as _c
    by = _c.Counter(empty_rows)
    print(f"  excluded {len(empty_rows)} rows with NO INK in either "
          f"compared cell across {len(by)} documents; worst: "
          f"{', '.join(f'{k} {v}' for k, v in by.most_common(3))}",
          flush=True)
    print(f"    These score distance 0 and would have counted as CLEAN. "
          f"On 1605.05775 they are a longtable page-break continuation "
          f"footer -- 49 px at 300 dpi, above the 40 px sliver floor -- "
          f"one per page, never on the last page.", flush=True)
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
