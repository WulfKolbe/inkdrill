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
    # XITS is an OTF family; 495 could not read it because type1.py
    # reads Type 1 programs and this package has no CFF reader. This
    # entry is a FontForge conversion of XITS-Regular to .pfb, supplied
    # by hand, so the gap 495 recorded is now partly closed: the
    # conversion carries the text face (2,517 charstrings, no plane-1
    # math alphanumerics), so it tests the HOLE-STABILITY half and not
    # the mathcal/mathscr separation, which needs a script alphabet.
    ("upright",  "XITS",     "~/XITS/XITS-Regular.pfb"),
    # XITSMath-Bold carries 638 mathematical alphanumerics from
    # U+1D400 on, which is the SCRIPT alphabet XITS-Regular has none
    # of -- so this face, and only this face, tests the mathcal/mathscr
    # separation on a design with no TeX lineage. It carries the BOLD
    # variant of every alphabet and no regular one; stroke weight is
    # therefore a confound against the 10 pt faces above and cannot be
    # removed without the regular math face.
    #
    # Unicode has ONE script block. \mathcal and \mathscr are two
    # FONTS for the same codepoints, so this entry is named for the
    # block it reads, not for a TeX command.
    ("mathscr",  "XITSMath",  "~/XITS/XITSMath-Bold.pfb", 0x1D4D0),
    ("mathfrak", "XITSMath",  "~/XITS/XITSMath-Bold.pfb", 0x1D56C),
    ("mathbb",   "XITSMath",  "~/XITS/XITSMath-Bold.pfb", 0x1D538),
    ("italic",   "XITSMath",  "~/XITS/XITSMath-Bold.pfb", 0x1D468),
]
GLYPHS = ["L", "G", "J", "g"]
SIZES = [40, 80, 160]

rows = []
print(f"{'family':<9} {'font':<9} {'glyph':<5} " +
      "  ".join(f"{s}px J/H" for s in SIZES) + "   holes stable?")
for entry in FONTS:
    # a 4th element is the base codepoint of a mathematical
    # alphanumeric block; the glyphs are then named u1DXXX rather than
    # "L"/"G"/"J", and lowercase g sits 26 further on.
    fam, tag, fn = entry[:3]
    base = entry[3] if len(entry) > 3 else None
    # an entry may name a file outside the TeX tree (a hand-converted
    # font); a leading ~ or / is taken as a path, anything else as a
    # name to find in the tree.
    if fn.startswith(("~", "/")):
        p = pathlib.Path(fn).expanduser()
        src = p if p.is_file() else None
    else:
        src = next(TREE.rglob(fn), None)
    if src is None:
        print(f"{fam:<9} {tag:<9} FONT NOT FOUND {fn}"); continue
    f = t1_load(src)
    for g0 in GLYPHS:
        if base is None:
            g = g0
        else:
            off = (ord(g0) - 97 + 26) if g0.islower() else (ord(g0) - 65)
            g = f"u{base + off:04X}"
        if g not in f.charstrings:
            rows.append((fam, tag, g0, None)); continue
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
            rows.append((fam, tag, g0, None)); continue
        hs = {c[1] for c in cells}
        js = {c[0] for c in cells}
        rows.append((fam, tag, g0, cells))
        print(f"{fam:<9} {tag:<9} {g0:<5} " +
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
