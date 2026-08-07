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
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import random
import struct
import sys
import time
import zlib
from collections import Counter, defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from inkdrill.pngio import _is_neutral, read_png            # noqa: E402
from inkdrill.raster import INK, InkMask, binarize          # noqa: E402
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


MEASUREMENTS = {
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
    args = ap.parse_args()

    root = args.corpus.expanduser()
    if not root.is_dir():
        sys.exit(f"corpus not found: {root}")
    todo = sorted(MEASUREMENTS) if "all" in args.what else args.what
    for name in todo:
        fn, default_n = MEASUREMENTS[name]
        print(f"\n=== {name} " + "=" * (62 - len(name)))
        fn(root, args.n or default_n, random.Random(args.seed))


if __name__ == "__main__":
    main()
