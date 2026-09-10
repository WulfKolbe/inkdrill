"""alignlatex.py -- match each MathPix expression to the author's own.

out/648's census counts constructs over whole documents, so it can say
one source uses `\\operatorname{` and the other does not, and cannot say
WHICH expression was changed. This aligns them.

HOW A ROW IS MATCHED, AND WHY THE LADDER IS THE MEASUREMENT. Both
sides are normalised and matched on the result. Normalisation is what
decides the answer, so it is not applied as one lump: each construct
class is a separate rule, and the harness reports the match rate with
ALL rules on, then again with each rule LEFT OUT in turn. The rows
that stop matching when rule C is removed are exactly the rows where
MathPix substituted C -- an aligned, per-expression count, obtained
without ever asserting that a particular row was changed.

A rule that removes nothing is reported too. `\\cdots` is in the list
precisely because out/648 measured it at 1.1x, so it should contribute
nothing, and a leave-one-out that gives it a large share would mean
the ladder is measuring itself.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.authordiff import author_tex                    # noqa: E402
from tools.formulafind import rows                         # noqa: E402

#: name -> (pattern, replacement). Each undoes ONE MathPix habit.
RULES = {
    "left/right":   (r"\\left|\\right", ""),
    "operatorname": (r"\\operatorname\s*\{([^{}]*)\}", r"\\\1"),
    "empty group":  (r"\{\s*\}", ""),
    "spacing":      (r"\\[,;!:]|\\quad\b|\\qquad\b|~", ""),
    "mid":          (r"\\mid\b", "|"),
    "cdots":        (r"\\cdots\b", r"\\dots"),
    "braces":       (r"\{([A-Za-z0-9])\}", r"\1"),
}


def norm(s, skip=()):
    s = s.strip()
    for name, (pat, rep) in RULES.items():
        if name in skip:
            continue
        s = re.sub(pat, rep, s)
    return re.sub(r"\s+", "", s)


def _brace_body(s, i):
    """The `{...}` starting at `i`, with nesting respected."""
    if i >= len(s) or s[i] != "{":
        return None, i
    d, j = 0, i
    while j < len(s):
        if s[j] == "{" and (j == 0 or s[j-1] != "\\"):
            d += 1
        elif s[j] == "}" and s[j-1] != "\\":
            d -= 1
            if d == 0:
                return s[i+1:j], j + 1
        j += 1
    return None, i


def expand_macros(text, passes=3):
    """Expand the author's own no-argument macros.

    NOT COSMETIC. 0902.0431 defines 149 of them -- backslash-ga for alpha
    and
    so on -- and that document is 56% of the aligned sample. MathPix
    reads the PAGE, so it emits the expansion; the author's file holds
    the shorthand. Comparing them without expanding measures the
    author's macro habits, not MathPix's substitutions.
    """
    macros = {}
    for m in re.finditer(r"\\def\s*\\(\w+)\s*\{", text):
        body, _ = _brace_body(text, m.end() - 1)
        if body is not None and len(body) < 200:
            macros[m.group(1)] = body
    for m in re.finditer(r"\\newcommand\s*\{?\s*\\(\w+)\s*\}?\s*\{", text):
        body, _ = _brace_body(text, m.end() - 1)
        if body is not None and len(body) < 200:
            macros.setdefault(m.group(1), body)
    if not macros:
        return text, 0
    rx = re.compile(r"\\(" + "|".join(sorted(macros, key=len, reverse=True))
                    + r")(?![a-zA-Z])")
    for _ in range(passes):
        new = rx.sub(lambda m: macros[m.group(1)], text)
        if new == text:
            break
        text = new
    return text, len(macros)


def author_math(text):
    """Every inline and display expression in the author's source."""
    out = []
    for m in re.finditer(r"\$\$(.+?)\$\$|\$(.+?)\$|\\\[(.+?)\\\]", text, re.S):
        g = m.group(1) or m.group(2) or m.group(3)
        if g and len(g) < 4000:
            out.append(g)
    for env in ("equation", "align", "eqnarray", "gather"):
        out += re.findall(r"\\begin\{" + env + r"\*?\}(.+?)\\end\{" + env
                          + r"\*?\}", text, re.S)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--library", type=pathlib.Path,
                    default=pathlib.Path.home() / "pdfdrill-library")
    ap.add_argument("--docs", default="")
    a = ap.parse_args()
    lib = a.library
    want = {x.strip() for x in a.docs.split(",") if x.strip()}
    docs = sorted(d for d in lib.iterdir() if d.is_dir()
                  and list(d.glob("*.tgz"))
                  and (d / "evidence-formula.tex").exists()
                  and (not want or d.name in want))

    print("macros are expanded in the author source before matching\n")
    print(f"{'document':<14} {'rows':>6} {'raw':>7} {'full':>7}   "
          + "  ".join(f"{k[:9]:>9}" for k in RULES))
    tot = {k: 0 for k in RULES}
    tot_rows = tot_raw = tot_full = 0
    for d in docs:
        src = author_tex(list(d.glob("*.tgz"))[0])
        if src is None:
            print(f"{d.name:<14} source unreadable")
            continue
        src, nmac = expand_macros(src)
        mp = [r["math"] for r in rows(d / "evidence-formula.tex")]
        au = author_math(src)
        idx_full = {norm(x) for x in au}
        raw = sum(1 for x in mp if re.sub(r"\s+", "", x)
                  in {re.sub(r"\s+", "", y) for y in au})
        full = sum(1 for x in mp if norm(x) in idx_full)
        share = {}
        for k in RULES:
            idx = {norm(x, skip=(k,)) for x in au}
            share[k] = full - sum(1 for x in mp if norm(x, skip=(k,)) in idx)
            tot[k] += share[k]
        tot_rows += len(mp); tot_raw += raw; tot_full += full
        print(f"{d.name:<14} {len(mp):>6} {raw:>7} {full:>7}   "
              + "  ".join(f"{share[k]:>9}" for k in RULES))
    print(f"\n{'TOTAL':<14} {tot_rows:>6} {tot_raw:>7} {tot_full:>7}   "
          + "  ".join(f"{tot[k]:>9}" for k in RULES))
    if tot_rows:
        print(f"\nmatched verbatim {100*tot_raw/tot_rows:.1f}%  ->  "
              f"after normalisation {100*tot_full/tot_rows:.1f}%")
        print("per-rule columns are rows that STOP matching when that one "
              "rule is left out")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
