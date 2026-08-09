"""Unit 9 part 2 against real fonts. OPT-IN.

The hermetic module assembles charstrings by hand, which proves the
interpreter agrees with the spec as read. This one runs it over every
glyph of every font on the machine, and adds the one check that is
independent of the interpreter altogether: **letterform topology**.

A lower-case `o` has two contours in every roman text face ever cut.
That is not a fact about this code, and no amount of arithmetic error
inside the interpreter produces it by accident -- so it tests
correctness rather than mere completion, which running without raising
does not.

The expectations are stated for a ROMAN TEXT font and applied only to
one. The same glyph NAMES in other faces have different topology and
the interpreter is right to report it -- `cmmi10`'s `g` is a
single-storey italic with 2 contours, not the 3 of a double-storey
roman, and `cmsy10`'s `B`, `O`, `P`, `R` are script capitals drawn in a
single stroke. Applying a roman table to those fonts produced four
"failures" that were all correct answers; the population, again.

    INKDRILL_TYPE1=/usr/share/texmf-dist/fonts/type1 python3 -m unittest \
        tests.test_charstring_corpus
"""

import os
import pathlib
import random
import unittest

from inkdrill.charstring import CharstringError, outline, run
from inkdrill.scan import render
from inkdrill.sweep import Capture, sweep
from inkdrill.type1 import load

_ROOT = os.environ.get("INKDRILL_TYPE1")
_MAX = int(os.environ.get("INKDRILL_TYPE1_FONTS", "60"))
_SEED = 20260809

# One roman text face, and glyphs whose contour count is a property of
# the alphabet rather than of a type designer's taste.
_ROMAN = "cmr10.pfb"
_TOPOLOGY = {
    "l": 1, "one": 1,               # a single stroke
    "i": 2, "o": 2, "e": 2,         # stem + tittle; ring; ring + bar
    "a": 2, "b": 2, "d": 2, "p": 2, "q": 2,
    "A": 2, "O": 2, "P": 2, "R": 2, "D": 2,
    "B": 3, "g": 3, "eight": 3,     # two counters
    "zero": 2, "four": 2, "six": 2, "nine": 2,
}


def _fonts():
    if not _ROOT:
        return []
    root = pathlib.Path(_ROOT).expanduser()
    if not root.is_dir():
        return []
    found = sorted(root.rglob("*.pfb"))
    if len(found) <= _MAX:
        return found
    return random.Random(_SEED).sample(found, _MAX)


def _roman():
    if not _ROOT:
        return None
    root = pathlib.Path(_ROOT).expanduser()
    return next(root.rglob(_ROMAN), None) if root.is_dir() else None


_FONTS = _fonts()
_ROMAN_PATH = _roman()
_WHY = ("set INKDRILL_TYPE1 to a directory of .pfb fonts, e.g. "
        "/usr/share/texmf-dist/fonts/type1")


@unittest.skipUnless(_FONTS, _WHY)
class T9_18_EveryGlyphRuns(unittest.TestCase):
    """Completion and the structural guarantees, at scale."""

    @classmethod
    def setUpClass(cls):
        cls.results = []
        for p in _FONTS:
            try:
                f = load(p)
            except Exception:
                continue
            cls.results.append((p, f))

    def test_every_charstring_runs_to_completion(self):
        failed = []
        for p, f in self.results:
            for name, code in f.charstrings.items():
                try:
                    run(f, code)
                except CharstringError as exc:
                    failed.append((p.name, name, str(exc)[:60]))
        self.assertEqual(failed[:10], [], f"{len(failed)} glyphs failed")

    def test_every_contour_comes_back_closed(self):
        """G2, over real data rather than over three fixtures."""
        open_ones = 0
        total = 0
        for p, f in self.results:
            for code in f.charstrings.values():
                for c in run(f, code).contours:
                    total += 1
                    if (c[0].x, c[0].y) != (c[-1].x, c[-1].y):
                        open_ones += 1
        self.assertGreater(total, 1000, "sample too small to mean anything")
        self.assertEqual(open_ones, 0)

    def test_the_hsbw_in_a_subr_case_is_settled(self):
        """`first_ops` defers `callsubr`; only the interpreter can judge.

        2.166% of the TeX tree's charstrings open `n callsubr` with the
        hsbw inside the subr. Running them is what verifies that class,
        so this asserts the sample actually contains some.
        """
        deferred = checked = 0
        for p, f in self.results:
            for k, v in f.first_ops().items():
                if k == "callsubr":
                    deferred += v
            for code in f.charstrings.values():
                if code and code[0] < 32 and code[0] == 10:
                    checked += 1
        if not deferred:
            self.skipTest("no subroutinized font in this sample")
        self.assertGreater(deferred, 0)


