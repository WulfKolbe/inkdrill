"""Region-overrun profile over the flagged rows of the compare channel
(102).

A component-class finding says the scan carries ink the rendering does
not. Two different things produce that, and they want opposite fixes:

  a CONVERSION defect -- the other tool dropped a symbol, which is the
  finding this channel exists to report;
  a CROPPING defect  -- the scan crop overran its region and captured
  ink belonging to the neighbouring line, rule or column, which is a
  finding about the crop and says nothing about the conversion.

`mathstruct.region_overrun` separates them by two conditions that must
BOTH hold: the surplus component is outside the main ink's
single-linkage cluster at `gap_scale` x the crop's median component
width, AND it reaches a crop edge. This tool prints the distribution of
both conditions across a threshold sweep BEFORE either default is
fixed, because a threshold chosen from a guess is the failure this
project has paid for repeatedly.

POPULATION and its rule are printed with the answer: rows come from the
cached 300 dpi report renders under $INKDRILL_WORK, which is the same
raster the flags were computed on, so nothing is re-rendered and no
document being rebuilt elsewhere can move under the measurement.

Usage: python3 tools/overrun.py [--gap-scale F ...] [--edge-tol N ...]
                                [--library DIR] [--work DIR]
"""
import argparse, os, pathlib, re, sys, tempfile, collections

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from inkdrill.__main__ import _table_cells, _cell_crop     # noqa: E402
from inkdrill.pngio import read_png, auto_mask             # noqa: E402
from inkdrill.mathstruct import region_overrun, pair_counts  # noqa: E402
from inkdrill.nest import ink_only                         # noqa: E402
from findings import flag_of                               # noqa: E402

ap = argparse.ArgumentParser(prog="tools/overrun.py",
                             description=__doc__.strip().splitlines()[0])
ap.add_argument("--library", default="~/pdfdrill-library")
ap.add_argument("--work", default=None)
ap.add_argument("--gap-scale", type=float, nargs="+",
                default=[0.5, 1.0, 1.5, 2.0, 3.0])
ap.add_argument("--edge-tol", type=int, nargs="+", default=[0, 1, 2, 4])
ap.add_argument("--only", nargs="*", default=None,
                help="restrict to these document directories")
ap.add_argument("--jobs", type=int, default=8,
                help="documents swept in parallel")
A = ap.parse_args()

LIB = pathlib.Path(A.library).expanduser()
S = pathlib.Path(A.work or os.environ.get("INKDRILL_WORK") or
                 (tempfile.gettempdir() + "/inkdrill-reportcompare"))


def demoted_idents(name):
    tex = LIB / name / "report.tex"
    if not tex.is_file():
        return set()
    return {m.group(1).replace("\\", "").replace("allowbreak{}", "")
            for m in re.finditer(
                r"\\ident\{([^&\n]*?EQ\d+)\}(.*?)\\\\ \\hline",
                tex.read_text(), re.S)
            if "emph{(not rendered)}" in m.group(2)}


def idents_for(name):
    tex = LIB / name / "report.tex"
    if not tex.is_file():
        return []

    def _clean(t):
        return t.replace("\\allowbreak{}", "").replace("\\", "")
    return [_clean(m.group(1)) for m in
            re.finditer(r"\\ident\{([^&\n]*?EQ\d+)\}[^&\n]*& *(\d+) *&",
                        tex.read_text())]


KEYS = ("components", "holes", "stacked", "centred", "offset")


def rows_of(name):
    """Every compared row of one document, from its CACHED render.

    Yields (ident_or_None, L, R, dis, comp_delta, flag, scan_crop).
    The md carries the five-tuples the flags were computed from; the
    png is re-cut only to get the scan crop's pixels.
    """
    d = S / name
    mds = sorted(d.glob("p*.md"))
    out = []
    for md in mds:
        p = int(md.stem[1:])
        png = d / f"p{p:03d}_r300.png"
        if not png.is_file():
            continue
        img = read_png(png)
        m = auto_mask(img.gray, img.width, img.height, 200)[0]
        cells = _table_cells(m, 4.0)
        if not cells:
            continue
        nr = max(r for r, _ in cells) + 1
        nc = max(c for _, c in cells) + 1
        hts = {r: cells[(r, 0)][3] - cells[(r, 0)][1] for r in range(nr)}
        for line in md.read_text().splitlines()[2:]:
            c = [x.strip() for x in line.split("|")[1:-1]]
            ln = int(c[1])
            if ln == 0 or hts.get(ln, 999) < 40:
                continue
            L = [int(x) for x in c[3:8]]
            R = [int(x) for x in c[8:13]]
            dis = sum(abs(x - y) for x, y in zip(L, R))
            cd = abs(L[0] - R[0])
            fl = flag_of(dis, cd, c[13] == "yes")
            b = cells.get((ln, nc - 1))
            crop = (_cell_crop(m, b[0], b[1], b[2] - 1, b[3] - 1)
                    if b else None)
            out.append([None, L, R, dis, cd, fl, crop])
    idents = idents_for(name)
    if len(idents) >= len(out):
        for rec, ident in zip(out, idents):
            rec[0] = ident
    return out


docs = sorted(p.name for p in S.iterdir()
              if p.is_dir() and list(p.glob("p*_r300.png")))
if A.only:
    docs = [d for d in docs if d in A.only]

GRID = ([(gs, et, "edge") for gs in A.gap_scale
         for et in A.edge_tol] +
        [(gs, 0, "extreme") for gs in A.gap_scale])


