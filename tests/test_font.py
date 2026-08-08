"""Unit 9 tests. Every test name is quoted verbatim in the status report."""

import unittest

from inkdrill.font import (Coverage, FontKind, FontRecord, Usability,
                           coverage, normalise, parse_pdffonts, resolve,
                           usability)

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
