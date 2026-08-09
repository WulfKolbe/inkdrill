"""Unit 9 (rasterizer half), part 3: contours to an ink mask.

Hermetic. Contours are built directly from `Segment`s, so the fill rule
and the sampling convention are tested without a font in the way.
`tests/test_charstring_corpus.py` runs the closing oracle on real
glyphs: `charstring`'s contour count against `sweep`'s components plus
holes, two computations sharing no code.
"""

import unittest

from inkdrill.charstring import Glyph, Segment
from inkdrill.raster import BG, INK
from inkdrill.scan import flatten, rasterize, render
from inkdrill.sweep import Capture, sweep


def poly(*pts):
    """A closed contour of straight segments through `pts`."""
    return [Segment(x, y) for x, y in pts] + [Segment(*pts[0])]


def square(x0, y0, x1, y1, *, reverse=False):
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return poly(*(reversed(pts) if reverse else pts))


IDENT = lambda x, y: (x, y)                                  # noqa: E731


class T9_20_Sampling(unittest.TestCase):
    """G3: a pixel is ink iff its centre is inside."""

    def test_a_pixel_aligned_rectangle_fills_exactly(self):
        m = rasterize(flatten([square(2, 2, 7, 5)], IDENT), 10, 10)
        self.assertEqual(m.ink_count, (7 - 2) * (5 - 2))

    def test_the_span_is_half_open_like_the_pixel_convention(self):
        m = rasterize(flatten([square(0, 0, 1, 1)], IDENT), 4, 4)
        self.assertEqual(m.ink_count, 1)
        self.assertEqual(m.data[0], INK)

    def test_a_rectangle_between_pixel_centres_is_empty(self):
        # Spanning x in [2.6, 2.9) contains no pixel centre, so no
        # pixel's centre is inside and the correct answer is nothing.
        m = rasterize(flatten([square(2.6, 2, 2.9, 5)], IDENT), 10, 10)
        self.assertEqual(m.ink_count, 0)

    def test_the_mask_uses_the_package_encoding(self):
        m = rasterize(flatten([square(1, 1, 3, 3)], IDENT), 5, 5)
        self.assertEqual(set(m.data), {BG, INK})

    def test_geometry_outside_the_buffer_is_clipped_not_wrapped(self):
        m = rasterize(flatten([square(-5, -5, 20, 20)], IDENT), 4, 4)
        self.assertEqual(m.ink_count, 16)


class T9_21_Winding(unittest.TestCase):
    """Non-zero winding, which is what Type 1 specifies."""

    def test_a_counter_wound_the_other_way_is_a_hole(self):
        m = rasterize(flatten(
            [square(0, 0, 10, 10), square(3, 3, 7, 7, reverse=True)],
            IDENT), 10, 10)
        self.assertEqual(m.ink_count, 100 - 16)

    def test_two_contours_wound_the_SAME_way_do_not_punch_a_hole(self):
        """The case where non-zero and even-odd disagree.

        Even-odd would clear the inner square. Real fonts contain
        same-wound nested contours, so choosing the wrong rule produces
        a glyph with a hole that should not be there.
        """
        m = rasterize(flatten(
            [square(0, 0, 10, 10), square(3, 3, 7, 7)], IDENT), 10, 10)
        self.assertEqual(m.ink_count, 100)

    def test_two_disjoint_squares_stay_disjoint(self):
        m = rasterize(flatten(
            [square(0, 0, 3, 3), square(6, 6, 9, 9)], IDENT), 10, 10)
        res = sweep(m, conn=8, capture=Capture.GRAPH)
        self.assertEqual(len(res.components), 2)


class T9_22_ClosingOracle(unittest.TestCase):
    """G7: contour count agrees with components + holes."""

    def _identity(self, contours, w=40, h=40):
        m = rasterize(flatten(contours, IDENT), w, h)
        res = sweep(m, conn=8, capture=Capture.GRAPH)
        return len(res.components) + sum(c.cycle_count
                                         for c in res.components)

    def test_a_ring_is_one_component_and_one_hole(self):
        self.assertEqual(self._identity(
            [square(5, 5, 35, 35), square(12, 12, 28, 28, reverse=True)]), 2)

    def test_two_rings_are_two_components_and_two_holes(self):
        self.assertEqual(self._identity([
            square(2, 2, 18, 18), square(6, 6, 14, 14, reverse=True),
            square(22, 22, 38, 38), square(26, 26, 34, 34, reverse=True),
        ]), 4)

    def test_a_solid_square_is_one_and_none(self):
        self.assertEqual(self._identity([square(5, 5, 35, 35)]), 1)


