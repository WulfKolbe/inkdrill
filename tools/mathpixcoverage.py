"""Check MathPix lines.json geometry against real ink (coverage.check),
documents processed oldest-lines.json-first.

Usage: python3 tools/mathpixcoverage.py [worker] [nworkers] [library]
  Shard `worker` of `nworkers` (default 0 of 1) over <library>/*/*.lines.json;
  run N copies in parallel with worker=0..N-1. Resumable: a document whose
  .coverage.tsv is newer than its lines.json is skipped.

Per page: components (>= 4 px, speck floor) classified against the
document's MathPix regions scaled from MathPix raster coordinates
(page_width/page_height) into our 200 dpi render. Output one TSV per
document: page, components, regions, and the five coverage classes --
the residual (MISSED ink) is the product.
"""
import ast, json, pathlib, subprocess, sys
# library filenames can carry lone surrogates (undecodable bytes); an
# encode error inside the FAILURE print killed all six workers of the
# first full run -- make stdout unable to raise
sys.stdout.reconfigure(errors="backslashreplace")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from inkdrill.aggregate import moments_per_component
from inkdrill.coverage import Box, CoverageClass, Region, check
from inkdrill.pnmio import read_pnm_stream
from inkdrill.pngio import auto_mask
from inkdrill.sweep import Capture, sweep

import argparse
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import corpusgate
import inkfit

_ap = argparse.ArgumentParser(
    prog="tools/mathpixcoverage.py",
    description=__doc__.strip().splitlines()[0])
_ap.add_argument("worker", nargs="?", type=int, default=0)
_ap.add_argument("workers", nargs="?", type=int, default=1)
_ap.add_argument("library", nargs="?", default="~/pdfdrill-library")
_ap.add_argument("--only", default=None,
                 help="comma-separated document names to measure "
                      "(implies --force; --limit still applies)")
_ap.add_argument("--math-pages", type=int, default=None,
                 help="PROBE MODE: measure only the first N pages that "
                      "carry a math line, and write NO coverage.tsv "
                      "(a partial measurement must not overwrite a "
                      "whole one). Makes the Q1 overlap comparable "
                      "across documents at a stated page budget.")
_ap.add_argument("--quarantine", type=float, default=None,
                 help="Q3: drop WHOLE any document whose max math "
                      "overlap exceeds F, appending it to "
                      "results/oversized.txt. No default: the measured "
                      "distribution (tools/inkfit.py, docs/state.md) "
                      "supports no cut, so a threshold is a caller's "
                      "decision, never a silent one.")
_ap.add_argument("--force", action="store_true",
                 help="re-measure documents whose coverage.tsv is current")
corpusgate.add_arguments(_ap)
ARGS = _ap.parse_args()
ONLY = set(ARGS.only.split(",")) if ARGS.only else None
W, K = ARGS.worker, ARGS.workers
LIB = pathlib.Path(ARGS.library).expanduser()
RESULTS = pathlib.Path(__file__).resolve().parent.parent / "results"


def _pages_of(lj):
    """Page count without parsing the (often multi-MB) lines.json."""
    import re as _re
    import subprocess as _sp
    pdf = lj.parent / (lj.name[:-len(".lines.json")] + ".pdf")
    if not pdf.exists():
        pdf = next((q for q in lj.parent.glob("*.pdf")
                    if q.name != "report.pdf"), None)
    if pdf is None:
        return 0
    out = _sp.run(["pdfinfo", str(pdf)], capture_output=True,
                  text=True).stdout
    m = _re.search(r"^Pages:\s+(\d+)", out, _re.M)
    return int(m.group(1)) if m else 0


# --limit applies to the WHOLE selection; the shard is taken after,
# so `--limit 12` means twelve documents across all workers.
_all = sorted(LIB.glob("*/*.lines.json"), key=lambda f: f.stat().st_mtime)
if ONLY is not None:
    _all = [f for f in _all
            if f.name[:-len(".lines.json")] in ONLY or f.parent.name in ONLY]
    missing = ONLY - {f.name[:-len(".lines.json")] for f in _all} \
                   - {f.parent.name for f in _all}
    if missing:
        raise SystemExit(f"--only: no lines.json for {sorted(missing)}")
docs = corpusgate.gate(f"mathpixcoverage[{W}/{K}]", _all,
                       ARGS.limit, ARGS.yes,
                       count_pages=_pages_of)[W::K]

MEASURED, QUARANTINED = [], []
REASONS = {}
OVERLAP_ROWS = []          # Q1's numbers, for the run file below


