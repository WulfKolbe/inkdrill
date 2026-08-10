"""Unit 9 (rasterizer half), part 2: running Type 1 charstrings.

Hermetic. Charstrings are assembled here from operator numbers rather
than copied out of a font, so each test names the operator it exercises
and a reader can check the bytes against the Type 1 spec without a hex
dump. `tests/test_charstring_corpus.py` runs the same interpreter over
every glyph of every font on the machine.
"""

import unittest

from inkdrill.charstring import (CharstringError, Glyph, Segment, outline,
                                 run)
from inkdrill.type1 import Type1Font

from tests.test_type1 import as_pfb, build
from inkdrill.type1 import parse


def num(v):
    """A value in Type 1 charstring number encoding."""
    v = int(v)
    if -107 <= v <= 107:
        return bytes([v + 139])
    if 108 <= v <= 1131:
        v -= 108
        return bytes([(v >> 8) + 247, v & 0xFF])
    if -1131 <= v <= -108:
        v = -v - 108
        return bytes([(v >> 8) + 251, v & 0xFF])
    return b"\xff" + int(v).to_bytes(4, "big", signed=True)


def cs(*parts):
    out = b""
    for p in parts:
        out += p if isinstance(p, bytes) else num(p)
    return out


HSBW = cs(0, 500, b"\x0d")
ENDCHAR = b"\x0e"


def font(charstrings, subrs=()):
    return parse(as_pfb(*build(charstrings, subrs=subrs)))


class T9_10_Numbers(unittest.TestCase):
    """All four number encodings, and div."""

    def _first_point(self, body):
        # A bare rmoveto draws nothing and is correctly dropped, so the
        # fixtures append a line to make the move observable.
        body = body + cs(10, 0, b"\x05")
        code = HSBW + body + ENDCHAR
        return run(font({"A": code}), code).contours[0][0]

    def test_the_four_encodings_agree_on_the_same_value(self):
        for v in (0, 107, 108, 1131, -107, -108, -1131, 32000, -32000):
            with self.subTest(v=v):
                p = self._first_point(cs(v, 0, b"\x15"))
                self.assertEqual(p.x, 0 + v)

    def test_div_produces_a_fraction(self):
        p = self._first_point(cs(1000, 4, b"\x0c\x0c", 0, b"\x15"))
        self.assertEqual(p.x, 250.0)

    def test_div_by_zero_raises(self):
        with self.assertRaises(CharstringError):
            self._first_point(cs(1, 0, b"\x0c\x0c", 0, b"\x15"))

    def test_a_truncated_number_raises(self):
        f = font({"A": HSBW})
        with self.assertRaises(CharstringError):
            run(f, HSBW + b"\xff\x00\x00")


class T9_11_Paths(unittest.TestCase):
    """The drawing operators, and G2: every contour comes back closed."""

    def _run(self, body):
        code = HSBW + body + ENDCHAR
        return run(font({"A": code}), code)

    def test_a_triangle_closes_itself(self):
        g = self._run(cs(0, 0, b"\x15", 100, 0, b"\x05", -50, 100, b"\x05"))
        self.assertEqual(len(g.contours), 1)
        c = g.contours[0]
        self.assertEqual((c[0].x, c[0].y), (c[-1].x, c[-1].y))

    def test_hlineto_and_vlineto_move_one_axis_only(self):
        g = self._run(cs(0, 0, b"\x15", 100, b"\x06", 50, b"\x07"))
        pts = [(s.x, s.y) for s in g.contours[0]]
        self.assertIn((100.0, 0.0), pts)
        self.assertIn((100.0, 50.0), pts)

    def test_rrcurveto_records_both_control_points(self):
        g = self._run(cs(0, 0, b"\x15", 10, 20, 30, 40, 50, 60, b"\x08"))
        seg = g.contours[0][1]
        self.assertTrue(seg.is_curve)
        self.assertEqual(seg.c1, (10.0, 20.0))
        self.assertEqual(seg.c2, (40.0, 60.0))
        self.assertEqual((seg.x, seg.y), (90.0, 120.0))

    def test_vhcurveto_starts_vertical_and_ends_horizontal(self):
        g = self._run(cs(0, 0, b"\x15", 10, 20, 30, 40, b"\x1e"))
        seg = g.contours[0][1]
        self.assertEqual(seg.c1, (0.0, 10.0))
        self.assertEqual(seg.y, seg.c2[1])

    def test_hvcurveto_starts_horizontal_and_ends_vertical(self):
        g = self._run(cs(0, 0, b"\x15", 10, 20, 30, 40, b"\x1f"))
        seg = g.contours[0][1]
        self.assertEqual(seg.c1, (10.0, 0.0))
        self.assertEqual(seg.x, seg.c2[0])

    def test_two_subpaths_give_two_contours(self):
        g = self._run(cs(0, 0, b"\x15", 50, 0, b"\x05", 0, 50, b"\x05",
                         b"\x09", 200, 200, b"\x15", 50, 0, b"\x05",
                         0, 50, b"\x05"))
        self.assertEqual(len(g.contours), 2)
        for c in g.contours:
            self.assertEqual((c[0].x, c[0].y), (c[-1].x, c[-1].y))

    def test_closepath_does_not_move_the_current_point(self):
        # Type 1's closepath differs from PostScript's: the current
        # point survives it, so the next rmoveto is relative to where
        # the path ended, not to its start.
        g = self._run(cs(0, 0, b"\x15", 100, 0, b"\x05", b"\x09",
                         0, 100, b"\x15", 10, 0, b"\x05"))
        self.assertEqual(g.contours[-1][0].x, 100.0)

    def test_an_empty_glyph_has_no_contours(self):
        g = self._run(b"")
        self.assertTrue(g.is_empty)


