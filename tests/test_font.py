"""Unit 9 tests. Every test name is quoted verbatim in the status report."""

import subprocess
import unittest

from inkdrill.font import (MATH_FAMILIES, Coverage, FontKind, FontRecord,
                           PdfFontsUnavailable, Usability, coverage,
                           family_of, inventory, is_math_family, normalise,
                           parse_pdffonts, resolve, usability)

# Real pdffonts output, copied verbatim from the corpus. The column
# widths are the ones pdffonts actually emits.
REAL = """\
name                                 type              encoding         emb sub uni object ID
------------------------------------ ----------------- ---------------- --- --- --- ---------
NZRZGH+CMBX10                        Type 1C           Custom           yes yes no      10  0
Times-Roman                          Type 1            Standard         no  no  no       9  0
OFAQXU+CMR10                         Type 1C           Custom           yes yes no      14  0
QYXZHS+CMSS9                         Type 1            Builtin          yes yes no       7  0
JHHKUO+TimesNewRomanPSMT             TrueType          MacRoman         yes yes no      11  0
"""

# The awkward cases the corpus actually contains: a name with a space, a
# type with a space, a Type 3 font, and an encoding suffix.
AWKWARD = """\
name                                 type              encoding         emb sub uni object ID
------------------------------------ ----------------- ---------------- --- --- --- ---------
New Roman TrueType                   TrueType          WinAnsi          yes no  no      31  0
CKXQCW+LMRoman10-Regular-Identity-H  CID TrueType      Identity-H       yes yes yes     44  0
ABCDEE+Calibri,Bold                  TrueType          WinAnsi          yes yes no      52  0
T1                                   Type 3            Custom           yes no  no      61  0
Mincho Pr6N R-4520-Identity-H        CID Type 0C       Identity-H       yes yes no      70  0
"""

# A name longer than the rule line's 36-character name column, which
# pushes every later column right and defeats fixed-width slicing. This
# is the case the whitespace fallback exists for -- and until this
# fixture it had never executed in a test.
OVERFLOW = """\
name                                 type              encoding         emb sub uni object ID
------------------------------------ ----------------- ---------------- --- --- --- ---------
WXYZAB+AVeryLongEmbeddedFontNameThatOverflowsTheColumn Type 1C           Custom           yes yes no      88  0
"""

EMPTY = """\
name                                 type              encoding         emb sub uni object ID
------------------------------------ ----------------- ---------------- --- --- --- ---------
"""


