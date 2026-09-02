r"""498 -- read a formula's ink off a LOCAL page render, not a CDN crop.

WHY THIS EXISTS. 231 found two documents where MathPix wrote \\mathscr
where the author's source says \\mathcal, and one row --
0707.4470_FO0175 -- where the swap also picked the wrong letter and
the glyph vanished. Checking that against ink needs a picture of the
formula, and 488 established that FO rows carry no canonical_uri: an
inline formula has no MathPix crop of its own. A check fed only by CDN
crops is therefore structurally blind to exactly the population the
finding lives in, and a null result from it would say nothing about
\\mathcal.

461 solved the same problem for tables on the pdfdrill side by
rendering the page locally and cutting the region out of it. This is
that route for formulas, on this side, where the junction count is.

--leading IS HOW A GLYPH GETS COMPARED WITHOUT BEING NAMED. A line is
many components and most of them are ordinary letters, so a statistic
over all of them measures the prose, not the script letter: over
0707.4470's \mathscr lines the median junction count is 4 and that
figure is mostly Roman text. The mode instead keeps only lines whose
LaTeX BEGINS with the token -- `\[\mathscr{J}=...` -- and reports the
LEFTMOST component, which is then that glyph by position rather than
by recognition. It is a positional claim, it is stated here, and the
harness prints how many lines it kept and how many it dropped, because
a selection rule that silently keeps three lines is the shape 231's
own class C came from.

WHAT IT DOES NOT DO. It does not name a glyph. Line regions come from
`lines.json`, and a line is many components; which component is the
script letter needs symbol identity, which this project does not have
and which units.md records as a deliberate gap. So this reports every
component of the line with its counts and leaves the reading to the
caller. A tool that picked "the script one" would be inventing the
identity it lacks.

THE THREE TRAPS 461 RECORDED, ALL OF WHICH APPLY HERE:

  * MathPix regions are in ITS page-image pixels. Every coordinate is
    scaled by (raster width / that page's page_width), READ PER PAGE.
    A page scaled by another page's width lands on the wrong part of
    the page and still looks like a plausible piece of it.
  * A page with no recorded width is SKIPPED, not defaulted.
  * The page is parsed OUT OF THE FILENAME rather than zipped against
    a request list, so a stale render cannot shift every pairing by
    one and cut each region from its neighbour's page.

AND ONE THIS SIDE ADDS. The junction count is not scale-invariant:
496 measured it moving on real pages and 497 on 25% of rendered
glyphs, because a 2-px stroke thins to a staircase and a staircase
branches. `--dpi` is therefore an argument that must be reported
beside any number this produces, and the harness prints it.
"""

from __future__ import annotations

import argparse
import ast
import json
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from inkdrill.pnmio import mask_from_pgm            # noqa: E402
from inkdrill.raster import InkMask                 # noqa: E402
from inkdrill.skeleton import parts                 # noqa: E402

THRESHOLD = 200


def lines_with(doc: pathlib.Path, pattern: str, leading: bool = False,
               math_only: bool = False):
    """Every `lines.json` line whose text matches, with its page geometry.

    Yields (page, index, type, text, region, page_width, page_height).
    A page carrying no width is skipped with a reason, never defaulted
    -- 461's second trap, and the one that fails silently.
    """
    lj = next(doc.glob("*.lines.json"), None)
    if lj is None:
        return [], "no lines.json"
    rx = re.compile(pattern)
    out, skipped = [], 0
    for pg in json.loads(lj.read_text())["pages"]:
        pw, ph = pg.get("page_width"), pg.get("page_height")
        for j, ln in enumerate(pg.get("lines", [])):
            txt = str(ln.get("text", ""))
            if not rx.search(txt):
                continue
            if math_only and ln.get("type") != "math":
                continue
            if leading:
                # the token must OPEN the line's maths, ignoring the
                # \[ or \( that delimits it
                head = re.sub(r"^[\s]*(\\\[|\\\()?[\s]*", "", txt)
                if not rx.match(head):
                    continue
            r = ln.get("region")
            if isinstance(r, str):
                r = ast.literal_eval(r)
            if not r:
                skipped += 1
                continue
            if not pw or not ph:
                skipped += 1
                continue
            out.append((pg["page"], j, ln.get("type", ""), txt, r, pw, ph))
    return out, (f"{skipped} matching lines had no region or no page width"
                 if skipped else "")


def source_pdf(d: pathlib.Path, name: str) -> pathlib.Path:
    """The document's OWN pdf, never `report.pdf`.

    A library directory holds both, and `next(d.glob("*.pdf"))` returned
    whichever the filesystem listed first. `report.pdf` is the generated
    report: its page numbering has nothing to do with `lines.json`, so a
    region for page 12 lands on page 12 of the report. Here that failed
    loudly because the report was shorter than the document; on a longer
    report it would have cropped a plausible-looking rectangle of the
    wrong page and reported numbers for it. Same family as 461's third
    trap, and it went the other way.
    """
    exact = d / f"{name}.pdf"
    if exact.is_file():
        return exact
    others = [f for f in d.glob("*.pdf") if f.name != "report.pdf"]
    if len(others) == 1:
        return others[0]
    raise SystemExit(f"{name}: cannot identify the source pdf "
                     f"(candidates {[f.name for f in others]})")


