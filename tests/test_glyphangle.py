"""The junction-angle feature, checked hermetically on the REAL glyphs.

`⌋` and `⇃` carry almost the same ink -- same stem, a short arm at the
bottom left, within a pixel of the same box -- so component counts, hole
counts and ink distance all pass them. What separates them is HOW the
arm meets the stem, and out/661 measured it on Mielke, the one book that
reads the same glyph both ways.

THE FIXTURES ARE THE GLYPHS THEMSELVES, rendered once from
`cmsy10/floorright` and `msam10/harpoondownleft` at 46 px per em -- the
size Mielke's ink actually has -- and pasted in. A shape drawn by hand
would have dimensions that came from nowhere, and the first version of
this file had exactly that: a synthetic barb whose reach and row count
were chosen, which failed its own test because the choice was arbitrary.

TWO DEFECTS WERE FOUND BY THESE TESTS, not by reading the code:

  * `stem_arm` took the extreme columns -- rightmost as the stem,
    leftmost as the arm tip -- so it was direction-blind and read a
    mirrored `⌊` as a `⌋`. The docstring's "reaches left" was prose
    until the mirror test refused to pass. The stem is now FOUND.
  * the separation was claimed on the drift. At 64 px the floor's own
    foot drifts 1.0, the same as the barb: only the ANGLE separates at
    every size, and the rule in out/661 says so because this failed.

Nothing here reads the TeX tree; the opt-in class at the end does, and
skips without it.
"""

import importlib.util
import pathlib
import unittest

from inkdrill.raster import InkMask

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "_glyphangle", _ROOT / "tools" / "glyphangle.py")
ga = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ga)

#: cmsy10/floorright at em 46 -- a stem, then a FLAT foot of two rows
FLOOR = """\
.............
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
...........#.
.###########.
.###########.
.............
"""

#: msam10/harpoondownleft at em 46 -- a stem, then a barb RAMPING away
HARPOON = """\
...........
........#..
........##.
........##.
........##.
........##.
........##.
........##.
........##.
........##.
........##.
........##.
........##.
........##.
........##.
........##.
........##.
........##.
........##.
........##.
........##.
........##.
........##.
........##.
........##.
........##.
........##.
........##.
........##.
........##.
........##.
........##.
........##.
........##.
.###....##.
..###...##.
....##..##.
.....##.##.
......####.
.......###.
........##.
........##.
...........
"""


def _mask(art):
    return InkMask.from_rows(art.splitlines())


def _flip(art):                 # top to bottom: `⌈` is `⌊` upside down
    return "\n".join(reversed(art.splitlines())) + "\n"


def _mirror(art):               # left to right: `⌊` is `⌋` mirrored
    return "\n".join(r[::-1] for r in art.splitlines()) + "\n"


class TG_1_TheTwoShapes(unittest.TestCase):
    """The feature separates a flat foot from a ramping barb."""

    def test_the_floor_stands_square_and_does_not_drift(self):
        self.assertEqual(ga.stem_arm(_mask(FLOOR)), (84.3, 0.0, 2, 46))

    def test_the_harpoon_leans_and_ramps(self):
        self.assertEqual(ga.stem_arm(_mask(HARPOON)), (58.0, 1.2, 6, 41))

    def test_the_angle_is_what_separates_them(self):
        f, b = ga.stem_arm(_mask(FLOOR)), ga.stem_arm(_mask(HARPOON))
        self.assertGreater(f[0] - b[0], 20)      # degrees apart
        self.assertGreater(f[0], 75)
        self.assertLess(b[0], 65)

    def test_the_reading_survives_a_pixel_of_noise_on_the_foot(self):
        """One pixel eaten out of the foot must not turn a floor into a
        barb: the drift is a MEAN over the arm, not a maximum."""
        art = FLOOR.splitlines()
        art[45] = "." + art[45][1:2] + "." + art[45][3:]   # bite the foot
        got = ga.stem_arm(_mask("\n".join(art) + "\n"))
        self.assertIsNotNone(got)
        self.assertGreater(got[0], 75)


