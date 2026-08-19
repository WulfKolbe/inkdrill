"""Three-way structural comparison of one formula: standalone render,
report cell, scan crop.

WHICH PAIR ANSWERS WHAT (P17 — the contract, written before the first
run):

  standalone vs report-cell   isolates LAYOUT. Same LaTeX compiled
                              twice — alone and inside the report's
                              longtable cell — so any disagreement is
                              the report's own typesetting (line
                              width, breaking, cramped cells), never
                              the conversion.
  report-cell vs scan         THE FINDING. This is the pair the
                              compare loop already measures: MathPix's
                              rendered opinion against the original
                              ink.
  standalone vs scan          the TIEBREAK. Removes the report's own
                              rendering from the loop; consulted when
                              the first two disagree — if
                              standalone-vs-scan is small while
                              report-cell-vs-scan is large, the report
                              cell (not the conversion) is at fault,
                              and vice versa.

A missing standalone PNG is checked against standalone/_failures.txt
before scoring: absence there is a class-1 defect (the formula will
not compile alone), not a coverage gap.

Usage:
  python3 tools/threeway.py <doc-dir> [ident ...]
      <doc-dir> = a pdfdrill-library document folder holding
      standalone/<ident>.png and report.compare.tsv; report cells and
      scan crops are cut from the report render cached by the compare
      harness. Without idents, every row of report.compare.tsv runs.
Output: TSV to stdout — ident, the three five-tuples, and the three
pairwise L1 distances (d_layout, d_finding, d_tiebreak).
"""

import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from inkdrill.__main__ import _cell_crop, _table_cells  # noqa: E402
from inkdrill.mathstruct import pair_stats               # noqa: E402
from inkdrill.pngio import read_png, auto_mask           # noqa: E402

SCRATCH = pathlib.Path(
    "/tmp/claude-1000/-home-wkolbe-inkdrill/"
    "4c2bddec-f2e9-4179-ac4a-ae5869ace73a/scratchpad")

KEYS = ("components", "holes", "stacked", "centred", "offset")


def five(mask):
    st = pair_stats(mask)
    return tuple(st[k] for k in KEYS)


def load_any_png(path: pathlib.Path):
    """pngio reads only png16m; a gs grayscale PNG goes through magick."""
    try:
        img = read_png(path)
    except Exception:
        with tempfile.NamedTemporaryFile(suffix=".png") as t:
            subprocess.run(["magick", str(path), "-define",
                            "png:color-type=2", t.name], check=True)
            img = read_png(pathlib.Path(t.name))
    return auto_mask(img.gray, img.width, img.height, 200)[0]


def report_cells_for(doc: pathlib.Path):
    """ident -> (rendered mask, scan mask), cut from the cached report
    renders of the compare harness (300 dpi)."""
    name = doc.name
    cache = None
    for sub in ("p13cmp", "mpx"):
        c = SCRATCH / sub / name
        if c.is_dir() and list(c.glob("p*_r300.png")) + \
                list(c.glob("png300/p*.png")):
            cache = c
            break
    if cache is None:
        raise SystemExit(f"no cached report renders for {name} — run the "
                         f"compare harness first")
    pages = sorted(cache.glob("p*_r300.png")) or \
        sorted((cache / "png300").glob("p*.png"))
    out = {}
    k = 0
    idents = ident_order(doc)
    for pg in pages:
        img = read_png(pg)
        m = auto_mask(img.gray, img.width, img.height, 200)[0]
        cells = _table_cells(m, 4.0)
        if not cells:
            continue
        nr = max(r for r, _ in cells) + 1
        nc = max(c for _, c in cells) + 1
        if nc < 4:
            continue
        for r in range(1, nr):
            b = cells[(r, 0)]
            if b[3] - b[1] < 40:
                continue                       # sliver row
            if k >= len(idents):
                return out
            rend = cells[(r, nc - 2)]
            scan = cells[(r, nc - 1)]
            out[idents[k]] = (
                _cell_crop(m, rend[0], rend[1], rend[2] - 1, rend[3] - 1),
                _cell_crop(m, scan[0], scan[1], scan[2] - 1, scan[3] - 1))
            k += 1
    return out


def ident_order(doc: pathlib.Path):
    import re
    tex = (doc / "report.tex").read_text()
    return [m.group(1).replace("\\", "") for m in
            re.finditer(r"\\ident\{([^}]*EQ\d+)\}", tex)]


def main():
    doc = pathlib.Path(sys.argv[1])
    only = set(sys.argv[2:])
    cells = report_cells_for(doc)
    failures = set()
    ftxt = doc / "standalone" / "_failures.txt"
    if ftxt.exists():
        failures = {l.split(":")[0].strip()
                    for l in ftxt.read_text().splitlines() if l.strip()}
    print("ident\tstandalone\treport_cell\tscan\t"
          "d_layout\td_finding\td_tiebreak\tnote")
    for ident, (rend, scan) in cells.items():
        if only and ident not in only:
            continue
        png = doc / "standalone" / f"{ident}.png"
        note = ""
        sa = None
        if png.exists():
            sa = five(load_any_png(png))
        elif ident in failures or any(ident in f for f in failures):
            note = "class-1: will not compile alone"
        else:
            note = "standalone PNG missing, NOT in _failures.txt"
        rc, sc = five(rend), five(scan)
        d = lambda a, b: sum(abs(x - y) for x, y in zip(a, b))
        print("\t".join(map(str, [
            ident,
            "/".join(map(str, sa)) if sa else "-",
            "/".join(map(str, rc)), "/".join(map(str, sc)),
            d(sa, rc) if sa else "-",
            d(rc, sc),
            d(sa, sc) if sa else "-",
            note])))


if __name__ == "__main__":
    main()
