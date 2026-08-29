"""Advisory gap data, in glyph-width units, per region (323).

    python3 tools/rowspaces.py --pdf doc.pdf --lines doc.lines.json \
        --pages 108 [--floor 0.45] [--types math,text]

JSON on stdout. For every row of every named region: the row's median
glyph width in px, its median gap in GLYPH WIDTHS, and each gap at or
above `--floor` with its position and its size in the same units.

IT EMITS MEASUREMENTS, NOT VERDICTS, and that is the whole design.
306 was refused because "a space is required at character 14" is
unauditable -- the consumer, an LLM placing \\quad, cannot tell a real
space from an artefact. "Gap of 1.11 glyph widths after character 14,
row median 0.31" is the same fact with its evidence attached: a
reader can see that 1.11 sits in the upper mode and 0.31 does not,
and can disagree with the floor without re-running anything.

THE UNITS ARE WHY THIS WORKS AT ALL. 305 normalised each gap by its
row's median GAP and found no separation -- the distribution ran
smoothly from 88% of rows above 2x to 36% above 10x with no knee.
309 renormalised by median GLYPH WIDTH on the same rows and the
distribution is bimodal: a main mode at 0.10-0.20, a trough at
0.40-0.50 (3.3% density, down from 10.8%), and a second mode at
1.00-1.25 that collapses to 1.6% immediately above. A peak with a
hard right edge is what a fixed-width space character makes.

`--floor` defaults to 0.45, the trough. It is a REPORTING floor, not
a claim: every gap above it is emitted with its value so the consumer
decides. Lower it to 0 and the full distribution comes out.

WHAT IS NOT CLAIMED, and it is in the JSON as `not_established`:
that the upper mode IS typeset spaces. The histogram shows two
populations of gaps; calling the upper one "spaces" is an inference
from its position at one glyph width and its sharp edge. Confirming
it means checking that these positions correspond to spaces in the
row's LaTeX -- a join with the text side, which this tool does not do
and must not be taken to have done.
"""
import argparse, json, pathlib, statistics, subprocess, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from inkdrill.pngio import read_png, auto_mask                  # noqa
from inkdrill.raster import InkMask                             # noqa
from inkdrill.nest import ink_only                              # noqa
from inkdrill.mathstruct import Glyph, rows                     # noqa

# from out/309.txt, one book, 7,894 gaps
TROUGH = 0.45
SECOND_MODE = (1.00, 1.25)

ap = argparse.ArgumentParser(prog="tools/rowspaces.py",
                             description=__doc__.strip().splitlines()[0])
ap.add_argument("--pdf", required=True, type=pathlib.Path)
ap.add_argument("--lines", required=True, type=pathlib.Path)
ap.add_argument("--pages", required=True,
                help="comma-separated page numbers")
ap.add_argument("--floor", type=float, default=TROUGH,
                help="report gaps at or above this many glyph widths; "
                     "0 emits every gap")
ap.add_argument("--types", default="math,text",
                help="lines.json region types to read")
ap.add_argument("--dpi", type=int, default=300)
ap.add_argument("--min-glyphs", type=int, default=4)
A = ap.parse_args()
TYPES = set(A.types.split(","))


def render(page):
    tmp = pathlib.Path(tempfile.mkdtemp()) / "p.png"
    r = subprocess.run(
        ["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=png16m",
         f"-r{A.dpi}", f"-dFirstPage={page}", f"-dLastPage={page}",
         f"-sOutputFile={tmp}", str(A.pdf)], capture_output=True)
    if r.returncode or not tmp.is_file():
        return None
    img = read_png(tmp)
    m, _ = auto_mask(img.gray, img.width, img.height, 200)
    tmp.unlink(missing_ok=True)
    return img, m


def crop(m, x0, y0, x1, y1):
    w, h = x1 - x0, y1 - y0
    if w < 4 or h < 4:
        return None
    b = bytearray(w * h)
    for yy in range(h):
        s = (y0 + yy) * m.width + x0
        b[yy * w:(yy + 1) * w] = m.data[s:s + w]
    return InkMask(bytes(b), w, h)


lj = json.loads(A.lines.read_text(errors="replace"))
out = []
for pg in (int(x) for x in A.pages.split(",")):
    p = next((x for x in lj["pages"] if x["page"] == pg), None)
    if p is None:
        out.append({"page": pg, "error": "no such page in lines.json"})
        continue
    got = render(pg)
    if got is None:
        out.append({"page": pg, "error": "ghostscript failed"})
        continue
    img, m = got
    sx, sy = img.width / p["page_width"], img.height / p["page_height"]
    for li, l in enumerate(p.get("lines", [])):
        if l.get("type") not in TYPES or not l.get("region"):
            continue
        r = l["region"]
        c = crop(m, max(0, int(r["top_left_x"] * sx)),
                 max(0, int(r["top_left_y"] * sy)),
                 min(img.width, int((r["top_left_x"] + r["width"]) * sx)),
                 min(img.height, int((r["top_left_y"] + r["height"]) * sy)))
        if c is None:
            continue
        regs = list(ink_only(c).regions)
        gl = [Glyph(i, float(g.x0), float(g.y0), float(g.x1 + 1),
                    float(g.y1 + 1)) for i, g in enumerate(regs)]
        rr = []
        for row in rows(gl):
            ms = sorted(row.members, key=lambda g: g.x0)
            if len(ms) < A.min_glyphs:
                continue
            mw = statistics.median(g.x1 - g.x0 for g in ms)
            if mw <= 0:
                continue
            gaps = [max(0.0, ms[i + 1].x0 - ms[i].x1)
                    for i in range(len(ms) - 1)]
            rr.append({
                "y0": round(row.top, 1), "y1": round(row.bottom, 1),
                "glyphs": len(ms),
                "median_glyph_width_px": round(mw, 1),
                "median_gap_glyph_widths": round(
                    statistics.median(gaps) / mw, 3),
                "gaps": [{"after_character": i + 1,   # 1-indexed
                          "x_px": round(ms[i].x1, 0),
                          "glyph_widths": round(g / mw, 2),
                          "in_second_mode":
                              SECOND_MODE[0] <= g / mw <= SECOND_MODE[1]}
                         for i, g in enumerate(gaps)
                         if g / mw >= A.floor]})
        if rr:
            out.append({"page": pg, "line": li, "type": l.get("type"),
                        "region": r, "rows": rr})

json.dump({"pdf": str(A.pdf), "dpi": A.dpi, "floor_glyph_widths": A.floor,
           "reference": {"trough": TROUGH, "second_mode": list(SECOND_MODE),
                         "source": "out/309.txt, 1511.08771, 7894 gaps"},
           "not_established":
               "that the upper mode is typeset spaces. The histogram "
               "shows two gap populations; naming the upper one is an "
               "inference from its position and edge, not a "
               "measurement. Confirming it needs a join against the "
               "row's LaTeX, which this tool does not do.",
           "regions": out}, sys.stdout, indent=1)
print()
