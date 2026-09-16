"""marksample.py -- draw a stratified sample of MARKS for eye verdicts.

    python3 tools/marksample.py OUT [--per 8] [--seed 674] [--by score]

The marking policy (out/658) tests four things and the fit score is not
one of them, so 1,850 of 8,383 published marks sit below score 0.80 and
`formularesidual` only flags them POOR_FIT. To decide whether the score
belongs in the policy, the score has to be measured against verdicts --
which is what this samples for (out/675).

Marked rows from every placed `marks.json`, banded by `score`, sampled
with a fixed seed, at most two per document per band, each drawn on the
LOSSLESS cut of its host line. THE LABEL CARRIES THE ID AND THE READING,
NEVER THE SCORE: a verdict that can see the number it is testing is not
evidence. `key.json` holds the scores for the join afterwards.

Writes only into OUT; reads the library and ~/inkdrill-marks.
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import random
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.formulafind import frame_rect, page_frames  # noqa: E402

LIB = pathlib.Path.home() / "pdfdrill-library"
MARKS = pathlib.Path.home() / "inkdrill-marks"
BANDS = [(0.0, 0.50), (0.50, 0.60), (0.60, 0.70), (0.70, 0.80),
         (0.80, 0.90), (0.90, 1.01)]


def marked_rows():
    for m in sorted(MARKS.iterdir()):
        f = m / "marks.json"
        if not (m.is_dir() and f.exists()):
            continue
        for r in json.loads(f.read_text())["rows"]:
            if r["mark"] and r.get("score") is not None:
                yield m.name, r


def draw(doc, r, out):
    """The mark on its host line, at 400 dpi, labelled without the score."""
    frames, _ = page_frames(LIB, doc)
    fr = frames.get(r["host_page"])
    if not fr:
        return None
    x, y, w, h = frame_rect(r["region"], fr)
    x0, y0, x1, y1 = r["rect"]                   # MathPix px, region-relative
    sx = fr[0]
    img = out / f"{r['id']}.png"
    subprocess.run(["magick", str(LIB / doc / "inspect" / "pages" / f"p{r['host_page']}.png"),
                    "-crop", f"{w}x{h}+{x}+{y}", "+repage",
                    "-fill", "none", "-stroke", "red", "-strokewidth", "3",
                    "-draw", f"rectangle {x0*sx:.0f},{y0*sx:.0f} {x1*sx:.0f},{y1*sx:.0f}",
                    "-resize", "1100x>", "-background", "white", "-gravity", "north",
                    "-splice", "0x26", "-pointsize", "18", "-fill", "blue", "-stroke", "none",
                    "-annotate", "+0+2",
                    f"{r['id'].rsplit('_', 1)[-1]}:  {(r['math'] or '')[:85]}", str(img)],
                   check=True)
    return img


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=pathlib.Path)
    ap.add_argument("--per", type=int, default=8, help="rows per band")
    ap.add_argument("--seed", type=int, default=674)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    rows = list(marked_rows())
    print(f"marked rows with a score: {len(rows)}")
    rnd = random.Random(args.seed)
    key = {}
    for lo, hi in BANDS:
        pool = [x for x in rows if lo <= x[1]["score"] < hi]
        rnd.shuffle(pool)
        per_doc, imgs = collections.Counter(), []
        for doc, r in pool:
            if per_doc[doc] >= 2:
                continue
            per_doc[doc] += 1
            img = draw(doc, r, args.out)
            if img is None:
                continue
            imgs.append(str(img))
            key[r["id"]] = dict(score=r["score"], margin=r["margin"], gaps=r["gaps"],
                                band=f"{lo:.2f}-{hi:.2f}", doc=doc, math=r["math"])
            if len(imgs) >= args.per:
                break
        if imgs:
            subprocess.run(["magick", *imgs, "-append",
                            str(args.out / f"band_{lo:.2f}_{hi:.2f}.png")], check=True)
        print(f"  band {lo:.2f}-{hi:.2f}: population "
              f"{sum(1 for _, r in rows if lo <= r['score'] < hi):>5}, drawn {len(imgs)}")
    (args.out / "key.json").write_text(json.dumps(key, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
