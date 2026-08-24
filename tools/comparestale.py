"""Which report.compare.tsv files no longer describe the pdf beside
them.

`report_page` and `line` are indices into a specific BUILD of
report.pdf. Rebuild the pdf -- add a legend row, change a column --
and those indices stay in range and stay plausible while pointing at
the wrong rows. Nothing inside the file can reveal it: no value is out
of range, nothing is missing, and it is quietly wrong.

That is the third face of the empty-row defect. The first was a crash
(ValueError on an empty lattice), the second a false CLEAN
(zero-vs-zero scoring perfectly), and this one is neither: a stale
positional field that survives a recompile.

`reportcompare.py` now writes `report.compare.source` beside each tsv,
recording the pdf's mtime and size at measurement time. This tool
reports every document where the pdf has moved since. Documents with
no sidecar were measured before the stamp existed and are reported
SEPARATELY -- "unknown" is not "fresh", and merging the two would be
the same mistake in miniature.

Usage: python3 tools/comparestale.py [--library DIR] [--list]
"""
import argparse, pathlib, sys

ap = argparse.ArgumentParser(prog="tools/comparestale.py",
                             description=__doc__.strip().splitlines()[0])
ap.add_argument("--library", default="~/pdfdrill-library")
ap.add_argument("--list", action="store_true",
                help="name every document, not just the counts")
A = ap.parse_args()
LIB = pathlib.Path(A.library).expanduser()

fresh, stale, unknown, orphan = [], [], [], []
for tsv in sorted(LIB.glob("*/report.compare.tsv")):
    d = tsv.parent
    pdf = d / "report.pdf"
    if not pdf.is_file():
        orphan.append(d.name)
        continue
    src = d / "report.compare.source"
    if not src.is_file():
        unknown.append(d.name)
        continue
    rec = dict(l.split("\t", 1) for l in src.read_text().splitlines()
               if "\t" in l)
    st = pdf.stat()
    if (str(int(st.st_mtime)) == rec.get("mtime")
            and str(st.st_size) == rec.get("size")):
        fresh.append(d.name)
    else:
        stale.append(d.name)

print(f"{LIB}")
print(f"  fresh    {len(fresh):5d}  the stamped pdf is the pdf on disk")
print(f"  STALE    {len(stale):5d}  the pdf changed since measurement; "
      f"report_page and line index a build that no longer exists")
print(f"  unknown  {len(unknown):5d}  measured before the stamp existed "
      f"-- NOT the same as fresh")
print(f"  orphan   {len(orphan):5d}  a compare tsv with no report.pdf "
      f"beside it")
if A.list:
    for name, group in (("STALE", stale), ("unknown", unknown),
                        ("orphan", orphan)):
        for n in group:
            print(f"  {name}\t{n}")
sys.exit(1 if stale else 0)
