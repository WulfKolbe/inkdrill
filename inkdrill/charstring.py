"""charstring.py -- run a Type 1 charstring, get contours.

CONTRACT (written before implementation; see docs/units.md U9)
=============================================================

This is the second third of U9's rasterizer. `type1.py` gets from a font
file to a glyph's charstring bytes; this runs those bytes and returns
the glyph's outline as closed contours in font units. Scan conversion --
contours to an `InkMask` -- is the remaining piece and is NOT here.

Sized by measurement, not by the spec
-------------------------------------
The Type 1 language has 25 operators. `measure.py charstrings` counted
them over 400 fonts of the TeX tree, 209,550 charstrings and 157,177
subroutines, before this module was written:

    endchar 98%   hsbw 97%   rmoveto 80%   closepath 74%   callsubr 58%
    rrcurveto 54%   rlineto 49%   hlineto 48%   vh/hvcurveto 36%
    div 8.75%   seac 1.89%   callothersubr 0.31%   pop 0.27%
    return 100% OF SUBRS -- and 0% of charstrings, which is how the
    measurement's first population error was caught
    never seen anywhere: dotsection, sbw

Two of the 25 are not switch cases but subsystems, and both are under
2%: `seac` reaches into a second glyph, and `callothersubr` into the
flex and hint-replacement protocol. They are implemented rather than
deferred, because at 1.89% `seac` is every accented character in a
Latin font and skipping it returns a *plausible wrong glyph* -- the
base letter without its accent -- which is precisely the failure mode
this project exists to make impossible.

Hints are parsed and discarded
------------------------------
`hstem`, `vstem`, `hstem3`, `vstem3` and `dotsection` describe stem
alignment for a hinting rasterizer. They carry no outline information,
so they are consumed for their arguments and dropped. That is a
decision, not an omission: their 50% occurrence rate is why the
operator histogram alone does not tell you what to build.

The flex protocol, and why it cannot be ignored
----------------------------------------------
`callothersubr` is the escape into PostScript. Three uses matter:

    OtherSubrs 0   FLEX -- the seven `rmoveto`s preceding it are not
                   moves, they are two curves' control points. Treating
                   them as moves shatters one contour into eight
                   subpaths, so ignoring flex does not lose detail, it
                   produces a *different and broken* outline
    OtherSubrs 1,2 flex bracketing; 1 opens, 2 collects
    OtherSubrs 3   HINT REPLACEMENT -- a genuine no-op for outlines,
                   but it must still leave a subr number on the
                   PostScript stack for the `pop` that follows, or the
                   interpreter desynchronises

So flex is handled and hint replacement is a no-op that still has to
push. `pop` reads from that stack, never from the charstring stack.

Guarantees
----------
G1  pure -- charstrings and subrs in, contours out; no file access, no
    font search, no state between calls
G2  every contour returned is CLOSED: the last point equals the first,
    so a caller never has to guess whether to close it
G3  curves are cubic Beziers, kept as control points rather than
    flattened, so the scan converter chooses its own tolerance
G4  `hsbw`/`sbw` set the left side bearing as the initial point, which
    is what makes a glyph's coordinates comparable across a font
G5  subroutine recursion is bounded and a runaway raises
    `CharstringError` rather than exhausting the interpreter stack
G6  `seac` composes from `STANDARD_ENCODING`, and a component that
    cannot be resolved raises rather than silently yielding the base
    glyph without its accent
G7  an unknown or unimplemented operator raises `CharstringError`
    naming it, so a font outside the measured population fails loudly
    instead of returning a partial outline
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .type1 import STANDARD_ENCODING, Type1Font

__all__ = ["CharstringError", "Glyph", "Segment", "run", "outline"]

MAX_DEPTH = 30


class CharstringError(ValueError):
    """The charstring could not be run to completion."""


@dataclass(frozen=True, slots=True)
class Segment:
    """One path segment. `on` is the endpoint; `c1`/`c2` are the cubic
    control points, both None for a straight line."""
    x: float
    y: float
    c1: tuple[float, float] | None = None
    c2: tuple[float, float] | None = None

    @property
    def is_curve(self) -> bool:
        return self.c1 is not None


@dataclass
class Glyph:
    """A run charstring: closed contours, plus the metrics hsbw set."""
    contours: list[list[Segment]] = field(default_factory=list)
    width: float = 0.0
    sbx: float = 0.0
    sby: float = 0.0

    @property
    def is_empty(self) -> bool:
        return not any(self.contours)

    def bounds(self):
        """(x0, y0, x1, y1) over on-curve and control points.

        Control points are included deliberately: the result is a bound
        the outline is guaranteed to fit inside, which is what a scan
        converter needs to size its buffer. It is not the tight bbox.
        """
        xs, ys = [], []
        for c in self.contours:
            for s in c:
                xs.append(s.x)
                ys.append(s.y)
                for p in (s.c1, s.c2):
                    if p is not None:
                        xs.append(p[0])
                        ys.append(p[1])
        if not xs:
            raise ValueError("bounds of an empty glyph")
        return (min(xs), min(ys), max(xs), max(ys))


class _Runner:
    """One charstring execution. Not reusable -- see G1."""

    def __init__(self, font: Type1Font):
        self.font = font
        self.g = Glyph()
        self.stack: list[float] = []
        self.ps: list[float] = []        # the PostScript operand stack
        self.x = self.y = 0.0
        self.cur: list[Segment] = []
        self.flex: list[tuple[float, float]] | None = None
        self.seac: tuple | None = None

    # -- path building ---------------------------------------------------

    def _close(self):
        """Close the open contour (G2). `closepath` in Type 1 does not
        move the current point, so the caller's position survives."""
        if len(self.cur) > 1:
            first = self.cur[0]
            if (self.cur[-1].x, self.cur[-1].y) != (first.x, first.y):
                self.cur.append(Segment(first.x, first.y))
            self.g.contours.append(self.cur)
        self.cur = []

    def _moveto(self, dx, dy):
        self.x += dx
        self.y += dy
        if self.flex is not None:
            # Inside a flex the moves are control points, not moves.
            self.flex.append((self.x, self.y))
            return
        self._close()
        self.cur = [Segment(self.x, self.y)]

    def _lineto(self, dx, dy):
        self.x += dx
        self.y += dy
        self.cur.append(Segment(self.x, self.y))

    def _curveto(self, dx1, dy1, dx2, dy2, dx3, dy3):
        c1 = (self.x + dx1, self.y + dy1)
        c2 = (c1[0] + dx2, c1[1] + dy2)
        self.x = c2[0] + dx3
        self.y = c2[1] + dy3
        self.cur.append(Segment(self.x, self.y, c1, c2))

    # -- the loop --------------------------------------------------------

    def run(self, code: bytes, depth: int = 0):
        if depth > MAX_DEPTH:
            raise CharstringError(f"subroutine nesting past {MAX_DEPTH}")
        i, n = 0, len(code)
        while i < n:
            b = code[i]
            if b >= 32:                                   # a number
                if b <= 246:
                    self.stack.append(b - 139)
                    i += 1
                elif b <= 250:
                    if i + 1 >= n:
                        raise CharstringError("truncated number")
                    self.stack.append((b - 247) * 256 + code[i + 1] + 108)
                    i += 2
                elif b <= 254:
                    if i + 1 >= n:
                        raise CharstringError("truncated number")
                    self.stack.append(-((b - 251) * 256) - code[i + 1] - 108)
                    i += 2
                else:
                    if i + 4 >= n:
                        raise CharstringError("truncated 32-bit number")
                    v = int.from_bytes(code[i + 1:i + 5], "big", signed=True)
                    self.stack.append(v)
                    i += 5
                continue
            if b == 12:
                if i + 1 >= n:
                    raise CharstringError("truncated escape")
                i += 2
                if self._escape(code[i - 1], depth):
                    return True
                continue
            i += 1
            if self._command(b, depth):
                return True
        return False

    def _command(self, op, depth):
        s = self.stack
        if op == 13:                                       # hsbw
            if len(s) < 2:
                raise CharstringError("hsbw needs 2 arguments")
            self.g.sbx, self.g.width = s[0], s[1]
            self.x, self.y = s[0], 0.0                     # G4
            s.clear()
        elif op == 21:                                     # rmoveto
            self._moveto(s[-2] if len(s) >= 2 else 0.0,
                         s[-1] if len(s) >= 2 else 0.0)
            s.clear()
        elif op == 22:                                     # hmoveto
            self._moveto(s[-1] if s else 0.0, 0.0)
            s.clear()
        elif op == 4:                                      # vmoveto
            self._moveto(0.0, s[-1] if s else 0.0)
            s.clear()
        elif op == 5:                                      # rlineto
            self._lineto(s[0], s[1])
            s.clear()
        elif op == 6:                                      # hlineto
            self._lineto(s[0], 0.0)
            s.clear()
        elif op == 7:                                      # vlineto
            self._lineto(0.0, s[0])
            s.clear()
        elif op == 8:                                      # rrcurveto
            self._curveto(*s[:6])
            s.clear()
        elif op == 30:                                     # vhcurveto
            self._curveto(0.0, s[0], s[1], s[2], s[3], 0.0)
            s.clear()
        elif op == 31:                                     # hvcurveto
            self._curveto(s[0], 0.0, s[1], s[2], 0.0, s[3])
            s.clear()
        elif op == 9:                                      # closepath
            # Does NOT reset the current point, unlike PostScript's.
            if len(self.cur) > 1:
                first = self.cur[0]
                if (self.cur[-1].x, self.cur[-1].y) != (first.x, first.y):
                    self.cur.append(Segment(first.x, first.y))
                self.g.contours.append(self.cur)
                self.cur = [Segment(self.x, self.y)]
            s.clear()
        elif op == 10:                                     # callsubr
            if not s:
                raise CharstringError("callsubr with no subr number")
            k = int(s.pop())
            if not 0 <= k < len(self.font.subrs):
                raise CharstringError(f"subr {k} out of range")
            if self.run(self.font.subrs[k], depth + 1):
                return True
        elif op == 11:                                     # return
            return False
        elif op == 14:                                     # endchar
            self._close()
            return True
        elif op in (1, 3):                                 # hstem, vstem
            s.clear()
        else:
            raise CharstringError(f"unimplemented operator {op}")
        return False

    def _escape(self, op, depth):
        s = self.stack
        if op == 12:                                       # div
            if len(s) < 2:
                raise CharstringError("div needs 2 arguments")
            b = s.pop()
            a = s.pop()
            if b == 0:
                raise CharstringError("div by zero")
            s.append(a / b)
        elif op == 6:                                      # seac
            if len(s) < 5:
                raise CharstringError("seac needs 5 arguments")
            self.seac = tuple(s[:5])
            s.clear()
            self._close()
            return True
        elif op == 7:                                      # sbw
            if len(s) < 4:
                raise CharstringError("sbw needs 4 arguments")
            self.g.sbx, self.g.sby, self.g.width = s[0], s[1], s[2]
            self.x, self.y = s[0], s[1]
            s.clear()
        elif op == 16:                                     # callothersubr
            self._othersubr()
        elif op == 17:                                     # pop
            # Reads the PostScript stack, never the charstring stack.
            s.append(self.ps.pop() if self.ps else 0.0)
        elif op == 33:                                     # setcurrentpoint
            if len(s) >= 2:
                self.x, self.y = s[0], s[1]
            s.clear()
        elif op in (0, 1, 2):                              # dotsection, stem3
            s.clear()
        else:
            raise CharstringError(f"unimplemented escape operator 12 {op}")
        return False

    def _othersubr(self):
        s = self.stack
        if len(s) < 2:
            raise CharstringError("callothersubr needs othersubr# and count")
        idx = int(s.pop())
        cnt = int(s.pop())
        args = [s.pop() for _ in range(min(cnt, len(s)))][::-1]
        if idx == 1:                                       # flex begins
            self.flex = []
        elif idx == 2:                                     # flex collects
            pass
        elif idx == 0:                                     # flex ends
            pts = self.flex or []
            self.flex = None
            # Seven points were gathered; the first is the reference
            # point and the remaining six are two cubics' controls.
            if len(pts) >= 7:
                p = pts[-6:]
                self.cur.append(Segment(p[2][0], p[2][1], p[0], p[1]))
                self.cur.append(Segment(p[5][0], p[5][1], p[3], p[4]))
                self.x, self.y = p[5]
            # The interpreter must leave the end point for two `pop`s.
            self.ps.extend([self.y, self.x])
        elif idx == 3:                                     # hint replacement
            self.ps.append(3)
        else:
            # Unknown OtherSubrs: the spec's own fallback is to push the
            # arguments back for the following pops.
            self.ps.extend(args)


