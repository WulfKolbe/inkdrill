"""Unit 1 tests. Every test name is quoted verbatim in the status report."""

import math
import random
import unittest

from inkdrill.space import (Affine, DegenerateAffine, NoPath, SpaceGraph,
                            SpaceNotFound, angle_deg_ccw, angle_deg_screen,
                            pixel_centre)


def random_affine(rng, scale=10.0):
    while True:
        m = Affine(rng.uniform(-scale, scale), rng.uniform(-scale, scale),
                   rng.uniform(-scale, scale), rng.uniform(-scale, scale),
                   rng.uniform(-scale, scale), rng.uniform(-scale, scale))
        if abs(m.det) > 1e-3:
            return m


class T1_1_Identity(unittest.TestCase):
    """G1: identity is a two-sided unit, exactly."""

    def test_identity_is_two_sided_unit(self):
        rng = random.Random(1)
        i = Affine.identity()
        for _ in range(200):
            m = random_affine(rng)
            self.assertTrue(i.then(m).approx_eq(m, 0.0))
            self.assertTrue(m.then(i).approx_eq(m, 0.0))


class T1_2_Inverse(unittest.TestCase):
    """G2: m.then(m.inverse()) == identity."""

    def test_inverse_round_trip(self):
        rng = random.Random(2)
        i = Affine.identity()
        for _ in range(200):
            m = random_affine(rng)
            self.assertTrue(m.then(m.inverse()).approx_eq(i, 1e-9))
            self.assertTrue(m.inverse().then(m).approx_eq(i, 1e-9))

    def test_degenerate_raises(self):
        with self.assertRaises(DegenerateAffine):
            Affine(1, 2, 2, 4).inverse()      # det == 0


class T1_3_Associativity(unittest.TestCase):
    """G3: composition is associative."""

    def test_associative(self):
        rng = random.Random(3)
        for _ in range(200):
            m1, m2, m3 = (random_affine(rng) for _ in range(3))
            self.assertTrue(m1.then(m2).then(m3)
                            .approx_eq(m1.then(m2.then(m3)), 1e-8))

    def test_chain_matches_manual(self):
        rng = random.Random(4)
        ms = [random_affine(rng) for _ in range(5)]
        manual = ms[0]
        for m in ms[1:]:
            manual = manual.then(m)
        self.assertTrue(Affine.chain(ms).approx_eq(manual, 1e-9))


class T1_4_Order(unittest.TestCase):
    """`then` must apply self FIRST — the PDF concatenation order."""

    def test_translate_then_scale(self):
        m = Affine.translate(1, 0).then(Affine.scale(10, 10))
        # point (0,0): translate -> (1,0); scale -> (10,0)
        self.assertAlmostEqual(m.point(0, 0)[0], 10.0, places=12)
        self.assertAlmostEqual(m.point(0, 0)[1], 0.0, places=12)

    def test_scale_then_translate(self):
        m = Affine.scale(10, 10).then(Affine.translate(1, 0))
        # point (0,0): scale -> (0,0); translate -> (1,0)
        self.assertAlmostEqual(m.point(0, 0)[0], 1.0, places=12)

    def test_vector_ignores_translation(self):
        m = Affine.translate(100, 200)
        self.assertEqual(m.vector(1, 0), (1.0, 0.0))
        self.assertEqual(m.point(1, 0), (101.0, 200.0))


class T1_5_KnownValues(unittest.TestCase):
    """Hand-computable cases: no round-tripping can hide a wrong sign."""

    def test_rotate_30_maps_x_axis(self):
        m = Affine.rotate(math.radians(30))
        x, y = m.x_axis
        self.assertAlmostEqual(x, math.cos(math.radians(30)), places=12)
        self.assertAlmostEqual(y, math.sin(math.radians(30)), places=12)

    def test_rotate_90_maps_x_to_y(self):
        m = Affine.rotate(math.radians(90))
        x, y = m.point(1, 0)
        self.assertAlmostEqual(x, 0.0, places=12)
        self.assertAlmostEqual(y, 1.0, places=12)

    def test_flip_y_is_self_inverse(self):
        m = Affine.flip_y(792.0)
        self.assertTrue(m.then(m).approx_eq(Affine.identity(), 1e-9))
        self.assertAlmostEqual(m.point(10, 0)[1], 792.0, places=12)
        self.assertAlmostEqual(m.point(10, 792)[1], 0.0, places=12)


