"""320 — table selection by ordinal, and the run grouping it rests on.
496 — the column count, which moved here so two harnesses read one
definition of it.

Hermetic: `group_tables` is a pure function over (page, columns) pairs, so
the grouping rule is held without rendering anything. The rendering itself
is `scan_columns`, exercised by the corpus runs recorded in units.md §3.
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import tempfile                                          # noqa: E402

from pagedetect import group_tables, target_columns       # noqa: E402


class T320_1_Grouping(unittest.TestCase):
    def test_g1_a_run_is_contiguous_and_constant(self):
        """2208.09292: equations 6, formulas 5, tables 4, image regions 6."""
        got = group_tables([(1, 6), (2, 5), (3, 4), (4, 6)])
        self.assertEqual([(t["ordinal"], t["columns"], t["pages"]) for t in got],
                         [(1, 6, [1]), (2, 5, [2]), (3, 4, [3]), (4, 6, [4])])

    def test_g1_a_table_spanning_pages_is_one_run(self):
        got = group_tables([(1, 6), (2, 6), (3, 6), (4, 5), (5, 5)])
        self.assertEqual([(t["ordinal"], t["columns"], t["pages"]) for t in got],
                         [(1, 6, [1, 2, 3]), (2, 5, [4, 5])])

    def test_g2_a_page_with_no_lattice_ends_the_run(self):
        """Two tables of equal width separated by prose are TWO tables.
        `probe`'s gap tolerance of 3 stitched pages 1 and 4 of 2208.09292
        into one selection spanning all four tables — 69 rows against 6
        identifiers."""
        got = group_tables([(1, 6), (2, 0), (3, 6)])
        self.assertEqual([(t["ordinal"], t["columns"], t["pages"]) for t in got],
                         [(1, 6, [1]), (2, 6, [3])])
        self.assertTrue(all(t["columns"] for t in got))

    def test_g3_ordinals_are_one_based_in_page_order(self):
        got = group_tables([(1, 4), (2, 5), (3, 6)])
        self.assertEqual([t["ordinal"] for t in got], [1, 2, 3])

    def test_empty_and_blank_documents(self):
        self.assertEqual(group_tables([]), [])
        self.assertEqual(group_tables([(1, 0), (2, 0)]), [])

    def test_adjacent_tables_of_equal_width_MERGE(self):
        """A LIMIT, recorded rather than hidden. 0049's equations and
        formulas are both 5 columns and adjacent, so they group as ONE run
        and the ordinal is not the longtable index there. Contiguity plus
        equal width cannot separate them; only the producer's own table
        boundaries could, and this tool does not see those."""
        got = group_tables([(1, 5), (2, 5), (3, 6), (4, 6)])
        self.assertEqual(len(got), 2)
        self.assertEqual(got[0]["pages"], [1, 2])


if __name__ == "__main__":
    unittest.main()


class T496_1_TargetColumns(unittest.TestCase):
    """The per-document column count, moved out of `reportcompare` when a
    second harness needed it (496).

    A constant was wrong twice in one day here: 5 before pdfdrill's 099
    added a Confidence column and 6 after, and the corpus holds both
    eras, so any single number reports a whole era as "no display
    pages". These hold the rule that replaced it.

    EVERY HEADER BELOW IS A REAL ONE, copied from a report.tex in the
    library -- except the pre-099 five-column form, which is the real
    six-column line with `Conf.` deleted, exactly as the docstring
    defines that era. A header invented to fit the rule cannot fail it:
    the first draft of this class asserted 6 against a line carrying
    four ampersands, and the fixture was wrong rather than the function.
    """

    #: the post-099 display-equation header, 843 documents in the library
    HDR6 = (r"\textbf{Identifier} & \textbf{Page} & \textbf{Conf.} "
            r"& \textbf{LaTeX source} & \textbf{Rendered} "
            r"& \textbf{Scan image} \\")
    #: the same without Conf. -- the pre-099 era
    HDR5 = (r"\textbf{Identifier} & \textbf{Page} "
            r"& \textbf{LaTeX source} & \textbf{Rendered} "
            r"& \textbf{Scan image} \\")
    #: the unrecovered-image-regions table, 272 documents in the
    #: library. It carries `Scan image` and NO `Rendered`, so it is the
    #: fixture that makes the `Rendered` half of the condition
    #: load-bearing -- without it the condition can be deleted and the
    #: suite still passes, and this table's width, 4, would be returned
    #: for a document whose display table has 6 columns.
    HDR_REGIONS = (r"\textbf{Identifier} & \textbf{Page} "
                   r"& \textbf{Content (LaTeX source if any)} "
                   r"& \textbf{Scan image} \\")
    #: a DIFFERENT real table that also carries Rendered, and whose
    #: last column is `Scan` rather than `Scan image`
    HDR_OTHER = (r"\textbf{Identifier} & \textbf{Page} & \textbf{Class} "
                 r"& \textbf{Source} & \textbf{Author source} "
                 r"& \textbf{Rendered} & \textbf{Scan} \\")

    def _tex(self, body):
        p = pathlib.Path(tempfile.mkdtemp()) / "report.tex"
        p.write_text(body)
        return p

    def test_g1_counts_the_post_099_six_column_header(self):
        self.assertEqual(target_columns(self._tex(self.HDR6)), 6)

    def test_g1_counts_the_pre_099_five_column_header(self):
        """The era a constant of 6 reports as having no display pages."""
        self.assertEqual(target_columns(self._tex(self.HDR5)), 5)

    def test_g2_a_header_without_a_scan_column_is_none(self):
        """None is a REASON -- this document's table has nothing to
        compare -- and must not be read as a count of zero. This is the
        real `Rendered`-without-`Scan image` header, 492 documents."""
        self.assertIsNone(target_columns(self._tex(
            self.HDR6.replace(r"& \textbf{Scan image} ", ""))))

    def test_g2_a_missing_file_is_none_not_an_exception(self):
        self.assertIsNone(
            target_columns(pathlib.Path("/nonexistent/report.tex")))

    def test_g3_a_rendered_header_without_scan_image_is_skipped_over(self):
        """Both sides of the refusal in one document. The image-regions
        table carries `Rendered` and `Scan`, and appears FIRST; the
        display-equation table carries `Rendered` and `Scan image`.
        Matching on `Rendered` alone would return 7 -- the wrong table's
        width -- and the whole document would then be probed for
        7-column pages and report none."""
        both = self.HDR_OTHER + "\n" + self.HDR6
        self.assertEqual(target_columns(self._tex(both)), 6)

    def test_g3_a_scan_image_header_without_rendered_is_skipped_over(self):
        """The other half of the same condition. The image-regions table
        carries `Scan image` and no `Rendered`; matching on `Scan image`
        alone returns 4 and the document is then probed for 4-column
        pages. Placed FIRST, so first-match cannot rescue it."""
        both = self.HDR_REGIONS + "\n" + self.HDR6
        self.assertEqual(target_columns(self._tex(both)), 6)

    def test_g3_the_first_qualifying_header_wins(self):
        """And when two headers BOTH qualify, it is the first, not the
        widest -- the accepting path, asserted next to the refusal."""
        both = self.HDR5 + "\n" + self.HDR6
        self.assertEqual(target_columns(self._tex(both)), 5)
