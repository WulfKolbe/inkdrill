"""Page 7 of 2409.18839: a grey-framed document image, found two ways.

The frame is drawn in grey (luma 153), not black. It is ink at any
threshold above ~154 and background below it. This page pins BOTH
routes, because either alone has a failure mode the other does not
share:

  ink route    finds the frame itself; fails if the threshold is set
               below the grey value (measured: 0 frames at 128)
  white route  finds the enclosed white interior; independent of the
               frame's colour entirely

Measured on the page at 400 dpi, threshold 200: the ink frame is
385.56 x 443.70 pt and the white interior 377.8 x 435.2 pt, so the
border is about 4 pt on each side.

TWO CORRECTIONS to the first version of this file, both found by
running it rather than reading it:

  * `test_the_two_routes_agree` never ran the white route. It compared
    the ink frame to the INNER_PT constant, so breaking the white route
    entirely left it green -- verified by mutation. The white route is
    now computed once, by `_white_interior`, and both tests call it.
  * Every filter was in PAGE PIXELS while every assertion was in
    points, so the file silently required ~150 dpi. At 120 dpi four of
    the five tests failed on the fixture rather than on the code. The
    filters are now in points and the same numbers hold at 150, 200 and
    400 dpi.

OPT-IN: needs the rasterised page. INKDRILL_PAGE7 names it.

    gs -q -dNOPAUSE -dBATCH -sDEVICE=png16m -r400 \\
       -dFirstPage=7 -dLastPage=7 -sOutputFile=p7.png 2409.18839.pdf
    INKDRILL_PAGE7=p7.png python3 -m unittest tests.test_page7_grey_frame
"""

import os
import pathlib
import unittest

from inkdrill.aggregate import moments_per_component
from inkdrill.pngio import read_png
from inkdrill.raster import InkMask, binarize, iter_runs
from inkdrill.sweep import sweep

PAGE = pathlib.Path(os.environ.get("INKDRILL_PAGE7", ""))

#: Measured, ink route, threshold 200. The frame grows with the
#: threshold -- 383.76 pt at 154 to 387.00 pt at 250 -- so the tolerance
#: below has to cover that 3.2 pt spread and nothing wider.
FRAME_PT = (385.6, 443.7)
#: Measured, white route, same threshold.
INNER_PT = (377.8, 435.2)
#: Shared, so a tolerance cannot be widened past the distinction it
#: exists to preserve: the two routes differ by ~7.8 pt in width, and
#: `test_the_constants_are_further_apart_than_the_tolerance` holds this.
DELTA_PT = 3.0

#: Filters in POINTS, converted to pixels per fixture. In page pixels
#: they are silently retuned by dpi -- the 800 px original excluded the
#: frame itself below 144 dpi.
MIN_FRAME_PT = 144.0        # 800 px at 400 dpi
MIN_INNER_PT = 270.0        # 1500 px at 400 dpi
MIN_GAP_PT = 7.2            # 40 px at 400 dpi
MAX_FILL = 0.35


