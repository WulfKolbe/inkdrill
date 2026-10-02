"""formulamarks.py -- formula-evidence MARKS for pdfdrill, as JSON on stdout.

The integration entry point for the marking policy closed in out/658.
pdfdrill consumes inkdrill only through subprocesses and tools called by
path (`regionink.reportpages_json` is the precedent), so this follows
that convention: one JSON document on stdout, progress on stderr, a
refusal NAMED in the JSON rather than guessed around, and nothing
written into the library.

    python3 tools/formulamarks.py run    <bibkey> --work DIR [--jobs N]
    python3 tools/formulamarks.py marks  <bibkey> --work DIR
    python3 tools/formulamarks.py update <bibkey> --work DIR

`run` measures -- `formulafind` on LOSSLESS crops cut from
`inspect/pages`, refit, the document scale voted on a sample of rows --
and then emits. `marks` re-emits from a finished run. Measuring is
minutes per book, so it is a step a caller schedules, not a lookup.

`update` measures ONLY the rows whose reading changed since the run (and
rows the run never placed whose MathPix reading differs from the one
shown), at the run's STORED scale, and emits. It exists because a fresh
`run` re-votes the scale, and on mielke a 0.64 -> 0.65 re-vote flipped 8
marks on rows that had not changed (out/670). Every row `update` did not
measure keeps its record, and the merge calibrates and takes the median
line from the ORIGINAL run only, so an unchanged row's mark and rect
cannot move. The host line of a refined row is found by MathPix's
reading from `*.tiddlers.json` (`formulafind.MATHPIX_FIELD`); its
rendering is still the reading the evidence file shows.

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


def _run_records(work):
    """(original records, update records, ids an update attempted)."""
    res = []
    for f in sorted(work.glob("shard*.json")):
        res += json.loads(f.read_text())
    upd_f, um_f = work / "update.json", work / "update_meta.json"
    upd = json.loads(upd_f.read_text()) if upd_f.exists() else []
    attempted = set(json.loads(um_f.read_text())["ids"]) if um_f.exists() else set()
    return res, upd, attempted


def merge(original, updated, attempted):
    """Original records minus every id an update ATTEMPTED, plus the
    update's records. An attempted row the update could not place keeps
    no stale record: it is reported with the update's own reason."""
    return [r for r in original if r["id"] not in attempted] + list(updated)


def update(library, bib, work):
    from tools.formulafind import first_occurrence_lines, mathpix_readings
    doc = library / bib
    meta_f = work / "meta.json"
    if not meta_f.exists():
        return _refuse(bib, f"no finished run in {work}; `run` first")
    meta = json.loads(meta_f.read_text())
    lines_key = f"{bib}.lines.json"
    if _inputs(doc, bib)[lines_key] != meta["measured_against"].get(lines_key):
        return _refuse(bib, f"stale: {lines_key} changed since the run; `run` "
                            f"again -- every host region may have moved",
                       measured_against=meta["measured_against"])
    if len(list(work.glob("shard*.json"))) != meta["jobs"]:
        return _refuse(bib, "incomplete run; `run` first")
    res, upd, attempted = _run_records(work)
    measured = {r["id"]: r for r in merge(res, upd, attempted)}
    mathpix = mathpix_readings(library, bib)
    first = first_occurrence_lines(library, bib)
    todo = []
    for e in rows(doc / "evidence-formula.tex"):
        if e["math"] is None:
            continue
        hm = mathpix.get(e["id"])
        look = (hm if hm and hm.strip() != e["math"].strip() else e["math"]).strip()
        r = measured.get(e["id"])
        if r is not None:
            if r["math"] != e["math"]:
                todo.append(e["id"])
            else:
                # THE SECOND TRIGGER: the host line moved. A mark is
                # measured on one line and drawn on pdfdrill's crop of
                # that line, so a row whose host changed -- or has none
                # now -- is measured again, whatever its reading says.
                # pdfdrill's rule changed on 2026-09-12 and 515 rows
                # moved with it (out/673).
                hit = first.get(look)
                now = (hit[0], hit[1]) if hit else None
                if now != (r.get("host_page"), r.get("region")):
                    todo.append(e["id"])
        elif e["id"] in attempted:      # noqa: E501 -- see the comment below
            # ATTEMPTED BEFORE AND LEFT NO RECORD -- unplaceable then, or a
            # placeholder then. Its reading may have changed since: johnston
            # FO1528 was `(not rendered)` at one update and MathPix's reading
            # again after pdfdrill withdrew the refinement (out/672). The
            # merge drops its original record, so skipping it here would
            # report the old reason forever.
            todo.append(e["id"])
        elif hm and hm.strip() != e["math"].strip():
            todo.append(e["id"])
    _log(f"{bib}: update -- {len(todo)} rows to measure at the stored scale "
         f"{meta['scale']}")
    if todo:
        new_f = work / "update_new.json"
        new_f.unlink(missing_ok=True)
        cmd = [sys.executable, str(FINDER), "--library", str(library),
               "--bibkey", bib, *FIND_ARGS, "--scale", str(meta["scale"]),
               "--ids", ",".join(todo), "--json", str(new_f)]
        p = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
        with open(work / "update.log", "a") as log:
            log.write(f"\n==== update {time.strftime('%Y-%m-%dT%H:%M:%S')} "
                      f"{len(todo)} rows\n{p.stdout}{p.stderr}")
        if p.returncode != 0:
            return _refuse(bib, f"the update crashed (rc={p.returncode}); see "
                                f"update.log", work=str(work))
        new = json.loads(new_f.read_text()) if new_f.exists() else []
        done = set(todo)
        upd = [r for r in upd if r["id"] not in done] + new
        (work / "update.json").write_text(json.dumps(upd, indent=1))
        (work / "update_meta.json").write_text(json.dumps(dict(
            ids=sorted(attempted | done), scale=meta["scale"],
            inkdrill=version.resolve(),
            last=time.strftime("%Y-%m-%dT%H:%M:%S"))))
        new_f.unlink(missing_ok=True)
    return marks(library, bib, work)