def _reason(kind):
    REASONS[kind] = REASONS.get(kind, 0) + 1


for lj in docs:
    done = lj.parent / (lj.name[:-len(".lines.json")] + ".coverage.tsv")
    if (done.exists() and done.stat().st_mtime > lj.stat().st_mtime
            and not (ARGS.force or ONLY)):
        continue
    try:
        d = lj.parent; name = lj.name[:-len(".lines.json")]
        pdf = d / (name + ".pdf")
        if not pdf.exists():
            pdf = next((p for p in d.glob("*.pdf")
                        if p.name != "report.pdf"), None)
        if pdf is None:
            print(f"{name}: no source pdf, skipped", flush=True)
            _reason("no-source-pdf"); continue
        data = json.loads(lj.read_text())
        pages = {p["page"]: p for p in data["pages"]}
        npg = max(pages)
        out = ["page\tcomponents\tregions\tinside\tmissed\tstraddle"
               "\toverlapping\tempty_regions\tmissed_px"]
        tot = {k: 0 for k in CoverageClass}; totc = totr = 0
        max_frac, max_where, n_math = 0.0, None, 0
        # PROBE MODE: the first N math-bearing pages, so every
        # document is compared at the same page budget.
        wanted = None
        if ARGS.math_pages:
            wanted = [pg for pg in sorted(pages)
                      if any(l.get("type") == "math"
                             for l in pages[pg].get("lines", []))
                      ][:ARGS.math_pages]
            if not wanted:
                print(f"{name}: PROBE no math-bearing page", flush=True)
                OVERLAP_ROWS.append((name, "", 0, "", "", "no-math-page"))
                _reason("probe-no-math-page"); continue
            npg = max(wanted)
        for lo in range(1, npg + 1, 10):
            hi = min(lo + 9, npg)
            if wanted is not None and not any(lo <= w <= hi
                                              for w in wanted):
                continue
            gs = subprocess.run(
                ["gs","-q","-dNOPAUSE","-dBATCH","-sDEVICE=pgmraw","-r200",
                 f"-dFirstPage={lo}",f"-dLastPage={hi}",
                 "-sOutputFile=%stdout",str(pdf)],
                capture_output=True, check=True).stdout
            for i, img in enumerate(read_pnm_stream(gs, dpi=(200.0,200.0))):
                pg = lo + i
                meta = pages.get(pg)
                if meta is None: continue
                if wanted is not None and pg not in wanted: continue
                mask,_ = auto_mask(img.gray, img.width, img.height, 200)
                res = sweep(mask, axis="row", conn=8, capture=Capture.GRAPH)
                moms = moments_per_component(res)
                boxes = [Box(c.root, moms[c.root].x0, moms[c.root].y0,
                             moms[c.root].x1, moms[c.root].y1,
                             moms[c.root].area)
                         for c in res.components]
                sx = mask.width / meta["page_width"]
                sy = mask.height / meta["page_height"]
                regs = []
                math_regions = []          # Q1: (key, bbox) per math line
                for j, ln in enumerate(meta.get("lines", [])):
                    r = ln.get("region")
                    if isinstance(r, str): r = ast.literal_eval(r)
                    if not r: continue
                    bx = (r["top_left_x"] * sx, r["top_left_y"] * sy,
                          (r["top_left_x"] + r["width"]) * sx,
                          (r["top_left_y"] + r["height"]) * sy)
                    regs.append(Region(j, bx[0], bx[1], bx[2], bx[3],
                                       ln.get("type", "")))
                    if ln.get("type") == "math":
                        math_regions.append(
                            ((ln.get("id", f"line{j}"), pg), bx))
                # Q1: the overlap check RIDES ALONG -- it reads the
                # components and regions this page already produced and
                # changes no measurement above it.
                for (ident, page_no), frac in inkfit.overlaps(
                        math_regions, boxes):
                    n_math += 1
                    if frac > max_frac:
                        max_frac, max_where = frac, (ident, page_no)
                rep = check(boxes, regs, min_pixels=4)
                missed = rep.members(CoverageClass.MISSED)
                mpx = sum(moms[b].area for b in missed if b in moms)
                row = [pg, rep.box_count, rep.region_count] + \
                      [rep.count(k) for k in CoverageClass] + [mpx]
                out.append("\t".join(map(str, row)))
                for k in CoverageClass: tot[k] += rep.count(k)
                totc += rep.box_count; totr += rep.region_count
        # Q3: the drop is decided BEFORE the measurement is written,
        # and it is whole -- a stale coverage.tsv from an earlier run
        # is removed too, or the corpus would still contain the data
        # this document was dropped for.
        if ARGS.quarantine is not None and max_frac > ARGS.quarantine:
            tsv = d / (name + ".coverage.tsv")
            removed = tsv.exists() and wanted is None
            if removed:
                tsv.unlink()
            ident, page_no = (max_where or ("?", "?"))
            RESULTS.mkdir(exist_ok=True)
            ox = RESULTS / "oversized.txt"
            if not ox.exists():
                ox.write_text("document\tidentifier\tpage\tfraction\n")
            with ox.open("a") as fh:
                fh.write(f"{name}\t{ident}\t{page_no}\t{max_frac:.4f}\n")
            QUARANTINED.append(name)
            _reason("oversized")
            print(f"{name}: QUARANTINED max overlap {max_frac:.3f} > "
                  f"{ARGS.quarantine} -- dropped whole"
                  f"{', removed its earlier coverage.tsv' if removed else ''}"
                  f", listed in {ox}", flush=True)
            continue
        if wanted is None:
            (d / (name + ".coverage.tsv")).write_text("\n".join(out) + "\n")
            MEASURED.append(name)      # probe mode writes nothing, so
        else:                          # it is NOT a measured document
            _reason("probe-only")
        cb = sum(v for k, v in tot.items() if k != CoverageClass.EMPTY_REGION)
        where = (f", worst {max_where[0][:12]} p{max_where[1]}"
                 if max_where else "")
        scope = (f" [PROBE: first {len(wanted)} math-bearing pages, "
                 f"no coverage.tsv written]" if wanted is not None else "")
        print(f"{name}: MATH OVERLAP max {max_frac:.3f} over {n_math} "
              f"math region(s){where}{scope}", flush=True)
        OVERLAP_ROWS.append((
            name, f"{max_frac:.4f}" if n_math else "", n_math,
            (max_where or ("", ""))[0], (max_where or ("", ""))[1],
            f"probe:{len(wanted)}-math-pages" if wanted is not None
            else "full"))
        if wanted is not None:
            continue
        print(f"{name}: {npg} pages, comps {totc}, regions {totr}, "
              f"missed {tot[CoverageClass.MISSED]} "
              f"({100*tot[CoverageClass.MISSED]/max(1,cb):.1f}% of ink), "
              f"empty regions {tot[CoverageClass.EMPTY_REGION]}", flush=True)
    except Exception as e:
        print(f"{lj.parent.name}: FAILED {type(e).__name__}: {e}", flush=True)
        _reason(f"failed:{type(e).__name__}")