@unittest.skipUnless(PAGE.is_file(), "set INKDRILL_PAGE7")
class T_Page7GreyFrame(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.img = read_png(PAGE)
        cls.pt = 72.0 / cls.img.dpi[0]

    # ---- the two routes, each computed in exactly one place ----------

    def _mask(self, th):
        i = self.img
        return binarize(i.gray, i.width, i.height, threshold=th)

    def _ink_frames(self, th):
        """Hollow components big enough to be the frame, largest first.

        `fill` is what separates a frame from a filled block, and the
        cycle count is what separates it from an open stroke.
        """
        m = self._mask(th)
        res = sweep(m)
        mo = moments_per_component(res)
        cyc = {c.root: c.cycle_count for c in res.components}
        floor = MIN_FRAME_PT / self.pt
        got = [x for cid, x in mo.items()
               if x.area / (x.width * x.height) < MAX_FILL
               and min(x.width, x.height) >= floor
               and cyc.get(cid, 0) >= 1]
        return sorted(got, key=lambda x: -x.width * x.height)

    def _white_interior(self, th):
        """Ink-bounded white runs, blobbed; the large regions only.

        A white run touching a scan-line edge is a margin rather than a
        gap -- keeping those connects the page into one blob.
        """
        m = self._mask(th)
        W, H = m.width, m.height
        inv = m.inverted()
        buf = bytearray(W * H)
        min_gap = MIN_GAP_PT / self.pt
        for axis in ("row", "col"):
            limit = W if axis == "row" else H
            for r in iter_runs(inv, axis):
                n = r.hi - r.lo + 1
                if r.lo == 0 or r.hi == limit - 1 or n < min_gap:
                    continue
                if axis == "row":
                    b = r.line * W
                    buf[b + r.lo:b + r.hi + 1] = b"\xff" * n
                else:
                    buf[r.lo * W + r.line:r.hi * W + r.line + 1:W] = \
                        b"\xff" * n
        mo = moments_per_component(sweep(InkMask(bytes(buf), W, H), conn=8))
        floor = MIN_INNER_PT / self.pt
        return [x for x in mo.values()
                if x.width > floor and x.height > floor]

    # ---- the ink route ----------------------------------------------

    def test_the_grey_frame_is_ink_above_its_own_luma(self):
        """One hollow component with at least one hole, at 160/200/240.

        The frame grows with the threshold because more of the grey's
        antialiased edge is admitted; 3.2 pt across the whole usable
        range, which is why one constant serves all three.
        """
        for th in (160, 200, 240):
            with self.subTest(threshold=th):
                frames = self._ink_frames(th)
                self.assertTrue(frames, "no hollow frame found")
                big = frames[0]
                self.assertAlmostEqual(big.width * self.pt, FRAME_PT[0],
                                       delta=DELTA_PT)
                self.assertAlmostEqual(big.height * self.pt, FRAME_PT[1],
                                       delta=DELTA_PT)

    def test_a_large_FILLED_block_is_not_a_frame(self):
        """The `fill` filter, asserted rather than assumed.

        Deleting it changed nothing, because the only assertion looked
        at the LARGEST candidate and the filled blocks on this page are
        smaller than the frame. But the page does contain them -- two
        halftone images, 152 x 183 pt at fill 0.90 and 0.75 -- so the
        filter has something to discriminate against and its effect can
        be seen by checking what is ABSENT from the list.
        """
        res = sweep(self._mask(200))
        mo = moments_per_component(res)
        floor = MIN_FRAME_PT / self.pt
        filled = [x for x in mo.values()
                  if min(x.width, x.height) >= floor
                  and x.area / (x.width * x.height) > 0.7]
        self.assertEqual(len(filled), 2,
                         "the page must contain large filled blocks or "
                         "this test discriminates against nothing")
        boxes = {(round(x.width), round(x.height))
                 for x in self._ink_frames(200)}
        for x in filled:
            self.assertNotIn((round(x.width), round(x.height)), boxes)

    def test_the_ink_route_LOSES_the_frame_below_the_grey(self):
        """The recorded failure mode, and the reason the white route
        exists -- a stated limit, not a defect. Grey is luma 153, so at
        128 the frame is background and the ink route finds nothing."""
        self.assertEqual(self._ink_frames(128), [],
                         "expected the grey to fall below threshold")

    # ---- the white route --------------------------------------------

    def test_the_white_route_finds_the_same_object(self):
        """It finds the frame's INTERIOR, inset by the border on each
        side, so it is smaller than the ink frame -- and that difference
        is the border thickness."""
        big = self._white_interior(200)
        self.assertEqual(len(big), 1, "expected one large white region")
        self.assertAlmostEqual(big[0].width * self.pt, INNER_PT[0],
                               delta=DELTA_PT)
        self.assertAlmostEqual(big[0].height * self.pt, INNER_PT[1],
                               delta=DELTA_PT)

    # ---- the two together, which is the point ------------------------

    def test_the_two_routes_agree_within_the_border_width(self):
        """BOTH routes are run here. The first version compared the ink
        frame to the `INNER_PT` constant and called that agreement --
        breaking the white route left this test green, which mutation
        showed.

        The white interior must sit inside the ink frame by roughly the
        stroke on each side. If they disagree by more, one of them is
        finding a different object.
        """
        frame = self._ink_frames(200)[0]
        inner = self._white_interior(200)[0]
        inset_w = (frame.width - inner.width) * self.pt / 2
        inset_h = (frame.height - inner.height) * self.pt / 2
        self.assertGreater(inset_w, 0.0,
                           "white interior must be inside the frame")
        self.assertLess(inset_w, 10.0, "inset larger than any border")
        self.assertAlmostEqual(inset_w, inset_h, delta=2.0,
                               msg="inset should be symmetric")

    def test_the_constants_are_further_apart_than_the_tolerance(self):
        """A tolerance is a guarantee too. `DELTA_PT` must not be wide
        enough to let the ink frame satisfy the white route's constant
        -- otherwise the two tests above would pass on one route."""
        for a, b in zip(FRAME_PT, INNER_PT):
            self.assertGreater(abs(a - b), 2 * DELTA_PT)

    # ---- end to end ---------------------------------------------------

    def test_the_page_emits_the_frame_as_a_diagram(self):
        """The frame must reach `lines.json`, not merely exist inside
        the sweep -- this catches an emit-path gap rather than a
        detection gap. It also exercises the containment rule: the
        frame encloses 103 separate ink components, which is why it
        survives as a `diagram`."""
        from inkdrill.emit import page_lines
        lines = page_lines(self._mask(200), pt=self.pt)
        wide = [l for l in lines if l["region"]["width"] > 300]
        self.assertEqual(len(wide), 1)
        self.assertEqual(wide[0]["type"], "diagram")
        self.assertAlmostEqual(wide[0]["region"]["width"], FRAME_PT[0],
                               delta=DELTA_PT)
        self.assertGreater(wide[0]["ink"]["contains"], 1)
