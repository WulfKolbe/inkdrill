"""610 -- the DIRECT comparison: emitted rule positions against the PDF's.

No raster, no lattice, no dpi. Both sides are bp in PDF user space, so
the delta is the emitter's error with nothing else folded into it.

BOTH SIDES MUST BE CENTRELINES. `mutool trace` gives a stroke's PATH,
which is its centreline: the ink covers centre +/- linewidth/2. Checked
against the pixels on 0049 page 1 -- the PDF says 692.852, which at 300
dpi predicts ink on raster rows 620.16..621.82, and the ink is on rows
620 and 621 exactly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import statistics
import subprocess as _sp
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from pdfrules import rules                                    # noqa: E402


def nearest(v, xs):
    """The closest rule, or None when the page carries none.

    EVERY CALLER MUST HANDLE THE NONE. The first version subtracted the
    result unconditionally and crashed with a TypeError on 21 of 22
    documents, which reads as a broken tool rather than as what it is:
    a manifest describing pages the PDF does not have. A refusal that
    names the reason is worth more than a traceback.
    """
    return min(xs, key=lambda x: abs(x - v)) if xs else None


def npages(pdf) -> int:
    out = _sp.run(["pdfinfo", str(pdf)], capture_output=True,
                  text=True).stdout
    for line in out.splitlines():
        if line.startswith("Pages:"):
            return int(line.split()[1])
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("doc")
    ap.add_argument("--library", type=pathlib.Path,
                    default=pathlib.Path.home() / "pdfdrill-library")
    args = ap.parse_args()
    d = args.library / args.doc
    man = json.loads((d / "pdfdrill-rows.json").read_text())
    pdf = d / man.get("measured_against", {}).get("pdf", "report.pdf")
    ph = man["page_height_bp"]
    rw = man.get("rule_width_bp", 0.4)
    print(f"{args.doc}   rule_width_bp {rw}   half {rw/2:.4f}")

    # THE MANIFEST MUST DESCRIBE THIS PDF, and there are two ways it
    # can fail to. The sha is the exact test; the page range is the one
    # that explains WHY when the sha has already failed.
    want = man.get("measured_against", {}).get("sha256")
    got = hashlib.sha256(pdf.read_bytes()).hexdigest()
    n = npages(pdf)
    # A ROW MAY CARRY NO PAGE. 488 established that inline-formula rows
    # have none, and `max()` over a generator holding a None raises a
    # TypeError comparing None to int rather than saying so. Counted and
    # reported, never silently dropped.
    paged = [r for r in man["rows"] if r.get("page") is not None]
    nopage = len(man["rows"]) - len(paged)
    hi = max((r["page"] for r in paged), default=0)
    if nopage:
        print(f"  {nopage} of {len(man['rows'])} rows carry no page and "
              f"are not checked here")
    print(f"  measured_against {pdf.name}  sha "
          f"{'MATCH' if want == got else 'MISMATCH'}"
          f"   manifest pages 1..{hi}, pdf has {n}")
    if hi > n:
        print(f"  REFUSED: the manifest names page {hi} and the pdf has "
              f"{n}. This is not a geometry difference -- it is a "
              f"different build, and no delta computed against it would "
              f"mean anything.")
        return 1
    if want != got:
        print("  WARNING: sha mismatch. The page count fits, so the "
              "deltas below are computed, but they compare a manifest "
              "against a pdf it does not claim to describe.")
    print()

    per_page = {}
    for r in paged:
        per_page.setdefault(r["page"], []).append(r)
    cache = {p: rules(pdf, p, ph) for p in sorted(per_page)}

    # VERTICAL: the manifest's column rules against the PDF's
    print("COLUMN RULES (x, bp)")
    print(f"  {'table':>5} {'n emitted':>10} {'n in pdf':>9}   deltas")
    dx = []
    for t in man["tables"]:
        page = next((r["page"] for r in paged
                     if r.get("table") == t.get("table")), None)
        if page is None:
            print(f"  {t.get('table'):>5} {len(t['column_rules_bp']):>10} "
                  f"{'-':>9}   no paged row references this table")
            continue
        _h, v = cache[page]
        xs = sorted(v)
        ds = [round(e - nearest(e, xs), 4) for e in t["column_rules_bp"]
              if nearest(e, xs) is not None]
        if not ds:
            print(f"  {t['table']:>5} {len(t['column_rules_bp']):>10} "
                  f"{len(xs):>9}   page {page} carries no vertical rules")
            continue
        dx += ds
        print(f"  {t['table']:>5} {len(t['column_rules_bp']):>10} "
              f"{len(xs):>9}   {ds}")

    # HORIZONTAL: each row's two rules against the PDF's
    print("\nROW RULES (y, bp)")
    dy = []
    for page in sorted(per_page):
        h, _v = cache[page]
        ys = sorted(h)
        for r in per_page[page]:
            if not r.get("rules_on_one_page", True):
                continue
            for key in ("rule_above_bp", "rule_below_bp"):
                nr = nearest(r[key], ys)
                if nr is not None:
                    dy.append(round(r[key] - nr, 4))
    def rep(name, v):
        if not v:
            print(f"  {name}: none")
            return
        print(f"  {name:<16} n {len(v):>4}  median {statistics.median(v):+.4f}"
              f"  min {min(v):+.4f}  max {max(v):+.4f}  "
              f"distinct {sorted(set(v))[:6]}")
    rep("x (columns)", dx)
    rep("y (rows)", dy)
    print(f"\n  half a rule is {rw/2:+.4f} bp")
    print(f"  a y delta of {rw/2:+.4f} means the EDGE was emitted, not the "
          f"centreline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
