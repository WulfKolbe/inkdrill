"""336: what a crop contains that its base image does not.

Registers the base inside the crop by a coarse scale/offset search --
the crop is the printed figure PLUS whatever was drawn over it, so
the base's ink should be almost entirely covered by the crop's ink,
and the transform that maximises that coverage places the figure.

Components of the crop left uncovered are the ADDITION. They are
clustered by single linkage and each cluster is described by where it
sits relative to the registered base rectangle.

REGISTRATION QUALITY IS REPORTED, not assumed. `coverage` is the
fraction of base ink the chosen transform explains; a pair whose
coverage is low has not been registered and its diff means nothing,
which must be visible rather than folded into the answer.
"""
import json, pathlib, subprocess, sys, tempfile, statistics
sys.path.insert(0, "/home/wkolbe/inkdrill")
from inkdrill.pngio import read_png, auto_mask
from inkdrill.raster import InkMask
from inkdrill.nest import ink_only

def load(p):
    tmp = pathlib.Path(tempfile.mkdtemp())/"x.png"
    r = subprocess.run(["magick", str(p), "-define","png:color-type=2", str(tmp)],
                       capture_output=True)
    if r.returncode or not tmp.is_file(): return None
    img = read_png(tmp); m,_ = auto_mask(img.gray, img.width, img.height, 200)
    tmp.unlink(missing_ok=True)
    return m

def shrink(m, target=140):
    """nearest-neighbour downsample to about `target` px wide"""
    s = max(1, round(m.width/target))
    w, h = m.width//s, m.height//s
    b = bytearray(w*h)
    for y in range(h):
        row = (y*s)*m.width
        for x in range(w):
            b[y*w+x] = m.data[row + x*s]
    return InkMask(bytes(b), w, h), s

def coverage(base, crop, scale, ox, oy):
    """fraction of base ink landing on crop ink at this placement"""
    hit = tot = 0
    bw, bh = base.width, base.height
    for y in range(bh):
        cy = int(y*scale) + oy
        if not (0 <= cy < crop.height): continue
        brow = y*bw; crow = cy*crop.width
        for x in range(bw):
            if not base.data[brow+x]: continue
            tot += 1
            cx = int(x*scale) + ox
            if 0 <= cx < crop.width and crop.data[crow+cx]: hit += 1
    return (hit/tot if tot else 0.0), tot

def register(base, crop):
    best = (0.0, 1.0, 0, 0)
    bw, bh = base.width, base.height
    for i in range(8, 26):
        s = i/20.0                       # 0.40 .. 1.25
        nw, nh = int(bw*s), int(bh*s)
        if nw < 8 or nh < 8 or nw > crop.width+4 or nh > crop.height+4: continue
        for oy in range(0, max(1, crop.height-nh+1), max(1, (crop.height-nh)//6 or 1)):
            for ox in range(0, max(1, crop.width-nw+1), max(1, (crop.width-nw)//6 or 1)):
                c, _ = coverage(base, crop, s, ox, oy)
                if c > best[0]: best = (c, s, ox, oy)
    return best

def cluster(comps, gap):
    parent = {c.id: c.id for c in comps}
    def find(i):
        while parent[i] != i: parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for i, a in enumerate(comps):
        for b in comps[i+1:]:
            dx = max(a.x0-b.x1, b.x0-a.x1); dy = max(a.y0-b.y1, b.y0-a.y1)
            if max(0, dx, dy) <= gap:
                ra, rb = find(a.id), find(b.id)
                if ra != rb: parent[ra] = rb
    g = {}
    for c in comps: g.setdefault(find(c.id), []).append(c)
    return list(g.values())

pairs = json.loads(pathlib.Path(sys.argv[1]).read_text())["matched"]
ROOT = pathlib.Path.home()/"pdfdrill-library/2004.05631v1"
for rec in pairs:
    basep = ROOT/"texsrc"/rec["base"]
    cand = rec["candidates"][0]
    hits = list((ROOT/"texsrc").rglob(f"*{cand.split('-')[-1]}"))
    print(f"\n=== {rec['base']}  ->  {cand}")
    if not basep.is_file() or not hits:
        print("   FILE MISSING", basep.is_file(), len(hits)); continue
    B, C = load(basep), load(hits[0])
    if B is None or C is None: print("   convert failed"); continue
    bs, _ = shrink(B); cs, sc = shrink(C)
    cov, s, ox, oy = register(bs, cs)
    nw, nh = int(bs.width*s), int(bs.height*s)
    print(f"   base {B.width}x{B.height}  crop {C.width}x{C.height}"
          f"   registered scale {s:.2f} at ({ox},{oy}) size {nw}x{nh}"
          f"   coverage {cov:.2f}")
    if cov < 0.5:
        print("   REGISTRATION FAILED -- diff not reported")
        continue
    # base ink, dilated by 1, in crop coordinates
    covered = bytearray(cs.width*cs.height)
    for y in range(bs.height):
        cy = int(y*s)+oy
        for x in range(bs.width):
            if not bs.data[y*bs.width+x]: continue
            cx = int(x*s)+ox
            for dy in (-1,0,1):
                for dx in (-1,0,1):
                    yy, xx = cy+dy, cx+dx
                    if 0 <= yy < cs.height and 0 <= xx < cs.width:
                        covered[yy*cs.width+xx] = 1
    comps = list(ink_only(cs).regions)
    added = []
    for c in comps:
        on = tot = 0
        for y in range(c.y0, c.y1+1):
            for x in range(c.x0, c.x1+1):
                if cs.data[y*cs.width+x]:
                    tot += 1
                    if covered[y*cs.width+x]: on += 1
        if tot and on/tot < 0.35: added.append(c)
    if not added:
        print("   NO ADDED COMPONENTS -- the crop is the base, to this method")
        continue
    mw = statistics.median(c.x1-c.x0+1 for c in comps) or 2
    for cl in sorted(cluster(added, max(2, mw)), key=lambda g: min(c.y0 for c in g)):
        x0=min(c.x0 for c in cl); x1=max(c.x1 for c in cl)
        y0=min(c.y0 for c in cl); y1=max(c.y1 for c in cl)
        rel=[]
        if y1 < oy: rel.append("above")
        elif y0 > oy+nh: rel.append("below")
        if x1 < ox: rel.append("left")
        elif x0 > ox+nw: rel.append("right")
        if not rel: rel.append("overlapping")
        cxc=(x0+x1)/2; base_cx=ox+nw/2
        off = abs(cxc-base_cx)/max(1,nw)
        where = "centred" if off <= 0.15 else ("offset %.2f" % off)
        print(f"   + {len(cl):3d} comp cluster  {'/'.join(rel):12} {where:14}"
              f"  extent {x1-x0+1}x{y1-y0+1} of crop {cs.width}x{cs.height}"
              f"  ({100*(x1-x0+1)/cs.width:.0f}% x {100*(y1-y0+1)/cs.height:.0f}%)")
