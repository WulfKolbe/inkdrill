"""What the identifier join costs against what it replaces.

TWO ROUTES TO THE SAME ANSWER -- which pages of a report carry table
rows, and which rows are on them.

  PROBE      `pagedetect.scan_columns` renders EVERY page at 150 dpi
             and builds a lattice on each to count its columns;
             `group_tables` then groups them into runs and an ordinal
             picks the table. This is what `reportcompare` does and
             what needed a cache to be bearable.
  JOIN       `rowjoin.join` reads the report's text layer once and the
             table manifest, and returns every row's page directly.

Both are timed on the same document in the same run, so the ratio is
not a comparison between two machines or two days. The row-level
result is printed beside the time, because a route that is fast and
finds fewer rows is not faster at the same job.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from inkdrill.rowjoin import join                            # noqa: E402
from pagedetect import group_tables, npages, scan_columns    # noqa: E402


def page_text(pdf: pathlib.Path) -> list:
    r = subprocess.run(["pdftotext", "-raw", str(pdf), "-"],
                       capture_output=True, text=True, timeout=900)
    return r.stdout.split("\f")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("docs", nargs="+")
    ap.add_argument("--library", type=pathlib.Path,
                    default=pathlib.Path.home() / "pdfdrill-library")
    ap.add_argument("--dpi", type=int, default=150,
                    help="the probe's dpi; reportcompare uses 150")
    args = ap.parse_args()
    print(f"{'document':<34} {'pp':>4} | {'probe s':>8} {'join s':>7} "
          f"{'x':>6} | {'rows':>6} {'found':>6}")
    tp = tj = 0.0
    for name in args.docs:
        d = args.library / name
        pdf = d / "report.pdf"
        man_f = d / "report.tables.json"
        if not (pdf.is_file() and man_f.is_file()):
            print(f"{name[:34]:<34}  missing report.pdf or "
                  f"report.tables.json")
            continue
        n = npages(pdf)

        t0 = time.perf_counter()
        runs = group_tables(scan_columns(pdf, n, dpi=args.dpi))
        t_probe = time.perf_counter() - t0

        man = json.loads(man_f.read_text())
        t0 = time.perf_counter()
        try:
            jn = join(man, page_text(pdf))
        except ValueError as e:
            # `join` refuses a manifest with no identifiers, which is a
            # real state: a corrections report lists tables whose rows
            # are captions rather than objects. Reported, not crashed.
            print(f"{name[:34]:<34} {n:>4} | {t_probe:>8.2f} "
                  f"{'-':>7} {'-':>6} | REFUSED: {e}")
            continue
        t_join = time.perf_counter() - t0

        rows = len(jn.rows)
        found = sum(1 for r in jn.rows if r.page is not None)
        tp += t_probe
        tj += t_join
        print(f"{name[:34]:<34} {n:>4} | {t_probe:>8.2f} {t_join:>7.2f} "
              f"{t_probe / max(t_join, 1e-9):>5.1f}x | {rows:>6} {found:>6}"
              f"   {len(runs)} runs")
    if tj > 0:
        print(f"\n  totals: probe {tp:.2f}s, join {tj:.2f}s, "
              f"{tp / tj:.1f}x")
        print("  The probe answers a DIFFERENT question -- which pages "
              "have a lattice of\n  N columns -- and 595 measured that "
              "answer wrong: a run can hold two\n  tables and a table "
              "can span several runs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