def suppressed(work):
    """id -> the EYE VERDICT that removed this row's mark, from
    `work/suppressed.json`.

    The policy's four clauses (out/658) and its fifth (out/677) are
    measurements; this is the other kind of evidence -- a rectangle
    somebody LOOKED AT and found wrong. gilmore FO2420 scores 0.9338 and
    still boxes `alpha -> Z alpha` for a reading of `\\alpha` (out/679),
    so no threshold reaches it and moving one to fit two rows would be
    tuning. The verdict travels WITH the mark set: each entry names what
    was seen, so a reader can disagree with it.
    """
    f = work / "suppressed.json"
    return json.loads(f.read_text()) if f.exists() else {}


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
    if r["score"] < fr.MARK_SCORE:
        return (f"the fit is not a match (score {r['score']:.3f} < "
                f"{fr.MARK_SCORE})")
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
    original, upd, attempted = _run_records(work)
    # CALIBRATED ON THE ORIGINAL RUN ONLY, and the median line taken from
    # it: both are population statistics, and an update must not move a
    # row it did not measure.
    cal, ref = fr.calibrate(original, MIN_MARGIN)
    if cal is None:
        return _refuse(bib, f"only {len(ref)} confidently placed rows; the "
                            f"flag thresholds cannot be calibrated")
    res = merge(original, upd, attempted)
    fr.classify(res, cal, MIN_MARGIN, line_h=fr.median_line_h(original))

    logged = {}
    for f in list(work.glob("shard*.log")) + [work / "update.log"]:
        if not f.exists():
            continue
        for line in f.read_text(errors="replace").splitlines():
            m = re.match(r"(FO\d+)\s+(NO LINE MATCH|RENDER FAILED)", line)
            if m:
                logged[m.group(1)] = m.group(2).lower()
    measured = {r["id"]: r for r in res}
    eye = suppressed(work)
    out, not_measured = [], {}
    changed = 0
    for e in rows(doc / "evidence-formula.tex"):
        # NOT RENDERED FIRST. A row the producer did not render has no
        # reading to mark, whatever record an earlier run or update left:
        # johnston FO5033's update measured the placeholder text
        # `\emph{(not rendered)}` as a formula (out/672).
        if e["math"] is None:
            not_measured[e["id"]] = (
                "not rendered by the producer (no \\FitMath)"
                if not e.get("placeholder") else
                "not rendered by the producer (\\FitMath placeholder)")
            continue
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
        verdict = eye.get(r["id"])
        if verdict and r["mark"]:
            r["mark"] = False
            why = f"suppressed by eye verdict ({verdict})"
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
        updated=dict(rows=len(upd), attempted=len(attempted)) if attempted else None,
        counts=counts, rows=out, not_measured=not_measured)))
    _log(f"{bib}: {counts['marked']} of {counts['evidence_rows']} rows marked; "
         f"{len(not_measured)} not measured")
    return 0



# --------------------------------------------------------------------------
# verify: is a set of marks actually DELIVERED, and did the build use them?
# --------------------------------------------------------------------------

