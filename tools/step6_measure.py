"""CR step 6 -- the branch's cumulative figure, in one place.

`sweep` against `_sweep_reference` over the 42 pages of
kolbe2018hubbard/inspect/pages, at Capture.NONE and Capture.GRAPH.

Best-of-N with `gc.collect()` between runs, and the two
implementations timed in BOTH ORDERS, because a single order lets the
second one profit from whatever the first left warm. The two orders
are reported separately; if they disagree by more than a point or two
the measurement is noise and should be read as such.

The page set is the 42 DISTINCT pages. The directory holds 84 files:
`p1.png` and `page-0001.png` are byte-identical, so globbing `*.png`
would time every page twice and report a page count that is wrong by
two.
"""
from __future__ import annotations
import argparse, gc, pathlib, sys, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from inkdrill.pngio import auto_mask, read_png          # noqa: E402
from inkdrill.sweep import Capture, _sweep_reference, sweep  # noqa: E402


def best(fn, n):
    ts = []
    for _ in range(n):
        gc.collect()
        t0 = time.perf_counter(); fn(); ts.append(time.perf_counter() - t0)
    return min(ts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=pathlib.Path,
                    default=pathlib.Path.home()
                    / "pdfdrill-library/kolbe2018hubbard/inspect/pages")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    pgs = sorted((p for p in args.pages.glob("p*.png")
                  if not p.stem.startswith("page-")),
                 key=lambda p: int("".join(c for c in p.stem if c.isdigit())))
    if args.limit:
        pgs = pgs[:args.limit]
    masks = []
    for p in pgs:
        img = read_png(p)
        masks.append(auto_mask(img.gray, img.width, img.height, 200)[0])
    px = sum(m.width * m.height for m in masks)
    print(f"{len(masks)} pages, {px/1e6:.1f} Mpx total, best of {args.reps}, "
          f"gc between runs\n")
    print(f"  {'capture':<8} {'order':<14} {'reference':>10} {'sweep':>9} "
          f"{'change':>9}")
    out = {}
    for cap in (Capture.NONE, Capture.GRAPH):
        for order in ("ref first", "sweep first"):
            r = f = 0.0
            for m in masks:
                if order == "ref first":
                    r += best(lambda: _sweep_reference(m, conn=8, capture=cap),
                              args.reps)
                    f += best(lambda: sweep(m, conn=8, capture=cap), args.reps)
                else:
                    f += best(lambda: sweep(m, conn=8, capture=cap), args.reps)
                    r += best(lambda: _sweep_reference(m, conn=8, capture=cap),
                              args.reps)
            out[(cap.value, order)] = (r, f)
            print(f"  {cap.value:<8} {order:<14} {r:>9.3f}s {f:>8.3f}s "
                  f"{100*(f-r)/r:>+8.1f}%")
    print()
    for cap in ("none", "graph"):
        rs = [out[(cap, o)] for o in ("ref first", "sweep first")]
        r = sum(x[0] for x in rs) / 2; f = sum(x[1] for x in rs) / 2
        print(f"  {cap:<6} mean of both orders: {r:.3f}s -> {f:.3f}s "
              f"= {100*(f-r)/r:+.1f}%   ({r/f:.2f}x)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
