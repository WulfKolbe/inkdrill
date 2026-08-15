"""fontmatch.py -- classify a page's glyphs against a FONT FILE's renders.

CONTRACT
========

Templates come from an EXTERNAL renderer (ImageMagick `magick`), not
from a font parser: `type1.py` reads only Type 1 programs, and
`measure.py fontmix` put that route at ~29% of general documents. A
scanned book has no embedded font at all, so the only honest template
source is "some font file, rendered" -- and rendering is exactly the
part an external tool already does. No new parser.

    python3 tools/fontmatch.py --font /path/to/font.ttf --page page.png
        [--threshold 200] [--chars ...] [--top 0]

WHAT THE REPORT IS, AND IS NOT
------------------------------
Per character: the HIT COUNT (how many page glyphs land nearest that
template) and the distance min/median/max. This is a CLOSED SET over
`--chars`: every glyph is assigned to something, so a hit count alone
proves nothing -- junk assignments hide in the distance columns, which
is why they are printed beside it.

The end-of-report check is LETTER-FREQUENCY ORDERING, not accuracy.
There is no ground truth for a scanned page here, but German prose has
a known frequency ordering (e n i r s t a d h u l ...), so a matcher
that is working puts `e` and `n` on top with tight distances, and one
that is broken produces an ordering no language has. It is a sanity
oracle, exactly as weak and exactly as cheap as that sounds.

POPULATION -- printed, because it is a decision
-----------------------------------------------
Page glyphs are `mathstruct.group()` CLUSTERS (so `i`, umlauts and `:`
arrive whole), filtered to glyph-sized: height within [0.25, 2.5]x and
width within 3x the median cluster height. Kept and dropped counts are
printed. The font is almost never the book's font; the report states
which file rendered the templates, and the mismatch caps everything
downstream -- distances are comparable within one run, not across
fonts.

Calibration: the templates are rendered so `n` matches the page's
median cluster height. The bitmap channel is resampled to a fixed grid
and does not care; the EXTENTS channel compares absolute pixels and
does, which is why the calibration exists and is printed.
"""

from __future__ import annotations

import argparse
import pathlib
import statistics
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from inkdrill.classify import Classifier, NoTemplates, template_of  # noqa: E402
from inkdrill.mathstruct import Glyph, group                        # noqa: E402
from inkdrill.nest import ink_only                                  # noqa: E402
from inkdrill.pngio import load_mask                                # noqa: E402
from inkdrill.pnmio import load_mask as pnm_load                    # noqa: E402
from inkdrill.raster import InkMask                                 # noqa: E402

#: German prose letter-frequency ordering, most common first. The
#: sanity oracle the report closes with -- a reference, not a truth.
GERMAN = "enisratdhulcgmobwfkzvüpäßjöyqx"

