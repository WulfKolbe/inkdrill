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
        # BOTH routes contribute, so this page carries two wide lines:
        # the frame from the ink route and a content block from the gap
        # route. Asserting exactly one was right before the second route
        # was wired and is now a change detector.
        diagrams = [l for l in wide if l["type"] == "diagram"]
        self.assertEqual(len(diagrams), 1)
        self.assertEqual(diagrams[0]["ink"]["route"], "ink")
        self.assertAlmostEqual(diagrams[0]["region"]["width"], FRAME_PT[0],
                               delta=DELTA_PT)
        self.assertGreater(diagrams[0]["ink"]["contains"], 1)
        blocks = [l for l in wide if l["type"] == "block"]
        self.assertTrue(blocks, "the gap route contributed nothing")
        self.assertEqual(blocks[0]["ink"]["route"], "white")

    def test_the_INTERIOR_is_the_frames_hole_not_a_second_route(self):
        """A correction to this file's own premise.

        It claimed the ink route finds the frame and "the white route"
        its interior, two routes on one object. Measured: the frame's
        HOLE is 377.8 x 435.2 pt -- exactly the INNER_PT this file
        recovered by blobbing white runs. `nest` had both numbers all
        along, and the border is (frame - hole) / 2 from ONE component.

        The genuine second route -- content between ink -- finds
        different objects on this page (349.9 x 170.5 pt and the two
        halftones), which is why it is worth having and why it is not
        what this pair of numbers demonstrates.
        """
        from inkdrill.nest import nest
        from inkdrill.emit import ink_regions
        n = nest(self._mask(200))
        frame = max(ink_regions(n),
                    key=lambda r: (r.x1 - r.x0) * (r.y1 - r.y0))
        holes = n.holes_of(frame.id)
        self.assertEqual(len(holes), 1)
        hr = n.regions[holes[0]]
        self.assertAlmostEqual((hr.x1 - hr.x0 + 1) * self.pt, INNER_PT[0],
                               delta=DELTA_PT)
        self.assertAlmostEqual((hr.y1 - hr.y0 + 1) * self.pt, INNER_PT[1],
                               delta=DELTA_PT)


# --------------------------------------------------------------------
# The same structure, hermetic. A test that never runs is not a test.
# --------------------------------------------------------------------

#: Derived from the real page, not chosen. At 400 dpi the frame is
#: 2142 x 2465 px with a 22 px border, so the border is 1.0% of the
#: short side and the interior is 98% of it. The fixture keeps those
#: RATIOS at 1/5 the size; a fixture whose dimensions came from nowhere
#: is the tell.
#: The fixture IS the real page at 1/5 resolution, so its dpi is
#: 400/5 = 80. That is not a free parameter: at 80 dpi the 428 px frame
#: is 385.2 pt against the real page's 385.6 pt, and every pt-based
#: floor in `content_blocks` lands where it lands on the real page.
#: Declaring 400 dpi for a 1/5-scale fixture was the first version, and
#: it put the 36 pt block floor at 200 px on a 508 px page.
FIX_DPI = 80.0
FIX_W, FIX_H = 428, 493          # frame, px  (2142/5, 2465/5)
FIX_BORDER = 4                   # px         (22/5, rounded)
GREY = 153                       # the real frame's luma


def _grey_frame_page():
    """A grey hollow frame containing text-sized marks, on white, with
    two filled blocks outside it.

    Everything the real page has that the rules discriminate on: a frame
    that is grey rather than black, an interior holding many separate
    components, and large FILLED components that must not be mistaken
    for frames.
    """
    W, H = FIX_W + 80, FIX_H + 80
    g = bytearray(b"\xff" * (W * H))

    def fill(x0, y0, x1, y1, v):
        for y in range(y0, y1):
            g[y * W + x0:y * W + x1] = bytes([v]) * (x1 - x0)

    ox, oy = 40, 40
    fill(ox, oy, ox + FIX_W, oy + FIX_H, GREY)                  # frame
    fill(ox + FIX_BORDER, oy + FIX_BORDER,
         ox + FIX_W - FIX_BORDER, oy + FIX_H - FIX_BORDER, 255)  # interior

    # TWO bands of marks with an 80 px gutter between them. The gutter
    # is not decoration: `content_blocks` only cuts on white runs of at
    # least 10.8 pt (60 px at 400 dpi), and the first version of this
    # fixture spaced its marks 22-26 px apart -- below the floor, so no
    # gap existed, the complement was the whole page, and the white
    # route correctly found nothing. A fixture for the gap route must
    # contain a GAP.
    for band in (0, 1):
        top = oy + 20 + band * 260
        for r in range(4):
            for c in range(8):
                x = ox + 20 + c * 48
                y = top + r * 36
                fill(x, y, x + 22, y + 14, 0)
    fill(ox + 30, oy + FIX_H - 120, ox + 170, oy + FIX_H - 20, 0)   # filled
    fill(ox + 220, oy + FIX_H - 120, ox + 360, oy + FIX_H - 20, 0)  # filled
    return bytes(g), W, H


