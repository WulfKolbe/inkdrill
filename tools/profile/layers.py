import pathlib, sys, time, gc
tree = sys.argv[1]
sys.path.insert(0, tree)
from inkdrill.pngio import read_png, auto_mask
from inkdrill.sweep import sweep, Capture
from inkdrill.raster import iter_runs
from inkdrill.nest import nest
P = pathlib.Path.home()/"pdfdrill-library/penev_A/inspect/pages"
f = sorted(P.glob("*.png"))[1]
img = read_png(f); m,_ = auto_mask(img.gray, img.width, img.height, 200)
inv = m.inverted()
def best(fn, n=3):
    ts=[]
    for _ in range(n):
        gc.collect(); t0=time.perf_counter(); fn(); ts.append(time.perf_counter()-t0)
    return min(ts)
r_runs  = best(lambda: sum(1 for _ in iter_runs(m,"row")))
r_none  = best(lambda: sweep(m, conn=8, capture=Capture.NONE))
r_graph = best(lambda: sweep(m, conn=8, capture=Capture.GRAPH))
b_none  = best(lambda: sweep(inv, conn=4, capture=Capture.NONE))
r_nest  = best(lambda: nest(m), 2)
print(f"{tree.split('/')[-1] or 'main'}")
print(f"  iter_runs only (fg)      {r_runs:7.3f}s")
print(f"  sweep fg conn8 NONE      {r_none:7.3f}s   (+{r_none-r_runs:.3f} over runs)")
print(f"  sweep fg conn8 GRAPH     {r_graph:7.3f}s   (+{r_graph-r_none:.3f} over NONE)")
print(f"  sweep bg conn4 NONE      {b_none:7.3f}s")
print(f"  nest (fg+bg+parents)     {r_nest:7.3f}s   (+{r_nest-r_none-b_none:.3f} over the two sweeps)")
