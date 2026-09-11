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
import collections
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

    The regions are in MathPix page pixels, the page's CropBox frame.
    `page_frames` carries them onto the local page image.
    """
    import json
    d = json.loads((library / bibkey / f"{bibkey}.lines.json").read_text())
    out = {}
    for pg in d["pages"]:
        out[pg["page"]] = [(l["region"], l.get("text") or "")
                           for l in pg.get("lines", [])]
    return out, d["pages"][0]["page_width"], d["pages"][0]["page_height"]


def _png_size(path):
    """(width, height) from the IHDR chunk -- 24 bytes, no decode."""
    import struct
    with open(path, "rb") as fh:
        head = fh.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", head[16:24])


def page_frames(library, bibkey):
    """page -> (sx, sy, ox, oy): a MathPix page pixel (x, y) is the
    inspect/pages pixel (ox + x*sx, oy + y*sy). Plus {page: reason} for
    every page it REFUSES to map.

    TWO FRAMES, NOT ONE SCALE. MathPix's page image is the PDF's
    CROPBOX (pdfdrill measured it, its 654). `inspect/pages/p{N}.png` is
    rendered from the MEDIABOX. On the 17 documents whose CropBox equals
    their MediaBox the two differ by a scale; on the four that do not --
    cardona, voloshin, gilmore and kohlhase-omdoc -- they differ by an
    inset as well. The first version read ONE ratio off page 1's WIDTH
    and applied it to x and y on every page, which is right only on the
    17. Measured on published crops it cut the wrong strip of page
    everywhere else: correlation with the published crop -0.014
    (cardona) and +0.034 (voloshin), against +0.916 and +0.950 once the
    inset is applied. Gilmore's page 1 is an 816 px cover, so the ratio
    read there was wrong for the whole book.

    x and y scale INDEPENDENTLY, as pdfdrill's `mathpix_to_raster` does:
    MathPix rounds its own page dimensions, so a shared factor drifts
    down the page.

    Refused, never defaulted: a page with no MathPix dimensions, no page
    image, no source PDF, a rotation, or a page image that is not the
    MediaBox at a whole dpi. Cutting a crop from the wrong strip is worse
    than not cutting it -- it still looks like a line.
    """
    import json
    doc = library / bibkey
    lj = json.loads((doc / f"{bibkey}.lines.json").read_text())
    pdf = doc / f"{doc.name}.pdf"
    frames, refused = {}, {}
    pages = [pg for pg in lj["pages"]]
    if not pdf.exists():
        return frames, {pg["page"]: "no source pdf" for pg in pages}
    last = max(pg["page"] for pg in pages)
    info = subprocess.run(["pdfinfo", "-box", "-f", "1", "-l", str(last),
                           str(pdf)], capture_output=True, text=True,
                          errors="replace").stdout
    box = collections.defaultdict(dict)
    for m in re.finditer(r"^Page\s+(\d+)\s+(MediaBox|CropBox|rot):\s+(.*)$",
                         info, re.M):
        box[int(m.group(1))][m.group(2)] = m.group(3).split()
    for pg in pages:
        n, mw, mh = pg["page"], pg.get("page_width"), pg.get("page_height")
        png = doc / "inspect" / "pages" / f"p{n}.png"
        b = box.get(n, {})
        wh = _png_size(png) if png.exists() else None
        if not mw or not mh:
            refused[n] = "no MathPix page dimensions"; continue
        if wh is None:
            refused[n] = "no page image"; continue
        if "MediaBox" not in b:
            refused[n] = "no MediaBox"; continue
        if b.get("rot", ["0"])[0] not in ("0", "360"):
            refused[n] = f"rotated {b['rot'][0]}"; continue
        f = frame_of([float(v) for v in b["MediaBox"]],
                     [float(v) for v in b.get("CropBox", b["MediaBox"])],
                     wh[0], wh[1], mw, mh)
        if f is None:
            refused[n] = f"page image is not the MediaBox ({wh[0]}x{wh[1]})"
            continue
        frames[n] = f
    return frames, refused


def frame_of(media, crop, W, H, mw, mh):
    """The arithmetic of `page_frames`, with no file and no pdfinfo.

    `media`, `crop`: PDF boxes [x0, y0, x1, y1] in points, y UP.
    `W x H`: the page image, rendered from the MediaBox, y DOWN.
    `mw x mh`: MathPix's page image, which is the CropBox.
    Returns (sx, sy, ox, oy), or None when the page image is not the
    MediaBox at one dpi in both axes.
    """
    mx0, my0, mx1, my1 = media
    cx0, cy0, cx1, cy1 = crop
    # the CropBox is clipped to the MediaBox (PDF 32000 14.11.2)
    cx0, cy0 = max(cx0, mx0), max(cy0, my0)
    cx1, cy1 = min(cx1, mx1), min(cy1, my1)
    kx, ky = W / (mx1 - mx0), H / (my1 - my0)
    if abs(kx - ky) * 72 > 1.0:
        return None
    return ((cx1 - cx0) / mw * kx, (cy1 - cy0) / mh * ky,
            (cx0 - mx0) * kx, (my1 - cy1) * ky)


def fullres_crop(library, bibkey, page, region, frame, out):
    """The line, cut from the LOCALLY RENDERED page. No resample, no JPEG.

    `frame` is this page's `page_frames` entry -- never a ratio shared
    across pages or axes.

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
    if not src.exists() or frame is None:
        return None
    x, y, w, h = frame_rect(region, frame)
    subprocess.run(["magick", str(src), "-crop", f"{w}x{h}+{x}+{y}",
                    "+repage", "-colorspace", "Gray", "-depth", "8", str(out)],
                   capture_output=True, check=True)
    return out


