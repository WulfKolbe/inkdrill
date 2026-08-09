"""Unit 9 (rasterizer half), part 1: Type 1 against real fonts. OPT-IN.

The hermetic module builds its own fonts, which proves the parser agrees
with the encoder it was written beside -- and nothing else. This one
reads whatever Type 1 fonts the machine actually has, and it exists
because both corrections to the parser's oracle came from real fonts and
neither could have come from a synthetic one:

    `div` between the width and the hsbw            all of cm-super
    the hsbw inside a subroutine                    Roboto, Tinos, Cascadia

Opt-in, like `test_pngio_corpus`: skipped unless `INKDRILL_TYPE1` names a
directory of Type 1 fonts. Defaulting it to the system TeX tree was
tempting -- the tree is present on most machines and the coverage would
be free -- but it would make the suite's own test COUNT depend on which
fonts a machine happens to have installed, and that count is quoted as a
fixed number. The usual invocation is one line:

    INKDRILL_TYPE1=/usr/share/texmf-dist/fonts/type1 python3 -m unittest \
        tests.test_type1_corpus

Font selection is a seeded random sample, NOT `sorted(...)[:n]`. The
tree is arranged by foundry, so the first n by name are all one family
and would have missed both corrections above.
"""

import os
import pathlib
import random
import unittest

from inkdrill.type1 import FontNotType1, load

_ROOT = os.environ.get("INKDRILL_TYPE1")
_MAX = int(os.environ.get("INKDRILL_TYPE1_FONTS", "150"))
_SEED = 20260809


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


_FONTS = _fonts()
_WHY = ("set INKDRILL_TYPE1 to a directory of .pfb fonts, e.g. "
        "/usr/share/texmf-dist/fonts/type1")


@unittest.skipUnless(_FONTS, _WHY)
class T9_8_RealFonts(unittest.TestCase):
    """The parser against every font on the machine, no golden files."""

    @classmethod
    def setUpClass(cls):
        cls.parsed = []
        cls.failed = []
        for p in _FONTS:
            try:
                cls.parsed.append((p, load(p)))
            except FontNotType1 as exc:
                cls.failed.append((p, exc))

    def test_every_pfb_in_the_tree_parses(self):
        self.assertEqual(
            [(p.name, str(e)) for p, e in self.failed], [],
            "a .pfb in a Type 1 tree that this parser rejects is either a "
            "parser gap or a mislabelled file; both need naming")

    def test_no_charstring_opens_with_a_path_operator(self):
        """The class that must be empty (see `first_ops`).

        A wrong length, offset, key or lenIV lands here. `callsubr` does
        not, and is counted separately rather than being absorbed into a
        pass rate -- which is what hid this until real fonts were read.
        """
        offenders = []
        for p, f in self.parsed:
            wrong = {k: v for k, v in f.first_ops().items()
                     if k.startswith("cmd") or k == "truncated"}
            if wrong:
                offenders.append((p.name, wrong, len(f.charstrings)))
        self.assertEqual(offenders, [])

    def test_the_sample_actually_contains_both_hard_cases(self):
        """Guards the test above from passing on an easy sample.

        Without this, a tree of nothing but plain cmr fonts would make
        every assertion here vacuous, and the module would report
        success while covering neither correction it exists for.
        """
        seen = set()
        for _, f in self.parsed:
            seen |= set(f.first_ops())
            if f.len_iv == 0:
                seen.add("lenIV0")
        self.assertIn("hsbw", seen)
        self.assertIn("lenIV0", seen)

    def test_charstrings_and_encoding_are_populated(self):
        for p, f in self.parsed:
            with self.subTest(font=p.name):
                self.assertTrue(f.charstrings)
                self.assertGreater(f.units_per_em, 0)

    def test_a_glyph_name_in_the_encoding_usually_has_a_charstring(self):
        """A code mapped to a name with no outline is a real defect in a
        font, but it does occur; assert on the aggregate, and print the
        spread rather than trusting it.
        """
        mapped = resolved = 0
        for _, f in self.parsed:
            for name in f.encoding.values():
                mapped += 1
                resolved += name in f.charstrings
        if not mapped:
            self.skipTest("no font in the sample has a builtin encoding")
        self.assertGreater(resolved / mapped, 0.90,
                           f"{resolved}/{mapped} encoded names have outlines")


@unittest.skipUnless(_FONTS, _WHY)
class T9_9_Wrapper(unittest.TestCase):
    """G2 on real fonts: the wrapper is not part of the answer."""

    def test_a_real_pfb_rewrapped_as_pfa_gives_identical_charstrings(self):
        from inkdrill.type1 import _split_pfb, parse
        for p in _FONTS[:5]:
            with self.subTest(font=p.name):
                clear, enc = _split_pfb(p.read_bytes())
                pfa = clear + enc.hex().encode("ascii") + b"\n"
                self.assertEqual(parse(pfa).charstrings,
                                 load(p).charstrings)


if __name__ == "__main__":
    unittest.main()
