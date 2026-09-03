r"""581 -- numbers beside warp.py's contract.

`warp.py` was written contract-first and its docstring carries one
measurement, on one page, at one angle. Three things are missing and
each is a separate subcommand here:

  gap     A2. Is the transported mask's cycle growth `_fill_quad`'s
          scanline rounding, or is it geometry? Dilate by one pixel and
          re-count. THE CONTROL IS DILATING THE SOURCE TOO: dilation
          closes real holes as well as rounding gaps, so
          dilated-transport against raw-source would credit the fix for
          holes it merely filled. The paired comparison is
          dilate(transport) against dilate(source).

  sweep   A1. The crossover angle -- where transport stops being nearer
          than resample. One page cannot locate it, because the answer
          moves with how much of the ink is adjacent runs, so this
          takes three pages of stated, measured ink density.

  group   A3. min-area-rect gives an angle per BLOB; a glued fragment
          needs one per REGION. Groups blobs by near-pairs and reports
          the angle spread inside each group, on ink rotated by a known
          amount so the ground truth is exact.

POPULATION. Real page ink, crops of a stated size, at 300 dpi, with the
ink fraction printed beside every result -- a warp result quoted
without it is the shape units.md S4 records four times.
"""

from __future__ import annotations

import argparse
import math
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from inkdrill.pnmio import mask_from_pgm                 # noqa: E402
from inkdrill.qc import topology_of                      # noqa: E402
from inkdrill.raster import InkMask                      # noqa: E402
from inkdrill.warp import compare, resample, transport   # noqa: E402


def render(pdf: pathlib.Path, page: int, dpi: int, work: pathlib.Path):
    f = work / f"{pdf.stem[:30]}_p{page:03d}_r{dpi}.pgm"
    if not f.exists():
        subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH",
                        "-sDEVICE=pgmraw", f"-r{dpi}",
                        f"-dFirstPage={page}", f"-dLastPage={page}",
                        f"-sOutputFile={f}", str(pdf)], check=True)
    return mask_from_pgm(f, threshold=200)


def crop(mask: InkMask, x0: int, y0: int, w: int, h: int) -> InkMask:
    x1 = min(mask.width, x0 + w)
    y1 = min(mask.height, y0 + h)
    buf = bytearray()
    for y in range(y0, y1):
        buf += mask.data[y * mask.width + x0:y * mask.width + x1]
    return InkMask(bytes(buf), x1 - x0, y1 - y0)


