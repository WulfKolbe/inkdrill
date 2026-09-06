"""What a corpus directory actually holds, so a test drive can start.

Exists because the test-drive commands must not require anyone to
write Python at a prompt. `--library` defaults to the usual place and
is printed, so a wrong guess is visible rather than silent.
"""

from __future__ import annotations

import argparse
import json
import pathlib


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--library", type=pathlib.Path,
                    default=pathlib.Path.home() / "pdfdrill-library")
    ap.add_argument("--list", type=int, default=5,
                    help="how many document names to print per class")
    args = ap.parse_args()
    L = args.library
    print(f"library: {L}")
    if not L.is_dir():
        print("  DOES NOT EXIST -- pass --library <dir>")
        return 1
    docs = [d for d in sorted(L.iterdir()) if d.is_dir()]
    print(f"  {len(docs)} directories\n")

    def having(*files):
        return [d.name for d in docs if all((d / f).is_file() for f in files)]

    rows = [
        ("report.pdf", having("report.pdf")),
        ("+ report.tables.json  (section 2)",
         having("report.pdf", "report.tables.json")),
        ("+ pdfdrill-rows.json  (section 3)",
         having("report.pdf", "report.tables.json", "pdfdrill-rows.json")),
    ]
    for label, names in rows:
        print(f"  {len(names):5d}  {label}")
        for n in names[:args.list]:
            print(f"           {n}")
    crops = [d.name for d in docs
             if (d / "report-crops").is_dir()
             and any((d / "report-crops").glob("*.jpg"))]
    print(f"  {len(crops):5d}  + report-crops/*.jpg  (section 8)")
    for n in crops[:args.list]:
        print(f"           {n}")

    # the biggest listing, which is the interesting one for section 2
    best, bestn = None, 0
    for d in docs:
        f = d / "report.tables.json"
        if not (f.is_file() and (d / "report.pdf").is_file()):
            continue
        try:
            n = sum(t.get("rows", 0)
                    for t in json.loads(f.read_text()).get("tables", []))
        except Exception:
            continue
        if n > bestn:
            best, bestn = d.name, n
    if best:
        print(f"\n  largest listing: {bestn} rows in \"{best}\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
