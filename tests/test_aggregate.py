"""Unit 5 tests. Every test name is quoted verbatim in the status report."""

import math
import random
import unittest

from inkdrill.aggregate import (PIXEL_VARIANCE, Moments, component_moments,
                                moments_of_mask, moments_per_component)
from inkdrill.raster import BG, INK, InkMask, InvalidAxis
from inkdrill.space import angle_deg_ccw, angle_deg_screen
from inkdrill.sweep import Capture, sweep


def m(rows):
    return InkMask.from_rows(rows)


def random_mask(rng, w, h, density=0.4):
    return InkMask(bytes(INK if rng.random() < density else BG
                         for _ in range(w * h)), w, h)


def brute_moments(mask):
    """Per-pixel accumulation. The independent oracle for the closed-form
    run accumulation -- deliberately the obvious slow way."""
    a = sx = sy = sxx = syy = sxy = 0
    for y in range(mask.height):
        for x in range(mask.width):
            if mask.at(x, y):
                a += 1
                sx += x
                sy += y
                sxx += x * x
                syy += y * y
                sxy += x * y
    return (a, sx, sy, sxx, syy, sxy)


def raw(mo):
    return (mo.area, mo.sx, mo.sy, mo.sxx, mo.syy, mo.sxy)


class T5_1_ClosedFormAccumulation(unittest.TestCase):

    def test_closed_form_matches_a_per_pixel_oracle(self):
        """G1. The closed form is the whole point of accumulating over
        runs; if it disagrees with per-pixel summation it is worthless."""
        rng = random.Random(20260807)
        for trial in range(120):
            w = rng.randint(1, 22)
            h = rng.randint(1, 22)
            mask = random_mask(rng, w, h)
            with self.subTest(trial=trial, w=w, h=h):
                self.assertEqual(raw(moments_of_mask(mask, "row")),
                                 brute_moments(mask))

    def test_every_raw_sum_is_an_exact_integer(self):
        """G1: no float may enter before a ratio is taken. A float here
        would make G2 approximate instead of exact."""
        rng = random.Random(5)
        mo = moments_of_mask(random_mask(rng, 17, 13))
        for name in ("area", "sx", "sy", "sxx", "syy", "sxy"):
            with self.subTest(name):
                self.assertIsInstance(getattr(mo, name), int)

    def test_hand_computed_values_on_a_small_fixture(self):
        # A 3x2 solid block at the origin.
        mask = m(["###", "###"])
        mo = moments_of_mask(mask)
        self.assertEqual(mo.area, 6)
        self.assertEqual(mo.sx, 2 * (0 + 1 + 2))          # each row
        self.assertEqual(mo.sy, 3 * (0 + 1))              # each column
        self.assertEqual(mo.sxx, 2 * (0 + 1 + 4))
        self.assertEqual(mo.syy, 3 * (0 + 1))
        self.assertEqual(mo.sxy, (0 + 1 + 2) * (0 + 1))
        self.assertEqual(mo.centroid, (1.5, 1.0))         # centres

    def test_extents_are_inclusive_and_bbox_is_half_open(self):
        mask = m(["...", ".##", ".##"])
        mo = moments_of_mask(mask)
        self.assertEqual((mo.x0, mo.y0, mo.x1, mo.y1), (1, 1, 2, 2))
        self.assertEqual(mo.bbox, (1, 1, 3, 3))
        self.assertEqual((mo.width, mo.height), (2, 2))

    def test_bad_axis_is_refused(self):
        with self.assertRaises(InvalidAxis):
            moments_of_mask(m(["#"]), "diagonal")

    def test_empty_mask_has_no_centroid(self):
        mo = moments_of_mask(m(["..", ".."]))
        self.assertEqual(mo.area, 0)
        with self.assertRaises(ValueError):
            mo.centroid