def write_overlap_run():
    """Q1's per-document numbers as a FILE, not prose (P19's rule
    applied to the overlap probe): the distribution that decides a
    quarantine threshold has to be re-readable, sortable, and
    attributable to a run. `scope` records the page budget, because
    a max over 20 math-bearing pages and a max over a whole document
    are different measurements."""
    if not OVERLAP_ROWS:
        return
    RESULTS.mkdir(exist_ok=True)
    import datetime
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    f = RESULTS / f"overlap-{stamp}-w{W}.tsv"
    f.write_text("\n".join(
        ["document\tmax_overlap\tmath_regions\tworst_id\tworst_page\tscope"]
        + ["\t".join(map(str, r)) for r in OVERLAP_ROWS]) + "\n")
    print(f"WORKER {W}: overlap of {len(OVERLAP_ROWS)} document(s) "
          f"-> {f}", flush=True)


def summary():
    """Q4: measured, quarantined and the reason breakdown print
    TOGETHER, from one call site. There is no path that prints a
    count of measured documents without the count that was dropped
    beside it -- an aggregate whose exclusions are invisible is the
    defect this exists to prevent."""
    reasons = ", ".join(f"{k} {v}" for k, v in sorted(REASONS.items())) \
        or "none"
    print(f"WORKER {W}: measured {len(MEASURED)}, "
          f"quarantined {len(QUARANTINED)}, "
          f"not measured for other reasons "
          f"{sum(v for k, v in REASONS.items() if k != 'oversized')}",
          flush=True)
    print(f"WORKER {W}: reasons -- {reasons}", flush=True)
    if ARGS.quarantine is None:
        print(f"WORKER {W}: quarantine OFF (no --quarantine F given): "
              f"nothing was dropped for overlap", flush=True)


write_overlap_run()
summary()
print(f"WORKER {W} DONE", flush=True)
