import pathlib, sys, time, gc
sys.path.insert(0,"/home/wkolbe/inkdrill")
import inkdrill.sweep as SW
from inkdrill.pngio import read_png, auto_mask
from inkdrill.__main__ import _table_cells
from inkdrill.raster import iter_runs
P = pathlib.Path.home()/"pdfdrill-library/penev_A/inspect/pages"
f = sorted(P.glob("*.png"))[1]
img = read_png(f); m,_ = auto_mask(img.gray, img.width, img.height, 200)
px = m.width*m.height
runs = sum(1 for _ in iter_runs(m, "row"))
print(f"{f.stem}: {m.width}x{m.height} = {px/1e6:.1f} Mpx, ink "
      f"{100*m.data.count(255)/px:.2f}%, {runs:,} runs "
      f"({px/max(runs,1):.1f} px per run)")
# how many sweeps does one _table_cells actually pay?
orig = SW.sweep; calls=[]
def counting(mask,*a,**k):
    calls.append((mask.width*mask.height, k.get("conn"), str(k.get("capture"))))
    return orig(mask,*a,**k)
SW.sweep = counting
import inkdrill.nest as NEST; NEST.sweep = counting
gc.collect(); t0=time.perf_counter(); _table_cells(m,4.0,debug={}); dt=time.perf_counter()-t0
SW.sweep = orig; NEST.sweep = orig
print(f"\n_table_cells: {dt:.2f}s, {len(calls)} sweep call(s):")
for w,c,cap in calls: print(f"   {w/1e6:.1f} Mpx  conn={c}  {cap}")
print(f"   total swept: {sum(w for w,_,_ in calls)/1e6:.1f} Mpx "
      f"= {sum(w for w,_,_ in calls)/px:.1f}x the page")
print(f"\nthroughput: {px/1e6/dt:.2f} Mpx/s")
print(f"  a 640x480 frame at that rate = {px/1e6/dt/(0.64*0.48*1e6/1e6):.1f} fps")
