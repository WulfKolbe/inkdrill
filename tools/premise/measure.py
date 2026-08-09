"""Measurement harness for the figures quoted in docs/units.md §3.

NOT part of the package and NOT part of the test suite. It exists so that
every measured claim in units.md is a RE-RUN rather than a
re-implementation -- when the corpus grows, when signature() gains
persistence, or when a reviewer wants to check a number.

    python3 tools/premise/measure.py --corpus ~/pdfdrill-library all
    python3 tools/premise/measure.py --corpus ~/pdfdrill-library rotation

Every subcommand prints the figure exactly as units.md quotes it, so a
mismatch is visible without arithmetic.

Subcommands
-----------
neutrality   share of corpus pages taking the colour decode path
colour       whether that colour is real content or a render artefact
throughput   decode throughput, neutral and colour paths, vs the naive
             reference decoder
skew         projection-profile skew of scanned pages
premise      hole count and signature stability vs pdfminer ground truth
contraction  RAG runs -> Reeb arcs reduction on real page ink
rotation     signature survival under resampled rotation
white        page layout from the GAPS -- ink-bounded white runs, cross-
             checked against the declared image rectangles
border       what the pixels just outside a component's runs say about
             the field it sits on -- 2 samples per run
boxes        drawn frames and filled panels from ink, cross-checked
             against the rectangles the PDF itself declares
outlines     U9 rasterizer premise: which outline format maths glyphs are
             in, and whether it is reachable without a PDF parser
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import random
import re
import struct
import sys
import time
import zlib
from collections import Counter, defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from inkdrill.pngio import _is_neutral, load_mask, read_png  # noqa: E402
from inkdrill.raster import INK, InkMask, binarize, iter_runs  # noqa: E402
from inkdrill.aggregate import (component_moments, moments_of_mask,  # noqa: E402
                                moments_per_component)
from inkdrill.band import canonical, stitch, sweep_bands, sweep_banded  # noqa: E402
from inkdrill.nest import Kind, nest  # noqa: E402
from inkdrill.font import (Usability, coverage as font_coverage, inventory,  # noqa: E402
                           family_of, is_math_family,
                           normalise as fnormalise)
from inkdrill.classify import (Channels, Classifier, Template,  # noqa: E402
                               confusion as classify_confusion, normalise)
from inkdrill.coverage import Box, CoverageClass, Region, check  # noqa: E402
from inkdrill.domains import (DIMENSIONS, Domain, convexity, describe,  # noqa: E402
                              dimensions_of, efficiency,
                              joint_mutual_information, mi_ceiling,
                              mutual_information)
from inkdrill.gold import (Component as GComp, Glyph as GGlyph,  # noqa: E402
                           MatchKind, match, page_transform)
from inkdrill.sched import Task, page_tasks, run as sched_run  # noqa: E402
from inkdrill.reeb import contract, graph_of, orient, signature, Direction  # noqa: E402
from inkdrill.sweep import Capture, sweep                   # noqa: E402


# --------------------------------------------------------------------------
# corpus plumbing
# --------------------------------------------------------------------------

def pages(root: pathlib.Path):
    return sorted(root.glob("*/inspect/pages/*.png"))


def inflate(path: pathlib.Path):
    """(width, height), inflated filtered scanlines -- for probes that must
    see the stream before unfiltering."""
    raw = path.read_bytes()
    i, idat, hdr = 8, [], None
    while i < len(raw):
        ln, typ = struct.unpack(">I4s", raw[i:i + 8])
        if typ == b"IHDR":
            hdr = struct.unpack(">IIBBBBB", raw[i + 8:i + 8 + ln])
        elif typ == b"IDAT":
            idat.append(raw[i + 8:i + 8 + ln])
        i += 12 + ln
    return (hdr[0], hdr[1]), zlib.decompress(b"".join(idat))


def naive_unfilter(dec, w, h):
    """The reference decoder, kept here as the throughput baseline."""
    stride = w * 3 + 1
    prev = bytearray(w * 3)
    out = []
    for r in range(h):
        ft = dec[r * stride]
        line = bytearray(dec[r * stride + 1:(r + 1) * stride])
        for i in range(len(line)):
            a = line[i - 3] if i >= 3 else 0
            b = prev[i]
            c = prev[i - 3] if i >= 3 else 0
            if ft == 1:
                line[i] = (line[i] + a) & 0xFF
            elif ft == 2:
                line[i] = (line[i] + b) & 0xFF
            elif ft == 3:
                line[i] = (line[i] + ((a + b) >> 1)) & 0xFF
            elif ft == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if (pa <= pb and pa <= pc)
                                      else (b if pb <= pc else c))) & 0xFF
        prev = line
        out.append(bytes(line))
    return b"".join(out)


def components(mask, *, min_area=25, min_side=6, max_px=200_000):
    """Every component rebuilt from its OWN runs into a clean sub-mask.

    Cropping a bounding box instead would swallow neighbouring ink and
    clip strokes -- see the `premise` subcommand's note.
    """
    res = sweep(mask, axis="row", conn=8, capture=Capture.GRAPH)
    node = {n.id: n for n in res.nodes}
    out = []
    for comp in res.components:
        runs = [node[i] for i in comp.nodes]
        if sum(r.hi - r.lo + 1 for r in runs) < min_area:
            continue
        x0 = min(r.lo for r in runs); x1 = max(r.hi for r in runs)
        y0 = min(r.line for r in runs); y1 = max(r.line for r in runs)
        w, h = x1 - x0 + 1, y1 - y0 + 1
        if w < min_side or h < min_side or w * h > max_px:
            continue
        buf = bytearray(w * h)
        for r in runs:
            base = (r.line - y0) * w - x0
            buf[base + r.lo: base + r.hi + 1] = b"\xff" * (r.hi - r.lo + 1)
        out.append(((x0, y0, x1, y1), InkMask(bytes(buf), w, h)))
    return out


def rotate(mask, deg):
    """Nearest-neighbour rotation about the centre. Deliberately crude --
    it is the harsh case, and the point is what survives it."""
    w, h = mask.width, mask.height
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    nw = int(abs(w * c) + abs(h * s)) + 2
    nh = int(abs(w * s) + abs(h * c)) + 2
    cx, cy, ncx, ncy = w / 2, h / 2, nw / 2, nh / 2
    out = bytearray(nw * nh)
    d = mask.data
    for y in range(nh):
        dy = y - ncy
        for x in range(nw):
            dx = x - ncx
            sx = int(cx + dx * c + dy * s)
            sy = int(cy - dx * s + dy * c)
            if 0 <= sx < w and 0 <= sy < h and d[sy * w + sx]:
                out[y * nw + x] = INK
    return InkMask(bytes(out), nw, nh)


# --------------------------------------------------------------------------
# measurements
# --------------------------------------------------------------------------

def m_neutrality(root, n, rng):
    """units.md: 54.0% of 400 pages across 361 documents are non-neutral."""
    sample = rng.sample(pages(root), n)
    neut = col = 0
    bydoc = defaultdict(set)
    ihdr = Counter()
    mix = Counter()
    for f in sample:
        (w, h), dec = inflate(f)
        stride = w * 3 + 1
        for r in range(h):
            mix[dec[r * stride]] += 1
        ok = _is_neutral(dec, w, h)
        neut += ok
        col += not ok
        bydoc[f.parent.parent.parent.name].add(ok)
        ihdr[(8, 2, 0, 0, 0)] += 1
    tot = neut + col
    print(f"pages sampled          {tot}")
    print(f"documents represented  {len(bydoc)}")
    print(f"neutral                {neut} ({neut/tot:.1%})")
    print(f"non-neutral (colour)   {col} ({col/tot:.1%})")
    print(f"documents mixing both  {sum(1 for v in bydoc.values() if len(v) > 1)}")
    total = sum(mix.values())
    names = {0: "None", 1: "Sub", 2: "Up", 3: "Average", 4: "Paeth"}
    print("filter mix             " + "  ".join(
        f"{names[k]} {v/total:.1%}" for k, v in sorted(mix.items())))


def m_colour(root, n, rng):
    """units.md: 70.0% of non-neutral pages carry substantial colour."""
    buckets = Counter()
    seen = 0
    for f in rng.sample(pages(root), n * 12):
        if seen >= n:
            break
        (w, h), dec = inflate(f)
        if _is_neutral(dec, w, h):
            continue
        rgb = naive_unfilter(dec, w, h)
        seen += 1
        strong = 0
        maxspread = 0
        for i in range(0, len(rgb), 3):
            d = max(rgb[i], rgb[i+1], rgb[i+2]) - min(rgb[i], rgb[i+1], rgb[i+2])
            if d > maxspread:
                maxspread = d
            if d > 32:
                strong += 1
        frac = strong / (w * h)
        if maxspread <= 16:
            buckets["fringing only (max spread <= 16)"] += 1
        elif frac < 1e-3:
            buckets["minor colour (<0.1% strong px)"] += 1
        else:
            buckets["substantial colour (>=0.1% strong px)"] += 1
    print(f"non-neutral pages classified  {seen}")
    for k, v in buckets.most_common():
        print(f"  {v:4} ({v/seen:5.1%})  {k}")


def m_throughput(root, n, rng):
    """units.md: neutral 18-21 Mpx/s median, colour 1.78, naive 1.82."""
    from inkdrill.pngio import _decode_gray_colour, _decode_gray_neutral
    fast, slow, colour = [], [], []
    for f in rng.sample(pages(root), n * 8):
        if len(fast) >= n and len(colour) >= n:
            break
        (w, h), dec = inflate(f)
        if _is_neutral(dec, w, h):
            if len(fast) >= n:
                continue
            t = time.perf_counter(); _decode_gray_neutral(dec, w, h)
            fast.append(w * h / (time.perf_counter() - t) / 1e6)
            t = time.perf_counter(); naive_unfilter(dec, w, h)
            slow.append(w * h / (time.perf_counter() - t) / 1e6)
        else:
            if len(colour) >= n:
                continue
            t = time.perf_counter(); _decode_gray_colour(dec, w, h)
            colour.append(w * h / (time.perf_counter() - t) / 1e6)
    def stat(v, label):
        v = sorted(v)
        if not v:
            print(f"{label:34} no pages"); return
        print(f"{label:34} median {v[len(v)//2]:6.2f}  "
              f"p10 {v[len(v)//10]:6.2f}  p90 {v[9*len(v)//10]:7.2f}  "
              f"n={len(v)}")
    stat(fast, "neutral fast path (Mpx/s)")
    stat(colour, "colour path (Mpx/s)")
    stat(slow, "naive reference (Mpx/s)")


def m_skew(root, n, rng):
    """units.md: the scanned corpus is pre-deskewed, max 0.50 deg."""
    scans = [p for p in pages(root) if "Z-Library" in str(p)]
    if not scans:
        print("no (Z-Library) scans under this corpus root")
        return
    out = []
    for f in rng.sample(scans, min(n, len(scans))):
        img = read_png(f)
        mask = binarize(img.gray, img.width, img.height)
        w, h = mask.width, mask.height
        ink = []
        for y in range(0, h, 4):
            row = mask.data[y*w:(y+1)*w]
            ink.extend((x, y) for x in range(0, w, 4) if row[x])
        if len(ink) < 500:
            continue
        best = (None, -1)
        a = -4.0
        while a <= 4.0:
            t = math.tan(math.radians(a))
            b = Counter(int(y - x*t) >> 2 for x, y in ink)
            v = sum(c*c for c in b.values())
            if v > best[1]:
                best = (a, v)
            a += 0.25
        out.append(best[0])
        print(f"  {f.parent.parent.parent.name[:44]:44} skew {best[0]:+.2f} deg")
    if out:
        print(f"\n|skew| >= 0.25 on {sum(1 for a in out if abs(a) >= 0.25)}"
              f"/{len(out)};  max |skew| {max(abs(a) for a in out):.2f} deg")


def m_premise(root, n_pages, rng):
    """units.md: hole count 98.7-100% vs character identity; 26.9% purity.

    NOTE the failure this method exists to avoid: cropping each glyph's
    pdfminer bbox gives a useless result, because that is the ADVANCE box,
    not the ink box. Components are rebuilt from their own runs instead.
    """
    docs = [(cj.parent, cj) for cj in sorted(root.glob("*/*.chars.json"))
            if (cj.parent / "inspect" / "pages").is_dir()]
    by_char = defaultdict(list)
    done = 0
    for doc, cj in docs:
        if done >= n_pages:
            break
        try:
            data = json.load(cj.open())
        except Exception:
            continue
        for page in data["pages"]:
            pdir = doc / "inspect" / "pages"
            png = next((pdir / p for p in
                        (f"p{page['page_number']}.png",
                         f"page-{page['page_number']:04d}.png")
                        if (pdir / p).exists()), None)
            if png is None:
                continue
            img = read_png(png)
            sx = img.width / page["width"]
            sy = img.height / page["height"]
            if abs(sx - sy) / sx > 0.01:
                continue
            mask = binarize(img.gray, img.width, img.height)
            glyphs = [(c["text"], c["x0"]*sx, (page["height"]-c["y1"])*sy,
                       c["x1"]*sx, (page["height"]-c["y0"])*sy)
                      for c in page["chars"]
                      if c.get("text") and len(c["text"]) == 1
                      and c["text"].strip()]
            for (cx0, cy0, cx1, cy1), sub in components(mask):
                ccx, ccy = (cx0+cx1)/2, (cy0+cy1)/2
                hits = [g for g in glyphs
                        if g[1] <= ccx <= g[3] and g[2] <= ccy <= g[4]]
                if len(hits) != 1:
                    continue
                t, gx0, _, gx1, _ = hits[0]
                if cx0 < gx0 - 3 or cx1 > gx1 + 3:
                    continue
                by_char[t].append(signature(graph_of(sub)))
            done += 1
            print(f"  {doc.name[:28]:28} p{page['page_number']:<3} "
                  f"{sum(len(v) for v in by_char.values()):6} glyphs so far")
            if done >= n_pages:
                break
    tot = sum(len(v) for v in by_char.values())
    print(f"\nisolated glyph components {tot}, distinct characters "
          f"{len(by_char)}\n")
    print("hole count vs character identity:")
    for c in "eaoibdgpqRA0lnrstuvwx":
        if c in by_char:
            h = Counter(s.cycles for s in by_char[c])
            mval, mn = h.most_common(1)[0]
            print(f"  {c!r}  modal cycles={mval}  "
                  f"consistency {mn/sum(h.values()):6.1%}  n={sum(h.values())}")
    s2c = defaultdict(Counter)
    for c, v in by_char.items():
        for s in v:
            s2c[s][c] += 1
    total = sum(sum(x.values()) for x in s2c.values())
    pure = sum(sum(x.values()) for x in s2c.values() if len(x) == 1)
    print(f"\ndistinct signatures {len(s2c)}; single-character signature "
          f"{pure}/{total} ({pure/total:.1%})")
    print("worst collisions:")
    for s, cc in sorted(s2c.items(), key=lambda x: -len(x[1]))[:4]:
        print(f"  {' '.join(repr(c) for c, _ in cc.most_common(9))}")


def m_contraction(root, n, rng):
    """units.md: 3,947 runs -> 566 arcs, 14-19% on real page ink."""
    for f in rng.sample(pages(root), n):
        img = read_png(f)
        mask = binarize(img.gray, img.width, img.height)
        band = InkMask(mask.data[:mask.width * 600], mask.width, 600)
        res = sweep(band, axis="row", conn=8, capture=Capture.GRAPH)
        g = contract(res)
        genuine = contract(sweep(
            InkMask(b"".join(band.data[(600-1-y)*band.width:(600-y)*band.width]
                             for y in range(600)), band.width, 600),
            axis="row", conn=8, capture=Capture.GRAPH))
        derived = orient(res, Direction.ROW_UP)
        g3 = (derived.node_count, derived.edge_count) == \
             (genuine.node_count, genuine.edge_count)
        print(f"  {f.parent.parent.parent.name[:30]:30} "
              f"{res.node_count:6} runs -> {g.node_count:5} arcs "
              f"({g.node_count/max(1,res.node_count):5.1%})   "
              f"G3 {'OK' if g3 else 'MISMATCH'}")


def m_rotation(root, n, rng):
    """units.md: full signature survives +-3 deg 47-54%, cycles 84%."""
    glyphs = []
    for f in rng.sample(pages(root), 40):
        if len(glyphs) >= n:
            break
        img = read_png(f)
        mask = binarize(img.gray, img.width, img.height)
        band = InkMask(mask.data[:mask.width * 900], mask.width, 900)
        glyphs.extend(sub for _, sub in components(band))
    glyphs = glyphs[:n]
    print(f"real glyph components tested: {len(glyphs)}")
    for ang in (0.0, 0.5, 1.0, 3.0, -3.0):
        same = cyc = 0
        for gm in glyphs:
            a = signature(graph_of(gm))
            b = signature(graph_of(rotate(gm, ang)))
            same += a == b
            cyc += a.cycles == b.cycles
        tag = "  (control)" if ang == 0.0 else ""
        print(f"  rotation {ang:+5.1f} deg: full signature kept "
              f"{same/len(glyphs):6.1%}   cycles kept "
              f"{cyc/len(glyphs):6.1%}{tag}")


def m_moments(root, n, rng):
    """units.md: row and col moments are IDENTICAL, per component and in
    total -- assumption 4, on real ink rather than random masks."""
    raw = lambda x: (x.area, x.sx, x.sy, x.sxx, x.syy, x.sxy)
    pages_ok = comps = 0
    for f in rng.sample(pages(root), n):
        img = read_png(f)
        mask = binarize(img.gray, img.width, img.height)
        band = InkMask(mask.data[:mask.width * 700], mask.width, 700)
        r = [raw(x) for x in component_moments(band, "row")]
        c = [raw(x) for x in component_moments(band, "col")]
        total = moments_of_mask(band)
        g7 = sum(x.area for x in component_moments(band, "row")) == total.area
        pages_ok += r == c
        comps += len(r)
        print(f"  {f.parent.parent.parent.name[:32]:32} {len(r):5} components"
              f"   G2 {'OK' if r == c else 'MISMATCH'}"
              f"   G7 area {'OK' if g7 else 'MISMATCH'}")
    print(f"\nG2 on real ink: {pages_ok}/{n} pages, {comps} components compared")


def m_nesting(root, n, rng):
    """units.md G1/assumption 3: nest's hole count, computed as background
    components of the inverted mask, must equal U3's cycle rank. The two
    share no code -- each is the other's oracle."""
    agree = disagree = 0
    examples = []
    for f in rng.sample(pages(root), n):
        img = read_png(f)
        mask = binarize(img.gray, img.width, img.height)
        band = InkMask(mask.data[:mask.width * 400], mask.width, 400)
        for (x0, y0, x1, y1), sub in components(band, min_area=1, min_side=1):
            res = sweep(sub, axis="row", conn=8, capture=Capture.GRAPH)
            got = nest(sub).hole_count
            if got == res.cycle_count:
                agree += 1
            else:
                disagree += 1
                if len(examples) < 5:
                    examples.append((res.cycle_count, got, sub.width, sub.height))
        print(f"  {f.parent.parent.parent.name[:32]:32} "
              f"{agree + disagree:5} components so far")
    tot = agree + disagree
    print(f"\ncomponents compared            {tot}")
    print(f"nest holes == U3 cycle_count   {agree} ({agree/max(1,tot):.2%})")
    print(f"disagree                       {disagree}")
    for cyc, got, w, h in examples:
        print(f"    cycle_count={cyc} nest={got}  ({w}x{h})")


