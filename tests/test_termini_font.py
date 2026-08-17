"""`termini` on rendered Type 1 glyphs. OPT-IN, like the other font
tests: skips unless INKDRILL_TYPE1 (default TeX tree) holds the fonts.

Two populations, asserted differently:

* the hermetic ideal strokes live in `test_sweep.T3_9_Termini`;
* here the REAL serif face is asserted at its MEASURED values, which
  differ from the ideal exactly where serifs add stroke ends -- cmr10's
  `u` grows a second bottom terminus from its right stem's serif, and
  its `L` a second right terminus from the top serif. The instructed
  ideal (`u` 1 bottom, `L` 1 right) is a property of sans strokes, and
  asserting it here would pin the wrong face.

The mirror pairs are the point of the exercise: `(components, cycles)`
is reflection-invariant and was blind to every one of them; the
4-tuple is direction-DEPENDENT, so a horizontal mirror swaps
(left, right) and a vertical mirror swaps (top, bottom). What it still
cannot separate is recorded beside what it can.
"""

import os
import pathlib
import unittest

from inkdrill.charstring import outline
from inkdrill.scan import render
from inkdrill.sweep import Capture, sweep, termini
from inkdrill.type1 import load

_TREE = pathlib.Path(os.environ.get("INKDRILL_TYPE1",
                                    "/usr/share/texmf-dist/fonts/type1"))


def _font(name):
    src = next(_TREE.rglob(name + ".pfb"), None) if _TREE.is_dir() else None
    return load(src) if src else None


@unittest.skipUnless(_TREE.is_dir(), "set INKDRILL_TYPE1")
class TT_1_SerifTermini(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.cmr = _font("cmr10")
        cls.sym = _font("cmsy10")
        if cls.cmr is None or cls.sym is None:
            raise unittest.SkipTest("cmr10/cmsy10 not under INKDRILL_TYPE1")

    def _t4(self, font, name, px_em=96.0):
        mask, _ = render(outline(font, name), font.units_per_em, px_em)
        return (termini(sweep(mask, axis="row", conn=8,
                              capture=Capture.GRAPH))
                + termini(sweep(mask, axis="col", conn=8,
                                capture=Capture.GRAPH)))

    def test_m_n_u_at_their_measured_serif_values(self):
        """(top, bottom, left, right). `m` 3 bottoms and `n` 2 as
        instructed; `u` measures 2 bottoms, NOT the ideal 1, because the
        right stem's serif descends past the bowl. Real face, real
        numbers."""
        self.assertEqual(self._t4(self.cmr, "m"), (3, 3, 4, 3))
        self.assertEqual(self._t4(self.cmr, "n"), (2, 2, 3, 2))
        self.assertEqual(self._t4(self.cmr, "u"), (2, 2, 2, 1))

    def test_E_has_three_right_termini_and_L_measures_two(self):
        """E: three arms end right, serifs and all. L: the instructed 1
        holds for a bare stroke; cmr10's top serif protrudes right and
        adds one."""
        self.assertEqual(self._t4(self.cmr, "E")[3], 3)
        self.assertEqual(self._t4(self.cmr, "L")[3], 2)

    def test_every_MIRROR_PAIR_is_separated(self):
        """The pairs (components, cycles) was blind to. A horizontal
        mirror swaps (left, right), a vertical one (top, bottom), and
        the swap is visible in every measured tuple."""
        pairs = [(self.sym, "propersubset", self.sym, "propersuperset"),
                 (self.sym, "lessequal", self.sym, "greaterequal"),
                 (self.sym, "union", self.sym, "intersection"),
                 (self.cmr, "E", self.sym, "existential")]
        for fa, a, fb, b in pairs:
            ta, tb = self._t4(fa, a), self._t4(fb, b)
            self.assertNotEqual(ta, tb, f"{a}/{b}")

    def test_the_horizontal_mirror_swap_is_the_MECHANISM(self):
        """Not merely different: ⊂ and ⊃ agree on (top, bottom) and
        swap (left, right) exactly. Asserting the mechanism stops the
        test passing on an accidental raster difference."""
        ta = self._t4(self.sym, "propersubset")
        tb = self._t4(self.sym, "propersuperset")
        self.assertEqual(ta[:2], tb[:2])
        self.assertEqual((ta[2], ta[3]), (tb[3], tb[2]))

    def test_plusminus_minusplus_remains_BLIND_and_is_recorded(self):
        """The limit, asserted rather than omitted: each half of ± has
        a mirror-symmetric terminus count of its own, so the counts
        carry no which-half-is-where information. (1, 1, 2, 2) both.
        The one pair left standing from the (components, cycles) blind
        set."""
        self.assertEqual(self._t4(self.sym, "plusminus"),
                         self._t4(self.sym, "minusplus"))


if __name__ == "__main__":
    unittest.main()
