"""font.py — font inventory, name resolution, and glyph-weighted coverage.

CONTRACT (written before implementation; see docs/units.md U9)
=============================================================

Scope, and why this unit is smaller than the plan's U9
------------------------------------------------------
The plan's U9 is two things joined: identify and load embedded fonts, and
rasterize a glyph from one. This module is the FIRST half -- inventory,
name resolution, and deciding whether a given glyph is on the fast path.

The second half -- parsing CFF and TrueType outlines and scan-converting
Bezier contours in pure standard library -- is a substantially larger
piece of work than any unit so far, and it is named here rather than
half-built. Splitting at this line is not arbitrary: everything below is
exactly and hermetically testable against fixture text, while a
rasterizer needs its own oracle and its own premise check.

The metric that inverts the answer
----------------------------------
docs/units.md assumption 8 asked whether arXiv PDFs are "predominantly
embedded, non-Type-3". Measured three ways on the same corpus, before
this module was written:

        counting font entries    94.3% embedded          -> fine
        counting DOCUMENTS       16.8% fully clean       -> catastrophic
        counting GLYPHS          95.90% on the fast path -> fine

**Glyph-weighted is the only one that answers U9's question**, because
the fast path applies per glyph. A paper with twenty fonts of which one
is an unused non-embedded Helvetica is not a paper U9 fails on. 80.7% of
documents contain some non-embedded font; that number is true and nearly
meaningless.

`coverage()` therefore counts glyph instances and nothing else, and
reports raw counts beside the fraction so a small denominator is visible
rather than hidden behind a percentage.

Name resolution is a real failure mode, not tidiness
----------------------------------------------------
pdfminer reports `CKXQCW+LMRoman10-Regular` where `pdffonts` reports
`CKXQCW+LMRoman10-Regular-Identity-H`: the same embedded font, failing to
join on an encoding suffix. Measured in the corpus. `resolve()` matches
on the normalised name -- subset tag stripped, encoding suffix stripped,
style suffix preserved because `Times,Bold` and `Times,Italic` are
genuinely different fonts.

Parsing is fixed-width, deliberately
------------------------------------
`pdffonts` emits a dashed rule line whose segment widths ARE the column
widths. Splitting on whitespace loses every font whose name or type
contains a space -- `New Roman TrueType`, `Mincho Pr6N R-4520-Identity-H
CID Type 0C` -- both of which occur in the corpus. The rule line is
parsed and used.

Guarantees
----------
G1  `parse_pdffonts` runs no subprocess; it is pure text in, records out,
    which is what makes every guarantee below hermetically testable
G2  column boundaries come from the dashed rule line, so names and types
    containing spaces survive
G3  `normalise` strips a 6-letter subset tag and a known encoding suffix,
    and preserves style suffixes -- `,Bold` is not noise
G4  `resolve` matches on the normalised name, so the corpus's
    `-Identity-H` mismatch joins
G5  usability is decided by the stated scope limit -- embedded,
    non-Type-3 -- and an unresolvable name is NEVER silently treated as
    usable; it gets its own class
G6  `coverage` is glyph-weighted and reports counts beside fractions
G7  every rejection names its reason, so a coverage report can be acted
    on rather than only totalled

Non-guarantees (out of scope for this module)
---------------------------------------------
  * **no rasterization.** No CFF or TrueType outline parsing, no
    scan conversion, no reference blob. That is the other half of the
    plan's U9 and needs its own contract and its own premise check.
  * no OpenType BASE or MATH table access -- same reason
  * no PDF parsing. `pdffonts` identifies the fonts, exactly as the plan
    specifies; this module reads what it says.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping

__all__ = ["FontKind", "FontRecord", "Usability", "Coverage",
           "parse_pdffonts", "inventory", "normalise", "resolve",
           "usability", "coverage", "PdfFontsUnavailable"]


class PdfFontsUnavailable(RuntimeError):
    """the pdffonts binary is missing or failed."""


class FontKind(Enum):
    TYPE1 = "Type 1"
    TYPE1C = "Type 1C"
    TRUETYPE = "TrueType"
    CID_TRUETYPE = "CID TrueType"
    CID_TYPE0 = "CID Type 0"
    CID_TYPE0C = "CID Type 0C"
    TYPE3 = "Type 3"
    OTHER = "other"

    @classmethod
    def parse(cls, text: str) -> "FontKind":
        """Longest match wins: `CID Type 0C` must not read as
        `CID Type 0`."""
        t = text.strip()
        for k in sorted(cls, key=lambda k: -len(k.value)):
            if k is cls.OTHER:
                continue
            if t == k.value or t.endswith(" " + k.value):
                return k
        return cls.OTHER

    @property
    def is_outline(self) -> bool:
        """Type 3 glyphs are arbitrary content streams, not outlines."""
        return self is not FontKind.TYPE3 and self is not FontKind.OTHER


class Usability(Enum):
    """Why a glyph is or is not on U9's fast path. Every rejection names
    its reason (G7)."""
    FAST_PATH = "embedded outline"
    NOT_EMBEDDED = "not embedded"
    TYPE3 = "Type 3"
    UNRESOLVED = "font name unresolvable"

    @property
    def usable(self) -> bool:
        return self is Usability.FAST_PATH


@dataclass(frozen=True, slots=True)
class FontRecord:
    name: str
    kind: FontKind
    encoding: str
    embedded: bool
    subset: bool
    unicode_ok: bool

    @property
    def base_name(self) -> str:
        return normalise(self.name)

    @property
    def usability(self) -> Usability:
        if self.kind is FontKind.TYPE3:
            return Usability.TYPE3
        if not self.embedded:
            return Usability.NOT_EMBEDDED
        return Usability.FAST_PATH


# A subset tag is exactly six uppercase letters then '+'.
_SUBSET = re.compile(r"^[A-Z]{6}\+")

# Encoding suffixes pdffonts appends that pdfminer does not report.
# Style suffixes such as ',Bold' are NOT here: those are different fonts.
_ENCODING_SUFFIX = re.compile(
    r"-(?:Identity-H|Identity-V|UniGB-UCS2-H|UniCNS-UCS2-H|UniJIS-UCS2-H|"
    r"UniKS-UCS2-H|WinAnsiEncoding|MacRomanEncoding)$")


def normalise(name: str) -> str:
    """Strip a subset tag and a known encoding suffix (G3).

    Style suffixes are preserved: `Times,Bold` and `Times,Italic` really
    are different fonts and must not collapse together.
    """
    n = _SUBSET.sub("", name.strip())
    prev = None
    while prev != n:
        prev = n
        n = _ENCODING_SUFFIX.sub("", n)
    return n


def parse_pdffonts(text: str) -> list[FontRecord]:
    """Parse `pdffonts` output. No subprocess (G1).

    Column boundaries come from the dashed rule line (G2), because
    splitting on whitespace loses every name or type containing a space
    and the corpus contains both.
    """
    lines = [L.rstrip("\n") for L in text.splitlines()]
    rule = next((i for i, L in enumerate(lines)
                 if L.strip() and set(L.strip()) <= {"-", " "}), None)
    if rule is None:
        return []

    spans = []
    for mt in re.finditer(r"-+", lines[rule]):
        spans.append((mt.start(), mt.end()))
    if len(spans) < 4:
        return []

    out: list[FontRecord] = []
    for L in lines[rule + 1:]:
        if not L.strip():
            continue
        cell = [L[a:b].strip() if a < len(L) else "" for a, b in spans]
        name = cell[0]
        if not name:
            continue
        # widths are minimums: a long name can push later columns right,
        # so fall back to a whitespace split when a flag cell is not a
        # yes/no.
        if len(cell) < 6 or cell[3] not in ("yes", "no"):
            tok = L.split()
            flags = [i for i, c in enumerate(tok) if c in ("yes", "no")]
            if len(flags) < 3:
                continue
            i = flags[0]
            name = tok[0]
            kind_text = " ".join(tok[1:i - 1]) if i > 2 else tok[1]
            enc = tok[i - 1] if i >= 2 else ""
            emb, sub, uni = tok[i], tok[i + 1], tok[i + 2]
        else:
            kind_text, enc, emb, sub, uni = cell[1], cell[2], cell[3], \
                cell[4], cell[5]
        out.append(FontRecord(name, FontKind.parse(kind_text), enc,
                              emb == "yes", sub == "yes", uni == "yes"))
    return out


def inventory(pdf_path, *, timeout: float = 60.0) -> list[FontRecord]:
    """Run `pdffonts` and parse it. The only subprocess in this module."""
    try:
        proc = subprocess.run(["pdffonts", str(pdf_path)],
                              capture_output=True, text=True,
                              timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PdfFontsUnavailable(f"pdffonts failed on {pdf_path}: "
                                  f"{exc!r}") from None
    if proc.returncode != 0:
        raise PdfFontsUnavailable(
            f"pdffonts exited {proc.returncode} on {pdf_path}: "
            f"{proc.stderr.strip()[:200]}")
    return parse_pdffonts(proc.stdout)


def resolve(name: str,
            records: Iterable[FontRecord]) -> FontRecord | None:
    """Find the record for a glyph's font name (G4).

    Exact match first, then normalised. The normalised pass is what joins
    pdfminer's `…-Regular` to pdffonts' `…-Regular-Identity-H`.
    """
    recs = list(records)
    for r in recs:
        if r.name == name:
            return r
    target = normalise(name)
    for r in recs:
        if r.base_name == target:
            return r
    return None


def usability(name: str, records: Iterable[FontRecord]) -> Usability:
    """Whether a glyph with this font name is on U9's fast path (G5).

    An unresolvable name gets its own class and is never counted as
    usable -- the corpus's `'unknown'` fonts would otherwise inflate the
    fast-path share by several points.
    """
    rec = resolve(name, records)
    return rec.usability if rec is not None else Usability.UNRESOLVED


@dataclass(slots=True)
class Coverage:
    """Glyph-weighted coverage (G6). Counts, not just fractions."""
    counts: dict[Usability, int]

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    @property
    def usable(self) -> int:
        return self.counts.get(Usability.FAST_PATH, 0)

    @property
    def fraction(self) -> float:
        return self.usable / self.total if self.total else 0.0

    def rejected(self) -> dict[Usability, int]:
        """Every rejection with its reason, so a report can be acted on
        rather than only totalled (G7)."""
        return {k: v for k, v in self.counts.items()
                if not k.usable and v}

    def report(self) -> str:
        if not self.total:
            return "no glyphs"
        lines = [f"{self.usable}/{self.total} ({self.fraction:.2%}) "
                 f"on the fast path"]
        for k, v in sorted(self.rejected().items(),
                           key=lambda kv: -kv[1]):
            lines.append(f"  {v:8} ({v/self.total:6.2%})  {k.value}")
        return "\n".join(lines)


def coverage(font_names: Iterable[str],
             records: Iterable[FontRecord]) -> Coverage:
    """Glyph-weighted coverage over one glyph font name per instance.

    Pass one name PER GLYPH, not per distinct font -- that difference is
    the whole finding recorded in docs/units.md §3 "U9 premise check".
    """
    recs = list(records)
    cache: dict[str, Usability] = {}
    counts: dict[Usability, int] = {}
    for n in font_names:
        u = cache.get(n)
        if u is None:
            u = usability(n, recs)
            cache[n] = u
        counts[u] = counts.get(u, 0) + 1
    return Coverage(counts)
