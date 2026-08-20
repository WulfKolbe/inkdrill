"""028: the shape of a trailing punctuation mark in a scan crop.

A formula whose LaTeX ends in `.` `,` `;` or `:` carries that mark in
the SOURCE but the scan crop may or may not show it, and when it does
it is the rightmost component. Two numbers describe it, both
normalised by the crop's own median glyph height so they are
resolution-free:

    height   = component height / median glyph height
    baseline = (component bottom - baseline) / median glyph height

where the baseline is the median bottom of the crop's full-height
components. A period sits ON the baseline and is short; a comma
descends BELOW it. Anything tall, or far above the baseline, is not
punctuation and the profile has to say so.

Usage: python3 tools/punctprofile.py <bibkey-dir> [--limit N]
Writes the distribution to out/028.txt.
"""

from __future__ import annotations

import json
import pathlib
import re
import statistics
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from inkdrill.aggregate import moments_per_component      # noqa: E402
from inkdrill.pnmio import load_mask                      # noqa: E402
from inkdrill.sweep import Capture, sweep                 # noqa: E402

PUNCT = ".,;:"
# TeX spacing that may follow the mark and is not part of it
_TRAIL = re.compile(r"(\\[,;:!>]|\\quad|\\qquad|\\ |\\\\|\s|\$|\\\])+$")


def ends_in_punct(latex: str) -> str | None:
    """The trailing mark, or None. Spacing macros are stripped first."""
    t = _TRAIL.sub("", (latex or "").strip())
    return t[-1] if t and t[-1] in PUNCT else None


def crop_stats(jpg: pathlib.Path):
    """(height ratio, baseline offset, components) of the RIGHTMOST
    component, or None when the crop holds too little to measure."""
    with tempfile.TemporaryDirectory() as td:
        pgm = pathlib.Path(td) / "c.pgm"
        subprocess.run(["magick", str(jpg), "-colorspace", "gray",
                        "-depth", "8", str(pgm)], check=True)
        mask = load_mask(pgm, dpi=(72.0, 72.0))
    res = sweep(mask, axis="row", conn=8, capture=Capture.GRAPH)
    moms = moments_per_component(res)
    comps = [moms[c.root] for c in res.components if moms[c.root].area >= 4]
    if len(comps) < 4:
        return None
    heights = [c.height for c in comps]
    med = statistics.median(heights)
    if med <= 0:
        return None
    full = [c for c in comps if c.height >= 0.5 * med]
    base = statistics.median(c.y1 for c in full) if full else \
        statistics.median(c.y1 for c in comps)
    right = max(comps, key=lambda c: (c.x1, -c.y1))
    return (right.height / med, (right.y1 - base) / med, len(comps))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    limit = 50
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    rows = []
    for arg in args:
        d = pathlib.Path(arg).expanduser()
        bib = d.name
        f = d / f"{bib}.tiddlers.json"
        if not f.is_file():
            continue
        for t in json.loads(f.read_text()):
            title = t.get("title", "")
            if not re.match(re.escape(bib) + r"_EQ\d+", title):
                continue
            mark = ends_in_punct(t.get("latex") or t.get("latex_code") or "")
            if not mark:
                continue
            jpg = d / "report-crops" / f"{title}.jpg"
            if not jpg.is_file():
                continue
            rows.append((title, mark, jpg))
            if len(rows) >= limit:
                break
        if len(rows) >= limit:
            break
    bib = ", ".join(pathlib.Path(a).name for a in args)

    out = [f"028 trailing punctuation profile -- {bib}",
           f"population: the first {len(rows)} EQ rows whose LaTeX ends "
           f"in one of {PUNCT!r} and that have a scan crop",
           "measured on the CROP itself (not the report raster), both "
           "figures normalised by the crop's median glyph height",
           ""]
    recs = []
    for title, mark, jpg in rows:
        st = crop_stats(jpg)
        if st is None:
            out.append(f"  {title}  {mark}  too few components to measure")
            continue
        h, b, n = st
        recs.append((title, mark, h, b, n))
    out.append(f"{'identifier':22}{'mark':>5}{'height':>9}{'baseline':>10}"
               f"{'comps':>7}")
    for title, mark, h, b, n in recs:
        out.append(f"{title:22}{mark:>5}{h:>9.2f}{b:>10.2f}{n:>7}")

    if recs:
        hs = sorted(r[2] for r in recs)
        bs = sorted(r[3] for r in recs)

        def q(v, p):
            return v[min(len(v) - 1, int(p * len(v)))]
        out += ["",
                f"height ratio   min {hs[0]:.2f}  p25 {q(hs,.25):.2f}  "
                f"med {statistics.median(hs):.2f}  p75 {q(hs,.75):.2f}  "
                f"max {hs[-1]:.2f}",
                f"baseline offset min {bs[0]:.2f}  p25 {q(bs,.25):.2f}  "
                f"med {statistics.median(bs):.2f}  p75 {q(bs,.75):.2f}  "
                f"max {bs[-1]:.2f}",
                "",
                "height ratio histogram (bin 0.1):"]
        from collections import Counter
        c = Counter(round(h, 1) for h in hs)
        for k in sorted(c):
            out.append(f"  {k:4.1f}  {'#' * c[k]} {c[k]}")
        out.append("")
        out.append("baseline offset histogram (bin 0.1):")
        c = Counter(round(b, 1) for b in bs)
        for k in sorted(c):
            out.append(f"  {k:+4.1f}  {'#' * c[k]} {c[k]}")
    if recs:
        # WHAT THE RIGHTMOST COMPONENT ACTUALLY IS. The measurement
        # assumes it is the trailing mark; two crops checked by eye
        # say otherwise -- bh2_EQ0119's is a 16x1 px underline
        # fragment and bh2_EQ0103's is a 70 px matrix bracket, both
        # in rows whose LaTeX ends in a period. So the band below is
        # a NECESSARY condition, never a sufficient one, and the
        # fraction outside it is the visible part of the
        # contamination.
        band = [r for r in recs if r[2] <= 0.7 and abs(r[3]) <= 0.5]
        out += ["", "PROFILE (necessary, not sufficient):",
                "  height <= 0.7 x median glyph height AND "
                "|baseline offset| <= 0.5",
                f"  inside the band  {len(band)} of {len(recs)} "
                f"({100*len(band)/len(recs):.0f}%)",
                f"  outside          {len(recs)-len(band)} -- the "
                f"rightmost component is demonstrably NOT the mark",
                "",
                "  Checked by eye, both inside-the-band cases and one "
                "outside:",
                "    bh2_EQ0119 (h 0.06, b +0.12) -- a 16x1 px "
                "UNDERLINE fragment, not a period",
                "    bh2_EQ0011 (h 0.59, b +0.41) -- a 5x10 px comma, "
                "correct",
                "    bh2_EQ0103 (h 5.83, b +1.17) -- a 12x70 px matrix "
                "BRACKET, not a period",
                "",
                "  So a rule that drops the rightmost component when it "
                "falls in the band will drop the wrong component on an "
                "unmeasured fraction of rows: the band admits an "
                "underline fragment as readily as a period. 029 must "
                "report its firing count, and 030's distribution is "
                "what tests whether the trim helped or hurt."]
    dest = pathlib.Path(__file__).resolve().parent.parent / "out" / "028.txt"
    dest.parent.mkdir(exist_ok=True)
    dest.write_text("\n".join(out) + "\n")
    print("\n".join(out[-24:]))
    print(f"\n-> {dest}")


if __name__ == "__main__":
    main()