class T_GreyFrameHermetic(unittest.TestCase):
    """The page-7 structure with no corpus, so it runs every time.

    The opt-in class above is the real evidence; this is the regression
    guard. Both exist because the corpus one skips unless the env var is
    set, which means in practice it does not run.
    """

    def setUp(self):
        self.gray, self.W, self.H = _grey_frame_page()
        self.pt = 72.0 / FIX_DPI

    def _mask(self, th):
        return binarize(self.gray, self.W, self.H, threshold=th)

    def _frames(self, th):
        m = self._mask(th)
        res = sweep(m)
        mo = moments_per_component(res)
        cyc = {c.root: c.cycle_count for c in res.components}
        return sorted((x for cid, x in mo.items()
                       if x.area / (x.width * x.height) < MAX_FILL
                       and min(x.width, x.height) >= 0.5 * FIX_W
                       and cyc.get(cid, 0) >= 1),
                      key=lambda x: -x.width * x.height)

    def test_the_grey_frame_is_ink_above_its_own_luma(self):
        for th in (160, 200, 240):
            with self.subTest(threshold=th):
                got = self._frames(th)
                self.assertTrue(got, "no hollow frame found")
                self.assertEqual((got[0].width, got[0].height),
                                 (FIX_W, FIX_H))

    def test_the_ink_route_LOSES_the_frame_below_the_grey(self):
        """Luma 153, so at 128 the frame is background. The stated limit
        of the ink route, and the reason the interior matters."""
        self.assertEqual(self._frames(128), [])

    def test_the_interior_is_the_frames_HOLE_and_holds_the_content(self):
        """What page 7 actually shows: the frame and its interior are
        ONE component's geometry, not two routes. `nest` has both --
        measured on the real page, the frame is 385.6 x 443.7 pt and its
        hole 377.8 x 435.2 pt, which is exactly the number the
        'white route' recovered.
        """
        from inkdrill.nest import nest
        from inkdrill.emit import ink_regions
        n = nest(self._mask(200))
        frame = max(ink_regions(n),
                    key=lambda r: (r.x1 - r.x0) * (r.y1 - r.y0))
        holes = n.holes_of(frame.id)
        self.assertEqual(len(holes), 1)
        hr = n.regions[holes[0]]
        self.assertEqual(hr.x1 - hr.x0 + 1, FIX_W - 2 * FIX_BORDER)
        self.assertEqual(hr.y1 - hr.y0 + 1, FIX_H - 2 * FIX_BORDER)
        self.assertGreater(len(n.ink_in_hole(holes[0])), 50)

    def test_the_border_is_recovered_symmetrically(self):
        """(frame - hole) / 2 on each side, which is the border. The
        real page gives 3.9 pt; the fixture gives its own 4 px."""
        from inkdrill.nest import nest
        from inkdrill.emit import ink_regions
        n = nest(self._mask(200))
        frame = max(ink_regions(n),
                    key=lambda r: (r.x1 - r.x0) * (r.y1 - r.y0))
        hr = n.regions[n.holes_of(frame.id)[0]]
        inset_w = ((frame.x1 - frame.x0) - (hr.x1 - hr.x0)) / 2
        inset_h = ((frame.y1 - frame.y0) - (hr.y1 - hr.y0)) / 2
        self.assertEqual(inset_w, FIX_BORDER)
        self.assertEqual(inset_h, FIX_BORDER)

    def test_a_large_FILLED_block_is_not_a_frame(self):
        """The fixture contains two, so the `fill` rule has something to
        discriminate against."""
        mo = moments_per_component(sweep(self._mask(200)))
        filled = [x for x in mo.values()
                  if min(x.width, x.height) >= 80
                  and x.area / (x.width * x.height) > 0.7]
        self.assertEqual(len(filled), 2)
        boxes = {(x.width, x.height) for x in self._frames(200)}
        for x in filled:
            self.assertNotIn((x.width, x.height), boxes)

    def test_the_frame_is_emitted_as_a_diagram_by_the_INK_route(self):
        from inkdrill.emit import page_lines
        lines = page_lines(self._mask(200), pt=self.pt)
        wide = [l for l in lines if l["type"] == "diagram"]
        self.assertEqual(len(wide), 1)
        self.assertEqual(wide[0]["ink"]["route"], "ink")
        self.assertGreater(wide[0]["ink"]["contains"], 50)

    def test_the_white_route_also_contributes_a_line(self):
        """Both routes run. The gap route finds content BETWEEN ink, so
        on this fixture it reports the block of marks inside the frame
        -- a different object from the frame itself, which is the point
        of having both."""
        from inkdrill.emit import page_lines
        lines = page_lines(self._mask(200), pt=self.pt)
        blocks = [l for l in lines if l["type"] == "block"]
        self.assertTrue(blocks)
        for b in blocks:
            self.assertEqual(b["ink"]["route"], "white")

    def test_a_SHORT_white_run_is_not_a_gap(self):
        """`min_gap` filters run LENGTH, not gap width -- a 6 px wide
        white strip between two tall blocks has 300 px runs down the
        column axis and is correctly a gap. Two fixtures went wrong on
        that before this one tested the rule at its own level.

        A run survives if EITHER axis is long enough, so the short
        pocket has to be short in BOTH -- an 8x8 pocket is 8 px in the
        row axis and 8 in the column, while a tall 8 px slit has 20 px
        column runs and is a gap. That cost two more fixtures.
        """
        from inkdrill.emit import gap_mask
        W, H = 200, 80
        g = bytearray(b"\x00" * (W * H))          # all ink
        for y in range(20, 28):                   # 8 x 8 pocket
            g[y * W + 40:y * W + 48] = b"\xff" * 8
        for y in range(20, 60):                   # 40 x 40 pocket
            g[y * W + 100:y * W + 140] = b"\xff" * 40
        m = binarize(bytes(g), W, H, threshold=200)
        kept = gap_mask(m, min_gap=12)
        self.assertEqual(kept.data[24 * W + 44], 0x00,
                         "an 8x8 pocket of white was kept as a gap")
        self.assertEqual(kept.data[40 * W + 120], 0xFF,
                         "a 40x40 pocket of white was lost")

    def test_a_run_touching_the_page_EDGE_is_a_margin_not_a_gap(self):
        """White connects around every object through the page border,
        so keeping edge-touching runs gives one page-sized blob and the
        route returns nothing. The fixture's outer margin is 40 px --
        well over the 12 px floor -- so this rule is load-bearing here
        and not decoration."""
        from inkdrill.emit import gap_mask
        m = self._mask(200)
        bounded = gap_mask(m, min_gap=10.8 / self.pt)
        edge_cols = sum(1 for y in range(m.height)
                        if bounded.data[y * m.width] == 0xFF)
        self.assertEqual(edge_cols, 0,
                         "a gap run reached the page edge; that is a "
                         "margin and it connects the page into one blob")

    def test_MERGING_joins_two_adjacent_blocks(self):
        """The step that took `fragmented` off the top: 7 to 5 and
        `matched` 6 to 8 over 14 labelled figures. Two blocks a few
        pixels apart must arrive as one."""
        from inkdrill.emit import content_blocks
        a = content_blocks(self._mask(200), pt=self.pt, merge_tol_pt=0.0)
        b = content_blocks(self._mask(200), pt=self.pt, merge_tol_pt=30.0)
        # The COUNT is the wrong observable and was the first assertion
        # here: on this fixture merging joins each pair of side-by-side
        # blocks into one wider block, so two stay two while the BOXES
        # grow from 166x100 to 358x193. What merging does is enlarge,
        # not always reduce.
        self.assertTrue(a and b)
        widest_a = max(x1 - x0 for x0, _, x1, _ in a)
        widest_b = max(x1 - x0 for x0, _, x1, _ in b)
        self.assertGreater(widest_b, widest_a,
                           "merging changed nothing on this fixture")

    def test_disabling_the_white_route_removes_only_its_lines(self):
        """The ink route must not depend on it -- `nest` is not removed
        or altered by the second route being present."""
        from inkdrill.emit import page_lines
        with_w = page_lines(self._mask(200), pt=self.pt)
        without = page_lines(self._mask(200), pt=self.pt, white_route=False)
        self.assertEqual([l for l in with_w if l["type"] != "block"],
                         without)
        self.assertTrue([l for l in with_w if l["type"] == "block"])
