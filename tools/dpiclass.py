"""496 -- does the resolution caveat reach the corpus?

495 measured hole-count instability on RENDERED GLYPHS at 40/80/160 px
and found 12% of glyphs change hole count with size. That is a
statement about single glyphs at sizes chosen to span a range. It is
not the working condition: the corpus comparisons run at 300 dpi, and
what they compare is a table CELL -- tens of glyphs at once -- against
another cell.

This harness answers the question in the working condition. For each
compared row it computes the five-tuple of BOTH columns at BOTH
resolutions the compare harness already renders, so the per-channel
disagreement can be separated (holes from components from the
geometric channels) and the FLAG CLASS can be recomputed at 600 dpi
and compared against the one the corpus recorded at 300.

`A=B` in the corpus TSV already carries 300-vs-600 equality, but it is
a conjunction over ten numbers and says nothing about which channel
moved -- and it is an INPUT to the class rather than a measure of the
class's stability. Both gaps are why this is a re-measurement and not
a query.

POPULATION: documents under the library holding both a report.pdf and
a report.compare.tsv (544 of 2,813 directories) -- i.e. exactly the
documents the corpus figures are computed over. SPLIT RULE: a seeded
shuffle of that list, `--docs` taken from the front, every display
page of each. Both are arguments, and the sample's own A=B rate is
printed against the corpus's so a reader can see whether the draw was
representative.

The row filters are the corpus's, not new ones: row 0 is the header,
a row shorter than 40 px at 300 dpi is a sliver, a page whose lattice
covers less than half its table region is refused, and a lattice with
fewer than two columns is refused. Changing them here would measure a
different population from the one the caveat is about.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import pathlib
import random
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from findings import flag_of                       # one definition (P19)
from inkdrill.__main__ import (_table_cells, _drop_slivers, _cell_crop)
from inkdrill.mathstruct import pair_stats
from inkdrill.pnmio import mask_from_pgm
from pagedetect import npages, probe, target_columns   # one implementation

KEYS = ("components", "holes", "stacked", "centred", "offset")
THRESHOLD = 200
TOL = 4.0


def _lattice(mask):
    """The compare harness's lattice, with its guards. Returns
    (cells, nrows, ncols) or a string naming why the page is refused."""
    dbg = {}
    cells = _table_cells(mask, TOL, debug=dbg)
    if cells is None:
        return "no ink region with >= 2 holes"
    cells = _drop_slivers(cells, mask.height)
    if not cells:
        return "no cell survived the lattice filters"
    nrows = max(r for r, _ in cells) + 1
    ncols = max(c for _, c in cells) + 1
    if ncols < 2:
        return f"lattice has {ncols} column(s)"
    span = dbg.get("span", 0)
    got = sum(cells[(r, 0)][3] - cells[(r, 0)][1]
              for r in range(nrows) if (r, 0) in cells)
    cov = got / span if span else 0.0
    if cov < 0.5:
        return f"row coverage {cov:.3f}"
    return cells, nrows, ncols


def _tuple_of(mask, cells, ncols, r, col):
    pick = (ncols - 2, ncols - 1)
    cell = cells.get((r, pick[col]))
    if cell is None:
        return None
    st = pair_stats(_cell_crop(mask, cell[0], cell[1],
                               cell[2] - 1, cell[3] - 1))
    return tuple(st.get(k, 0) for k in KEYS)


def one_page(pdf: pathlib.Path, page: int, work: pathlib.Path):
    """Every compared row of one page, at both resolutions."""
    out = []
    paths = {}
    for dpi in (300, 600):
        f = work / f"{pdf.parent.name[:40]}_p{page:03d}_r{dpi}.pgm"
        paths[dpi] = f
        if not f.exists():
            subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH",
                            "-sDEVICE=pgmraw", f"-r{dpi}",
                            f"-dFirstPage={page}", f"-dLastPage={page}",
                            f"-sOutputFile={f}", str(pdf)], check=True)
    try:
        lat, masks = {}, {}
        for dpi in (300, 600):
            masks[dpi] = mask_from_pgm(paths[dpi], threshold=THRESHOLD)
            got = _lattice(masks[dpi])
            if isinstance(got, str):
                return [], f"{dpi}: {got}"
            lat[dpi] = got
        n = min(lat[300][1], lat[600][1])
        for r in range(1, n):                     # row 0 is the header
            cells3 = lat[300][0]
            b = cells3.get((r, 0))
            if b is None or (b[3] - b[1]) < 40:   # the sliver floor
                continue
            rec = {}
            ok = True
            for dpi in (300, 600):
                cells, _, ncols = lat[dpi]
                L = _tuple_of(masks[dpi], cells, ncols, r, 0)
                R = _tuple_of(masks[dpi], cells, ncols, r, 1)
                if L is None or R is None:
                    ok = False
                    break
                rec[dpi] = (L, R)
            if ok:
                out.append((page, r, rec[300], rec[600]))
        return out, None
    finally:
        for f in paths.values():
            f.unlink(missing_ok=True)


def _row_line(doc, page, r, t3, t6):
    L3, R3 = t3
    L6, R6 = t6
    return "\t".join([doc, str(page), str(r)]
                     + [str(x) for x in L3] + [str(x) for x in R3]
                     + [str(x) for x in L6] + [str(x) for x in R6])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--library", type=pathlib.Path,
                    default=pathlib.Path.home() / "pdfdrill-library")
    ap.add_argument("--work", type=pathlib.Path,
                    default=pathlib.Path.home() / "inkdrill-work" / "dpi496")
    ap.add_argument("--docs", type=int, default=40)
    ap.add_argument("--seed", type=int, default=496)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("-o", type=pathlib.Path, required=True)
    args = ap.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)

    pool = sorted(d.name for d in args.library.iterdir()
                  if d.is_dir() and (d / "report.pdf").is_file()
                  and (d / "report.compare.tsv").is_file())
    print(f"population {len(pool)} documents (report.pdf AND "
          f"report.compare.tsv)", flush=True)
    rng = random.Random(args.seed)
    picked = pool[:]
    rng.shuffle(picked)
    picked = picked[:args.docs]
    print(f"sample {len(picked)} at seed {args.seed}", flush=True)

    jobs = []
    for name in picked:
        d = args.library / name
        pdf = d / "report.pdf"
        # the probe cache written by reportcompare, if it is there
        cached = sorted(d.glob("probe-*-*.txt"))
        disp = None
        if cached:
            v = cached[-1].read_text().split()
            if v and v[0] == "ok":
                disp = [int(x) for x in v[1:]]
        if disp is None:
            # THE COLUMN COUNT IS PER DOCUMENT. A constant was wrong
            # twice in one day and reported a whole era as "no display
            # pages"; the count comes from the document's own
            # report.tex, through the one implementation.
            want = target_columns(d / "report.tex")
            if want is None:
                print(f"{name}: no scan column in report.tex", flush=True)
                continue
            try:
                disp, _ = probe(pdf, npages(pdf), want)
            except Exception as e:
                print(f"{name}: probe FAILED {e}", flush=True)
                continue
        print(f"{name}: {len(disp)} display pages", flush=True)
        for p in disp:
            jobs.append((name, pdf, p))

    print(f"{len(jobs)} pages", flush=True)
    hdr = ("doc\tpage\trow"
           + "".join(f"\tL3_{k}" for k in KEYS)
           + "".join(f"\tR3_{k}" for k in KEYS)
           + "".join(f"\tL6_{k}" for k in KEYS)
           + "".join(f"\tR6_{k}" for k in KEYS))
    lines = [hdr]
    refused = []

    def run(job):
        name, pdf, p = job
        try:
            rows, why = one_page(pdf, p, args.work)
        except Exception as e:
            return name, p, [], f"{type(e).__name__}: {e}"
        return name, p, rows, why

    done = 0
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        for name, p, rows, why in ex.map(run, jobs):
            done += 1
            if why:
                refused.append((name, p, why))
            for (page, r, t3, t6) in rows:
                lines.append(_row_line(name, page, r, t3, t6))
            if done % 25 == 0:
                print(f"pages {done}/{len(jobs)}  rows {len(lines)-1}",
                      flush=True)
    args.o.write_text("\n".join(lines) + "\n")
    print(f"{len(lines)-1} rows -> {args.o}", flush=True)
    print(f"{len(refused)} pages refused", flush=True)
    for name, p, why in refused[:20]:
        print(f"  {name} p{p}: {why}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