# Distinguishable subroutines. A single-element `subrs=[sub]` cannot
# verify that the interpreter used the number it popped -- an
# implementation that always called subr 0 would pass every test built
# on one. Each of these draws a different distance, so calling the wrong
# one is visible. That is the same fixture-degeneracy that let
# `test_hint_replacement...` pass against an interpreter which pushed
# nothing: the fixture, not the assertion, was the hole.
SUBRS = [cs(v, 0, b"\x05", b"\x0b") for v in (11, 22, 33, 44, 55)]


class T9_12_Subroutines(unittest.TestCase):
    """callsubr, return, and G5's depth bound."""

    def test_a_subr_draws_into_the_caller(self):
        code = HSBW + cs(0, 0, b"\x15", 3, b"\x0a") + ENDCHAR
        g = run(font({"A": code}, subrs=SUBRS), code)
        self.assertIn((44.0, 0.0), [(s.x, s.y) for s in g.contours[0]])

    def test_each_subr_number_selects_a_different_subr(self):
        seen = []
        for k, want in enumerate((11.0, 22.0, 33.0, 44.0, 55.0)):
            code = HSBW + cs(0, 0, b"\x15", k, b"\x0a") + ENDCHAR
            g = run(font({"A": code}, subrs=SUBRS), code)
            seen.append(g.contours[0][1].x)
        self.assertEqual(seen, [11.0, 22.0, 33.0, 44.0, 55.0])

    def test_return_resumes_the_caller(self):
        code = HSBW + cs(0, 0, b"\x15", 1, b"\x0a", 0, 70, b"\x05") + ENDCHAR
        g = run(font({"A": code}, subrs=SUBRS), code)
        self.assertIn((22.0, 70.0), [(s.x, s.y) for s in g.contours[0]])

    def test_an_out_of_range_subr_raises(self):
        code = HSBW + cs(0, 0, b"\x15", 9, b"\x0a") + ENDCHAR
        with self.assertRaises(CharstringError):
            run(font({"A": code}, subrs=SUBRS), code)

    def test_runaway_recursion_raises_rather_than_exhausting_the_stack(self):
        sub = cs(0, b"\x0a", b"\x0b")            # subr 0 calls itself
        code = HSBW + cs(0, 0, b"\x15", 0, b"\x0a") + ENDCHAR
        with self.assertRaises(CharstringError):
            run(font({"A": code}, subrs=[sub]), code)

    def test_a_charstring_whose_hsbw_is_inside_a_subr_still_works(self):
        # The `callsubr` class first_ops could not verify: 2.166% of the
        # TeX tree opens this way, and only the interpreter can settle it.
        code = cs(2, b"\x0a") + cs(0, 0, b"\x15", 10, 0, b"\x05") + ENDCHAR
        subrs = list(SUBRS)
        subrs[2] = HSBW + b"\x0b"
        g = run(font({"A": code}, subrs=subrs), code)
        self.assertEqual(g.width, 500)