class T9_1_ParsingIsFixedWidth(unittest.TestCase):
    """G1 and G2. Splitting on whitespace loses every name or type
    containing a space, and the corpus contains both."""

    def test_parses_a_real_pdffonts_table(self):
        recs = parse_pdffonts(REAL)
        self.assertEqual(len(recs), 5)
        self.assertEqual(recs[0].name, "NZRZGH+CMBX10")
        self.assertEqual(recs[0].kind, FontKind.TYPE1C)
        self.assertTrue(recs[0].embedded)
        self.assertTrue(recs[0].subset)

    def test_a_non_embedded_font_is_read_as_such(self):
        recs = parse_pdffonts(REAL)
        times = next(r for r in recs if r.name == "Times-Roman")
        self.assertFalse(times.embedded)
        self.assertEqual(times.kind, FontKind.TYPE1)

    def test_a_name_containing_a_space_survives(self):
        """`New Roman TrueType` -- a whitespace split would read the name
        as `New` and the type as `Roman`."""
        recs = parse_pdffonts(AWKWARD)
        rec = next(r for r in recs if r.name.startswith("New Roman"))
        self.assertEqual(rec.name, "New Roman TrueType")
        self.assertEqual(rec.kind, FontKind.TRUETYPE)

    def test_a_type_containing_a_space_survives(self):
        recs = parse_pdffonts(AWKWARD)
        kinds = {r.name: r.kind for r in recs}
        self.assertEqual(kinds["CKXQCW+LMRoman10-Regular-Identity-H"],
                         FontKind.CID_TRUETYPE)
        self.assertEqual(kinds["Mincho Pr6N R-4520-Identity-H"],
                         FontKind.CID_TYPE0C)

    def test_cid_type_zero_c_does_not_read_as_cid_type_zero(self):
        """Longest match wins, or `CID Type 0C` silently becomes a
        different kind."""
        self.assertEqual(FontKind.parse("CID Type 0C"), FontKind.CID_TYPE0C)
        self.assertEqual(FontKind.parse("CID Type 0"), FontKind.CID_TYPE0)

    def test_a_name_overflowing_its_column_takes_the_fallback(self):
        """The fallback exists because "widths are minimums: a long name
        can push later columns right". Until this fixture it had never
        executed in a test, so it would first have run on real corpus
        data, unverified, and mis-parsed silently rather than raising."""
        recs = parse_pdffonts(OVERFLOW)
        self.assertEqual(len(recs), 1)
        r = recs[0]
        self.assertEqual(
            r.name, "WXYZAB+AVeryLongEmbeddedFontNameThatOverflowsTheColumn")
        self.assertEqual(r.kind, FontKind.TYPE1C)
        self.assertEqual(r.encoding, "Custom")
        self.assertTrue(r.embedded)
        self.assertTrue(r.subset)
        self.assertFalse(r.unicode_ok)

    def test_the_overflowing_name_is_usable_like_any_other(self):
        """A mis-parse here would silently misclassify a perfectly good
        embedded font."""
        recs = parse_pdffonts(OVERFLOW)
        self.assertEqual(
            usability("WXYZAB+AVeryLongEmbeddedFontNameThatOverflowsTheColumn",
                      recs), Usability.FAST_PATH)

    def test_a_table_with_no_rows_parses_to_nothing(self):
        self.assertEqual(parse_pdffonts(EMPTY), [])

    def test_text_without_a_rule_line_parses_to_nothing(self):
        self.assertEqual(parse_pdffonts("not pdffonts output at all"), [])

    def test_parsing_runs_no_subprocess(self):
        """G1: this is what makes every guarantee here hermetic."""
        import subprocess
        real = subprocess.run

        def boom(*a, **k):
            raise AssertionError("parse_pdffonts must not run a subprocess")

        subprocess.run = boom
        try:
            self.assertEqual(len(parse_pdffonts(REAL)), 5)
        finally:
            subprocess.run = real


