"""hostdrift.py -- does formulafind's host-line rule still agree with pdfdrill's?

    python3 tools/hostdrift.py [--pdfdrill-src ~/MX/PDFDRILL/src]

`formulafind.first_occurrence_lines` REPRODUCES pdfdrill's host-line rule
so a mark lands on the line pdfdrill crops. pdfdrill changed that rule on
2026-09-12 (their 674/676): a span counts only on a line whose type can
host a transclusion (`docmodel.line_types.hosts_transclusion` -- tables,
headings, titles, TOC entries and figure labels excluded), and the span
scan reads `text_display or text`. Nothing here noticed, because a mark
whose host differs is REFUSED by pdfdrill, not drawn wrong (out/673).

This imports pdfdrill's own `inlinectx.load_spans` / `first_occurrences`
read-only and compares, per published formula row, the host each rule
gives -- by MathPix's reading where the shown one was refined, as
`formulamarks` looks it up -- and counts marks pdfdrill's rule refuses.
Reads the library and pdfdrill's source; writes nothing.
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.formulafind import first_occurrence_lines, mathpix_readings, rows  # noqa: E402

LIB = pathlib.Path.home() / "pdfdrill-library"
MARKS = pathlib.Path.home() / "inkdrill-marks"


def _key(page, region):
    return (page, tuple(sorted((region or {}).items())))


def document(D, load_spans, first_occurrences):
    lj = LIB / D / f"{D}.lines.json"
    mine = first_occurrence_lines(LIB, D)
    theirs = {k: _key(s["page"], s["region"])
              for k, s in first_occurrences(load_spans(lj)).items()}
    mp = mathpix_readings(LIB, D)
    marked = {r["id"]: r for r in json.loads((MARKS / D / "marks.json").read_text())["rows"]
              if r["mark"]}
    c, refused = collections.Counter(), []
    for e in rows(LIB / D / "evidence-formula.tex"):
        if e["math"] is None:
            continue
        hm = mp.get(e["id"])
        look = (hm if hm and hm.strip() != e["math"].strip() else e["math"]).strip()
        a = mine.get(look)
        a = _key(*a) if a else None
        b = theirs.get(look)
        c["rows"] += 1
        if a == b:
            continue
        c["theirs: no host" if b is None else "mine: no host" if a is None
          else "different host"] += 1
        r = marked.get(e["id"])
        if r and _key(r["host_page"], r["region"]) != b:
            c["marked, refused by their rule"] += 1
            refused.append(e["id"])
    return c, refused


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdfdrill-src", type=pathlib.Path,
                    default=pathlib.Path.home() / "MX/PDFDRILL/src")
    args = ap.parse_args()
    sys.path.insert(0, str(args.pdfdrill_src))
    from pdfdrill.inlinectx import first_occurrences, load_spans
    tot, all_refused = collections.Counter(), {}
    for m in sorted(MARKS.iterdir()):
        if not (m.is_dir() and (m / "marks.json").exists()
                and (LIB / m.name / f"{m.name}.lines.json").exists()):
            continue
        c, refused = document(m.name, load_spans, first_occurrences)
        print(f"{m.name[:40]:<41} {dict(c)}")
        tot.update(c)
        if refused:
            all_refused[m.name] = refused
    print("TOTAL", dict(tot))
    print(json.dumps(all_refused, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
