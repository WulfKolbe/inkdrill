"""Measure the FINAL glyph of each candidate crop: holes and chi."""
import pathlib, subprocess, sys, tempfile, collections
sys.path.insert(0, "/home/wkolbe/inkdrill")
from inkdrill.pngio import read_png, auto_mask
from inkdrill.nest import ink_only
LIB = pathlib.Path.home()/"pdfdrill-library"
rows = [l.split("\t") for l in pathlib.Path(sys.argv[1]).read_text().splitlines() if l.strip()]
out = []
tmp = pathlib.Path(tempfile.mkdtemp())
for doc, ident, cls, tok in rows:
    jpg = LIB/doc/"report-crops"/f"{ident}.jpg"
    png = tmp/"c.png"
    r = subprocess.run(["magick", str(jpg), "-define", "png:color-type=2",
                        str(png)], capture_output=True)
    if r.returncode or not png.exists():
        out.append((doc, ident, cls, tok, "convert-failed", "", "", "")); continue
    img = read_png(png); m,_ = auto_mask(img.gray, img.width, img.height, 200)
    ip = ink_only(m); regs = list(ip.regions); cyc = list(ip.cycles)
    png.unlink()
    if not regs:
        out.append((doc, ident, cls, tok, "no-ink", "", "", "")); continue
    order = sorted(range(len(regs)), key=lambda i: regs[i].x0)
    # NO PUNCTUATION HEURISTIC. Two were tried -- component height
    # against the row MEDIAN, then against the TALLEST -- and each
    # fixed one class while breaking the other: the median let a 4x11
    # comma through on crops full of subscripts, the maximum skipped
    # the emptyset itself on crops carrying a tall delimiter. Choosing
    # between them by which answer came out better is tuning a
    # threshold to the result.
    #
    # The label names a RING, so look for a ring: the rightmost
    # component with at least one hole whose bbox aspect is between
    # 0.4 and 1.5. A comma has no hole. A tall delimiter is not
    # ring-shaped. Rows with no ring at all are EXCLUDED AND NAMED
    # rather than measured on whatever the rightmost component
    # happened to be.
    pick = None
    for i in reversed(order):
        r_ = regs[i]
        rw, rh = r_.x1-r_.x0+1, r_.y1-r_.y0+1
        if cyc[i] >= 1 and 0.4 <= rw/rh <= 1.5:
            pick = i; break
    if pick is None:
        out.append((doc, ident, cls, tok, "no-ring-shaped-component",
                    "", "", "")); continue
    r_ = regs[pick]
    out.append((doc, ident, cls, tok, "ok", str(cyc[pick]), str(1-cyc[pick]),
                f"{r_.x1-r_.x0+1}x{r_.y1-r_.y0+1}"))
p = pathlib.Path(sys.argv[2]); p.write_text("\n".join("\t".join(x) for x in out)+"\n")
c = collections.Counter()
for doc, ident, cls, tok, st, holes, chi, box in out:
    if st != "ok": c[f"{cls} {st}"] += 1; continue
    h = int(holes)
    if cls == "unslashed":
        c["unslashed, holes 2 -- CONTRADICTION" if h == 2 else
          f"unslashed, holes {h}"] += 1
    else:
        c["slashed, holes 1 -- CONTRADICTION" if h == 1 else
          f"slashed, holes {h}"] += 1
for k, v in sorted(c.items()): print(f"  {k:<44} {v}")
print("->", p)
