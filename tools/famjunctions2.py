"""495: does the family separation survive more fonts, and how
unstable is the HOLE count across all of them."""
import pathlib, sys, os, collections, json
sys.path.insert(0, "/home/wkolbe/inkdrill")
from inkdrill.type1 import load as t1_load
from inkdrill.charstring import outline as cs_outline
from inkdrill.scan import render as scan_render
from inkdrill.nest import ink_only
from inkdrill.skeleton import junction_sites, endpoints

TREE = pathlib.Path(os.environ.get("INKDRILL_TYPE1",
                                   "/usr/share/texmf-dist/fonts/type1"))
FONTS = [
    ("upright",  "CM",       "cmr10.pfb"),
    ("upright",  "LM",       "lmr10.pfb"),
    ("upright",  "TeXGyre",  "qplr.pfb"),
    ("italic",   "CM",       "cmmi10.pfb"),
    ("italic",   "LM",       "lmmi10.pfb"),
    ("italic",   "TeXGyre",  "qplri.pfb"),
    ("mathcal",  "CM",       "cmsy10.pfb"),
    ("mathcal",  "LM",       "lmsy10.pfb"),
    ("mathcal",  "txfonts",  "txsy.pfb"),
    ("mathscr",  "rsfs10",   "rsfs10.pfb"),
    ("mathscr",  "rsfs7",    "rsfs7.pfb"),
    ("mathfrak", "eufm10",   "eufm10.pfb"),
    ("mathfrak", "eufb10",   "eufb10.pfb"),
    ("mathbb",   "msbm10",   "msbm10.pfb"),
    ("mathbb",   "msbm7",    "msbm7.pfb"),
    ("mathbb",   "bbold10",  "bbold10.pfb"),
]
GLYPHS = ["L", "G", "J", "g"]
SIZES = [40, 80, 160]

rows = []
print(f"{'family':<9} {'font':<9} {'glyph':<5} " +
      "  ".join(f"{s}px J/H" for s in SIZES) + "   holes stable?")
for fam, tag, fn in FONTS:
    src = next(TREE.rglob(fn), None)
    if src is None:
        print(f"{fam:<9} {tag:<9} FONT NOT FOUND {fn}"); continue
    f = t1_load(src)
    for g in GLYPHS:
        if g not in f.charstrings:
            rows.append((fam, tag, g, None)); continue
        cells = []
        for px in SIZES:
            try:
                gl = cs_outline(f, g)
                if gl.is_empty: cells.append(None); continue
                m, _ = scan_render(gl, f.units_per_em, px)
                ip = ink_only(m)
                cells.append((junction_sites(m), sum(ip.cycles)))
            except Exception:
                cells.append(None)
        if any(c is None for c in cells): 
            rows.append((fam, tag, g, None)); continue
        hs = {c[1] for c in cells}
        js = {c[0] for c in cells}
        rows.append((fam, tag, g, cells))
        print(f"{fam:<9} {tag:<9} {g:<5} " +
              "  ".join(f"{c[0]}/{c[1]}   " for c in cells) +
              ("  yes" if len(hs) == 1 else f"  NO {sorted(hs)}") +
              ("" if len(js) == 1 else f"   J moves {sorted(js)}"))
json.dump([[a,b,c,d] for a,b,c,d in rows], open(sys.argv[1],"w"))

meas = [r for r in rows if r[3] is not None]
print(f"\nGLYPHS MEASURED {len(meas)} of {len(rows)}")
hb = [r for r in meas if len({c[1] for c in r[3]}) > 1]
jb = [r for r in meas if len({c[0] for c in r[3]}) > 1]
print(f"  HOLE count changes with size : {len(hb)} ({100*len(hb)/len(meas):.0f}%)")
print(f"  junction count changes       : {len(jb)} ({100*len(jb)/len(meas):.0f}%)")
for r in hb:
    print(f"     holes {sorted({c[1] for c in r[3]})}  {r[0]}/{r[1]} {r[2]}")
print("\nMATHCAL ACROSS FONTS")
for r in meas:
    if r[0] == "mathcal":
        print(f"   {r[1]:<9} {r[2]}  J {[c[0] for c in r[3]]}  H {[c[1] for c in r[3]]}")
print("MATHSCR ACROSS FONTS")
for r in meas:
    if r[0] == "mathscr":
        print(f"   {r[1]:<9} {r[2]}  J {[c[0] for c in r[3]]}  H {[c[1] for c in r[3]]}")