class T1_6_Decomposition(unittest.TestCase):
    """G4/G5: decompose -> recompose is exact; flip tracks det sign."""

    def test_recompose_round_trip(self):
        rng = random.Random(6)
        for _ in range(500):
            m = random_affine(rng)
            self.assertTrue(m.decompose().recompose().approx_eq(m, 1e-8))

    def test_flip_matches_det_sign(self):
        rng = random.Random(7)
        for _ in range(500):
            m = random_affine(rng)
            self.assertEqual(m.decompose().flip, m.det < 0)

    def test_pure_rotation_has_unit_scales_no_shear(self):
        for deg in (0, 17, 90, 179, -45):
            d = Affine.rotate(math.radians(deg)).decompose()
            self.assertAlmostEqual(d.sx, 1.0, places=12)
            self.assertAlmostEqual(d.sy, 1.0, places=12)
            self.assertAlmostEqual(d.shear, 0.0, places=12)
            self.assertFalse(d.flip)

    def test_italic_shear_recovered(self):
        # 12 deg oblique, upright, unit scale
        k = math.tan(math.radians(12))
        d = Affine.skew_x(k).decompose()
        self.assertAlmostEqual(d.italic_shear, k, places=12)
        self.assertAlmostEqual(d.sx, 1.0, places=12)
        self.assertAlmostEqual(d.sy, 1.0, places=12)

    def test_anisotropic_scale_recovered(self):
        d = Affine.scale(3.0, 7.0).decompose()
        self.assertAlmostEqual(d.sx, 3.0, places=12)
        self.assertAlmostEqual(d.sy, 7.0, places=12)
        self.assertAlmostEqual(d.shear, 0.0, places=12)

    def test_mirrored_text_detected(self):
        d = Affine.scale(-1.0, 1.0).decompose()
        self.assertTrue(d.flip)

    def test_degenerate_raises(self):
        with self.assertRaises(DegenerateAffine):
            Affine(0, 0, 0, 0).decompose()


class T1_7_AngleBoundary(unittest.TestCase):
    """The two angle conventions must differ exactly by a sign."""

    def test_ccw_and_screen_are_negatives(self):
        rng = random.Random(8)
        for _ in range(200):
            v = (rng.uniform(-5, 5), rng.uniform(-5, 5))
            if abs(v[0]) < 1e-6 and abs(v[1]) < 1e-6:
                continue
            a, s = angle_deg_ccw(v), angle_deg_screen(v)
            if abs(abs(a) - 180.0) < 1e-9:
                continue                      # +/-180 is the branch cut
            self.assertAlmostEqual(a, -s, places=9)

    def test_known_angles(self):
        self.assertAlmostEqual(angle_deg_ccw((1, 0)), 0.0, places=12)
        self.assertAlmostEqual(angle_deg_ccw((0, 1)), 90.0, places=12)
        self.assertAlmostEqual(angle_deg_screen((0, 1)), -90.0, places=12)

    def test_pixel_centre(self):
        self.assertEqual(pixel_centre(0, 0), (0.5, 0.5))
        self.assertEqual(pixel_centre(3, 7), (3.5, 7.5))


class T1_8_PdfTextChain(unittest.TestCase):
    """A realistic PDF text rendering chain must land where hand arithmetic says.

    Trm = [Tfs*Th, 0, 0, Tfs, 0, Trise] x Tm x CTM, and the glyph space
    scale comes from FontMatrix (0.001 for a Type 1).
    """

    def test_glyph_to_device_position(self):
        font_matrix = Affine(0.001, 0, 0, 0.001, 0, 0)
        tfs = 10.0
        param = Affine(tfs, 0, 0, tfs, 0, 0)          # Th=1, Trise=0
        tm = Affine.translate(72.0, 720.0)
        ctm = Affine.identity()
        trm = Affine.chain([font_matrix, param, tm, ctm])
        # A glyph-space point at (500, 0) -- half an em along the baseline
        x, y = trm.point(500, 0)
        self.assertAlmostEqual(x, 72.0 + 0.5 * tfs, places=9)
        self.assertAlmostEqual(y, 720.0, places=9)
        # x-axis image length is the effective size
        d = trm.decompose()
        self.assertAlmostEqual(d.sx, tfs * 0.001, places=12)

    def test_ctm_scale_changes_effective_size(self):
        """size_pt alone is wrong whenever the CTM scales: the decomposition
        must report the scaled size, not Tfs."""
        font_matrix = Affine(0.001, 0, 0, 0.001, 0, 0)
        param = Affine(10.0, 0, 0, 10.0, 0, 0)
        tm = Affine.identity()
        ctm = Affine.scale(2.0, 2.0)                  # form XObject at 2x
        trm = Affine.chain([font_matrix, param, tm, ctm])
        d = trm.decompose()
        self.assertAlmostEqual(d.sx, 10.0 * 0.001 * 2.0, places=12)

    def test_rotated_text_baseline_direction(self):
        trm = Affine.chain([Affine(0.001, 0, 0, 0.001, 0, 0),
                            Affine.scale(12.0, 12.0),
                            Affine.rotate(math.radians(30)),
                            Affine.identity()])
        self.assertAlmostEqual(angle_deg_ccw(trm.x_axis), 30.0, places=9)