#: Each check below exists because that exact thing failed on 2026-10-02,
#: and every one of them was invisible to the obvious test. Dates and
#: timestamps said the set was complete; it was not.
#:
#:   not delivered     the 09-16 delivery copied marks.json into 20 of 21
#:                     document folders and missed penev_A. A build with no
#:                     marks.json does not fail -- it produces evidence
#:                     without marks.
#:   stale delivery    same class, one step on: a delivered copy older than
#:                     the marks it claims to be.
#:   built without     pdfdrill's build takes the marks as an OFF-BY-DEFAULT
#:                     option, so a build without them succeeds, is newer
#:                     than the marks, and is byte-identical to one from
#:                     before marks existed. 20 of 21 were in this state and
#:                     a date-based check called all 20 ready.
#:   index disagrees   index.json carried the 09-11 emission's counts while
#:                     15 of 21 files had been edited by eye verdict since:
#:                     8,408 against a true 8,256.
#:
#: The tell in every case is the ARTIFACT, never the date. So this reads
#: what the build actually references, not when it ran.

MARKED_CROPS = "report-crops-marks"


def _evidence_parts(doc: pathlib.Path, stem: str = "evidence-formula"):
    """Every .tex that makes up the evidence set.

    A set is ONE file normally and SEVERAL when it had to be split: a
    22.3 MB Cardona against a 20 MB publishing ceiling, already floored
    at scale 0.60/q72, so the only remaining move was to cut it into
    parts. Anything that reads the evidence by one exact name goes blind
    the moment that happens, and reports a complete document as having
    no evidence at all.

    Both layouts, flat and nested, and both spellings -- `evidence-formula.tex`
    and `evidence-formula-1.tex`.
    """
    return sorted(set(list(doc.glob(f"{stem}*.tex"))
                      + list((doc / stem).glob(f"{stem}*.tex"))))


def _evidence_tex(doc: pathlib.Path, stem: str = "evidence-formula"):
    """The evidence .tex, NEWEST FIRST when both layouts exist.

    Two layouts are in the library -- `<doc>/<stem>/<stem>.tex` and the
    flat `<doc>/<stem>.tex` -- and assuming only the first had earlier
    reported four documents as missing evidence that was there.

    Order matters now, not just existence. pdfdrill's `ensure_doc_folder`
    had promoted 17 of 21 documents' evidence into a nested folder; today's
    build writes FLAT, so a rebuild leaves the stale nested copy in place
    beside the fresh one. A fixed preference reads whichever the author of
    the preference happened to pick, which for the nested one means
    reporting a correct rebuild as "built without marks". Newest wins, and
    the caller is told both exist.
    """
    found = _evidence_parts(doc, stem)
    if not found:
        return None
    return max(found, key=lambda p: p.stat().st_mtime)


def _evidence_both(doc: pathlib.Path, stem: str = "evidence-formula"):
    """The nested and flat copies of the SAME part, when both exist."""
    return [p for p in (doc / stem / f"{stem}.tex", doc / f"{stem}.tex")
            if p.exists()]