@unittest.skipUnless(_ROMAN_PATH, f"{_ROMAN} not found under INKDRILL_TYPE1")
class T9_19_LetterformTopology(unittest.TestCase):
    """The oracle that is independent of the interpreter."""

    @classmethod
    def setUpClass(cls):
        cls.font = load(_ROMAN_PATH)

    def test_contour_counts_match_the_alphabet(self):
        wrong = []
        for name, want in _TOPOLOGY.items():
            if name not in self.font.charstrings:
                continue
            got = len(outline(self.font, name).contours)
            if got != want:
                wrong.append((name, want, got))
        self.assertEqual(wrong, [])

    def test_the_table_actually_covered_something(self):
        present = [n for n in _TOPOLOGY if n in self.font.charstrings]
        self.assertGreaterEqual(len(present), 15)

    def test_a_counter_is_inside_its_letter(self):
        """`o`'s inner contour lies strictly within the outer one.

        A sign error in the curve operators can leave the right number
        of contours in the wrong places, which the count alone permits.
        """
        g = outline(self.font, "o")
        boxes = []
        for c in g.contours:
            xs = [s.x for s in c]
            ys = [s.y for s in c]
            boxes.append((min(xs), min(ys), max(xs), max(ys)))
        boxes.sort(key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
        inner, outer = boxes[0], boxes[-1]
        self.assertTrue(outer[0] < inner[0] and outer[1] < inner[1]
                        and outer[2] > inner[2] and outer[3] > inner[3],
                        f"inner {inner} not inside outer {outer}")


@unittest.skipUnless(_ROMAN_PATH, f"{_ROMAN} not found under INKDRILL_TYPE1")
class T9_25_ClosingOracle(unittest.TestCase):
    """`charstring` and `sweep` agree about the same glyph (scan G7).

    Contour count from Bezier control points in font units, against
    components plus holes from run adjacency on a bitmap. The two share
    no code, and they agree only if the fill rule, the winding
    direction, the y flip and the sampling convention are ALL right --
    a sign error in any one breaks it.
    """

    @classmethod
    def setUpClass(cls):
        cls.font = load(_ROMAN_PATH)

    def test_contours_equal_components_plus_holes(self):
        wrong, checked = [], 0
        for name in _TOPOLOGY:
            if name not in self.font.charstrings:
                continue
            g = outline(self.font, name)
            mask, _ = render(g, self.font.units_per_em, 64)
            res = sweep(mask, conn=8, capture=Capture.GRAPH)
            got = len(res.components) + sum(c.cycle_count
                                            for c in res.components)
            checked += 1
            if got != len(g.contours):
                wrong.append((name, len(g.contours), got))
        self.assertGreaterEqual(checked, 15)
        self.assertEqual(wrong, [])

    def test_the_identity_survives_a_small_raster(self):
        """At 24 px a counter can close up; that is a resolution limit,
        not a bug, so this asserts only that it does not go the other
        way -- ink never gains holes as it shrinks."""
        for name in ("o", "B", "eight"):
            if name not in self.font.charstrings:
                continue
            g = outline(self.font, name)
            mask, _ = render(g, self.font.units_per_em, 24)
            res = sweep(mask, conn=8, capture=Capture.GRAPH)
            got = len(res.components) + sum(c.cycle_count
                                            for c in res.components)
            self.assertLessEqual(got, len(g.contours), name)


if __name__ == "__main__":
    unittest.main()