def sweep_document(name):
    """One document's contribution: flag counts, the threshold tally,
    and one record per flagged row. Returned rather than accumulated
    so the documents can run in separate processes -- the tally is a
    sum and the row list a concatenation, both order-free, so the
    worker count cannot change the answer."""
    counts = collections.Counter()
    tally = {k: [0, 0, 0, 0, 0] for k in GRID}
    rows = []
    demoted = 0
    dem = demoted_idents(name)
    for ident, L, R, dis, cd, fl, crop in rows_of(name):
        if ident is not None and ident in dem:
            demoted += 1
            continue
        counts[fl] += 1
        if fl not in ("component", "stable", "weak") or crop is None:
            continue
        surplus = R[0] - L[0]
        ip = ink_only(crop)
        cs = list(ip.regions)
        cy = dict(zip((r.id for r in cs), ip.cycles))
        row_over = {}
        for k in GRID:
            gs, et, anchor = k
            ro = region_overrun(crop, gap_scale=gs, edge_tol=et,
                                anchor=anchor, comps=cs)
            tl = tally[k]
            tl[0] += bool(ro["separated"])
            tl[1] += bool(ro["at_edge"])
            n = len(ro["overrun"])
            row_over[k] = n
            if not n:
                continue
            tl[2] += 1
            if surplus > 0 and n >= surplus:
                tl[3] += 1
            kept = ro["kept"]
            st, ce, of = pair_counts(kept)
            R2 = [len(kept), sum(cy[c.id] for c in kept), st, ce, of]
            d2 = sum(abs(x - y) for x, y in zip(L, R2))
            if flag_of(d2, abs(L[0] - R2[0]), False) in ("clean", "noise"):
                tl[4] += 1
        # The INSET diagnostic: how far the ink stops short of each
        # border. A CONSTANT margin across differently sized crops
        # means the edge anchor is measuring the producer's inset and
        # not the region boundary -- the reason the second anchor
        # exists, and it is recorded per row rather than asserted.
        margins = (min(c.x0 for c in cs), min(c.y0 for c in cs),
                   crop.width - 1 - max(c.x1 for c in cs),
                   crop.height - 1 - max(c.y1 for c in cs))
        rows.append((name, ident, dis, cd, fl, surplus,
                     [row_over[k] for k in GRID], margins,
                     crop.width, crop.height))
    return counts, demoted, tally, rows


def main():
    import concurrent.futures as cf
    counts = collections.Counter()
    tally = {k: [0, 0, 0, 0, 0] for k in GRID}
    per_row = []
    skipped_demoted = 0
    with cf.ProcessPoolExecutor(max_workers=A.jobs) as ex:
        for i, (c, dm, tl, rows) in enumerate(
                ex.map(sweep_document, docs), 1):
            counts.update(c)
            skipped_demoted += dm
            for k in GRID:
                for j in range(5):
                    tally[k][j] += tl[k][j]
            per_row.extend(rows)
            print(f"  .. {i}/{len(docs)}", file=sys.stderr, flush=True)

    n_flagged = len(per_row)
    n_surplus = sum(1 for r in per_row if r[5] > 0)
    print(f"POPULATION: {len(docs)} documents with a cached 300 dpi "
          f"render under {S}")
    print(f"  rows compared      {sum(counts.values())}")
    print(f"  demoted excluded   {skipped_demoted}")
    print("  flags              " +
          "  ".join(f"{k} {counts[k]}" for k in
                    ("clean", "noise", "weak", "stable", "component")))
    print(f"  FLAGGED (component+stable+weak) {n_flagged}")
    print(f"  of which the SCAN has more components than the "
          f"rendering: {n_surplus}")
    print()
    print("condition counts over the flagged rows "
          "(REGION-OVERRUN needs BOTH)")
    print("anchor\tgap_scale\tedge_tol\tseparated\tat_edge\toverrun"
          "\texplains_surplus\tfalls_to_noise")
    for k in GRID:
        gs, et, anchor = k
        print("\t".join(map(str, [anchor, gs,
                                  et if anchor == "edge" else "-"]
                            + tally[k])))

    # The inset, measured rather than assumed.
    import statistics
    for i, side in enumerate(("left", "top", "right", "bottom")):
        v = sorted(r[7][i] for r in per_row)
        if not v:
            continue
        print(f"  margin {side:<7} px  min {v[0]}  p50 "
              f"{statistics.median(v):.0f}  p95 {v[int(.95 * (len(v) - 1))]}"
              f"  max {v[-1]}")

    RES = pathlib.Path(__file__).resolve().parent.parent / "results"
    RES.mkdir(exist_ok=True)
    import datetime
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = RES / f"overrun-{stamp}.tsv"
    hdr = ["bibkey", "id", "distance", "comp_delta", "flag", "surplus"] \
        + [f"{a}@g{gs}" + (f"e{et}" if a == "edge" else "")
           for gs, et, a in GRID] \
        + ["m_left", "m_top", "m_right", "m_bottom", "crop_w", "crop_h"]
    out.write_text("\n".join(
        ["\t".join(hdr)] +
        ["\t".join(map(str, list(r[:6]) + r[6] + list(r[7]) +
                        [r[8], r[9]]))
         for r in sorted(per_row)]) + "\n")
    print(f"\n{len(per_row)} flagged rows -> {out}")


if __name__ == "__main__":
    main()