class T5_2_AxisInvariance(unittest.TestCase):
    """G2, and docs/units.md assumption 4. U2 proves the pixel SETS
    agree; that the moments agree does not follow from that, it follows
    from the sums being exact integers."""

    def test_whole_mask_moments_are_identical_across_axes(self):
        rng = random.Random(11)
        for trial in range(150):
            w = rng.randint(1, 20)
            h = rng.randint(1, 20)
            mask = random_mask(rng, w, h)
            with self.subTest(trial=trial, w=w, h=h):
                self.assertEqual(raw(moments_of_mask(mask, "row")),
                                 raw(moments_of_mask(mask, "col")))

    def test_per_component_moments_are_identical_across_axes(self):
        """The stronger claim: not just the totals, but the partition."""
        rng = random.Random(2026)
        for trial in range(120):
            w = rng.randint(2, 18)
            h = rng.randint(2, 18)
            mask = random_mask(rng, w, h, density=0.35)
            with self.subTest(trial=trial, w=w, h=h):
                self.assertEqual([raw(x) for x in component_moments(mask, "row")],
                                 [raw(x) for x in component_moments(mask, "col")])

    def test_axis_invariance_holds_on_the_u3_fixtures(self):
        fixtures = (["#####", "#...#", "#...#", "#...#", "#####"],
                    ["..#..", ".#.#.", "#####", "#...#", "#...#"],
                    ["#...#", "#...#", "#####", "#...#", "#...#"],
                    ["#######", "#.....#", "#.###.#", "#.#.#.#",
                     "#.###.#", "#.....#", "#######"])

        for rows in fixtures:
            with self.subTest(rows[0]):
                self.assertEqual([raw(x) for x in component_moments(m(rows), "row")],
                                 [raw(x) for x in component_moments(m(rows), "col")])


class T5_3_CentralMomentsAndTranslation(unittest.TestCase):

    def test_central_moments_are_exactly_translation_invariant(self):
        """G4."""
        rows = ["..#..", ".###.", "#####", ".#.#."]
        base = moments_of_mask(m(rows)).central
        for pad_t, pad_l in ((1, 0), (0, 3), (4, 6)):
            w = len(rows[0]) + pad_l
            moved = ["." * w] * pad_t + ["." * pad_l + r for r in rows]
            with self.subTest(pad=(pad_t, pad_l)):
                got = moments_of_mask(m(moved)).central
                for a, b in zip(base, got):
                    self.assertAlmostEqual(a, b, places=12)

    def test_translated_matches_an_actually_translated_mask(self):
        rows = ["..#..", ".###.", "#####"]
        mo = moments_of_mask(m(rows))
        dx, dy = 5, 3
        w = len(rows[0]) + dx
        moved = ["." * w] * dy + ["." * dx + r for r in rows]
        self.assertEqual(raw(mo.translated(dx, dy)),
                         raw(moments_of_mask(m(moved))))

    def test_centroid_uses_pixel_centres(self):
        """G3: a single pixel at the origin is centred at (0.5, 0.5), not
        at (0, 0) -- the convention that removes the +-0.5 ambiguity."""
        self.assertEqual(moments_of_mask(m(["#"])).centroid, (0.5, 0.5))


class T5_4_PrincipalAxis(unittest.TestCase):

    def test_a_horizontal_rule_points_along_x(self):
        """G5: a unit vector, never an angle."""
        mo = moments_of_mask(m(["#" * 40]))
        vx, vy = mo.principal_axis
        self.assertAlmostEqual(math.hypot(vx, vy), 1.0, places=12)
        self.assertAlmostEqual(abs(vx), 1.0, places=9)
        self.assertAlmostEqual(vy, 0.0, places=9)

    def test_a_vertical_rule_points_along_y(self):
        mo = moments_of_mask(m(["#"] * 40))
        vx, vy = mo.principal_axis
        self.assertAlmostEqual(math.hypot(vx, vy), 1.0, places=12)
        self.assertAlmostEqual(vx, 0.0, places=9)
        self.assertAlmostEqual(abs(vy), 1.0, places=9)

    def test_the_axis_is_always_a_unit_vector(self):
        rng = random.Random(7)
        for trial in range(60):
            mask = random_mask(rng, rng.randint(2, 16), rng.randint(2, 16))
            if mask.ink_count == 0:
                continue
            with self.subTest(trial=trial):
                vx, vy = moments_of_mask(mask).principal_axis
                self.assertAlmostEqual(math.hypot(vx, vy), 1.0, places=12)

    def test_the_sign_is_canonical(self):
        """Without this two runs over the same shape could return
        opposite vectors and every comparison downstream is a coin flip."""
        rng = random.Random(3)
        for trial in range(60):
            mask = random_mask(rng, rng.randint(2, 14), rng.randint(2, 14))
            if mask.ink_count == 0:
                continue
            with self.subTest(trial=trial):
                vx, vy = moments_of_mask(mask).principal_axis
                self.assertTrue(vx > 0 or (vx == 0.0 and vy >= 0),
                                f"non-canonical sign ({vx}, {vy})")

    def test_a_rotated_rule_recovers_its_angle_through_angle_deg_screen(self):
        """The axis is a vector; `space.angle_deg_screen` is the only
        sanctioned way to turn it into degrees, and it names its
        convention (y-down, image space).

        The sign here is the whole reason U1 forbids stored angles. The
        fixture's direction in INDEX space is (cos t, sin t) -- right and
        DOWNWARD, because raster y grows downward. A reader sees that as
        a clockwise slope, so the screen convention reports -t, not +t.
        The first draft of this test asserted +t and failed on every
        non-zero angle."""
        for want in (0.0, 15.0, 30.0, 45.0, 60.0, 75.0):
            n = 240
            t = math.radians(want)
            pts = {(int(round(i * math.cos(t))), int(round(i * math.sin(t))))
                   for i in range(n)}
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            w = max(xs) - min(xs) + 1
            h = max(ys) - min(ys) + 1
            buf = bytearray(w * h)
            for x, y in pts:
                buf[(y - min(ys)) * w + (x - min(xs))] = INK
            mo = moments_of_mask(InkMask(bytes(buf), w, h))
            got = angle_deg_screen(mo.principal_axis) % 180.0
            with self.subTest(want=want):
                self.assertAlmostEqual(got, (-want) % 180.0, delta=1.0)
                # and the y-up producer reports the opposite sign
                self.assertAlmostEqual(
                    angle_deg_ccw(mo.principal_axis) % 180.0,
                    want % 180.0, delta=1.0)