class TG_2_WhatItRefuses(unittest.TestCase):
    """Both sides of every clause: a refusal that cannot accept is not a
    guard, and a guard that cannot refuse is not one either."""

    def test_the_shapes_it_is_for_are_accepted(self):
        self.assertIsNotNone(ga.stem_arm(_mask(FLOOR)))
        self.assertIsNotNone(ga.stem_arm(_mask(HARPOON)))

    def test_an_arm_at_the_TOP_is_a_ceiling_not_a_floor(self):
        self.assertIsNone(ga.stem_arm(_mask(_flip(FLOOR))))

    def test_a_mirrored_glyph_is_the_OTHER_hand(self):
        """`⌊` is `⌋` mirrored and must not read as one -- the defect
        this test was written for. Both sides asserted: refused as a
        left-arm glyph, accepted as a right-arm one."""
        self.assertIsNone(ga.stem_arm(_mask(_mirror(FLOOR))))
        self.assertEqual(ga.stem_arm(_mask(_mirror(FLOOR)), side="right"),
                         ga.stem_arm(_mask(FLOOR)))

    def test_a_bare_stem_has_no_arm(self):
        art = [r for r in FLOOR.splitlines() if r.count("#") <= 1]
        self.assertIsNone(ga.stem_arm(_mask("\n".join(art) + "\n")))

    def test_too_few_rows(self):
        art = FLOOR.splitlines()[:3] + FLOOR.splitlines()[-3:]
        self.assertIsNone(ga.stem_arm(_mask("\n".join(art) + "\n")))

    def test_a_squat_blob_is_not_a_stem(self):
        self.assertIsNone(ga.stem_arm(_mask("\n".join(["#" * 20] * 8) + "\n")))


class TG_3_TheDisplayWrapper(unittest.TestCase):
    r"""`\[ ... \]` inside `$...$` is "Bad math environment delimiter",
    and it failed all 57 display lines of the document at once."""

    def test_the_display_wrapper_is_stripped(self):
        self.assertEqual(ga._clean("\\[\n a \\rfloor b \n\\]"), "a \\rfloor b")

    def test_dollars_and_a_tag_too(self):
        self.assertEqual(ga._clean("$$ x \\tag{3.1} $$"), "x")

    def test_an_expression_without_a_wrapper_is_untouched(self):
        self.assertEqual(ga._clean("e_{a} \\rfloor L"), "e_{a} \\rfloor L")


class TG_4_AgainstTheFontsThemselves(unittest.TestCase):
    """Opt-in: that the pasted fixtures still ARE the glyphs, and what
    separates the two across the sizes real ink comes in."""

    SIZES = (34, 40, 46, 52, 58, 64, 80)

    def setUp(self):
        tex = pathlib.Path("/usr/share/texmf-dist/fonts/type1")
        if not (next(tex.rglob("cmsy10.pfb"), None)
                and next(tex.rglob("msam10.pfb"), None)):
            self.skipTest("cmsy10/msam10 not in the TeX tree")

    def test_the_fixtures_match_the_fonts(self):
        row = ga.reference([46])[0]
        self.assertEqual(row["rfloor"], ga.stem_arm(_mask(FLOOR)))
        self.assertEqual(row["downharpoonleft"], ga.stem_arm(_mask(HARPOON)))

    def test_the_angle_separates_at_every_size(self):
        for row in ga.reference(list(self.SIZES)):
            f, b = row["rfloor"], row["downharpoonleft"]
            self.assertGreater(f[0], 75, row)
            self.assertLess(b[0], 65, row)

    def test_the_drift_does_NOT_separate_at_every_size(self):
        """Recorded, not fixed: at 64 px the floor's own foot drifts as
        much as the barb. A rule resting on the drift would fail there,
        which is why out/661's rule rests on the angle."""
        big = [r for r in ga.reference([64]) if r["rfloor"][1] >= r["downharpoonleft"][1] - 0.2]
        self.assertTrue(big, "the floor no longer drifts at 64 px -- "
                             "re-measure and re-word out/661 section 5")


if __name__ == "__main__":
    unittest.main()
