"""Geometry against the DRAWING PROGRAM, not against another tool. OPT-IN.

Every other check in this suite compares inkdrill to an oracle that is
itself an opinion -- pdfminer's boxes, pdfdrill's `images_layer`, a
mutation sweep. This module compares it to a **declared answer**:
`e12s39.ps`, 5,093 lines of PostScript from June 1995, states the panel
width and the tick pitch as arithmetic, and `e12s39.pdf` is that file
through Ghostscript 9.05 with nothing else in the path.

    /cm { 28.346456 mul } bind def
    /axis.length 6.2 cm def          -> 175.7480 pt   (line 964)
    /axis.width  0.25 def            ->   0.25   pt   (line 962)
    /label.inc {axis.length 31.0 div 5 mul} def

Two numbers are checked, and both are derived from the source rather
than recorded from a previous run -- change the PostScript and the
expected values move with it.

Gated on `INKDRILL_CORPUS`, like the other corpus modules.

    INKDRILL_CORPUS=~/pdfdrill-library python3 -m unittest \
        tests.test_source_truth_corpus
"""

import os
import pathlib
import statistics
import unittest

from inkdrill.aggregate import moments_per_component
from inkdrill.pngio import load_mask, read_png
from inkdrill.raster import InkMask, iter_runs
from inkdrill.sweep import Capture, sweep

_ROOT = os.environ.get("INKDRILL_CORPUS")
_DOC = "e12s39"

# Authored in the PostScript, not measured. `axis.width` is redefined
# three times in the file and PostScript is sequential, so the value
# that applies is the LAST one before the panels are drawn -- 0.25 at
# line 962, not the 0.01 cm at line 672.
_PT_PER_CM = 28.346456
_AXIS_LENGTH_PT = 6.2 * _PT_PER_CM              # 175.7480
_AXIS_WIDTH_PT = 0.25
_DAYS = 31

# A4's NOMINAL size. Not this document's -- its MediaBox is `0 0 595 842`
# -- and that is the point: deriving dpi from the nominal size instead of
# reading the PNG's pHYs chunk shifts the answer by 0.071 pt, which is
# the same size as the residual being measured.
_A4_NOMINAL_WIDTH_PT = 595.32

# One tolerance, shared by the assertion and by the guard that proves the
# assertion can fail. They must not drift apart: at 0.15 the measurement
# passes at 0.072 AND the A4 error passes at 0.143, so the test admits
# exactly the mistake its docstring claims to catch.
_PANEL_TOL_PT = 0.10


def _page():
    if not _ROOT:
        return None
    p = (pathlib.Path(_ROOT).expanduser() / _DOC / "inspect" / "pages" / "p1.png")
    return p if p.exists() else None


_PAGE = _page()
_WHY = f"set INKDRILL_CORPUS to a corpus containing {_DOC}"


def _white_gaps(mask, *, min_len=60):
    """White runs bounded by ink at both ends -- the gap/margin rule."""
    W, H = mask.width, mask.height
    buf = bytearray(W * H)
    inv = mask.inverted()
    for axis in ("row", "col"):
        limit = W if axis == "row" else H
        for r in iter_runs(inv, axis):
            if r.lo == 0 or r.hi == limit - 1:
                continue
            n = r.hi - r.lo + 1
            if n < min_len:
                continue
            if axis == "row":
                base = r.line * W
                buf[base + r.lo:base + r.hi + 1] = b"\xff" * n
            else:
                buf[r.lo * W + r.line:r.hi * W + r.line + 1:W] = b"\xff" * n
    return InkMask(bytes(buf), W, H)


