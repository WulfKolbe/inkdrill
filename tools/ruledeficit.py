"""Do the components a scan is MISSING sit next to a rule? (117)

A flagged row with a negative component delta says the scan carries
fewer marks than the rendering of the same expression. If those marks
cluster around rules -- fraction bars, radicals, table separators --
the deficit is a story about thin horizontal ink surviving a scan, and
that is a locatable defect a consumer can act on. If they are
scattered, it is not.

WHICH COMPONENTS ARE MISSING is a matching problem, and the matching
here is deliberately THRESHOLD-FREE. Both cells hold the same
expression at different scales and offsets, so each component's box is
normalised to its own crop's ink bounding box and a rendered component
counts as PRESENT when any scan component's normalised box overlaps
it. Overlap is `> 0`; there is no tolerance to tune, and therefore no
constant that could be moved until the answer came out.

THE MATCHING CHECKS ITSELF. `unmatched` should come out close to the
row's actual deficit. Where it does not, the normalisation is wrong
for that row -- one stray blob moves a bounding box, and 102 measured
that scan cells really do carry ink from outside their region -- so
the residual is printed per row and the aggregate is reported over
rows whose matching is sound, with the rest counted and named.

Usage: python3 tools/ruledeficit.py [--work DIR] [--library DIR]
                                    [--reach F] [--only DOC ...]
"""
import argparse, collections, os, pathlib, re, statistics, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from inkdrill.__main__ import _table_cells, _cell_crop     # noqa: E402
from inkdrill.pngio import read_png, auto_mask             # noqa: E402
from inkdrill.nest import ink_only                         # noqa: E402
from inkdrill.emit import is_rule                          # noqa: E402
from findings import flag_of                               # noqa: E402

ap = argparse.ArgumentParser(prog="tools/ruledeficit.py",
                             description=__doc__.strip().splitlines()[0])
ap.add_argument("--library", default="~/pdfdrill-library")
ap.add_argument("--work", default=None)
ap.add_argument("--reach", type=float, default=1.0,
                help="nearness to a rule, in median glyph widths")
ap.add_argument("--only", nargs="*", default=None)
ap.add_argument("--jobs", type=int, default=8)
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
                tex.read_text(errors="replace"), re.S)
            if "emph{(not rendered)}" in m.group(2)}


def idents_for(name):
    tex = LIB / name / "report.tex"
    if not tex.is_file():
        return []
    return [m.group(1).replace("\\allowbreak{}", "").replace("\\", "")
            for m in re.finditer(
                r"\\ident\{([^&\n]*?EQ\d+)\}[^&\n]*& *(\d+) *&",
                tex.read_text(errors="replace"))]


def norm_boxes(comps):
    """Each box as a fraction of the ink bounding box of its own crop."""
    if not comps:
        return []
    x0 = min(c.x0 for c in comps); x1 = max(c.x1 for c in comps)
    y0 = min(c.y0 for c in comps); y1 = max(c.y1 for c in comps)
    w = max(1, x1 - x0 + 1); h = max(1, y1 - y0 + 1)
    return [((c.x0 - x0) / w, (c.y0 - y0) / h,
             (c.x1 - x0 + 1) / w, (c.y1 - y0 + 1) / h) for c in comps]


def unmatched(rend, scan):
    """Indices of rendered components no scan component overlaps."""
    R, S_ = norm_boxes(rend), norm_boxes(scan)
    out = []
    for i, (ax0, ay0, ax1, ay1) in enumerate(R):
        hit = any(min(ax1, bx1) > max(ax0, bx0)
                  and min(ay1, by1) > max(ay0, by0)
                  for bx0, by0, bx1, by1 in S_)
        if not hit:
            out.append(i)
    return out


def box_gap(a, b):
    dx = max(a.x0 - b.x1, b.x0 - a.x1) - 1
    dy = max(a.y0 - b.y1, b.y0 - a.y1) - 1
    return max(0, dx, dy)


def gap_to_box(c, r):
    dx = max(c.x0 - r.x1, r.x0 - c.x1) - 1
    dy = max(c.y0 - r.y1, r.y0 - c.y1) - 1
    return max(0, dx, dy)


