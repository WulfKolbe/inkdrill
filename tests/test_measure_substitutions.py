"""The OCR substitution audit's harness, checked hermetically.

This exists because the two worst measurement errors in this project so
far were both in a harness rather than in a module -- `m_maths` stored
four of `Signature`'s six fields and extracted a query as its largest
component, and the pair moved the headline from 70.94% to 88.10%. The
audit's number is only as good as the alignment and the filter that
produce it, so both are pinned here rather than trusted.

`measure.py` is a script and not an importable package, so it is loaded
by path. Nothing here reads the corpus or the Heim pages.
"""

import importlib.util
import pathlib
import unittest

_SRC = pathlib.Path(__file__).resolve().parents[1] / "tools/premise/measure.py"
_spec = importlib.util.spec_from_file_location("_measure", _SRC)
measure = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(measure)


class TC_1_TexWords(unittest.TestCase):
    """The word stream both sides are reduced to."""

    def test_maths_is_dropped_rather_than_flattened(self):
        """An error inside `$...$` is a MATHS error. Flattening the
        formula into words would put two error modes under one
        number, so the whole span goes."""
        self.assertEqual(measure._tex_words(r"vor $a_{i}^{2}$ nach"),
                         ["vor", "nach"])

    def test_a_macro_is_removed_and_its_argument_kept(self):
        self.assertEqual(measure._tex_words(r"die {\it Quantenfeldtheorie} ist"),
                         ["die", "Quantenfeldtheorie", "ist"])

    def test_eszett_is_restored_because_the_truth_spells_it_that_way(self):
        """`\\eszett` is the transcription's own macro. Left alone it
        would be stripped as a macro, and every word containing it
        would stop aligning -- silently shrinking the population."""
        self.assertEqual(measure._tex_words(r"da\eszett es"), ["daß", "es"])

    def test_a_comment_is_removed(self):
        self.assertEqual(measure._tex_words("text % normale Text Zeile\nmehr"),
                         ["text", "mehr"])


class TC_2_Filter(unittest.TestCase):
    """What the 1:1 filter keeps, and what it drops."""

    def test_a_single_character_substitution_is_counted(self):
        subs, kept, dropped, aligned = measure._substitutions(
            ["Das", "i@t", "gut"], ["Das", "ist", "gut"])
        self.assertEqual(subs, {("@", "s"): 1})
        self.assertEqual((kept, dropped, aligned), (1, 0, 2))

    def test_a_MERGED_character_is_DROPPED_not_counted(self):
        """`rn` read as `m` shortens the word. Comparing it would put a
        one-glyph topology against a two-glyph one, which is a different
        measurement -- so it is dropped, and the drop is reported."""
        subs, kept, dropped, _ = measure._substitutions(
            ["moden"], ["rnoden"])
        self.assertEqual(subs, {})
        self.assertEqual((kept, dropped), (0, 1))

    def test_a_TWO_character_error_is_DROPPED(self):
        """Two substitutions in one word are ambiguous to attribute --
        the alignment inside the word is a guess -- so the word leaves
        the population rather than contributing two uncertain pairs."""
        subs, kept, dropped, _ = measure._substitutions(
            ["b@@is"], ["basis"])
        self.assertEqual((subs, kept, dropped), ({}, 0, 1))

    def test_an_UNEQUAL_LENGTH_block_is_dropped_whole(self):
        """Found by mutation. Without the length guard the two sides
        are `zip`ped, which truncates to the shorter and compares words
        that are not each other -- here it MANUFACTURES a y->z
        substitution out of `xy`/`qq` against `xz`. A fabricated pair
        is worse than a missing one: it lands in the population as
        evidence."""
        subs, kept, dropped, _ = measure._substitutions(
            ["a", "xy", "qq", "b"], ["a", "xz", "b"])
        self.assertEqual(subs, {})
        self.assertEqual((kept, dropped), (0, 2))

    def test_the_dropped_count_is_not_zero_by_construction(self):
        """The guard on the guard. A filter that dropped nothing would
        pass every test above, and the drop count is half the result."""
        _, kept, dropped, _ = measure._substitutions(
            ["a", "i@t", "moden", "b@@is"], ["a", "ist", "rnoden", "basis"])
        self.assertEqual((kept, dropped), (1, 2))


