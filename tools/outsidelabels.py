"""Equations carrying LABELS outside their delimiters (203).

200 measured one: a 4x4 flavour matrix whose region also contains
`up`, `down`, `strange`, `charm`, `flavors`, `red`, `yellow`, `blue`
and `lilac` -- prose, sitting outside the bracket pair and inside the
region MathPix called `math`. A consumer treating that region as an
expression gets the labels as part of the maths.

THE DETECTOR, built from that page's geometry and nothing else:

  1 the region's components, from the source page raster;
  2 the OUTERMOST DELIMITER PAIR -- leftmost and rightmost components
    that `emit.is_delimiter` accepts (a thin full-height stem with a
    full-width serif at each end and none in between);
  3 components lying entirely outside that pair -- left of the left
    one, right of the right one, or below their common bottom -- and
    inside the region;
  4 those grouped into text rows by `mathstruct.rows`.

An equation QUALIFIES when it has a delimiter pair and at least one
outside row. No delimiter pair means nothing to be outside of, and
that is reported separately rather than as a zero.

WHAT IS NOT CLAIMED: that the outside rows are words. This project
reads no text and has no word former -- `group()` joins stacked
components, an `i` with its dot, never adjacent letters. The unit is
the ROW, and a count of labels would be the LaTeX's number, not the
ink's.

Usage: python3 tools/outsidelabels.py [--books B ...] [--jobs N]
"""
import argparse, collections, json, pathlib, subprocess, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from inkdrill.pngio import read_png, auto_mask                  # noqa
from inkdrill.raster import InkMask                             # noqa
from inkdrill.nest import ink_only                              # noqa
from inkdrill.emit import is_delimiter                          # noqa
from inkdrill.mathstruct import Glyph, rows                     # noqa

BOOKS = ["BH1org_OCR", "bh2", "BH3FR", "WDorg4",
         "Geometrodynamics of Gauge Fields On the Geometry of "
         "Yang-Mills and Gravitational Gauge Theories "
         "(Eckehard W. Mielke) (Z-Library)"]

ap = argparse.ArgumentParser(prog="tools/outsidelabels.py",
                             description=__doc__.strip().splitlines()[0])
ap.add_argument("--library", default="~/pdfdrill-library")
ap.add_argument("--books", nargs="*", default=None)
ap.add_argument("--dpi", type=int, default=300)
ap.add_argument("--jobs", type=int, default=6)
ap.add_argument("--cache", default=None)
A = ap.parse_args()
LIB = pathlib.Path(A.library).expanduser()
CACHE = pathlib.Path(A.cache or (tempfile.gettempdir() + "/inkdrill-203"))
CACHE.mkdir(parents=True, exist_ok=True)


def source_pdf(d):
    """The document's own pdf, never its report."""
    cands = sorted(p for p in d.glob("*.pdf") if p.name != "report.pdf")
    return cands[0] if cands else None


def lines_json(d):
    c = [p for p in sorted(d.glob("*.lines.json"))
         if "pdfminer" not in p.name]
    return c[0] if c else None


def render(pdf, page, out):
    if out.is_file():
        return True
    r = subprocess.run(
        ["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=png16m",
         f"-r{A.dpi}", f"-dFirstPage={page}", f"-dLastPage={page}",
         f"-sOutputFile={out}", str(pdf)], capture_output=True)
    return r.returncode == 0 and out.is_file()


def analyse(mask, x0, y0, x1, y1):
    """(qualifies, n_outside_components, n_outside_rows, n_delims)."""
    w, h = x1 - x0, y1 - y0
    if w < 10 or h < 10:
        return None
    buf = bytearray(w * h)
    for yy in range(h):
        s = (y0 + yy) * mask.width + x0
        buf[yy * w:(yy + 1) * w] = mask.data[s:s + w]
    crop = InkMask(bytes(buf), w, h)
    regs = list(ink_only(crop).regions)
    if not regs:
        return None
    delims = [r for r in regs if is_delimiter(crop, r)]
    if len(delims) < 2:
        return (False, 0, 0, len(delims), 0)
    delims.sort(key=lambda r: r.x0)
    L, R = delims[0], delims[-1]
    bottom = max(L.y1, R.y1)
    # RIGHT of the pair or BELOW it -- NOT left of it. The first
    # version included `r.x1 < L.x0` and every equation with a
    # delimiter pair then qualified: 156 of 156, with
    # "delimited, nothing outside" at exactly ZERO. An empty class in
    # a two-class comparison built to make that comparison is the
    # first thing to check, and the cause was immediate -- everything
    # left of the opening bracket is the equation's LEFT-HAND SIDE.
    # On the case this detector was built from, `\psi =` sits there.
    # A left-hand side is part of the expression, not a label.
    #
    # 200's measurement used right-and-below and this now matches it
    # exactly. The left-hand side is counted separately so the class
    # is named rather than silently dropped.
    left = [r for r in regs if r.x1 < L.x0]
    out = [r for r in regs if r.x0 > R.x1 or r.y0 > bottom]
    if not out:
        return (False, 0, 0, len(delims), len(left))
    gl = [Glyph(i, float(r.x0), float(r.y0), float(r.x1 + 1),
                float(r.y1 + 1)) for i, r in enumerate(out)]
    return (True, len(out), len(rows(gl)), len(delims), len(left))


