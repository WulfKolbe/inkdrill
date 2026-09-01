"""472: three shape siblings for the five-tuple, computed not gating.

  extent          the cell's ink bounding box, w x h in px
  aspect          that box's w/h
  ink_per_max     ink pixels / max(w, h) -- how much ink the longest
                  side is carrying, which distinguishes a long thin
                  mark from a dense block of the same extent

Reported per cell for RENDER and SCAN, and per row as the disagreement
between them. Nothing gates on any of it.
"""
import json, pathlib, statistics, subprocess, sys, tempfile
sys.path.insert(0, "/home/wkolbe/inkdrill")
sys.path.insert(0, "/home/wkolbe/inkdrill/tools")
from inkdrill.pngio import read_png, auto_mask
from inkdrill.raster import InkMask
from inkdrill.nest import ink_only
from inkdrill.__main__ import _table_cells, _cell_crop
from pagedetect import probe, npages

def shape(mask):
    regs = list(ink_only(mask).regions)
    if not regs: return None
    x0=min(r.x0 for r in regs); x1=max(r.x1 for r in regs)
    y0=min(r.y0 for r in regs); y1=max(r.y1 for r in regs)
    w, h = x1-x0+1, y1-y0+1
    ink = mask.ink_count
    return dict(w=w, h=h, aspect=w/max(1,h), ink=ink,
                ink_per_max=ink/max(1,max(w,h)), comps=len(regs))

D = pathlib.Path(sys.argv[1]); COLS = int(sys.argv[2])
pdf = D/"report.pdf"
pages, census = probe(pdf, npages(pdf), COLS)
print(f"display pages {len(pages)} of {npages(pdf)}   census "
      f"{dict(sorted(census.items()))}", flush=True)
tmp = pathlib.Path(tempfile.mkdtemp())
rows = []
for k, p in enumerate(pages):
    out = tmp/"p.png"
    r = subprocess.run(["gs","-q","-dNOPAUSE","-dBATCH","-sDEVICE=png16m",
        "-r300",f"-dFirstPage={p}",f"-dLastPage={p}",f"-sOutputFile={out}",
        str(pdf)], capture_output=True)
    if r.returncode or not out.is_file(): continue
    img = read_png(out); m,_ = auto_mask(img.gray, img.width, img.height, 200)
    out.unlink(missing_ok=True)
    cells = _table_cells(m, 4.0)
    if not cells: continue
    nr = max(a for a,_ in cells)+1; nc = max(b for _,b in cells)+1
    if nc < 2: continue
    for rr in range(1, nr):
        b0 = cells.get((rr,0))
        if b0 is None or b0[3]-b0[1] < 40: continue
        cr = cells.get((rr, nc-2)); cs = cells.get((rr, nc-1))
        if cr is None or cs is None: continue
        R = shape(_cell_crop(m, cr[0],cr[1],cr[2]-1,cr[3]-1))
        S = shape(_cell_crop(m, cs[0],cs[1],cs[2]-1,cs[3]-1))
        if R is None or S is None: continue
        rows.append((p, rr, R, S))
    if (k+1) % 25 == 0: print(f"  ..{k+1}/{len(pages)} pages, {len(rows)} rows", flush=True)
print(f"ROWS MEASURED {len(rows)}", flush=True)
json.dump([[p,rr,R,S] for p,rr,R,S in rows],
          open(sys.argv[3],"w"))
def q(v,f): 
    v=sorted(v); return v[min(len(v)-1,int(f*(len(v)-1)))]
for name, fn in (("aspect ratio  |log2(render/scan)|",
                  lambda R,S: abs((R["aspect"]/max(1e-9,S["aspect"])))),
                 ("ink_per_max   render/scan",
                  lambda R,S: R["ink_per_max"]/max(1e-9,S["ink_per_max"])),
                 ("extent area   render/scan",
                  lambda R,S: (R["w"]*R["h"])/max(1,S["w"]*S["h"]))):
    v = [fn(R,S) for _,_,R,S in rows]
    print(f"\n{name}")
    for f in (.05,.25,.5,.75,.9,.95,.99,1.0):
        print(f"   p{int(f*100):<3} {q(v,f):8.3f}")