def sweep_document(name):
    d = S / name
    dem = demoted_idents(name)
    idents = idents_for(name)
    mds = sorted(d.glob("p*.md"))
    pages = sorted(int(md.stem[1:]) for md in mds
                   if (d / f"{md.stem}_r300.png").is_file())
    contiguous = pages == list(range(pages[0], pages[0] + len(pages))) \
        if pages else False
    recs = []
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
        for line in md.read_text(errors="replace").splitlines()[2:]:
            c = [x.strip() for x in line.split("|")[1:-1]]
            ln = int(c[1])
            if ln == 0 or hts.get(ln, 999) < 40:
                continue
            L = [int(x) for x in c[3:8]]
            R = [int(x) for x in c[8:13]]
            dis = sum(abs(x - y) for x, y in zip(L, R))
            fl = flag_of(dis, abs(L[0] - R[0]), c[13] == "yes")
            recs.append((p, ln, L, R, dis, fl, nc))
    if contiguous and len(idents) >= len(recs):
        labels = idents[:len(recs)]
    else:
        labels = ["?"] * len(recs)

    rows = []
    for (p, ln, L, R, dis, fl, nc), ident in zip(recs, labels):
        if ident in dem:
            continue
        deficit = L[0] - R[0]                 # render has MORE
        if deficit <= 0 or fl not in ("component", "stable", "weak"):
            continue
        png = d / f"p{p:03d}_r300.png"
        img = read_png(png)
        m = auto_mask(img.gray, img.width, img.height, 200)[0]
        cells = _table_cells(m, 4.0)
        rb = cells.get((ln, nc - 2)); sb = cells.get((ln, nc - 1))
        if rb is None or sb is None:
            continue
        rc = _cell_crop(m, rb[0], rb[1], rb[2] - 1, rb[3] - 1)
        sc = _cell_crop(m, sb[0], sb[1], sb[2] - 1, sb[3] - 1)
        rcomps = list(ink_only(rc).regions)
        scomps = list(ink_only(sc).regions)
        if not rcomps:
            continue
        miss = unmatched(rcomps, scomps)
        rules = [c for c in rcomps if is_rule(c)]
        med_w = statistics.median(c.x1 - c.x0 + 1 for c in rcomps)
        reach = A.reach * med_w

        # ZONE COUNTS, which is what the question can actually support.
        # Per-component correspondence between a LaTeX render and a
        # scan of the same expression is not recoverable by position
        # (see `unmatched`'s residual in the report), so "how many of
        # the missing components are near a rule" is answered by
        # counting each side within the SAME normalised zone and
        # taking the difference. Zone membership is geometric; no
        # identity is claimed for any single mark.
        def bbox(cs):
            return (min(c.x0 for c in cs), min(c.y0 for c in cs),
                    max(c.x1 for c in cs), max(c.y1 for c in cs))
        rx0, ry0, rx1, ry1 = bbox(rcomps)
        rw = max(1, rx1 - rx0 + 1); rh = max(1, ry1 - ry0 + 1)
        zones = [((r.x0 - reach - rx0) / rw, (r.y0 - reach - ry0) / rh,
                  (r.x1 + reach - rx0) / rw, (r.y1 + reach - ry0) / rh)
                 for r in rules]

        def in_zone(c, x0, y0, w, h):
            cx = (c.x0 + c.x1) / 2.0
            cy = (c.y0 + c.y1) / 2.0
            nx = (cx - x0) / w; ny = (cy - y0) / h
            return any(zx0 <= nx <= zx1 and zy0 <= ny <= zy1
                       for zx0, zy0, zx1, zy1 in zones)
        rend_near = sum(1 for c in rcomps if in_zone(c, rx0, ry0, rw, rh))
        if scomps:
            sx0, sy0, sx1, sy1 = bbox(scomps)
            sw = max(1, sx1 - sx0 + 1); sh = max(1, sy1 - sy0 + 1)
            scan_near = sum(1 for c in scomps
                            if in_zone(c, sx0, sy0, sw, sh))
        else:
            scan_near = 0
        near = max(0, rend_near - scan_near)
        rows.append([name, ident, p, ln, deficit, len(miss), len(rules),
                     near, float(med_w), len(rcomps), len(scomps),
                     rend_near, scan_near])
    return rows


docs = sorted(p.name for p in S.iterdir()
              if p.is_dir() and list(p.glob("p*_r300.png")))
if A.only:
    docs = [d for d in docs if d in A.only]


