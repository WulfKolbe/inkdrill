"""Screen signals and the topology gate. Hermetic.

The screen fixtures are generated dot lattices at stated tones, because
the point of the module is that a detector must work in the HIGHLIGHTS
and a single dark fixture cannot show that.
"""

import unittest

from inkdrill.qc import (ScreenSignals, px_per_run, runs_per_area,
                         screen_signals, topology_of, topology_preserved,
                         topology_within)
from inkdrill.raster import InkMask


def screen(w, h, pitch, radius):
    """A dot lattice: `pitch` px between centres, dots of `radius`.

    Small radius is a highlight (isolated dots, no mesh); large radius
    is a shadow (dots merge, the white becomes the mesh).
    """
    buf = bytearray(w * h)
    r2 = radius * radius
    for cy in range(pitch // 2, h, pitch):
        for cx in range(pitch // 2, w, pitch):
            for dy in range(-radius, radius + 1):
                y = cy + dy
                if not 0 <= y < h:
                    continue
                for dx in range(-radius, radius + 1):
                    x = cx + dx
                    if 0 <= x < w and dx * dx + dy * dy <= r2:
                        buf[y * w + x] = 0xFF
    return InkMask(bytes(buf), w, h)


def textish(w, h):
    """Body text at 400 dpi, with the dimensions DERIVED not chosen.

    A 10 pt line at 400 dpi is ~56 px of leading, a glyph ~40 px tall
    and ~25 px of advance, and a glyph is about 9 runs. That gives
    9 / (25 * 56) = 0.0064 runs per pixel, against the 0.0085 measured
    on real pages -- the right order.

    The first version of this fixture put 4 px marks every 12 px on
    six-row bands 16 px apart and read 0.089 runs/px, TEN TIMES denser
    than the screen it was meant to be distinguished from, so the test
    asserted the separation backwards. A fixture whose dimensions came
    from nowhere is the tell.
    """
    buf = bytearray(w * h)
    for y in range(6, h - 40, 56):                 # leading
        for x in range(6, w - 25, 25):             # advance
            for dy in range(0, 40, 5):             # ~9 runs per glyph
                if y + dy < h:
                    buf[(y + dy) * w + x:(y + dy) * w + x + 14] = b"\xff" * 14
    return InkMask(bytes(buf), w, h)


def photo(w, h):
    """Large smooth blobs -- long runs, few of them."""
    buf = bytearray(w * h)
    for y in range(h):
        if (y // 40) % 2 == 0:
            buf[y * w + 10:y * w + w - 10] = b"\xff" * (w - 20)
    return InkMask(bytes(buf), w, h)


class QC_1_TheHighlightBlindSpot(unittest.TestCase):
    """Why `cycle_count` cannot be the gate."""

    def test_a_highlight_screen_has_NO_cycles(self):
        """The measured blind spot: isolated dots bridge nothing, so a
        cycles gate reports "not a halftone" for a pale screen."""
        s = screen_signals(screen(240, 240, 8, 1))
        self.assertEqual(s.cycles, 0)

    def test_but_it_still_has_a_high_run_density(self):
        """The channel that does see it."""
        s = screen_signals(screen(240, 240, 8, 1))
        self.assertGreater(s.runs_per_area, 0.01)

    def test_run_density_is_stable_across_the_tone_range(self):
        """Tone-independence is the claim, so it is the assertion. A
        dark screen and a pale one must land in the same band even
        though their cycle counts differ by orders of magnitude."""
        # radius 4 at pitch 8 gives diameter 9 > 8, so the dots MERGE
        # and a mesh exists. At radius 3 the diameter is 7 and they do
        # not -- the first version of this fixture was not dark at all,
        # and asserted a cycle count of 0 > 0.
        light = screen_signals(screen(240, 240, 8, 1))
        dark = screen_signals(screen(240, 240, 8, 4))
        self.assertGreater(light.runs_per_area, 0.005)
        self.assertGreater(dark.runs_per_area, 0.005)
        self.assertGreater(dark.cycles, light.cycles)

    def test_a_screen_separates_from_text_on_run_density(self):
        sc = screen_signals(screen(240, 240, 8, 1))
        tx = screen_signals(textish(240, 240))
        self.assertGreater(sc.runs_per_area, 3 * tx.runs_per_area)

    def test_a_screen_separates_from_a_photo_on_run_LENGTH(self):
        """The second discriminator: a lattice has short runs, a smooth
        tone has long ones, whatever their densities."""
        sc = screen_signals(screen(240, 240, 8, 2))
        ph = screen_signals(photo(240, 240))
        self.assertLess(sc.px_per_run, 12.0)
        self.assertGreater(ph.px_per_run, 100.0)


class QC_1b_RunLengthCV(unittest.TestCase):
    """The third channel -- reported, and NOT a separator here.

    The proposal was that a screen is a regular lattice so its run
    lengths are near-constant, against CV 8.4-9.5 for real text: a 21x
    separation on the pair the other channels overlap.

    **It does not reproduce on this definition.** CV over every run of a
    page reads 0.566-0.576 for a light synthetic screen and a MINIMUM of
    0.603 over real corpus pages, median 0.753 -- a 6% gap, not 21x.
    The published figures are presumably a different denominator (per
    component, or over a selected run set); on this one there is no
    separation to use.

    So the value is computed and reported and nothing is asserted about
    its discriminative power. These tests hold only what is mechanically
    true.
    """

    def test_a_uniform_lattice_gives_zero(self):
        m = InkMask(bytes([0xFF, 0xFF, 0, 0] * 16), 8, 8)
        self.assertEqual(screen_signals(m).run_length_cv, 0.0)

    def test_no_runs_gives_zero_rather_than_raising(self):
        self.assertEqual(screen_signals(InkMask(bytes(64), 8, 8)
                                        ).run_length_cv, 0.0)

    def test_varied_run_lengths_give_a_positive_CV(self):
        m = InkMask.from_rows(["#.....", "##....", "####..", "######"])
        self.assertGreater(screen_signals(m).run_length_cv, 0.0)

    def test_a_denser_screen_has_MORE_varied_runs_not_less(self):
        """The direction is the opposite of the proposal's intuition:
        as dots merge, run lengths spread rather than tighten."""
        light = screen_signals(screen(240, 240, 8, 1)).run_length_cv
        dark = screen_signals(screen(240, 240, 8, 4)).run_length_cv
        self.assertGreater(dark, light)


class QC_2_Signals(unittest.TestCase):
    """G1, G3: measurements, and no verdict."""

    def test_screen_signals_returns_no_classification(self):
        s = screen_signals(screen(80, 80, 8, 2))
        self.assertIsInstance(s, ScreenSignals)
        self.assertFalse(hasattr(s, "is_halftone"))

    def test_runs_per_area_matches_the_signals_object(self):
        m = screen(80, 80, 8, 2)
        self.assertAlmostEqual(runs_per_area(m), screen_signals(m).runs_per_area)

    def test_px_per_run_matches_the_signals_object(self):
        m = screen(80, 80, 8, 2)
        self.assertAlmostEqual(px_per_run(m), screen_signals(m).px_per_run)

    def test_an_empty_mask_answers_zero_rather_than_raising(self):
        m = InkMask(bytes(64), 8, 8)
        s = screen_signals(m)
        self.assertEqual((s.runs, s.ink_px), (0, 0))
        self.assertEqual((s.runs_per_area, s.px_per_run), (0.0, 0.0))

    def test_a_zero_extent_mask_answers_zero(self):
        self.assertEqual(runs_per_area(InkMask(b"", 0, 0)), 0.0)

    def test_a_supplied_sweep_result_is_reused(self):
        from inkdrill.sweep import Capture, sweep
        m = screen(80, 80, 8, 2)
        res = sweep(m, conn=8, capture=Capture.GRAPH)
        self.assertEqual(screen_signals(m, result=res).cycles,
                         screen_signals(m).cycles)


class QC_3_TopologyGate(unittest.TestCase):
    """G4, G5: the acceptance gate for a transform."""

    def _ring(self, w=40, h=40):
        buf = bytearray(w * h)
        for x in range(8, 32):
            buf[8 * w + x] = 0xFF
            buf[31 * w + x] = 0xFF
        for y in range(8, 32):
            buf[y * w + 8] = 0xFF
            buf[y * w + 31] = 0xFF
        return InkMask(bytes(buf), w, h)

    def test_an_identical_mask_passes(self):
        m = self._ring()
        self.assertTrue(topology_preserved(m, m))

    def test_a_translation_passes(self):
        m = self._ring()
        w, h = m.width, m.height
        buf = bytearray(w * h)
        for y in range(h - 2):
            buf[(y + 2) * w:(y + 2) * w + w - 2] = \
                m.data[y * w + 2:y * w + w]
        self.assertTrue(topology_preserved(m, InkMask(bytes(buf), w, h)))

    def test_breaking_the_ring_FAILS(self):
        """A transform that opens a closed contour has changed the page,
        and the cycle count is what notices."""
        m = self._ring()
        buf = bytearray(m.data)
        for x in range(18, 24):
            buf[8 * m.width + x] = 0
        self.assertFalse(topology_preserved(m, InkMask(bytes(buf),
                                                       m.width, m.height)))

    def test_merging_two_components_FAILS(self):
        a = InkMask(bytes([0xFF, 0, 0xFF]), 3, 1)
        b = InkMask(bytes([0xFF, 0xFF, 0xFF]), 3, 1)
        self.assertFalse(topology_preserved(a, b))

    def test_topology_of_reports_both_counts(self):
        self.assertEqual(topology_of(self._ring()), (1, 1))

    def test_two_empty_masks_are_trivially_preserving(self):
        m = InkMask(bytes(64), 8, 8)
        self.assertTrue(topology_preserved(m, m))
        self.assertEqual(topology_of(m), (0, 0))


class QC_4_ToleranceGate(unittest.TestCase):
    """G4's second form, for inputs where equality cannot hold."""

    def _blobs(self, n, w=80, h=20):
        buf = bytearray(w * h)
        for i in range(n):
            x = 2 + i * 3
            if x < w - 1:
                for y in range(4, 10):
                    buf[y * w + x] = 0xFF
        return InkMask(bytes(buf), w, h)

    def test_identical_masks_pass_at_any_tolerance(self):
        m = self._blobs(10)
        self.assertTrue(topology_within(m, m, tol=0.0))

    def test_a_small_change_passes_a_generous_tolerance(self):
        a, b = self._blobs(20), self._blobs(19)      # 5% fewer
        self.assertTrue(topology_within(a, b, tol=0.10))

    def test_the_same_change_FAILS_a_tight_one(self):
        a, b = self._blobs(20), self._blobs(19)
        self.assertFalse(topology_within(a, b, tol=0.01))

    def test_tol_zero_reduces_to_exact_equality(self):
        """The convergence property: the tolerance gate must BE the
        exact gate at zero, or it is a different check wearing the
        same name."""
        for n, k in ((10, 10), (10, 9), (10, 4)):
            a, b = self._blobs(n), self._blobs(k)
            with self.subTest(n=n, k=k):
                self.assertEqual(topology_within(a, b, tol=0.0),
                                 topology_preserved(a, b))

    def test_the_CYCLE_channel_is_compared_too(self):
        """Every other fixture here has zero cycles, so comparing only
        components passed them all. A ring pair with identical component
        counts and different hole counts is what separates them."""
        def rings(n, w=90, h=24):
            buf = bytearray(w * h)
            for i in range(n):
                ox = 2 + i * 12
                for x in range(ox, ox + 9):
                    buf[4 * w + x] = 0xFF
                    buf[19 * w + x] = 0xFF
                for y in range(4, 20):
                    buf[y * w + ox] = 0xFF
                    buf[y * w + ox + 8] = 0xFF
            return InkMask(bytes(buf), w, h)

        def bars(n, w=90, h=24):
            buf = bytearray(w * h)
            for i in range(n):
                ox = 2 + i * 12
                for y in range(4, 20):
                    for x in range(ox, ox + 9):
                        buf[y * w + x] = 0xFF
            return InkMask(bytes(buf), w, h)

        a, b = rings(6), bars(6)
        self.assertEqual(topology_of(a)[0], topology_of(b)[0])
        self.assertNotEqual(topology_of(a)[1], topology_of(b)[1])
        self.assertFalse(topology_within(a, b, tol=0.10))

    def test_a_negative_tolerance_raises(self):
        m = self._blobs(4)
        with self.assertRaises(ValueError):
            topology_within(m, m, tol=-0.1)

    def test_two_empty_masks_pass(self):
        m = InkMask(bytes(64), 8, 8)
        self.assertTrue(topology_within(m, m, tol=0.0))

    def test_the_tolerance_is_RELATIVE_not_absolute(self):
        """1 component of 4 is a 25% change; 1 of 40 is 2.5%. An
        absolute gate would treat them alike and a page-size change
        would silently retune it -- the normalisation rule again."""
        self.assertFalse(topology_within(self._blobs(4), self._blobs(3),
                                         tol=0.10))
        self.assertTrue(topology_within(self._blobs(40), self._blobs(39),
                                        tol=0.10))


if __name__ == "__main__":
    unittest.main()
