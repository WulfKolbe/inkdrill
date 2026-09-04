"""608 -- run the residual against a real emitted manifest.

`cellcheck.py` compares the lattice to rules read out of the PDF's own
vector content, which is the stand-in emitter. This one takes the
MANIFEST pdfdrill emits and does the same comparison, so the number
describes the thing that will actually be shipped.

MATCHING IS BY GEOMETRY, NOT BY INDEX. A page's lattice includes the
table's printed header row and the manifest does not, so pairing the
k-th manifest row to the k-th lattice row is off by one on exactly the
pages that carry a header -- the defect 386 and `inkmeasure` both had
to work around. Each manifest row is instead paired to the lattice row
its y-range overlaps most, and anything unpaired on either side is
reported rather than dropped.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import statistics
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from inkdrill.__main__ import _drop_slivers, _table_cells      # noqa: E402
from inkdrill.cellrect import row_rects                        # noqa: E402
from inkdrill.pnmio import mask_from_pgm                       # noqa: E402


def lattice_of(pdf, page, dpi, work):
    f = work / f"mc_{pdf.parent.name[:16]}_{page}_{dpi}.pgm"
    if not f.exists():
        subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH",
                        "-sDEVICE=pgmraw", f"-r{dpi}",
                        f"-dFirstPage={page}", f"-dLastPage={page}",
                        f"-sOutputFile={f}", str(pdf)], check=True)
    m = mask_from_pgm(f, threshold=200)
    c = _table_cells(m, 4.0, debug={})
    if not c:
        return None, m
    return _drop_slivers(c, m.height), m


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("doc")
    ap.add_argument("--library", type=pathlib.Path,
                    default=pathlib.Path.home() / "pdfdrill-library")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--work", type=pathlib.Path, default=pathlib.Path("/tmp"))
    args = ap.parse_args()
    d = args.library / args.doc
    man = json.loads((d / "pdfdrill-rows.json").read_text())
    pdf = d / man.get("measured_against", {}).get("pdf", "report.pdf")

    # THE MANIFEST NAMES THE BUILD IT DESCRIBES. 606B measured a
    # manifest 14 s older than the pdf beside it, whose rows were not
    # in that pdf at all; checking the stamp costs one hash.
    want = man.get("measured_against", {}).get("sha256")
    got = hashlib.sha256(pdf.read_bytes()).hexdigest()
    print(f"{args.doc}  manifest {len(man['rows'])} rows, "
          f"{len(man['tables'])} tables")
    print(f"  measured_against {pdf.name}  sha "
          f"{'MATCH' if want == got else 'MISMATCH'}")
    if want != got:
        print("  refusing: the manifest does not describe this pdf")
        return 1
    ph = man["page_height_bp"]
    rw = man.get("rule_width_bp", 0.4)
    cols = {t["table"]: t["column_rules_bp"] for t in man["tables"]}
    for t in sorted(cols):
        print(f"  table {t}: {len(cols[t])} column rules "
              f"({len(cols[t])-1} columns)")

    per_page = {}
    for r in man["rows"]:
        per_page.setdefault(r["page"], []).append(r)

    d_all = {k: [] for k in ("x0", "y0", "x1", "y1")}
    per_page_d = {}
    refused, unpaired = [], []
    for page in sorted(per_page):
        lat, m = lattice_of(pdf, page, args.dpi, args.work)
        rows = per_page[page]
        if lat is None:
            print(f"  page {page}: NO LATTICE, {len(rows)} manifest rows")
            unpaired += [(r["identifier"], "no lattice") for r in rows]
            continue
        nr = max(a for a, _ in lat) + 1
        nc = max(b for _, b in lat) + 1
        lat_rows = {a: lat[(a, 0)] for a in range(nr) if (a, 0) in lat}
        used = set()
        d_page = {k: [] for k in ("x0", "y0", "x1", "y1")}
        for r in rows:
            if not r.get("rules_on_one_page", True):
                refused.append(r["identifier"])
                continue
            rects = row_rects(cols[r["table"]], r["rule_above_bp"],
                              r["rule_below_bp"], page_height_bp=ph,
                              dpi=args.dpi, rule_bp=rw)
            # pair to the lattice row it overlaps most
            best, bidx = 0, None
            for a, (_x0, ly0, _x1, ly1) in lat_rows.items():
                if a in used:
                    continue
                ov = min(rects[0].y1, ly1) - max(rects[0].y0, ly0)
                if ov > best:
                    best, bidx = ov, a
            if bidx is None:
                unpaired.append((r["identifier"], f"p{page} no overlap"))
                continue
            used.add(bidx)
            for c in range(min(nc, len(rects))):
                if (bidx, c) not in lat:
                    continue
                lx0, ly0, lx1, ly1 = lat[(bidx, c)]
                e = rects[c]
                for k, v in zip(("x0", "y0", "x1", "y1"),
                                (e.x0 - lx0, e.y0 - ly0,
                                 e.x1 - lx1, e.y1 - ly1)):
                    d_all[k].append(v)
                    d_page[k].append(v)
        per_page_d[page] = d_page
        print(f"  page {page}: lattice {nr}x{nc}, {len(rows)} manifest rows, "
              f"{len(d_page['x0'])} cells compared")

    def table(d, label):
        n = len(d["x0"])
        if not n:
            print(f"\n{label}: no cells")
            return
        print(f"\n{label}  ({n} cells)")
        print(f"  {'edge':>5} {'median':>7} {'min':>5} {'max':>5} "
              f"{'<=1px':>7}")
        for k in ("x0", "y0", "x1", "y1"):
            v = d[k]
            print(f"  {k:>5} {statistics.median(v):>7.1f} {min(v):>5} "
                  f"{max(v):>5} "
                  f"{100*sum(1 for x in v if abs(x)<=1)/len(v):>6.1f}%")

    table(d_all, "ALL CELLS")
    for page in sorted(per_page_d):
        table(per_page_d[page], f"page {page}")
    print(f"\nrefused (rules_on_one_page false): {refused}")
    print(f"unpaired: {unpaired}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