class T9_2_NameNormalisation(unittest.TestCase):
    """G3 and G4 -- a measured failure mode, not tidiness."""

    def test_a_subset_tag_is_stripped(self):
        self.assertEqual(normalise("NZRZGH+CMBX10"), "CMBX10")

    def test_only_a_six_letter_uppercase_tag_counts_as_a_subset(self):
        self.assertEqual(normalise("ABC+Times"), "ABC+Times")
        self.assertEqual(normalise("abcdef+Times"), "abcdef+Times")
        self.assertEqual(normalise("ABCDEFG+Times"), "ABCDEFG+Times")

    def test_an_encoding_suffix_is_stripped(self):
        self.assertEqual(normalise("LMRoman10-Regular-Identity-H"),
                         "LMRoman10-Regular")

    def test_a_style_suffix_is_preserved(self):
        """`Times,Bold` and `Times,Italic` are different fonts and must
        not collapse together."""
        self.assertEqual(normalise("ABCDEE+Calibri,Bold"), "Calibri,Bold")
        self.assertNotEqual(normalise("Times,Bold"), normalise("Times,Italic"))

    def test_the_corpus_mismatch_resolves(self):
        """pdfminer says `…-Regular`, pdffonts says `…-Regular-Identity-H`.
        Measured in the corpus; without this they never join."""
        recs = parse_pdffonts(AWKWARD)
        got = resolve("CKXQCW+LMRoman10-Regular", recs)
        self.assertIsNotNone(got)
        self.assertEqual(got.name, "CKXQCW+LMRoman10-Regular-Identity-H")

    def test_an_exact_match_wins_over_a_normalised_one(self):
        recs = parse_pdffonts(REAL)
        self.assertEqual(resolve("Times-Roman", recs).name, "Times-Roman")

    def test_a_base_name_collision_prefers_the_embedded_record(self):
        """A document may reference a standard font AND embed a subset of
        it. On list order alone the same glyph answered "not embedded" or
        "embedded outline" depending on which row pdffonts printed
        first."""
        not_emb = FontRecord("ABCDEF+Times-Roman", FontKind.TYPE1,
                             "WinAnsi", False, True, False)
        emb = FontRecord("GHIJKL+Times-Roman", FontKind.TYPE1,
                         "WinAnsi", True, True, False)
        for order in ([not_emb, emb], [emb, not_emb]):
            with self.subTest(first=order[0].name):
                got = resolve("MNOPQR+Times-Roman", order)
                self.assertTrue(got.embedded)
                self.assertEqual(usability("MNOPQR+Times-Roman", order),
                                 Usability.FAST_PATH)

    def test_a_base_name_collision_never_prefers_type_three(self):
        t3 = FontRecord("ABCDEF+Foo", FontKind.TYPE3, "Custom",
                        True, True, False)
        outline = FontRecord("GHIJKL+Foo", FontKind.TYPE1C, "Custom",
                             True, True, False)
        for order in ([t3, outline], [outline, t3]):
            with self.subTest(first=order[0].name):
                self.assertEqual(resolve("MNOPQR+Foo", order).kind,
                                 FontKind.TYPE1C)

    def test_a_collision_of_two_unusable_records_still_resolves(self):
        """It must still report WHY, not fall through to unresolvable."""
        a = FontRecord("ABCDEF+Bar", FontKind.TYPE1, "WinAnsi",
                       False, True, False)
        b = FontRecord("GHIJKL+Bar", FontKind.TYPE1, "WinAnsi",
                       False, True, False)
        self.assertEqual(usability("MNOPQR+Bar", [a, b]),
                         Usability.NOT_EMBEDDED)

    def test_an_unknown_name_resolves_to_nothing(self):
        self.assertIsNone(resolve("unknown", parse_pdffonts(REAL)))


class T9_3_UsabilityNamesItsReason(unittest.TestCase):
    """G5 and G7."""

    def test_an_embedded_outline_font_is_the_fast_path(self):
        recs = parse_pdffonts(REAL)
        self.assertEqual(usability("NZRZGH+CMBX10", recs),
                         Usability.FAST_PATH)

    def test_a_non_embedded_font_is_refused_by_name(self):
        recs = parse_pdffonts(REAL)
        self.assertEqual(usability("Times-Roman", recs),
                         Usability.NOT_EMBEDDED)

    def test_a_type_three_font_is_refused_by_name(self):
        recs = parse_pdffonts(AWKWARD)
        self.assertEqual(usability("T1", recs), Usability.TYPE3)

    def test_an_unresolvable_name_is_never_counted_as_usable(self):
        """The corpus's `'unknown'` fonts would otherwise inflate the
        fast-path share by several points."""
        recs = parse_pdffonts(REAL)
        self.assertEqual(usability("unknown", recs), Usability.UNRESOLVED)
        self.assertFalse(Usability.UNRESOLVED.usable)

    def test_only_the_fast_path_reports_as_usable(self):
        for u in Usability:
            with self.subTest(u.value):
                self.assertEqual(u.usable, u is Usability.FAST_PATH)

    def test_type_three_is_not_an_outline_kind(self):
        self.assertFalse(FontKind.TYPE3.is_outline)
        self.assertTrue(FontKind.TYPE1C.is_outline)
        self.assertTrue(FontKind.CID_TYPE0C.is_outline)