def frame_rect(region, frame):
    """A MathPix region -> (x, y, w, h) in page-image pixels."""
    sx, sy, ox, oy = frame
    x0 = ox + region["top_left_x"] * sx
    y0 = oy + region["top_left_y"] * sy
    x1 = ox + (region["top_left_x"] + region["width"]) * sx
    y1 = oy + (region["top_left_y"] + region["height"]) * sy
    return (int(round(x0)), int(round(y0)),
            max(1, int(round(x1)) - int(round(x0))),
            max(1, int(round(y1)) - int(round(y0))))


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
            out[row["id"]] = (pg, lines[hit][0])
            cursor[pg] = hit
    return out


#: pdfdrill's inline-span delimiters, verbatim from `inlinectx.INLINE`:
#: `$...$` or `\( ... \)`, a `\$` being an escaped dollar.
INLINE = re.compile(r"(?<!\\)\$(?!\$)(.+?)(?<!\\)\$|\\\((.+?)\\\)", re.S)


def first_occurrence_lines(library, bibkey):
    """latex -> (page, region) of its FIRST inline span in document order.

    THIS IS PDFDRILL'S HOST-LINE RULE, reproduced so a rectangle drawn
    here lands on the line pdfdrill cropped: `inlinectx.load_spans` then
    `first_occurrences` (their 535). The model holds one Formula per
    DISTINCT value, so a row is the value's first span -- page order,
    then line order, then span order -- found by EQUALITY of the span
    body, never by containment. `math` lines are display maths and are
    skipped. Pages are numbered by POSITION in `lines.json`, as pdfdrill
    numbers them.

    A mark measured on any other line cannot be drawn on pdfdrill's
    crop, so `formulamarks` refuses a row whose region differs from the
    host region pdfdrill reports.
    """
    import json
    lj = json.loads((library / bibkey / f"{bibkey}.lines.json").read_text(
        encoding="utf-8", errors="replace"))
    first = {}
    for page, pg in enumerate(lj.get("pages") or [], 1):
        for ln in pg.get("lines") or []:
            if ln.get("type") == "math":
                continue
            for m in INLINE.finditer(ln.get("text") or ""):
                body = (m.group(1) or m.group(2) or "").strip()
                if body:
                    first.setdefault(body, (page, ln.get("region") or {}))
    return first


