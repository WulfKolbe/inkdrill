"""A/B per-cell diff of two builds of the SAME report.

The decisive check for a change that is supposed to leave the ink
alone: render both builds at the same dpi, extract every lattice
cell of the last two columns, and diff the five-tuples cell by cell.
A change that moves a character outside a math box must produce
IDENTICAL ink; anything else is the change doing more than it said.

Reports the count of differing cells and names them, because "3 of
1,610 differ" and "0 differ" are different findings and an aggregate
would hide which.

Usage: python3 tools/abdiff.py <PRE.pdf> <POST.pdf> [--dpi 300]
       [--pages N] [--out out/xxx.txt]
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from inkdrill.__main__ import _cell_crop, _table_cells      # noqa: E402
from inkdrill.mathstruct import pair_stats                  # noqa: E402
from inkdrill.pnmio import read_pnm_stream                  # noqa: E402
from inkdrill.pngio import auto_mask                        # noqa: E402

KEYS = ("components", "holes", "stacked", "centred", "offset")


def cells_of(pdf, lo, hi, dpi):
    """{(page, row, col): five-tuple} for the last two columns."""
    gs = subprocess.run(
        ["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=pgmraw", f"-r{dpi}",
         f"-dFirstPage={lo}", f"-dLastPage={hi}", "-sOutputFile=%stdout",
         str(pdf)], capture_output=True, check=True).stdout
    out = {}
    for i, img in enumerate(read_pnm_stream(gs, dpi=(float(dpi),) * 2)):
        page = lo + i
        m, _ = auto_mask(img.gray, img.width, img.height, 200)
        cells = _table_cells(m, 6.0)
        if not cells:
            continue
        nr = max(r for r, _ in cells) + 1
        nc = max(c for _, c in cells) + 1
        for r in range(1, nr):
            b0 = cells[(r, 0)]
            if b0[3] - b0[1] < 40:
                continue
            for col in (nc - 2, nc - 1):
                b = cells[(r, col)]
                st = pair_stats(_cell_crop(m, b[0], b[1], b[2] - 1,
                                           b[3] - 1))
                out.setdefault(page, []).append(
                    ("rendered" if col == nc - 2 else "scan",
                     tuple(st[k] for k in KEYS)))
    return out


def main():
    pre, post = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    dpi = int(sys.argv[sys.argv.index("--dpi") + 1]) \
        if "--dpi" in sys.argv else 300
    import re
    n = int(re.search(r"^Pages:\s+(\d+)",
                      subprocess.run(["pdfinfo", str(pre)],
                                     capture_output=True, text=True).stdout,
                      re.M).group(1))
    if "--pages" in sys.argv:
        n = min(n, int(sys.argv[sys.argv.index("--pages") + 1]))
    a, b = {}, {}
    for lo in range(1, n + 1, 10):
        hi = min(lo + 9, n)
        a.update(cells_of(pre, lo, hi, dpi))
        b.update(cells_of(post, lo, hi, dpi))
        print(f"pages {lo}..{hi}: {sum(len(v) for v in a.values())} "
              f"cells measured", flush=True)

    # Rows are keyed by their POSITION IN THE DOCUMENT, not by
    # (page, row). A change that moves a row across a page boundary
    # shifts every later row index, and a positional key then reports
    # every one of them as a differing cell -- 143 of them on
    # 0902.0431, all of which were row N of one build against row N+1
    # of the other. Reflow is not an ink change and must not read as
    # one.
    def flat(d):
        out = []
        for page in sorted(d):
            out.extend(d[page])
        return out

    fa, fb = flat(a), flat(b)
    keys = list(range(min(len(fa), len(fb))))
    diff = [k for k in keys if fa[k] != fb[k]]
    only = list(range(len(keys), max(len(fa), len(fb))))
    a = {k: fa[k][1] for k in keys}
    b = {k: fb[k][1] for k in keys}
    kind = {k: fa[k][0] for k in keys}
    lines = [f"A/B per-cell diff at {dpi} dpi",
             f"  PRE  {pre}",
             f"  POST {post}",
             f"cells compared: {len(keys)}  "
             f"(cells present in only one build: {len(only)})",
             f"cells DIFFERING: {len(diff)}"]
    for k in diff[:40]:
        lines.append(f"  cell #{k} ({kind[k]}): "
                     f"{'/'.join(map(str, a[k]))} -> "
                     f"{'/'.join(map(str, b[k]))}")
    if only:
        lines.append(f"  one-sided cells: {only[:20]}")
    text = "\n".join(lines)
    print(text)
    if "--out" in sys.argv:
        p = pathlib.Path(sys.argv[sys.argv.index("--out") + 1])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text + "\n")
        print(f"-> {p}")


if __name__ == "__main__":
    main()