class T9_4_CoverageIsGlyphWeighted(unittest.TestCase):
    """G6, and the finding the whole premise check produced: the same
    corpus reads as 94.3% / 16.8% / 95.90% depending on what is counted,
    and only the glyph-weighted number answers U9's question."""

    def test_coverage_counts_glyph_instances_not_distinct_fonts(self):
        recs = parse_pdffonts(REAL)
        # one good font used 900 times, one bad font used once
        names = ["NZRZGH+CMBX10"] * 900 + ["Times-Roman"]
        cov = coverage(names, recs)
        self.assertEqual(cov.total, 901)
        self.assertEqual(cov.usable, 900)
        self.assertAlmostEqual(cov.fraction, 900 / 901, places=9)

    def test_the_document_weighted_view_would_disagree(self):
        """Counting distinct fonts, this document is 50% bad. Counting
        glyphs it is 0.1% bad. The metric choice inverts the reading,
        which is exactly what the premise check found."""
        recs = parse_pdffonts(REAL)
        names = ["NZRZGH+CMBX10"] * 999 + ["Times-Roman"]
        cov = coverage(names, recs)
        self.assertGreater(cov.fraction, 0.99)
        distinct = {"NZRZGH+CMBX10", "Times-Roman"}
        bad = sum(1 for n in distinct
                  if not usability(n, recs).usable)
        self.assertEqual(bad / len(distinct), 0.5)

    def test_every_rejection_is_reported_with_its_reason(self):
        recs = parse_pdffonts(AWKWARD)
        names = (["ABCDEE+Calibri,Bold"] * 10 + ["T1"] * 3
                 + ["nope"] * 2)
        cov = coverage(names, recs)
        self.assertEqual(cov.rejected(),
                         {Usability.TYPE3: 3, Usability.UNRESOLVED: 2})

    def test_counts_are_reported_beside_fractions(self):
        """A fraction alone hides a tiny denominator."""
        cov = coverage(["NZRZGH+CMBX10"], parse_pdffonts(REAL))
        self.assertEqual(cov.total, 1)
        self.assertIn("1/1", cov.report())

    def test_empty_coverage_is_not_a_division_by_zero(self):
        cov = coverage([], parse_pdffonts(REAL))
        self.assertEqual(cov.total, 0)
        self.assertEqual(cov.fraction, 0.0)
        self.assertEqual(cov.report(), "no glyphs")

    def test_report_lists_the_worst_rejection_first(self):
        recs = parse_pdffonts(AWKWARD)
        names = ["T1"] * 2 + ["nope"] * 9 + ["ABCDEE+Calibri,Bold"] * 5
        lines = coverage(names, recs).report().splitlines()
        self.assertIn("unresolvable", lines[1])
        self.assertIn("Type 3", lines[2])

    def test_resolution_is_cached_without_changing_the_answer(self):
        recs = parse_pdffonts(REAL)
        names = ["NZRZGH+CMBX10", "Times-Roman"] * 50
        cov = coverage(names, recs)
        self.assertEqual(cov.counts[Usability.FAST_PATH], 50)
        self.assertEqual(cov.counts[Usability.NOT_EMBEDDED], 50)


if __name__ == "__main__":
    unittest.main()


MATHY = """\
name                                 type              encoding         emb sub uni object ID
------------------------------------ ----------------- ---------------- --- --- --- ---------
NZRZGH+CMR10                         Type 1C           Custom           yes yes no      10  0
OFAQXU+CMMI10                        Type 1C           Custom           yes yes no      14  0
QUQGES+CMSY10                        Type 3            Custom           yes yes no      12  0
ZUMHSS+CMEX10                        Type 1C           Custom           no  no  no      21  0
"""


