r"""595 -- a table is several runs, and the join is by identifier.

WHAT A RUN IS. `pagedetect.scan_columns` renders every page at 150 dpi
and reports its lattice column count; `group_tables` then takes
MAXIMAL CONTIGUOUS runs of pages sharing a count. Two things end a
run: a page whose count differs, and a page with no lattice at all
(0 columns), which belongs to no table and ends the run it follows.

SO A LOGICAL LONGTABLE IS NOT A RUN. It is split wherever the lattice
detection wobbles by one column, wherever a page carries no lattice,
and wherever another table interrupts. `inkmeasure` takes ONE run by
ordinal and treats it as the whole table, which is right only when the
table happens to have produced exactly one run.

THE ORDINAL CANNOT CARRY THIS. `group_tables`' own docstring says a
column count cannot identify a table when two share one -- pdfdrill's
report has four longtables and the first and last are both six columns
-- so it falls back to order. But order only identifies a table when
the run count equals the table count, which is the assumption that
fails as soon as one table splits.

THE IDENTIFIERS CAN. `report.tables.json` already carries, per table,
its `identifiers` list, its `columns` and its `rows` count. And the
row identifiers are in report.pdf's TEXT LAYER, so a page can be asked
which rows are on it. That is a join key that needs no ordinal and no
column count, and it is available today without the row manifest of
580 stage 2.

READING THE TEXT LAYER IS NOT A G6 VIOLATION. G6 forbids inkdrill
reading text off a RASTER, which is what would make it agree with the
tool it cross-checks. `pdftotext` reads the PDF's own text objects --
the same standing as `reportcompare.target_columns` reading report.tex,
and that boundary is already stated there. No ink measurement touches
this.

AMBIGUITY IS REPORTED, NOT RESOLVED. A run whose identifiers fall in
more than one table is CONTESTED and is attributed to neither. Taking
the majority table, or the first, is 282's defect and the reason 285
was written.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from pagedetect import npages, tables                    # noqa: E402


def page_identifiers(pdf: pathlib.Path, bibkey: str, known: set):
    """{page: [identifier, ...]} from the PDF's text layer, plus any
    token that looked like an identifier and is not in the manifest.

    THE PATTERN IS NOT GUESSED. The first version matched
    `<bibkey>_[A-Z]{2,4}[0-9a-f]+`, which misses `0049_DIA_0001` --
    the image-region rows carry an underscore before the digits -- and
    reported six rows as MISSING when they were on the page all along.
    A join that silently drops a whole table because of a regex is
    worse than one that refuses.

    So extraction is deliberately permissive and the manifest decides:
    anything shaped like `<bibkey>_<letters><rest>` is a candidate, and
    the candidates are intersected with the identifiers the manifest
    actually lists. Whatever is left over is RETURNED and printed, so a
    pattern that is still too narrow shows up as unmatched tokens
    rather than as missing rows.

    ONE `pdftotext` call, not one per page: it separates pages with a
    form feed, so the split is free and 300 subprocesses are not.
    """
    # -raw, AND the identifier is then un-wrapped. Three modes were
    # tried and only this one works on both shapes of document:
    #
    #   plain    reads column-wise. Keeps a SHORT identifier whole
    #            (0049_DIA_0001) but returns it in the wrong sequence,
    #            and finds nothing at all when the identifier wraps.
    #   -layout  preserves the visual row, so a wrapped identifier is
    #            split by the entire rest of the line and cannot be
    #            rejoined without knowing the column geometry.
    #   -raw     content-stream order, so the two halves of a wrapped
    #            identifier are ADJACENT and a newline join recovers
    #            them. 14 rows on a page where the others found 0.
    #
    # A LONG BIBKEY IS WHAT WRAPS IT. `0049_EQ0001` fits the Identifier
    # column; `Geometric_topology_EQ0145` does not, and breaks after the
    # underscore. Both shapes are in the corpus, so the extraction has
    # to survive both -- and the sequence is taken from the manifest,
    # which is why -raw's ordering does not matter.
    r = subprocess.run(["pdftotext", "-raw", str(pdf), "-"],
                       capture_output=True, text=True, timeout=900)
    rx = re.compile(re.escape(bibkey) + r"_[A-Za-z]{2,6}_?[0-9A-Za-z]+")
    unwrap = re.compile(re.escape(bibkey) + r"_\s*\n\s*")
    out, unmatched = {}, collections.Counter()
    for i, page in enumerate(r.stdout.split("\f"), 1):
        page = unwrap.sub(bibkey + "_", page)
        seen, ordered = set(), []
        for g in rx.findall(page):
            if g not in known:
                unmatched[g] += 1
                continue
            if g not in seen:
                seen.add(g)
                ordered.append(g)
        if ordered:
            out[i] = ordered
    return out, unmatched


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("doc")
    ap.add_argument("--library", type=pathlib.Path,
                    default=pathlib.Path.home() / "pdfdrill-library")
    ap.add_argument("--dpi", type=int, default=150)
    args = ap.parse_args()
    d = args.library / args.doc
    pdf = d / "report.pdf"
    man = json.loads((d / "report.tables.json").read_text())
    bibkey = man["bibkey"]
    tabs = man["tables"]

    print(f"{args.doc}   bibkey {bibkey}")
    print(f"manifest: {len(tabs)} tables, "
          f"{sum(t['rows'] for t in tabs)} rows\n")
    print(f"  {'ord':>3} {'cols':>5} {'rows':>6}  caption")
    for t in tabs:
        print(f"  {t['ordinal']:>3} {t['columns']:>5} {t['rows']:>6}  "
              f"{t['caption']}")

    n = npages(pdf)
    print(f"\nreport.pdf: {n} pages. Scanning lattices at {args.dpi} dpi "
          f"...", flush=True)
    runs = tables(pdf, n, dpi=args.dpi)
    owner = {}
    for t in tabs:
        for i in t["identifiers"]:
            owner[i] = t["ordinal"]
    ident_of, unmatched = page_identifiers(pdf, bibkey, set(owner))
    print(f"{len(runs)} runs found; identifiers on "
          f"{len(ident_of)} of {n} pages")
    if unmatched:
        print(f"  {sum(unmatched.values())} identifier-shaped tokens NOT in "
              f"the manifest, e.g. {list(unmatched)[:4]}")
    print()

    # WHICH PAGE EACH ROW IS ON. Set membership comes from the text
    # layer; SEQUENCE comes from the manifest, which is the builder's
    # own emission order and needs no inference. Where the two can be
    # compared they are, and the disagreement is printed.
    page_of = {}
    for pg in sorted(ident_of):
        for i_ in ident_of[pg]:
            page_of.setdefault(i_, pg)
    run_of = {}
    for r in runs:
        for pg in r["pages"]:
            run_of[pg] = r["ordinal"]

    print("RUNS, in document order")
    print(f"  {'ord':>3} {'cols':>5} {'pages':>11} {'ids':>6}  "
          f"tables whose rows appear in it")
    for r in runs:
        ids = [i_ for pg in r["pages"] for i_ in ident_of.get(pg, [])]
        tally = collections.Counter(owner[i_] for i_ in ids if i_ in owner)
        span = (f"{r['pages'][0]}-{r['pages'][-1]}"
                if len(r["pages"]) > 1 else str(r["pages"][0]))
        note = ("none" if not tally else
                ", ".join(f"table {k} x{v}" for k, v in sorted(tally.items())))
        print(f"  {r['ordinal']:>3} {r['columns']:>5} {span:>11} "
              f"{len(ids):>6}  {note}")

    print("\nTABLES, joined by identifier rather than by ordinal")
    print(f"  {'ord':>3} {'cols':>5} {'expected':>9} {'matched':>8} "
          f"{'missing':>8} {'runs':>6}  run ordinals / order")
    for tb in tabs:
        exp = tb["identifiers"]
        found = [i_ for i_ in exp if i_ in page_of]
        rset = sorted({run_of[page_of[i_]] for i_ in found
                       if page_of[i_] in run_of})
        pages = [page_of[i_] for i_ in found]
        monotone = all(a <= b for a, b in zip(pages, pages[1:]))
        cols = sorted({r["columns"] for r in runs
                       if r["ordinal"] in rset})
        print(f"  {tb['ordinal']:>3} {tb['columns']:>5} {len(exp):>9} "
              f"{len(found):>8} {len(exp)-len(found):>8} {len(rset):>6}  "
              f"{rset if len(rset) <= 6 else str(rset[:6]) + '...'}"
              f"  cols {cols}  "
              f"{'page order ok' if monotone else 'PAGE ORDER BREAKS'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