def _marks_of(path: pathlib.Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


#: emitted-by fields: they record WHICH BUILD wrote the file, not what it
#: says. Everything else, `measured_against` included, is content.
PROVENANCE = ("inkdrill",)


def _content(m):
    return {k: v for k, v in m.items() if k not in PROVENANCE}


def verify_document(name, marks_dir: pathlib.Path, library: pathlib.Path,
                    index=None):
    """One document's delivery state. Returns a dict; `fail` is the list
    of conditions that make it NOT delivered."""
    local_p = marks_dir / name / "marks.json"
    deliv_p = library / name / "marks.json"
    local = _marks_of(local_p) if local_p.exists() else None
    deliv = _marks_of(deliv_p) if deliv_p.exists() else None
    row = {"document": name, "fail": [], "warn": [], "parts": 0,
           "marked": (local or {}).get("counts", {}).get("marked"),
           "delivered": deliv is not None, "embedded": 0, "crops": 0}

    if local is None:
        row["fail"].append("no local marks.json")
        return row
    if deliv is None:
        row["fail"].append("not delivered to the library")
    elif deliv != local:
        # PROVENANCE IS NOT CONTENT. Three documents differed only in
        # `inkdrill`, the commit that emitted the file -- the marks were
        # identical, so a rebuild from the delivered copy draws exactly
        # the same boxes. Failing those would have sent someone
        # re-delivering three documents to change one hex string.
        # `measured_against` is NOT volatile: it names the pdfdrill build
        # the marks were measured against, and a disagreement there is a
        # real one.
        if _content(deliv) == _content(local):
            row["warn"].append(
                f"delivered copy was emitted by a different inkdrill build "
                f"({deliv.get('inkdrill')} against {local.get('inkdrill')}); "
                f"the marks themselves are identical")
        else:
            dm = deliv.get("counts", {}).get("marked")
            row["fail"].append(f"delivered copy differs in content "
                               f"(marked {dm} against {row['marked']})")

    doc = library / name
    both = _evidence_both(doc)
    if len(both) > 1:
        newest = max(both, key=lambda p: p.stat().st_mtime)
        stale = [p for p in both if p != newest]
        row["warn"].append(
            f"two evidence trees: reading {newest.relative_to(doc)}, "
            f"{', '.join(str(p.relative_to(doc)) for p in stale)} is older "
            f"and will be read by anything that prefers a fixed layout")
    # A SPLIT SET IS STILL ONE SET. Marks are summed across the parts:
    # a part covering a stretch of unmarked rows legitimately carries
    # none, and requiring each part to have some would fail a correct
    # split.
    # Drop the OLDER of a nested/flat pair -- by age, never by position.
    # `both` is built in layout order, so `both[1:]` is "the flat one",
    # which after a rebuild is the NEW one: excluding it reads the stale
    # nested copy and calls a correct rebuild unmarked, which is this
    # check inverted.
    stale = set()
    if len(both) > 1:
        newest = max(both, key=lambda q: q.stat().st_mtime)
        stale = {q for q in both if q != newest}
    parts = [p for p in _evidence_parts(doc) if p not in stale]
    row["parts"] = len(parts)
    if not parts:
        row["fail"].append("no evidence-formula.tex")
    else:
        used = None
        for tex in parts:
            src = tex.read_text(encoding="utf-8", errors="replace")
            row["embedded"] += src.count(MARKED_CROPS + "/")
            used = used or re.search(r"\{(report-crops[^/]*)/", src)
        if not row["embedded"]:
            row["fail"].append(
                "evidence built WITHOUT the marks"
                + (f" (it uses {used.group(1)})" if used else ""))

    crops = doc / MARKED_CROPS
    row["crops"] = len(list(crops.glob("*.jpg"))) if crops.is_dir() else 0
    if row["fail"] and row["crops"]:
        row["warn"].append(f"{row['crops']} marked crops are already on disk "
                           f"-- this is a rebuild, not a re-measure")
    if row["embedded"] and row["marked"] and row["embedded"] != row["marked"]:
        row["warn"].append(f"evidence draws {row['embedded']} marks, the file "
                           f"carries {row['marked']}")
    if index is not None:
        im = (index.get(name) or {}).get("marked")
        if im is not None and im != row["marked"]:
            row["warn"].append(f"index says {im}, the file says {row['marked']}")
    return row


def verify(marks_dir: pathlib.Path, library: pathlib.Path):
    """Every document under `marks_dir` that carries a marks.json."""
    names = sorted(p.parent.name for p in marks_dir.glob("*/marks.json"))
    idx_p = marks_dir / "index.json"
    index = None
    if idx_p.exists():
        index = (_marks_of(idx_p) or {}).get("documents")
    return [verify_document(n, marks_dir, library, index) for n in names]


def verify_cmd(marks_dir: pathlib.Path, library: pathlib.Path, as_json=False):
    rows = verify(marks_dir, library)
    if as_json:
        print(json.dumps({"documents": rows,
                          "delivered": sum(1 for r in rows if not r["fail"]),
                          "total": len(rows)}, indent=1))
    else:
        ok = [r for r in rows if not r["fail"]]
        print(f"{len(ok)} of {len(rows)} documents delivered AND built with "
              f"their marks")
        for r in rows:
            if not r["fail"] and not r["warn"]:
                continue
            print(f"\n  {r['document']}")
            for f in r["fail"]:
                print(f"    FAIL  {f}")
            for w in r["warn"]:
                print(f"    warn  {w}")
        if not any(r["fail"] or r["warn"] for r in rows):
            print("  nothing to report")
    return 1 if any(r["fail"] for r in rows) else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify")
    v.add_argument("--marks-dir", type=pathlib.Path,
                   default=pathlib.Path.home() / "inkdrill-marks")
    v.add_argument("--library", type=pathlib.Path,
                   default=pathlib.Path.home() / "pdfdrill-library")
    v.add_argument("--json", action="store_true")
    for name in ("run", "marks", "update"):
        a = sub.add_parser(name)
        a.add_argument("bibkey")
        a.add_argument("--library", type=pathlib.Path,
                       default=pathlib.Path.home() / "pdfdrill-library")
        a.add_argument("--work", type=pathlib.Path, required=True)
        if name == "run":
            a.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args()
    if args.cmd == "verify":
        return verify_cmd(args.marks_dir, args.library, args.json)
    if args.cmd == "run":
        return run(args.library, args.bibkey, args.work, args.jobs)
    if args.cmd == "update":
        return update(args.library, args.bibkey, args.work)
    return marks(args.library, args.bibkey, args.work)


if __name__ == "__main__":
    raise SystemExit(main())
