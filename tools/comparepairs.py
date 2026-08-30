#!/usr/bin/env python3
"""382 — compare image PAIRS directly. No PDF, no page, no lattice, no table.

    python3 tools/comparepairs.py --manifest pairs.json [-o out.tsv] [--threshold N]

The manifest is a list of {"id", "image_a", "image_b"}; one row comes out per
pair — the structural five-tuple of each side, their L1 distance, the component
delta, and the class.

WHY THIS EXISTS. `compare` reads a rendered PDF page, finds the table lattice,
locates two cells per row and measures those. That is the right shape when the
two images only exist AS a printed table. It is pure overhead when the caller
already holds both images as files, which a generator always does: it rendered
them. Measured on pdfdrill's 100-row DaTikZ report, the lattice detection alone
costs 487 s for 34 pages — 14.3 s per page — before a single cell is compared,
and the whole path runs at about one page a minute.

The measurement itself is unchanged: `mathstruct.pair_stats`, the same
definition `compare` uses. Only the transport is removed.
"""
import argparse
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from inkdrill.pngio import read_png, auto_mask                # noqa: E402
from inkdrill.mathstruct import pair_stats                    # noqa: E402

KEYS = ("components", "holes", "stacked", "centred", "offset")
#: the same thresholds the consumer classifies with, kept here so a pair row
#: and a table row cannot be classified by two different rules.
NOISE_DISTANCE = 7
NOISE_COMP_DELTA = 2


def classify(distance: int, comp_delta: int) -> str:
    if distance == 0:
        return "clean"
    if comp_delta > NOISE_COMP_DELTA:
        return "component"
    if distance <= NOISE_DISTANCE:
        return "noise"
    return "weak"


def five(path: pathlib.Path, threshold: int) -> tuple:
    img = read_png(path)
    mask, _ = auto_mask(img.gray, img.width, img.height, threshold)
    st = pair_stats(mask)
    return tuple(int(st[k]) for k in KEYS)


def main() -> int:
    ap = argparse.ArgumentParser(prog="tools/comparepairs.py",
                                 description=__doc__.strip().splitlines()[0])
    ap.add_argument("--manifest", required=True, type=pathlib.Path)
    ap.add_argument("-o", "--out", type=pathlib.Path)
    ap.add_argument("--threshold", type=int, default=200)
    a = ap.parse_args()

    spec = json.loads(a.manifest.read_text(encoding="utf-8"))
    pairs = spec["pairs"] if isinstance(spec, dict) else spec
    base = a.manifest.parent

    head = (["id"] + ["A " + k for k in KEYS] + ["B " + k for k in KEYS]
            + ["distance", "comp_delta", "class", "note"])
    lines = ["\t".join(head)]
    t0, ok, bad = time.time(), 0, 0
    for p in pairs:
        pid = str(p.get("id", ""))
        ia, ib = base / p["image_a"], base / p["image_b"]
        note = ""
        if not ia.is_file() or not ib.is_file():
            # a missing side is NOT a distance of zero; it is an absence, and
            # the row says so rather than scoring clean.
            note = "missing " + ("A" if not ia.is_file() else "B")
            lines.append("\t".join([pid] + ["" ] * 12 + [note]))
            bad += 1
            continue
        try:
            A, B = five(ia, a.threshold), five(ib, a.threshold)
        except Exception as exc:                              # noqa: BLE001
            lines.append("\t".join([pid] + [""] * 12
                                   + ["unreadable: %s" % type(exc).__name__]))
            bad += 1
            continue
        d = sum(abs(x - y) for x, y in zip(A, B))
        cd = abs(A[0] - B[0])
        lines.append("\t".join([pid] + [str(x) for x in A] + [str(x) for x in B]
                               + [str(d), str(cd), classify(d, cd), note]))
        ok += 1
    el = time.time() - t0
    text = "\n".join(lines) + "\n"
    if a.out:
        a.out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    print("%d pairs in %.1fs = %.1f pairs/min (%d unmeasurable)"
          % (ok, el, 60.0 * ok / max(el, 1e-9), bad), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