class T9_13_Metrics(unittest.TestCase):
    """G4: the side bearing is the initial point."""

    def test_hsbw_sets_width_and_starts_the_pen_at_the_side_bearing(self):
        code = cs(40, 600, b"\x0d") + cs(0, 0, b"\x15", 10, 0, b"\x05") + ENDCHAR
        g = run(font({"A": code}), code)
        self.assertEqual((g.width, g.sbx), (600, 40))
        self.assertEqual(g.contours[0][0].x, 40.0)

    def test_sbw_sets_both_bearings(self):
        code = (cs(40, 15, 600, 0, b"\x0c\x07")
                + cs(0, 0, b"\x15", 10, 0, b"\x05") + ENDCHAR)
        g = run(font({"A": code}), code)
        self.assertEqual((g.sbx, g.sby, g.width), (40, 15, 600))
        self.assertEqual((g.contours[0][0].x, g.contours[0][0].y), (40.0, 15.0))

    def test_hsbw_with_too_few_arguments_raises(self):
        code = cs(40, b"\x0d") + ENDCHAR
        with self.assertRaises(CharstringError):
            run(font({"A": code}), code)


class T9_14_Seac(unittest.TestCase):
    """G6: accented characters compose, or raise."""

    def _accented(self, **kw):
        base = HSBW + cs(0, 0, b"\x15", 100, 0, b"\x05", 0, 100,
                         b"\x05") + ENDCHAR
        acc = HSBW + cs(0, 0, b"\x15", 20, 0, b"\x05", 0, 20,
                        b"\x05") + ENDCHAR
        # 65 is 'A' and 194 is 'acute' in StandardEncoding.
        comp = HSBW + cs(0, 30, 700, 65, 194, b"\x0c\x06")
        cstrings = {"A": base, "acute": acc, "Aacute": comp}
        for k in kw.get("drop", ()):
            del cstrings[k]
        return font(cstrings), comp

    def test_a_composite_carries_both_components(self):
        f, comp = self._accented()
        g = run(f, comp)
        self.assertEqual(len(g.contours), 2)

    def test_the_accent_is_offset_by_adx_and_ady(self):
        f, comp = self._accented()
        g = run(f, comp)
        ys = [max(s.y for s in c) for c in g.contours]
        self.assertAlmostEqual(max(ys) - min(ys), 620.0, delta=1.0)

    def test_a_missing_component_raises_rather_than_dropping_the_accent(self):
        # The failure this project exists to prevent: returning the base
        # letter without its accent is a PLAUSIBLE wrong answer.
        f, comp = self._accented(drop=("acute",))
        with self.assertRaises(CharstringError):
            run(f, comp)

    def test_an_unencoded_component_code_raises(self):
        comp = HSBW + cs(0, 30, 700, 65, 5, b"\x0c\x06")
        f = font({"A": HSBW + ENDCHAR, "X": comp})
        with self.assertRaises(CharstringError):
            run(f, comp)


class T9_15_Flex(unittest.TestCase):
    """The seven moves inside a flex are control points, not moves."""

    def _flex(self):
        body = cs(0, 0, b"\x15")
        body += cs(0, 1, b"\x0c\x10")              # othersubr 1: flex on
        for dx, dy in ((10, 0), (10, 10), (10, 10), (10, 10),
                       (10, -10), (10, -10), (10, 0)):
            body += cs(dx, dy, b"\x15") + cs(0, 2, b"\x0c\x10")
        body += cs(50, 50, 0, b"\x0c\x10")         # othersubr 0: flex off
        body += b"\x0c\x11" + b"\x0c\x11"          # two pops
        body += b"\x0c\x21"                        # setcurrentpoint
        return HSBW + body + ENDCHAR

    def test_a_flex_stays_one_contour(self):
        code = self._flex()
        g = run(font({"A": code}), code)
        self.assertEqual(len(g.contours), 1,
                         "flex moves were treated as real movetos")

    def test_a_flex_becomes_two_curves(self):
        code = self._flex()
        g = run(font({"A": code}), code)
        self.assertEqual(sum(1 for s in g.contours[0] if s.is_curve), 2)

    def test_hint_replacement_leaves_a_value_for_its_pop(self):
        """OtherSubrs 3 draws nothing but must still push.

        `3 1 3 callothersubr pop callsubr` re-applies hints by calling
        the subr whose number OtherSubrs 3 left on the PostScript
        stack. If nothing is pushed, `pop` yields 0 and the WRONG
        subroutine runs.

        The subrs below must therefore differ observably: an earlier
        version made them all bare `return`s, so calling subr 0 instead
        of subr 3 changed nothing and the test passed against an
        interpreter that pushed nothing at all.
        """
        body = cs(0, 0, b"\x15")
        body += cs(3, 1, 3, b"\x0c\x10") + b"\x0c\x11" + b"\x0a"
        code = HSBW + body + ENDCHAR
        subrs = [cs(500, 0, b"\x05", b"\x0b")] + [b"\x0b"] * 2 + \
                [cs(10, 0, b"\x05", b"\x0b")]
        g = run(font({"A": code}, subrs=subrs), code)
        self.assertEqual([(s.x, s.y) for s in g.contours[0]][1], (10.0, 0.0),
                         "pop returned the wrong subr number")


