"""Check MathPix lines.json geometry against real ink (coverage.check),
documents processed oldest-lines.json-first.

Usage: python3 tools/mathpixcoverage.py [worker] [nworkers] [library]
  Shard `worker` of `nworkers` (default 0 of 1) over <library>/*/*.lines.json;
  run N copies in parallel with worker=0..N-1. Resumable: a document whose
  .coverage.tsv is newer than its lines.json is skipped.

Per page: components (>= 4 px, speck floor) classified against the
document's MathPix regions scaled from MathPix raster coordinates
(page_width/page_height) into our 200 dpi render. Output one TSV per
document: page, components, regions, and the five coverage classes --
the residual (MISSED ink) is the product.
"""
import ast, json, pathlib, subprocess, sys
# library filenames can carry lone surrogates (undecodable bytes); an
# encode error inside the FAILURE print killed all six workers of the
# first full run -- make stdout unable to raise
sys.stdout.reconfigure(errors="backslashreplace")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from inkdrill.aggregate import moments_per_component
from inkdrill.coverage import Box, CoverageClass, Region, check
from inkdrill.pnmio import read_pnm_stream
from inkdrill.pngio import auto_mask
from inkdrill.sweep import Capture, sweep

W = int(sys.argv[1]) if len(sys.argv) > 1 else 0
K = int(sys.argv[2]) if len(sys.argv) > 2 else 1
LIB = pathlib.Path(sys.argv[3] if len(sys.argv) > 3
                   else "~/pdfdrill-library").expanduser()
docs = sorted(LIB.glob("*/*.lines.json"),
              key=lambda f: f.stat().st_mtime)[W::K]

for lj in docs:
    done = lj.parent / (lj.name[:-len(".lines.json")] + ".coverage.tsv")
    if done.exists() and done.stat().st_mtime > lj.stat().st_mtime:
        continue
    try:
        d = lj.parent; name = lj.name[:-len(".lines.json")]
        pdf = d / (name + ".pdf")
        if not pdf.exists():
            pdf = next((p for p in d.glob("*.pdf")
                        if p.name != "report.pdf"), None)
        if pdf is None:
            print(f"{name}: no source pdf, skipped", flush=True); continue
        data = json.loads(lj.read_text())
        pages = {p["page"]: p for p in data["pages"]}
        npg = max(pages)
        out = ["page\tcomponents\tregions\tinside\tmissed\tstraddle"
               "\toverlapping\tempty_regions\tmissed_px"]
        tot = {k: 0 for k in CoverageClass}; totc = totr = 0
        for lo in range(1, npg + 1, 10):
            hi = min(lo + 9, npg)
            gs = subprocess.run(
                ["gs","-q","-dNOPAUSE","-dBATCH","-sDEVICE=pgmraw","-r200",
                 f"-dFirstPage={lo}",f"-dLastPage={hi}",
                 "-sOutputFile=%stdout",str(pdf)],
                capture_output=True, check=True).stdout
            for i, img in enumerate(read_pnm_stream(gs, dpi=(200.0,200.0))):
                pg = lo + i
                meta = pages.get(pg)
                if meta is None: continue
                mask,_ = auto_mask(img.gray, img.width, img.height, 200)
                res = sweep(mask, axis="row", conn=8, capture=Capture.GRAPH)
                moms = moments_per_component(res)
                boxes = [Box(c.root, moms[c.root].x0, moms[c.root].y0,
                             moms[c.root].x1, moms[c.root].y1,
                             moms[c.root].area)
                         for c in res.components]
                sx = mask.width / meta["page_width"]
                sy = mask.height / meta["page_height"]
                regs = []
                for j, ln in enumerate(meta.get("lines", [])):
                    r = ln.get("region")
                    if isinstance(r, str): r = ast.literal_eval(r)
                    if not r: continue
                    regs.append(Region(j, r["top_left_x"] * sx,
                                       r["top_left_y"] * sy,
                                       (r["top_left_x"] + r["width"]) * sx,
                                       (r["top_left_y"] + r["height"]) * sy,
                                       ln.get("type", "")))
                rep = check(boxes, regs, min_pixels=4)
                missed = rep.members(CoverageClass.MISSED)
                mpx = sum(moms[b].area for b in missed if b in moms)
                row = [pg, rep.box_count, rep.region_count] + \
                      [rep.count(k) for k in CoverageClass] + [mpx]
                out.append("\t".join(map(str, row)))
                for k in CoverageClass: tot[k] += rep.count(k)
                totc += rep.box_count; totr += rep.region_count
        (d / (name + ".coverage.tsv")).write_text("\n".join(out) + "\n")
        cb = sum(v for k, v in tot.items() if k != CoverageClass.EMPTY_REGION)
        print(f"{name}: {npg} pages, comps {totc}, regions {totr}, "
              f"missed {tot[CoverageClass.MISSED]} "
              f"({100*tot[CoverageClass.MISSED]/max(1,cb):.1f}% of ink), "
              f"empty regions {tot[CoverageClass.EMPTY_REGION]}", flush=True)
    except Exception as e:
        print(f"{lj.parent.name}: FAILED {type(e).__name__}: {e}", flush=True)
print(f"WORKER {W} DONE", flush=True)
