"""One page listing every document's evidence, for inspection by eye.

    python3 tools/evidenceindex.py [--marks-dir D] [--library L] [--out F]

Reads nothing but the artifacts. Two rules it exists to hold, both of
which were violated by the ad-hoc version it replaces:

COUNTS COME FROM THE MARKS FILES, NEVER FROM index.json. The index
carried the counts of the emission that wrote it, and 15 of 21 documents
had been edited by eye verdict since -- a published total of 8,408
against a true 8,256, one document off by 94.

A DATE IS NOT EVIDENCE THAT THE MARKS ARE IN THE PDF. pdfdrill's build
takes the marks as an off-by-default option, so a build without them
succeeds and is NEWER than the marks it does not contain. The column
that matters reads which crop directory the .tex pulls in; 20 of 21
builds dated after their marks contained none of them.

Where two evidence trees exist -- the nested `<doc>/evidence-formula/`
and the flat `<doc>/evidence-formula.tex` -- the NEWER is read and the
older is named, because a rebuild writes flat and leaves the nested one
in place.
"""
from __future__ import annotations

import argparse
import datetime
import html
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from tools.formulamarks import (MARKED_CROPS, _evidence_both,  # noqa: E402
                                _evidence_tex, verify_document)

KINDS = ("formula", "equation", "image", "table")


def _newest(doc: pathlib.Path, stem: str, ext: str):
    found = [p for p in (doc / stem / f"{stem}.{ext}", doc / f"{stem}.{ext}")
             if p.exists()]
    return max(found, key=lambda p: p.stat().st_mtime) if found else None


def collect(marks_dir: pathlib.Path, library: pathlib.Path):
    out = []
    for mf in sorted(marks_dir.glob("*/marks.json")):
        name = mf.parent.name
        doc = library / name
        row = verify_document(name, marks_dir, library)
        row["evidence"] = {k: _newest(doc, f"evidence-{k}", "pdf") for k in KINDS}
        row["report"] = _newest(doc, "report", "pdf")
        row["residuals"] = _newest(doc, "residuals", "pdf")
        row["html"] = {k: (doc / v) if (doc / v).exists() else None
                       for k, v in (("formula", "formula-report.html"),
                                    ("compare", "compare.html"),
                                    ("inspect", f"{name}.inspect.html"))}
        pages = doc / "inspect" / "pages"
        row["pages_dir"] = pages if pages.is_dir() else None
        row["pages"] = len(list(pages.glob("*.png"))) if pages.is_dir() else 0
        out.append(row)
    return out


def render(rows):
    def link(p, label):
        return (f'<a href="file://{html.escape(str(p))}">{label}</a>' if p
                else '<span class="no">—</span>')
    cells = []
    for r in sorted(rows, key=lambda r: -(r["marked"] or 0)):
        state = ('<span class="ok">marks embedded</span>' if r["embedded"]
                 else f'<span class="warn">no marks in the PDF</span>')
        note = ("" if not r["warn"] else
                '<div class="w">' + "<br>".join(html.escape(w) for w in r["warn"])
                + "</div>")
        cells.append(f"""<tr>
 <td class="doc">{html.escape(r['document'])}{note}</td>
 <td class="n">{r['marked']}</td>
 <td>{' '.join(link(r['evidence'][k], k) for k in KINDS)}</td>
 <td>{link(r['report'],'report')} {link(r['residuals'],'residuals')}</td>
 <td>{' '.join(link(v, k) for k, v in r['html'].items())}</td>
 <td class="n">{link(r['pages_dir'], str(r['pages'])) if r['pages'] else '—'}</td>
 <td class="st">{state}<div class="w">{r['crops']} crops</div></td></tr>""")
    emb = sum(1 for r in rows if r["embedded"])
    banner = ("" if emb == len(rows) else
              f'<div class="note"><b>{emb} of {len(rows)} evidence PDFs embed '
              f'the marks.</b> The rest were built before the marks were passed '
              f'to the build, so they show unmarked crops. The marked crops '
              f'exist on disk for every document, so this is a rebuild, not a '
              f're-measure.</div>')
    return f"""<!doctype html>
<meta charset="utf-8"><title>Evidence index</title>
<style>
 :root {{ --fg:#1a1a1a; --bg:#fff; --mut:#6b6b6b; --line:#e3e3e3; --acc:#8a2f2f;
   --ok:#1f6f3f; --warn:#b35b00; }}
 @media (prefers-color-scheme: dark) {{ :root:not([data-theme=light]) {{
   --fg:#e8e6e3; --bg:#17191c; --mut:#9aa0a6; --line:#2c3034; --acc:#e0908c;
   --ok:#6cc08b; --warn:#e0a060; }} }}
 body {{ background:var(--bg); color:var(--fg); margin:0; padding:24px 16px;
   font:15px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,sans-serif; }}
 .wrap {{ max-width:1150px; margin:0 auto; }}
 h1 {{ font-size:22px; margin:0 0 4px; }}
 p.sub {{ color:var(--mut); margin:0 0 6px; }}
 .note {{ border-left:3px solid var(--warn); padding:8px 12px; margin:14px 0 20px;
   background:color-mix(in srgb, var(--warn) 8%, transparent); font-size:14px; }}
 table {{ border-collapse:collapse; width:100%; font-size:14px; }}
 th {{ text-align:left; font-weight:600; color:var(--mut); font-size:12px;
   text-transform:uppercase; letter-spacing:.04em; padding:6px 8px;
   border-bottom:1px solid var(--line); }}
 td {{ padding:7px 8px; border-bottom:1px solid var(--line); vertical-align:top; }}
 td.doc {{ max-width:330px; }}
 td.n {{ text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums; }}
 a {{ color:var(--acc); text-decoration:none; }} a:hover {{ text-decoration:underline; }}
 .no {{ color:var(--mut); }} .st {{ white-space:nowrap; font-size:13px; }}
 .ok {{ color:var(--ok); font-weight:600; }} .warn {{ color:var(--warn); font-weight:600; }}
 .w {{ color:var(--mut); font-size:12px; font-weight:400; }}
 footer {{ color:var(--mut); font-size:13px; margin-top:18px; }}
</style>
<div class="wrap">
<h1>Formula evidence — {len(rows)} documents</h1>
<p class="sub">Marks measured by inkdrill, evidence built by pdfdrill.
Links open the local files.</p>
{banner}
<table>
<tr><th>document</th><th>marked</th><th>evidence PDFs</th><th>report</th>
    <th>html</th><th>pages</th><th>marks in the PDF</th></tr>
{"".join(cells)}
</table>
<footer>Generated {datetime.date.today()} by tools/evidenceindex.py. Counts read
from each marks.json; the &ldquo;marks in the PDF&rdquo; column reads which crop
directory the evidence .tex pulls in, not its date.</footer>
</div>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--marks-dir", type=pathlib.Path,
                    default=pathlib.Path.home() / "inkdrill-marks")
    ap.add_argument("--library", type=pathlib.Path,
                    default=pathlib.Path.home() / "pdfdrill-library")
    ap.add_argument("--out", type=pathlib.Path, default=None)
    args = ap.parse_args()
    rows = collect(args.marks_dir, args.library)
    out = args.out or args.marks_dir / "reports-index.html"
    out.write_text(render(rows))
    emb = sum(1 for r in rows if r["embedded"])
    print(f"{out}: {len(rows)} documents, {emb} with marks in the PDF, "
          f"{sum(r['marked'] or 0 for r in rows)} marks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