def densest(mask: InkMask, w: int, h: int) -> tuple[int, int]:
    """The (x, y) of the w x h window holding the most ink, on a coarse
    grid. Picking the window by ink rather than by a fixed offset stops
    a crop of the margin being reported as a page result."""
    best, bxy = -1, (0, 0)
    step = max(64, w // 4)
    for y in range(0, max(1, mask.height - h), step):
        for x in range(0, max(1, mask.width - w), step):
            n = 0
            for yy in range(y, min(y + h, mask.height), 8):
                n += mask.data[yy * mask.width + x:
                               yy * mask.width + min(x + w, mask.width)
                               ].count(0xFF)
            if n > best:
                best, bxy = n, (x, y)
    return bxy


def dilate(mask: InkMask) -> InkMask:
    """One-pixel 8-connected dilation.

    Rows are shifted as big integers so the work happens in C rather
    than in a per-pixel Python loop; every byte is 0x00 or 0xFF, so OR
    keeps the package's mask encoding valid.
    """
    w, h = mask.width, mask.height
    if w == 0 or h == 0:
        return mask
    full = (1 << (8 * w)) - 1
    horiz = []
    for y in range(h):
        v = int.from_bytes(mask.data[y * w:(y + 1) * w], "big")
        horiz.append(((v | (v << 8) | (v >> 8)) & full))
    out = bytearray()
    for y in range(h):
        v = horiz[y]
        if y > 0:
            v |= horiz[y - 1]
        if y + 1 < h:
            v |= horiz[y + 1]
        out += v.to_bytes(w, "big")
    return InkMask(bytes(out), w, h)


def rot(deg: float, cx: float, cy: float):
    """Rotation about (cx, cy), in the package's row-vector order."""
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    return (c, s, -s, c,
            cx - c * cx + s * cy,
            cy - s * cx - c * cy)


def ink_pct(m: InkMask) -> float:
    return 100.0 * m.data.count(0xFF) / max(1, m.width * m.height)


PAGES = [("2002.06055", 6), ("1205.3463v2", 3), ("2005.05886", 5)]


def load(args, name, page):
    lib = args.library / name
    pdf = lib / f"{name}.pdf"
    if not pdf.is_file():
        cands = [f for f in lib.glob("*.pdf") if f.name != "report.pdf"]
        if len(cands) != 1:
            raise SystemExit(f"{name}: cannot identify the source pdf")
        pdf = cands[0]
    page_mask = render(pdf, page, args.dpi, args.work)
    x, y = densest(page_mask, args.size, args.size)
    return crop(page_mask, x, y, args.size, args.size)


def cmd_gap(args) -> int:
    print(f"A2 -- is the cycle growth rounding or geometry?  "
          f"{args.size}x{args.size} crops @ {args.dpi} dpi, "
          f"{args.angle} deg\n")
    print(f"{'document':<14} {'ink%':>6} | {'source':>14} {'transport':>15} "
          f"{'dilate(tr)':>15} {'dilate(src)':>15} {'resample':>14}")
    for name, page in PAGES:
        m = load(args, name, page)
        c = m.width / 2.0
        M = rot(args.angle, c, c)
        tr = transport(m, M)
        rs = resample(m, M)
        s_t, t_t = topology_of(m), topology_of(tr)
        dt, ds = topology_of(dilate(tr)), topology_of(dilate(m))
        r_t = topology_of(rs)
        f = lambda p: f"({p[0]}, {p[1]})"
        print(f"{name:<14} {ink_pct(m):>6.2f} | {f(s_t):>14} {f(t_t):>15} "
              f"{f(dt):>15} {f(ds):>15} {f(r_t):>14}", flush=True)
    print("\n(components, cycles). The question is whether dilate(tr) "
          "matches dilate(src),\nNOT whether it matches source: dilation "
          "closes real holes too.")
    return 0


def cmd_sweep(args) -> int:
    print(f"A1 -- the crossover.  {args.size}x{args.size} crops @ "
          f"{args.dpi} dpi\n")
    angles = [float(a) for a in args.angles.split(",")]
    for name, page in PAGES:
        m = load(args, name, page)
        c = m.width / 2.0
        print(f"{name}  ink {ink_pct(m):.2f}%   source "
              f"{topology_of(m)}")
        print(f"   {'deg':>6} {'transport':>15} {'resample':>15} "
              f"{'tr drift':>16} {'rs drift':>16}  {'comp':>5} {'cyc':>5} verdict")
        for a in angles:
            cmp_ = compare(m, rot(a, c, c))
            nc, ny = cmp_.nearer_by_channel
            v = cmp_.transport_is_nearer
            td = cmp_.transport_drift
            rd = cmp_.resample_drift
            print(f"   {a:>6.1f} {str(cmp_.transported):>15} "
                  f"{str(cmp_.resampled):>15} "
                  f"{td[0]:>7.3f},{td[1]:.3f} {rd[0]:>7.3f},{rd[1]:.3f}  "
                  f"{str(nc):>5} {str(ny):>5} "
                  f"{'transport' if v else ('resample' if v is False else 'SPLIT')}",
                  flush=True)
        print()
    return 0


def _hull(pts):
    """Andrew monotone chain. Returns the convex hull, CCW."""
    pts = sorted(set(pts))
    if len(pts) < 3:
        return pts

    def half(seq):
        out = []
        for p in seq:
            while len(out) >= 2:
                (ax, ay), (bx, by) = out[-2], out[-1]
                if (bx - ax) * (p[1] - ay) - (by - ay) * (p[0] - ax) > 0:
                    break
                out.pop()
            out.append(p)
        return out

    return half(pts)[:-1] + half(reversed(pts))[:-1]


def min_area_rect(pts):
    """(angle_deg, long, short) of the minimum-area enclosing rectangle.

    Rotating calipers' key fact: a minimum-area rectangle has a side
    FLUSH with a hull edge, so trying every hull edge is exact rather
    than a search. The angle is the LONG axis, reduced to [-90, 90).
    """
    h = _hull(pts)
    if len(h) < 3:
        return None
    best = None
    for i in range(len(h)):
        ax, ay = h[i]
        bx, by = h[(i + 1) % len(h)]
        ex, ey = bx - ax, by - ay
        n = math.hypot(ex, ey)
        if n == 0:
            continue
        ux, uy = ex / n, ey / n
        us = [p[0] * ux + p[1] * uy for p in h]
        vs = [-p[0] * uy + p[1] * ux for p in h]
        w = max(us) - min(us)
        hh = max(vs) - min(vs)
        area = w * hh
        if best is None or area < best[0]:
            ang = math.degrees(math.atan2(uy, ux))
            if w < hh:                      # the long axis, not the edge
                ang += 90.0
                w, hh = hh, w
            best = (area, ((ang + 90.0) % 180.0) - 90.0, w, hh)
    return None if best is None else (best[1], best[2], best[3])


def blobs(mask: InkMask, min_ink: int):
    """Each 8-connected component as (points, box, ink)."""
    from inkdrill.sweep import sweep as _sweep
    res = _sweep(mask, conn=8)
    node = {n.id: n for n in res.nodes}
    out = []
    for comp in res.components:
        pts, ink = [], 0
        x0 = y0 = 10 ** 9
        x1 = y1 = -1
        for i in comp.nodes:
            n = node[i]
            a, b, c, _d = n.as_run().image_span("row")
            ink += c - a + 1
            pts += [(a, b), (c + 1, b), (c + 1, b + 1), (a, b + 1)]
            x0 = min(x0, a); x1 = max(x1, c)
            y0 = min(y0, b); y1 = max(y1, b)
        if ink >= min_ink:
            out.append((pts, (x0, y0, x1, y1), ink))
    return out


def group_blobs(bs, gap: float):
    """Union-find over blobs whose BOXES come within `gap` pixels.

    Box distance, not centroid distance: two fragments of one broken
    stroke are near along their facing edges and can be far apart
    centre to centre, which is the case the grouping exists for.
    """
    parent = list(range(len(bs)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(bs)):
        ax0, ay0, ax1, ay1 = bs[i][1]
        for j in range(i + 1, len(bs)):
            bx0, by0, bx1, by1 = bs[j][1]
            dx = max(0, max(bx0 - ax1, ax0 - bx1))
            dy = max(0, max(by0 - ay1, ay0 - by1))
            if math.hypot(dx, dy) <= gap:
                a, b = find(i), find(j)
                if a != b:
                    parent[a] = b
    g = {}
    for i in range(len(bs)):
        g.setdefault(find(i), []).append(i)
    return list(g.values())


def cmd_group(args) -> int:
    """A3 -- one angle per REGION, not per blob."""
    import statistics
    print(f"A3 -- angle spread per blob against per group.  "
          f"{args.size}x{args.size} crop @ {args.dpi} dpi, "
          f"skew {args.angle} deg APPLIED (so the truth is exact), "
          f"gap {args.gap} px, min ink {args.min_ink}\n")
    for name, page in PAGES:
        m0 = load(args, name, page)
        c = m0.width / 2.0
        m = transport(m0, rot(args.angle, c, c))
        bs = blobs(m, args.min_ink)
        per = []
        for pts, _b, _i in bs:
            r = min_area_rect(pts)
            if r:
                per.append(r[0])
        groups = group_blobs(bs, args.gap)
        gang, spread, sizes = [], [], []
        for idx in groups:
            pts = [p for i in idx for p in bs[i][0]]
            r = min_area_rect(pts)
            if not r:
                continue
            gang.append(r[0])
            sizes.append(len(idx))
            mem = [min_area_rect(bs[i][0]) for i in idx]
            mem = [x[0] for x in mem if x]
            spread.append(max(mem) - min(mem) if len(mem) > 1 else 0.0)
        def med(v):
            return statistics.median(v) if v else float("nan")
        def iqr(v):
            if len(v) < 4:
                return float("nan")
            s = sorted(v)
            return s[int(.75 * len(s))] - s[int(.25 * len(s))]
        print(f"{name}  ink {ink_pct(m):.2f}%   {len(bs)} blobs -> "
              f"{len(groups)} groups (median size "
              f"{med(sizes):.0f}, max {max(sizes) if sizes else 0})")
        print(f"    per BLOB  angle median {med(per):>7.2f}  "
              f"IQR {iqr(per):>7.2f}  n={len(per)}")
        print(f"    per GROUP angle median {med(gang):>7.2f}  "
              f"IQR {iqr(gang):>7.2f}  n={len(gang)}")
        print(f"    within-group blob spread: median {med(spread):>6.2f} "
              f"deg, max {max(spread) if spread else 0:.2f}")
        multi = [s for s, n in zip(spread, sizes) if n > 1]
        print(f"    groups with >1 blob: {len(multi)}"
              + (f", their spread median {med(multi):.2f} deg" if multi else ""))
        print()
    return 0


def _box_down(grey: bytes, w: int, h: int, k: int):
    """Box-average the GREY by k, then the caller thresholds.

    Averaging before the threshold is what a scanner at the lower
    resolution actually does, and it is the only fair way to ask the
    dpi question: decimating the MASK instead would delete thin strokes
    by sampling rather than by tone, which is the resample failure mode
    and would put it into the source.
    """
    w2, h2 = w // k, h // k
    out = bytearray(w2 * h2)
    kk = k * k
    for y in range(h2):
        base = y * k
        row = y * w2
        for x in range(w2):
            x0 = x * k
            s = 0
            for dy in range(k):
                o = (base + dy) * w + x0
                s += sum(grey[o:o + k])
            out[row + x] = s // kk
    return bytes(out), w2, h2


def _png_dpi(f: pathlib.Path):
    """The pHYs dpi, from the header alone -- decoding a 34 Mpx PNG in
    pure Python to read one chunk costs ~24 s a page."""
    import struct
    raw = f.open("rb").read(4096)
    i = 8
    while i + 8 <= len(raw):
        ln = struct.unpack(">I", raw[i:i + 4])[0]
        tag = raw[i + 4:i + 8]
        if tag == b"pHYs":
            x, _y, u = struct.unpack(">IIB", raw[i + 8:i + 17])
            return round(x * 0.0254) if u == 1 else None
        if tag in (b"IDAT", b"IEND"):
            return None
        i += 12 + ln
    return None


def cmd_docreal(args) -> int:
    """589 -- the docstring's own corpus, at a stated dpi and threshold.

    warp.py's table was measured on DocReal scans; 581 measured
    RENDERED arXiv pages. That is a population difference, not a
    disagreement about the code, and it is the first thing to remove
    before asking about dpi or threshold.
    """
    from inkdrill.pngio import auto_mask, read_png
    D = args.docreal
    ids = [int(x) for x in args.ids.split(",")]
    # NATIVE RESOLUTION IS NOT UNIFORM IN THIS CORPUS: 38 of 50 DocReal
    # scans are 600 dpi and 12 are 72. A downsample factor is an
    # integer, so a mixed population puts one page's "100 dpi" request
    # at 72 and another's at 100, and the buckets stop being buckets.
    # The first grid run here did exactly that. Pages whose native
    # resolution is not `--native` are refused by name.
    kept = []
    for i in ids:
        f = D / f"{i}.png"
        if not f.is_file():
            print(f"  skip {i}: no file", flush=True)
            continue
        n = _png_dpi(f)
        if n is None or abs(n - args.native) > 1:
            print(f"  skip {i}: native {n} dpi, not {args.native}",
                  flush=True)
            continue
        kept.append(i)
    print(f"  {len(kept)} of {len(ids)} pages at {args.native} dpi native\n",
          flush=True)
    ids = kept
    excluded = 0
    inches = args.inches
    print(f"589 -- DocReal scans, threshold {args.threshold}, "
          f"{inches}in square crop at the densest window, "
          f"{args.angle} deg\n")
    print(f"{'page':>5} {'dpi':>5} {'crop':>10} {'ink%':>6} {'comp':>5} | "
          f"{'source':>13} {'transport':>13} {'dilate(tr)':>13} "
          f"{'dilate(src)':>13} {'resample':>13}   cycles")
    for i in ids:
        f = D / f"{i}.png"
        if not f.is_file():
            print(f"{i:>5}  missing {f}")
            continue
        img = read_png(f)
        native = img.dpi[0] if img.dpi else float(args.native)
        for dpi in [float(x) for x in args.dpis.split(",")]:
            k = max(1, int(round(native / dpi)))
            g, w, h = (img.gray, img.width, img.height) if k == 1 else \
                _box_down(img.gray, img.width, img.height, k)
            m0, _ = auto_mask(g, w, h, args.threshold)
            side = max(16, int(inches * native / k))
            x, y = densest(m0, side, side)
            m = crop(m0, x, y, side, side)
            c = m.width / 2.0
            M = rot(args.angle, c, c)
            tr = transport(m, M)
            s_t, t_t = topology_of(m), topology_of(tr)
            dt, ds = topology_of(dilate(tr)), topology_of(dilate(m))
            r_t = topology_of(resample(m, M))
            fmt = lambda p: f"({p[0]}, {p[1]})"
            grew = "GROW" if t_t[1] > s_t[1] else "shrink"
            # A CROP WITH TOO FEW COMPONENTS CANNOT CARRY THE CLAIM.
            # At 100 dpi a 1.5in crop is 150 px and the earlier grid
            # produced rows of 12 components, where one merged blob
            # moves the cycle count by more than the effect. Excluded
            # BY COUNT and the exclusions are printed, never silent.
            if s_t[0] < args.min_comp:
                excluded += 1
                print(f"{i:>5} {native/k:>5.0f} {m.width}x{m.height:<5} "
                      f"{ink_pct(m):>6.2f} {s_t[0]:>5} | "
                      f"EXCLUDED: under {args.min_comp} components",
                      flush=True)
                continue
            print(f"{i:>5} {native/k:>5.0f} {m.width}x{m.height:<5} "
                  f"{ink_pct(m):>6.2f} {s_t[0]:>5} | {fmt(s_t):>13} "
                  f"{fmt(t_t):>13} {fmt(dt):>13} {fmt(ds):>13} "
                  f"{fmt(r_t):>13}   {grew}", flush=True)
    print(f"\n{excluded} rows excluded for under {args.min_comp} "
          f"components", flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("gap", "sweep", "group", "docreal"))
    ap.add_argument("--library", type=pathlib.Path,
                    default=pathlib.Path.home() / "pdfdrill-library")
    ap.add_argument("--work", type=pathlib.Path,
                    default=pathlib.Path.home() / "inkdrill-work" / "warp581")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--size", type=int, default=600)
    ap.add_argument("--angle", type=float, default=7.0)
    ap.add_argument("--angles", default="0,0.5,1,2,3,5,7,10,15,20,30,45")
    ap.add_argument("--gap", type=float, default=6.0,
                    help="box gap under which two blobs join a group")
    ap.add_argument("--min-ink", type=int, default=12)
    ap.add_argument("--docreal", type=pathlib.Path,
                    default=pathlib.Path.home() / "Downloads/DocReal/scanned")
    ap.add_argument("--ids", default="1,3,6")
    ap.add_argument("--dpis", default="600,300,150")
    ap.add_argument("--inches", type=float, default=1.5)
    ap.add_argument("--threshold", type=int, default=200)
    ap.add_argument("--native", type=int, default=600,
                    help="refuse pages whose native pHYs dpi is not this")
    ap.add_argument("--min-comp", type=int, default=20,
                    help="a crop with fewer source components is excluded "
                         "and the exclusion is printed")
    args = ap.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    return {"gap": cmd_gap, "sweep": cmd_sweep, "group": cmd_group,
            "docreal": cmd_docreal}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
