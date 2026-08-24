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


class TC_4_BlockAssignment(unittest.TestCase):
    """The block/figure assignment, which has been wrong twice.

    Both failures were the same shape and neither raised: a class that
    could not occur. The first version counted ANY overlap as coverage,
    so `matched` was nearly unreachable; the second left a
    page-spanning block in the candidate list, so `missed` was
    unreachable. Every class is therefore asserted to FIRE here, not
    merely to be computed.
    """

    def test_a_clean_one_to_one_cover_is_MATCHED(self):
        got, errs = measure._classify_blocks(
            [(0, 0, 100, 100)], [(2, 2, 102, 102)], 0.5)
        self.assertEqual(got["matched"], 1)
        self.assertEqual(errs, [0])

    def test_a_figure_broken_into_pieces_is_FRAGMENTED(self):
        """The route's actual failure mode. Two half-height blocks each
        overlap the figure and neither reaches the IoU, so it is covered
        by nothing whole -- which is not the same fault as `split`."""
        got, _ = measure._classify_blocks(
            [(0, 0, 100, 100)],
            [(0, 0, 100, 40), (0, 60, 100, 100)], 0.5)
        self.assertEqual(got["fragmented"], 1)
        self.assertEqual(got["matched"], 0)

    def test_a_figure_no_block_touches_is_MISSED(self):
        """MISSED must be reachable. It was not, for a whole run, because
        a page-spanning block overlapped every truth -- so `missed` read
        0 at every setting and that zero meant nothing."""
        got, _ = measure._classify_blocks(
            [(0, 0, 100, 100)], [(500, 500, 700, 700)], 0.5)
        self.assertEqual(got["missed"], 1)
        self.assertEqual(got["fragmented"], 0)

    def test_one_block_over_two_figures_is_MERGED(self):
        got, _ = measure._classify_blocks(
            [(0, 0, 100, 100), (0, 0, 100, 99)], [(0, 0, 100, 100)], 0.5)
        self.assertEqual(got["merged"], 2)

    def test_two_blocks_each_covering_it_is_SPLIT(self):
        got, _ = measure._classify_blocks(
            [(0, 0, 100, 100)],
            [(0, 0, 100, 99), (1, 0, 100, 100)], 0.5)
        self.assertEqual(got["split"], 1)

    def test_a_block_touching_nothing_is_SPURIOUS(self):
        got, _ = measure._classify_blocks(
            [(0, 0, 100, 100)],
            [(0, 0, 100, 100), (900, 900, 1000, 1000)], 0.5)
        self.assertEqual((got["matched"], got["spurious"]), (1, 1))

    def test_a_block_that_OVERLAPS_but_does_not_cover_is_not_spurious(self):
        """The other side of the refusal. A block partly over a figure
        is evidence about that figure, not a free-standing find, so it
        must not inflate the count this project treats as its output."""
        got, _ = measure._classify_blocks(
            [(0, 0, 100, 100)], [(50, 50, 400, 400)], 0.5)
        self.assertEqual(got["spurious"], 0)
        self.assertEqual(got["fragmented"], 1)

    def test_iou_is_zero_for_disjoint_and_one_for_identical(self):
        self.assertEqual(measure._iou((0, 0, 10, 10), (20, 20, 30, 30)), 0.0)
        self.assertEqual(measure._iou((0, 0, 10, 10), (0, 0, 10, 10)), 1.0)


class TC_5_PageNumbers(unittest.TestCase):
    """Lexicographic glob order produced a wrong conclusion twice in
    one day. This is the ten lines that stop it."""

    def test_page_19_is_not_index_18(self):
        """`sorted(pages)[18]` was read as page 19 and is not. The
        corpus sorts p1, p10, p11, ... so position and page number
        diverge from the tenth page on."""
        names = [pathlib.Path(f"p{i}.png") for i in range(1, 25)]
        lexical = sorted(names, key=lambda p: p.name)
        self.assertNotEqual(measure.page_number(lexical[18]), 19)
        self.assertEqual(measure.page_number(pathlib.Path("p19.png")), 19)

    def test_both_naming_schemes_are_read(self):
        self.assertEqual(measure.page_number(pathlib.Path("page-0007.png")), 7)
        self.assertEqual(measure.page_number(pathlib.Path("p7.png")), 7)

    def test_a_name_that_is_not_a_page_returns_None(self):
        """Absent, not zero. A zero would key a real entry in the map."""
        self.assertIsNone(measure.page_number(pathlib.Path("compare.png")))
        self.assertIsNone(measure.page_number(pathlib.Path("p12b.png")))


