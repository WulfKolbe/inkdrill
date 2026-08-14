"""S4: the self-referential bench -- transport against resample.

Hermetic, and scored on synthetic pages where the true topology is known
by construction. No undistorted reference is used by either path, which
is what makes the comparison runnable on unstable input.
"""

import math
import unittest

from inkdrill.raster import InkMask
from inkdrill.qc import topology_of
from inkdrill.warp import (Comparison, compare, corner_affine, resample,
                           transport)

IDENT = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def rings(n, w=120, h=40, thin=1):
    """`n` rectangular rings -- 1 component and 1 hole each, so both
    channels of the topology are exercised."""
    buf = bytearray(w * h)
    for i in range(n):
        ox = 3 + i * 20
        for t in range(thin):
            for x in range(ox, ox + 14):
                buf[(5 + t) * w + x] = 0xFF
                buf[(34 - t) * w + x] = 0xFF
            for y in range(5, 35):
                buf[y * w + ox + t] = 0xFF
                buf[y * w + ox + 13 - t] = 0xFF
    return InkMask(bytes(buf), w, h)


def rotation(deg, cx, cy):
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    return (c, -s, s, c,
            cx - c * cx + s * cy, cy - s * cx - c * cy)


class S4_1_Identity(unittest.TestCase):
    """G5: the identity must be a fixed point of transport."""

    def test_transport_under_the_identity_returns_the_mask(self):
        m = rings(4)
        self.assertEqual(transport(m, IDENT), m)

    def test_which_is_the_check_that_transport_is_not_resampling(self):
        """A resampler returns the mask under the identity too -- but
        only because the sample points land exactly. The property that
        distinguishes them is what happens off-grid, below."""
        m = rings(4)
        self.assertEqual(topology_of(transport(m, IDENT)), topology_of(m))


class S4_2_TheThesis(unittest.TestCase):
    """The thesis is NOT demonstrated on these fixtures, and that is
    recorded rather than tuned away.

    Measured on rectangular rings at 1 px stroke, rotated about the
    page centre:

        deg 0    transported (4, 4)   resampled (4, 4)
        deg 3    transported (4, 4)   resampled (4, 4)
        deg 7    transported (4, 3)   resampled (4, 3)

    **The two paths agree at every angle tried**, and where topology is
    lost at 7 degrees both lose the same hole -- to the page edge, not
    to sampling. So this fixture cannot separate transport from
    resampling, and the ordering claim is untested here.

    A fixture could be shaped until it showed a difference. That would
    be choosing the answer, which is the failure this project has found
    six times, so the machinery is shipped with the question open and
    the real bench is DocReal at a valley threshold.
    """

    def test_both_paths_agree_on_this_fixture(self):
        m = rings(4, thin=1)
        for deg in (0.0, 3.0, 7.0):
            with self.subTest(deg=deg):
                c = compare(m, rotation(deg, 60, 20))
                self.assertEqual(c.transported, c.resampled)

    def test_neither_path_touches_an_undistorted_reference(self):
        """The property that makes the bench runnable on unstable input:
        both take the same mask and the same transform, so a threshold
        wrong for the page is wrong for both identically."""
        m = rings(4, thin=1)
        c = compare(m, rotation(7.0, 60, 20))
        self.assertEqual(c.source, topology_of(m))

    def test_loss_at_seven_degrees_is_the_page_edge_not_sampling(self):
        """Both paths lose the same hole, which is what says the cause
        is clipping rather than interpolation."""
        m = rings(4, thin=1)
        c = compare(m, rotation(7.0, 60, 20))
        self.assertEqual(c.transported, c.resampled)
        self.assertNotEqual(c.transported, c.source)