def m_banding(root, n, rng):
    """units.md U7 G2: a stitched banded sweep must be indistinguishable
    from a single sweep, at every K, on real page ink."""
    for f in rng.sample(pages(root), n):
        img = read_png(f)
        mask = binarize(img.gray, img.width, img.height)
        band = InkMask(mask.data[:mask.width * 600], mask.width, 600)
        whole = sweep(band, axis="row", conn=8, capture=Capture.GRAPH)
        want = canonical(whole)
        line = f"  {f.parent.parent.parent.name[:28]:28} V={whole.node_count:6} "
        for k in (1, 2, 3, 7, 64, 600):
            got = canonical(sweep_banded(band, k))
            line += f" K={k}:{'OK' if got == want else 'DIFF'}"
        print(line)


def m_stitchcost(root, n, rng):
    """units.md 3 "U7 stitch cost": stitch is serial, so it is an Amdahl
    floor on band parallelism. Reports the ceiling no scheduler can beat."""
    import pickle

    def best(fn, reps=3):
        t = float("inf")
        r = None
        for _ in range(reps):
            s = time.perf_counter()
            r = fn()
            t = min(t, time.perf_counter() - s)
        return t, r

    for f in rng.sample(pages(root), n):
        img = read_png(f)
        mask = binarize(img.gray, img.width, img.height)
        band = InkMask(mask.data[:mask.width * 800], mask.width, 800)
        t_sweep, res = best(lambda: sweep(band, axis="row", conn=8,
                                          capture=Capture.GRAPH))
        print(f"  {f.parent.parent.parent.name[:34]:34} V={res.node_count:6} "
              f"sweep {t_sweep*1000:6.1f} ms")
        for k in (1, 8, 64, 256):
            t_b, bands = best(lambda k=k: sweep_bands(band, k))
            t_s, _ = best(lambda b=bands: stitch(b))
            wall = t_b / k + t_s
            print(f"     K={k:4} stitch {t_s*1000:6.1f} ms "
                  f"({t_s/t_sweep:4.2f}x sweep)  ideal wall {wall*1000:6.1f} ms"
                  f"  speedup {t_sweep/wall:4.2f}x  ceiling {t_sweep/t_s:4.2f}x")
        # serialization, both parallel tiers (assumption 9)
        bands = sweep_bands(band, 64)
        allb = sum(len(pickle.dumps(b, protocol=5)) for b in bands)
        node = {x.id: x for x in res.nodes}
        allc = sum(len(pickle.dumps([node[i].as_run() for i in c.nodes],
                                    protocol=5)) for c in res.components)
        print(f"     serialization: 64 bands {allb/1e6:5.2f} MB, "
              f"{res.component_count} components {allc/1e6:5.2f} MB, "
              f"raw mask {len(band.data)/1e6:5.2f} MB")


