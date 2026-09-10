"""authordiff.py -- MathPix's LaTeX against the AUTHOR'S LaTeX, directly.

Every measurement in out/639-646 compared our render of MathPix's
LaTeX against the ink. That needs a rasteriser, a scale estimate and a
placement, and each of those has been wrong at least once. Most arXiv
documents ship their source, so a third comparison is available with
none of that machinery in between: what the author WROTE against what
MathPix SAYS they wrote.

    census    token counts over both sources, per document
    geometry  does a substitution change the RENDERED INK at all?

THE SECOND HALF IS WHAT MAKES THE FIRST USEFUL. A token ratio says
MathPix writes something else; it does not say the page looks
different. `\\operatorname{det}` for `\\det` is the most substituted
token in the corpus and renders to identical ink, so it can never
produce a residual and must never be flagged as one.

NOT AN ALIGNED COMPARISON. The census counts tokens over whole
documents. It cannot say a given expression was changed, only that one
source uses a construct the other does not. Per-expression alignment
needs the evidence table, and only 7 of 389 pairs have one.

    python3 tools/authordiff.py census
    python3 tools/authordiff.py geometry
"""
from __future__ import annotations

import argparse
import collections
import gzip
import io
import pathlib
import re
import subprocess
import sys
import tarfile
import tempfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

#: token -> regex. Chosen because each has a plain-LaTeX counterpart an
#: author would write instead; `geometry` below pairs them up.
CLASSES = {
    r"\left(": r"\\left\(",
    r"\boldsymbol{": r"\\boldsymbol\{",
    r"\operatorname{": r"\\operatorname\{",
    r"{ }^{": r"\{\s*\}\^\{",
    r"\mathfrak{": r"\\mathfrak\{",
    r"\left\{": r"\\left\\\{",
    r"\mid": r"\\mid\b",
    r"\quad": r"\\quad\b",
    r"\stackrel": r"\\stackrel\b",
    r"\cdots": r"\\cdots\b",
}

#: (label, as MathPix writes it, as an author would). The author forms
#: are taken from real corpus source, not invented -- `{}^tA` and
#: `\, | \,` are both idioms of 0902.0431's SpEcxp.tex.
PAIRS = [
    ("{ }^{ } prescript", r"\tau\left({ }^{t} A\right) A=E", r"\tau({}^tA)A = E"),
    (r"\operatorname", r"\operatorname{det} A=1", r"\det A = 1"),
    (r"\left(", r"\left(x+y\right) z", r"(x+y) z"),
    (r"\left\{", r"\left\{x \in V\right\}", r"\{x \in V\}"),
    (r"\mid", r"\{x \in V \mid f(x)=x\}", r"\{x \in V \, | \, f(x) = x\}"),
    (r"\boldsymbol", r"\boldsymbol{R}^{n}", r"\mathbf{R}^n"),
    (r"\cdots", r"a_{1}, \cdots, a_{7}", r"a_1, \cdots, a_7"),
]


def author_tex(p):
    """The author's LaTeX out of a `.tgz`.

    arXiv e-prints come both ways and the file extension lies about
    which: 29 of 389 are a gzip of ONE `.tex` and the rest are real
    tarballs, so the ustar magic decides rather than the name. Every
    `.tex` member is concatenated -- a paper split across files would
    otherwise be counted as whatever happens to be first.
    """
    try:
        raw = gzip.decompress(p.read_bytes())
    except Exception:
        return None
    if raw[257:262] == b"ustar":
        try:
            tf = tarfile.open(fileobj=io.BytesIO(raw))
            t = [m for m in tf.getmembers() if m.name.endswith(".tex")]
            if not t:
                return None
            return b"\n".join(tf.extractfile(m).read()
                              for m in t).decode("utf-8", "replace")
        except Exception:
            return None
    return raw.decode("utf-8", "replace")


def mathpix_tex(p):
    try:
        z = zipfile.ZipFile(p)
        n = [x for x in z.namelist() if x.endswith(".tex")]
        return z.read(n[0]).decode("utf-8", "replace") if n else None
    except Exception:
        return None


def pairs_in(library):
    return sorted(d for d in library.iterdir() if d.is_dir()
                  and list(d.glob("*.tgz")) and list(d.glob("*.tex.zip")))


def census(library):
    docs = pairs_in(library)
    agg = {k: dict(a=0, m=0, docs_m=0, intro=0) for k in CLASSES}
    n = 0
    for d in docs:
        a = author_tex(list(d.glob("*.tgz"))[0])
        m = mathpix_tex(list(d.glob("*.tex.zip"))[0])
        if a is None or m is None:
            continue
        n += 1
        for k, pat in CLASSES.items():
            ca, cm = len(re.findall(pat, a)), len(re.findall(pat, m))
            agg[k]["a"] += ca
            agg[k]["m"] += cm
            agg[k]["docs_m"] += bool(cm)
            agg[k]["intro"] += bool(cm and not ca)
    print(f"{n} document pairs of {len(docs)} readable\n")
    print(f"{'token':<18} {'author':>8} {'mathpix':>9} {'ratio':>7} "
          f"{'docs':>6} {'author never':>13}")
    for k in sorted(CLASSES, key=lambda k: -(agg[k]["m"] - agg[k]["a"])):
        v = agg[k]
        r = f"{v['m']/v['a']:>7.1f}" if v["a"] else "    inf"
        print(f"{k:<18} {v['a']:>8} {v['m']:>9} {r} {v['docs_m']:>6} "
              f"{v['intro']:>13}")
    return 0


def geometry():
    from tools.formulafind import blobs, render
    print(f"{'class':<20} {'mathpix':>8} {'author':>7} {'delta':>7} "
          f"{'%':>7}  verdict")
    with tempfile.TemporaryDirectory() as td:
        t = pathlib.Path(td)
        for name, mp, au in PAIRS:
            got = []
            for i, s in enumerate((mp, au)):
                if not render(s, t / f"{i}.pgm", 600):
                    got.append(None)
                    continue
                m, b = blobs(t / f"{i}.pgm", 600.0)
                got.append((max(x[1] for x in b) - min(x[0] for x in b) + 1,
                            len(b), m.data.count(255)))
            if None in got:
                print(f"{name:<20} render failed")
                continue
            (wm, bm, im), (wa, ba, ia) = got
            d = wm - wa
            verdict = ("identical ink" if (d == 0 and bm == ba and im == ia)
                       else ("GEOMETRIC" if d else "same width, other glyphs"))
            print(f"{name:<20} {wm:>8} {wa:>7} {d:>+7} {100*d/wa:>+6.1f}%  "
                  f"{verdict}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("census", "geometry"))
    ap.add_argument("--library", type=pathlib.Path,
                    default=pathlib.Path.home() / "pdfdrill-library")
    a = ap.parse_args()
    return census(a.library) if a.mode == "census" else geometry()


if __name__ == "__main__":
    raise SystemExit(main())
