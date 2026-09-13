"""cropcheck.py -- does each PUBLISHED evidence crop show the line its row names?

A published formula crop is the picture a reader is shown as evidence.
This checks it against a second, independent cut of the same thing:
the row's own `lines.json` region, cut from the lossless 400 dpi page
render, resampled to the published crop's exact size, and correlated
with it pixel for pixel. A correct crop correlates near 1 despite JPEG
and resampling; a crop cut from somewhere else correlates near 0.

THE TWO POPULATIONS DO NOT SEPARATE CLEANLY ON EVERY BUILD. They did on
2026-09-11 (0902.0431: 3,101 rows at 0.7-1.0, 62 near 0, nothing
between). On the 09-12 rebuild they do not: print quality and the
per-document crop scale push correct rows down as far as 0.348, and
`WRONG` had to be re-placed by eye. Re-check the boundary whenever the
corpus is rebuilt -- see the note on `WRONG`.

SIZE IS NOT ENOUGH, which is why this compares CONTENT. FO0068 of
0902.0431 is the right rectangle cut from the wrong page: its published
crop has exactly the width the region predicts, 419 against 1118 x
0.3749, and shows a different line. A size check passes it; out/658's
"99.8% of published crops are a pure scale" was a size check and passed
it.

THE MAPPING IS PER PAGE AND PER AXIS, and knows the CropBox:
`formulafind.page_frames`. The first version of this tool used png
width / MathPix page width, one factor for x and y, and so reported
cardona and voloshin 100% wrong -- its own error, not pdfdrill's:
MathPix's page image is the CropBox and `inspect/pages` is the
MediaBox, and on those two books the CropBox is inset.

    python3 tools/cropcheck.py run  <bibkey> [--shard I/N] --out F.json
    python3 tools/cropcheck.py report F.json [F2.json ...]

Needs `magick`. Reads the library; writes only the --out file.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.formulafind import (frame_rect, host_regions,  # noqa: E402
                               page_frames, rows)

#: below this the published crop does not show its row's line.
#:
#: RECALIBRATED 2026-09-13 on pdfdrill's 09-12 rebuild (out/665), because
#: a threshold is a claim about a POPULATION and the population changed.
#: On the 09-11 build the two groups were separated by an empty interval
#: (highest wrong 0.262, lowest right 0.413) and 0.35 sat inside it. On
#: the rebuild that interval is full -- 599 rows lie between 0.30 and
#: 0.50 -- because the crops are now scaled per document (1.0, 0.85,
#: 0.6, 0.5, 0.42) and a heavily reduced, soft-printed crop correlates
#: low while showing exactly the right line.
#:
#: Placed by eye again on this build: 8 of 8 rows examined from 0.002 to
#: 0.299 are WRONG lines, 8 of 8 from 0.348 to 0.355 are RIGHT.
#:
#: THE POPULATIONS OVERLAP HERE, which they did not on 09-11. Of six
#: rows examined in 0.30-0.35, five are right (blurred, reduced crops of
#: the right expression) and ONE is wrong: johnston FO0086 at 0.304,
#: whose crop reads `e_2 \in R^7` where the host line reads `e_3 \in
#: R^7` -- the neighbouring row's expression. So no single threshold
#: separates the two classes on this build, and a count taken at any
#: cut is a FLOOR, not a total: wrong rows live above it. 0.30 sits
#: below every verified-right row (lowest 0.302) and above the highest
#: row verified wrong with a clear margin (0.299).
WRONG = 0.30


def _pgm(args):
    r = subprocess.run(["magick", *args, "-colorspace", "Gray", "-depth", "8",
                        "pgm:-"], capture_output=True, check=True).stdout
    p = r.split(b"\n", 3)
    w, h = map(int, p[1].split())
    return w, h, p[3][:w * h]


def _corr(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    s = sum((u - ma) * (v - mb) for u, v in zip(a, b))
    d = math.sqrt(sum((u - ma) ** 2 for u in a) * sum((v - mb) ** 2 for v in b))
    return s / d if d else 0.0


def check(library: pathlib.Path, bib: str, shard=0, nshards=1, every=1,
          rule="first"):
    doc = library / bib
    allr = list(rows(doc / "evidence-formula.tex"))[::every]
    per = (len(allr) + nshards - 1) // nshards
    mine = allr[shard * per:(shard + 1) * per]
    frames, refused = page_frames(library, bib)
    regs = host_regions(library, bib, mine, rule)
    out = []
    for r in mine:
        hit = regs.get(r["id"])
        # A row can have NEITHER a host line NOR a page column -- the row
        # column is `None` for a row the producer did not place. The first
        # version wrote `int(r["page"])` here and died on it, losing a whole
        # shard of mielke silently (out/665).
        page = hit[0] if hit else (int(r["page"]) if r["page"] else None)
        reg = hit[1] if hit else None
        rec = dict(id=r["id"], page=r["page"], host_page=page,
                   conf=float(r["conf"]) if r["conf"] is not None else None,
                   corr=None, why="")
        pub = doc / r["crop"] if r["crop"] else None
        png = doc / "inspect" / "pages" / f"p{page}.png" if page else None
        if page is None:
            rec["why"] = "no host line and no page column"
        elif pub is None or not pub.exists():
            rec["why"] = "no published crop"
        elif reg is None:
            rec["why"] = "no line match"
        elif page not in frames:
            rec["why"] = f"page refused: {refused.get(page, 'no frame')}"
        else:
            try:
                w, h, a = _pgm([str(pub)])
                x, y, cw, ch = frame_rect(reg, frames[page])
                _, _, b = _pgm([str(png), "-crop", f"{cw}x{ch}+{x}+{y}",
                                "+repage", "-resize", f"{w}x{h}!"])
                rec["corr"] = _corr(a, b)
            except Exception as e:                       # pragma: no cover
                rec["why"] = f"error {type(e).__name__}"
        out.append(rec)
    return out


def report(res):
    by = collections.defaultdict(list)
    for r in res:
        by[r["id"].rsplit("_", 1)[0]].append(r)
    print(f"{'document':<42} {'rows':>6} {'checked':>8} {'wrong':>6} {'%':>6}")
    tot = collections.Counter()
    for d in sorted(by):
        g = by[d]
        ok = [r for r in g if r["corr"] is not None]
        w = sum(1 for r in ok if r["corr"] < WRONG)
        tot.update(rows=len(g), ok=len(ok), w=w)
        print(f"{d[:42]:<42} {len(g):>6} {len(ok):>8} {w:>6} "
              f"{100 * w / max(1, len(ok)):>5.1f}%")
    print(f"{'TOTAL':<42} {tot['rows']:>6} {tot['ok']:>8} {tot['w']:>6} "
          f"{100 * tot['w'] / max(1, tot['ok']):>5.1f}%")


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("run")
    a.add_argument("bibkey")
    a.add_argument("--library", type=pathlib.Path,
                   default=pathlib.Path.home() / "pdfdrill-library")
    a.add_argument("--shard", default="0/1")
    a.add_argument("--host", choices=("first", "cursor"), default="first",
                   help="first: pdfdrill's CURRENT host rule -- is the published "
                        "crop the line pdfdrill would crop today?")
    a.add_argument("--every", type=int, default=1,
                   help="every K-th row -- a SAMPLE, say so beside the result")
    a.add_argument("--out", type=pathlib.Path, required=True)
    b = sub.add_parser("report")
    b.add_argument("files", nargs="+", type=pathlib.Path)
    args = ap.parse_args()
    if args.cmd == "run":
        i, n = (int(x) for x in args.shard.split("/"))
        args.out.write_text(json.dumps(check(args.library, args.bibkey, i, n, args.every, args.host)))
        return 0
    res = []
    for f in args.files:
        res += json.loads(f.read_text())
    report(res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
