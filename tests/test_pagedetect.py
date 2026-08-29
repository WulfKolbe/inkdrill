"""320 — table selection by ordinal, and the run grouping it rests on.

Hermetic: `group_tables` is a pure function over (page, columns) pairs, so
the grouping rule is held without rendering anything. The rendering itself
is `scan_columns`, exercised by the corpus runs recorded in units.md §3.
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from pagedetect import group_tables                       # noqa: E402


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