class TC_3_Blindness(unittest.TestCase):
    """The audit must be able to return BOTH answers.

    A harness that reported every pair as separable would pass a suite
    made only of separable pairs. The blind class is the finding, so it
    is asserted directly.
    """

    def setUp(self):
        import os
        tree = pathlib.Path(os.environ.get(
            "INKDRILL_TYPE1", "/usr/share/texmf-dist/fonts/type1"))
        src = next(tree.rglob("DejaVuSans.pfb"), None) if tree.is_dir() else None
        if src is None:
            self.skipTest("no DejaVuSans.pfb; set INKDRILL_TYPE1")
        self.font = measure.t1_load(src)

    def test_o_and_c_are_SEPARABLE_by_a_hole(self):
        """`o` closes and `c` does not. NOT `o` against `e`: the eye of
        an `e` is a closed counter too, so both are (1, 1) and the pair
        an intuition offers first is one topology cannot separate."""
        self.assertEqual(measure._glyph_topology(self.font, "o", 96.0), (1, 1))
        self.assertEqual(measure._glyph_topology(self.font, "c", 96.0), (1, 0))

    def test_i_and_l_are_SEPARABLE_by_a_component(self):
        """The other channel. A tittle is a second component, so the
        audit is not reading holes alone."""
        self.assertEqual(measure._glyph_topology(self.font, "i", 96.0), (2, 0))
        self.assertEqual(measure._glyph_topology(self.font, "l", 96.0), (1, 0))

    def test_I_and_l_are_BLIND_and_no_threshold_changes_that(self):
        """Both are one stroke with no hole at every size. This is the
        boundary of what ink alone can say, and it is measured rather
        than asserted in prose."""
        for px_em in (48.0, 96.0, 192.0):
            self.assertEqual(measure._glyph_topology(self.font, "I", px_em),
                             measure._glyph_topology(self.font, "l", px_em),
                             f"at {px_em} px/em")

    def test_a_REFLECTED_pair_is_blind_TO_THIS_INVARIANT(self):
        """(components, cycles) is a topological invariant, so it is
        unchanged by reflection, and no size reaches that.

        CORRECTED SCOPE. This says nothing about the ink -- only about
        the two-number summary. `test_the_two_axis_signature_LIFTS_it`
        separates the same pair, so "nothing about the ink
        distinguishes them" was wrong and is not asserted here."""
        import os
        tree = pathlib.Path(os.environ.get(
            "INKDRILL_TYPE1", "/usr/share/texmf-dist/fonts/type1"))
        src = next(tree.rglob("cmsy10.pfb"), None) if tree.is_dir() else None
        if src is None:
            self.skipTest("no cmsy10.pfb; set INKDRILL_TYPE1")
        sym = measure.t1_load(src)
        for a, b in (("union", "intersection"),
                     ("lessequal", "greaterequal")):
            for px_em in (48.0, 96.0, 192.0):
                self.assertEqual(
                    measure._glyph_topology(sym, None, px_em, name=a),
                    measure._glyph_topology(sym, None, px_em, name=b),
                    f"{a}/{b} at {px_em} px/em")

    def test_a_pair_differing_in_HOLE_COUNT_is_separable(self):
        """The other answer, so the test above is not vacuous: a class
        that reported everything blind would pass it."""
        import os
        tree = pathlib.Path(os.environ.get(
            "INKDRILL_TYPE1", "/usr/share/texmf-dist/fonts/type1"))
        src = next(tree.rglob("cmsy10.pfb"), None) if tree.is_dir() else None
        if src is None:
            self.skipTest("no cmsy10.pfb; set INKDRILL_TYPE1")
        sym = measure.t1_load(src)
        self.assertNotEqual(
            measure._glyph_topology(sym, None, 96.0, name="circleplus"),
            measure._glyph_topology(sym, None, 96.0, name="circleminus"))

    def test_the_two_axis_signature_LIFTS_it(self):
        """The correction, pinned. A finer invariant of the SAME KIND --
        already in this package -- separates pairs that (components,
        cycles) cannot, so the blind set is a property of the summary
        and not of topology.

        The two axes are COMPLEMENTARY, which is the part worth
        keeping: union/intersection is a vertical reflection and falls
        to the row sweep; lessequal/greaterequal is a horizontal one
        and falls to the column sweep. Each is blind on the other axis.
        `reeb.signature` is documented as not rotation invariant --
        that recorded limitation is what does the work here.
        """
        import os
        from inkdrill.reeb import contract, signature
        from inkdrill.sweep import Capture, sweep as do_sweep
        from inkdrill.charstring import outline
        from inkdrill.scan import render
        tree = pathlib.Path(os.environ.get(
            "INKDRILL_TYPE1", "/usr/share/texmf-dist/fonts/type1"))
        src = next(tree.rglob("cmsy10.pfb"), None) if tree.is_dir() else None
        if src is None:
            self.skipTest("no cmsy10.pfb; set INKDRILL_TYPE1")
        sym = measure.t1_load(src)

        def sig(name, axis):
            mask, _ = render(outline(sym, name), sym.units_per_em, 96.0)
            return signature(contract(
                do_sweep(mask, axis=axis, conn=8, capture=Capture.GRAPH)))

        # vertical reflection: the row sweep sees it, the column one does not
        self.assertNotEqual(sig("union", "row"), sig("intersection", "row"))
        self.assertEqual(sig("union", "col"), sig("intersection", "col"))
        # horizontal reflection: exactly the other way round
        self.assertEqual(sig("lessequal", "row"), sig("greaterequal", "row"))
        self.assertNotEqual(sig("lessequal", "col"),
                            sig("greaterequal", "col"))

    def test_an_unmapped_character_returns_None_rather_than_a_topology(self):
        """An unrenderable pair must leave the population visibly. A
        silent (0, 0) would count as separable against anything."""
        self.assertIsNone(measure._glyph_topology(self.font, "中", 96.0))


if __name__ == "__main__":
    unittest.main()