class T9_16_Rejects(unittest.TestCase):
    """G7: an operator outside the measured population fails loudly."""

    def test_an_unknown_operator_raises_and_names_itself(self):
        code = HSBW + cs(0, 0, b"\x15") + b"\x02" + ENDCHAR
        with self.assertRaises(CharstringError) as cm:
            run(font({"A": code}), code)
        self.assertIn("2", str(cm.exception))

    def test_an_unknown_escape_raises(self):
        code = HSBW + cs(0, 0, b"\x15") + b"\x0c\x63" + ENDCHAR
        with self.assertRaises(CharstringError):
            run(font({"A": code}), code)

    def test_outline_names_a_missing_glyph(self):
        with self.assertRaises(CharstringError):
            outline(font({"A": HSBW + ENDCHAR}), "nosuchglyph")

    def test_hints_are_consumed_not_drawn(self):
        code = HSBW + cs(0, 700, b"\x01") + cs(50, 60, b"\x03") + \
            cs(0, 0, b"\x15", 10, 0, b"\x05") + ENDCHAR
        g = run(font({"A": code}), code)
        self.assertEqual(len(g.contours), 1)
        self.assertEqual(len(g.contours[0]), 3)


class T9_17_Bounds(unittest.TestCase):

    def test_bounds_include_control_points(self):
        code = HSBW + cs(0, 0, b"\x15", 0, 500, 0, 0, 100, 0,
                         b"\x08") + ENDCHAR
        g = run(font({"A": code}), code)
        self.assertEqual(g.bounds()[3], 500.0)

    def test_bounds_of_an_empty_glyph_raises(self):
        g = Glyph()
        with self.assertRaises(ValueError):
            g.bounds()


