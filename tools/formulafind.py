"""formulafind.py -- locate a rendered formula inside a line crop, in x.

MEASUREMENT HARNESS, not a unit. It answers one question: given column
5 of an evidence report (the expression as TeX renders it) and column 6
(the Mathpix crop of the line where it first occurs), WHERE along that
line does the expression sit, and how well does it fit?

The two rasters share nothing but the shapes. Column 5 is rendered here
and now, from Mathpix's LaTeX, by pdflatex at a dpi we choose. Column 6
is a crop of the ORIGINAL page, rasterised by Mathpix at its own scale
and then downscaled again for the report -- 0.5998 on the sample
measured, giving about 150 dpi and a 27 px line. So the scale relating
them is UNKNOWN and is searched for, not assumed.

WHY BLOBS AND NOT PIXELS. At 27 px a glyph is 8-10 px tall and its
counters are 1-2 px, which is the speckle floor out/591 measured. Hole
counts are not trustworthy there and are deliberately not used. What
survives a 4x scale change and a different rasteriser is the pattern of
INK AND GAP along x -- where the blobs are and where they are not --
so that is the whole signal here. Each mask is reduced to a binary
column profile built from the blob boxes, never from the pixels.

FIGURE OF MERIT is the 1-D Jaccard of those two profiles: the columns
where both say ink, over the columns where either does. It is 1.0 for a
perfect fit and drops when the expression is stretched, shifted or
absent. The RESIDUAL -- which columns disagree, and on which side -- is
reported beside it, because a single score would throw away the finding.

    python3 tools/formulafind.py --bibkey 0902.0431 --ids FO0001,FO0002
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from inkdrill.pnmio import load_mask                      # noqa: E402
from inkdrill.sweep import sweep                          # noqa: E402

STANDALONE = r"""\documentclass[border=0pt]{standalone}
\usepackage{amsmath}\usepackage{amssymb}\usepackage{bbm}
\usepackage{bm}\usepackage{mathtools}\usepackage{extarrows}\usepackage{cancel}
\usepackage{mathrsfs}\usepackage{stmaryrd}
\providecommand{\Perp}{\mathrel{\perp\!\!\!\perp}}
\providecommand{\overparen}[1]{\overset{\frown}{#1}}
\providecommand{\oiint}{\oint\!\!\!\oint}
\begin{document}$\displaystyle %s$\end{document}
"""

def line_index(library, bibkey):
    """page -> [(region, text)] from `lines.json`, in reading order.

    The regions are in MathPix page pixels. For 0902.0431 that raster
    is 2125 x 2750 for a 612 x 792 pt page -- exactly 250 dpi -- and
    the locally rendered page is 3400 x 4400, exactly 400 dpi, so the
    two differ by 1.6 with no rounding.
    """
    import json
    d = json.loads((library / bibkey / f"{bibkey}.lines.json").read_text())
    out = {}
    for pg in d["pages"]:
        out[pg["page"]] = [(l["region"], l.get("text") or "")
                           for l in pg.get("lines", [])]
    return out, d["pages"][0]["page_width"], d["pages"][0]["page_height"]


def fullres_crop(library, bibkey, page, region, ratio, out):
    """The line, cut from the LOCALLY RENDERED page. No resample, no JPEG.

    `report-crops-b` is a PUBLISHING artefact: the line region scaled to
    0.5998 and saved at JPEG q92. out/641 measured what that costs --
    the component count moves on 2 of 20 crops and the hole count on 4
    of 20, by as much as 4 -- so a residual report of sixteen rows must
    never be measured on it. There is no reason to measure on it
    either: the same line is available lossless.

    Cropped with `magick` rather than decoded in Python, so the 3400 x
    4400 page is never held in memory, and written straight to PGM,
    which is what `pnmio` reads.
    """
    src = library / bibkey / "inspect" / "pages" / f"p{page}.png"
    if not src.exists():
        return None
    x = int(round(region["top_left_x"] * ratio))
    y = int(round(region["top_left_y"] * ratio))
    w = int(round(region["width"] * ratio))
    h = int(round(region["height"] * ratio))
    subprocess.run(["magick", str(src), "-crop", f"{w}x{h}+{x}+{y}",
                    "+repage", "-colorspace", "Gray", "-depth", "8", str(out)],
                   capture_output=True, check=True)
    return out


def match_rows_to_lines(picked, index):
    """Row -> the line whose text contains it, assigned in reading order.

    The line text carries the maths delimited as `\\(...\\)`, so the row's
    own expression is a literal substring. Assignment walks each page
    FORWARD and never re-uses an earlier line, because an expression
    like `G` occurs on many lines of a page and the first match would
    put every one of them on line 1.
    """
    out, cursor = {}, {}
    for row in picked:
        pg = int(row["page"])
        lines = index.get(pg, [])
        start = cursor.get(pg, 0)
        needle = "\\(" + row["math"] + "\\)"
        hit = None
        for i in range(start, len(lines)):
            if needle in lines[i][1]:
                hit = i
                break
        if hit is None:                      # fall back to anywhere on the page
            for i in range(0, len(lines)):
                if needle in lines[i][1]:
                    hit = i
                    break
        if hit is not None:
            out[row["id"]] = lines[hit][0]
            cursor[pg] = hit
    return out


ROW_RX = re.compile(
    r"\\ident\{(?P<id>.*?)\}\s*&\s*(?P<page>\d+)\s*&\s*"
    r"\\confcell\{\w+\}\{(?P<conf>[\d.]+)\}\s*&.*?&\s*"
    r"\\FitMath\{\$\\displaystyle (?P<math>.*?)\$\}\s*&\s*"
    r".*?\\includegraphics\[width=[\d.]+mm\]\{(?P<crop>[^}]+)\}", re.S)


def rows(tex_path):
    body = tex_path.read_text(encoding="utf-8",
                              errors="replace").split(r"\endhead", 1)[1]
    for m in ROW_RX.finditer(body):
        d = m.groupdict()
        d["id"] = d["id"].replace(r"\allowbreak{}", "").replace("\\_", "_")
        yield d


def render(math, out, dpi):
    """The expression alone, no page, no margin beyond the glyphs."""
    with tempfile.TemporaryDirectory() as td:
        t = pathlib.Path(td)
        (t / "f.tex").write_text(STANDALONE % math, encoding="utf-8")
        subprocess.run(["pdflatex", "-interaction=nonstopmode",
                        "-halt-on-error", "f.tex"],
                       cwd=t, capture_output=True, text=True)
        if not (t / "f.pdf").exists():
            return False
        subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=pgmraw",
                        f"-r{dpi}", f"-sOutputFile={out}", str(t / "f.pdf")],
                       capture_output=True, check=True)
    return True


def to_pgm(src, out):
    subprocess.run(["magick", str(src), "-colorspace", "Gray", "-depth", "8",
                    str(out)], capture_output=True, check=True)


def blobs(pgm, dpi, threshold=200):
    """(x0, x1, y0, y1, area) per component, in raster order along x."""
    m = load_mask(str(pgm), dpi=dpi, threshold=threshold)
    r = sweep(m, conn=8, moments=True)
    b = sorted((mo.x0, mo.x1, mo.y0, mo.y1, mo.area)
               for mo in r.moments.values())
    return m, b


def profile(bs, width):
    """Binary ink/gap along x, built from the BLOB BOXES.

    Not from the pixels: a column inside a blob's box counts as ink even
    where that glyph happens to have a gap, which is what makes the
    signal survive a 4x scale change and a different rasteriser.
    """
    p = bytearray(width)
    for x0, x1, *_ in bs:
        for x in range(max(0, x0), min(width, x1 + 1)):
            p[x] = 1
    return p


def resample(p, n):
    """Nearest-neighbour to `n` columns. Nearest, not area-averaged,
    because the profile is binary and must stay binary."""
    if n <= 0:
        return bytearray()
    m = len(p)
    return bytearray(p[min(m - 1, i * m // n)] for i in range(n))


def jaccard(a, b, off):
    """|both| / |either| for `a` laid over `b` at column `off`."""
    inter = union = 0
    for i, v in enumerate(a):
        w = b[off + i] if 0 <= off + i < len(b) else 0
        if v and w:
            inter += 1
        if v or w:
            union += 1
    return (inter / union) if union else 0.0, inter, union


def trimmed(fb, fw):
    """The formula profile, cropped to its own ink (the render has a
    border, and the border is not part of the expression)."""
    fp = profile(fb, fw)
    lo = next((i for i, v in enumerate(fp) if v), 0)
    hi = len(fp) - next((i for i, v in enumerate(reversed(fp)) if v), 0)
    return fp[lo:hi]


def gaps_of(p):
    """Interior gaps in a binary profile. THE DISCRIMINATING POWER.

    A profile with no gap is a solid bar, and a bar of any width fits
    over any bar: `G` scored a perfect 1.000 at column 2 of a line it
    does not start, because a one-blob expression carries no
    information along x at all. The gap count is what makes a match
    mean something, so it is reported beside every score rather than
    left implicit in the blob count.
    """
    n = 0
    for i in range(1, len(p)):
        if p[i - 1] and not p[i]:
            n += 1
    return n


def scan(fp, cp, s):
    """Scores at every offset for one scale. Returns (n, [score, ...])."""
    n = round(len(fp) * s)
    if not 4 <= n <= len(cp):
        return 0, []
    q = resample(fp, n)
    return n, [jaccard(q, cp, off)[0] for off in range(len(cp) - n + 1)]


def locate(fb, fw, cb, cw, scales):
    """Best (score, scale, x0, x1) over the whole scale range."""
    fp, cp = trimmed(fb, fw), profile(cb, cw)
    best = (0.0, None, None, None)
    for s in scales:
        n, sc = scan(fp, cp, s)
        if not sc:
            continue
        i = max(range(len(sc)), key=sc.__getitem__)
        if sc[i] > best[0]:
            best = (sc[i], s, i, i + n - 1)
    return best


def locate_at(fb, fw, cb, cw, s):
    """Best position at ONE scale, with the margin over the best
    NON-OVERLAPPING alternative.

    The margin is the finding. A high score says the expression fits
    where it was put; a high score that a dozen other columns also
    achieve says the line is repetitive and the position is not
    established. Reporting only the score would throw that away.
    """
    fp, cp = trimmed(fb, fw), profile(cb, cw)
    n, sc = scan(fp, cp, s)
    if not sc:
        return None
    i = max(range(len(sc)), key=sc.__getitem__)
    rival = max((v for j, v in enumerate(sc) if abs(j - i) >= n), default=0.0)
    return sc[i], i, i + n - 1, sc[i] - rival, gaps_of(fp)


def vertical(cb, x0, x1):
    """The y-extent of the crop blobs whose CENTRE lies in [x0, x1]."""
    ys = [(b[2], b[3]) for b in cb if x0 <= (b[0] + b[1]) // 2 <= x1]
    if not ys:
        return None, None, 0
    return min(y[0] for y in ys), max(y[1] for y in ys), len(ys)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--library", type=pathlib.Path,
                    default=pathlib.Path.home() / "pdfdrill-library")
    ap.add_argument("--bibkey", default="0902.0431")
    ap.add_argument("--ids", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dpi", type=int, default=600)
    ap.add_argument("--smin", type=float, default=0.10)
    ap.add_argument("--smax", type=float, default=1.60)
    ap.add_argument("--sstep", type=float, default=0.005)
    ap.add_argument("--crops", choices=("report", "fullres"),
                    default="fullres",
                    help="report = the downsampled q92 JPEGs (a PUBLISHING "
                         "artefact, see out/641); fullres = the line cut "
                         "losslessly from inspect/pages at 400 dpi")
    ap.add_argument("--crop-dpi", type=float, default=0.0,
                    help="0 = infer: 400 for fullres, 150 for report")
    ap.add_argument("--min-gaps", type=int, default=2)
    ap.add_argument("--scale-min-gaps", type=int, default=6)
    ap.add_argument("--min-score", type=float, default=0.80)
    ap.add_argument("--min-margin", type=float, default=0.10)
    ap.add_argument("--json", type=pathlib.Path)
    args = ap.parse_args()

    doc = args.library / args.bibkey
    tex = doc / "evidence-formula.tex"
    want = {i.strip() for i in args.ids.split(",") if i.strip()}
    scales = [args.smin + i * args.sstep
              for i in range(int((args.smax - args.smin) / args.sstep) + 1)]

    picked = []
    for row in rows(tex):
        short = row["id"].split("_")[-1]
        if want and short not in want and row["id"] not in want:
            continue
        if (doc / row["crop"]).exists():
            picked.append(row)
        if args.limit and len(picked) >= args.limit:
            break

    fullres = args.crops == "fullres"
    crop_dpi = args.crop_dpi or (400.0 if fullres else 150.0)
    regions = ratio = None
    if fullres:
        index, raster_w, _ = line_index(args.library, args.bibkey)
        probe = doc / "inspect" / "pages" / "p1.png"
        pw = int(subprocess.run(["magick", "identify", "-format", "%w",
                                 str(probe)], capture_output=True,
                                text=True, check=True).stdout)
        ratio = pw / raster_w
        regions = match_rows_to_lines(picked, index)
        print(f"crops: LOSSLESS, cut from inspect/pages at {crop_dpi:g} dpi")
        print(f"  page raster {raster_w} px (MathPix) -> {pw} px (local), "
              f"ratio {ratio:g}")
        print(f"  {len(regions)} of {len(picked)} rows matched to a line\n")
    else:
        print(f"crops: report-crops-b, DOWNSAMPLED q92 "
              f"(a publishing artefact -- see out/641)\n")

    # The scale is PREDICTED from the two dpi, then checked against the
    # vote rather than assumed. Searching a wide range invites the
    # collapse to the floor that out/640 had to retract a rule over.
    expect = crop_dpi / args.dpi
    scales = [s for s in scales if 0.6 * expect <= s <= 1.5 * expect] or scales

    prepared, out = [], []
    with tempfile.TemporaryDirectory() as td:
        t = pathlib.Path(td)
        for row in picked:
            if fullres:
                reg = regions.get(row["id"])
                if reg is None or not fullres_crop(args.library, args.bibkey,
                                                   int(row["page"]), reg,
                                                   ratio, t / "c.pgm"):
                    print(f"{row['id'].split('_')[-1]:<8} NO LINE MATCH")
                    continue
            else:
                to_pgm(doc / row["crop"], t / "c.pgm")
            if not render(row["math"], t / "f.pgm", args.dpi):
                print(f"{row['id'].split('_')[-1]:<8} RENDER FAILED  "
                      f"{row['math'][:50]}")
                continue
            fm, fb = blobs(t / "f.pgm", float(args.dpi))
            cm, cb = blobs(t / "c.pgm", crop_dpi)
            prepared.append((row, fm.width, fb, cm, cb))

        # ---- PASS 1: the document's scale, from the rows that can
        # establish one. The crop scale is a property of how the REPORT
        # was built -- one downscale applied to every line -- not of the
        # row, so it is estimated once from the rows carrying enough
        # gaps to place unambiguously, and then imposed on all of them.
        # Estimating it per row is what let `G` pick 0.100.
        votes = []
        for row, fw, fb, cm, cb in prepared:
            # A HIGHER BAR THAN THE ACCEPTANCE ONE, ON PURPOSE. The
            # first version of this voted with `--min-gaps`, and the
            # vote landed on 0.165 instead of 0.250 because expressions
            # of one or two blobs match degenerately at ANY small scale
            # and there are many more of them than there are long ones.
            # A row may only vote if it could not have matched by
            # accident.
            if gaps_of(trimmed(fb, fw)) >= args.scale_min_gaps:
                sc, s, _, _ = locate(fb, fw, cb, cm.width, scales)
                if s and sc >= args.min_score:
                    votes.append(round(s, 4))
        if votes:
            votes.sort()
            scale = votes[len(votes) // 2]
        else:
            scale = None
        import collections
        spread = collections.Counter(votes)
        print(f"predicted scale {expect:.4g} = {crop_dpi:g}/{args.dpi} dpi")
        print(f"document scale: {scale}  (median of {len(votes)} rows with "
              f">= {args.scale_min_gaps} gaps and score >= {args.min_score})")
        print(f"  vote spread: "
              f"{dict(sorted(spread.items())[:8])}"
              f"{' ...' if len(spread) > 8 else ''}\n")
        if scale is None:
            print("no row could establish a scale; nothing to impose")
            return 1

        print(f"{'id':<8} {'score':>6} {'margin':>7} {'gaps':>5} "
              f"{'rect x':>12} {'y':>8} {'blobs':>10}  expression")
        for row, fw, fb, cm, cb in prepared:
            got = locate_at(fb, fw, cb, cm.width, scale)
            if got is None:
                continue
            sc, x0, x1, margin, gaps = got
            y0, y1, nin = vertical(cb, x0, x1)
            own_sc, own_scale, _, _ = locate(fb, fw, cb, cm.width, scales)
            cut = [b for b in cb
                   if b[0] < x0 <= b[1] or b[0] <= x1 < b[1]]
            ok = (sc >= args.min_score and margin >= args.min_margin
                  and gaps >= args.min_gaps)
            rec = dict(id=row["id"], page=int(row["page"]),
                       conf=float(row["conf"]), math=row["math"],
                       crop_w=cm.width, crop_h=cm.height, scale=scale,
                       formula_blobs=len(fb), crop_blobs=len(cb), gaps=gaps,
                       score=round(sc, 4), margin=round(margin, 4),
                       rect=[x0, y0, x1, y1], blobs_in_rect=nin,
                       own_scale=own_scale, own_score=round(own_sc, 4),
                       edge_cuts=len(cut), crop=row["crop"],
                       accepted=ok)
            out.append(rec)
            print(f"{row['id'].split('_')[-1]:<8} {sc:>6.3f} {margin:>7.3f} "
                  f"{gaps:>5} {f'{x0}-{x1}':>12} {f'{y0}-{y1}':>8} "
                  f"{f'{len(fb)}->{nin}':>10}  {'' if ok else 'REJECT '}"
                  f"{row['math'][:34]}")

    if out:
        acc = [r for r in out if r["accepted"]]
        print(f"\n{len(acc)} of {len(out)} accepted "
              f"({100*len(acc)/len(out):.1f}%)")
        for why, n in (("score below %.2f" % args.min_score,
                        sum(1 for r in out if r["score"] < args.min_score)),
                       ("margin below %.2f" % args.min_margin,
                        sum(1 for r in out if r["margin"] < args.min_margin)),
                       ("fewer than %d gaps" % args.min_gaps,
                        sum(1 for r in out if r["gaps"] < args.min_gaps))):
            print(f"   rejected -- {why:<22} {n}")
    if args.json:
        args.json.write_text(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