def match_rows_first(picked, first):
    """Row -> (host page, region) by pdfdrill's rule; see
    `first_occurrence_lines`. The row's own page column is NOT used."""
    return {r["id"]: first[r["math"].strip()] for r in picked
            if r.get("math") and r["math"].strip() in first}


def host_regions(library, bibkey, picked, rule="first"):
    """The one switch between the two matchers. `first` is pdfdrill's
    rule and the default: it is the line the published crop shows."""
    if rule == "first":
        return match_rows_first(picked, first_occurrence_lines(library, bibkey))
    index, _, _ = line_index(library, bibkey)
    return match_rows_to_lines(picked, index)


def _group(s, i):
    """The content of the `{...}` starting at s[i], nesting respected and
    `\\{` / `\\}` skipped as the literal braces they are."""
    if i >= len(s) or s[i] != "{":
        return None, i
    d, j = 0, i
    while j < len(s):
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == "{":
            d += 1
        elif c == "}":
            d -= 1
            if d == 0:
                return s[i + 1:j], j + 1
        j += 1
    return None, i


def rows(tex_path):
    """One record per evidence row, parsed ROW BY ROW -- never across rows.

    The first version matched the whole table body with one lazy regex
    that demanded every cell, so wherever a row lacked one it matched ON
    INTO THE NEXT ROW. Two ways, both silent:

      * A row with no published crop (`---` in the image column) took the
        NEXT row's picture and swallowed that row. In 0902.0431 FO0064
        was paired with FO0065's image and FO0065 vanished -- seven rows
        lost that way, and five of the "published crops of the wrong
        size" reported on 2026-09-11 were this pairing, not pdfdrill.
      * pdfdrill now writes `\\lowconf{...}` inside the id cell, and the
        lazy id absorbed it: 35 ids in 1510.06699 read
        `...FO0984}\\lowconf{0.000`.

    Every `\\ident` now yields exactly one record. A missing cell is
    `None` rather than a reason to borrow the neighbour's: `crop` is None
    for a row with no published image, `conf` is None where the producer
    gave none, `math` is None where there is no `\\FitMath`. A caller
    decides what a missing cell means for it; this function never does.
    """
    body = tex_path.read_text(encoding="utf-8",
                              errors="replace").split(r"\endhead", 1)[-1]
    # A row runs from one `\ident` to the next. Splitting on the row
    # terminator `\\ \hline` instead cut rows in half wherever the MATHS
    # held one -- an `array` with `\hline` rules (johnston FO2040, FO2066)
    # -- and lost both the math and the crop of that row.
    starts = [m.start() for m in re.finditer(r"\\ident\{", body)] + [len(body)]
    for a, b in zip(starts, starts[1:]):
        chunk = body[a:b]
        i = 0
        ident, j = _group(chunk, i + len(r"\ident"))
        if ident is None:
            continue
        rest = chunk[j:]
        m = re.match(r"\s*(?:\\lowconf\{[^}]*\})?\s*&\s*(\d+)\s*&", rest)
        conf = re.search(r"\\confcell\{\w+\}\{([\d.]+)\}", rest)
        math = None
        k = rest.find(r"\FitMath{")
        if k >= 0:
            g, _ = _group(rest, k + len(r"\FitMath"))
            if g is not None:
                mm = re.match(r"\$\\displaystyle (.*)\$\Z", g, re.S)
                math = mm.group(1) if mm else g.strip().strip("$")
        c = re.search(r"\\includegraphics\[[^\]]*\]\{([^}]+)\}", rest)
        yield dict(id=ident.replace(r"\allowbreak{}", "").replace("\\_", "_").strip(),
                   page=m.group(1) if m else None,
                   conf=conf.group(1) if conf else None,
                   math=math,
                   crop=c.group(1) if c else None,
                   lowconf=r"\lowconf{" in rest[:60])

