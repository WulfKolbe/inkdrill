"""typeface signals: hermetic ideals here, TeX Gyre measurements gated.

Every classifier-like decision asserts each class FIRES -- the standing
rule. The gated tests assert the measured premises: bold/regular
1.43-1.58x, italic/roman 3.2-11.9x, serif-sans page medians 0 vs -1.
"""

import os
import pathlib
import statistics
import unittest

from inkdrill.raster import InkMask
from inkdrill.sweep import Capture, sweep
from inkdrill.typeface import (font_weight_class, hollow, serif_excess,
                               slant, stroke_width)


def m(rows):
    w = len(rows[0])
    return InkMask(bytes(0xFF if c == "#" else 0
                         for r in rows for c in r), w, len(rows))


class TF_1_StrokeWidth(unittest.TestCase):

    def test_a_long_bar_converges_on_its_width(self):
        """2A/P on a 3x40 bar: 240/86 = 2.79 -- approaches 3 from
        below, the end caps being the shortfall."""
        bar = m(["#" * 40] * 3)
        self.assertAlmostEqual(stroke_width(bar), 240 / 86, places=6)

    def test_a_thicker_bar_reports_thicker(self):
        thin = m(["#" * 40] * 3)
        thick = m(["#" * 40] * 6)
        self.assertGreater(stroke_width(thick), stroke_width(thin) * 1.5)

    def test_an_empty_mask_is_zero_not_an_exception(self):
        self.assertEqual(stroke_width(InkMask(b"\x00" * 12, 4, 3)), 0.0)


class TF_2_WeightClass(unittest.TestCase):

    def test_two_weights_give_two_classes(self):
        """The instructed case: a page mixing regular and bold. Ratios
        from the MEASURED TeX Gyre values (5.3/28 and 8.2/28-ish)."""
        page = [(5.3, 28)] * 10 + [(8.2, 28)] * 4
        classes, modal = font_weight_class(page)
        self.assertEqual(len(set(classes)), 2)
        self.assertEqual(classes[0], 0, "classes are ordered light-first")
        self.assertEqual(classes[-1], 1)
        self.assertEqual(modal, 0, "the body weight is modal")

    def test_one_weight_gives_ONE_class(self):
        """The other side, so the split cannot be unconditional. Jitter
        at raster scale must not create classes."""
        page = [(5.3 + 0.05 * (i % 3), 28) for i in range(12)]
        classes, modal = font_weight_class(page)
        self.assertEqual(set(classes), {0})
        self.assertEqual(modal, 0)

    def test_headline_SIZE_is_not_a_weight(self):
        """A heading is thicker in px but not in ratio -- the division
        by height is what keeps size out of weight."""
        page = [(5.3, 28)] * 8 + [(10.6, 56)] * 3   # same ratio, 2x size
        classes, _ = font_weight_class(page)
        self.assertEqual(set(classes), {0})

    def test_empty_input_is_empty_output(self):
        self.assertEqual(font_weight_class([]), ([], 0))


