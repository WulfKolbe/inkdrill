"""491: junctions and holes per typeface family (not per negation)."""
import pathlib, sys, os, collections
sys.path.insert(0, "/home/wkolbe/inkdrill")
from inkdrill.type1 import load as t1_load
from inkdrill.charstring import outline as cs_outline
from inkdrill.scan import render as scan_render
from inkdrill.nest import ink_only
from inkdrill.skeleton import junction_sites, endpoints

TREE = pathlib.Path(os.environ.get("INKDRILL_TYPE1",
                                   "/usr/share/texmf-dist/fonts/type1"))
FAMILIES = [("upright",  "cmr10.pfb"),
            ("italic",   "cmmi10.pfb"),
            ("mathcal",  "cmsy10.pfb"),
            ("mathscr",  "rsfs10.pfb"),
            ("mathfrak", "eufm10.pfb"),
            ("mathbb",   "msbm10.pfb")]
GLYPHS = ["L", "G", "J", "g"]
SIZES = [40, 80, 160]

print(f"{'family':<9} {'glyph':<6} " + "  ".join(f"{s:>3}px J/H/E" for s in SIZES))
rows = []
for fam, fn in FAMILIES:
    src = next(TREE.rglob(fn), None)
    if src is None:
        print(f"{fam:<9} FONT NOT FOUND {fn}"); continue
    f = t1_load(src)
    for g in GLYPHS:
        if g not in f.charstrings:
            print(f"{fam:<9} {g:<6} absent from {fn}")
            rows.append((fam, g, None)); continue
        cells = []
        for px in SIZES:
            try:
                gl = cs_outline(f, g)
                if gl.is_empty: cells.append(None); continue
                m, _ = scan_render(gl, f.units_per_em, px)
            except Exception as e:
                cells.append(None); continue
            ip = ink_only(m)
            holes = sum(ip.cycles)
            j = junction_sites(m)
            e = endpoints(m)
            cells.append((j, holes, e))
        rows.append((fam, g, cells))
        print(f"{fam:<9} {g:<6} " + "  ".join(
            "   absent  " if c is None else f"  {c[0]}/{c[1]}/{c[2]:<2}   "
            for c in cells))
print()
print("J = junction sites, H = holes, E = skeleton endpoints")
