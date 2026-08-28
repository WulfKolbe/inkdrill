"""Does the coordinate filename resolve to a lines.json region on its
own? If it does, 285's matching problem does not exist."""
import pathlib, re, zipfile, json, collections, random, sys
LIB = pathlib.Path.home()/"pdfdrill-library"
COORD = re.compile(r"-(\d+)_(\d+)_(\d+)_(\d+)_(\d+)\.\w+$")
IMG = (".png",".jpg",".jpeg",".gif")
zips = sorted(LIB.glob("*/*.tex.zip"))
random.seed(5); zips = random.sample(zips, min(60, len(zips)))
c = collections.Counter(); miss = []
for z in zips:
    d = z.parent
    lj = [p for p in sorted(d.glob("*.lines.json")) if "pdfminer" not in p.name]
    if not lj: c["no lines.json"] += 1; continue
    try:
        j = json.loads(lj[0].read_text(errors="replace"))
    except Exception:
        c["lines.json unreadable"] += 1; continue
    regions = collections.defaultdict(set)
    for p in j.get("pages", []):
        for l in p.get("lines", []):
            r = l.get("region")
            if r: regions[p["page"]].add((r["height"], r["width"],
                                          r["top_left_y"], r["top_left_x"]))
    c["documents"] += 1
    try:
        with zipfile.ZipFile(z) as f:
            names = [n for n in f.namelist() if n.lower().endswith(IMG)]
    except Exception:
        c["unreadable zip"] += 1; continue
    for n in names:
        m = COORD.search(n.rsplit("/",1)[-1])
        if not m: c["not coordinate form"] += 1; continue
        pg, h, w, y, x = (int(g) for g in m.groups())
        c["coordinate images"] += 1
        if (h, w, y, x) in regions.get(pg, ()):
            c["EXACT region match"] += 1
        else:
            c["no exact match"] += 1
            if len(miss) < 8: miss.append((d.name, n.rsplit("/",1)[-1]))
for k in ("documents","coordinate images","EXACT region match","no exact match",
          "not coordinate form","no lines.json","lines.json unreadable"):
    if c[k]: print(f"  {k:<24} {c[k]}")
if c["coordinate images"]:
    print(f"  match rate {100.0*c['EXACT region match']/c['coordinate images']:.2f}%")
for d,n in miss: print(f"    unmatched: {n[:52]}  {d[:26]}")
