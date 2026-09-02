"""496 -- is the rendered column's hole instability caused by ALIASING?

The compare harness renders with `-sDEVICE=pgmraw` and no alpha bits,
so the LaTeX column comes back with exactly two grey levels: every
pixel is a hard in/out decision at the sampling grid. The scan column
is a real greyscale photograph, 200+ levels, thresholded at 200.

That is the whole of the left/right asymmetry in the corpus. A hard
bilevel rasteriser re-decides every near-tangent contact when the grid
changes; a threshold crossing in a smooth grey field does not move,
because the contour it crosses is in the same place at any sampling
density.

This measures the claim directly: the same pages, the same cells, the
same threshold, rendered once WITHOUT and once WITH anti-aliasing, and
the hole count compared between 300 and 600 dpi in each case. If
aliasing is the cause, the instability falls; if it does not fall, the
cause is elsewhere and the caveat is about resolution rather than
about this project's render settings.
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from inkdrill.__main__ import _table_cells, _drop_slivers, _cell_crop
from inkdrill.mathstruct import pair_stats
from inkdrill.pnmio import mask_from_pgm
from pagedetect import npages, probe, target_columns

THRESHOLD = 200
TOL = 4.0
ALIAS = {"aliased": [], "antialiased": ["-dTextAlphaBits=4",
                                        "-dGraphicsAlphaBits=4"]}


def cells_of(mask):
    c = _table_cells(mask, TOL, debug={})
    if c is None:
        return None
    c = _drop_slivers(c, mask.height)
    if not c:
        return None
    return c, max(cc for _, cc in c) + 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("doc")
    ap.add_argument("--library", type=pathlib.Path,
                    default=pathlib.Path.home() / "pdfdrill-library")
    ap.add_argument("--work", type=pathlib.Path,
                    default=pathlib.Path.home() / "inkdrill-work" / "dpi496a")
    args = ap.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    d = args.library / args.doc
    pdf = d / "report.pdf"
    want = target_columns(d / "report.tex")
    disp, _ = probe(pdf, npages(pdf), want)
    print(f"{args.doc}: {len(disp)} display pages, tex says {want} cols")

    tally = {k: {"left": [0, 0], "right": [0, 0]} for k in ALIAS}
    levels = {k: {"left": set(), "right": set()} for k in ALIAS}
    for p in disp:
        for mode, flags in ALIAS.items():
            m, grey = {}, {}
            for dpi in (300, 600):
                f = args.work / f"{args.doc[:30]}_{mode}_p{p:03d}_{dpi}.pgm"
                if not f.exists():
                    subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH",
                                    "-sDEVICE=pgmraw", f"-r{dpi}"] + flags
                                   + [f"-dFirstPage={p}", f"-dLastPage={p}",
                                      f"-sOutputFile={f}", str(pdf)],
                                   check=True)
                m[dpi] = mask_from_pgm(f, threshold=THRESHOLD)
                from inkdrill.pnmio import read_pnm
                grey[dpi] = read_pnm(f, dpi=dpi)
                f.unlink()
            lat = {dpi: cells_of(m[dpi]) for dpi in (300, 600)}
            if any(v is None for v in lat.values()):
                continue
            n = min(max(r for r, _ in lat[dpi][0]) for dpi in (300, 600))
            for r in range(1, n + 1):
                b = lat[300][0].get((r, 0))
                if b is None or (b[3] - b[1]) < 40:
                    continue
                for name, off in (("left", 2), ("right", 1)):
                    h = []
                    for dpi in (300, 600):
                        cs, nc = lat[dpi]
                        c = cs.get((r, nc - off))
                        if c is None:
                            h = None
                            break
                        h.append(pair_stats(_cell_crop(
                            m[dpi], c[0], c[1], c[2] - 1, c[3] - 1))["holes"])
                    if h is None or h == [0, 0]:
                        continue
                    tally[mode][name][0] += 1
                    tally[mode][name][1] += (h[0] != h[1])
                    cs, nc = lat[300]
                    c = cs[(r, nc - off)]
                    im = grey[300]
                    for y in range(c[1], min(c[3], im.height), 9):
                        levels[mode][name].update(
                            im.gray[y * im.width + c[0]:
                                    y * im.width + min(c[2], im.width)])
        print(f"  page {p} done", flush=True)

    print(f"\n{'render':<14} {'column':<7} {'cells':>7} "
          f"{'holes move 300->600':>22}")
    for mode in ALIAS:
        for name in ("left", "right"):
            n, mv = tally[mode][name]
            print(f"{mode:<14} {name:<7} {n:>7} "
                  f"{mv:>10} {100*mv/n if n else 0:>10.1f}%")
        print(f"{'':<14} grey levels inside the cells at 300 dpi: "
              f"left {len(levels[mode]['left'])}, "
              f"right {len(levels[mode]['right'])}")


if __name__ == "__main__":
    raise SystemExit(main())
