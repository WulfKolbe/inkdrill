"""591 -- is the ring channel above the speckle floor?

589 found that at 150 dpi a scanned crop can reach ~3.4 holes per
component: at that density the hole count is speckle, and a topology
claim built on it is noise. 218 and 222 rest on hole counts taken from
MathPix's own crops, whose dpi neither harness recorded.

This reports the ratio for the population those findings were made
over, so "the crop is above the floor" is a number rather than an
assumption. It measures the same way `ringmeasure.py` does -- magick to
PNG, threshold 200, `ink_only` -- because a second decode path would
answer a different question.
"""

from __future__ import annotations

import argparse
import pathlib
import random
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from inkdrill.nest import ink_only                       # noqa: E402
from inkdrill.pngio import auto_mask, read_png           # noqa: E402


def ratio(jpg: pathlib.Path, tmp: pathlib.Path, threshold: int):
    png = tmp / "r.png"
    r = subprocess.run(["magick", str(jpg), "-define", "png:color-type=2",
                        str(png)], capture_output=True)
    if r.returncode != 0 or not png.is_file():
        return None
    img = read_png(png)
    m, _ = auto_mask(img.gray, img.width, img.height, threshold)
    ip = ink_only(m)
    comp = len(list(ip.regions))
    if comp == 0:
        return None
    return comp, sum(ip.cycles), img.width, img.height


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--library", type=pathlib.Path,
                    default=pathlib.Path.home() / "pdfdrill-library")
    ap.add_argument("--n", type=int, default=400)
    ap.add_argument("--seed", type=int, default=591)
    ap.add_argument("--threshold", type=int, default=200)
    ap.add_argument("--work", type=pathlib.Path,
                    default=pathlib.Path("/tmp"))
    args = ap.parse_args()
    tmp = args.work / "ringfloor"
    tmp.mkdir(parents=True, exist_ok=True)

    crops = []
    for d in sorted(args.library.iterdir()):
        rc = d / "report-crops"
        if rc.is_dir():
            crops += [f for f in rc.glob("*_EQ*.jpg")]
    print(f"population: {len(crops)} EQ crops in "
          f"{len({c.parent for c in crops})} documents", flush=True)
    rng = random.Random(args.seed)
    rng.shuffle(crops)
    picked = crops[:args.n]

    rows = []
    for i, f in enumerate(picked):
        got = ratio(f, tmp, args.threshold)
        if got:
            rows.append(got)
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(picked)}", flush=True)
    rs = sorted(h / c for c, h, _w, _hh in rows)
    n = len(rs)
    print(f"\nmeasured {n} crops, threshold {args.threshold}, seed "
          f"{args.seed}")
    print(f"  holes per component:  p50 {rs[n//2]:.3f}   "
          f"p90 {rs[int(.90*n)]:.3f}   p99 {rs[int(.99*n)]:.3f}   "
          f"max {rs[-1]:.3f}")
    for cut in (1.0, 2.0, 3.0):
        k = sum(1 for v in rs if v >= cut)
        print(f"  at or above {cut:.1f} holes/component: {k:5d}  "
              f"{100*k/n:5.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
