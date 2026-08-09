"""type1.py -- Type 1 font programs: eexec, charstrings, encoding.

CONTRACT (written before implementation; see docs/units.md U9)
=============================================================

Why this format, and why from disk
----------------------------------
This is the first half of U9's rasterizer -- getting from a font to the
bytes that describe a glyph's outline. `measure.py outlines` decided both
halves of that sentence before a line was written, and the joint
distribution overturned what the marginals implied.

Measured over GLYPH INSTANCES (not font entries, not documents) in 30
sampled corpus documents, restricted to maths families:

    format the PDF embedded      48.13% Type 1C, 46.48% Type 1
    format the SAME font has     94.61% resolve to a `.pfb` in the
    on disk in the TeX tree      TeX tree -- Type 1, all of it
    /FontFile* reachable         20/30 documents

Read only the first row and the plan is "a CFF interpreter and a Type 1
interpreter, behind a PDF extractor with an object-stream decoder". Read
the joint and it is one parser and no PDF handling at all: the TeX tree
ships Type 1 `.pfb` even for the fonts a producer embedded as Type 1C,
because the producer converted at embed time. Subsetting removes glyphs;
it does not alter the outlines of the glyphs that remain, so the on-disk
outline IS the embedded outline for every glyph the page actually used.

So this module reads Type 1 only, from a file, and knows nothing about
PDF. CFF is not a fallback that was skipped -- on this route it is not
reachable, and the 5.39% that route B misses is named rather than
hidden: LibertinusMath and Cambria Math, non-TeX OpenType maths fonts.

The dependency this creates, stated rather than assumed
------------------------------------------------------
94.61% is measured against ONE machine's TeX tree. On a machine without
`texmf-dist` it is 0%. That is a deployment constraint, not a detail, so
this module never searches for a font: the caller supplies the path, and
a missing font is the caller's own class to report. `FontNotType1` is
raised for a file that is not a Type 1 program, so a `.otf` handed in by
mistake fails loudly instead of yielding plausible garbage.

The oracle: how a charstring opens, not a golden file
-----------------------------------------------------
A Type 1 charstring sets the side bearing and width before any path
operator, so it opens with `hsbw` or `sbw`. That is what validates this
parser across every glyph of every font on the machine WITHOUT a
recorded output: a wrong charstring length, a wrong `lenIV`, a misplaced
binary offset or a wrong key all produce bytes that decode as something
else. `first_ops()` reports it.

It reports four CLASSES rather than a pass rate, because the first two
attempts at this oracle were both too strict and both looked like parser
bugs:

    a two-class rate read 88.33% over the TeX tree. The gap was `div`.
    cm-super writes every width as `<num> <den> div hsbw`, and `div` is
    12-12 -- below 32, like a command. Counting it as one declares all
    585 charstrings of a correct font broken.

    the fixed rate read 97.86%. The gap was SUBROUTINIZATION. Roboto,
    Tinos and Cascadia hold the hsbw inside a subr, so 436 of
    Roboto-Black's 1250 glyphs correctly open `n callsubr`. That class
    cannot be verified without the interpreter, and calling it a failure
    or calling it a pass would both be assertions.

So `callsubr` is its own class, deferred and counted; the class that
must be empty is `cmd<n>`, a path operator where the width belongs.
Both corrections were the instrument, not the parser -- which is the
argument for reporting the residual instead of one number.

The second oracle is that encryption is invertible. `encrypt` is exposed
beside `decrypt` for exactly that reason: a round trip is a test rather
than a claim, and it also lets the hermetic suite BUILD a real Type 1
font in memory rather than commit a binary fixture.

What is read from the font rather than assumed
----------------------------------------------
Three constants differ between real fonts and every one of them has bitten
implementations that hardcoded it:

    lenIV       the charstring decryption skip. Defaults to 4 and is
                usually 4, but `/lenIV 0` fonts exist and every
                charstring in one would lose its first four bytes --
                which is to say its `hsbw` -- silently.
    RD / -|     the operator naming the binary read. A font DEFINES this
                name in its own private dict; `RD` and `-|` are both
                common. Matching one literal loses every font using the
                other, entirely, with no error.
    FontMatrix  the units-per-em scale. 0.001 in nearly all Type 1
                fonts, and not guaranteed.

Guarantees
----------
G1  pure bytes in, structures out -- no subprocess, no network, no font
    search. Everything below is hermetically testable
G2  PFB (segmented binary) and PFA/raw (hex eexec) yield IDENTICAL
    charstrings for the same font; the wrapper is not part of the answer
G3  the binary-read operator name is taken from the font, not assumed,
    so `-|` fonts and `RD` fonts both parse
G4  `lenIV` is read from the private dict, defaulting to 4 only when the
    font does not state it
G5  `encrypt` and `decrypt` are exact inverses, which is asserted rather
    than argued
G6  a file that is not a Type 1 program raises `FontNotType1`; it never
    returns a partially-parsed font
G7  the builtin encoding is returned as code -> glyph name, and
    `StandardEncoding` is recognised by name rather than silently
    yielding an empty map
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

__all__ = [
    "FontNotType1", "Type1Font", "decrypt", "encrypt", "load", "parse",
    "STANDARD_ENCODING",
]


class FontNotType1(ValueError):
    """The bytes handed in are not a Type 1 font program."""


# --------------------------------------------------------------------------
# eexec
# --------------------------------------------------------------------------

_C1, _C2 = 52845, 22719

# The two keys the Type 1 spec fixes: the private dict, and charstrings.
EEXEC_R = 55665
CHARSTRING_R = 4330


def decrypt(data: bytes, r: int, skip: int) -> bytes:
    """Type 1 eexec decryption, dropping `skip` leading plaintext bytes.

    The dropped bytes are random padding the encryptor prepended; they
    carry no information, which is why `encrypt` is free to choose them.
    """
    out = bytearray(len(data))
    for i, c in enumerate(data):
        out[i] = c ^ (r >> 8)
        r = ((c + r) * _C1 + _C2) & 0xFFFF
    return bytes(out[skip:])


def encrypt(plain: bytes, r: int, skip: int, pad: bytes | None = None) -> bytes:
    """The exact inverse of `decrypt` (G5).

    `pad` supplies the leading bytes `decrypt` will discard; it defaults
    to zeros of exactly the right length, and an explicit one must be at
    least `skip` long. Its content is irrelevant to the result of a
    round trip, which is the point -- the test can pass anything.
    """
    if pad is None:
        pad = bytes(skip)
    if len(pad) < skip:
        raise ValueError(f"pad {len(pad)} shorter than skip {skip}")
    out = bytearray()
    for p in pad[:skip] + plain:
        c = p ^ (r >> 8)
        out.append(c)
        r = ((c + r) * _C1 + _C2) & 0xFFFF
    return bytes(out)


# --------------------------------------------------------------------------
# wrappers: PFB segments, PFA hex
# --------------------------------------------------------------------------

def _split_pfb(raw: bytes):
    """(clear, encrypted) from a segmented PFB, or None if not a PFB."""
    if not raw.startswith(b"\x80"):
        return None
    clear, enc, i = bytearray(), bytearray(), 0
    while i < len(raw) and raw[i] == 0x80:
        kind = raw[i + 1]
        if kind == 3:                       # EOF marker, no length follows
            break
        n = int.from_bytes(raw[i + 2:i + 6], "little")
        body = raw[i + 6:i + 6 + n]
        if len(body) != n:
            raise FontNotType1(f"PFB segment claims {n} bytes, got {len(body)}")
        # Segment type 2 is binary: the eexec portion. Type 1 is ASCII --
        # but that covers BOTH the header before eexec and the 512 zeros
        # after it, so appending every ASCII segment to `clear` would
        # append the trailer as well. Only ASCII seen before any binary
        # segment is the clear-text header.
        if kind == 2:
            enc.extend(body)
        elif not enc:
            clear.extend(body)
        i += 6 + n
    if not enc:
        raise FontNotType1("PFB has no binary segment")
    return bytes(clear), bytes(enc)


_HEX = frozenset(b"0123456789abcdefABCDEF")


def _split_raw(raw: bytes):
    """(clear, encrypted) from an unsegmented PFA/raw font program.

    The eexec portion may be binary or hex; the spec's own test is
    whether the first four bytes after `eexec` are all hex digits, and
    that is the test used here.
    """
    at = raw.find(b"eexec")
    if at < 0:
        raise FontNotType1("no eexec section")
    clear = raw[:at]
    i = at + 5
    while i < len(raw) and raw[i] in b" \t\r\n":
        i += 1
    body = raw[i:]
    if len(body) >= 4 and all(c in _HEX for c in body[:4]):
        hexdigits = bytes(c for c in body if c in _HEX)
        if len(hexdigits) % 2:
            hexdigits = hexdigits[:-1]
        return clear, bytes.fromhex(hexdigits.decode("ascii"))
    return clear, body


# --------------------------------------------------------------------------
# the private dict
# --------------------------------------------------------------------------

# `/name len RD <binary>`. The operator token is captured, never assumed
# (G3), and exactly ONE space separates it from the binary -- so the
# binary offset is `match.end()`, not a search.
_ENTRY = re.compile(rb"/([^\s/{}\[\]()<>]+)[ \t]+(\d+)[ \t]+([^\s]{1,12})[ ]")
_SUBR = re.compile(rb"dup[ \t]+(\d+)[ \t]+(\d+)[ \t]+([^\s]{1,12})[ ]")
_LENIV = re.compile(rb"/lenIV[ \t]+(-?\d+)")
_ENCODING_PUT = re.compile(rb"dup[ \t]+(\d+)[ \t]*/([^\s/{}\[\]()<>]+)[ \t]+put")
_FONTMATRIX = re.compile(rb"/FontMatrix[ \t]*\[([^\]]*)\]")


@dataclass
class Type1Font:
    """A parsed Type 1 font program.

    `charstrings` and `subrs` hold DECRYPTED bytes with the `lenIV`
    prefix already removed, so a consumer never repeats the decryption
    and never has to know `lenIV`.
    """

    charstrings: dict[str, bytes]
    subrs: list[bytes]
    encoding: dict[int, str] = field(default_factory=dict)
    font_matrix: tuple[float, float, float, float, float, float] = \
        (0.001, 0.0, 0.0, 0.001, 0.0, 0.0)
    len_iv: int = 4
    name: str = ""

    @property
    def units_per_em(self) -> float:
        """Charstring units per em, from the FontMatrix x-scale.

        1000 for the usual `[0.001 0 0 0.001 0 0]`. Taken from the font
        because it is not guaranteed (G4's sibling case).
        """
        a = self.font_matrix[0]
        if a == 0:
            raise FontNotType1(f"FontMatrix has zero x-scale: {self.font_matrix}")
        return 1.0 / a

    def first_ops(self) -> "Counter[str]":
        """How each charstring opens, as a count per class -- the
        parser's oracle. See the module docstring.

        Four classes, not a pass rate, because they mean different
        things and averaging them hides the one that matters:

            hsbw, sbw   correct, and verified here
            callsubr    correct pending the interpreter: a subroutinized
                        font holds its hsbw inside subr n, so the
                        charstring legitimately opens with `n callsubr`.
                        436 of Roboto-Black's 1250 glyphs do
            cmd<n>      WRONG -- a real command where the width should
                        be. This is the class a bad length, offset, key
                        or lenIV lands in, and it must be empty
            truncated   the charstring ended inside its arguments

        A wrong parse cannot hide in `callsubr`, because reaching it
        still requires the byte stream to decode as numbers up to that
        point.
        """
        out = Counter()
        for cs in self.charstrings.values():
            # hsbw is 13; sbw is the two-byte escape 12 7. Both follow
            # their arguments, so scan past the number encoding first --
            # and past `div` (12 12), which is a number-PRODUCING operator
            # and legal among those arguments. The whole cm-super family
            # writes its widths as `<num> <den> div hsbw`, so a scanner
            # that stops at the first byte below 32 reads `div` as the
            # first command and reports 585 of 585 charstrings broken in
            # a font that is entirely correct.
            i = 0
            while True:
                if i >= len(cs):
                    out["truncated"] += 1
                    break
                b = cs[i]
                if b >= 32:
                    i += 1 if b <= 246 else (2 if b <= 254 else 5)
                    continue
                if b == 12:
                    if i + 1 >= len(cs):
                        out["truncated"] += 1
                        break
                    if cs[i + 1] == 12:         # div: produces a number
                        i += 2
                        continue
                    out["sbw" if cs[i + 1] == 7 else f"cmd12-{cs[i + 1]}"] += 1
                    break
                out["hsbw" if b == 13 else
                    "callsubr" if b == 10 else f"cmd{b}"] += 1
                break
        return out


def _binary_entries(priv: bytes, start: int, pattern, key):
    """Every `<key> <len> <op> <binary>` entry from `start`, as
    (key, raw_binary). Scanning is sequential from each match's end, so
    a binary body containing something that looks like a header cannot
    produce a phantom entry -- the next search begins past that body.
    """
    out, i = [], start
    while True:
        m = pattern.search(priv, i)
        if not m:
            return out
        n = int(m.group(2))
        body = priv[m.end():m.end() + n]
        if len(body) != n:
            return out
        out.append((key(m), body))
        i = m.end() + n


def parse(raw: bytes, *, name: str = "") -> Type1Font:
    """Parse a Type 1 font program from PFB or PFA/raw bytes (G2, G6)."""
    if not raw:
        raise FontNotType1("empty file")
    clear, enc = _split_pfb(raw) or _split_raw(raw)
    if b"%!" not in clear[:4] and b"%!" not in clear[:64]:
        raise FontNotType1("no PostScript header before eexec")

    priv = decrypt(enc, EEXEC_R, 4)
    m = _LENIV.search(priv)
    len_iv = int(m.group(1)) if m else 4
    if len_iv < 0:
        raise FontNotType1(f"negative lenIV {len_iv}")

    at = priv.find(b"/Subrs")
    subrs: list[bytes] = []
    if at >= 0:
        found = _binary_entries(priv, at, _SUBR, lambda m: int(m.group(1)))
        if found:
            subrs = [b""] * (max(i for i, _ in found) + 1)
            for i, body in found:
                subrs[i] = decrypt(body, CHARSTRING_R, len_iv)

    at = priv.find(b"/CharStrings")
    if at < 0:
        raise FontNotType1("no /CharStrings in the private dict")
    # Start past `/CharStrings <n> dict dup begin`, not at it: that header
    # is itself of the form `/name <number> <token> `, so scanning from
    # `at` parses the section header as a glyph called `CharStrings`
    # whose body is the next two bytes -- inflating every count by one
    # and shifting nothing else, which is why it survives a smoke test.
    begin = priv.find(b"begin", at)
    charstrings = {
        gname.decode("latin-1"): decrypt(body, CHARSTRING_R, len_iv)
        for gname, body in _binary_entries(
            priv, begin + 5 if begin > at else at + 12,
            _ENTRY, lambda m: m.group(1))
    }
    if not charstrings:
        raise FontNotType1("/CharStrings present but empty")

    return Type1Font(charstrings=charstrings, subrs=subrs,
                     encoding=_encoding(clear), font_matrix=_matrix(clear),
                     len_iv=len_iv, name=name or _fontname(clear))


def _encoding(clear: bytes) -> dict[int, str]:
    """code -> glyph name from the clear-text header (G7)."""
    at = clear.find(b"/Encoding")
    if at < 0:
        return {}
    head = clear[at:at + 40]
    if b"StandardEncoding" in head:
        return dict(STANDARD_ENCODING)
    return {int(m.group(1)): m.group(2).decode("latin-1")
            for m in _ENCODING_PUT.finditer(clear, at)}


def _matrix(clear: bytes):
    m = _FONTMATRIX.search(clear)
    if not m:
        return (0.001, 0.0, 0.0, 0.001, 0.0, 0.0)
    try:
        vals = [float(t) for t in m.group(1).split()]
    except ValueError:
        return (0.001, 0.0, 0.0, 0.001, 0.0, 0.0)
    if len(vals) != 6:
        return (0.001, 0.0, 0.0, 0.001, 0.0, 0.0)
    return tuple(vals)


def _fontname(clear: bytes) -> str:
    m = re.search(rb"/FontName[ \t]*/([^\s/{}\[\]()<>]+)", clear)
    return m.group(1).decode("latin-1") if m else ""


def load(path, *, name: str = "") -> Type1Font:
    """Parse the Type 1 font program at `path`.

    No searching: the caller decides which file this is (see the module
    docstring on why the TeX-tree dependency is the caller's to state).
    """
    import pathlib
    p = pathlib.Path(path)
    return parse(p.read_bytes(), name=name or p.stem)


# The Adobe StandardEncoding, needed because a font may name it instead
# of listing 256 `dup ... put` lines (G7). Only the occupied codes are
# listed; absent codes are unmapped, which is the correct answer for
# them rather than a missing one.
STANDARD_ENCODING = {
    32: "space", 33: "exclam", 34: "quotedbl", 35: "numbersign",
    36: "dollar", 37: "percent", 38: "ampersand", 39: "quoteright",
    40: "parenleft", 41: "parenright", 42: "asterisk", 43: "plus",
    44: "comma", 45: "hyphen", 46: "period", 47: "slash",
    48: "zero", 49: "one", 50: "two", 51: "three", 52: "four",
    53: "five", 54: "six", 55: "seven", 56: "eight", 57: "nine",
    58: "colon", 59: "semicolon", 60: "less", 61: "equal", 62: "greater",
    63: "question", 64: "at",
    **{c: chr(c) for c in range(65, 91)},
    91: "bracketleft", 92: "backslash", 93: "bracketright",
    94: "asciicircum", 95: "underscore", 96: "quoteleft",
    **{c: chr(c) for c in range(97, 123)},
    123: "braceleft", 124: "bar", 125: "braceright", 126: "asciitilde",
    161: "exclamdown", 162: "cent", 163: "sterling", 164: "fraction",
    165: "yen", 166: "florin", 167: "section", 168: "currency",
    169: "quotesingle", 170: "quotedblleft", 171: "guillemotleft",
    172: "guilsinglleft", 173: "guilsinglright", 174: "fi", 175: "fl",
    177: "endash", 178: "dagger", 179: "daggerdbl", 180: "periodcentered",
    182: "paragraph", 183: "bullet", 184: "quotesinglbase",
    185: "quotedblbase", 186: "quotedblright", 187: "guillemotright",
    188: "ellipsis", 189: "perthousand", 191: "questiondown",
    193: "grave", 194: "acute", 195: "circumflex", 196: "tilde",
    197: "macron", 198: "breve", 199: "dotaccent", 200: "dieresis",
    202: "ring", 203: "cedilla", 205: "hungarumlaut", 206: "ogonek",
    207: "caron", 208: "emdash", 225: "AE", 227: "ordfeminine",
    232: "Lslash", 233: "Oslash", 234: "OE", 235: "ordmasculine",
    241: "ae", 245: "dotlessi", 248: "lslash", 249: "oslash",
    250: "oe", 251: "germandbls",
}