@unittest.skipUnless(_PAGE, _WHY)
class T11_1_DeclaredGeometry(unittest.TestCase):
    """The measurement against the number the source declares."""

    @classmethod
    def setUpClass(cls):
        img = read_png(_PAGE)
        # The PNG's own pHYs chunk, NOT a dpi derived from an assumed
        # page size: deriving it from A4's nominal 595.32 pt rather than
        # the PDF's actual 595 gives 175.39 pt where the answer is
        # 175.32, which is the same size as the residual being measured.
        cls.dpi = img.dpi[0]
        cls.mask = load_mask(_PAGE, threshold=240)
        white = _white_gaps(cls.mask)
        res = sweep(white, conn=8, capture=Capture.GRAPH)
        cls.blobs = list(moments_per_component(res).values())

    def _pt(self, px):
        return px * 72.0 / self.dpi

    def test_the_png_declares_its_own_resolution(self):
        self.assertAlmostEqual(self.dpi, 400.0, delta=0.01)

    def test_panel_width_matches_the_authored_axis_length(self):
        """`axis.length` minus the two strokes that bound the interior.

        The white interior is the inside of the frame, so it is shorter
        than the authored axis by one stroke width at each end.
        """
        widths = [c.width for c in self.blobs if 960 <= c.width <= 990]
        self.assertGreaterEqual(len(widths), 10,
                                "panels not found; the detector changed")
        # Every panel is the same object drawn repeatedly: no spread.
        self.assertEqual(len(set(widths)), 1,
                         f"panel widths should be identical, got {set(widths)}")
        expected = _AXIS_LENGTH_PT - 2 * _AXIS_WIDTH_PT
        self.assertAlmostEqual(self._pt(widths[0]), expected,
                               delta=_PANEL_TOL_PT,
                               msg=f"{len(widths)} panels at {widths[0]} px")

    def test_a_dpi_taken_from_nominal_A4_is_rejected_by_that_tolerance(self):
        """The guard the test above rests on, asserted rather than implied.

        `test_panel_width...` only catches a nominal-A4 dpi if its
        tolerance is tighter than that error. Stating the tolerance in a
        docstring does not make it so -- at delta=0.15 the wrong
        derivation lands at 0.143 and passes. This asserts the
        separation directly, so widening the tolerance past the mistake
        fails here instead of silently disarming the check there.
        """
        widths = [c.width for c in self.blobs if 960 <= c.width <= 990]
        expected = _AXIS_LENGTH_PT - 2 * _AXIS_WIDTH_PT
        wrong = widths[0] * _A4_NOMINAL_WIDTH_PT / self.mask.width
        self.assertGreater(
            abs(wrong - expected), _PANEL_TOL_PT,
            f"a dpi from nominal A4 gives {wrong:.3f} pt, only "
            f"{abs(wrong - expected):.3f} pt from the authored "
            f"{expected:.3f} -- the tolerance no longer catches it")
        self.assertLess(abs(self._pt(widths[0]) - expected), _PANEL_TOL_PT)

    def test_the_ink_sweep_alone_cannot_find_these_panels(self):
        """Why the white sweep is not redundant with the ink sweep.

        The frames are connected to axes, labels and traces, so no ink
        component has the panel's extent. The white detector finds two
        dozen; the ink detector finds none.
        """
        res = sweep(self.mask, conn=8, capture=Capture.GRAPH)
        frames = [c for c in moments_per_component(res).values()
                  if 960 <= c.width <= 990 and c.height > 60
                  and c.area / (c.width * c.height) < 0.35]
        self.assertEqual(frames, [])

    def test_tick_pitch_matches_the_authored_day_division(self):
        """The ticks are at `axis.length / 31`, one per day.

        `label.inc` is `axis.length/31*5` and is the LABEL spacing --
        every fifth day carries a number. Searching for that pitch finds
        text rather than ticks, which is what made this parameter look
        unmeasurable.

        Ticks are drawn as part of the axis path here, so none is a
        separate component; they are found as perpendicular protrusions
        by reading the ink row just outside the interior.
        """
        W, H, data = self.mask.width, self.mask.height, self.mask.data
        panels = [c for c in self.blobs if 960 <= c.width <= 990]
        spacings = []
        for c in sorted(panels, key=lambda c: (c.x0, c.y0)):
            for off in (4, 5, 6):
                y = c.y1 + off
                if y >= H:
                    continue
                row = data[y * W + c.x0:y * W + c.x1 + 1]
                xs, i = [], 0
                while True:
                    s = row.find(b"\xff", i)
                    if s < 0:
                        break
                    e = row.find(b"\x00", s + 1)
                    if e < 0:
                        e = len(row)
                    xs.append((s + e - 1) / 2)
                    i = e + 1
                if len(xs) < 20:
                    continue
                gaps = [xs[k + 1] - xs[k] for k in range(len(xs) - 1)]
                regular = [g for g in gaps if 25 < g < 40]
                if len(regular) >= 0.8 * len(gaps):
                    spacings.extend(regular)
                    break
        self.assertGreaterEqual(len(spacings), 100,
                                "no panel with a regular tick row found")
        got = self._pt(statistics.median(spacings))
        self.assertAlmostEqual(got, _AXIS_LENGTH_PT / _DAYS, delta=0.01,
                               msg=f"{len(spacings)} intervals")


if __name__ == "__main__":
    unittest.main()
