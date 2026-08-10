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
edges        M2.1: 2NN vs 6NN vs line-of-sight candidate edges
spacing      M1.1: does typography explain the horizontal geometry?
maths        THE measurement: maths-symbol classification, never done
rasterisers  U9->U13 premise: template (scan) vs query (Ghostscript)
charstrings  U9 interpreter premise: which Type 1 operators real fonts
             actually use, and which are subsystems rather than cases
outlines     U9 rasterizer premise: which outline format maths glyphs are
             in, and whether it is reachable without a PDF parser
"""

from __future__ import annotations

import argparse
import json
import math
import os
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
from inkdrill.type1 import load as t1_load                  # noqa: E402
from inkdrill.charstring import outline as cs_outline       # noqa: E402
from inkdrill.scan import render as scan_render             # noqa: E402


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
    dropped_repeats = 0
    pos_deltas = []
    for d, drill, png, pno in picked:
        pw_pt, _ = drill["_page_pt"]
        # The oracle is a list of XObject PLACEMENTS, not of figures. A
        # repeated header logo is 109 of one corporate document's 213
        # entries, so a recovery rate over the raw list has a 49%
        # ceiling no detector can pass. Count each distinct placement
        # once and say how many were dropped.
        seen_place, uniq = set(), []
        for e in drill["images_layer"]:
            k = (e.get("name"), round(e["w_pt"], 1), round(e["h_pt"], 1))
            if k not in seen_place:
                seen_place.add(k)
                uniq.append(e)
        repeats = len(drill["images_layer"]) - len(uniq)
        decl = [e for e in uniq if e["page"] == pno]
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
        dropped_repeats = max(dropped_repeats, repeats)
        # Locate by POSITION, then ask how wrong the SIZE is. Matching on
        # size alone cannot tell a miss from a padded figure.
        for e in decl:
            near = [(max(abs(c.x0 * 72.0 / dp - e["x0"]),
                         abs(c.y0 * 72.0 / dp - e["y0"])), c, dp)
                    for c, dp in union.values()]
            near = [t for t in near if t[0] <= 12.0]
            if near:
                _, c, dp = min(near, key=lambda t: t[0])
                pos_deltas.append(max(abs(c.width * 72.0 / dp - e["w_pt"]),
                                      abs(c.height * 72.0 / dp - e["h_pt"])))
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
    if dropped_repeats:
        print(f"  oracle hygiene: {dropped_repeats} repeated placements "
              f"dropped (a header logo repeats once per page)")
    if pos_deltas:
        ds = sorted(pos_deltas)
        mid = ds[len(ds) // 2]
        p90 = ds[max(0, int(0.9 * len(ds)) - 1)]
        print(f"  size error where the figure WAS located (matched by "
              f"position, n={len(ds)}): median {mid:.2f} pt, p90 {p90:.2f} pt, "
              f"max {ds[-1]:.2f} pt")
        print("  A declared rectangle is the PLACEMENT BOX; ink gives the "
              "CONTENT EXTENT. They coincide for tight vector figures and")
        print("  differ by the raster's own white padding otherwise, so a "
              "tight tolerance measures the padding, not the detector.")


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


_T1_OPS = {
    1: "hstem", 3: "vstem", 4: "vmoveto", 5: "rlineto", 6: "hlineto",
    7: "vlineto", 8: "rrcurveto", 9: "closepath", 10: "callsubr",
    11: "return", 13: "hsbw", 14: "endchar", 21: "rmoveto", 22: "hmoveto",
    30: "vhcurveto", 31: "hvcurveto",
}
_T1_ESC = {
    0: "dotsection", 1: "vstem3", 2: "hstem3", 6: "seac", 7: "sbw",
    12: "div", 16: "callothersubr", 17: "pop", 33: "setcurrentpoint",
}


def _t1_ops(cs):
    """Operators used by one Type 1 charstring, as a Counter.

    Decodes the number encoding so an argument byte below 32 is never
    read as a command -- the mistake that made `first_ops` report 88%
    on a correct tree.
    """
    out, i = Counter(), 0
    while i < len(cs):
        b = cs[i]
        if b >= 32:
            i += 1 if b <= 246 else (2 if b <= 254 else 5)
            continue
        if b == 12:
            if i + 1 >= len(cs):
                out["TRUNCATED"] += 1
                break
            out[_T1_ESC.get(cs[i + 1], f"esc{cs[i + 1]}")] += 1
            i += 2
            continue
        out[_T1_OPS.get(b, f"op{b}")] += 1
        i += 1
    return out


def m_charstrings(root, n, rng, doc=None):
    """U9 interpreter premise: which of the Type 1 charstring language a
    rasterizer must actually implement.

    The spec has 25 operators. Building all of them before knowing which
    occur is how a unit doubles in size for nothing -- and two of them,
    `seac` and `callothersubr`, are not drawing commands at all but
    escape hatches into composite glyphs and into the flex/hint-
    replacement protocol, each of which is a subsystem rather than a
    case in a switch.

    POPULATION: Type 1 fonts on this machine, not the corpus -- `root`
    is ignored, because U9's route B reads outlines from the TeX tree
    and that is where the charstrings to be interpreted live. Reported
    twice: over ALL fonts, and over MATHS families only, since maths is
    the application and body text is 99% of any unweighted count.

    SPLIT: fonts sampled without replacement; every charstring of a
    sampled font counts, so a font with 3,000 glyphs outweighs one with
    100 -- which is correct here, because the question is what an
    interpreter will MEET, not what a typical font declares.

    SUBRS ARE PART OF THE POPULATION. The first version of this
    measurement scanned charstrings only and reported `return` as
    occurring in 0 of 209,550 -- which is impossible in a language with
    subroutines, and is what exposed the error: `return` only ever
    appears inside a subr. An interpreter meets both, so both are
    counted, and the two are reported separately because a subr is
    entered by reference and a charstring is not.
    """
    tree = pathlib.Path(os.environ.get("INKDRILL_TYPE1",
                                       "/usr/share/texmf-dist/fonts/type1"))
    if not tree.is_dir():
        print(f"  no Type 1 tree at {tree}; set INKDRILL_TYPE1")
        return
    files = sorted(tree.rglob("*.pfb"))
    if not files:
        print(f"  no .pfb under {tree}")
        return
    picked = files if len(files) <= n else rng.sample(files, n)
    allc, mathc = Counter(), Counter()
    glyphs = mglyphs = 0
    per_glyph = Counter()
    subc, per_sub = Counter(), Counter()
    subs = 0
    fonts = mfonts = 0
    for p in picked:
        try:
            f = t1_load(p)
        except Exception:
            continue
        fonts += 1
        maths = is_math_family(f.name or p.stem)
        mfonts += maths
        for cs in f.charstrings.values():
            ops = _t1_ops(cs)
            glyphs += 1
            allc.update(ops)
            for k in ops:
                per_glyph[k] += 1
            if maths:
                mglyphs += 1
                mathc.update(ops)
        for sub in f.subrs:
            if sub:
                subs += 1
                sops = _t1_ops(sub)
                subc.update(sops)
                for k in sops:
                    per_sub[k] += 1
    if not glyphs:
        print("  no charstrings parsed")
        return
    print(f"  {fonts} fonts ({mfonts} maths), {glyphs} charstrings "
          f"({mglyphs} in maths fonts)")
    print(f"  operators by SHARE OF GLYPHS that use them at least once:")
    for k, v in per_glyph.most_common():
        star = "  <-- subsystem" if k in ("seac", "callothersubr") else ""
        print(f"    {v:9} ({v/glyphs:7.2%})  {k}{star}")
    print(f"  {subs} subroutines, operators by share of SUBRS using them:")
    for k, v in per_sub.most_common(8):
        print(f"    {v:9} ({v/subs:7.2%})  {k}")
    both = set(per_glyph) | set(per_sub)
    never = [o for o in list(_T1_OPS.values()) + list(_T1_ESC.values())
             if o not in both]
    print(f"  operators never seen in EITHER population ({len(never)}): "
          f"{', '.join(never) or '-'}")
    if mglyphs:
        print("  maths-font glyphs only, share using each:")
        seen = Counter()
        for k, v in mathc.items():
            seen[k] = v
        for k in ("seac", "callothersubr", "div", "flex", "hvcurveto"):
            if k in mathc:
                print(f"    {k}: {mathc[k]} occurrences in {mglyphs} glyphs")


def m_rasterisers(root, n, rng, doc=None):
    """U9 -> U13 premise: does a template rendered by `scan` match a
    query rendered by Ghostscript?

    Maths templates come from the font and queries come from the page,
    so the classifier's first real measurement is a CROSS-RASTERISER
    comparison. The two differ by construction: Ghostscript fills by
    coverage with anti-aliasing and `scan` samples pixel centres with
    none, so the same nominal stroke lands a fraction of a pixel wider
    on one side than the other.

    POPULATION: glyphs of one roman text face (`cmr10`), rendered both
    ways at the SAME nominal size, over several sizes -- because the
    bias is absolute and sub-pixel, so its importance is a function of
    how thick the strokes are, and one size cannot show that.

    `root` is ignored; the font comes from the TeX tree, like the rest
    of route B.
    """
    import subprocess
    from inkdrill.type1 import _split_pfb
    tree = pathlib.Path(os.environ.get("INKDRILL_TYPE1",
                                       "/usr/share/texmf-dist/fonts/type1"))
    src = next(tree.rglob("cmr10.pfb"), None) if tree.is_dir() else None
    if src is None:
        print(f"  cmr10.pfb not found under {tree}; set INKDRILL_TYPE1")
        return
    clear, enc = _split_pfb(src.read_bytes())
    # A PFB is a segmented wrapper around a PostScript program. Inlined
    # rather than `run`, because Ghostscript sandboxes file access.
    font_ps = clear + enc + b"\n" + b"0" * 512 + b"\ncleartomark\n"
    f = t1_load(src)
    names = ["o", "e", "a", "b", "d", "g", "B", "A", "O", "R", "eight",
             "zero", "two", "three", "P", "D", "c", "n", "s", "u"][:max(n, 4)]
    dpi = 400

    def gs(nm, pt):
        body = ("\n/CMR10 findfont %d scalefont setfont\n30 30 moveto\n"
                "/%s glyphshow\nshowpage\n" % (pt, nm)).encode()
        tmp = pathlib.Path(os.environ.get("TMPDIR", "/tmp")) / "inkdrill_r.ps"
        png = tmp.with_suffix(".png")
        tmp.write_bytes(b"%!PS\n" + font_ps + body)
        r = subprocess.run(
            ["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=png16m",
             f"-r{dpi}", "-g400x400", "-dTextAlphaBits=4",
             "-dGraphicsAlphaBits=4", f"-sOutputFile={png}", str(tmp)],
            capture_output=True)
        if r.returncode or not png.exists():
            return None
        return _crop_ink(load_mask(png, threshold=200))

    def topo(m):
        res = sweep(m, conn=8, capture=Capture.GRAPH)
        try:
            sig = signature(contract(res))
        except Exception:
            sig = None
        return (len(res.components),
                sum(c.cycle_count for c in res.components), sig)

    print("  cmr10, Ghostscript (coverage + AA) vs scan (centre, no AA)")
    print(f"  {'pt':>4} {'px/em':>6} {'topology':>9} {'signature':>10} "
          f"{'bitmap med':>11} {'ink gs/scan':>12}")
    for pt in (10, 12, 20, 40):
        px_em = pt * dpi / 72.0
        ok_t = ok_s = tot = 0
        dists, ratios = [], []
        for nm in names:
            if nm not in f.charstrings:
                continue
            a = gs(nm, pt)
            if a is None:
                continue
            b, _ = scan_render(cs_outline(f, nm), f.units_per_em, px_em)
            ca, ha, sa = topo(a)
            cb, hb, sb = topo(b)
            tot += 1
            ok_t += (ca == cb and ha == hb)
            ok_s += (sa == sb)
            dists.append((normalise(a) ^ normalise(b)).bit_count())
            if b.ink_count:
                ratios.append(a.ink_count / b.ink_count)
        if not tot:
            continue
        med = sorted(dists)[len(dists) // 2]
        rat = sorted(ratios)[len(ratios) // 2] if ratios else float("nan")
        print(f"  {pt:>4} {px_em:>6.0f} {ok_t:>4}/{tot:<4} {ok_s:>5}/{tot:<4} "
              f"{med:>8}/1024 {rat:>12.3f}")
    print("  The ink ratio is the stroke bias: Ghostscript is heavier, and")
    print("  the excess SHRINKS with size, which is what an absolute")
    print("  sub-pixel bias must do as strokes thicken relative to it.")


MATH_FONTS = ("cmmi10.pfb", "cmsy10.pfb", "cmex10.pfb",
              "msam10.pfb", "msbm10.pfb")


def _feature_tuple(sig):
    """The signature as a feature vector -- ONE definition.

    Assembled inline at two call sites before this existed, and both
    dropped `parts` and `closes`; the second inherited the defect by
    copy and was fixed a commit later than the first. A tuple built at
    each call site drifts, and this one drifted silently because the
    missing fields made a channel look weak rather than making anything
    fail.
    """
    return (sig.parts, sig.cycles, sig.births, sig.closes,
            sig.merges, sig.splits)


def _crop_ink(mask):
    """The whole inked area of a render, not its largest component.

    Taking `max(components, key=ink_count)` drops the dot of an `i` and
    the bar of a `Theta` -- which is exactly the `parts` field the
    signature verifier depends on. A query stripped of its parts matches
    `dotlessi` by construction, so the harness manufactured the very
    confusions it then reported as findings.
    """
    from inkdrill.raster import InkMask
    res = sweep(mask, conn=8, capture=Capture.GRAPH)
    if not res.components:
        return None
    node = {nd.id: nd for nd in res.nodes}
    runs = [node[i] for c in res.components for i in c.nodes]
    x0 = min(r.lo for r in runs)
    x1 = max(r.hi for r in runs)
    y0 = min(r.line for r in runs)
    y1 = max(r.line for r in runs)
    w, h = x1 - x0 + 1, y1 - y0 + 1
    buf = bytearray(w * h)
    for r in runs:
        b = (r.line - y0) * w - x0
        buf[b + r.lo:b + r.hi + 1] = b"\xff" * (r.hi - r.lo + 1)
    return InkMask(bytes(buf), w, h)


def _template_of(mask, label):
    from inkdrill.aggregate import moments_of_mask
    from inkdrill.reeb import graph_of, signature as reeb_signature
    if mask is None or mask.width == 0 or mask.height == 0:
        return None
    sig = reeb_signature(graph_of(mask))
    mo = moments_of_mask(mask)
    w, h = mask.width, mask.height
    # The WHOLE signature. An earlier version stored four of its six
    # fields and dropped `parts` and `closes` -- and `parts` is exactly
    # what separates i/dotlessi and Theta/O. A verifier measured on a
    # crippled feature is measuring the harness.
    return Template(label, normalise(mask),
                    _feature_tuple(sig),
                    (w / h, float(h), float(w), mo.elongation))


def m_maths(root, n, rng, doc=None, extents_tol=None, candidates=0,
            candidate_families=0):
    """**The measurement this whole chain was built for.**

    Every accuracy figure in this repository is body text. U13's class
    filter (>=12 instances) excluded every maths symbol and the only
    non-ASCII survivors were the quotes and the fi ligature. So maths
    classification has never been measured, and two units are partial on
    it.

    PROTOCOL: templates rendered from the FONT by
    `type1 -> charstring -> scan`; queries rendered from the same font by
    GHOSTSCRIPT. That is the real deployment shape -- a template comes
    from the document's own font and a query comes from the page -- and
    `measure.py rasterisers` established what the two paths do differ
    by: an 18.8% ink bias at body-text size and 15 bits in 1024.

    POPULATION: every glyph of the TeX maths families, so the class
    count is in the hundreds rather than U13's 23. **State the class
    count beside the accuracy** -- a 300-class problem and a 23-class
    problem are not comparable, and chance alone differs by an order of
    magnitude.

    WHAT THIS DOES NOT TEST: the same font is on both sides, so this is
    cross-RASTERISER, not cross-font. It also has no page noise, no
    neighbouring ink and no baseline variation. It is the ceiling, and a
    figure measured here is an upper bound on a real page.

    THE RESIDUAL IS THE PRODUCT. A wrong answer that the signature
    channel REJECTS is a detected error, which is what this project is
    for; a wrong answer it accepts is the dangerous class. Both are
    reported, never one accuracy.
    """
    import subprocess
    from inkdrill.type1 import _split_pfb
    tree = pathlib.Path(os.environ.get("INKDRILL_TYPE1",
                                       "/usr/share/texmf-dist/fonts/type1"))
    if not tree.is_dir():
        print(f"  no Type 1 tree at {tree}; set INKDRILL_TYPE1")
        return
    pt, dpi = 10, 400
    px_em = pt * dpi / 72.0
    tmp = pathlib.Path(os.environ.get("TMPDIR", "/tmp"))

    templates, queries = [], []
    for fname in MATH_FONTS:
        src = next(tree.rglob(fname), None)
        if src is None:
            continue
        f = t1_load(src)
        ps_name = (f.name or src.stem).upper()
        clear, encp = _split_pfb(src.read_bytes())
        font_ps = clear + encp + b"\n" + b"0" * 512 + b"\ncleartomark\n"
        names = sorted(f.charstrings)
        if n and len(names) > n:
            names = rng.sample(names, n)
        made = 0
        for nm in names:
            if nm == ".notdef":
                continue
            label = f"{src.stem}:{nm}"
            try:
                g = cs_outline(f, nm)
            except Exception:
                continue
            if g.is_empty:
                continue
            mask, _ = scan_render(g, f.units_per_em, px_em)
            t = _template_of(mask, label)
            if t is None:
                continue
            body = ("\n/%s findfont %d scalefont setfont\n30 30 moveto\n"
                    "/%s glyphshow\nshowpage\n" % (ps_name, pt, nm)).encode()
            psf = tmp / "inkdrill_m.ps"
            png = tmp / "inkdrill_m.png"
            psf.write_bytes(b"%!PS\n" + font_ps + body)
            r = subprocess.run(
                ["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=png16m",
                 f"-r{dpi}", "-g400x400", "-dTextAlphaBits=4",
                 "-dGraphicsAlphaBits=4", f"-sOutputFile={png}", str(psf)],
                capture_output=True)
            if r.returncode or not png.exists():
                continue
            q = _template_of(_crop_ink(load_mask(png, threshold=200)), label)
            if q is None:
                continue
            templates.append(t)
            queries.append(q)
            made += 1
        print(f"  {src.stem:10} {made} glyphs")
    if not queries:
        print("  nothing rendered; is ghostscript on PATH?")
        return

    labels = {t.label for t in templates}
    print(f"  {len(templates)} templates, {len(queries)} queries, "
          f"{len(labels)} CLASSES (chance = {1/len(labels):.3%})")
    # The deployment protocol. 647 classes is the open set; a real
    # document constrains the answer to the glyphs its own fonts
    # actually draw -- measured over 21 corpus documents with maths
    # fonts, a MEDIAN OF 53 distinct maths glyphs, range 3-195, which
    # is 8.2% of the open set.
    #
    # Modelled by drawing the candidate set per query: the true class
    # plus `candidates - 1` others. STATED LIMIT: the sample is uniform
    # over all five families, so it keeps cross-font confusability but
    # loses the correlation of which glyphs actually co-occur in one
    # paper. A real candidate set is drawn from fewer families and is
    # therefore likely HARDER than this models, not easier.
    if candidates:
        print(f"  candidate set {candidates} per query (open set is "
              f"{len(labels)}; corpus median is 53)")
    for name, ch in (("bitmap only", Channels(1.0, 0.0, 0.0)),
                     ("extents only", Channels(0.0, 0.0, 1.0)),
                     ("signature only", Channels(0.0, 1.0, 0.0)),
                     ("all channels", Channels(1.0, 1.0, 1.0))):
        clf = Classifier(channels=ch)
        for t in templates:
            clf.add(t)
        right = detected = missed = false_reject = 0
        worst = Counter()
        by_label = defaultdict(list)
        for t in templates:
            by_label[t.label].append(t)
        pool = sorted(by_label)
        for qi, q in enumerate(queries):
            if candidates and candidates < len(pool):
                r = random.Random(20260810 + qi)
                others = [l for l in pool if l != q.label]
                if candidate_families:
                    # A real document draws its maths glyphs from a few
                    # families, not from all of them: measured over 40
                    # corpus documents the median is 4 of these 5. Draw
                    # the candidate set the same way, keeping the true
                    # class's own family in, so within-family
                    # confusability is preserved rather than diluted.
                    fams = sorted({l.split(":")[0] for l in pool})
                    own = q.label.split(":")[0]
                    rest = [f for f in fams if f != own]
                    keep = {own} | set(r.sample(
                        rest, min(candidate_families - 1, len(rest))))
                    others = [l for l in others if l.split(":")[0] in keep]
                pick = r.sample(others, min(candidates - 1, len(others)))
                sub = Classifier(channels=ch)
                for lab in pick + [q.label]:
                    for t in by_label[lab]:
                        sub.add(t)
                clf_q = sub
            else:
                clf_q = clf
            pred = clf_q.classify(q)
            if pred.label == q.label:
                right += 1
                # The other side of the ledger. A verifier that rejects
                # everything scores a perfect "accepted" rate, so the
                # rate at which it rejects CORRECT answers must be
                # printed beside it or the number is meaningless.
                if not clf_q.agrees(q, pred.label, extents_tol=extents_tol):
                    false_reject += 1
            else:
                # A wrong answer the signature REJECTS is a DETECTED
                # error -- the product. One it accepts is the dangerous
                # class.
                if clf_q.agrees(q, pred.label, extents_tol=extents_tol):
                    missed += 1
                    worst[(q.label, pred.label)] += 1
                else:
                    detected += 1
        tot = len(queries)
        print(f"    {name:15} {right/tot:7.2%}  "
              f"wrong-and-detected {detected/tot:6.2%}  "
              f"WRONG AND ACCEPTED {missed/tot:6.2%}  "
              f"correct-but-REJECTED {false_reject/max(right,1):6.2%}")
        if name == "all channels" and worst:
            print("      most dangerous confusions (wrong, accepted):")
            for (a, b), k in worst.most_common(6):
                print(f"        {a}  read as  {b}   x{k}")


# TeX's own math spacing, in em. These are DEFINITIONS from the
# typesetter, not clusters found in data -- which is what makes them a
# prediction the measurement can fail.
TEX_SPACES = {"none": 0.0, "thin": 3 / 18, "medium": 4 / 18,
              "thick": 5 / 18, "quad": 1.0}


def m_spacing(root, n, rng, doc=None):
    """M1.1: does typography explain the horizontal geometry?

    The residual is what a glyph's position is NOT explained by the
    previous glyph's advance:

        r(a, b) = x0(b) - (x0(a) + advance(a))

    pdfminer gives `x0` and `adv` per character, so this needs no new
    extraction. Divided by the font size it is in em, and TeX's math
    spaces are DEFINED in em -- thin 3/18, medium 4/18, thick 5/18,
    quad 1 -- so the modes to look for are stated in advance rather
    than discovered. A measurement that finds them is evidence; one
    that finds a single blob says the spacing edges of a relation graph
    were never going to work, which is the cheaper answer to get first.

    POPULATION: adjacent character pairs within one pdfminer line, same
    font and size, in reading order. Reported separately for MATHS
    fonts and text fonts, because TeX applies math spacing only in math
    mode and pooling them would let body text set the shape.

    SPLIT: documents sampled without replacement; every qualifying pair
    of a sampled document counts.

    FILTER: pairs with a negative residual (the glyph starts before the
    previous one ended) are counted and reported, not dropped -- they
    are kerning, which is the one class this formula cannot separate
    from a typesetting space without the font's kern table.
    """
    docs = [(cj.parent, cj) for cj in sorted(root.glob("*/*.chars.json"))]
    if doc:
        docs = [t for t in docs if t[0].name == doc]
    else:
        rng.shuffle(docs)
    math_r, text_r = [], []
    neg = 0
    ndoc = 0
    for d, cj in docs:
        if ndoc >= n:
            break
        try:
            data = json.load(cj.open())
        except Exception:
            continue
        got = False
        for page in data["pages"]:
            chars = [c for c in page["chars"] if c.get("text", "").strip()]
            chars.sort(key=lambda c: (round(c["top"], 1), c["x0"]))
            for a, b in zip(chars, chars[1:]):
                if a["fontname"] != b["fontname"]:
                    continue
                if abs(a["size"] - b["size"]) > 0.01 or a["size"] <= 0:
                    continue
                if abs(a["top"] - b["top"]) > 0.5:      # same line
                    continue
                r = (b["x0"] - (a["x0"] + a["adv"])) / a["size"]
                if not -1.0 < r < 2.0:
                    continue
                if r < -0.005:
                    neg += 1
                (math_r if is_math_family(a["fontname"]) else text_r).append(r)
                got = True
        ndoc += got
    if not math_r and not text_r:
        print("  no qualifying adjacent pairs")
        return
    print(f"  {ndoc} documents;  maths pairs {len(math_r)}, "
          f"text pairs {len(text_r)};  negative residuals {neg} "
          f"(kerning -- this formula cannot separate it from a space)")

    def report(label, vals):
        if not vals:
            return
        vals = sorted(vals)
        print(f"  {label} (n={len(vals)}):")
        # Fixed bins, so two populations are directly comparable.
        edges = [-0.05, 0.005, 0.05, 0.12, 0.20, 0.25, 0.31, 0.5, 0.8, 2.0]
        hist = Counter()
        for v in vals:
            for e in edges:
                if v < e:
                    hist[e] += 1
                    break
        lo = None
        for e in edges:
            k = hist[e]
            bar = "#" * int(60 * k / len(vals))
            print(f"    {'' if lo is None else f'{lo:+.3f}':>7}"
                  f" .. {e:+.3f}  {k:7} ({k/len(vals):6.2%}) {bar}")
            lo = e
        # How much mass sits within 0.02 em of a DEFINED TeX space?
        for nm, target in TEX_SPACES.items():
            near = sum(1 for v in vals if abs(v - target) <= 0.02)
            print(f"      within 0.02 em of {nm:6} ({target:.4f}): "
                  f"{near:7} ({near/len(vals):6.2%})")

    report("MATHS fonts", math_r)
    report("text fonts", text_r)

    # M1.2. The class must not be a binning of the feature itself -- that
    # would be circular. The honest question is whether the residual
    # carries information about MODE, so the label is maths-font vs
    # text-font, which is independent of the residual.
    #
    # And per U12: report the CEILING beside the MI. A feature with k
    # values against a 2-class label cannot exceed H(label), so a
    # continuous feature finely binned will always look better than a
    # coarse one for reasons that have nothing to do with the data.
    edges = [0.005, 0.05, 0.12, 0.20, 0.25, 0.31, 0.5, 0.8]

    def band(v):
        for i, e in enumerate(edges):
            if v < e:
                return i
        return len(edges)

    xs = [band(v) for v in math_r] + [band(v) for v in text_r]
    ys = ["maths"] * len(math_r) + ["text"] * len(text_r)
    mi = mutual_information(xs, ys)
    ceil = mi_ceiling(xs, ys)
    print(f"  residual band vs maths/text: MI {mi:.4f} bits, "
          f"ceiling {ceil:.4f}, efficiency {efficiency(xs, ys):.3f}")
    print(f"  the single most diagnostic band is the thin space: "
          f"{sum(1 for v in math_r if abs(v - 3/18) <= 0.02)/max(len(math_r),1):.2%} "
          f"of maths pairs against "
          f"{sum(1 for v in text_r if abs(v - 3/18) <= 0.02)/max(len(text_r),1):.2%} "
          f"of text pairs")
    print("  CAUTION: the text peak near 0.28 em is the WORD SPACE -- the")
    print("  space glyph is filtered out by `text.strip()`, so its advance")
    print("  reappears as a gap. It is not TeX's thick space.")


def _blocked(a, b, others):
    """Is the centre-to-centre segment from `a` to `b` blocked?

    The line-of-sight test, in its usual approximation: a third symbol
    occludes the pair if its box crosses the segment. Boxes are
    (x0, y0, x1, y1) with y increasing downward.
    """
    ax, ay = (a[0] + a[2]) / 2, (a[1] + a[3]) / 2
    bx, by = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    dx, dy = bx - ax, by - ay
    for c in others:
        # Liang-Barsky against the box; t restricted to the open segment
        # so a box touching an endpoint does not count as blocking.
        t0, t1 = 0.0, 1.0
        ok = True
        for p, q in ((-dx, ax - c[0]), (dx, c[2] - ax),
                     (-dy, ay - c[1]), (dy, c[3] - ay)):
            if p == 0:
                if q < 0:
                    ok = False
                    break
                continue
            r = q / p
            if p < 0:
                if r > t1:
                    ok = False
                    break
                t0 = max(t0, r)
            else:
                if r < t0:
                    ok = False
                    break
                t1 = min(t1, r)
        if ok and t1 > t0 and t1 > 0.02 and t0 < 0.98:
            return True
    return False


def m_edges(root, n, rng, doc=None):
    """M2.1: which candidate-edge rule should a relation graph use?

    Three strategies from the lgap comparison -- 2NN, 6NN and
    line-of-sight -- measured on this corpus rather than taken on
    faith, because the published comparison was on a handwriting-heavy
    benchmark and this population is printed arXiv maths.

    ORACLE, and its limits. There is no relation gold set here yet (M0
    is the other CLI's), so the necessary condition is used instead:
    **two characters adjacent in pdfminer's reading order must be
    connected**, or no relation between them is expressible at all.
    That is a lower bound on what a candidate graph has to contain, not
    a measure of whether its other edges are useful -- a complete graph
    scores 100% on it. So recall is reported BESIDE edges-per-node, and
    neither means anything alone.

    The occlusion count is the claim being tested: LOS exists because
    kNN connects symbols with a third between them, which is said to
    fail around fractions and large operators. That is measurable here
    directly, with no gold at all.

    POPULATION: pdfminer lines of >= 3 characters containing at least
    one maths-font glyph, so the graph is measured where it would run.
    """
    docs = [(cj.parent, cj) for cj in sorted(root.glob("*/*.chars.json"))]
    if doc:
        docs = [t for t in docs if t[0].name == doc]
    else:
        rng.shuffle(docs)
    stats = {k: [0, 0, 0] for k in ("2NN", "6NN", "LOS")}   # hit, want, edges
    occl = Counter()
    nlines = nnodes = ndoc = 0
    for d, cj in docs:
        if ndoc >= n:
            break
        try:
            data = json.load(cj.open())
        except Exception:
            continue
        got = False
        for page in data["pages"]:
            rows = defaultdict(list)
            for c in page["chars"]:
                if c.get("text", "").strip():
                    rows[round(c["top"], 0)].append(c)
            for _, cs_ in rows.items():
                if len(cs_) < 3 or not any(is_math_family(c["fontname"])
                                           for c in cs_):
                    continue
                cs_.sort(key=lambda c: c["x0"])
                if len(cs_) > 40:
                    cs_ = cs_[:40]           # bound the O(n^3) LOS check
                box = [(c["x0"], c["top"], c["x1"], c["bottom"]) for c in cs_]
                cen = [((b[0] + b[2]) / 2, (b[1] + b[3]) / 2) for b in box]
                m = len(box)
                nlines += 1
                nnodes += m
                need = {(i, i + 1) for i in range(m - 1)}
                for name in stats:
                    E = set()
                    if name == "LOS":
                        for i in range(m):
                            for j in range(i + 1, m):
                                others = [box[k] for k in range(m)
                                          if k != i and k != j]
                                if not _blocked(box[i], box[j], others):
                                    E.add((i, j))
                    else:
                        k = 2 if name == "2NN" else 6
                        for i in range(m):
                            order = sorted(
                                range(m),
                                key=lambda j: ((cen[i][0] - cen[j][0]) ** 2 +
                                               (cen[i][1] - cen[j][1]) ** 2))
                            for j in order[1:k + 1]:
                                E.add((min(i, j), max(i, j)))
                        for i, j in E:
                            others = [box[k] for k in range(m)
                                      if k != i and k != j]
                            if _blocked(box[i], box[j], others):
                                occl[name] += 1
                    stats[name][0] += len(need & E)
                    stats[name][1] += len(need)
                    stats[name][2] += len(E)
                got = True
        ndoc += got
    if not nlines:
        print("  no qualifying lines")
        return
    print(f"  {ndoc} documents, {nlines} maths lines, {nnodes} symbols "
          f"({nnodes/nlines:.1f} per line)")
    print(f"  {'strategy':10} {'reading-order recall':>21} "
          f"{'edges/node':>11} {'occluded edges':>15}")
    for name, (hit, want, ed) in stats.items():
        print(f"  {name:10} {hit/want:20.2%} {ed/nnodes:11.2f} "
              f"{(str(occl[name]) if name in occl else '0 by construction'):>15}")
    print("  Recall alone is not a ranking: a complete graph scores 100%.")
    print("  Read it against edges/node -- the cost of that recall.")


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
                                      _feature_tuple(s),
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
    "charstrings": (m_charstrings, 400),
    "boxes": (m_boxes, 8),
    "edges": (m_edges, 8),
    "spacing": (m_spacing, 12),
    "maths": (m_maths, 0),
    "rasterisers": (m_rasterisers, 20),
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
    ap.add_argument("--candidates", type=int, default=0,
                    help="maths only: classes visible per query. 0 is the "
                         "open set; 53 is the corpus median for one "
                         "document's own maths fonts.")
    ap.add_argument("--candidate-families", type=int, default=0,
                    help="maths only: draw the candidate set from this many "
                         "families rather than all of them. 4 is the corpus "
                         "median per document; 1 is the hardest case.")
    ap.add_argument("--extents-tol", type=float, default=None,
                    help="maths only: make the verifier a CONJUNCTION -- "
                         "signature AND extents within this distance. "
                         "None (default) is signature-only.")
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
        elif name == "maths":
            fn(root, args.n or default_n, random.Random(args.seed),
               extents_tol=args.extents_tol, candidates=args.candidates,
               candidate_families=args.candidate_families)
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
