"""Find equation rows whose LAST maths token is a ring command."""
import re, pathlib, json, sys, collections
LIB = pathlib.Path.home()/"pdfdrill-library"
UNSLASHED = [r"\\mathbb\{O\}", r"\\bigcirc", r"\\circ", r"\\mathrm\{O\}", r"(?<![A-Za-z\\])O"]
SLASHED   = [r"\\emptyset", r"\\varnothing", r"\\slashed\{0\}"]
ROW = re.compile(r"\\ident\{([^&\n]*?EQ\d+)\}[^&\n]*& *(\d+) *&(.*?)\\\\ \\hline", re.S)
FIT = re.compile(r"\\FitMath\{\$(.*?)\$\}", re.S)
# trailing text/punctuation LaTeX allows after the last symbol
# Strip only what leaves NO INK AFTER THE TOKEN. The first version
# stripped any trailing \text{...}, which made `\circ \text{ for all
# } x` look as if `\circ` were final -- final in the LaTeX and not in
# the ink, so the rightmost component was a letter and the measurement
# was of the wrong glyph. 8 of 22 unslashed rows were this. Trailing
# text is now stripped only when it contains nothing but punctuation
# and space.
TAIL = re.compile(r"(?:\s|\\[,;!:]|\\quad|\\qquad"
                  r"|\\(?:text|mathrm)\s*\{[\s.,;:]*\}"
                  r"|[.,;:]|\\ |\\\\)*$")
def last_token_class(latex):
    body = latex.strip()
    body = TAIL.sub("", body)
    for pat in SLASHED:
        if re.search(pat + r"\s*$", body): return "slashed", re.search(pat, body).group(0)
    for pat in UNSLASHED:
        if re.search(pat + r"\s*$", body): return "unslashed", re.search(pat, body).group(0)
    return None, None
out = []
docs = 0
for tex in sorted(LIB.glob("*/report.tex")):
    d = tex.parent
    if not (d/"report-crops").is_dir(): continue
    docs += 1
    try: t = tex.read_text(errors="replace")
    except Exception: continue
    for m in ROW.finditer(t):
        f = FIT.search(m.group(3))
        if not f: continue
        cls, tok = last_token_class(f.group(1))
        if cls is None: continue
        ident = m.group(1).replace("\\allowbreak{}","").replace("\\","")
        crop = d/"report-crops"/f"{ident}.jpg"
        if not crop.is_file(): continue
        out.append((str(d.name), ident, cls, tok))
print(f"documents scanned {docs}")
c = collections.Counter(x[2] for x in out)
print("candidate rows:", dict(c))
p = pathlib.Path(sys.argv[1])
p.write_text("\n".join("\t".join(x) for x in out) + "\n")
print("->", p)
