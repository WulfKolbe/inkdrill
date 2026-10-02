"""The paragraph instrument's three rules, each of which was wrong first.

`measure.py paragraphs` is a harness, not package code, but these three
rules are the measurement: each produced a confident, reproducible,
WRONG number before it was fixed (out/683), and two of them produced the
same one -- "paragraph starts are not indented", which is untrue of
LaTeX. Both sides of each rule are asserted, because a rule tested only
where it fires can be made unconditional without failing anything.
"""
import importlib.util
import pathlib
import sys
import unittest


def _measure():
    p = (pathlib.Path(__file__).resolve().parent.parent
         / "tools" / "premise" / "measure.py")
    spec = importlib.util.spec_from_file_location("_m_par", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_m_par"] = mod
    spec.loader.exec_module(mod)
    return mod


M = _measure()
#: 40 characters of prose, so a paragraph clears the min_chars filter.
LONG = ("the automorphism group of a graphon is compact and metrizable "
        "under the topology described above")
LONG2 = ("conversely an arbitrary compact metrizable group arises as the "
         "automorphism group of some pure graphon")


def doc(body):
    return "\\begin{document}\n" + body + "\n\\end{document}\n"


class TP_1_ADisplayIsNotABreak(unittest.TestCase):
    """The rule that cost the most: a display equation does not end a
    paragraph. LaTeX sets the continuation unindented, and counting it as
    a new paragraph made the median indent at a gold boundary 0.02 line
    heights -- i.e. the gold claimed paragraphs are not indented."""

    def test_text_across_a_display_is_one_paragraph(self):
        gold, _ = M._par_gold(doc(
            LONG + "\n\\begin{equation}\n x = y \n\\end{equation}\n" + LONG2))
        self.assertEqual(len(gold), 1)
        self.assertIn("conversely", gold[0][1])

    def test_a_blank_line_after_the_display_DOES_break(self):
        """The other side. Without it the rule could be made
        unconditional -- never break -- and the first test still
        passes."""
        gold, _ = M._par_gold(doc(
            LONG + "\n\\begin{equation}\n x = y \n\\end{equation}\n\n" + LONG2))
        self.assertEqual(len(gold), 2)

    def test_a_blank_line_in_prose_breaks(self):
        gold, _ = M._par_gold(doc(LONG + "\n\n" + LONG2))
        self.assertEqual(len(gold), 2)

    def test_the_display_is_counted_where_a_reader_can_see_it(self):
        _, counts = M._par_gold(doc(
            LONG + "\n\\begin{equation}\n x=y \n\\end{equation}\n" + LONG2))
        self.assertEqual(counts["spanned: equation"], 1)


class TP_1b_TheWalkRecoversFromABadlyClosedEnvironment(unittest.TestCase):
    """Found by pdfdrill's cross-check, not here: sigma26-077's gold
    stopped at line 257 of 1,531 because line 261 writes `\\end {pmatrix}`
    WITH A SPACE, which is legal LaTeX. A depth counter that misses one
    close never recovers -- it skips the rest of the document and reports
    a plausible paragraph count for the fraction it did read (30 against
    107). The regex was the proximate cause; the counter was the defect.
    """

    def test_a_space_before_the_brace_still_closes(self):
        gold, _ = M._par_gold(doc(
            LONG + "\n" + r"\begin{equation}" + "\n x=y\n"
            + r"\end {equation}" + "\n\n" + LONG2))
        self.assertEqual(len(gold), 2)
        self.assertIn("conversely", gold[1][1])

    def test_no_space_still_closes(self):
        gold, _ = M._par_gold(doc(
            LONG + "\n" + r"\begin{equation}" + "\n x=y\n"
            + r"\end{equation}" + "\n\n" + LONG2))
        self.assertEqual(len(gold), 2)

    def test_an_inner_environment_left_open_does_not_swallow_the_document(self):
        """The stack pops BY NAME, so `pmatrix` left open inside
        `equation` is discarded when `equation` closes. With a counter
        this returned one paragraph and dropped everything after it."""
        gold, _ = M._par_gold(doc(
            LONG + "\n" + r"\begin{equation}" + "\n" + r"\begin{pmatrix} a"
            + "\n" + r"\end{equation}" + "\n\n" + LONG2))
        self.assertEqual(len(gold), 2)
        self.assertIn("conversely", gold[1][1])

    def test_an_unmatched_end_is_ignored_and_counted(self):
        gold, counts = M._par_gold(doc(LONG + "\n" + r"\end{equation}"
                                       + "\n\n" + LONG2))
        self.assertEqual(len(gold), 2)
        self.assertEqual(counts["unmatched \\end"], 1)

    def test_the_walk_reports_its_own_coverage(self):
        """077 was found by a peer because nothing printed that the gold
        stopped at 27.1% of the body."""
        gold, counts = M._par_gold(doc(LONG + "\n\n" + LONG2 + "\n" * 40))
        self.assertGreater(counts["body lines"], 40)
        self.assertGreater(counts["last paragraph at line"], 0)
        self.assertLess(counts["last paragraph at line"], counts["body lines"])


class TP_1c_ListItemsAreASplitRule(unittest.TestCase):
    """`--par-lists` decides whether an `\\item` is a paragraph. It is a
    flag and not a constant BECAUSE it changes the answer, so both of
    its settings are asserted -- with only the default asserted, the
    clause can be deleted and the suite still passes."""

    SRC = (LONG + "\n\n" + r"\begin{itemize}" + "\n" + r"\item " + LONG2
           + "\n" + r"\item " + LONG2 + "\n" + r"\end{itemize}" + "\n")

    def test_list_items_are_not_paragraphs_by_default(self):
        gold, _ = M._par_gold(doc(self.SRC))
        self.assertEqual(len(gold), 1)

    def test_with_lists_true_they_are(self):
        gold, _ = M._par_gold(doc(self.SRC), lists=True)
        self.assertGreater(len(gold), 1)


class TP_2_AnchorIsWordsThePageCanCarry(unittest.TestCase):
    """`\\cite{ACM}` prints as `[1]` and `\\begin{definition}` as
    `Definition 2.1.`, so an anchor containing either is a string no
    reading can hold. Anchoring on the first 40 characters located 27%
    of the gold; the first gap-free run locates 90%."""

    def test_a_citation_is_not_part_of_the_anchor(self):
        off, seg = M._par_anchor("In the paper \\cite{ACM}, Arena and "
                                 "Monti generalized the earlier result")
        self.assertNotIn("ACM", seg)
        self.assertIn("Monti generalized the earlier result", seg)
        self.assertGreater(off, 0)

    def test_clean_prose_anchors_at_the_start(self):
        """The positive side: nothing to cut, so the anchor is the
        paragraph itself and the offset is 0 -- which is what makes the
        located line the paragraph's FIRST line."""
        off, seg = M._par_anchor(LONG)
        self.assertEqual(off, 0)
        self.assertTrue(seg.startswith("the automorphism group"))

    def test_an_environment_name_is_not_prose(self):
        off, seg = M._par_anchor("\\begin{definition} a graphon consists "
                                 "of a standard probability space and a "
                                 "measurable symmetric function")
        self.assertNotIn("definition", seg)

    def test_a_long_citation_LABEL_cannot_become_the_anchor(self):
        """What the citation rule is actually FOR.

        Cutting `\\cite` as a plain macro already splits the sentence, so
        a short label is harmless either way -- the rule only earns its
        place against a label long enough to be mistaken for prose. This
        one is 34 characters and would otherwise be the first run of 20,
        i.e. the anchor, and it appears on no page.
        """
        off, seg = M._par_anchor(
            "As shown in \\cite{VeryLongLabelNameExceedingTwentyChars} the "
            "automorphism group is compact and metrizable")
        self.assertNotIn("VeryLongLabel", seg)
        self.assertIn("automorphism group is compact", seg)

    def test_a_paragraph_with_no_long_clean_run_yields_no_anchor(self):
        off, seg = M._par_anchor("$x$ \\cite{a} $y$ \\ref{b} $z$")
        self.assertIsNone(seg)


class TP_3_ABandIsChosenByOverlapNotByItsTop(unittest.TestCase):
    """A reader's box top includes the leading and sits ABOVE the ink, so
    matching a boundary by its top edge credited it to the line above --
    the indented `Conversely,` line of sigma26-073 p5 was scored as
    unindented because the band above it was not."""

    #: (y0, y1, left, right, ink) -- two text lines, 60 px apart
    BANDS = [(100, 160, 481, 2900, 9000), (220, 280, 560, 2900, 9000)]

    #: a reader's box for the SECOND line: its top carries the leading and
    #: reaches back into the first line's ink, its body covers the second.
    BOX = (155, 285)

    def test_the_band_is_the_one_the_box_mostly_covers(self):
        self.assertEqual(M._par_band_at(self.BANDS, *self.BOX), 1)

    def test_the_old_top_edge_rule_would_have_chosen_the_line_above(self):
        """The defect, asserted so it cannot come back. The old rule took
        the first band CONTAINING the top edge; this box's top is 5 px
        inside band 0 and its body is 65 px of band 1."""
        y, y2 = self.BOX
        contains_top = next(i for i, b in enumerate(self.BANDS)
                            if b[0] - 2 <= y <= b[1] + 2)
        self.assertEqual(contains_top, 0)
        self.assertEqual(M._par_band_at(self.BANDS, y, y2), 1)

    def test_a_box_well_inside_a_band_takes_that_band(self):
        self.assertEqual(M._par_band_at(self.BANDS, 110, 150), 0)

    def test_a_box_nowhere_near_any_band_is_refused(self):
        self.assertIsNone(M._par_band_at(self.BANDS, 900, 940))


class TP_4_ColumnsAreASplitRule(unittest.TestCase):
    """Two columns break the row-profile band model (recall 92.9% vs
    18.8%, no overlap), so the class is reported rather than averaged
    over."""

    @staticmethod
    def _lines(starts, pw=2000, type="text"):
        return [{"x": x, "w": 800, "pw": pw, "type": type} for x in starts]

    def test_one_column(self):
        self.assertEqual(M._par_columns(self._lines([100] * 20)), 1)

    def test_two_columns(self):
        self.assertEqual(
            M._par_columns(self._lines([100] * 10 + [1100] * 10)), 2)

    def test_centred_display_maths_is_not_a_second_column(self):
        """What the type filter is for. A display equation is wide and
        starts mid-page, and on that alone sigma26-085 -- a one-column
        maths paper -- was classed two-column by 16 equations and one
        sentence, which would have filed its 93.3% recall under the
        heading for pages the instrument cannot see."""
        lines = self._lines([100] * 10)
        lines += self._lines([1100] * 16, type="math")
        self.assertEqual(M._par_columns(lines), 1)

    def test_narrow_lines_do_not_vote(self):
        """A short line is not evidence of a column; only body-width
        lines are counted."""
        lines = [{"x": 1100, "w": 50, "pw": 2000} for _ in range(10)]
        lines += [{"x": 100, "w": 800, "pw": 2000} for _ in range(10)]
        self.assertEqual(M._par_columns(lines), 1)


if __name__ == "__main__":
    unittest.main()