def _page_job(path_str):
    """Module-level so a process pool can pickle it."""
    img = read_png(pathlib.Path(path_str))
    mask = binarize(img.gray, img.width, img.height)
    res = sweep(mask, axis="row", conn=8, capture=Capture.GRAPH)
    return (img.width * img.height, res.component_count)


def m_schedcost(root, n, rng):
    """units.md 3 "U8 premise check": where per-page time goes, and what
    page-parallel scaling actually delivers. WARNING: slow -- it decodes
    every sampled page several times over."""
    import multiprocessing as mp

    sample = [str(p) for p in rng.sample(pages(root), n)]
    print(f"  cores {mp.cpu_count()}   pages {len(sample)}")

    # stage breakdown
    dec = swp = 0.0
    per = []
    for s in sample:
        p = pathlib.Path(s)
        t0 = time.perf_counter(); img = read_png(p); d = time.perf_counter() - t0
        mask = binarize(img.gray, img.width, img.height)
        t0 = time.perf_counter()
        sweep(mask, axis="row", conn=8, capture=Capture.GRAPH)
        sw = time.perf_counter() - t0
        dec += d; swp += sw
        per.append(d + sw)
    tot = dec + swp
    print(f"  decode {dec:6.1f}s ({dec/tot:5.1%})   sweep {swp:6.1f}s "
          f"({swp/tot:5.1%})")
    print(f"  Amdahl ceiling, parallelise sweep only : {tot/(tot-swp):5.2f}x")
    print(f"  Amdahl ceiling, parallelise decode     : {tot/(tot-dec):5.2f}x")
    per.sort()
    print(f"  per-page cost spread: {per[-1]/max(per[0], 1e-9):6.1f}x "
          f"(min {per[0]:.2f}s  max {per[-1]:.2f}s)")

    tasks = page_tasks(sample)
    base = sched_run(tasks, _page_job, workers=1)
    print(f"  serial {base.wall_seconds:6.2f} s   "
          f"Amdahl ceiling from longest task {base.amdahl_ceiling:5.2f}x")
    for k in (2, 4, 8, mp.cpu_count()):
        rep = sched_run(tasks, _page_job, workers=k)
        assert rep.values() == base.values(), "worker count changed the answer"
        print(f"    workers {k:3}: wall {rep.wall_seconds:6.2f} s  "
              f"speedup {base.wall_seconds/rep.wall_seconds:5.2f}x  "
              f"utilisation {rep.utilisation:5.1%}")


def m_fonts(root, n, rng):
    """units.md 3 "U9 premise check": glyph-weighted font coverage. The
    metric matters -- per-document this reads ~17%, per-glyph ~95%."""
    from collections import Counter
    cands = [(cj.parent, cj, list(cj.parent.glob("*.pdf"))[0])
             for cj in sorted(root.glob("*/*.chars.json"))
             if list(cj.parent.glob("*.pdf"))]
    if not cands:
        print("  no documents with both chars.json and a pdf")
        return
    tot = Counter()
    mth = Counter()
    fams = Counter()
    ndoc = allok = 0
    for d, cj, pdf in rng.sample(cands, min(n, len(cands))):
        try:
            recs = inventory(pdf)
            data = json.load(cj.open())
        except Exception as exc:
            print(f"  skip {d.name[:26]}: {exc!r}"[:90])
            continue
        names = [ch["fontname"] for pg in data["pages"] for ch in pg["chars"]
                 if ch.get("text", "").strip()]
        if not names:
            continue
        cov = font_coverage(names, recs)
        ndoc += 1
        allok += cov.fraction == 1.0
        for k, v in cov.counts.items():
            tot[k] += v
        for k, v in cov.math_counts().items():
            mth[k] += v
        for fam, c in cov.by_family.items():
            if is_math_family(fam):
                fams[fam] += sum(c.values())
    total = sum(tot.values())
    if not total:
        print("  no glyphs")
        return
    print(f"  {ndoc} documents, {total} glyph instances")
    for k, v in tot.most_common():
        print(f"    {v:8} ({v/total:6.2%})  {k.value}")
    print(f"  fast-path share {tot[Usability.FAST_PATH]/total:.2%};  "
          f"documents fully on it {allok}/{ndoc}")
    m = sum(mth.values())
    if m:
        print(f"  MATHS glyphs {m} ({m/total:.2%} of all): "
              f"{mth[Usability.FAST_PATH]/m:.2%} on the fast path")
        for k, v in mth.most_common():
            if k is not Usability.FAST_PATH:
                print(f"    {v:7} ({v/m:6.2%})  {k.value}")
        print("  maths families by volume: " +
              ", ".join(f"{f} {c}" for f, c in fams.most_common(6)))
    else:
        print("  MATHS glyphs: none seen in this sample")


def _kpsewhich(names):
    """Where the TeX tree keeps these font files, or None.

    One subprocess per call, several candidate filenames per call;
    kpsewhich prints one line per name it FINDS and nothing for the rest,
    so the first line is the first candidate that exists. Callers must
    therefore pass candidates in preference order and must not try to
    join the output back to the input list positionally.
    """
    import subprocess
    try:
        out = subprocess.run(["kpsewhich", *names], capture_output=True,
                             text=True, timeout=20).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return out.split("\n")[0] or None if out else None