class T9_26_ExactGeometry(unittest.TestCase):
    """What came OUT, not merely that something did.

    Every other test here observes how a charstring OPENS or how many
    contours it produced. A mutation sweep found three branches that
    could be taken or skipped with no test noticing -- `closepath`,
    `setcurrentpoint`, and the trailing close of a charstring that ends
    without one. All three appear in real fonts, and all three are
    invisible to an oracle that never looks at the point list.

    These assert the contour point list EXACTLY.
    """

    def _pts(self, body, name="A"):
        code = HSBW + body + ENDCHAR
        g = run(font({name: code}), code)
        return [[(s.x, s.y) for s in c] for c in g.contours]

    def test_a_rectangle_yields_exactly_its_corners(self):
        pts = self._pts(cs(0, 0, b"\x15", 100, 0, b"\x05",
                           0, 50, b"\x05", -100, 0, b"\x05"))
        self.assertEqual(pts, [[(0.0, 0.0), (100.0, 0.0), (100.0, 50.0),
                                (0.0, 50.0), (0.0, 0.0)]])

    def test_a_curve_yields_exact_control_and_end_points(self):
        code = HSBW + cs(0, 0, b"\x15", 10, 20, 30, 40, 50, 60,
                         b"\x08") + ENDCHAR
        g = run(font({"A": code}), code)
        seg = g.contours[0][1]
        self.assertEqual((seg.c1, seg.c2, (seg.x, seg.y)),
                         ((10.0, 20.0), (40.0, 60.0), (90.0, 120.0)))

    def test_a_charstring_ending_without_closepath_is_still_closed(self):
        """Legal, and common. The trailing close is what handles it."""
        pts = self._pts(cs(0, 0, b"\x15", 60, 0, b"\x05", 0, 60, b"\x05"))
        self.assertEqual(pts, [[(0.0, 0.0), (60.0, 0.0), (60.0, 60.0),
                                (0.0, 0.0)]])

    def test_closepath_emits_the_contour_and_keeps_the_pen(self):
        """Type 1's closepath closes the path WITHOUT moving the point,
        so the following rmoveto is relative to where drawing ended --
        the exact geometry, not just the contour count."""
        pts = self._pts(cs(0, 0, b"\x15", 40, 0, b"\x05", 0, 40, b"\x05",
                           b"\x09", 10, 10, b"\x15", 20, 0, b"\x05"))
        self.assertEqual(pts[0], [(0.0, 0.0), (40.0, 0.0), (40.0, 40.0),
                                  (0.0, 0.0)])
        # Second subpath starts at (40+10, 40+10), NOT at (10, 10).
        self.assertEqual(pts[1], [(50.0, 50.0), (70.0, 50.0), (50.0, 50.0)])

    def test_closepath_then_a_line_starts_a_NEW_contour(self):
        """The only case where `closepath`'s body is not redundant.

        `_moveto` closes the open contour itself, so whenever a moveto
        follows, removing closepath's body changes nothing -- which is
        why deleting it survived a mutation sweep. Drawing straight on
        after a closepath, with no moveto between, is what distinguishes
        them: with the body, the line begins a fresh contour from the
        current point; without it, the line extends a contour that was
        never emitted.
        """
        pts = self._pts(cs(0, 0, b"\x15", 40, 0, b"\x05", 0, 40, b"\x05",
                           b"\x09", 30, 0, b"\x05"))
        self.assertEqual(pts, [
            [(0.0, 0.0), (40.0, 0.0), (40.0, 40.0), (0.0, 0.0)],
            [(40.0, 40.0), (70.0, 40.0), (40.0, 40.0)],
        ])

    def test_a_charstring_with_no_endchar_still_returns_its_contour(self):
        """The trailing close in `run`, which nothing else reaches.

        `endchar` closes the path, so after one the trailing close is
        dead. A charstring that simply runs out -- which happens, and
        which the interpreter must not silently drop -- is the only
        thing that exercises it.
        """
        code = HSBW + cs(0, 0, b"\x15", 25, 0, b"\x05", 0, 25, b"\x05")
        g = run(font({"A": code + ENDCHAR}), code)
        self.assertEqual([[(s.x, s.y) for s in c] for c in g.contours],
                         [[(0.0, 0.0), (25.0, 0.0), (25.0, 25.0), (0.0, 0.0)]])

    def test_setcurrentpoint_moves_the_pen_absolutely(self):
        """`setcurrentpoint` takes ABSOLUTE coordinates and ends the
        flex protocol; a following rmoveto is relative to it."""
        pts = self._pts(cs(0, 0, b"\x15", 10, 0, b"\x05",
                           700, 800, b"\x0c\x21",
                           5, 5, b"\x15", 10, 0, b"\x05"))
        self.assertEqual(pts[1], [(705.0, 805.0), (715.0, 805.0),
                                  (705.0, 805.0)])

    def test_a_flex_yields_exact_curve_control_points(self):
        body = cs(0, 0, b"\x15") + cs(0, 1, b"\x0c\x10")
        for dx, dy in ((10, 0), (10, 10), (10, 10), (10, 10),
                       (10, -10), (10, -10), (10, 0)):
            body += cs(dx, dy, b"\x15") + cs(0, 2, b"\x0c\x10")
        body += cs(50, 50, 0, b"\x0c\x10") + b"\x0c\x11\x0c\x11"
        code = HSBW + body + ENDCHAR
        g = run(font({"A": code}), code)
        curves = [s for s in g.contours[0] if s.is_curve]
        self.assertEqual(len(curves), 2)
        self.assertEqual(curves[0].c1, (20.0, 10.0))
        self.assertEqual(curves[0].c2, (30.0, 20.0))
        self.assertEqual((curves[0].x, curves[0].y), (40.0, 30.0))
        self.assertEqual((curves[1].x, curves[1].y), (70.0, 10.0))


if __name__ == "__main__":
    unittest.main()
