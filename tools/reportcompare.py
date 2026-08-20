"""Compare the Rendered and Scan columns of formula reports.

Usage: python3 tools/reportcompare.py [list.txt] [library]
  The list is pdfdrill's report roster (lines ending
  "-> ~/pdfdrill-library/<dir>/report.pdf"). Renders cache under
  $INKDRILL_WORK; each document gets <dir>/report.compare.tsv. An
  input yielding zero rows is REPORTED with its reason and sets a
  nonzero exit (P16) -- an empty result is a defect, not a silence.

Per report: 150 dpi probe -> LEADING RUN of 5-col pages (gap <= 3) =
the display section; render those at 300+600; `inkdrill compare` per
page; aggregate with the sliver filter (lattice rows < 40 px @300 are
inter-row strips, not table rows) into <dir>/report.compare.tsv.
"""
import concurrent.futures as cf
import os, pathlib, re, subprocess, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from inkdrill.pnmio import read_pnm_stream
from inkdrill.pngio import read_png, auto_mask
from inkdrill.__main__ import _table_cells

import tempfile
LIB = pathlib.Path(sys.argv[2] if len(sys.argv) > 2
                   else "~/pdfdrill-library").expanduser()
LIST = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else \
    LIB / "P13-arxiv-reports.txt"
S = pathlib.Path(os.environ.get("INKDRILL_WORK") or
                 (tempfile.gettempdir() + "/inkdrill-reportcompare"))
S.mkdir(parents=True, exist_ok=True)
if not LIST.is_file():
    raise SystemExit(__doc__.strip().splitlines()[2] +
                     f"\n  no such list: {LIST}")
DIRS = re.findall(r"-> ~/pdfdrill-library/(\S+)/report\.pdf",
                  LIST.read_text())
if not DIRS:
    raise SystemExit(f"{LIST}: no '-> ~/pdfdrill-library/<dir>/report.pdf' "
                     f"lines found")

def npages(pdf):
    out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True,
                         text=True).stdout
    return int(re.search(r"^Pages:\s+(\d+)", out, re.M).group(1))

def probe(pdf, n):
    five = []
    for lo in range(1, n + 1, 25):
        hi = min(lo + 24, n)
        gs = subprocess.run(
            ["gs","-q","-dNOPAUSE","-dBATCH","-sDEVICE=pgmraw","-r150",
             f"-dFirstPage={lo}",f"-dLastPage={hi}",
             "-sOutputFile=%stdout",str(pdf)],
            capture_output=True, check=True).stdout
        for i, img in enumerate(read_pnm_stream(gs, dpi=(150.0,150.0))):
            mask,_ = auto_mask(img.gray, img.width, img.height, 200)
            cells = _table_cells(mask, 4.0)
            if cells and max(c for _, c in cells) + 1 == 5:
                five.append(lo + i)
    run, last = [], 0
    for p in five:
        if not run and p <= 3: run.append(p); last = p
        elif run and p - last <= 3:
            run.extend(range(last + 1, p + 1)); last = p
        elif run: break
    return run

jobs = []
display_count = {}
for name in DIRS:
    pdf = LIB / name / "report.pdf"
    d = S / name; d.mkdir(exist_ok=True)
    # the regeneration rolled through while the first pass ran: any
    # scratch older than the pdf is from a superseded build
    pm = pdf.stat().st_mtime
    stale = [f for f in d.iterdir() if f.stat().st_mtime < pm]
    if stale:
        for f in d.iterdir(): f.unlink()
        print(f"{name}: cleared {len(stale)} stale files", flush=True)
    try:
        disp = probe(pdf, npages(pdf))
    except Exception as e:
        print(f"{name}: probe FAILED {e}", flush=True); continue
    display_count[name] = len(disp)
    print(f"{name}: display pages {len(disp)}", flush=True)
    for p in disp:
        jobs.append((name, pdf, p, d))

def one(job):
    name, pdf, p, d = job
    a = d / f"p{p:03d}_r300.png"; b = d / f"p{p:03d}_r600.png"
    for dpi, out in ((300, a), (600, b)):
        if not out.exists():
            subprocess.run(["gs","-q","-dNOPAUSE","-dBATCH",
                            "-sDEVICE=png16m",f"-r{dpi}",
                            f"-dFirstPage={p}",f"-dLastPage={p}",
                            f"-sOutputFile={out}",str(pdf)], check=True)
    md = d / f"p{p:03d}.md"
    if not md.exists():
        subprocess.run([sys.executable,"-m","inkdrill","compare",
                        str(a),str(b),"-o",str(md)],
                       capture_output=True, cwd=str(pathlib.Path(__file__).resolve().parent.parent))
    return name, p

with cf.ThreadPoolExecutor(max_workers=4) as ex:
    n = 0
    for name, p in ex.map(one, jobs):
        n += 1
        if n % 25 == 0: print(f"compared {n}/{len(jobs)}", flush=True)

zero_rows = []
for name in DIRS:
    d = S / name
    hdr = ("report_page\tline\tdis\tA_eq_B\tL_comp\tL_holes\tL_stk"
           "\tL_cen\tL_off\tR_comp\tR_holes\tR_stk\tR_cen\tR_off")
    rows = []
    for md in sorted(d.glob("p*.md")):
        p = int(md.stem[1:])
        png = d / f"p{p:03d}_r300.png"
        img = read_png(png)
        m = auto_mask(img.gray, img.width, img.height, 200)[0]
        cells = _table_cells(m, 4.0)
        if not cells: continue
        nr = max(r for r, _ in cells) + 1
        hts = {r: cells[(r, 0)][3] - cells[(r, 0)][1] for r in range(nr)}
        for line in md.read_text().splitlines()[2:]:
            c = [x.strip() for x in line.split("|")[1:-1]]
            ln = int(c[1])
            if ln == 0 or hts.get(ln, 999) < 40: continue
            L = [int(x) for x in c[3:8]]; R = [int(x) for x in c[8:13]]
            dis = sum(abs(x - y) for x, y in zip(L, R))
            rows.append("\t".join(map(str, [p, ln, dis, c[13]] + L + R)))
    (LIB / name / "report.compare.tsv").write_text(
        "\n".join([hdr] + rows) + "\n")
    print(f"{name}: {len(rows)} rows -> report.compare.tsv", flush=True)
    if not rows:
        zero_rows.append(
            (name, "probe found no 5-column display pages"
             if not display_count.get(name)
             else f"{display_count[name]} display pages compared but "
                  f"every row was filtered"))
# P16: an empty result is an error, not a silence -- every zero-row
# input is listed with its reason, and the exit code says so
if zero_rows:
    print(f"ZERO-ROW INPUTS ({len(zero_rows)} of {len(DIRS)}):",
          flush=True)
    for name, why in zero_rows:
        print(f"  ZERO {name}: {why}", flush=True)
print("ALL DONE", flush=True)
import sys
sys.exit(1 if zero_rows else 0)
