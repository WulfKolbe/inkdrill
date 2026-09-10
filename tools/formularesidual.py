"""formularesidual.py -- which rows of an evidence table are WRONG.

Consumes `formulafind.py --json`. It answers a different question from
that tool, and the difference is the whole design:

    formulafind    where is this expression in its line?
    formularesidual  which rows have EVIDENCE that something is wrong?

NOT PLACING A ROW IS NOT EVIDENCE OF ANYTHING. 49 of the first 200 rows
measured carry one gap or none -- `G`, `w`, `\\mathfrak{D}^{\\prime}` --
and an expression that short has no position to find. Marking those red
would report the instrument's blind spot as the document's error, which
is the failure CLAUDE.md records under "a filter that excludes the
class it exists to compare against". They get their own colour and
their own name, and they never enter the residual report.

A RED FLAG IS A CONTRADICTION BETWEEN TWO COMPUTATIONS THAT DO NOT
SHARE CODE. Every rule below is of that form, and every threshold is
calibrated from the rows that agree rather than chosen:

  R1 EDGE CUT     the rectangle's boundary falls INSIDE a blob. A
                  placement that is right ends in a gap, because that
                  is what a gap is. An edge through a glyph means the
                  expression is truncated or misplaced.
  R2 BLOB COUNT   the rendered LaTeX has a different number of
                  components from the ink it was placed on. This is
                  the one that accuses the SOURCE rather than the
                  placement: a missing subscript, a swallowed operator.
  R3 POOR FIT     the position is established -- a high margin, so
                  the expression fits HERE and nowhere else -- and yet
                  the shape agrees badly. Two computations
                  contradicting each other: where it is, versus what
                  it looks like.

                  THIS RULE REPLACED AN EARLIER ONE and the earlier
                  one is worth recording. It compared each row's own
                  best-fit scale against the document's, reasoning
                  that a different length accuses the LaTeX. It fired
                  on 9 rows, and all 9 were artefacts of the search:
                  the own-scale distribution is bimodal, 85 of 97
                  reference rows at 0.24-0.27 and 10 collapsed onto
                  0.10, the FLOOR of the scale range. `FO0036` scored
                  a perfect 1.000 there -- the same degeneracy as `G`,
                  a template shrunk until it fits anywhere. The rule
                  was measuring the instrument.
  R4 OVERLAP      two expressions on ONE line placed on overlapping x.
                  Impossible; one of them is wrong.
  R5 ORDER        two expressions on one line placed out of reading
                  order. Also impossible.

R4 and R5 need no external data at all: crops shared by several rows
are byte-identical, so grouping by content hash recovers the line.

THE MOST INTERESTING ROW IS A RED FLAG BESIDE A GREEN CONFIDENCE.
Column 3 already carries the other tool's own opinion. Where that says
1.000 and this says CONTRADICTED, the disagreement is the finding --
which is the point of the package, and the reason the flag is reported
next to that cell rather than replacing it.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pathlib
import statistics

GREY = ("UNPLACEABLE", "AMBIGUOUS")
RED = ("EDGE_CUT", "BLOB_COUNT", "POOR_FIT", "OVERLAP", "ORDER")


def calibrate(rows, min_margin):
    """Thresholds from the rows that AGREE, never chosen by hand.

    The reference population is the confidently placed rows: enough
    gaps to carry a position, and a margin over every non-overlapping
    alternative. Whatever those rows do is normal by definition, and a
    rule is what they do not do. The 90th percentile is the cut, so
    roughly a tenth of the reference population would flag itself --
    which is stated rather than hidden, because a rule that fires on
    nothing it was calibrated against is a rule with no measured
    false-positive rate at all.
    """
    ref = [r for r in rows if r["gaps"] >= 2 and r["margin"] >= min_margin]
    if len(ref) < 8:
        return None, ref

    def p90(v):
        v = sorted(v)
        return v[min(len(v) - 1, int(0.90 * len(v)))]

    def p10(v):
        v = sorted(v)
        return v[min(len(v) - 1, int(0.10 * len(v)))]

    diffs = [abs(r["blobs_in_rect"] - r["formula_blobs"]) for r in ref]
    cuts = [r["edge_cuts"] for r in ref]
    scores = [r["score"] for r in ref]
    return dict(n_ref=len(ref),
                blob_diff_max=p90(diffs),
                edge_cut_max=p90(cuts),
                score_min=round(p10(scores), 4),
                blob_diff_spread=dict(sorted(collections.Counter(diffs).items())),
                edge_cut_spread=dict(sorted(collections.Counter(cuts).items()))), ref


def classify(rows, cal, min_margin):
    """One row -> its flags. Grey and red are kept apart."""
    by_crop = collections.defaultdict(list)
    for r in rows:
        # BY CONTENT, NOT PATH. Every row names its own crop file, but
        # rows on the SAME LINE are given byte-identical copies of it --
        # 86 of the first 400 crops are shared. Grouping by path found
        # 0 shared lines and silently disabled both line-level rules.
        by_crop[r.get("crop_hash") or r["crop"]].append(r)

    for r in rows:
        r["flags"] = []
        if r["gaps"] <= 1:
            r["flags"].append("UNPLACEABLE")
            continue                      # nothing else can be said
        if r["margin"] < min_margin:
            r["flags"].append("AMBIGUOUS")
            continue                      # the position is not established,
                                          # so no contradiction can rest on it
        if r["edge_cuts"] > cal["edge_cut_max"]:
            r["flags"].append("EDGE_CUT")
        if abs(r["blobs_in_rect"] - r["formula_blobs"]) > cal["blob_diff_max"]:
            r["flags"].append("BLOB_COUNT")
        if r["score"] < cal["score_min"]:
            r["flags"].append("POOR_FIT")

    # ---- the line-level rules. Crops shared by several rows are
    # byte-identical, so the crop path IS the line key.
    order_pairs = order_bad = 0
    for crop, group in by_crop.items():
        placed = [g for g in group
                  if not set(g["flags"]) & set(GREY)]
        placed.sort(key=lambda g: g["id"])
        for i in range(len(placed)):
            for j in range(i + 1, len(placed)):
                a, b = placed[i], placed[j]
                if a["rect"][0] <= b["rect"][2] and b["rect"][0] <= a["rect"][2]:
                    for x in (a, b):
                        if "OVERLAP" not in x["flags"]:
                            x["flags"].append("OVERLAP")
                order_pairs += 1
                if b["rect"][0] < a["rect"][0]:
                    order_bad += 1
                    for x in (a, b):
                        if "ORDER" not in x["flags"]:
                            x["flags"].append("ORDER")
    return by_crop, order_pairs, order_bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("json", type=pathlib.Path)
    ap.add_argument("--library", type=pathlib.Path,
                    default=pathlib.Path.home() / "pdfdrill-library")
    ap.add_argument("--bibkey", default="0902.0431")
    ap.add_argument("--min-margin", type=float, default=0.10)
    ap.add_argument("--out", type=pathlib.Path)
    ap.add_argument("--show", type=int, default=6)
    args = ap.parse_args()
    rows = json.loads(args.json.read_text())
    doc = args.library / args.bibkey
    for r in rows:
        f = doc / r["crop"]
        if f.exists():
            r["crop_hash"] = hashlib.md5(f.read_bytes()).hexdigest()
    print(f"{len(rows)} rows\n")

    cal, ref = calibrate(rows, args.min_margin)
    if cal is None:
        print(f"only {len(ref)} confidently placed rows; cannot calibrate")
        return 1
    print("CALIBRATION -- from the rows that agree, not chosen by hand")
    for k in ("n_ref", "blob_diff_max", "edge_cut_max", "score_min"):
        print(f"   {k:<16} {cal[k]}")
    print(f"   blob-diff spread in the reference set {cal['blob_diff_spread']}")
    print(f"   edge-cut spread in the reference set  {cal['edge_cut_spread']}")
    print()

    by_crop, order_pairs, order_bad = classify(rows, cal, args.min_margin)

    multi = sum(1 for g in by_crop.values() if len(g) > 1)
    print(f"LINES: {len(by_crop)} distinct crops, {multi} carry more than one "
          f"row, {order_pairs} placed pairs to compare")
    print(f"   reading-order premise: {order_pairs - order_bad} of "
          f"{order_pairs} pairs have x order matching id order")
    print()

    counts = collections.Counter()
    for r in rows:
        for f in r["flags"] or ["SILENT"]:
            counts[f] += 1
    print(f"{'class':<14} {'rows':>5}   what it means")
    meaning = {
        "SILENT": "placed and everything agrees",
        "UNPLACEABLE": "GREY -- too short to carry a position",
        "AMBIGUOUS": "GREY -- the line repeats; position not established",
        "EDGE_CUT": "RED -- a rectangle edge falls inside a glyph",
        "BLOB_COUNT": "RED -- rendered LaTeX has a different glyph count",
        "POOR_FIT": "RED -- placed uniquely, but the shape disagrees",
        "OVERLAP": "RED -- two expressions placed on the same ink",
        "ORDER": "RED -- two expressions placed out of reading order",
    }
    for k in ("SILENT",) + GREY + RED:
        print(f"{k:<14} {counts[k]:>5}   {meaning[k]}")
    red = [r for r in rows if set(r["flags"]) & set(RED)]
    grey = [r for r in rows if set(r["flags"]) & set(GREY)]
    print(f"\nRED {len(red)} of {len(rows)} ({100*len(red)/len(rows):.1f}%) "
          f"-- these are the residual report")
    print(f"GREY {len(grey)} ({100*len(grey)/len(rows):.1f}%) "
          f"-- reported as not examined, never as wrong")

    hi = [r for r in red if r["conf"] >= 0.99]
    print(f"\n{len(hi)} of the {len(red)} red rows carry a source confidence "
          f">= 0.99. THAT DISAGREEMENT IS THE PRODUCT.")
    for r in sorted(red, key=lambda r: -r["conf"])[:args.show]:
        print(f"   {r['id'].split('_')[-1]:<8} conf={r['conf']:.3f} "
              f"{'+'.join(r['flags']):<22} blobs {r['formula_blobs']}->"
              f"{r['blobs_in_rect']} score {r['score']:.2f} margin {r['margin']:.2f}"
              f" {r['math'][:34]}")
    if args.out:
        args.out.write_text(json.dumps(rows, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
