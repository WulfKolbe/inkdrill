"""U-trace: boundary contours against the sweep oracle.

The oracles are the unit: per component the tracer must produce
exactly `1 + cycle_count` loops (`sweep`, sharing no code with the
walk), and the signed areas must sum to the exact pixel count -- holes
subtract. The sign convention itself was caught by that second oracle:
the first draft negated the shoelace and the ring fixture summed to
-14 instead of 14.
"""

import os
import pathlib
import random
import unittest

from inkdrill.raster import InkMask
from inkdrill.sweep import Capture, sweep
from inkdrill.trace import Contour, contours, signed_area


def m(rows):
    w = len(rows[0])
    return InkMask(bytes(0xFF if c == "#" else 0
                         for r in rows for c in r), w, len(rows))


class TT_2_Contours(unittest.TestCase):

    def test_a_ring_gives_outer_plus_hole_with_opposite_winding(self):
        ring = m(["#####",
                  "#...#",
                  "#...#",
                  "#####"])
        (comp,) = contours(ring)
        self.assertEqual(len(comp), 2)
        outer, hole = comp
        self.assertTrue(outer.is_outer)
        self.assertFalse(hole.is_outer)
        self.assertEqual(outer.area, 20.0)      # the full rectangle
        self.assertEqual(hole.area, -6.0)       # minus the hole
        self.assertEqual(outer.area + hole.area, ring.ink_count)

    def test_the_outer_comes_FIRST(self):
        """G6. Sorting puts it there; deleting the sort must fail."""
        ring = m(["####",
                  "#..#",
                  "####"])
        (comp,) = contours(ring)
        self.assertTrue(comp[0].is_outer)
        self.assertFalse(comp[1].is_outer)

    def test_a_diagonal_pair_is_ONE_loop_through_the_saddle(self):
        """The connectivity pairing, at the only place the walk can get
        it wrong. 8-connected ink: a checkerboard pair is one component
        and must yield ONE outer contour visiting the shared corner
        twice -- the left-turn-first saddle rule. Two loops here means
        the walker split a connected component."""
        cb = m(["#.",
                ".#"])
        (comp,) = contours(cb)
        self.assertEqual(len(comp), 1)
        self.assertEqual(comp[0].area, 2.0)
        self.assertEqual(comp[0].points.count((1, 1)), 2)

    def test_every_contour_is_closed_and_uses_each_crack_once(self):
        """G2, on a shape with a pinch and a hole at once."""
        blob = m(["##.##",
                  "#####",
                  "#.#.#",
                  "#####"])
        comps = contours(blob)
        seen = set()
        for comp in comps:
            for c in comp:
                for i in range(len(c.points)):
                    a = c.points[i]
                    b = c.points[(i + 1) % len(c.points)]
                    self.assertEqual(abs(a[0] - b[0]) + abs(a[1] - b[1]), 1,
                                     "non-unit step")
                    self.assertNotIn((a, b), seen, "crack reused")
                    seen.add((a, b))

    def test_the_sweep_oracle_over_random_masks(self):
        """G3 + G5 on 120 random masks: loops per component equal
        1 + cycle_count, one outer each, and signed areas sum to the
        exact ink count."""
        rng = random.Random(20260817)
        for _ in range(120):
            w, h = rng.randint(2, 16), rng.randint(2, 16)
            mk = InkMask(bytes(0xFF if rng.random() < rng.choice((0.25, 0.55,
                                                                  0.8))
                               else 0 for _ in range(w * h)), w, h)
            res = sweep(mk, conn=8, capture=Capture.GRAPH)
            got = contours(mk)
            self.assertEqual(len(got), len(res.components))
            for ci, comp in enumerate(res.components):
                self.assertEqual(len(got[ci]), 1 + comp.cycle_count,
                                 f"{w}x{h} comp {ci}")
                self.assertEqual(sum(1 for c in got[ci] if c.is_outer), 1)
            self.assertEqual(sum(c.area for comp in got for c in comp),
                             mk.ink_count)

    def test_connectivity_is_refused_and_accepted(self):
        with self.assertRaises(ValueError):
            contours(m(["#"]), conn=4)
        self.assertEqual(contours(m(["#"]))[0][0].area, 1.0)

    def test_signed_area_sign_is_the_documented_convention(self):
        """The ink-on-left OUTER direction -- east along the top edge,
        then down the right side (clockwise on screen, y down) -- is
        positive. Held to a constant, not to itself; the first version
        of this constant was backwards and failed against the tracer,
        which is the check working in the unfashionable direction."""
        self.assertEqual(signed_area([(0, 0), (1, 0), (1, 1), (0, 1)]), 1.0)
        self.assertEqual(signed_area([(0, 0), (0, 1), (1, 1), (1, 0)]), -1.0)


_TREE = pathlib.Path(os.environ.get("INKDRILL_TYPE1",
                                    "/usr/share/texmf-dist/fonts/type1"))


@unittest.skipUnless(_TREE.is_dir(), "set INKDRILL_TYPE1")
class TT_3_RenderedGlyphs(unittest.TestCase):
    """The instructed cases, on the real font route."""

    def _glyph(self, name):
        from inkdrill.charstring import outline
        from inkdrill.scan import render
        from inkdrill.type1 import load
        src = next(_TREE.rglob("cmr10.pfb"), None)
        if src is None:
            self.skipTest("cmr10.pfb not under INKDRILL_TYPE1")
        f = load(src)
        mask, _ = render(outline(f, name), f.units_per_em, 96.0)
        return contours(mask)

    def test_O_gives_two_contours_with_opposite_winding(self):
        (comp,) = self._glyph("O")
        self.assertEqual(len(comp), 2)
        self.assertGreater(comp[0].area, 0)
        self.assertLess(comp[1].area, 0)

    def test_eight_gives_three_the_holes_agreeing_against_the_outer(self):
        (comp,) = self._glyph("eight")
        self.assertEqual(len(comp), 3)
        self.assertGreater(comp[0].area, 0)
        self.assertLess(comp[1].area, 0)
        self.assertLess(comp[2].area, 0)


if __name__ == "__main__":
    unittest.main()