def one_book(name):
    d = LIB / name
    pdf, lj = source_pdf(d), lines_json(d)
    if pdf is None or lj is None:
        return name, None
    j = json.loads(lj.read_text(errors="replace"))
    by_page = collections.defaultdict(list)
    for p in j["pages"]:
        for l in p.get("lines", []):
            if l.get("type") == "math" and l.get("region"):
                by_page[p["page"]].append(
                    (l["region"], p["page_width"], p["page_height"]))
    stat = collections.Counter()
    detail = []
    sub = CACHE / name.replace("/", "_")[:60]
    sub.mkdir(parents=True, exist_ok=True)
    for page in sorted(by_page):
        png = sub / f"p{page:04d}.png"
        if not render(pdf, page, png):
            stat["render failed"] += 1
            continue
        img = read_png(png)
        m, _ = auto_mask(img.gray, img.width, img.height, 200)
        for reg, pw, ph in by_page[page]:
            sx, sy = img.width / pw, img.height / ph
            x0, y0 = int(reg["top_left_x"] * sx), int(reg["top_left_y"] * sy)
            x1 = int((reg["top_left_x"] + reg["width"]) * sx)
            y1 = int((reg["top_left_y"] + reg["height"]) * sy)
            x0, y0 = max(0, x0), max(0, y0)
            x1, y1 = min(img.width, x1), min(img.height, y1)
            r = analyse(m, x0, y0, x1, y1)
            stat["equations"] += 1
            if r is None:
                stat["too small or no ink"] += 1
                continue
            ok, nc, nr, nd, nl = r
            if nd < 2:
                stat["no delimiter pair"] += 1
            elif ok:
                stat["1 labels right-and-below"] += 1
                stat["left-hand-side components"] += nl
                stat["outside components"] += nc
                stat["outside rows"] += nr
                detail.append((page, nc, nr, nd))
            elif nl:
                # a delimited expression with something to the LEFT of
                # the opening bracket and nothing right or below: an
                # ordinary `lhs = [ ... ]`. Counted on its own because
                # merging it with "nothing outside" would hide the
                # commonest shape a matrix equation has.
                stat["2 left-hand side only"] += 1
                stat["lhs-only components"] += nl
            else:
                stat["3 nothing outside at all"] += 1
        png.unlink(missing_ok=True)
    return name, (stat, detail)


def main():
    import concurrent.futures as cf
    books = A.books or BOOKS
    print(f"{len(books)} books, {A.dpi} dpi, rendered from each "
          f"document's OWN pdf (never its report)")
    tot = collections.Counter()
    with cf.ProcessPoolExecutor(max_workers=A.jobs) as ex:
        for name, res in ex.map(one_book, books):
            if res is None:
                print(f"\n{name[:50]}: no source pdf or no lines.json")
                continue
            stat, detail = res
            tot.update(stat)
            print(f"\n{name[:60]}")
            for k in ("equations", "1 labels right-and-below",
                      "2 left-hand side only",
                      "3 nothing outside at all", "no delimiter pair",
                      "too small or no ink", "render failed"):
                if stat[k]:
                    print(f"    {k:<28} {stat[k]:6d}")
            if stat["1 labels right-and-below"]:
                print(f"    outside components (sum)     "
                      f"{stat['outside components']:6d}")
                print(f"    outside rows (sum)           "
                      f"{stat['outside rows']:6d}")
                d = sorted(detail, key=lambda x: -x[2])[:5]
                print(f"    worst by outside rows: " +
                      ", ".join(f"p{p} {r}rows/{c}comps"
                                for p, c, r, _ in d))
    print("\n" + "=" * 62)
    print("ACROSS THE FIVE BOOKS")
    for k in ("equations", "no delimiter pair",
              "1 labels right-and-below", "2 left-hand side only",
              "3 nothing outside at all", "too small or no ink",
              "outside components", "outside rows",
              "lhs-only components"):
        print(f"  {k:<30} {tot[k]:6d}")
    d = sum(tot[k] for k in ("1 labels right-and-below",
                             "2 left-hand side only",
                             "3 nothing outside at all"))
    print(f"  delimited (the three classes)  {d:6d}")
    if tot["equations"]:
        print(f"  class 1 share of all equations "
              f"{100.0 * tot['1 labels right-and-below'] / tot['equations']:5.1f}%")
        if d:
            print(f"  class 1 share of DELIMITED     "
                  f"{100.0 * tot['1 labels right-and-below'] / d:5.1f}%")


if __name__ == "__main__":
    main()
