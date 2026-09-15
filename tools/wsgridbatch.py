r"""wsgridbatch.py -- `wsgrid` over a list of display equations, against their readings.

    python3 tools/wsgridbatch.py CANDIDATES.json --out DIR [--jobs 8]

CANDIDATES.json is pdfdrill's shape: {"rows": [{"id": "<bibkey>_EQnnnn", ...}]}.
For each row: find its host `math` line, cut it lossless from
`inspect/pages` (400 dpi) through `page_frames`, run `wsgrid.measure`,
compare cells per row with the reading. Writes DIR/<id>.pgm, DIR/<id>.json
and DIR/batch.json; reads the library and nothing else.

THE HOST RULE FOR A DISPLAY ROW is not formulafind's. `host_regions`
places INLINE spans and skips `math` lines, which is exactly where a
display equation lives; run on 132 display rows it placed none. Here, in
order, and the rule used is recorded per row:

  1. on the row's page, the math line whose body (\[ \] or $$ stripped,
     whitespace removed) EQUALS the reading          -> "exact"
  2. on the row's page, the most similar line, ratio >= 0.8
                                                     -> "similar 0.xx"
  3. no page column: the ONE line on any page that equals the reading
                                                     -> "exact, any page"

Rule 3 was written for 62 candidates that appeared to have no page. They
had one: `formulafind.rows` lost it behind the `~\eqnum{...}` suffix of
the id cell (out/669). With the parser fixed, every evidence row carries
a page and rule 3 is a fallback that should not fire. The reading is
the rendered one, else the source cell of a not-rendered row.

WHAT THE OUTPUT IS NOT (out/668): a count of blank cells. Eye-checked
on 17 candidates chosen across outcomes, 5 grids were right, 5 partly
right, 7 wrong. The region of a display line holds more than the array
(labels, `A :=`, `\in R^{n x n}`), subscripts and diagonal dots split
lines, and two alignments sharing a pitch merge into one lattice whose
margins read as empty. See out/668 for which gate, if any, selects the
right ones.
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import difflib
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from inkdrill import pnmio  # noqa: E402
from tools import wsgrid  # noqa: E402
from tools.formulafind import frame_rect, line_index, page_frames, rows  # noqa: E402

LIB = pathlib.Path.home() / "pdfdrill-library"
MARKS = pathlib.Path.home() / "inkdrill-marks"
SIMILAR = 0.8


def norm(t: str) -> str:
    t = (t or "").strip()
    for a, b in (("\\[", "\\]"), ("$$", "$$")):
        if t.startswith(a) and t.endswith(b):
            t = t[len(a):len(t) - len(b)]
    return re.sub(r"\s+", "", t)


def reading(r):
    """The rendered reading, else the source cell (a not-rendered row)."""
    return r["math"] if r["math"] is not None else (r.get("source") or "")


def display_hosts(dirname, picked):
    """id -> (page, region, rule). See the module docstring."""
    idx = line_index(LIB, dirname)[0]
    everywhere = [(p, reg, norm(t)) for p, lines in idx.items() for reg, t in lines]
    out = {}
    for r in picked:
        want = norm(reading(r))
        if not want:
            continue
        if r["page"]:
            pg = int(r["page"])
            cands = [(reg, norm(t)) for reg, t in idx.get(pg, [])]
            exact = [reg for reg, t in cands if t == want]
            if exact:
                out[r["id"]] = (pg, exact[0], "exact")
                continue
            scored = [(difflib.SequenceMatcher(None, t, want).ratio(), reg) for reg, t in cands]
            if scored:
                q, reg = max(scored, key=lambda s: s[0])
                if q >= SIMILAR:
                    out[r["id"]] = (pg, reg, f"similar {q:.2f}")
            continue
        hits = [(p, reg) for p, reg, t in everywhere if t == want]
        if len(hits) == 1:
            out[r["id"]] = (hits[0][0], hits[0][1], "exact, any page")
    return out


def reading_empties(latex):
    rc = wsgrid.reading_cells(latex or "")
    return None if rc is None else sum(a - b for a, b in zip(*rc))


def one_document(dirname, ids, outdir):
    doc = LIB / dirname
    f = doc / "evidence-equation.tex"
    mtime0 = f.stat().st_mtime
    picked = [r for r in rows(f) if r["id"] in ids]
    hosts = display_hosts(dirname, picked)
    frames, refused = page_frames(LIB, dirname)
    res = []
    for r in picked:
        rec = dict(id=r["id"], page=r["page"], reading_empties=reading_empties(reading(r)))
        hit = hosts.get(r["id"])
        if not hit:
            rec["why"] = "no host line"
            res.append(rec)
            continue
        page, reg, rule = hit
        if page not in frames:
            rec["why"] = f"page refused: {refused.get(page)}"
            res.append(rec)
            continue
        x, y, w, h = frame_rect(reg, frames[page])
        pgm = outdir / f"{r['id']}.pgm"
        subprocess.run(["magick", str(doc / "inspect" / "pages" / f"p{page}.png"), "-crop",
                        f"{w}x{h}+{x}+{y}", "+repage", "-colorspace", "Gray", "-depth", "8",
                        str(pgm)], check=True, capture_output=True)
        g = wsgrid.measure(pnmio.load_mask(str(pgm), dpi=400))
        g["reading"] = wsgrid.compare(g, reading(r))
        g.update(page=page, region_mathpix_px=reg, host=rule)
        rd = g["reading"]
        rec.update(host_page=page, region=reg, host=rule, crop=[w, h],
                   blocks=[[b["rows"], b["columns"], sum(map(sum, b["empty"]))] for b in g["blocks"]],
                   ink_empties=sum(sum(map(sum, b["empty"])) for b in g["blocks"]),
                   outcome=("refused" if "refused" in rd else
                            "agree" if not rd["disagree"] else "disagree"))
        (outdir / f"{r['id']}.json").write_text(json.dumps({r["id"]: g}))
        res.append(rec)
    return dict(dir=dirname, rows=res, evidence_changed_during_run=f.stat().st_mtime != mtime0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("candidates", type=pathlib.Path)
    ap.add_argument("--out", type=pathlib.Path, required=True)
    ap.add_argument("--jobs", type=int, default=8)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    cand = json.loads(args.candidates.read_text())["rows"]
    prefix = {}
    for m in MARKS.iterdir():
        f = LIB / m.name / "evidence-equation.tex"
        if m.is_dir() and f.exists():
            first = next(iter(rows(f)), None)
            if first:
                prefix[first["id"].rsplit("_", 1)[0]] = m.name
    by = collections.defaultdict(set)
    unmapped = []
    for c in cand:
        p = c["id"].rsplit("_", 1)[0]
        (by[prefix[p]].add(c["id"]) if p in prefix else unmapped.append(c["id"]))
    with cf.ProcessPoolExecutor(args.jobs) as ex:
        docs = list(ex.map(one_document, list(by), [by[k] for k in by],
                           [args.out] * len(by)))
    allr = [r for d in docs for r in d["rows"]]
    summary = dict(candidates=len(cand), unmapped=unmapped,
                   outcomes=collections.Counter(r.get("why") or r["outcome"] for r in allr),
                   hosts=collections.Counter(r.get("host", "none") for r in allr),
                   changed_during_run=[d["dir"] for d in docs if d["evidence_changed_during_run"]])
    (args.out / "batch.json").write_text(json.dumps(dict(summary=summary, documents=docs), indent=1))
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