DEFAULT_CHARS = ("abcdefghijklmnopqrstuvwxyz"
                 "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                 "äöüßÄÖÜ0123456789.,;:-()'!?")


def render_char(font: str, ch: str, pointsize: float) -> InkMask | None:
    """One character through `magick`, as a mask. None if unrenderable."""
    r = subprocess.run(
        ["magick", "-background", "white", "-fill", "black",
         "-font", font, "-pointsize", f"{pointsize:.1f}",
         f"label:{ch}", "-depth", "8", "-colorspace", "gray", "pgm:-"],
        capture_output=True)
    if r.returncode or not r.stdout.startswith(b"P5"):
        return None
    try:
        # dpi is a required formality of the PNM reader; nothing here
        # reads coordinates back out in points.
        return pnm_load(r.stdout, dpi=72, threshold=128)
    except ValueError:
        return None


def crop_ink(mask: InkMask) -> InkMask | None:
    """The WHOLE inked area -- not the largest component, which drops
    the dot of an `i` and the umlaut of an `ä` (the measure.py lesson,
    `_crop_ink`)."""
    w, h = mask.width, mask.height
    d = mask.data
    x0 = y0 = 1 << 30
    x1 = y1 = -1
    for y in range(h):
        base = y * w
        lo = d.find(b"\xff", base, base + w)
        if lo < 0:
            continue
        hi = d.rfind(b"\xff", base, base + w)
        y1 = y
        if y0 == 1 << 30:
            y0 = y
        x0 = min(x0, lo - base)
        x1 = max(x1, hi - base)
    if x1 < 0:
        return None
    cw, ch_ = x1 - x0 + 1, y1 - y0 + 1
    buf = bytearray(cw * ch_)
    for j in range(ch_):
        src = (y0 + j) * w + x0
        buf[j * cw:(j + 1) * cw] = d[src:src + cw]
    return InkMask(bytes(buf), cw, ch_)


def crop_box(mask: InkMask, x0: int, y0: int, x1: int, y1: int) -> InkMask:
    """A bbox crop, neighbours included -- what a page hands a matcher."""
    w = x1 - x0 + 1
    h = y1 - y0 + 1
    buf = bytearray(w * h)
    for j in range(h):
        src = (y0 + j) * mask.width + x0
        buf[j * w:(j + 1) * w] = mask.data[src:src + w]
    return InkMask(bytes(buf), w, h)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--font", required=True,
                    help="font file (or magick font name) for templates")
    ap.add_argument("--page", required=True, type=pathlib.Path)
    ap.add_argument("--threshold", type=int, default=200)
    ap.add_argument("--chars", default=DEFAULT_CHARS)
    ap.add_argument("--top", type=int, default=0,
                    help="rows to print; 0 = every char with a hit")
    args = ap.parse_args(argv)

    mask = load_mask(args.page, threshold=args.threshold)
    regions = ink_only(mask).regions
    if not regions:
        sys.exit("no ink on the page")
    glyphs = [Glyph(r.id, float(r.x0), float(r.y0), float(r.x1),
                    float(r.y1)) for r in regions]
    by_id = {g.id: g for g in glyphs}
    clusters = group(glyphs)
    boxes = []
    for ids in clusters:
        gs = [by_id[i] for i in ids]
        boxes.append((int(min(g.x0 for g in gs)), int(min(g.top for g in gs)),
                      int(max(g.x1 for g in gs)),
                      int(max(g.bottom for g in gs))))
    med = statistics.median(y1 - y0 + 1 for _, y0, _, y1 in boxes)

    # THE FILTER, printed. Glyph-sized only; rules, blobs and specks
    # leave the population here and nowhere else.
    kept, dropped = [], 0
    for x0, y0, x1, y1 in boxes:
        w, h = x1 - x0 + 1, y1 - y0 + 1
        if 0.25 * med <= h <= 2.5 * med and w <= 3 * med:
            kept.append((x0, y0, x1, y1))
        else:
            dropped += 1
    print(f"page {args.page.name}: {len(regions)} components, "
          f"{len(clusters)} clusters, median height {med:.0f} px")
    print(f"FILTER glyph-sized: kept {len(kept)}, dropped {dropped}")

    # Calibrate `n` to the median cluster height, so the extents
    # channel compares like with like.
    probe = render_char(args.font, "n", 100.0)
    probe = crop_ink(probe) if probe else None
    if probe is None:
        sys.exit(f"cannot render from {args.font!r} via magick")
    pointsize = 100.0 * med / probe.height
    print(f"font {args.font}: calibrated pointsize {pointsize:.1f} "
          f"(n height {probe.height}px at 100pt -> target {med:.0f}px)")

    clf = Classifier()
    skipped = []
    for ch in dict.fromkeys(args.chars):
        m = render_char(args.font, ch, pointsize)
        m = crop_ink(m) if m else None
        t = template_of(m, ch) if m else None
        if t is None:
            skipped.append(ch)
            continue
        clf.add(t)
    print(f"templates: {len(clf.templates)} of {len(dict.fromkeys(args.chars))}"
          + (f", unrenderable: {''.join(skipped)}" if skipped else ""))

    hits: dict[str, list[float]] = {}
    unmatched = 0
    for x0, y0, x1, y1 in kept:
        q = template_of(crop_box(mask, x0, y0, x1, y1), "?")
        if q is None:
            unmatched += 1
            continue
        try:
            p = clf.classify(q, top_k=1)
        except NoTemplates:
            sys.exit("no templates")
        hits.setdefault(p.label, []).append(p.distance)

    rows = sorted(hits.items(), key=lambda kv: -len(kv[1]))
    if args.top:
        rows = rows[:args.top]
    print(f"\n{'char':>5} {'hits':>6} {'d.min':>8} {'d.med':>8} {'d.max':>8}")
    for ch, ds in rows:
        ds.sort()
        print(f"{ch!r:>5} {len(ds):>6} {ds[0]:>8.1f} "
              f"{ds[len(ds) // 2]:>8.1f} {ds[-1]:>8.1f}")
    if unmatched:
        print(f"(plus {unmatched} empty crops)")

    order = "".join(ch for ch, _ in sorted(hits.items(),
                                           key=lambda kv: -len(kv[1]))
                    if ch.isalpha())
    print(f"\nletter-frequency ordering (this page): {order}")
    print(f"German prose reference:                 {GERMAN}")
    print("A working matcher puts e/n on top with tight distances; a "
          "broken one\nproduces an ordering no language has. This is a "
          "sanity oracle, not accuracy:\nthe set is CLOSED and the font "
          "is not the book's.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