def m_outlines(root, n, rng):
    """U9 rasterizer premise check: for the glyphs a maths classifier
    must template, WHICH outline format is the program in, and is that
    program reachable without writing a PDF parser?

    Two routes are open and they are different modules:

      A  extract the font program from the PDF -- needs an xref walker,
         an object-stream inflater, and then one parser per format
      B  find the same font in the TeX tree by name -- needs no PDF
         parsing at all, and subsetting removes glyphs without altering
         the outlines of the ones that remain

    POPULATION: glyph instances, not font entries and not documents.
    U9's inventory already showed those three denominators disagree by
    78 points on the same corpus. SPLIT: documents sampled without
    replacement; every glyph instance of a sampled document counts.
    FILTER: glyphs whose `text` is blank are dropped (they are advance
    records, not ink); the count kept and dropped is printed.
    """
    cands = [(cj.parent, cj, list(cj.parent.glob("*.pdf"))[0])
             for cj in sorted(root.glob("*/*.chars.json"))
             if list(cj.parent.glob("*.pdf"))]
    if not cands:
        print("  no documents with both chars.json and a pdf")
        return
    if _kpsewhich(["cmr10.pfb"]) is None:
        print("  NOTE: kpsewhich found nothing -- route B numbers below "
              "measure this machine's TeX tree, not the corpus")

    kind_all, kind_math = Counter(), Counter()
    disk_math, disk_all = Counter(), Counter()
    missing_families = Counter()
    kept_fams, drop_fams = Counter(), Counter()
    joint = Counter()
    ndoc = kept = dropped = 0
    raw_ok = raw_docs = 0
    where = {}

    for d, cj, pdf in rng.sample(cands, min(n, len(cands))):
        try:
            recs = inventory(pdf)
            data = json.load(cj.open())
        except Exception as exc:
            print(f"  skip {d.name[:26]}: {exc!r}"[:90])
            continue
        by_base = {}
        for r in recs:
            # An embedded record beats a non-embedded one of the same
            # base name, exactly as font.resolve does (G4).
            cur = by_base.get(r.base_name)
            if cur is None or (r.embedded and not cur.embedded):
                by_base[r.base_name] = r
        names = Counter()
        for pg in data["pages"]:
            for ch in pg["chars"]:
                if ch.get("text", "").strip():
                    names[ch["fontname"]] += 1
                else:
                    dropped += 1
        if not names:
            continue
        ndoc += 1

        # Route A proxy: are the font-program streams visible in the
        # uncompressed object layer? If /FontFile* tokens are fewer than
        # the embedded fonts, the descriptors sit inside object streams
        # and route A needs an ObjStm decoder before it can even look.
        try:
            blob = pdf.read_bytes()
        except OSError:
            blob = b""
        if blob:
            raw_docs += 1
            seen = sum(blob.count(b"/FontFile" + s) for s in (b"", b"2", b"3"))
            n_emb = sum(1 for r in recs if r.embedded)
            raw_ok += seen >= n_emb > 0

        for name, count in names.items():
            base = fnormalise(name)
            rec = by_base.get(base)
            kind = rec.kind.value if rec else "unresolved"
            math = is_math_family(name)
            kept += count
            kind_all[kind] += count
            if math:
                kind_math[kind] += count
            if base not in where:
                stem = base.split(",")[0].lower()
                where[base] = _kpsewhich([stem + e for e in
                                          (".pfb", ".otf", ".ttf", ".pfa")])
            hit = where[base] is not None
            disk_all[hit] += count
            (kept_fams if math else drop_fams)[family_of(name)] += count
            if math:
                disk_math[hit] += count
                # The format ON DISK is what a route-B parser must read,
                # and it need not match what the PDF embedded: a
                # producer may ship Type 1C for a font the TeX tree
                # keeps as a .pfb. Record both or the parser count is a
                # guess.
                ext = pathlib.Path(where[base]).suffix if hit else "-"
                joint[(kind, ext)] += count
                if not hit:
                    missing_families[base] += count

    if not kept:
        print("  no glyphs")
        return
    m = sum(kind_math.values())
    print(f"  {ndoc} documents, {kept} glyph instances kept, "
          f"{dropped} blank dropped")
    print(f"  MATHS glyph instances {m} ({m/kept:.2%} of kept)")

    def table(label, c, total):
        print(f"  {label} (weighted by glyph instance, n={total}):")
        for k, v in c.most_common():
            print(f"    {v:8} ({v/total:6.2%})  {k}")

    table("outline program format, ALL glyphs", kind_all, kept)
    if m:
        table("outline program format, MATHS glyphs", kind_math, m)
        print(f"  route B -- font present in the TeX tree: "
              f"{disk_math[True]/m:.2%} of maths glyph instances "
              f"({disk_math[True]}/{m})")
        if missing_families:
            print("    maths fonts NOT on disk: " + ", ".join(
                f"{b} {c}" for b, c in missing_families.most_common(6)))
        # The two routes only substitute for each other if route B's
        # hits are spread across formats. If route B covers exactly the
        # formats route A would have handled, both are still needed and
        # the marginals above are misleading.
        print("  MATHS joint -- format in PDF x format on disk (the "
              "marginals do not decide this):")
        for (k, ext), v in sorted(joint.items(), key=lambda kv: -kv[1]):
            print(f"    {v:8} ({v/m:6.2%})  {k:<14} -> "
                  f"{ext if ext != '-' else 'NOT on disk'}")
    print(f"  route B -- font present in the TeX tree, all glyphs: "
          f"{disk_all[True]/kept:.2%}")
    if raw_docs:
        print(f"  route A proxy -- /FontFile* visible outside object "
              f"streams: {raw_ok}/{raw_docs} documents")
    # is_math_family is a fixed list, so it DEFINES the population above.
    # Print both sides of it: a maths family missing from the list would
    # sit in the dropped column and silently narrow every figure here.
    print("  filter -- families is_math_family KEPT: " + ", ".join(
        f"{f} {c}" for f, c in kept_fams.most_common(8)))
    print("  filter -- families it DROPPED (check for maths among them): "
          + ", ".join(f"{f} {c}" for f, c in drop_fams.most_common(10)))


_PAGE_SIZE = re.compile(r"([\d.]+)\s*x\s*([\d.]+)\s*pts")


def _drill(doc):
    """The pdfdrill sidecar for a corpus document, or None.

    `images_layer` lists every embedded XObject's rectangle in PDF
    points. That is an independent oracle for a box detector -- produced
    by a different tool, from the PDF's own object graph rather than
    from ink -- and it is already on disk, so using it costs nothing.
    """
    hits = list(doc.glob("*.drill.json"))
    if not hits:
        return None
    try:
        d = json.load(hits[0].open())
    except (OSError, ValueError):
        return None
    info = d.get("pdfinfo") or {}
    m = _PAGE_SIZE.search(info.get("page_size") or "")
    if not m or not d.get("images_layer"):
        return None
    d["_page_pt"] = (float(m.group(1)), float(m.group(2)))
    return d


def _rect_candidates(mask, *, fill_max, hole):
    """Components that look like a drawn frame, as (moments, hole).

    Two sweeps, no `nest`: the foreground gives components and the
    inverted mask at conn=4 gives holes, which is the same pair `nest`
    computes and 15x cheaper (see the C2 note in units.md).

    `hole` selects how a hole's size is measured -- "bbox" or "area".
    It is an ARGUMENT because it changes the answer by a factor of two
    and because the two readings disagree about what the detector even
    found; see the U11 box section of units.md.
    """
    fg = sweep(mask, conn=8, capture=Capture.GRAPH)
    bg = sweep(mask.inverted(), conn=4, capture=Capture.GRAPH)
    comps = moments_per_component(fg)
    W, H = mask.width, mask.height
    # A background component touching the page border is the page, not a
    # hole. Everything else is enclosed by ink.
    def size(h):
        return h.width * h.height if hole == "bbox" else h.area
    holes = sorted((h for h in moments_per_component(bg).values()
                    if h.x0 > 0 and h.y0 > 0 and h.x1 < W - 1 and h.y1 < H - 1),
                   key=lambda h: -size(h))
    out = []
    for c in comps.values():
        bb = c.width * c.height
        if bb == 0 or c.area / bb >= fill_max:
            continue
        for h in holes:                     # sorted, so the first fit wins
            if size(h) * 2 < bb:
                break
            if (h.x0 >= c.x0 and h.y0 >= c.y0 and h.x1 <= c.x1
                    and h.y1 <= c.y1 and size(h) >= 0.5 * bb):
                out.append((c, h))
                break
    return out


def _solid_candidates(mask, *, min_px=50_000, fill_min=0.9, min_side=40):
    """The OTHER polarity: a filled tint, not a stroked frame (F1).

    A layout panel drawn as a translucent fill is a nearly solid
    component, and the hollow test cannot see it at all -- `fill` near 1
    is the opposite end of the same axis. Same moments, no new
    computation.
    """
    res = sweep(mask, conn=8, capture=Capture.GRAPH)
    return [c for c in moments_per_component(res).values()
            if c.width * c.height >= min_px and c.width >= min_side
            and c.height >= min_side
            and c.area / (c.width * c.height) > fill_min]


def _depths(rects):
    """Nesting depth per rectangle, by strict bbox containment."""
    bs = [(c.x0, c.y0, c.x1, c.y1) for c in rects]
    area = [(b[2] - b[0]) * (b[3] - b[1]) for b in bs]
    return [sum(1 for j, b in enumerate(bs)
                if j != i and b[0] <= a[0] and b[1] <= a[1]
                and b[2] >= a[2] and b[3] >= a[3] and area[j] > area[i])
            for i, a in enumerate(bs)]