class S4_3_Mechanics(unittest.TestCase):

    def test_a_run_is_drawn_as_a_connected_line(self):
        """G2: a horizontal run under a rotation must not become dots."""
        buf = bytearray(40 * 20)
        for x in range(4, 36):
            buf[10 * 40 + x] = 0xFF
        m = InkMask(bytes(buf), 40, 20)
        got = transport(m, rotation(30.0, 20, 10))
        self.assertEqual(topology_of(got)[0], 1, "the run broke into pieces")

    def test_resample_refuses_a_singular_transform(self):
        with self.assertRaises(ValueError):
            resample(rings(2), (0.0, 0.0, 0.0, 0.0, 0.0, 0.0))

    def test_both_paths_get_the_same_output_extent(self):
        m = rings(3)
        phi = rotation(5.0, 60, 20)
        a = transport(m, phi, width=200, height=60)
        b = resample(m, phi, width=200, height=60)
        self.assertEqual((a.width, a.height), (b.width, b.height))
        self.assertEqual((a.width, a.height), (200, 60))

    def test_drift_is_zero_when_the_topology_matches(self):
        c = Comparison((10, 4), (10, 4), (7, 1))
        self.assertEqual(c.transport_drift, (0.0, 0.0))
        self.assertGreater(max(c.resample_drift), 0.0)
        self.assertTrue(c.transport_is_nearer)

    def test_compare_draws_no_conclusion_itself(self):
        """G6: it reports three topologies; the ordering is a property a
        caller reads, not a verdict the function returns."""
        c = compare(rings(2), IDENT)
        self.assertIsInstance(c, Comparison)
        self.assertFalse(hasattr(c, "verdict"))


class S4_4_CrudePhi(unittest.TestCase):

    def test_matched_corners_recover_a_known_affine(self):
        want = (1.1, 0.05, -0.02, 0.95, 3.0, -2.0)
        src = [(0, 0), (100, 0), (0, 60), (100, 60)]
        dst = [(want[0] * x + want[1] * y + want[4],
                want[2] * x + want[3] * y + want[5]) for x, y in src]
        got = corner_affine(src, dst)
        for a, b in zip(got, want):
            self.assertAlmostEqual(a, b, places=6)

    def test_degenerate_points_raise(self):
        with self.assertRaises(ValueError):
            corner_affine([(0, 0), (0, 1), (0, 2)], [(0, 0), (0, 1), (0, 2)])

    def test_too_few_points_raise(self):
        with self.assertRaises(ValueError):
            corner_affine([(0, 0)], [(1, 1)])

    def test_a_crude_phi_runs_through_both_paths_identically(self):
        """Both paths get the SAME crude phi, so its inaccuracy moves
        both answers together and cannot change their order -- which is
        why the bench does not wait on an accurate warp model, even
        though these fixtures do not yet separate the paths."""
        m = rings(4, thin=1)
        crude = corner_affine([(0, 0), (119, 0), (0, 39), (119, 39)],
                              [(2, 1), (118, 3), (1, 38), (117, 39)])
        c = compare(m, crude)
        self.assertEqual(c.source, topology_of(m))
        # `None` is a legitimate verdict -- see T-S4_5 -- so the type
        # is bool OR None and asserting `bool` alone would forbid the
        # answer real ink usually gives.
        self.assertIn(c.transport_is_nearer, (True, False, None))


class TS4_5_TheVerdictIsPerChannel(unittest.TestCase):
    """The summary used to be `max(transport_drift) < max(resample_drift)`.

    That is a decision disguised as a metric: with two channels it has
    to pick one to believe, and `max` picks whichever is WORSE. On real
    DocReal ink transport tracked components while multiplying cycles by
    an order of magnitude, so the single boolean reported "not nearer"
    on the strength of the channel that was losing and hid the one that
    was winning.
    """

    def test_agreeing_channels_give_a_boolean(self):
        c = Comparison((100, 10), (100, 10), (70, 4))
        self.assertEqual(c.nearer_by_channel, (True, True))
        self.assertIs(c.transport_is_nearer, True)

    def test_agreeing_the_other_way_gives_False(self):
        """Both sides of the boolean, so it cannot be a constant."""
        c = Comparison((100, 10), (70, 4), (100, 10))
        self.assertEqual(c.nearer_by_channel, (False, False))
        self.assertIs(c.transport_is_nearer, False)

    def test_DISAGREEING_channels_give_None_not_a_guess(self):
        """The real-ink case, and the whole point. Components track and
        cycles blow up: the honest answer is that this page does not
        order the two paths."""
        c = Comparison(source=(436, 180), transported=(408, 2238),
                       resampled=(337, 188))
        self.assertEqual(c.nearer_by_channel, (True, False))
        self.assertIsNone(c.transport_is_nearer)

    def test_the_per_channel_drifts_are_still_readable(self):
        """`None` must not hide the numbers -- a caller needing one
        boolean has to decide what to do with the disagreement, and it
        can only do that if both drifts are available."""
        c = Comparison((436, 180), (408, 2238), (337, 188))
        self.assertLess(c.transport_drift[0], c.resample_drift[0])
        self.assertGreater(c.transport_drift[1], c.resample_drift[1])


if __name__ == "__main__":
    unittest.main()
