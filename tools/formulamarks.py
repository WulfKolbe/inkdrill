"""formulamarks.py -- formula-evidence MARKS for pdfdrill, as JSON on stdout.

The integration entry point for the marking policy closed in out/658.
pdfdrill consumes inkdrill only through subprocesses and tools called by
path (`regionink.reportpages_json` is the precedent), so this follows
that convention: one JSON document on stdout, progress on stderr, a
refusal NAMED in the JSON rather than guessed around, and nothing
written into the library.

    python3 tools/formulamarks.py run   <bibkey> --work DIR [--jobs N]
    python3 tools/formulamarks.py marks <bibkey> --work DIR

`run` measures -- `formulafind` on LOSSLESS crops cut from
`inspect/pages`, refit, the document scale voted on a sample of rows --
and then emits. `marks` re-emits from a finished run. Measuring is
minutes per book, so it is a step a caller schedules, not a lookup.

WHAT A ROW SAYS

  mark         draw the rectangle, or not: out/658's four clauses.
               `why_no_mark` names the clause that suppressed it.
  rect         [x0, y0, x1, y1] in MathPix page pixels RELATIVE TO THE
               HOST LINE REGION's top-left corner, or null when `mark` is
               false. pdfdrill's crop of a line is that region resized to
               exactly its MathPix pixel size, so this is a pixel of the
               full-size crop. For a scaled copy use `rect_frac`.
  rect_frac    the same rectangle as fractions of the region's width and
               height -- independent of any resize.
  host_page, region
               the line the rectangle was measured on, by pdfdrill's own
               host-line rule (`formulafind.first_occurrence_lines`). A
               consumer MUST compare it with its own host line and draw
               nothing on a mismatch: a rectangle is meaningless on
               another line.
  flags        `formularesidual`'s classes. LOW_CONFIDENCE is the
               producer's own opinion and the residual report's
               business; the RED classes are evidence-table detail for
               someone chasing one row (out/658).

WHAT IT REFUSES

  the whole document, when `lines.json` changed since `run` -- every
  host region may have moved (digest recorded then, compared now; a mark
  set must name the build it describes, HANDOVER, Coordination);
  A ROW, not the document, when its reading changed since `run`: it
  moves to `not_measured` as "reading changed", and every unchanged row
  keeps its mark. pdfdrill republishes `evidence-formula.tex` -- to
  insert these marks, to render rows it once could not -- and a
  document-wide digest over the rows would refuse every mark for one
  corrected row. Each emitted row carries the `math` it was measured
  on, so a consumer can hold its own row to the same test;
  the whole document, when the run is incomplete or no row could vote a
  scale; a row, with its reason in `not_measured`, when it could not be
  measured. No row is ever given a default.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pathlib
import re
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from inkdrill import version                               # noqa: E402
from tools import formularesidual as fr                    # noqa: E402
from tools.formulafind import frame_rect, rows             # noqa: E402

FINDER = ROOT / "tools" / "formulafind.py"
#: The configuration out/655 and out/658 validated the policy on:
#: lossless crops, per-row refit, formulas rendered at 600 dpi.
FIND_ARGS = ["--crops", "fullres", "--refit", "--dpi", "600", "--host", "first"]
#: Rows the document-scale vote is taken over, spread evenly over the
#: document. The vote is a median of rows with >= 6 gaps, so a few
#: hundred rows pin it; 0902.0431 voted 0.665 on all 3,163.
VOTE_ROWS = 400
#: formularesidual's own default: below it a position is AMBIGUOUS.
MIN_MARGIN = 0.10


def _log(msg):
    print(msg, file=sys.stderr, flush=True)


def _sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inputs(doc: pathlib.Path, bib: str) -> dict:
    """What a mark set DEPENDS ON -- not the bytes of the file it is
    published in. pdfdrill rewrites `evidence-formula.tex` every time it
    republishes, including to insert these very marks, so hashing its
    bytes would make every mark set refuse itself. A mark depends on
    which rows exist with which maths, and on the lines they were
    measured on; a changed crop or confidence cell moves neither."""
    ev = [(r["id"], r["math"]) for r in rows(doc / "evidence-formula.tex")]
    return {"evidence rows (id, math)":
                hashlib.sha256(json.dumps(ev).encode()).hexdigest(),
            f"{bib}.lines.json": _sha(doc / f"{bib}.lines.json")}


def _refuse(bib, why, **extra):
    print(json.dumps(dict(bibkey=bib, refused=why, **extra)))
    return 2


def run(library, bib, work, jobs):
    doc = library / bib
    work.mkdir(parents=True, exist_ok=True)
    for f in list(work.glob("shard*")) + [work / "meta.json"]:
        f.unlink(missing_ok=True)       # an earlier run's shard must not merge
    inputs = _inputs(doc, bib)
    ev = [r for r in rows(doc / "evidence-formula.tex") if r["math"] is not None]
    if not ev:
        return _refuse(bib, "no rendered rows in evidence-formula.tex")
    sample = ev[::max(1, len(ev) // VOTE_ROWS)]
    base = [sys.executable, str(FINDER), "--library", str(library),
            "--bibkey", bib, *FIND_ARGS]
    t0 = time.time()
    _log(f"{bib}: voting the document scale on {len(sample)} of {len(ev)} rows")
    vote = subprocess.run(base + ["--ids", ",".join(r["id"] for r in sample)],
                          capture_output=True, text=True, errors="replace")
    (work / "vote.log").write_text(vote.stdout + vote.stderr)
    # A CRASH IS NOT A VERDICT. The first corpus run reported mielke as
    # "no row could vote a scale" when formulafind had died on a byte
    # pdflatex echoed back -- a refusal naming the wrong cause.
    if vote.returncode != 0:
        return _refuse(bib, f"the scale vote crashed (rc={vote.returncode}); "
                            f"see vote.log", work=str(work))
    m = re.search(r"^document scale: ([\d.]+)", vote.stdout, re.M)
    if not m:
        return _refuse(bib, "no row could vote a document scale; see vote.log",
                       work=str(work))
    scale = float(m.group(1))
    _log(f"  scale {scale} ({time.time() - t0:.0f}s); measuring in {jobs} shards")
    procs = []
    for i in range(jobs):
        log = open(work / f"shard{i}.log", "w")
        procs.append((subprocess.Popen(
            base + ["--scale", str(scale), "--shard", f"{i}/{jobs}",
                    "--json", str(work / f"shard{i}.json")],
            stdout=log, stderr=subprocess.STDOUT), log))
    failed = []
    for i, (p, log) in enumerate(procs):
        if p.wait() != 0:
            failed.append(i)
        log.close()
    if failed:
        return _refuse(bib, f"shards {failed} failed; see their logs",
                       work=str(work))
    (work / "meta.json").write_text(json.dumps(dict(
        bibkey=bib, measured_against=inputs, scale=scale, jobs=jobs,
        find_args=FIND_ARGS, inkdrill=version.resolve(),
        seconds=round(time.time() - t0))))
    _log(f"  measured in {time.time() - t0:.0f}s")
    return marks(library, bib, work)


def why_no_mark(r):
    """The clause of out/658's policy that suppressed this row's mark, or
    None. `formularesidual.classify` holds the policy; this names it, and
    `marks` refuses if the two ever disagree."""
    if not r["line_like"]:
        return (f"host region is not a line (taller than {fr.NON_LINE}x "
                f"the median line)")
    if r["gaps"] <= 1:
        return "too short to carry a position (gaps <= 1)"
    if r["margin"] < fr.MARK_MARGIN:
        return (f"position not unique (margin {r['margin']:.3f} < "
                f"{fr.MARK_MARGIN})")
    if r["gaps"] <= fr.MARK_GAPS and r["edge_cuts"] >= fr.MARK_CUTS:
        return (f"short expression cut by a rectangle edge (gaps "
                f"{r['gaps']} <= {fr.MARK_GAPS}, edge cuts {r['edge_cuts']})")
    return None


def to_region(r):
    """formulafind's rect, in pixels of ITS crop, -> MathPix pixels
    relative to the host region's top-left, and fractions of the region.
    Returns (px, frac, y_from).

    x is the measurement. y is the ink's extent inside that x range, and
    a rectangle over no ink has none (formulafind reports None): then y
    spans the whole line, and `y_from` says "line" rather than "ink" so
    the fallback is never mistaken for a measured extent."""
    reg, frame = r["region"], r["frame"]
    cx, cy, _, ch = frame_rect(reg, frame)
    sx, sy, ox, oy = frame
    x0, y0, x1, y1 = r["rect"]
    y_from = "ink"
    if y0 is None or y1 is None:
        y0, y1, y_from = 0, ch, "line"
    px = [(cx + x0 - ox) / sx - reg["top_left_x"],
          (cy + y0 - oy) / sy - reg["top_left_y"],
          (cx + x1 - ox) / sx - reg["top_left_x"],
          (cy + y1 - oy) / sy - reg["top_left_y"]]
    frac = [px[0] / reg["width"], px[1] / reg["height"],
            px[2] / reg["width"], px[3] / reg["height"]]
    return [round(v, 1) for v in px], [round(v, 4) for v in frac], y_from


def marks(library, bib, work):
    doc = library / bib
    meta_f = work / "meta.json"
    if not meta_f.exists():
        return _refuse(bib, f"no finished run in {work}; `run` first")
    meta = json.loads(meta_f.read_text())
    now, was = _inputs(doc, bib), meta["measured_against"]
    lines_key = f"{bib}.lines.json"
    if now[lines_key] != was.get(lines_key):
        return _refuse(bib, f"stale: {lines_key} changed since the run; every "
                            f"host region may have moved", measured_against=was)
    shards = sorted(work.glob("shard*.json"))
    if len(shards) != meta["jobs"]:
        return _refuse(bib, f"incomplete run: {len(shards)} of {meta['jobs']} "
                            f"shards")
    res = []
    for f in shards:
        res += json.loads(f.read_text())
    cal, ref = fr.calibrate(res, MIN_MARGIN)
    if cal is None:
        return _refuse(bib, f"only {len(ref)} confidently placed rows; the "
                            f"flag thresholds cannot be calibrated")
    fr.classify(res, cal, MIN_MARGIN)

    logged = {}
    for f in work.glob("shard*.log"):
        for line in f.read_text(errors="replace").splitlines():
            m = re.match(r"(FO\d+)\s+(NO LINE MATCH|RENDER FAILED)", line)
            if m:
                logged[m.group(1)] = m.group(2).lower()
    measured = {r["id"]: r for r in res}
    out, not_measured = [], {}
    changed = 0
    for e in rows(doc / "evidence-formula.tex"):
        r = measured.get(e["id"])
        if r is not None and e["math"] != r["math"]:
            changed += 1
            not_measured[e["id"]] = ("reading changed since the run; re-run "
                                     "to mark it")
            continue
        if r is None:
            not_measured[e["id"]] = (
                "not rendered by the producer (no \\FitMath)"
                if e["math"] is None else
                logged.get(e["id"].split("_")[-1],
                           "not placed (at every scale of the refit band "
                           "the rendering is wider than its host line, or "
                           "under 4 px)"))
            continue
        why = why_no_mark(r)
        if (why is None) != r["mark"]:
            raise SystemExit(f"POLICY DRIFT on {r['id']}: formularesidual "
                             f"says mark={r['mark']}, why_no_mark={why!r}")
        px, frac, y_from = to_region(r)
        out.append(dict(
            id=r["id"], page=r["page"], host_page=r["host_page"],
            math=r["math"],
            region=r["region"], mark=r["mark"], why_no_mark=why,
            rect=px if r["mark"] else None,
            rect_frac=frac if r["mark"] else None,
            y_from=y_from if r["mark"] else None,
            flags=r["flags"], conf=r["conf"],
            margin=r["margin"], gaps=r["gaps"], edge_cuts=r["edge_cuts"],
            score=r["score"]))
    flags = collections.Counter(f for r in out for f in (r["flags"] or ["SILENT"]))
    counts = dict(
        evidence_rows=len(out) + len(not_measured), measured=len(out),
        reading_changed=changed,
        marked=sum(1 for r in out if r["mark"]),
        not_measured=dict(collections.Counter(not_measured.values())),
        suppressed=dict(collections.Counter(
            r["why_no_mark"].split(" (")[0] for r in out if not r["mark"])),
        flags=dict(sorted(flags.items())))
    print(json.dumps(dict(
        bibkey=bib, refused=None, tool="inkdrill/tools/formulamarks.py",
        inkdrill=version.resolve(), measured_with=meta["inkdrill"],
        measured_against=meta["measured_against"], scale=meta["scale"],
        policy=dict(closed="out/658", MARK_MARGIN=fr.MARK_MARGIN,
                    MARK_GAPS=fr.MARK_GAPS, MARK_CUTS=fr.MARK_CUTS,
                    NON_LINE=fr.NON_LINE, LOW_CONFIDENCE=fr.LOW_CONFIDENCE),
        calibration={k: cal[k] for k in ("n_ref", "blob_diff_max",
                                         "edge_cut_max", "score_min")},
        rect_frame="MathPix page px relative to the host region's top-left",
        counts=counts, rows=out, not_measured=not_measured)))
    _log(f"{bib}: {counts['marked']} of {counts['evidence_rows']} rows marked; "
         f"{len(not_measured)} not measured")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "marks"):
        a = sub.add_parser(name)
        a.add_argument("bibkey")
        a.add_argument("--library", type=pathlib.Path,
                       default=pathlib.Path.home() / "pdfdrill-library")
        a.add_argument("--work", type=pathlib.Path, required=True)
        if name == "run":
            a.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args()
    if args.cmd == "run":
        return run(args.library, args.bibkey, args.work, args.jobs)
    return marks(args.library, args.bibkey, args.work)


if __name__ == "__main__":
    raise SystemExit(main())
