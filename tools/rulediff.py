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
import json
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from pdfrules import rules                                    # noqa: E402


def nearest(v, xs):
    return min(xs, key=lambda x: abs(x - v)) if xs else None


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
    print(f"{args.doc}   rule_width_bp {rw}   half {rw/2:.4f}\n")

    per_page = {}
    for r in man["rows"]:
        per_page.setdefault(r["page"], []).append(r)
    cache = {p: rules(pdf, p, ph) for p in sorted(per_page)}

    # VERTICAL: the manifest's column rules against the PDF's
    print("COLUMN RULES (x, bp)")
    print(f"  {'table':>5} {'n emitted':>10} {'n in pdf':>9}   deltas")
    dx = []
    for t in man["tables"]:
        page = next(r["page"] for r in man["rows"] if r["table"] == t["table"])
        _h, v = cache[page]
        xs = sorted(v)
        ds = [round(e - nearest(e, xs), 4) for e in t["column_rules_bp"]]
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
                dy.append(round(r[key] - nearest(r[key], ys), 4))
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
