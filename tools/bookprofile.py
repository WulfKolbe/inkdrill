"""Per-page structural profile of a scanned book, one TSV row per page.

Population: every page, rendered at 200 dpi via ghostscript pgmraw
streaming. Polarity is the committed conjunction rule (fraction gate
AND more-components-when-flipped); all numbers are measured on the
mask that rule selects.
"""
import pathlib, statistics, subprocess, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from inkdrill.aggregate import moments_per_component
from inkdrill.pnmio import read_pnm_stream
from inkdrill.pngio import auto_mask
from inkdrill.raster import stroke_mode
from inkdrill.sweep import Capture, sweep

DPI = 200
CHUNK = 20

def profile(pdf: pathlib.Path, out: pathlib.Path, npages: int):
    rows = []
    for lo in range(1, npages + 1, CHUNK):
        hi = min(lo + CHUNK - 1, npages)
        gs = subprocess.run(
            ["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=pgmraw",
             f"-r{DPI}", f"-dFirstPage={lo}", f"-dLastPage={hi}",
             "-sOutputFile=%stdout", str(pdf)],
            capture_output=True, check=True).stdout
        for i, img in enumerate(read_pnm_stream(gs, dpi=(DPI, DPI))):
            page = lo + i
            mask, flipped = auto_mask(img.gray, img.width, img.height, 200)
            res = sweep(mask, axis="row", conn=8, capture=Capture.GRAPH)
            ink = mask.ink_count
            runs = res.node_count
            moms = moments_per_component(res)
            heights = [m.height for m in moms.values()]
            rm, _ = stroke_mode(mask, "row")
            cm, _ = stroke_mode(mask, "col")
            rows.append((page, mask.width, mask.height,
                         round(100 * ink / (mask.width * mask.height), 2),
                         int(flipped), res.component_count,
                         res.cycle_count, runs,
                         round(ink / runs, 2) if runs else 0,
                         round(statistics.median(heights), 1)
                         if heights else 0, rm, cm))
        print(f"{pdf.stem}: {hi}/{npages}", flush=True)
    hdr = ("page\twidth\theight\tink_pct\tflipped\tcomponents\tholes"
           "\truns\tpx_per_run\tmed_comp_h\trow_mode\tcol_mode\n")
    out.write_text(hdr + "\n".join("\t".join(map(str, r))
                                   for r in rows) + "\n")
    print(f"WROTE {out}", flush=True)

def _npages(pdf):
    out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True,
                         text=True).stdout
    import re
    return int(re.search(r"^Pages:\s+(\d+)", out, re.M).group(1))


if __name__ == "__main__":
    import argparse
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import corpusgate
    ap = argparse.ArgumentParser(
        prog="tools/bookprofile.py",
        description=__doc__.strip().splitlines()[0])
    ap.add_argument("pdf", nargs="+")
    corpusgate.add_arguments(ap)
    args = ap.parse_args()
    chosen = corpusgate.gate("bookprofile", args.pdf, args.limit, args.yes,
                             count_pages=lambda a: _npages(pathlib.Path(a)))
    for arg in chosen:
        p = pathlib.Path(arg)
        profile(p, p.parent / (p.stem + ".profile.tsv"), _npages(p))
    print("ALL DONE", flush=True)