def m_boxes(root, n, rng, fill_max=0.10, hole="bbox", doc=None):
    """units.md "U11 box detection": frames and rules from ink alone,
    cross-checked against the rectangles the PDF itself declares.

    POPULATION: rendered pages of corpus documents that carry a pdfdrill
    sidecar with a non-empty `images_layer`. The sample is deliberately
    HALF pages with declared images and half without: a detector
    measured only on pages that contain boxes cannot report a false
    positive, and the control pages are where the interesting number is.

    SPLIT: documents sampled without replacement, then pages within
    them; a page never appears under two thresholds as two samples.

    FILTERS, both of which change the answer and are therefore
    arguments rather than constants:

        --fill-max      how hollow a component must be. At the 0.35
                        originally proposed this admits every hollow
                        GLYPH: an italic zero at 400 dpi reads
                        fill 0.31, and real frames read 0.016-0.031
        --hole-measure  bbox or area. "bbox" finds every declared
                        image; "area" loses a third of them
    """
    docs = [d for d in sorted(root.iterdir())
            if d.is_dir() and (d / "inspect" / "pages").is_dir()]
    if doc:
        docs = [d for d in docs if d.name == doc]
        if not docs:
            print(f"  no document named {doc} in the corpus")
            return
    else:
        rng.shuffle(docs)
    thresholds = (200, 240)
    picked = []
    for d in docs:
        drill = _drill(d)
        if drill is None:
            continue
        with_img = {e["page"] for e in drill["images_layer"]}
        # Page files are `p<n>.png` in most of the corpus and
        # `page-<nnnn>.png` in some of it; a naive `p*.png` sort raised
        # on the second form rather than skipping it.
        seen_no = {}
        for p in sorted((d / "inspect" / "pages").glob("*.png")):
            m = re.fullmatch(r"p(?:age-)?0*(\d+)", p.stem)
            if m:
                # Some documents carry BOTH conventions for the same
                # page; keeping both put one page in the sample twice.
                seen_no.setdefault(int(m.group(1)), p)
        numbered = sorted(seen_no.items())
        pos = [p for k, p in numbered if k in with_img]
        neg = [p for k, p in numbered if k not in with_img]
        nums = dict((p, k) for k, p in numbered)
        if not pos or not neg:
            continue
        k = max(1, min(len(pos), len(neg), (n - len(picked)) // 2))
        chosen = (pos + neg) if doc else (rng.sample(pos, k) + rng.sample(neg, k))
        for p in chosen:
            picked.append((d, drill, p, nums[p]))
        if len(picked) >= n:
            break
    if not picked:
        print("  no document with rendered pages and an images_layer")
        return

    print(f"  fill_max {fill_max}  hole={hole}  thresholds {thresholds}")
    print(f"  {len(picked)} pages from "
          f"{len({d.name for d, _, _, _ in picked})} documents")
    tot_decl = tot_hit = 0
    fp_pages = fp_rects = 0
    worst = 0.0
    unbordered = []
    for d, drill, png, pno in picked:
        decl = [e for e in drill["images_layer"] if e["page"] == pno]
        pw_pt, _ = drill["_page_pt"]
        union, per_th = {}, []
        solids = 0
        for th in thresholds:
            mask = load_mask(png, threshold=th)
            dpi = mask.width * 72.0 / pw_pt
            rects = [c for c, _ in _rect_candidates(mask, fill_max=fill_max,
                                                    hole=hole)]
            per_th.append((th, len(rects)))
            solids = max(solids, len(_solid_candidates(mask)))
            for c in rects:              # union by bbox identity (F2)
                union[(c.x0, c.y0, c.x1, c.y1)] = (c, dpi)
        rects = [c for c, _ in union.values()]
        hist = Counter(_depths(rects))
        # Cross-check: every declared image should have a measured
        # rectangle of the same size. Sizes, not positions -- the
        # declared rectangle is the image's placement box and the ink
        # frame is drawn on its border.
        hit, deltas = 0, []
        for e in decl:
            best = min(((max(abs(c.width * 72.0 / dpi - e["w_pt"]),
                             abs(c.height * 72.0 / dpi - e["h_pt"])))
                        for c, dpi in union.values()), default=None)
            if best is not None and best <= 3.0:
                hit += 1
                deltas.append(best)
        tot_decl += len(decl)
        tot_hit += hit
        if deltas:
            worst = max(worst, max(deltas))
        if not decl:
            fp_pages += 1
            fp_rects += len(rects)
        if decl and hit == 0 and rects:
            unbordered.append((d.name, pno, len(decl)))
        print(f"    {d.name[:18]:18} p{pno:<3} "
              f"{'images ' + str(len(decl)) if decl else 'CONTROL':>9}  "
              f"rects {len(rects):4} " +
              " ".join(f"th{t}:{k}" for t, k in per_th) +
              f"  depth {dict(sorted(hist.items()))}"
              f"  solid {solids}" +
              (f"  recovered {hit}/{len(decl)}" if decl else ""))
    print(f"  declared images recovered: {tot_hit}/{tot_decl}"
          + (f", worst size error {worst:.2f} pt" if tot_hit else ""))
    print("  NOTE on that denominator: a declared image yields a measurable")
    print("  rectangle only when the figure is DRAWN WITH A BORDER. A bare")
    print("  photograph has no stroked frame, so there is no ink rectangle")
    print("  to recover and a miss is not a detector failure. Recovery is")
    print("  an upper-bound check on the bordered ones, never an accuracy.")
    print(f"  FALSE POSITIVES on {fp_pages} control pages: {fp_rects} "
          f"rectangles where the PDF declares no image")


def _unfilter_rgb(dec, w, h):
    """Unfilter to RGB and KEEP it.

    A near-copy of `pngio._decode_gray_colour`'s loop with the luma
    reduction removed. It lives here rather than in the package because
    the package deliberately does not retain RGB, and whether it should
    is exactly what this measurement is for -- see `m_border`.
    """
    stride, row_len = w * 3 + 1, w * 3
    prev = bytearray(row_len)
    out = []
    for r in range(h):
        base = r * stride
        ft = dec[base]
        line = bytearray(dec[base + 1:base + stride])
        if ft == 1:
            for i in range(3, row_len):
                line[i] = (line[i] + line[i - 3]) & 0xFF
        elif ft == 2:
            for i in range(row_len):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ft == 3:
            for i in range(row_len):
                a = line[i - 3] if i >= 3 else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif ft == 4:
            for i in range(row_len):
                a = line[i - 3] if i >= 3 else 0
                b = prev[i]
                c = prev[i - 3] if i >= 3 else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if (pa <= pb and pa <= pc)
                                      else (b if pb <= pc else c))) & 0xFF
        elif ft != 0:
            raise ValueError(f"unknown filter type {ft} on row {r}")
        prev = line
        out.append(bytes(line))
    return b"".join(out)


def _shannon(cnt):
    tot = sum(cnt.values())
    if tot <= 0:
        return 0.0
    return -sum((v / tot) * math.log2(v / tot) for v in cnt.values())


def _border_class(cnt, *, flat_max=2, texture_min=9):
    """Which regime a component's border-colour histogram is in.

    The classes are defined by DISTINCT COLOUR COUNT, which is why
    quantising the samples cannot sharpen them -- see `m_border`.
    """
    d = len(cnt)
    if d == 0:
        return "empty"
    if d == 1:
        return "flat-white" if next(iter(cnt)) == (255, 255, 255) \
            else "flat-coloured"
    if d == 2:
        return "boundary"
    if d < texture_min:
        return "mixed"
    return "textured"


