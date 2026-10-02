"""The shapes a PDF font name really takes, and the CMEX family rule.

pdf2mmd proposes distrusting any StandardEncoding glyph name found in a
CMEX font. Measured in out/684, that is safe for the Computer Modern
extension fonts -- cmex7/8/9/10 carry exactly one standard name,
`space` -- and unsafe one step away: `yhcmex` carries 149 and `lcmex8`
122, both legitimately, and five corpus documents embed `Yhcmex`.

So the rule stands or falls on resolving the FAMILY, and the family has
to be read off names in the shapes producers actually emit. Every
fixture below is a name taken from `probe-pdffonts.txt` in the library.
"""
import importlib.util
import pathlib
import sys
import unittest


def _measure():
    p = (pathlib.Path(__file__).resolve().parent.parent
         / "tools" / "premise" / "measure.py")
    spec = importlib.util.spec_from_file_location("_m_fonts", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_m_fonts"] = mod
    spec.loader.exec_module(mod)
    return mod


M = _measure()


class TF_1_SubsetTagsComeInTwoShapes(unittest.TestCase):
    def test_the_ordinary_plus_separated_tag(self):
        self.assertEqual(M._font_base("ATGUKY+CMEX10"), "CMEX10")

    def test_a_tag_with_no_plus(self):
        """`VpqhhbCMEX10` is in the corpus: six letters, capital first,
        glued straight onto the font name."""
        self.assertEqual(M._font_base("GGHPMO+VpqhhbCMEX10"), "CMEX10")

    def test_a_tilde_suffix(self):
        self.assertEqual(M._font_base("CMEX10~154"), "CMEX10")

    def test_a_bare_name_is_unchanged(self):
        self.assertEqual(M._font_base("CMEX10"), "CMEX10")


class TF_2_TheFamilyRuleIsNotASubstringTest(unittest.TestCase):
    """The whole point. A substring match on `cmex` would distrust every
    letter of five real documents."""

    def test_the_computer_modern_extension_fonts_match(self):
        for n in ("CMEX10", "CMEX7", "CMEX8", "CMEX9", "cmex10", "Cmex10"):
            with self.subTest(n=n):
                self.assertTrue(M._CMEX_RE.match(M._font_base(n)), n)

    def test_the_dvips_spelling_matches(self):
        for n in ("TeX-cmex7", "TeX-cmex8", "TeX-cmex9"):
            with self.subTest(n=n):
                self.assertTrue(M._CMEX_RE.match(M._font_base(n)), n)

    def test_yhmath_and_lxfonts_do_NOT_match(self):
        """`yhcmex` has 149 standard names and `lcmex8` has 122 -- they
        are extension fonts by name and alphabets by content. Five
        corpus documents embed `Yhcmex`."""
        for n in ("Yhcmex", "YINZZB+Yhcmex", "lcmex8", "cmexb10"):
            with self.subTest(n=n):
                self.assertIsNone(M._CMEX_RE.match(M._font_base(n)), n)

    def test_an_instance_counter_is_not_a_size(self):
        """`CMEX1048` is CMEX10 instance 48, not a 1048 pt font. The
        rule must still recognise it as the family; only a parser that
        reads the digits as a SIZE is wrong, which is why the family
        test does not look at them."""
        m = M._CMEX_RE.match(M._font_base("CMEX1048"))
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "1048")


if __name__ == "__main__":
    unittest.main()