class T1_9_SpaceGraph(unittest.TestCase):
    """G6/G7 plus path and error behaviour."""

    def _graph(self):
        g = SpaceGraph()
        g.connect("glyph", "text", Affine(0.001, 0, 0, 0.001, 0, 0))
        g.connect("text", "user", Affine.chain([Affine.scale(10, 10),
                                                Affine.translate(72, 720)]))
        g.connect("user", "page", Affine.flip_y(792.0))
        g.connect("page", "render", Affine.scale(600 / 72.0, 600 / 72.0))
        return g

    def test_self_transform_is_identity(self):
        g = self._graph()
        self.assertTrue(g.transform("user", "user")
                        .approx_eq(Affine.identity(), 0.0))
        self.assertEqual(g.path("user", "user"), ["user"])

    def test_forward_and_reverse_are_inverses(self):
        g = self._graph()
        fwd = g.transform("glyph", "render")
        rev = g.transform("render", "glyph")
        self.assertTrue(fwd.then(rev).approx_eq(Affine.identity(), 1e-7))

    def test_path_matches_manual_composition(self):
        g = self._graph()
        manual = Affine.chain([
            Affine(0.001, 0, 0, 0.001, 0, 0),
            Affine.chain([Affine.scale(10, 10), Affine.translate(72, 720)]),
            Affine.flip_y(792.0),
            Affine.scale(600 / 72.0, 600 / 72.0),
        ])
        self.assertTrue(g.transform("glyph", "render").approx_eq(manual, 1e-9))

    def test_path_names(self):
        g = self._graph()
        self.assertEqual(g.path("glyph", "render"),
                         ["glyph", "text", "user", "page", "render"])

    def test_cache_returns_equal_result(self):
        g = self._graph()
        first = g.transform("glyph", "render")
        second = g.transform("glyph", "render")
        self.assertTrue(first.approx_eq(second, 0.0))

    def test_connect_invalidates_cache(self):
        g = self._graph()
        before = g.transform("page", "render")
        g.connect("page", "render", Affine.scale(300 / 72.0, 300 / 72.0))
        after = g.transform("page", "render")
        self.assertFalse(before.approx_eq(after, 1e-9))

    def test_unknown_space_raises(self):
        g = self._graph()
        with self.assertRaises(SpaceNotFound):
            g.transform("glyph", "nowhere")

    def test_disconnected_raises(self):
        g = self._graph()
        g.declare("island")
        with self.assertRaises(NoPath):
            g.transform("glyph", "island")

    def test_degenerate_edge_rejected(self):
        g = SpaceGraph()
        with self.assertRaises(DegenerateAffine):
            g.connect("a", "b", Affine(0, 0, 0, 0))

    def test_consistency_check_finds_bad_edge(self):
        g = self._graph()
        # a deliberately wrong shortcut: glyph -> render must equal the chain
        g.connect("glyph", "render", Affine.scale(1.0, 1.0))
        bad = g.check_consistency("glyph", "render")
        self.assertTrue(bad, "an inconsistent shortcut was not detected")

    def test_consistency_check_clean_graph(self):
        g = self._graph()
        self.assertEqual(g.check_consistency("glyph", "render"), [])

    def test_y_flip_orientation(self):
        """Crossing the y-flip must reverse orientation exactly once."""
        g = self._graph()
        self.assertFalse(g.transform("glyph", "user").decompose().flip)
        self.assertTrue(g.transform("glyph", "render").decompose().flip)


if __name__ == "__main__":
    unittest.main(verbosity=2)