def m_border(root, n, rng, quantise=0, doc=None):
    """units.md "U0/U3 border colour": what the pixels just outside a
    component's runs say about what it is sitting on.

    A run is `(line, lo, hi)`, so `(lo-1, line)` and `(hi+1, line)` are
    addresses the adjacency test already computes: 2 samples per RUN, not
    per pixel.

    POPULATION: rendered pages of corpus documents whose pdfdrill sidecar
    declares at least one embedded image, so both photographic and vector
    content are present on the same page. Neutral pages are reported
    SEPARATELY and not pooled: a neutral page has no colour to sample,
    and pooling them would dilute every class with pages on which the
    measurement is vacuous by construction.

    SPLIT: documents sampled without replacement, then one page each, so
    no document contributes twice.

    FILTER: `--quantise` rounds each channel before counting. It defaults
    to 0 (off) because it is measured to destroy the classes rather than
    sharpen them; it stays an argument so that result is re-runnable.
    """
    docs = [d for d in sorted(root.iterdir())
            if d.is_dir() and (d / "inspect" / "pages").is_dir()]
    if doc:
        docs = [d for d in docs if d.name == doc]
    else:
        rng.shuffle(docs)
    picked = []
    for d in docs:
        drill = _drill(d)
        if drill is None:
            continue
        with_img = {e["page"] for e in drill["images_layer"]}
        seen = {}
        for p in sorted((d / "inspect" / "pages").glob("*.png")):
            mt = re.fullmatch(r"p(?:age-)?0*(\d+)", p.stem)
            if mt:
                seen.setdefault(int(mt.group(1)), p)
        pos = [(k, p) for k, p in sorted(seen.items()) if k in with_img]
        if not pos:
            continue
        picked.extend(pos if doc else [rng.choice(pos)])
        if len(picked) >= n:
            break
    picked = picked[:n]
    if not picked:
        print("  no document with rendered pages and a declared image")
        return

    print(f"  quantise {quantise or 'off'};  {len(picked)} pages")
    totals, t_dec, t_sw, t_bd = Counter(), 0.0, 0.0, 0.0
    neutral_pages = colour_pages = 0
    pairs = Counter()
    for pno, png in picked:
        img = read_png(png)
        if img.neutral:
            neutral_pages += 1
            continue
        colour_pages += 1
        (w, h), dec = inflate(png)
        t = time.perf_counter()
        rgb = _unfilter_rgb(dec, w, h)
        t_dec += time.perf_counter() - t
        mask = load_mask(png, threshold=200)
        t = time.perf_counter()
        res = sweep(mask, conn=8, capture=Capture.GRAPH)
        t_sw += time.perf_counter() - t
        node = {nd.id: nd for nd in res.nodes}
        t = time.perf_counter()
        per = []
        for c in res.components:
            cnt = Counter()
            for i in c.nodes:
                r = node[i].as_run()
                off = r.line * w
                for x in (r.lo - 1, r.hi + 1):
                    if 0 <= x < w:
                        o = (off + x) * 3
                        px = (rgb[o], rgb[o + 1], rgb[o + 2])
                        if quantise:
                            px = tuple(v // quantise * quantise for v in px)
                        cnt[px] += 1
            per.append(cnt)
        t_bd += time.perf_counter() - t
        for cnt in per:
            k = _border_class(cnt)
            totals[k] += 1
            if k == "boundary":
                (a, na), (b, nb) = cnt.most_common(2)
                # A CLOSED frame borders its two fields about equally.
                pairs["balanced" if min(na, nb) / max(na, nb) > 0.5
                      else "one-sided"] += 1
    if not colour_pages:
        print("  every sampled page was neutral -- nothing to sample")
        return
    tot = sum(totals.values())
    print(f"  {colour_pages} colour pages measured, {neutral_pages} neutral "
          f"pages SKIPPED (no colour to sample)")
    for k, v in totals.most_common():
        print(f"    {v:7} ({v/tot:6.2%})  {k}")
    print(f"  boundary blobs by field balance: {dict(pairs)}")
    print(f"  cost per page: RGB unfilter {t_dec/colour_pages:.2f}s, "
          f"sweep {t_sw/colour_pages:.2f}s, "
          f"border sampling {t_bd/colour_pages:.2f}s "
          f"(+{100*t_bd/t_sw:.0f}% on the sweep, "
          f"{100*t_bd/(t_dec+t_sw+t_bd):.0f}% of the three)")


def _white_mask(mask, *, min_len, bounded=True):
    """A mask of the white runs that look like GAPS rather than margins.

    Two rules, both one line, and the first is the whole trick: a white
    run touching the scan-line edge is a margin -- white connects around
    every object through the page border, so keeping those gives one
    page-sized blob. Discarding them disconnects the page into layout.

    Both axes are written with C-speed slice assignment, the row one
    contiguous and the column one strided. Writing the column axis as a
    per-pixel loop is the run-discipline violation this project keeps
    finding; `raster._iter_runs_col` already reads that way.
    """
    W, H = mask.width, mask.height
    inv = mask.inverted()
    buf = bytearray(W * H)
    kept = edge = short = 0
    for axis in ("row", "col"):
        limit = W if axis == "row" else H
        for r in iter_runs(inv, axis):
            if bounded and (r.lo == 0 or r.hi == limit - 1):
                edge += 1
                continue
            n = r.hi - r.lo + 1
            if n < min_len:
                short += 1
                continue
            kept += 1
            if axis == "row":
                base = r.line * W
                buf[base + r.lo:base + r.hi + 1] = b"\xff" * n
            else:
                buf[r.lo * W + r.line:r.hi * W + r.line + 1:W] = b"\xff" * n
    return InkMask(bytes(buf), W, H), kept, edge, short


def m_white(root, n, rng, min_len=60, doc=None):
    """units.md "U11 white-run layout": what the page's GAPS say, rather
    than its ink. Baird 1994 and Breuel 2002 in run form.

    POPULATION: pages of corpus documents whose pdfdrill sidecar declares
    at least one embedded image, so there is an independent oracle for
    what the white rectangles should be. SPLIT: documents sampled without
    replacement, one page each unless `--doc` names one document, in
    which case all of its image-bearing pages are measured.

    FILTERS, both arguments because both were chosen on two pages and
    neither has a measured value: `--min-len` (default 60 px at 400 dpi,
    which is an absolute number where the right one almost certainly
    scales with body-text size) and the ink-bounded rule, whose cost is
    printed as the count of runs it drops.

    THRESHOLDS: 128, 200 and 240 are all run, because the proposal's
    central claim is that white and ink want opposite ones.
    """
    docs = [d for d in sorted(root.iterdir())
            if d.is_dir() and (d / "inspect" / "pages").is_dir()]
    if doc:
        docs = [d for d in docs if d.name == doc]
    else:
        rng.shuffle(docs)
    picked = []
    for d in docs:
        drill = _drill(d)
        if drill is None:
            continue
        with_img = {e["page"] for e in drill["images_layer"]}
        seen = {}
        for p in sorted((d / "inspect" / "pages").glob("*.png")):
            mt = re.fullmatch(r"p(?:age-)?0*(\d+)", p.stem)
            if mt:
                seen.setdefault(int(mt.group(1)), p)
        pos = [(k, p) for k, p in sorted(seen.items()) if k in with_img]
        if not pos:
            continue
        picked.extend(pos if doc else [rng.choice(pos)])
        if len(picked) >= n:
            break
        drills = drill
    picked = picked[:n]
    if not picked:
        print("  no document with rendered pages and a declared image")
        return
    print(f"  min_len {min_len} px;  {len(picked)} pages")

    by_th = defaultdict(lambda: [0, 0, 0.0])      # th -> [hit, decl, worst]
    for pno, png in picked:
        d = png.parent.parent.parent
        drill = _drill(d)
        decl = [e for e in drill["images_layer"] if e["page"] == pno]
        pw_pt = drill["_page_pt"][0]
        first = True
        for th in (128, 200, 240):
            mask = load_mask(png, threshold=th)
            dpi = mask.width * 72.0 / pw_pt
            if first:
                # The failure the ink-bounded rule exists to prevent,
                # measured rather than asserted.
                naive, _, _, _ = _white_mask(mask, min_len=1, bounded=False)
                nres = sweep(naive, conn=8, capture=Capture.GRAPH)
                nmo = moments_per_component(nres)
                big = max(nmo.values(), key=lambda c: c.area, default=None)
                share = big.area / (mask.width * mask.height) if big else 0.0
            wm, kept, edge, short = _white_mask(mask, min_len=min_len)
            res = sweep(wm, conn=8, capture=Capture.GRAPH)
            mo = moments_per_component(res)
            hit, worst = 0, 0.0
            for e in decl:
                best = min((max(abs(c.width * 72.0 / dpi - e["w_pt"]),
                                abs(c.height * 72.0 / dpi - e["h_pt"]))
                            for c in mo.values()), default=None)
                if best is not None and best <= 3.0:
                    hit += 1
                    worst = max(worst, best)
            b = by_th[th]
            b[0] += hit
            b[1] += len(decl)
            b[2] = max(b[2], worst)
            if first:
                print(f"    {d.name[:18]:18} p{pno:<3} images {len(decl):2}  "
                      f"naive largest blob {share:5.1%} of page  "
                      f"-> ink-bounded {len(res.components)} blobs "
                      f"(dropped {edge} edge, {short} short)")
                first = False
            print(f"        th{th}: {len(res.components):5} blobs, "
                  f"recovered {hit}/{len(decl)}"
                  + (f", worst {worst:.2f} pt" if hit else ""))
    print("  declared images recovered by threshold "
          "(the proposal says white needs 128 and ink needs 240):")
    for th in sorted(by_th):
        hit, dec, worst = by_th[th]
        print(f"    th{th}: {hit}/{dec}" + (f", worst {worst:.2f} pt" if hit else ""))


def m_residuals(root, n, rng):
    """units.md 3 "U10 premise check": the four residual classes.

    Reports a PER-PAGE distribution, not just an aggregate. The
    aggregate is dominated by whichever pages happen to be figure-heavy,
    so the mechanism plus the spread is the claim -- not the mean."""
    docs = [(cj.parent, cj) for cj in sorted(root.glob("*/*.chars.json"))
            if (cj.parent / "inspect" / "pages").is_dir()]
    per_page = []
    agg = Counter()
    for doc, cj in rng.sample(docs, min(len(docs), n * 6)):
        if len(per_page) >= n:
            break
        try:
            data = json.load(cj.open())
        except Exception:
            continue
        for page in data["pages"]:
            pdir = doc / "inspect" / "pages"
            png = next((pdir / p for p in
                        (f"p{page['page_number']}.png",
                         f"page-{page['page_number']:04d}.png")
                        if (pdir / p).exists()), None)
            if png is None:
                continue
            img = read_png(png)
            sx = img.width / page["width"]
            if abs(sx - img.height / page["height"]) / sx > 0.01:
                continue
            mask = binarize(img.gray, img.width, img.height)
            comps = [GComp(i, x0, y0, x1, y1)
                     for i, ((x0, y0, x1, y1), _sub)
                     in enumerate(components(mask, min_area=1, min_side=1))]
            glyphs = [GGlyph(c["text"], c["x0"], c["y0"], c["x1"], c["y1"],
                             c.get("fontname", ""))
                      for c in page["chars"]
                      if c.get("text") and len(c["text"]) == 1
                      and c["text"].strip()]
            t = page_transform(page["height"], sx * 72.0)
            rep = match(comps, glyphs, to_pixels=t)
            for k in MatchKind:
                agg[k] += rep.count(k)
            per_page.append((doc.name, rep))
            print(f"  {doc.name[:26]:26} p{page['page_number']:<3} "
                  f"{sx*72:.0f} dpi  1:1 {rep.fraction(MatchKind.ONE_TO_ONE):6.1%}"
                  f"  image-only {rep.fraction(MatchKind.IMAGE_ONLY):6.1%}"
                  f"  no-ink {rep.glyphs_without_ink:6.2%}")
            break
    if not per_page:
        print("  no usable pages")
        return
    tot = sum(agg.values())
    print(f"\n  AGGREGATE over {len(per_page)} pages, {tot} assignments")
    for k in MatchKind:
        if agg[k]:
            print(f"    {agg[k]:7} ({agg[k]/tot:6.2%})  {k.value}")
    for label, kind in (("1:1", MatchKind.ONE_TO_ONE),
                        ("ink with no glyph", MatchKind.IMAGE_ONLY)):
        vals = sorted(r.fraction(kind) for _d, r in per_page)
        print(f"  per-page {label:18} min {vals[0]:6.1%}  "
              f"median {vals[len(vals)//2]:6.1%}  max {vals[-1]:6.1%}")
    noink = sorted(r.glyphs_without_ink for _d, r in per_page)
    print(f"  per-page glyphs with no ink  min {noink[0]:6.2%}  "
          f"median {noink[len(noink)//2]:6.2%}  max {noink[-1]:6.2%}")


def m_missed(root, n, rng):
    """units.md 3 "U11 premise check": what another tool missed.

    Scanned pages with line-level OCR. Reports the PER-PAGE spread --
    the aggregate is dominated by whichever page the tool did worst on,
    and that page is the deliverable, not an outlier."""
    docs = [d for d in root.glob("*Z-Library*")
            if (d / "inspect" / "pages").is_dir()
            and list(d.glob("*.lines.json"))]
    if not docs:
        print("  no scanned documents with OCR under this corpus root")
        return
    agg = Counter()
    per_page = []
    for d in rng.sample(docs, min(len(docs), n * 5)):
        if len(per_page) >= n:
            break
        try:
            data = json.load(list(d.glob("*.lines.json"))[0].open())
        except Exception:
            continue
        for pg in data["pages"]:
            if not pg.get("lines"):
                continue
            num = pg["page"]
            pdir = d / "inspect" / "pages"
            png = next((pdir / p for p in (f"p{num}.png",
                                           f"page-{num:04d}.png")
                        if (pdir / p).exists()), None)
            if png is None:
                continue
            img = read_png(png)
            sx = img.width / pg["page_width"]
            if abs(sx - img.height / pg["page_height"]) / sx > 0.01:
                continue
            mask = binarize(img.gray, img.width, img.height)
            boxes = [Box(i, x0, y0, x1, y1)
                     for i, ((x0, y0, x1, y1), _s)
                     in enumerate(components(mask, min_area=1, min_side=1))]
            regs = []
            for j, L in enumerate(pg["lines"]):
                g = L["region"]
                regs.append(Region(j, g["top_left_x"] * sx,
                                   g["top_left_y"] * sx,
                                   (g["top_left_x"] + g["width"]) * sx,
                                   (g["top_left_y"] + g["height"]) * sx,
                                   L.get("type", "")))
            rep = check(boxes, regs, min_pixels=9)
            for k in CoverageClass:
                agg[k] += rep.count(k)
            per_page.append(rep)
            print(f"  {d.name[:26]:26} p{num:<4} {len(regs):4} regions "
                  f"{rep.box_count:6} ink   "
                  f"missed {rep.missed_fraction:6.2%}   straddle "
                  f"{rep.fraction(CoverageClass.STRADDLE):6.2%}")
            break
    if not per_page:
        print("  no usable pages")
        return
    tot = sum(v for k, v in agg.items() if k is not CoverageClass.EMPTY_REGION)
    print(f"\n  AGGREGATE over {len(per_page)} pages, {tot} ink assignments")
    for k in CoverageClass:
        if agg[k]:
            print(f"    {agg[k]:7} ({agg[k]/tot:6.2%})  {k.value}")
    for label, kind in (("missed", CoverageClass.MISSED),
                        ("straddle", CoverageClass.STRADDLE)):
        vals = sorted(r.fraction(kind) for r in per_page)
        print(f"  per-page {label:9} min {vals[0]:6.2%}  "
              f"median {vals[len(vals)//2]:6.2%}  max {vals[-1]:6.2%}")


def m_convexity(root, n, rng):
    """units.md 3 "U12 premise check": the Gardenfors design test.

    Uses the SHIPPED convexity() and mutual_information(), so the numbers
    recorded in domains.DIMENSIONS are reproducible from the module
    rather than from a scratch script."""
    from collections import defaultdict
    from inkdrill.aggregate import moments_of_mask
    from inkdrill.nest import nest as nest_of
    from inkdrill.reeb import graph_of, signature

    docs = [(cj.parent, cj) for cj in sorted(root.glob("*/*.chars.json"))
            if (cj.parent / "inspect" / "pages").is_dir()]
    rows = []          # (char, feature dict)
    pages = 0
    for doc, cj in rng.sample(docs, len(docs)):
        if pages >= n:
            break
        try:
            data = json.load(cj.open())
        except Exception:
            continue
        for page in data["pages"]:
            pdir = doc / "inspect" / "pages"
            png = next((pdir / p for p in
                        (f"p{page['page_number']}.png",
                         f"page-{page['page_number']:04d}.png")
                        if (pdir / p).exists()), None)
            if png is None:
                continue
            img = read_png(png)
            sx = img.width / page["width"]
            if abs(sx - img.height / page["height"]) / sx > 0.01:
                continue
            mask = binarize(img.gray, img.width, img.height)
            glyphs = [(c["text"], c["x0"] * sx,
                       (page["height"] - c["y1"]) * sx, c["x1"] * sx,
                       (page["height"] - c["y0"]) * sx)
                      for c in page["chars"]
                      if c.get("text") and len(c["text"]) == 1
                      and c["text"].strip()]
            for (x0, y0, x1, y1), sub in components(mask, min_area=1,
                                                    min_side=5):
                cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                hit = [g for g in glyphs
                       if g[1] <= cx <= g[3] and g[2] <= cy <= g[4]]
                if len(hit) != 1:
                    continue
                mo = moments_of_mask(sub)
                s = signature(graph_of(sub))
                rows.append((hit[0][0], {
                    "width": sub.width, "height": sub.height,
                    "area": mo.area, "elongation": mo.elongation,
                    "cycles": s.cycles, "births": s.births,
                    "merges": s.merges, "splits": s.splits,
                    "depth": max((r.depth for r in
                                  nest_of(sub).regions.values()), default=0),
                }))
            pages += 1
            print(f"  {doc.name[:26]:26} p{page['page_number']:<3} "
                  f"{len(rows)} glyphs so far")
            break

    counts = Counter(c for c, _f in rows)
    common = {c for c, k in counts.items() if k >= 40}
    use = [(c, f) for c, f in rows if c in common]
    if not use:
        print("  not enough glyphs per class")
        return
    print(f"\n  {len(use)} glyph instances, {len(common)} classes with 40+"
          f"   baseline {1/len(common):.3f}\n")
    print(f"  {'dimension':12} {'domain':10} {'convex':>7} {'lift':>6} "
          f"{'nmi':>6} {'distinct':>9} {'ceiling':>8} {'eff':>6}")
    out = []
    cols = {}
    labels_all = [c for c, _f in use]
    for dim in DIMENSIONS:
        vals, labs = [], []
        for c, f in use:
            v = describe(f).get(dim.name)
            if v is not None:
                vals.append(v)
                labs.append(c)
        if len(vals) < 50:
            continue
        cv = convexity(vals, labs)
        nmi = mutual_information(vals, labs)
        ceil = mi_ceiling(vals, labs)
        out.append((dim, cv, nmi, len(set(vals)), ceil,
                    efficiency(vals, labs)))
        if len(vals) == len(labels_all):
            cols[dim.name] = vals
    for dim, cv, nmi, dis, ceil, eff in sorted(out, key=lambda r: -r[2]):
        print(f"  {dim.name:12} {dim.domain.value:10} {cv.score:7.3f} "
              f"{cv.lift:5.1f}x {nmi:6.3f} {dis:9} {ceil:8.3f} {eff:6.2f}")

    print(f"\n  {'domain':12} {'dims':>5} {'joint nmi':>10}   "
          f"(marginals cannot see joint information)")
    for dom in Domain:
        names = [d.name for d in dimensions_of(dom) if d.name in cols]
        if not names:
            print(f"  {dom.value:12} {0:5}        --   declared, no data")
            continue
        j = joint_mutual_information({k: cols[k] for k in names},
                                     labels_all)
        best = max(mutual_information(cols[k], labels_all) for k in names)
        print(f"  {dom.value:12} {len(names):5} {j:10.3f}   "
              f"best marginal {best:.3f}")
    everything = joint_mutual_information(cols, labels_all)
    print(f"  {'ALL':12} {len(cols):5} {everything:10.3f}")


def m_classify(root, n, rng, split="document"):
    """units.md 3 "U13 premise check": channel accuracy and the confusion
    matrix.

    THE SPLIT RULE IS THE EXPERIMENT. A component-level random split over
    pages that appear on both sides leaks: nearly every test glyph has a
    near-identical twin -- same document, page, font and size -- in the
    training half. Splitting by DOCUMENT is the honest default here;
    `--split component` reproduces the leaky protocol for comparison.
    """
    from inkdrill.aggregate import moments_of_mask
    from inkdrill.reeb import graph_of, signature

    docs = [(cj.parent, cj) for cj in sorted(root.glob("*/*.chars.json"))
            if (cj.parent / "inspect" / "pages").is_dir()]
    rows = []          # (doc, page, Template)
    pages = 0
    for doc, cj in rng.sample(docs, len(docs)):
        if pages >= n:
            break
        try:
            data = json.load(cj.open())
        except Exception:
            continue
        for page in data["pages"]:
            pdir = doc / "inspect" / "pages"
            png = next((pdir / p for p in
                        (f"p{page['page_number']}.png",
                         f"page-{page['page_number']:04d}.png")
                        if (pdir / p).exists()), None)
            if png is None:
                continue
            img = read_png(png)
            sx = img.width / page["width"]
            if abs(sx - img.height / page["height"]) / sx > 0.01:
                continue
            mask = binarize(img.gray, img.width, img.height)
            glyphs = [(c["text"], c["x0"] * sx,
                       (page["height"] - c["y1"]) * sx, c["x1"] * sx,
                       (page["height"] - c["y0"]) * sx)
                      for c in page["chars"]
                      if c.get("text") and len(c["text"]) == 1
                      and c["text"].strip()]
            for (x0, y0, x1, y1), sub in components(mask, min_area=1,
                                                    min_side=5):
                cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                hit = [g for g in glyphs
                       if g[1] <= cx <= g[3] and g[2] <= cy <= g[4]]
                if len(hit) != 1:
                    continue
                s = signature(graph_of(sub))
                mo = moments_of_mask(sub)
                w, h = sub.width, sub.height
                font = next((c.get("fontname", "") for c in page["chars"]
                             if c.get("text") == hit[0][0]), "")
                rows.append((doc.name, page["page_number"], font,
                             Template(hit[0][0], normalise(sub),
                                      (s.cycles, s.births, s.merges,
                                       s.splits),
                                      (w / h, float(h), float(w),
                                       mo.elongation))))
            pages += 1
            print(f"  {doc.name[:26]:26} p{page['page_number']:<3} "
                  f"{len(rows)} glyphs")
            break

    counts = Counter(r[3].label for r in rows)
    common = {c for c, k in counts.items() if k >= 12}
    rows = [r for r in rows if r[3].label in common]
    # The class filter is a decision, not plumbing: it silently excludes
    # every character too rare to clear the threshold, which on body-text
    # pages means every maths symbol. Print what survived.
    dropped = sorted(c for c in counts if c not in common)
    print(f"\n  CLASSES KEPT ({len(common)}, >=12 instances): "
          f"{''.join(sorted(common))}")
    print(f"  CLASSES DROPPED ({len(dropped)}): {''.join(dropped)[:80]}")
    mathy = [c for c in common if ord(c) > 127]
    print(f"  non-ASCII among kept: {''.join(sorted(mathy)) or 'NONE'}"
          f"   <- if none, this measures BODY TEXT only")
    if len(rows) < 100:
        print("  not enough labelled glyphs")
        return

    if split == "component":
        shuffled = rows[:]
        rng.shuffle(shuffled)
        cut = len(shuffled) // 2
        train = [r[3] for r in shuffled[:cut]]
        test = [(r[3].label, r[3]) for r in shuffled[cut:]]
        note = "component-level random split -- LEAKY, pages on both sides"
    else:
        key = {"document": 0, "page": 1, "font": 2}[split]
        groups = sorted({r[key] for r in rows})
        if len(groups) < 2:
            print(f"\n  cannot split by {split}: only {len(groups)} group "
                  f"present ({groups}). The corpus cannot test this axis, "
                  f"so the question stays OPEN rather than answered.")
            return
        rng.shuffle(groups)
        held = set(groups[:max(1, len(groups) // 2)])
        train = [r[3] for r in rows if r[key] not in held]
        test = [(r[3].label, r[3]) for r in rows if r[key] in held]
        note = (f"split by {split}: no {split} appears on both sides "
                f"({len(groups)} groups)")

    test = test[:600]
    if not train or not test:
        print("  split left one side empty")
        return
    shared = {lab for lab, _t in test} & {t.label for t in train}
    test = [(lab, t) for lab, t in test if lab in shared]
    base = Counter(lab for lab, _t in test).most_common(1)[0][1] / len(test)
    print(f"\n  SPLIT RULE: {note}")
    print(f"  train {len(train)}, test {len(test)}, "
          f"{len(shared)} classes;  majority baseline {base:.1%}")
    for name, ch in (("signature only", Channels(0, 1, 0)),
                     ("extents only", Channels(0, 0, 1)),
                     ("bitmap only", Channels(1, 0, 0)),
                     ("bitmap + extents", Channels(1, 0, 6)),
                     ("all three", Channels(1, 3, 6))):
        acc, pairs = classify_confusion(Classifier(train, ch), test)
        print(f"    {name:20} {acc:7.1%}")
        if name == "all three":
            worst = pairs.most_common(8)
    print("  worst confusions (all three):")
    for (truth, pred), k in worst:
        print(f"    {truth!r} read as {pred!r}   x{k}")


MEASUREMENTS = {
    "banding": (m_banding, 3),
    "border": (m_border, 10),
    "boxes": (m_boxes, 8),
    "white": (m_white, 8),
    "classify": (m_classify, 6),
    "convexity": (m_convexity, 2),
    "missed": (m_missed, 8),
    "outlines": (m_outlines, 30),
    "residuals": (m_residuals, 12),
    "fonts": (m_fonts, 25),
    "schedcost": (m_schedcost, 8),
    "stitchcost": (m_stitchcost, 2),
    "moments": (m_moments, 3),
    "nesting": (m_nesting, 2),
    "neutrality": (m_neutrality, 400),
    "colour": (m_colour, 60),
    "throughput": (m_throughput, 5),
    "skew": (m_skew, 10),
    "premise": (m_premise, 3),
    "contraction": (m_contraction, 3),
    "rotation": (m_rotation, 158),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("what", nargs="+",
                    choices=sorted(MEASUREMENTS) + ["all"])
    ap.add_argument("--corpus", required=True, type=pathlib.Path)
    ap.add_argument("--n", type=int, default=None,
                    help="sample size; each measurement has its own default")
    ap.add_argument("--seed", type=int, default=20260807)
    ap.add_argument("--min-len", type=int, default=60,
                    help="white only: shortest white run counted as a gap, "
                         "in px. Chosen on two pages; not yet measured.")
    ap.add_argument("--quantise", type=int, default=0,
                    help="border only: round each RGB channel to this step "
                         "before counting. 0 = off, which is the measured "
                         "answer -- quantising destroys the classes.")
    ap.add_argument("--doc", default=None,
                    help="boxes/border only: measure one named corpus document, "
                         "all of its pages, instead of a random sample.")
    ap.add_argument("--fill-max", type=float, default=0.10,
                    help="boxes only: how hollow a component must be to "
                         "count as a frame. 0.35 admits hollow glyphs.")
    ap.add_argument("--hole-measure", default="bbox",
                    choices=("bbox", "area"),
                    help="boxes only: how a hole's size is measured. "
                         "Changes the count by 2x -- see units.md.")
    ap.add_argument("--split", default="document",
                    choices=("component", "page", "document", "font"),
                    help="classify only: how train and test are divided. "
                         "The split rule IS the experiment -- see the "
                         "U13 premise check in docs/units.md.")
    args = ap.parse_args()

    root = args.corpus.expanduser()
    if not root.is_dir():
        sys.exit(f"corpus not found: {root}")
    todo = sorted(MEASUREMENTS) if "all" in args.what else args.what
    for name in todo:
        fn, default_n = MEASUREMENTS[name]
        print(f"\n=== {name} " + "=" * (62 - len(name)))
        if name == "white":
            fn(root, args.n or default_n, random.Random(args.seed),
               min_len=args.min_len, doc=args.doc)
        elif name == "border":
            fn(root, args.n or default_n, random.Random(args.seed),
               quantise=args.quantise, doc=args.doc)
        elif name == "boxes":
            fn(root, args.n or default_n, random.Random(args.seed),
               fill_max=args.fill_max, hole=args.hole_measure, doc=args.doc)
        elif name == "classify":
            fn(root, args.n or default_n, random.Random(args.seed),
               split=args.split)
        else:
            fn(root, args.n or default_n, random.Random(args.seed))


if __name__ == "__main__":
    main()