class T9_23_Curves(unittest.TestCase):
    """G5: flattening is relative to device size."""

    def _circleish(self, r, cx=0.0, cy=0.0):
        k = 0.5523 * r
        return [
            Segment(cx + r, cy),
            Segment(cx, cy + r, (cx + r, cy + k), (cx + k, cy + r)),
            Segment(cx - r, cy, (cx - k, cy + r), (cx - r, cy + k)),
            Segment(cx, cy - r, (cx - r, cy - k), (cx - k, cy - r)),
            Segment(cx + r, cy, (cx + k, cy - r), (cx + r, cy - k)),
        ]

    def test_a_flattened_circle_approaches_its_area(self):
        r = 60.0
        m = rasterize(flatten([self._circleish(r, 70, 70)], IDENT), 140, 140)
        import math
        self.assertAlmostEqual(m.ink_count / (math.pi * r * r), 1.0, delta=0.01)

    def test_a_bigger_circle_is_flattened_into_more_points(self):
        small = flatten([self._circleish(5, 10, 10)], IDENT)[0]
        big = flatten([self._circleish(500, 600, 600)], IDENT)[0]
        self.assertGreater(len(big), len(small))

    def test_a_straight_segment_adds_exactly_one_point(self):
        p = flatten([poly((0, 0), (10, 0), (10, 10))], IDENT)[0]
        self.assertEqual(len(p), 4)


class T9_24_Render(unittest.TestCase):
    """G4 and G6: the y flip, and the empty cases."""

    def _glyph(self, contours):
        g = Glyph()
        g.contours.extend(contours)
        return g

    def test_the_y_axis_is_flipped_exactly_once(self):
        """A shape high in font space must land NEAR THE TOP of the mask.

        Flipping twice, or not at all, leaves the mask upside down --
        which no area or component count would notice.
        """
        g = self._glyph([square(0, 0, 100, 20), square(0, 700, 40, 720)])
        m, _ = render(g, 1000, 72)
        rows = [any(m.data[j * m.width:(j + 1) * m.width])
                for j in range(m.height)]
        top = rows.index(True)
        bottom = len(rows) - 1 - rows[::-1].index(True)
        wide_top = sum(1 for x in range(m.width) if m.data[top * m.width + x])
        wide_bot = sum(1 for x in range(m.width)
                       if m.data[bottom * m.width + x])
        self.assertGreater(wide_bot, wide_top,
                           "the wide shape sat at y=0 and must be at the "
                           "BOTTOM of the mask")

    def test_size_scales_the_bitmap(self):
        g = self._glyph([square(0, 0, 500, 500)])
        small, _ = render(g, 1000, 20)
        big, _ = render(g, 1000, 200)
        self.assertGreater(big.width, small.width * 5)

    def test_an_empty_glyph_renders_to_an_empty_mask(self):
        m, origin = render(Glyph(), 1000, 64)
        self.assertEqual((m.width, m.height), (0, 0))

    def test_size_zero_renders_to_an_empty_mask(self):
        g = self._glyph([square(0, 0, 500, 500)])
        m, _ = render(g, 1000, 0)
        self.assertEqual((m.width, m.height), (0, 0))

    def test_the_glyph_is_not_clipped_by_its_own_bounds(self):
        g = self._glyph([square(0, 0, 500, 500)])
        m, _ = render(g, 1000, 50, pad=1)
        # One pad ring all round, so the ink is inset but complete.
        self.assertEqual(m.ink_count, (m.width - 2) * (m.height - 2))

    def test_an_axis_invariant_result(self):
        """Row and column sweeps must agree, as everywhere else."""
        g = self._glyph([square(0, 0, 400, 300),
                         square(100, 100, 300, 200, reverse=True)])
        m, _ = render(g, 1000, 60)
        a = sweep(m, axis="row", conn=8, capture=Capture.GRAPH)
        b = sweep(m, axis="col", conn=8, capture=Capture.GRAPH)
        self.assertEqual(len(a.components), len(b.components))
        self.assertEqual(sum(c.cycle_count for c in a.components),
                         sum(c.cycle_count for c in b.components))


if __name__ == "__main__":
    unittest.main()