class TC_6_MergeBoxes(unittest.TestCase):
    """S1's grouping fix. Every outcome is asserted to FIRE -- the
    standing rule after two 'a class that could not occur' defects.

    It moved into the package as `emit.merge_boxes` when the white route
    was wired in; the harness imports it rather than keeping a copy, so
    there is one definition to test.
    """

    @property
    def _m(self):
        from inkdrill.emit import merge_boxes
        return merge_boxes

    def test_boxes_that_touch_are_unioned(self):
        got = self._m([(0, 0, 10, 10), (10, 0, 20, 10)], 1)
        self.assertEqual(got, [(0, 0, 20, 10)])

    def test_boxes_beyond_the_tolerance_are_LEFT_ALONE(self):
        """The other answer. A merge that unioned everything would pass
        the test above, and that is exactly what happened on p10 -- 13
        boxes became 1 at a tolerance of one pixel."""
        got = self._m([(0, 0, 10, 10), (50, 0, 60, 10)], 1)
        self.assertEqual(sorted(got), [(0, 0, 10, 10), (50, 0, 60, 10)])

    def test_merging_is_TRANSITIVE_to_a_fixed_point(self):
        """A chain must close in one call. Three boxes where only the
        neighbours touch is the case a single pass gets wrong."""
        got = self._m(
            [(0, 0, 10, 10), (10, 0, 20, 10), (20, 0, 30, 10)], 1)
        self.assertEqual(got, [(0, 0, 30, 10)])

    def test_the_x_sorted_early_exit_does_not_miss_a_pair(self):
        """The inner loop breaks once a candidate starts beyond this
        box's right edge. A box that is wide and early must still reach
        one that starts late and overlaps it."""
        got = self._m(
            [(0, 0, 100, 10), (5, 0, 15, 10), (90, 0, 110, 10)], 0.0)
        self.assertEqual(got, [(0, 0, 110, 10)])

    def test_a_negative_tolerance_is_refused(self):
        with self.assertRaises(ValueError):
            self._m([(0, 0, 1, 1)], -1)

    def test_a_zero_tolerance_still_merges_overlapping_boxes(self):
        """The accepting side of the refusal above, so the guard cannot
        be made unconditional."""
        self.assertEqual(self._m([(0, 0, 10, 10),
                                               (5, 5, 15, 15)], 0),
                         [(0, 0, 15, 15)])