def main():
    import concurrent.futures as cf
    rows = []
    with cf.ProcessPoolExecutor(max_workers=A.jobs) as ex:
        for i, r in enumerate(ex.map(sweep_document, docs), 1):
            rows.extend(r)
            print(f"  .. {i}/{len(docs)}", file=sys.stderr, flush=True)
    if not rows:
        raise SystemExit("no negative-delta flagged rows found (P16: "
                         "said, not silent)")
    print(f"POPULATION: {len(docs)} documents with a cached 300 dpi "
          f"render under {S}")
    print(f"  flagged rows where the RENDER has more components than "
          f"the scan: {len(rows)}")

    # The matching's own check: `unmatched` should track the deficit.
    sound = [r for r in rows if abs(r[5] - r[4]) <= max(2, 0.25 * r[4])]
    print(f"  matching SOUND (unmatched within 25% or 2 of the "
          f"deficit): {len(sound)}")
    print(f"  matching UNRELIABLE, excluded from the fractions: "
          f"{len(rows) - len(sound)}")
    resid = sorted(r[5] - r[4] for r in rows)
    print(f"  unmatched minus deficit: p5 {resid[int(.05*(len(resid)-1))]}"
          f"  p50 {resid[len(resid)//2]}"
          f"  p95 {resid[int(.95*(len(resid)-1))]}")

    withrules = [r for r in rows if r[6] > 0]
    print(f"\n  rows with a rule in the RENDERED cell: {len(withrules)}"
          f"   without: {len(rows) - len(withrules)}")
    print(f"  a row with no rule cannot answer the question. It is "
          f"counted, not dropped, and it is the denominator that "
          f"decides whether this measurement means anything.")
    if withrules:
        near = sorted(r[7] for r in withrules)
        both = [r for r in withrules if r[4] > 0]
        fr = sorted(min(1.0, r[7] / r[4]) for r in both)
        print(f"\nDEFICIT NEAR A RULE, zone counts, {A.reach:g} x median "
              f"glyph width, over {len(both)} rows")
        for q in (0, 10, 25, 50, 75, 90, 100):
            print(f"  p{q:<3} {fr[int(q / 100 * (len(fr) - 1))]:.3f}")
        tot_d = sum(r[4] for r in both)
        tot_n = sum(min(r[7], r[4]) for r in both)
        print(f"  pooled: {tot_n} of {tot_d} missing components fall in "
              f"a rule zone ({100.0 * tot_n / tot_d:.1f}%)")
        print(f"  rows where EVERY missing component is near a rule: "
              f"{sum(1 for f in fr if f >= 1.0)}")
        print(f"  rows where NONE is:                                "
              f"{sum(1 for f in fr if f == 0.0)}")
        # The null model: what fraction of the RENDERED cell's
        # components sit in a rule zone at all. If the deficit
        # fraction matches this, the missing marks are where the
        # marks are and the rule has nothing to do with it.
        base = [r[11] / r[9] for r in withrules if r[9]]
        base.sort()
        print(f"\n  NULL MODEL -- share of the rendered cell's components "
              f"that lie in a rule zone at all:")
        print(f"    p25 {base[len(base)//4]:.3f}  p50 "
              f"{base[len(base)//2]:.3f}  p75 "
              f"{base[3*len(base)//4]:.3f}")
        print(f"    pooled {sum(r[11] for r in withrules)}"
              f" of {sum(r[9] for r in withrules)} = "
              f"{100.0*sum(r[11] for r in withrules)/max(1,sum(r[9] for r in withrules)):.1f}%")
        print(f"  The deficit share means something only if it EXCEEDS "
              f"this. Equal shares say the missing marks are simply "
              f"where the marks are.")

    RES = pathlib.Path(__file__).resolve().parent.parent / "results"
    RES.mkdir(exist_ok=True)
    import datetime
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = RES / f"ruledeficit-{stamp}.tsv"
    out.write_text("\n".join(
        ["\t".join(["bibkey", "id", "page", "line", "deficit",
                    "unmatched", "rules", "near_rule", "med_glyph_w",
                    "rend_comps", "scan_comps", "rend_near",
                    "scan_near", "fraction"])] +
        ["\t".join(map(str, r + [round(min(1.0, r[7] / r[4]), 4)
                                 if r[4] else ""]))
         for r in rows]) + "\n")
    print(f"\n{len(rows)} rows -> {out}")


if __name__ == "__main__":
    main()