def render(math, out, dpi):
    """The expression alone, no page, no margin beyond the glyphs."""
    with tempfile.TemporaryDirectory() as td:
        t = pathlib.Path(td)
        (t / "f.tex").write_text(STANDALONE % math, encoding="utf-8")
        subprocess.run(["pdflatex", "-interaction=nonstopmode",
                        "-halt-on-error", "f.tex"],
                       cwd=t, capture_output=True, text=True,
                       errors="replace")   # pdflatex echoes the input's bytes:
                                           # mielke's 0xa3 crashed a whole vote
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


def bits(p):
    """A binary profile as ONE integer, column i in bit i.

    The score is a 1-D Jaccard, and both terms are popcounts of AND and
    OR. As bytes-per-column that is a Python loop over every column at
    every offset at every scale; as a big integer it is two shifts, two
    bitwise ops and two `bit_count()` calls, all in C. Same arithmetic,
    and `test_bits_matches_the_column_loop` in the harness holds them
    equal -- an optimisation that changes the answer is a bug, and this
    one is on the path a per-row refit multiplies by a hundred.
    """
    v = 0
    for i, x in enumerate(p):
        if x:
            v |= 1 << i
    return v


def scan(fp, cp, s):
    """Scores at every offset for one scale. Returns (n, [score, ...])."""
    n = round(len(fp) * s)
    if not 4 <= n <= len(cp):
        return 0, []
    q = bits(resample(fp, n))
    line = bits(cp)
    window = (1 << n) - 1
    out = []
    for off in range(len(cp) - n + 1):
        t = q << off
        lw = line & (window << off)
        u = (t | lw).bit_count()
        out.append(((t & lw).bit_count() / u) if u else 0.0)
    return n, out


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


