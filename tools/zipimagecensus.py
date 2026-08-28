"""Independent census of tex.zip image filenames (285's premise)."""
import pathlib, re, zipfile, collections, sys
LIB = pathlib.Path.home()/"pdfdrill-library"
COORD = re.compile(r"-(\d+)_(\d+)_(\d+)_(\d+)_(\d+)\.\w+$")
IMG = (".png", ".jpg", ".jpeg", ".gif", ".pdf", ".eps")
c = collections.Counter()
odd, coll = [], []
zips = sorted(LIB.glob("*/*.tex.zip"))
for z in zips:
    c["zips"] += 1
    try:
        with zipfile.ZipFile(z) as f:
            names = [n for n in f.namelist() if n.lower().endswith(IMG)]
    except Exception as e:
        c["unreadable zips"] += 1; continue
    for n in names:
        c["images"] += 1
        base = n.rsplit("/", 1)[-1]
        if COORD.search(base):
            c["coordinate form"] += 1
        elif re.search(r"[()\[\]]|%28|%29", n):
            c["collision form (brackets)"] += 1
            if len(coll) < 20: coll.append((z.parent.name, n))
        else:
            c["neither"] += 1
            if len(odd) < 25: odd.append((z.parent.name, base))
for k in ("zips","images","coordinate form","collision form (brackets)",
          "neither","unreadable zips"):
    print(f"  {k:<28} {c[k]}")
print("\n  'neither' examples:")
for d, b in odd[:12]:
    print(f"    {b[:60]:<62} {d[:24]}")
if coll:
    print("\n  COLLISION FORM FOUND:")
    for d, n in coll: print(f"    {n}  in {d}")
