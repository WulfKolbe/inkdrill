import pathlib, sys, time, gc
sys.path.insert(0,"/home/wkolbe/inkdrill")
from inkdrill.pngio import read_png, auto_mask
from inkdrill.nest import nest
P = pathlib.Path.home()/"pdfdrill-library/penev_A/inspect/pages"
pgs = sorted(P.glob("*.png"), key=lambda p:int(''.join(c for c in p.stem if c.isdigit()) or 0))[:12]
print(f"{'page':<6} {'ink%':>6} {'runs':>9} | {'decode':>7} {'nest':>7} | "
      f"{'decode share':>13} {'Mpx/s':>7}")
td=tn=0
for f in pgs:
    gc.collect(); t0=time.perf_counter(); img=read_png(f); d=time.perf_counter()-t0
    m,_=auto_mask(img.gray,img.width,img.height,200)
    px=m.width*m.height
    from inkdrill.raster import iter_runs
    runs=sum(1 for _ in iter_runs(m,"row"))
    gc.collect(); t0=time.perf_counter(); nest(m); n=time.perf_counter()-t0
    td+=d; tn+=n
    print(f"{f.stem:<6} {100*m.data.count(255)/px:>5.2f} {runs:>9,} | "
          f"{d:>7.3f} {n:>7.3f} | {100*d/(d+n):>12.1f}% {px/1e6/(d+n):>7.2f}")
print(f"\n  {len(pgs)} pages: decode {td:.2f}s, nest {tn:.2f}s "
      f"-> decode is {100*td/(td+tn):.1f}% of decode+nest")