def locate_refit(fb, fw, cb, cw, scale, band, step):
    """Best fit with the scale REFITTED for this row.

    One scale per document is right for the document and wrong for a
    long expression: out/644 measured the per-row spread at about
    +/-5%, and a 0.5% error over a 1,500 px expression is 7 px, which
    is a glyph. Refitting recovered FO0237 (260 px out) and FO0200 (a
    missing Fraktur C) outright.

    The band is CONSTRAINED and the constraint is REPORTED. A free
    scale search collapses to the floor of its range -- that is what
    out/640 had to retract a rule over -- and the tell is a refined
    scale sitting on the boundary. The caller counts those.
    """
    fp, cp = trimmed(fb, fw), profile(cb, cw)
    steps = int(round(2 * band / step))
    best = None
    for k in range(steps + 1):
        s = scale * (1 - band + k * step)
        n, sc = scan(fp, cp, s)
        if not sc:
            continue
        i = max(range(len(sc)), key=sc.__getitem__)
        if best is None or sc[i] > best[0]:
            best = (sc[i], i, n, s, sc)
    if best is None:
        return None
    top, i, n, s, sc = best
    rival = max((v for j, v in enumerate(sc) if abs(j - i) >= n), default=0.0)
    on_edge = abs(s / scale - (1 - band)) < 1e-9 or \
        abs(s / scale - (1 + band)) < 1e-9
    return top, i, i + n - 1, top - rival, gaps_of(fp), s, on_edge


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
    ap.add_argument("--scale", type=float, default=0.0,
                    help="impose this document scale instead of voting for "
                         "it; required when sharding, so every shard uses "
                         "the SAME scale and the results stay comparable")
    ap.add_argument("--shard", default="",
                    help="I/N -- take contiguous block I of N. Contiguous, "
                         "not modulo, so rows sharing a line stay in one "
                         "shard and the crop cache still hits.")
    ap.add_argument("--refit", action=argparse.BooleanOptionalAction,
                    default=True,
                    help="refit the scale per row within a band around the "
                         "document scale (out/644)")
    ap.add_argument("--host", choices=("first", "cursor"), default="first",
                    help="first: pdfdrill's host line (first span in document "
                         "order); cursor: the row's page, walked forward")
    ap.add_argument("--refit-band", type=float, default=0.12)
    ap.add_argument("--refit-step", type=float, default=0.002)
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

    picked, dropped = [], collections.Counter()
    for row in rows(tex):
        short = row["id"].split("_")[-1]
        if want and short not in want and row["id"] not in want:
            continue
        # A FILTER IS A DECISION, so what it drops is counted and printed.
        # Fullres mode cuts its own crop from the page, so a row with no
        # PUBLISHED image is still measurable; only report mode needs one.
        if row["page"] is None:
            dropped["no page"] += 1; continue
        if row["math"] is None:
            dropped["no rendered LaTeX"] += 1; continue
        if args.crops == "report" and not (row["crop"] and (doc / row["crop"]).exists()):
            dropped["no published crop"] += 1; continue
        picked.append(row)
        if args.limit and len(picked) >= args.limit:
            break
    if dropped:
        print(f"rows not measured: {dict(dropped)}")

    if args.shard:
        i, n = (int(x) for x in args.shard.split("/"))
        per = (len(picked) + n - 1) // n
        picked = picked[i * per:(i + 1) * per]
        print(f"shard {i}/{n}: rows {i*per}..{i*per+len(picked)-1}")
        if not args.scale:
            raise SystemExit("--shard needs --scale: a per-shard vote would "
                             "give each shard a different document scale")

    fullres = args.crops == "fullres"
    crop_dpi = args.crop_dpi or (400.0 if fullres else 150.0)
    regions = frames = None
    if fullres:
        frames, refused = page_frames(args.library, args.bibkey)
        regions = host_regions(args.library, args.bibkey, picked, args.host)
        inset = sum(1 for f in frames.values() if f[2] > 0.5 or f[3] > 0.5)
        print(f"crops: LOSSLESS, cut from inspect/pages at {crop_dpi:g} dpi")
        print(f"  {len(frames)} page frames (MathPix CropBox -> MediaBox "
              f"render), {inset} with a CropBox inset; {len(refused)} pages "
              f"refused: {dict(collections.Counter(refused.values()))}")
        print(f"  {len(regions)} of {len(picked)} rows matched to a line "
              f"(host rule: {args.host})\n")
    else:
        print(f"crops: report-crops-b, DOWNSAMPLED q92 "
              f"(a publishing artefact -- see out/641)\n")

    # The scale is PREDICTED from the two dpi, then checked against the
    # vote rather than assumed. Searching a wide range invites the
    # collapse to the floor that out/640 had to retract a rule over.
    expect = crop_dpi / args.dpi
    scales = [s for s in scales if 0.6 * expect <= s <= 1.5 * expect] or scales

    prepared, out, crop_cache = [], [], {}
    with tempfile.TemporaryDirectory() as td:
        t = pathlib.Path(td)
        for row in picked:
            if fullres:
                hit = regions.get(row["id"])
                if hit is None:
                    print(f"{row['id'].split('_')[-1]:<8} NO LINE MATCH")
                    continue
                hp, reg = hit
                row["_host"] = (hp, reg, frames.get(hp))
                # 2,067 distinct lines carry 3,163 rows, so a third of
                # the crops are re-cutting a line already cut.
                key = (hp, tuple(sorted(reg.items())))
                if key not in crop_cache:
                    if not fullres_crop(args.library, args.bibkey,
                                        hp, reg, frames.get(hp),
                                        t / f"c{len(crop_cache)}.pgm"):
                        print(f"{row['id'].split('_')[-1]:<8} NO LINE MATCH")
                        continue
                    crop_cache[key] = t / f"c{len(crop_cache)}.pgm"
                crop_path = crop_cache[key]
            else:
                to_pgm(doc / row["crop"], t / "c.pgm")
                crop_path = t / "c.pgm"
            if not render(row["math"], t / "f.pgm", args.dpi):
                print(f"{row['id'].split('_')[-1]:<8} RENDER FAILED  "
                      f"{row['math'][:50]}")
                continue
            fm, fb = blobs(t / "f.pgm", float(args.dpi))
            cm, cb = blobs(crop_path, crop_dpi)
            prepared.append((row, fm.width, fb, cm, cb))

        # ---- PASS 1: the document's scale, from the rows that can
        # establish one. The crop scale is a property of how the REPORT
        # was built -- one downscale applied to every line -- not of the
        # row, so it is estimated once from the rows carrying enough
        # gaps to place unambiguously, and then imposed on all of them.
        # Estimating it per row is what let `G` pick 0.100.
        votes = []
        for row, fw, fb, cm, cb in ([] if args.scale else prepared):
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
        if args.scale:
            scale = args.scale
        elif votes:
            votes.sort()
            scale = votes[len(votes) // 2]
        else:
            scale = None
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
        edge_hits = 0
        for row, fw, fb, cm, cb in prepared:
            if args.refit:
                got = locate_refit(fb, fw, cb, cm.width, scale,
                                   args.refit_band, args.refit_step)
                if got is None:
                    continue
                sc, x0, x1, margin, gaps, own_scale, on_edge = got
                edge_hits += on_edge
                own_sc = sc
            else:
                got = locate_at(fb, fw, cb, cm.width, scale)
                if got is None:
                    continue
                sc, x0, x1, margin, gaps = got
                own_sc, own_scale, _, _ = locate(fb, fw, cb, cm.width, scales)
                on_edge = False
            y0, y1, nin = vertical(cb, x0, x1)
            cut = [b for b in cb
                   if b[0] < x0 <= b[1] or b[0] <= x1 < b[1]]
            ok = (sc >= args.min_score and margin >= args.min_margin
                  and gaps >= args.min_gaps)
            rec = dict(id=row["id"], page=int(row["page"]),
                       conf=(float(row["conf"]) if row["conf"] is not None
                             else None), math=row["math"],
                       crop_w=cm.width, crop_h=cm.height, scale=scale,
                       formula_blobs=len(fb), crop_blobs=len(cb), gaps=gaps,
                       score=round(sc, 4), margin=round(margin, 4),
                       rect=[x0, y0, x1, y1], blobs_in_rect=nin,
                       own_scale=own_scale, own_score=round(own_sc, 4),
                       edge_cuts=len(cut), crop=row["crop"],
                       refit=bool(args.refit), on_edge=bool(on_edge),
                       accepted=ok)
            if row.get("_host"):
                # WHERE the crop was cut, so a consumer can map `rect`
                # back onto its own picture of the same line: host page,
                # MathPix region, and the page frame used.
                rec.update(host_page=row["_host"][0], region=row["_host"][1],
                           frame=row["_host"][2], host_rule=args.host)
            out.append(rec)
            print(f"{row['id'].split('_')[-1]:<8} {sc:>6.3f} {margin:>7.3f} "
                  f"{gaps:>5} {f'{x0}-{x1}':>12} {f'{y0}-{y1}':>8} "
                  f"{f'{len(fb)}->{nin}':>10}  {'' if ok else 'REJECT '}"
                  f"{row['math'][:34]}")

    if out and args.refit:
        r = [x["own_scale"] / scale for x in out if x.get("own_scale")]
        r.sort()
        print(f"\nREFIT: per-row scale / document scale -- "
              f"min {r[0]:.3f}  p25 {r[len(r)//4]:.3f}  median "
              f"{r[len(r)//2]:.3f}  p75 {r[3*len(r)//4]:.3f}  max {r[-1]:.3f}")
        # COUNTED AMONG PLACED ROWS, which is the number that matters.
        # Reported over all rows it read 54 of 260 and looked alarming;
        # every one of those was a row the gap rule had already thrown
        # out -- 48 of them at the LOW edge with a median of ZERO gaps,
        # which is a one-blob template shrinking until it fits
        # anywhere. The degeneracy is real and lands entirely on rows
        # that carry no position to begin with.
        pl = [x for x in out if x["accepted"]]
        pe = sum(1 for x in pl if x.get("on_edge"))
        print(f"  band edge: {pe} of {len(pl)} PLACED rows "
              f"(+/-{args.refit_band:.0%}) -- this is the number that "
              f"matters; {edge_hits} of {len(out)} over all rows, the rest "
              f"being unplaceable templates shrinking to fit")
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