class TF_3_Hollow(unittest.TestCase):

    def _stats(self, mask):
        res = sweep(mask, conn=8, capture=Capture.GRAPH)
        (comp,) = res.components
        w = mask.width
        return dict(area=mask.ink_count, width=w, height=mask.height,
                    cycles=comp.cycle_count)

    @staticmethod
    def _outline_B(filled=False):
        """A B drawn as an outline face draws it: every stroke edge a
        line, bowls' inner edges joined to the outer contour at the
        stroke junctions. One component, 3 holes, thin.

        Two earlier fixtures failed structurally: disjoint nested rings
        are separate components (no single component reaches 3 cycles),
        and at 14x8 the fill is 0.54 -- stroke thickness only thins
        RELATIVE to size, so the fixture must be big enough for its own
        rule. Generated, with the numbers checked by sweep in the test.
        """
        W, H = 38, 20
        g = [[0] * W for _ in range(H)]

        def hbar(y, x0, x1):
            for x in range(x0, x1 + 1):
                g[y][x] = 1

        def vbar(x, y0, y1):
            for y in range(y0, y1 + 1):
                g[y][x] = 1
        hbar(0, 0, W - 1)
        hbar(H - 1, 0, W - 1)
        vbar(0, 0, H - 1)
        vbar(W - 1, 0, H - 1)
        for x0, x1 in ((3, 17), (21, 35)):
            hbar(3, x0, x1)
            hbar(H - 4, x0, x1)
            vbar(x0, 3, H - 4)
            vbar(x1, 3, H - 4)
        mid = H // 2
        hbar(mid, 1, 2)
        hbar(mid, 18, 20)
        if filled:
            # the same glyph filled: every hole flooded
            from inkdrill.nest import nest
            mk = InkMask(bytes(0xFF if g[y][x] else 0
                               for y in range(H) for x in range(W)), W, H)
            n = nest(mk)
            buf = bytearray(mk.data)
            for r in n.regions.values():
                if r.kind.value == "hole":
                    for y in range(r.y0, r.y1 + 1):
                        for x in range(r.x0, r.x1 + 1):
                            buf[y * W + x] = 0xFF
            return InkMask(bytes(buf), W, H)
        return InkMask(bytes(0xFF if g[y][x] else 0
                             for y in range(H) for x in range(W)), W, H)

    def test_an_outline_B_is_hollow_and_a_filled_one_is_not(self):
        """The outline face multiplies boundary lines: holes reach 3 and
        fill collapses. The filled twin of the SAME glyph -- holes
        flooded, nothing else changed -- must not qualify."""
        outline = self._outline_B()
        st = self._stats(outline)
        self.assertGreaterEqual(st["cycles"], 3, "fixture lost its holes")
        self.assertTrue(hollow(**st))
        self.assertFalse(hollow(**self._stats(self._outline_B(filled=True))))

    def test_a_thin_frame_with_ONE_hole_is_not_hollow(self):
        """Low fill alone must not qualify -- the cycles floor is what
        refuses it. The frame must be LARGE enough that its fill is
        actually under the cap: an 8x4 frame is 0.63 fill and both
        conditions fail together, which let the cycles floor be deleted
        unnoticed. 16x8 is 0.34."""
        frame = m(["#" * 16,
                   *["#" + "." * 14 + "#"] * 6,
                   "#" * 16])
        st = self._stats(frame)
        self.assertLess(st["area"] / (st["width"] * st["height"]), 0.35,
                        "the fixture must reach the fill branch")
        self.assertFalse(hollow(**st))

    def test_a_DENSE_block_with_three_pinholes_is_not_hollow(self):
        """High cycles alone must not qualify either -- the halftone
        case, and the fixture the fill cap could not be deleted
        without."""
        rows = ["#" * 16 for _ in range(8)]
        rows[2] = "##.####.####.###"
        block = m(rows)
        st = self._stats(block)
        self.assertGreaterEqual(st["cycles"], 3)
        self.assertFalse(hollow(**st))

    def test_degenerate_extents_are_false_not_a_crash(self):
        self.assertFalse(hollow(area=0, width=0, height=0, cycles=9))


_TREE = pathlib.Path(os.environ.get(
    "INKDRILL_TYPE1", "/usr/share/texmf-dist/fonts/type1"))
_GYRE = _TREE / "public" / "tex-gyre"


