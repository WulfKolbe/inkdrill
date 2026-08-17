"""rowmodes.py -- col_mode/row_mode per text row over a PDF deck (T17).

    python3 tools/rowmodes.py <deck.pdf> [dpi]

Per polarity-corrected page, per text row surviving the T15 floor
(>= 6 glyphs, median glyph height >= 45 px, row-mode stem >= 5 px):
the ratio of the column-axis run-length mode to the row-axis one.
Anchors, measured on pure faces at the same procedure: Termes (serif)
0.38, Heros (sans) 0.88 -- a clean gap. The question the histogram
answers is whether a real corpus's rows respect that gap.

On the Ultimate-Guide-Typography deck they do NOT: 138 surviving rows
form a continuum whose MODAL bin (0.6-0.8) sits inside the anchor
gap. A typography guide's display faces -- slabs, scripts,
intermediate-contrast display types -- fill the space between the
book-face classes. The ratio is a serif/sans detector for
conventional text faces and not for this corpus.
"""
import sys, pathlib, subprocess, collections
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from inkdrill.pnmio import read_pnm_stream
from inkdrill.raster import InkMask, binarize, looks_inverted, stroke_mode
from inkdrill.sweep import Capture, sweep
from inkdrill.nest import ink_only
from inkdrill.mathstruct import Glyph, rows
pdf=pathlib.Path(sys.argv[1])
DPI=int(sys.argv[2]) if len(sys.argv)>2 else 120
ratios=[]; rows_used=0; rows_skipped=0; pages_flipped=0
CHUNK = 25 if DPI <= 150 else 6      # a 300 dpi page is ~17 MB of gray
for lo in range(1, 201, CHUNK):
    hi=min(lo+CHUNK-1, 200)
    r=subprocess.run(["gs","-q","-dNOPAUSE","-dBATCH","-sDEVICE=pgmraw",
        f"-r{DPI}", f"-dFirstPage={lo}", f"-dLastPage={hi}",
        "-sOutputFile=%stdout", str(pdf)], capture_output=True)
    for img in read_pnm_stream(r.stdout, dpi=DPI):
        dark=binarize(img.gray, img.width, img.height, threshold=128)
        m=dark
        if looks_inverted(dark):
            light=binarize(img.gray, img.width, img.height,
                           threshold=128, ink_is_dark=False)
            nd=len(sweep(dark,conn=8,capture=Capture.NONE).components)
            nl=len(sweep(light,conn=8,capture=Capture.NONE).components)
            if nl>nd:
                m=light; pages_flipped+=1
        regs=ink_only(m).regions
        gl=[Glyph(x.id,float(x.x0),float(x.y0),float(x.x1),float(x.y1))
            for x in regs]
        by={g.id:g for g in gl}
        for row in rows(gl):
            mem=row.members
            hs=sorted(g.height for g in mem)
            med_h=hs[len(hs)//2] if hs else 0
            # T15 floor: stems >= 5px needs glyphs >= ~50px at 0.1 ratio
            if len(mem) < 6 or med_h < 45:
                rows_skipped+=1
                continue
            # pool run lengths over the row's glyph crops, both axes
            from inkdrill.raster import iter_runs
            cnt={"row":collections.Counter(), "col":collections.Counter()}
            for g in mem:
                x0,y0,x1,y1=int(g.x0),int(g.top),int(g.x1),int(g.bottom)
                w=x1-x0+1; h=y1-y0+1
                if w<=0 or h<=0: continue
                buf=bytearray(w*h)
                for j in range(h):
                    src=(y0+j)*m.width+x0
                    buf[j*w:(j+1)*w]=m.data[src:src+w]
                cm=InkMask(bytes(buf),w,h)
                for axis in ("row","col"):
                    for run in iter_runs(cm, axis):
                        cnt[axis][run.hi-run.lo+1]+=1
            if not cnt["row"] or not cnt["col"]:
                rows_skipped+=1; continue
            rm=min(cnt["row"], key=lambda k:(-cnt["row"][k],k))
            cm_=min(cnt["col"], key=lambda k:(-cnt["col"][k],k))
            if rm < 5:                       # below the stem floor
                rows_skipped+=1; continue
            ratios.append(cm_/rm)
            rows_used+=1
    print(f"pages {lo}-{hi} done: rows used {rows_used}, "
          f"skipped {rows_skipped}, flipped {pages_flipped}", flush=True)
ratios.sort()
n=len(ratios)
print(f"\nROWS: {n} used, {rows_skipped} skipped (short/small/sub-floor); "
      f"{pages_flipped} pages flipped")
hist=collections.Counter(min(int(x*5),15) for x in ratios)   # 0.2-wide bins
for b in range(0,16):
    lo_=b/5
    print(f"  {lo_:>4.1f}-{lo_+0.2:<4.1f}  {hist.get(b,0):>4}  "
          + "#"*hist.get(b,0))
if n:
    print(f"min {ratios[0]:.2f}  p25 {ratios[n//4]:.2f}  med {ratios[n//2]:.2f}"
          f"  p75 {ratios[3*n//4]:.2f}  max {ratios[-1]:.2f}")