class T13_12_AcceptedIsASubsetOfAllWrong(unittest.TestCase):
    """A2b: the verifier can only remove confusions, never add one.

    `measure.py maths` now prints two tables -- every wrong pair the
    classifier produced, and the subset of those the signature
    accepted. The relation between them is the reason both can be
    printed side by side, so it is checked in code rather than left
    to the reader, and BOTH sides are asserted: the accepting path as
    well as the refusal, or the guard could be made unconditional
    without a failure.
    """

    @staticmethod
    def _fn():
        import importlib.util, pathlib, sys
        p = (pathlib.Path(__file__).resolve().parent.parent
             / "tools" / "premise" / "measure.py")
        spec = importlib.util.spec_from_file_location("_m_sub", p)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["_m_sub"] = mod
        spec.loader.exec_module(mod)
        return mod.check_accepted_subset

    def test_a_proper_subset_is_accepted(self):
        from collections import Counter
        f = self._fn()
        allw = Counter({("a", "b"): 5, ("c", "d"): 2, ("e", "f"): 1})
        acc = Counter({("a", "b"): 3, ("c", "d"): 2})
        self.assertTrue(f(acc, allw))

    def test_an_equal_pair_of_counters_is_accepted(self):
        """The verifier accepting everything is a legitimate outcome
        and must not raise -- otherwise the guard would forbid the
        case where the signature rejects nothing."""
        from collections import Counter
        c = Counter({("a", "b"): 5, ("c", "d"): 2})
        self.assertTrue(self._fn()(Counter(c), c))

    def test_an_empty_accepted_set_is_accepted(self):
        from collections import Counter
        self.assertTrue(self._fn()(Counter(),
                                   Counter({("a", "b"): 5})))

    def test_a_pair_the_classifier_never_produced_raises(self):
        from collections import Counter
        with self.assertRaises(AssertionError):
            self._fn()(Counter({("x", "y"): 1}),
                       Counter({("a", "b"): 5}))

    def test_an_accepted_count_above_the_total_raises(self):
        """Same keys, impossible counts. The subset test on keys alone
        would pass this, which is why the counts are checked too."""
        from collections import Counter
        with self.assertRaises(AssertionError):
            self._fn()(Counter({("a", "b"): 9}),
                       Counter({("a", "b"): 5}))


class T13_13_ArgvProvenanceLine(unittest.TestCase):
    """A3a: every measurement's first line is the command that made it.

    The round trip is the test. A provenance line that does not parse
    back to the arguments the run actually used is decoration -- it
    looks like reproducibility and is not -- so the assertion is
    equality with the parsed args, not a substring match on the text.
    """

    @staticmethod
    def _mod():
        import importlib.util, pathlib, sys
        p = (pathlib.Path(__file__).resolve().parent.parent
             / "tools" / "premise" / "measure.py")
        spec = importlib.util.spec_from_file_location("_m_argv", p)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["_m_argv"] = mod
        spec.loader.exec_module(mod)
        return mod

    @staticmethod
    def _args(**over):
        import argparse
        d = dict(corpus="/tmp/corpus", n=None, seed=20260807,
                 candidates=0, candidate_families=0, extents_tol=None,
                 min_len=60, quantise=0, doc=None, fill_max=0.10,
                 hole_measure="bbox", merge_tol=0, iou=0.5,
                 min_block=200, truth_tex=None, ocr_dir=None,
                 first_page=0, split="document", what=["maths"])
        d.update(over)
        return argparse.Namespace(**d)

    def test_the_line_parses_back_to_the_arguments_it_was_built_from(self):
        m = self._mod()
        args = self._args()
        got = m.parse_argv_line(m.argv_line("maths", args))
        want = {"what": "maths"}
        want.update({k: "None" if v is None else str(v)
                     for k, v in vars(args).items() if k != "what"})
        self.assertEqual(got, want)

    def test_a_changed_flag_changes_the_line(self):
        """The line must be a function of the arguments, not a
        constant that happens to look right. Two runs differing only
        in --split must produce different provenance."""
        m = self._mod()
        a = m.argv_line("classify", self._args(split="document"))
        b = m.argv_line("classify", self._args(split="font"))
        self.assertNotEqual(a, b)
        self.assertEqual(m.parse_argv_line(b)["split"], "font")

    def test_it_names_one_measurement_not_the_whole_run(self):
        """A run of three subcommands prints three lines. A number
        lifted out of a combined log must carry a command that
        reproduces IT, not the batch it happened to be in."""
        m = self._mod()
        args = self._args(what=["maths", "classify", "fonts"])
        self.assertEqual(
            m.parse_argv_line(m.argv_line("classify", args))["what"],
            "classify")

    def test_a_line_that_is_not_provenance_is_refused(self):
        """Both sides: the accepting path is asserted above, so the
        guard cannot be made unconditional."""
        m = self._mod()
        with self.assertRaises(ValueError):
            m.parse_argv_line("    bitmap only  79.44%")
        with self.assertRaises(ValueError):
            m.parse_argv_line("# argv: measure.py maths notaflag 1")