def run(font: Type1Font, code: bytes) -> Glyph:
    """Run one charstring against `font`'s subroutines (G1)."""
    r = _Runner(font)
    r.run(code)
    if r.seac is not None:
        return _compose(font, r)
    if r.cur:
        r._close()
    return r.g


def _compose(font: Type1Font, r: _Runner) -> Glyph:
    """`seac`: an accented character as base plus accent (G6)."""
    asb, adx, ady, bchar, achar = r.seac
    try:
        bname = STANDARD_ENCODING[int(bchar)]
        aname = STANDARD_ENCODING[int(achar)]
    except KeyError as exc:
        raise CharstringError(f"seac names an unencoded code: {exc}") from None
    if bname not in font.charstrings or aname not in font.charstrings:
        raise CharstringError(
            f"seac needs {bname!r} and {aname!r}; font has "
            f"{bname in font.charstrings}/{aname in font.charstrings}")
    base = run(font, font.charstrings[bname])
    acc = run(font, font.charstrings[aname])
    # The accent is placed so its side bearing lands at sbx + adx - asb.
    dx = r.g.sbx + adx - asb
    dy = ady
    out = Glyph(width=r.g.width, sbx=r.g.sbx, sby=r.g.sby)
    out.contours.extend(base.contours)
    for c in acc.contours:
        out.contours.append([
            Segment(s.x + dx, s.y + dy,
                    None if s.c1 is None else (s.c1[0] + dx, s.c1[1] + dy),
                    None if s.c2 is None else (s.c2[0] + dx, s.c2[1] + dy))
            for s in c])
    return out


def outline(font: Type1Font, name: str) -> Glyph:
    """The named glyph's contours. Raises if the font has no such glyph."""
    try:
        code = font.charstrings[name]
    except KeyError:
        raise CharstringError(f"font has no glyph {name!r}") from None
    return run(font, code)
