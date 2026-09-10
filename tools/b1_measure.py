"""b1_measure.py -- CR B1 step 5. Three numbers, one harness.

    python3 tools/b1_measure.py

1. THE GATE. `sweep(moments=False)` on this checkout against the same
   call on the PRE-B1 baseline, which is checked out into a temporary
   directory as a second package so both run in one process. The CR
   budgets the per-run `if moments:` branch at about 2% and says the
   flag is in the wrong place above that.

2. THE WIN. `sweep(moments=True)` against
   `sweep(moments=False)` + `aggregate.moments_per_component`.

3. MEMORY. Peak allocation during each, by `tracemalloc`: ten integers
   in a list per component against the dict of frozen `Moments` the
   second pass builds.

Population is named in the output. Best-of-N with `gc.collect()`
between runs, and 1 and 2 are timed in BOTH ORDERS, because a single
order lets the second implementation profit from whatever the first
left warm.

The page set is the 42 DISTINCT pages of kolbe2018hubbard: the
directory holds 84 files because `p1.png` and `page-0001.png` are
byte-identical, so a naive `*.png` glob times every page twice.
"""
from __future__ import annotations

import argparse
import gc
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import tracemalloc

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASELINE = "0796014"          # the commit before B1 step 0


def checkout_baseline(rev: str, into: pathlib.Path) -> None:
    """The pre-B1 package, as a SECOND importable package.

    Copied rather than imported from a worktree so both versions live
    in one process and one timing loop -- two processes cannot be
    compared to 1%.
    """
    pkg = into / "inkdrill_pre"
    pkg.mkdir(parents=True)
    names = subprocess.run(["git", "ls-tree", "--name-only", f"{rev}:inkdrill"],
                           cwd=ROOT, capture_output=True, text=True, check=True)
    for name in names.stdout.split():
        blob = subprocess.run(["git", "show", f"{rev}:inkdrill/{name}"],
                              cwd=ROOT, capture_output=True, check=True)
        (pkg / name).write_bytes(blob.stdout)


def best(fn, n):
    ts = []
    for _ in range(n):
        gc.collect()
        t0 = time.perf_counter()
        fn()
        ts.append(time.perf_counter() - t0)
    return min(ts)


def peak(fn):
    gc.collect()
    tracemalloc.start()
    keep = fn()
    _, hi = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    del keep
    return hi


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=pathlib.Path,
                    default=pathlib.Path.home()
                    / "pdfdrill-library/kolbe2018hubbard/inspect/pages")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--baseline", default=BASELINE)
    args = ap.parse_args()

    sys.path.insert(0, str(ROOT))
    from inkdrill.aggregate import moments_per_component      # noqa: E402
    from inkdrill.pngio import auto_mask, read_png            # noqa: E402
    from inkdrill.sweep import Capture, sweep                 # noqa: E402

    tmp = tempfile.mkdtemp()
    try:
        checkout_baseline(args.baseline, pathlib.Path(tmp))
        sys.path.insert(0, tmp)
        from inkdrill_pre.sweep import sweep as sweep_pre     # noqa: E402

        pgs = sorted((p for p in args.pages.glob("p*.png")
                      if not p.stem.startswith("page-")),
                     key=lambda p: int("".join(c for c in p.stem
                                               if c.isdigit())))
        if args.limit:
            pgs = pgs[:args.limit]
        masks = []
        for p in pgs:
            img = read_png(p)
            masks.append(auto_mask(img.gray, img.width, img.height, 200)[0])
        px = sum(m.width * m.height for m in masks)
        ncomp = sum(len(sweep(m, capture=Capture.NONE).components)
                    for m in masks)
        print(f"{len(masks)} pages, {px/1e6:.1f} Mpx, {ncomp} components, "
              f"best of {args.reps}, gc between runs")
        print(f"baseline {args.baseline} (the commit before B1 step 0)\n")

        # ---- 1. the gate -------------------------------------------
        print("1. THE GATE -- moments=False against pre-B1")
        print(f"   {'order':<14} {'pre-B1':>10} {'now':>10} {'change':>9}")
        acc = {}
        for order in ("pre first", "now first"):
            a = b = 0.0
            for m in masks:
                if order == "pre first":
                    a += best(lambda: sweep_pre(m, capture=Capture.NONE),
                              args.reps)
                    b += best(lambda: sweep(m, capture=Capture.NONE),
                              args.reps)
                else:
                    b += best(lambda: sweep(m, capture=Capture.NONE),
                              args.reps)
                    a += best(lambda: sweep_pre(m, capture=Capture.NONE),
                              args.reps)
            acc[order] = (a, b)
            print(f"   {order:<14} {a:>9.3f}s {b:>9.3f}s "
                  f"{100*(b-a)/a:>+8.2f}%")
        a = sum(x[0] for x in acc.values()) / 2
        b = sum(x[1] for x in acc.values()) / 2
        print(f"   mean of both orders: {a:.3f}s -> {b:.3f}s "
              f"= {100*(b-a)/a:+.2f}%\n")

        # ---- 2. the win --------------------------------------------
        print("2. THE WIN -- moments=True against sweep + second pass")
        print(f"   {'order':<14} {'two passes':>11} {'in-loop':>10} "
              f"{'change':>9}")
        acc2 = {}

        def two_pass(m):
            r = sweep(m, capture=Capture.NONE)
            moments_per_component(r)

        for order in ("two first", "loop first"):
            a2 = b2 = 0.0
            for m in masks:
                if order == "two first":
                    a2 += best(lambda: two_pass(m), args.reps)
                    b2 += best(lambda: sweep(m, capture=Capture.NONE,
                                             moments=True), args.reps)
                else:
                    b2 += best(lambda: sweep(m, capture=Capture.NONE,
                                             moments=True), args.reps)
                    a2 += best(lambda: two_pass(m), args.reps)
            acc2[order] = (a2, b2)
            print(f"   {order:<14} {a2:>10.3f}s {b2:>9.3f}s "
                  f"{100*(b2-a2)/a2:>+8.2f}%")
        a2 = sum(x[0] for x in acc2.values()) / 2
        b2 = sum(x[1] for x in acc2.values()) / 2
        print(f"   mean of both orders: {a2:.3f}s -> {b2:.3f}s "
              f"= {100*(b2-a2)/a2:+.2f}%   ({a2/b2:.2f}x)\n")

        # ---- 3. memory ---------------------------------------------
        print("3. MEMORY -- peak allocation, tracemalloc, 3 pages")
        print(f"   {'page':<6} {'comps':>6} {'no moments':>12} "
              f"{'in-loop':>11} {'second pass':>12}")
        for m, p in list(zip(masks, pgs))[:3]:
            n = len(sweep(m, capture=Capture.NONE).components)
            p0 = peak(lambda: sweep(m, capture=Capture.NONE))
            p1 = peak(lambda: sweep(m, capture=Capture.NONE, moments=True))
            def second():
                r = sweep(m, capture=Capture.NONE)
                return (r, moments_per_component(r))
            p2 = peak(second)
            print(f"   {p.stem:<6} {n:>6} {p0/1e6:>11.2f}M "
                  f"{p1/1e6:>10.2f}M {p2/1e6:>11.2f}M")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