class T9_5_CoverageIsStratifiedByFamily(unittest.TestCase):
    """G8. An aggregate is dominated by body text, and the first
    application of the fast path is maths -- a small minority of any
    paper's glyph count. A 95.9% aggregate is compatible with maths
    coverage anywhere from 0% to 100%, so the aggregate alone cannot
    answer the question U9 exists to answer."""

    def test_family_strips_the_design_size(self):
        """CMSY7, CMSY10 and CMSY8 are one family at three sizes.
        Counting them separately would fragment exactly the population
        this exists to measure."""
        for n in ("NZRZGH+CMSY10", "AAAAAA+CMSY7", "CMSY8"):
            with self.subTest(n):
                self.assertEqual(family_of(n), "CMSY")

    def test_family_handles_style_and_encoding_suffixes(self):
        self.assertEqual(family_of("ABCDEE+Calibri,Bold"), "CALIBRI")
        self.assertEqual(family_of("CKXQCW+LMRoman10-Regular-Identity-H"),
                         "LMROMAN")

    def test_math_families_are_recognised(self):
        for n in ("CMMI10", "ABCDEF+CMSY7", "CMEX10", "MSAM10", "MSBM10"):
            with self.subTest(n):
                self.assertTrue(is_math_family(n))

    def test_opentype_math_fonts_are_recognised_by_suffix(self):
        for n in ("XITSMath-Regular", "LatinModernMath", "AsanaMath"):
            with self.subTest(n):
                self.assertTrue(is_math_family(n))

    def test_body_text_families_are_not_maths(self):
        for n in ("CMR10", "ABCDEE+Calibri,Bold", "Times-Roman",
                  "JHHKUO+TimesNewRomanPSMT"):
            with self.subTest(n):
                self.assertFalse(is_math_family(n))

    def test_a_healthy_aggregate_can_hide_broken_maths(self):
        """The finding, encoded. Body text is fine, maths is entirely
        off the fast path, and the aggregate still reads 98%."""
        recs = parse_pdffonts(MATHY)
        names = (["NZRZGH+CMR10"] * 4900          # body text, fine
                 + ["QUQGES+CMSY10"] * 50         # maths, Type 3
                 + ["ZUMHSS+CMEX10"] * 50)        # maths, not embedded
        cov = coverage(names, recs)
        self.assertGreater(cov.fraction, 0.97)    # aggregate looks fine
        self.assertEqual(cov.math_total, 100)
        self.assertEqual(cov.math_fraction, 0.0)  # maths is broken
        self.assertIn("maths glyphs: 0.00%", cov.report())

    def test_maths_coverage_is_counted_when_it_is_good(self):
        recs = parse_pdffonts(MATHY)
        names = ["OFAQXU+CMMI10"] * 30 + ["NZRZGH+CMR10"] * 70
        cov = coverage(names, recs)
        self.assertEqual(cov.math_total, 30)
        self.assertEqual(cov.math_fraction, 1.0)

    def test_by_family_carries_every_family_seen(self):
        recs = parse_pdffonts(MATHY)
        cov = coverage(["NZRZGH+CMR10"] * 3 + ["OFAQXU+CMMI10"] * 2, recs)
        self.assertEqual(sorted(cov.by_family), ["CMMI", "CMR"])
        self.assertEqual(cov.family_fraction("CMR"), 1.0)
        self.assertEqual(cov.family_fraction("cmmi"), 1.0)

    def test_a_document_with_no_maths_says_so_rather_than_zero(self):
        """0% and 'none seen' are different facts and must not read the
        same in a report."""
        cov = coverage(["NZRZGH+CMR10"] * 10, parse_pdffonts(MATHY))
        self.assertEqual(cov.math_total, 0)
        self.assertIn("maths glyphs: none seen", cov.report())

    def test_unresolved_maths_glyphs_count_against_maths(self):
        recs = parse_pdffonts(MATHY)
        cov = coverage(["ZZZZZZ+CMSY7"] * 10, recs)
        self.assertEqual(cov.math_total, 10)
        self.assertEqual(cov.math_fraction, 0.0)
        self.assertEqual(cov.counts[Usability.UNRESOLVED], 10)


# pdffonts output with a blank line in the body, and one with a rule line
# too short to be a real table. Both reach guards that a branch-mutation
# sweep found unreached.
BLANKS = """\
name                                 type              encoding         emb sub uni object ID
------------------------------------ ----------------- ---------------- --- --- --- ---------
NZRZGH+CMBX10                        Type 1C           Custom           yes yes no      10  0

OFAQXU+CMR10                         Type 1C           Custom           yes yes no      14  0
"""