def render(pdf: pathlib.Path, pages, dpi: int, work: pathlib.Path, key: str):
    """One gs call per page. Returns {page: path}, keyed by the page
    parsed OUT OF THE FILENAME (461's third trap).

    `key` is the DOCUMENT name, not the pdf stem: every document's own
    pdf is `<name>.pdf`, but a fallback stem can repeat across
    documents, and two concurrent runs sharing a work directory would
    then read each other's pages.
    """
    got = {}
    for p in sorted(set(pages)):
        f = work / f"{key}_p{p:04d}_r{dpi}.pgm"
        if not f.exists():
            subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH",
                            "-sDEVICE=pgmraw", f"-r{dpi}",
                            "-dTextAlphaBits=4", "-dGraphicsAlphaBits=4",
                            f"-dFirstPage={p}", f"-dLastPage={p}",
                            f"-sOutputFile={f}", str(pdf)], check=True)
        # GHOSTSCRIPT EXITS 0 FOR A PAGE PAST THE END and writes
        # nothing, so `check=True` does not catch it. A missing page is
        # a refusal, not a crash four frames down in the reader.
        if not f.exists():
            raise SystemExit(f"{pdf.name}: no page {p} (gs wrote nothing); "
                             f"the region file and this pdf disagree "
                             f"about how many pages the document has")
        got[int(f.stem.split("_p")[1].split("_r")[0])] = f
    return got


def crop(mask: InkMask, region, page_w, page_h) -> InkMask:
    """The region, scaled from MathPix page pixels into raster pixels
    by THIS page's width (461's first trap)."""
    sx = mask.width / page_w
    sy = mask.height / page_h
    x0 = max(0, int(region["top_left_x"] * sx))
    y0 = max(0, int(region["top_left_y"] * sy))
    x1 = min(mask.width, int((region["top_left_x"] + region["width"]) * sx))
    y1 = min(mask.height, int((region["top_left_y"] + region["height"]) * sy))
    if x1 <= x0 or y1 <= y0:
        raise ValueError(f"empty region {region} on {mask.width}x{mask.height}")
    buf = bytearray()
    for y in range(y0, y1):
        buf += mask.data[y * mask.width + x0:y * mask.width + x1]
    return InkMask(bytes(buf), x1 - x0, y1 - y0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("docs", nargs="+")
    ap.add_argument("--library", type=pathlib.Path,
                    default=pathlib.Path.home() / "pdfdrill-library")
    ap.add_argument("--work", type=pathlib.Path,
                    default=pathlib.Path.home() / "inkdrill-work" / "scriptink")
    ap.add_argument("--token", default=r"\\mathscr")
    ap.add_argument("--dpi", type=int, default=900)
    ap.add_argument("--min-ink", type=int, default=20,
                    help="drop components below this many pixels")
    ap.add_argument("--max-lines", type=int, default=0,
                    help="cap lines per document (0 = no cap). The cap "
                         "is REPORTED, never silent.")
    ap.add_argument("--math-only", action="store_true",
                    help="keep only display-math lines. A text line is "
                         "mostly prose, so a statistic over its "
                         "components measures Roman letters; this is "
                         "the high-yield filter, applied identically "
                         "to both populations.")
    ap.add_argument("--leading", action="store_true",
                    help="keep only lines whose LaTeX begins with the "
                         "token, and report the LEFTMOST component")
    ap.add_argument("-o", type=pathlib.Path)
    args = ap.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)

    rows = ["doc\tpage\tline\ttype\tncomp\tx0\ty0\tw\th\tink\tholes\tJ\tends"]
    print(f"token /{args.token}/   dpi {args.dpi}   "
          f"min_ink {args.min_ink}", flush=True)
    for name in args.docs:
        d = args.library / name
        if not d.is_dir():
            print(f"{name}: no such document", flush=True)
            continue
        pdf = source_pdf(d, name)
        found, why = lines_with(d, args.token, args.leading,
                                args.math_only)
        if why:
            print(f"{name}: {why}", flush=True)
        if not found:
            print(f"{name}: no matching line with a region", flush=True)
            continue
        dropped = 0
        if args.max_lines and len(found) > args.max_lines:
            dropped = len(found) - args.max_lines
            found = found[:args.max_lines]
        rendered = render(pdf, [f[0] for f in found], args.dpi,
                          args.work, name)
        nline = 0
        for page, j, kind, txt, r, pw, ph in found:
            f = rendered.get(page)
            if f is None:
                print(f"{name} p{page}: not rendered", flush=True)
                continue
            m = mask_from_pgm(f, threshold=THRESHOLD)
            try:
                c = crop(m, r, pw, ph)
            except ValueError as e:
                print(f"{name} p{page} line {j}: {e}", flush=True)
                continue
            ps = parts(c, min_ink=args.min_ink)
            if args.leading:
                ps = ps[:1]
            nline += 1
            for p in ps:
                rows.append("\t".join(map(str, [
                    name, page, j, kind, len(ps), p.x0, p.y0,
                    p.width, p.height, p.ink, p.holes,
                    p.junctions, p.ends])))
        js = [int(x.split("\t")[11]) for x in rows[1:]
              if x.startswith(name + "\t")]
        print(f"{name}: {nline} lines, {len(js)} components, "
              f"junctions max {max(js) if js else 0}, "
              f"median {sorted(js)[len(js)//2] if js else 0}"
              + (f"   [{dropped} lines dropped by --max-lines]"
                 if dropped else ""), flush=True)
        for f in rendered.values():
            f.unlink(missing_ok=True)
    if args.o:
        args.o.write_text("\n".join(rows) + "\n")
        print(f"{len(rows)-1} component rows -> {args.o}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
