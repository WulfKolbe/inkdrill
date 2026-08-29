"""Gaps WITHIN a lines.json region, not within a page-wide row (305).

The first population was wrong. `mathstruct.rows` groups by vertical
overlap across the WHOLE PAGE, so one "row" can span an equation and
its equation number with 400 px of margin between them -- that is
page layout, not a typeset space, and it put 82-96% of rows above
every candidate threshold. A gap is only a space if the two glyphs
are in the same LINE, and lines.json says where the lines are.
"""
import sys, pathlib, statistics, subprocess, tempfile, json, collections
sys.path.insert(0, "/home/wkolbe/inkdrill")
from inkdrill.pngio import read_png, auto_mask
from inkdrill.raster import InkMask
from inkdrill.nest import ink_only
from inkdrill.mathstruct import Glyph, rows

def page_regions(lj, page):
    for p in lj["pages"]:
        if p["page"] == page:
            return p, [l for l in p.get("lines", []) if l.get("region")]
    return None, []

def render(pdf, page, dpi=300):
    tmp = pathlib.Path(tempfile.mkdtemp())/"p.png"
    r = subprocess.run(["gs","-q","-dNOPAUSE","-dBATCH","-sDEVICE=png16m",
        f"-r{dpi}",f"-dFirstPage={page}",f"-dLastPage={page}",
        f"-sOutputFile={tmp}",str(pdf)], capture_output=True)
    if r.returncode or not tmp.is_file(): return None
    img = read_png(tmp)
    m, _ = auto_mask(img.gray, img.width, img.height, 200)
    tmp.unlink(missing_ok=True)
    return img, m

def crop(m, x0, y0, x1, y1):
    w, h = x1-x0, y1-y0
    if w < 4 or h < 4: return None
    b = bytearray(w*h)
    for yy in range(h):
        s = (y0+yy)*m.width + x0
        b[yy*w:(yy+1)*w] = m.data[s:s+w]
    return InkMask(bytes(b), w, h)

def region_gaps(mask, min_glyphs=4):
    regs = list(ink_only(mask).regions)
    gl = [Glyph(i, float(r.x0), float(r.y0), float(r.x1+1), float(r.y1+1))
          for i, r in enumerate(regs)]
    out = []
    for row in rows(gl):
        ms = sorted(row.members, key=lambda g: g.x0)
        if len(ms) < min_glyphs: continue
        gaps = [max(0.0, ms[i+1].x0 - ms[i].x1) for i in range(len(ms)-1)]
        med = statistics.median(gaps) or 1.0
        out.append((med, [g/med for g in gaps], len(ms)))
    return out

pdf = pathlib.Path(sys.argv[1]); ljp = pathlib.Path(sys.argv[2])
pages = [int(x) for x in sys.argv[3:]]
lj = json.loads(ljp.read_text(errors="replace"))
allrows, bytype = [], collections.Counter()
for pg in pages:
    p, lines = page_regions(lj, pg)
    if p is None: continue
    got = render(pdf, pg)
    if got is None: continue
    img, m = got
    sx, sy = img.width/p["page_width"], img.height/p["page_height"]
    # MATH REGIONS ONLY. The restriction is decided by 306's
    # PURPOSE -- telling an LLM where to put \quad inside a maths
    # string -- not by which population gives a break. The previous
    # population was every region type, and lines.json nests
    # table/table_column/simple_cell over the same ink, so one cell
    # was counted up to four times.
    for l in lines:
        if l.get("type") not in ("math", "text"): continue
        r = l["region"]
        c = crop(m, max(0,int(r["top_left_x"]*sx)), max(0,int(r["top_left_y"]*sy)),
                 min(img.width, int((r["top_left_x"]+r["width"])*sx)),
                 min(img.height, int((r["top_left_y"]+r["height"])*sy)))
        if c is None: continue
        for med, ratios, n in region_gaps(c):
            allrows.append((l.get("type"), med, ratios, n))
            bytype[l.get("type")] += 1
ratios = sorted(r for _,_,rs,_ in allrows for r in rs)
print(f"pages {len(pages)}  regions with rows {len(allrows)}  gaps {len(ratios)}")
print("  by region type:", dict(bytype))
for q in (50,75,90,95,97,98,99,100):
    print(f"  p{q:<3} {ratios[min(len(ratios)-1,int(q/100*(len(ratios)-1)))]:8.2f}")
for thr in (2,3,4,5,6,8,10):
    n = sum(1 for _,_,rs,_ in allrows if any(r >= thr for r in rs))
    print(f"  rows with a gap >= {thr:2d}x median: {n:5d} ({100.0*n/max(1,len(allrows)):5.1f}%)")