SHORT_RULE = """\
name  type
----- ----
Foo   Type 1C
"""

MALFORMED_LONG = """\
name                                 type              encoding         emb sub uni object ID
------------------------------------ ----------------- ---------------- --- --- --- ---------
AVeryLongNameWithNoFlagsAtAllInThisRow whatever whatever whatever
"""


class T9_6_BranchesFoundByMutationSweep(unittest.TestCase):
    """Written after a `if True` / `if False` sweep over every non-trivial
    branch in the module surfaced eight unreached ones. Each of these is a
    branch that would otherwise first execute on real corpus data, and
    whose failure mode is a silently wrong record rather than an
    exception.

    See CLAUDE.md, "Mutate before you claim a guarantee is held"."""

    def test_a_blank_line_in_the_body_is_skipped(self):
        recs = parse_pdffonts(BLANKS)
        self.assertEqual([r.name for r in recs],
                         ["NZRZGH+CMBX10", "OFAQXU+CMR10"])

    def test_a_rule_line_with_too_few_columns_is_refused(self):
        """Better to return nothing than to invent columns."""
        self.assertEqual(parse_pdffonts(SHORT_RULE), [])

    def test_a_row_with_no_yes_no_flags_is_skipped_not_invented(self):
        """The fallback's own guard: a row it cannot read must be
        dropped, not turned into a FontRecord with garbage fields."""
        self.assertEqual(parse_pdffonts(MALFORMED_LONG), [])

    def test_an_unrecognised_type_reads_as_other_and_is_not_an_outline(self):
        self.assertEqual(FontKind.parse("Some Future Format"),
                         FontKind.OTHER)
        self.assertFalse(FontKind.OTHER.is_outline)

    def test_the_literal_word_other_is_not_a_font_kind(self):
        """FontKind.OTHER carries the value 'other'; matching on it would
        make a font literally typed 'other' outrank a real kind."""
        self.assertEqual(FontKind.parse("other"), FontKind.OTHER)
        self.assertEqual(FontKind.parse("Type 1C"), FontKind.TYPE1C)

    def test_an_exact_name_match_wins_over_an_embedded_sibling(self):
        """The exact pass runs before the embedded tie-break. Without
        that ordering, asking for a font BY NAME could return a different
        font that merely shares its base name."""
        exact = FontRecord("Times-Roman", FontKind.TYPE1, "Standard",
                           False, False, False)
        sibling = FontRecord("ABCDEF+Times-Roman", FontKind.TYPE1C,
                             "Custom", True, True, False)
        for order in ([exact, sibling], [sibling, exact]):
            with self.subTest(first=order[0].name):
                self.assertEqual(resolve("Times-Roman", order).name,
                                 "Times-Roman")

    def test_inventory_reports_a_failing_pdffonts_rather_than_guessing(self):
        real = subprocess.run

        class Proc:
            returncode = 1
            stdout = ""
            stderr = "Syntax Error: Could not read file"

        subprocess.run = lambda *a, **k: Proc()
        try:
            with self.assertRaises(PdfFontsUnavailable) as cm:
                inventory("nonexistent.pdf")
            self.assertIn("exited 1", str(cm.exception))
        finally:
            subprocess.run = real

    def test_inventory_reports_a_missing_binary(self):
        real = subprocess.run

        def boom(*a, **k):
            raise FileNotFoundError("pdffonts")

        subprocess.run = boom
        try:
            with self.assertRaises(PdfFontsUnavailable):
                inventory("whatever.pdf")
        finally:
            subprocess.run = real

    def test_inventory_parses_a_successful_run(self):
        real = subprocess.run

        class Proc:
            returncode = 0
            stdout = REAL
            stderr = ""

        subprocess.run = lambda *a, **k: Proc()
        try:
            self.assertEqual(len(inventory("ok.pdf")), 5)
        finally:
            subprocess.run = real
