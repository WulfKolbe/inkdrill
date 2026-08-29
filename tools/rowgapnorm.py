"""309: gap / median GLYPH WIDTH, against 305's gap / median GAP.

Same population, same pages, same rows -- only the denominator
changes, so a difference between the two is the normaliser and
nothing else.

EXPECTATION RECORDED BEFORE RUNNING: the saturation 305 found should
disappear, because a median glyph width at 300 dpi is 20-40 px and
cannot collapse to 1 the way a median gap does. Whether the
distribution SEPARATES is the open question and the expectation says
nothing about it.
"""
import sys, pathlib, statistics, subprocess, tempfile, json, collections
sys.path.insert(0, "/home/wkolbe/inkdrill")
from inkdrill.pngio import read_png, auto_mask
from inkdrill.raster import InkMask
from inkdrill.nest import ink_only
from inkdrill.mathstruct import Glyph, rows

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

pdf = pathlib.Path(sys.argv[1]); lj = json.loads(pathlib.Path(sys.argv[2]).read_text(errors="replace"))
pages = [int(x) for x in sys.argv[3:]]
by_gap, by_width, meds = [], [], []
for pg in pages:
    p = next((x for x in lj["pages"] if x["page"] == pg), None)
    if p is None: continue
    got = render(pdf, pg)
    if got is None: continue
    img, m = got
    sx, sy = img.width/p["page_width"], img.height/p["page_height"]
    for l in p.get("lines", []):
        if l.get("type") not in ("math", "text") or not l.get("region"): continue
        r = l["region"]
        c = crop(m, max(0,int(r["top_left_x"]*sx)), max(0,int(r["top_left_y"]*sy)),
                 min(img.width,int((r["top_left_x"]+r["width"])*sx)),
                 min(img.height,int((r["top_left_y"]+r["height"])*sy)))
        if c is None: continue
        regs = list(ink_only(c).regions)
        gl = [Glyph(i, float(x.x0), float(x.y0), float(x.x1+1), float(x.y1+1))
              for i, x in enumerate(regs)]
        for row in rows(gl):
            ms = sorted(row.members, key=lambda g: g.x0)
            if len(ms) < 4: continue
            gaps = [max(0.0, ms[i+1].x0 - ms[i].x1) for i in range(len(ms)-1)]
            mgap = statistics.median(gaps) or 1.0
            mw = statistics.median(g.x1 - g.x0 for g in ms) or 1.0
            meds.append((mgap, mw))
            by_gap.append([g/mgap for g in gaps])
            by_width.append([g/mw for g in gaps])
def show(name, rowsets):
    flat = sorted(v for rs in rowsets for v in rs)
    print(f"\n{name}: {len(rowsets)} rows, {len(flat)} gaps")
    for q in (50,75,90,95,97,99,100):
        print(f"   p{q:<3} {flat[min(len(flat)-1,int(q/100*(len(flat)-1)))]:8.2f}")
    prev = None
    for thr in (0.25,0.5,0.75,1.0,1.5,2,3,4,5,6,8,10):
        n = sum(1 for rs in rowsets if any(v >= thr for v in rs))
        d = "" if prev is None else f"   drop {prev-n:4d}"
        print(f"   >= {thr:5.2f}x : {n:5d} rows ({100.0*n/len(rowsets):5.1f}%){d}")
        prev = n
mg = sorted(m for m,_ in meds); mwv = sorted(w for _,w in meds)
print(f"median GAP per row:   p10 {mg[len(mg)//10]:.1f}  p50 {mg[len(mg)//2]:.1f}  p90 {mg[9*len(mg)//10]:.1f}")
print(f"median WIDTH per row: p10 {mwv[len(mwv)//10]:.1f}  p50 {mwv[len(mwv)//2]:.1f}  p90 {mwv[9*len(mwv)//10]:.1f}")
print(f"rows whose median gap is <= 1 px: {sum(1 for m,_ in meds if m <= 1)} of {len(meds)}")
print(f"rows whose median width is <= 1 px: {sum(1 for _,w in meds if w <= 1)} of {len(meds)}")
show("305  gap / median GAP", by_gap)
show("309  gap / median GLYPH WIDTH", by_width)
