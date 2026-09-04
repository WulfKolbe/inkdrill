r"""rowjoin.py -- which page each report row is on (597).

A report's table is not a lattice run. `pagedetect.group_tables` takes
maximal contiguous page spans of constant detected column count, and
595 measured both ways that fails: one run can hold SEVERAL tables --
0049's display equations and inline formulas are both 5 columns and
contiguous, so they are one run -- and one table can span several runs
of DIFFERENT widths, as Geometric_topology's 212 image-region rows do,
6 columns on their first page and 5 after.

So a run cannot be attributed to a table at all, and an ordinal cannot
carry it either: 608 of 717 documents have two tables sharing a column
count. The join key is the ROW IDENTIFIER, which the table manifest
already lists and the report's own text layer already carries.

This module is the join and nothing else. It takes text, not a path:
the extraction rules below are the whole of the difficulty and they
are testable without a PDF, while `pdftotext` belongs to the caller
that has one. Nothing here reads a file or starts a process.

CONTRACT
========

G1  pure -- a manifest and per-page text in, a `Join` out. No file
    access, no subprocess, no clock.
G2  THE PATTERN IS PERMISSIVE AND THE MANIFEST DECIDES. Extraction
    matches anything shaped like an identifier; membership is decided
    by the manifest's own lists. A guessed pattern
    (`<bibkey>_[A-Z]{2,4}[0-9a-f]+`) missed `0049_DIA_0001`, whose
    image-region rows carry an underscore before the digits, and
    reported all six rows of that table as absent. Tokens that look
    like identifiers and are not in the manifest are RETURNED in
    `unknown`, never dropped -- that diagnostic is what caught it.
G3  A WRAPPED IDENTIFIER IS REJOINED. `0049_EQ0001` fits the report's
    Identifier column; `Geometric_topology_EQ0145` does not and breaks
    after the underscore. In content-stream order the halves are
    adjacent, so a `<bibkey>_` ending a line is joined to the next
    line. Without this, 6,485 of 6,717 rows on one report read as
    missing.
G4  ORDER COMES FROM THE MANIFEST, never from reading order. A page's
    text can return the right SET in the wrong SEQUENCE -- 0049's
    image rows come back 1, 3, 4, 5, 2 -- which mispairs every row
    while the counts look perfect. The manifest's `identifiers` list
    is the builder's own emission order.
G5  A row found on more than one page keeps its FIRST page, so a
    repeated header or a cross-reference cannot move a row later in
    the document than it is.
G6  An identifier the manifest names and no page carries is reported
    in `missing`, not omitted. A short result and a complete one must
    not look alike.
G7  `Join.rows` is ordered by (table ordinal, row index) and every
    manifest row appears exactly once, found or not, so a consumer can
    walk it against the manifest without re-sorting or re-counting.
"""

from __future__ import annotations

import re
from typing import NamedTuple

__all__ = ["Row", "Join", "join", "IDENT"]

#: permissive on purpose (G2) -- the manifest, not this, decides
IDENT = r"_[A-Za-z]{2,8}_?[0-9A-Za-z]+"


class Row(NamedTuple):
    """One manifest row, with the page it was found on or `None`."""
    table: int
    index: int
    identifier: str
    page: "int | None"


class Join(NamedTuple):
    rows: list            #: every manifest row, ordered (G7)
    missing: list         #: identifiers no page carried (G6)
    unknown: dict         #: identifier-shaped tokens not in the manifest
    pages_with_rows: int

    def by_table(self) -> dict:
        """{table ordinal: [Row, ...]} in row order."""
        out: dict = {}
        for r in self.rows:
            out.setdefault(r.table, []).append(r)
        return out

    def page_of(self) -> dict:
        return {r.identifier: r.page for r in self.rows if r.page is not None}


def _tables_of(manifest):
    ts = manifest["tables"] if isinstance(manifest, dict) else manifest
    return sorted(ts, key=lambda t: t["ordinal"])


def find_identifiers(text: str, bibkey: str, known) -> list:
    """Identifiers in ONE page's text, first occurrence first (G2, G3).

    `known` decides membership; anything matching the shape and not in
    it is the caller's problem to see, not this function's to hide --
    `join` collects those separately.
    """
    # G3: a bibkey left dangling at a line end belongs to the token
    # beginning the next line.
    text = re.sub(re.escape(bibkey) + r"_[ \t]*\n[ \t]*", bibkey + "_", text)
    seen, out = set(), []
    for m in re.finditer(re.escape(bibkey) + IDENT, text):
        g = m.group(0)
        if g in known and g not in seen:
            seen.add(g)
            out.append(g)
    return out


def unknown_tokens(text: str, bibkey: str, known) -> list:
    """The diagnostic of G2: identifier-shaped, manifest-absent."""
    text = re.sub(re.escape(bibkey) + r"_[ \t]*\n[ \t]*", bibkey + "_", text)
    return [m.group(0) for m in re.finditer(re.escape(bibkey) + IDENT, text)
            if m.group(0) not in known]


def join(manifest, pages) -> Join:
    """Join a table manifest to the pages its rows appear on.

    `manifest` is a `report.tables.json` -- a dict with `bibkey` and
    `tables`, each table carrying `ordinal` and `identifiers`.
    `pages` is the report's text, one string per page, page 1 first.
    """
    bibkey = manifest["bibkey"]
    tables = _tables_of(manifest)
    known = {i for t in tables for i in t["identifiers"]}
    if not known:
        raise ValueError(f"{bibkey}: the manifest lists no identifiers")

    first_page, unknown = {}, {}
    hit_pages = 0
    for n, text in enumerate(pages, 1):
        got = find_identifiers(text, bibkey, known)
        if got:
            hit_pages += 1
        for g in got:
            first_page.setdefault(g, n)      # G5
        for u in unknown_tokens(text, bibkey, known):
            unknown[u] = unknown.get(u, 0) + 1

    rows, missing = [], []
    for t in tables:                          # G4, G7
        for k, ident in enumerate(t["identifiers"]):
            p = first_page.get(ident)
            if p is None:
                missing.append(ident)         # G6
            rows.append(Row(t["ordinal"], k, ident, p))
    return Join(rows, missing, unknown, hit_pages)