class T5_5_ElongationFloor(unittest.TestCase):

    def test_the_floor_engages_exactly_at_one_pixel_width(self):
        """G6. A floor that engaged at 2 px would quietly flatten every
        thin stroke in the corpus, so the boundary is the test."""
        one = moments_of_mask(m(["#"] * 30))
        _, l2_one = one.eigenvalues
        self.assertEqual(l2_one, PIXEL_VARIANCE)          # engaged

        two = moments_of_mask(m(["##"] * 30))
        _, l2_two = two.eigenvalues
        self.assertGreater(l2_two, PIXEL_VARIANCE)        # did not engage
        self.assertAlmostEqual(l2_two, 0.25, places=12)   # variance of {0,1}

    def test_elongation_is_finite_for_a_one_pixel_stroke(self):
        e = moments_of_mask(m(["#"] * 50)).elongation
        self.assertTrue(math.isfinite(e))
        self.assertGreater(e, 10.0)

    def test_elongation_is_one_for_a_square(self):
        self.assertAlmostEqual(moments_of_mask(m(["####"] * 4)).elongation,
                               1.0, places=9)

    def test_elongation_is_finite_for_every_single_pixel(self):
        mo = moments_of_mask(m(["#"]))
        self.assertTrue(math.isfinite(mo.elongation))
        self.assertAlmostEqual(mo.elongation, 1.0, places=12)

    def test_a_longer_stroke_is_more_elongated(self):
        short = moments_of_mask(m(["#"] * 10)).elongation
        long = moments_of_mask(m(["#"] * 40)).elongation
        self.assertGreater(long, short)


class T5_6_MomentsAdd(unittest.TestCase):
    """G7: the algebra U7 will stitch bands with."""

    def test_disjoint_components_sum_to_the_whole(self):
        rng = random.Random(1234)
        for trial in range(60):
            w = rng.randint(3, 18)
            h = rng.randint(3, 18)
            mask = random_mask(rng, w, h, density=0.3)
            if mask.ink_count == 0:
                continue
            res = sweep(mask, axis="row", conn=8, capture=Capture.GRAPH)
            total = moments_of_mask(mask)
            acc = Moments(0, 0, 0, 0, 0, 0, 0, 0, -1, -1)
            for mo in moments_per_component(res).values():
                acc = acc + mo
            with self.subTest(trial=trial):
                self.assertEqual(raw(acc), raw(total))

    def test_addition_is_exact_not_approximate(self):
        a = moments_of_mask(m(["###", "###"]))
        b = moments_of_mask(m(["#"]))
        s = a + b
        self.assertIsInstance(s.sxx, int)
        self.assertEqual(s.area, a.area + b.area)
        self.assertEqual(s.sxy, a.sxy + b.sxy)

    def test_adding_an_empty_aggregate_changes_nothing(self):
        a = moments_of_mask(m(["###", "###"]))
        empty = Moments(0, 0, 0, 0, 0, 0, 0, 0, -1, -1)
        self.assertEqual(raw(a + empty), raw(a))
        self.assertEqual(raw(empty + a), raw(a))

    def test_addition_takes_the_union_of_extents(self):
        a = moments_of_mask(m(["#..", "...", "..."]))
        b = moments_of_mask(m(["...", "...", "..#"]))
        s = a + b
        self.assertEqual((s.x0, s.y0, s.x1, s.y1), (0, 0, 2, 2))


if __name__ == "__main__":
    unittest.main()