@unittest.skipUnless(_GYRE.is_dir(), "set INKDRILL_TYPE1 (needs tex-gyre)")
class TF_4_TeXGyre(unittest.TestCase):
    """The measured premises, pinned on the fonts they were measured on."""

    CH = "nohaesitmruc"

    @classmethod
    def _glyphs(cls, fname):
        from inkdrill.charstring import outline
        from inkdrill.scan import render
        from inkdrill.type1 import load
        f = load(_GYRE / fname)
        for ch in cls.CH:
            mask, _ = render(outline(f, ch), f.units_per_em, 96.0)
            yield mask

    def test_bold_stroke_width_is_at_least_1_4x_regular(self):
        for reg, bold in (("qtmr.pfb", "qtmb.pfb"),
                          ("qhvr.pfb", "qhvb.pfb")):
            for ch, rm, bm in zip(self.CH, self._glyphs(reg),
                                  self._glyphs(bold)):
                if ch not in "noeH":
                    continue
                self.assertGreaterEqual(
                    stroke_width(bm) / stroke_width(rm), 1.4,
                    f"{reg}/{bold} {ch}")

    def test_italic_slant_median_is_at_least_1_7x_roman(self):
        from inkdrill.aggregate import moments_of_mask
        for rom, ita in (("qtmr.pfb", "qtmri.pfb"),
                         ("qhvr.pfb", "qhvri.pfb")):
            rmed = statistics.median(slant(moments_of_mask(g))
                                     for g in self._glyphs(rom))
            imed = statistics.median(slant(moments_of_mask(g))
                                     for g in self._glyphs(ita))
            self.assertGreaterEqual(imed / max(rmed, 1e-9), 1.7,
                                    f"{rom}/{ita}")

    def test_mixed_alphabet_weight_classing_is_REFUTED_and_pinned(self):
        """T7's instructed test -- two classes from a real regular+bold
        page -- FAILS by measurement, and the failure is pinned rather
        than papered over.

        The stroke-width/height distributions INTERLEAVE across a mixed
        alphabet: regular `u` reaches 0.121 while bold `t` sits at
        0.121, regular `m`/`n` (0.115) above bold `s`/`i` (0.111). No
        1-D cut or gap separates interleaved distributions, so
        per-glyph weight classes on a mixed alphabet are not a thing
        this feature can deliver. Weight separates PER CHARACTER
        (bold/regular >= 1.4x for the same letter, the T6 result) and
        on uniform-ratio pages (the hermetic case); a page-level claim
        needs like-for-like glyph populations.
        """
        reg = [stroke_width(g) / g.height for g in self._glyphs("qtmr.pfb")]
        bold = [stroke_width(g) / g.height for g in self._glyphs("qtmb.pfb")]
        self.assertGreater(max(reg), min(bold),
                           "distributions no longer interleave -- the "
                           "refutation has expired; re-measure and "
                           "restore the two-class assertion")
        # and per character the separation is clean, which is why T6
        # holds while T7's page form does not
        for r, b in zip(reg, bold):
            self.assertGreater(b, r)

    def test_serif_excess_exact_values_pin_the_formula(self):
        """The directional page test cannot see the formula's constant
        -- halving the 2x shifts both medians together and the order
        survives. Exact values pin it: Termes `o` has termini
        (1,1,1,1) and births+closes 2, so 4 - 2*2 = 0; `n` (2,2,3,2)
        and 4, so 9 - 8 = 1."""
        from inkdrill.reeb import contract, signature  # noqa: F401
        vals = {}
        from inkdrill.charstring import outline
        from inkdrill.scan import render
        from inkdrill.type1 import load
        f = load(_GYRE / "qtmr.pfb")
        for ch in ("o", "n"):
            g, _ = render(outline(f, ch), f.units_per_em, 96.0)
            row = sweep(g, axis="row", conn=8, capture=Capture.GRAPH)
            col = sweep(g, axis="col", conn=8, capture=Capture.GRAPH)
            vals[ch] = serif_excess(row, col)
        self.assertEqual(vals, {"o": 0, "n": 1})

    def test_serif_excess_page_median_sans_below_serif(self):
        """WEAK signal, page median only: measured 0 (Termes) vs -1
        (Heros), per-glyph ranges overlapping. The direction is the
        assertion; a per-glyph claim would not survive the overlap."""
        med = {}
        for fname in ("qtmr.pfb", "qhvr.pfb"):
            vals = []
            for g in self._glyphs(fname):
                row = sweep(g, axis="row", conn=8, capture=Capture.GRAPH)
                col = sweep(g, axis="col", conn=8, capture=Capture.GRAPH)
                vals.append(serif_excess(row, col))
            med[fname] = statistics.median(vals)
        self.assertLess(med["qhvr.pfb"], med["qtmr.pfb"])


if __name__ == "__main__":
    unittest.main()
