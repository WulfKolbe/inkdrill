"""Does a PER-ROW scale refit recover the misplaced rectangles?

out/639 named this as the obvious next measurement and did not run it:
one scale is estimated per document and imposed on every row, so any
residual error accumulates along a long expression. The eye review of
out/643 says exactly that -- FO0150's rect misses `11` on the left and
`)` on the right, FO0200 misses the final Fraktur C, FO0237 sits
several characters left of its expression.

Search is CONSTRAINED to +/-12% around the document scale. A free
search is what collapsed to the floor of its range in out/640, and the
tell of that failure is a refined scale sitting ON the boundary -- so
the boundary hits are counted and reported.
"""
import json, os, pathlib, subprocess, sys
sys.path.insert(0, "/home/wkolbe/inkdrill")
from tools.formulafind import (blobs, fullres_crop, line_index, locate_at,
                               match_rows_to_lines, profile, render, rows,
                               scan, trimmed, vertical)

LIB = pathlib.Path.home()/"pdfdrill-library"; BIB = "0902.0431"
DOC_SCALE = 0.665; DPI = 600; CROP_DPI = 400.0
MAN = json.load(open(LIB/BIB/"inkdrill-residuals/manifest.json"))
index, raster_w, _ = line_index(LIB, BIB)
pw = int(subprocess.run(["magick","identify","-format","%w",
      str(LIB/BIB/"inspect/pages/p1.png")],capture_output=True,text=True).stdout)
ratio = pw/raster_w
allrows = {r["id"]: r for r in rows(LIB/BIB/"evidence-formula.tex")}
want = [f"{BIB}_{m['id']}" for m in MAN]
regs = match_rows_to_lines([allrows[i] for i in want], index)

LO, HI, STEP = 0.88, 1.12, 0.002
band = [DOC_SCALE*(LO + i*STEP) for i in range(int((HI-LO)/STEP)+1)]

print(f"{'id':<8} {'flags':<20} {'blobs':>10} {'score':>6} -> "
      f"{'blobs':>10} {'score':>6} {'scale':>7} {'dx0':>6} {'dx1':>6}")
import tempfile
fixed = same = boundary = 0
with tempfile.TemporaryDirectory() as td:
    t = pathlib.Path(td)
    for m in MAN:
        rid = f"{BIB}_{m['id']}"
        fullres_crop(LIB, BIB, int(m["page"]), regs[rid], ratio, t/"c.pgm")
        if not render(m["math"], t/"f.pgm", DPI):
            continue
        fm, fb = blobs(t/"f.pgm", float(DPI))
        cm, cb = blobs(t/"c.pgm", CROP_DPI)
        fp, cp = trimmed(fb, fm.width), profile(cb, cm.width)
        best = (0.0, None, None, None)
        for s in band:
            n, sc = scan(fp, cp, s)
            if not sc: continue
            i = max(range(len(sc)), key=sc.__getitem__)
            if sc[i] > best[0]:
                best = (sc[i], s, i, i+n-1)
        sc2, s2, x0, x1 = best
        _, _, nin2 = vertical(cb, x0, x1)
        on_edge = abs(s2/DOC_SCALE - LO) < 1e-9 or abs(s2/DOC_SCALE - HI) < 1e-9
        boundary += on_edge
        ok = (nin2 == m["fb"]) and (m["cb"] != m["fb"])
        fixed += ok
        same += (x0 == m["rect"][0] and x1 == m["rect"][2])
        print(f"{m['id']:<8} {'+'.join(m['flags']):<20} "
              f"{f'{m[chr(102)+chr(98)]}->{m[chr(99)+chr(98)]}':>10} {m['score']:>6.3f} -> "
              f"{f'{m[chr(102)+chr(98)]}->{nin2}':>10} {sc2:>6.3f} "
              f"{s2/DOC_SCALE:>7.3f} {x0-m['rect'][0]:>+6} {x1-m['rect'][2]:>+6}"
              f"{'  <- blob count now exact' if ok else ''}"
              f"{'  [ON BOUNDARY]' if on_edge else ''}")
print(f"\n{fixed} rows whose blob count becomes exact; {same} rects unchanged; "
      f"{boundary} refined scales sit ON the search boundary")
