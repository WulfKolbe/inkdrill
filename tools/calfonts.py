"""498 -- what actually DRAWS \\mathcal, per document.

231 classified rows by comparing the author's SOURCE TOKEN against
MathPix's. That is the right comparison for a transcription question
and the wrong one for an ink question, because \\mathcal is not a
glyph -- it is a name bound to whatever math alphabet the preamble
installed. A document loading `mathdesign` or `mathptmx` writes
\\mathcal and draws an ornate chancery script; a document loading
nothing draws Computer Modern's plain calligraphic.

So before any ink check can read a \\mathcal, this counts how often
the corpus rebinds it. The package list is the one that ships a
replacement math alphabet or redeclares the symbol font directly; it
is a NAMED LIST rather than a heuristic, so a reader can see what it
misses.
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import re
import tarfile

#: packages that install a math alphabet set, hence redraw \mathcal
REBINDS = ("mathdesign", "mathptmx", "txfonts", "newtxmath", "pxfonts",
           "newpxmath", "fourier", "kpfonts", "libertinust1math",
           "mathpazo", "mathtime", "mtpro2", "eulervm", "concmath",
           "arev", "cmbright", "stix", "stix2", "unicode-math",
           "XCharter", "notomath", "erewhon")
#: explicit rebindings of the alphabet itself
EXPLICIT = (r"\\DeclareMathAlphabet\s*\{?\\mathcal",
            r"\\renewcommand\s*\{?\\mathcal",
            r"\\usepackage\s*\[[^]]*\bmathcal\b[^]]*\]\s*\{eu(script|cal)\}",
            r"\\usepackage\s*\{eucal\}")
_USE = re.compile(r"\\usepackage\s*(\[[^]]*\])?\s*\{([^}]*)\}")


def preamble_of(tgz: pathlib.Path) -> str:
    """Every .tex in the e-print, concatenated. Not just the main file:
    a preamble is routinely split into a style file, and 231's own
    1808.07302 nearly fell out of its class because macros were read
    from one file and uses from another."""
    out = []
    try:
        with tarfile.open(tgz) as tf:
            for mem in tf.getmembers():
                if not mem.isfile() or not mem.name.lower().endswith(
                        (".tex", ".sty", ".cls")):
                    continue
                if mem.size > 4_000_000:
                    continue
                f = tf.extractfile(mem)
                if f is None:
                    continue
                out.append(f.read().decode("utf8", "replace"))
    except Exception:
        return ""
    return "\n".join(out)


def classify(text: str):
    """(verdict, evidence). `cm` means nothing found that rebinds it."""
    if not text:
        return "unreadable", ""
    for pat in EXPLICIT:
        m = re.search(pat, text)
        if m:
            return "rebound", m.group(0)[:60]
    for m in _USE.finditer(text):
        for pkg in (p.strip() for p in m.group(2).split(",")):
            if pkg in REBINDS:
                return "rebound", pkg
    return "cm", ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--library", type=pathlib.Path,
                    default=pathlib.Path.home() / "pdfdrill-library")
    ap.add_argument("--min-cal", type=int, default=25)
    ap.add_argument("-o", type=pathlib.Path)
    args = ap.parse_args()
    tally = collections.Counter()
    rows = ["doc\tverdict\tevidence\tn_mathcal\tn_mathscr"]
    for d in sorted(args.library.iterdir()):
        if not d.is_dir():
            continue
        lj = next(d.glob("*.lines.json"), None)
        tgz = next(d.glob("*.tgz"), None)
        if lj is None or tgz is None:
            continue
        try:
            s = lj.read_text()
        except Exception:
            continue
        nc, ns = s.count("mathcal"), s.count("mathscr")
        if nc + ns < args.min_cal:
            continue
        v, ev = classify(preamble_of(tgz))
        tally[v] += 1
        rows.append(f"{d.name}\t{v}\t{ev}\t{nc}\t{ns}")
    print(f"documents with >= {args.min_cal} script mentions in lines.json "
          f"AND an author e-print: {sum(tally.values())}")
    for k, v in tally.most_common():
        print(f"   {k:<11} {v:5d}  {100*v/sum(tally.values()):5.1f}%")
    if args.o:
        args.o.write_text("\n".join(rows) + "\n")
        print(f"{len(rows)-1} rows -> {args.o}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
