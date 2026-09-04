"""597 -- the identifier join, and the three extraction traps it carries.

Every fixture below is a REAL shape taken from the corpus, because all
three traps produced clean-looking wrong answers that a fixture built
from the rule could not have caught:

  `0049_DIA_0001`             an underscore before the digits
  `Geometric_topology_EQ0145` long enough to wrap the column
  0049's image rows            returned 1, 3, 4, 5, 2 by reading order

The counts asserted are the measured ones: 34 rows over 3 tables on
0049, and Geometric_topology's image table spanning two runs.
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from inkdrill.rowjoin import Row, find_identifiers, join    # noqa: E402


def manifest(bibkey, *tables):
    return {"bibkey": bibkey,
            "tables": [{"ordinal": i, "identifiers": list(ids)}
                       for i, ids in enumerate(tables, 1)]}


class T597_1_Extraction(unittest.TestCase):
    def test_g2_an_underscore_before_the_digits_is_found(self):
        """The trap that dropped a whole table: the guessed pattern
        `<bibkey>_[A-Z]{2,4}[0-9a-f]+` cannot match `DIA_0001`."""
        known = {"0049_DIA_0001"}
        self.assertEqual(
            find_identifiers("x 0049_DIA_0001 y", "0049", known),
            ["0049_DIA_0001"])

    def test_g2_the_manifest_decides_not_the_pattern(self):
        """A token of the right SHAPE that the manifest does not list
        is not an identifier. The pattern is deliberately permissive,
        so this is the only thing keeping it honest."""
        self.assertEqual(
            find_identifiers("0049_EQ0001 0049_ZZ9999", "0049",
                             {"0049_EQ0001"}),
            ["0049_EQ0001"])

    def test_g3_a_wrapped_identifier_is_rejoined(self):
        """`Geometric_topology_` fills the Identifier column and breaks
        after the underscore; in content-stream order the halves are
        adjacent. 6,485 of 6,717 rows read as missing without this."""
        text = "Geometric_topology_\nEQ0145  0.791"
        self.assertEqual(
            find_identifiers(text, "Geometric_topology",
                             {"Geometric_topology_EQ0145"}),
            ["Geometric_topology_EQ0145"])

    def test_g3_a_short_identifier_is_unaffected_by_the_rejoin(self):
        """BOTH SIDES: the un-wrap must not corrupt the case that never
        wrapped, which is most of the corpus."""
        self.assertEqual(
            find_identifiers("0049_EQ0001\n0049_EQ0002", "0049",
                             {"0049_EQ0001", "0049_EQ0002"}),
            ["0049_EQ0001", "0049_EQ0002"])

    def test_g3_the_rejoin_does_not_leap_a_blank_line(self):
        """A dangling bibkey with an EMPTY line after it is not a wrap;
        joining across it would invent an identifier from two rows."""
        self.assertEqual(
            find_identifiers("0049_\n\nEQ0001", "0049", {"0049_EQ0001"}),
            [])


class T597_2_Order(unittest.TestCase):
    ROWS = ["0049_DIA_000%d" % i for i in range(1, 6)]

    def test_g4_order_comes_from_the_manifest_not_the_page(self):
        """0049's real reading order. The right SET in the wrong
        SEQUENCE mispairs every row while the counts look perfect."""
        page = " ".join(["0049_DIA_0001", "0049_DIA_0003", "0049_DIA_0004",
                         "0049_DIA_0005", "0049_DIA_0002"])
        j = join(manifest("0049", self.ROWS), [page])
        self.assertEqual([r.identifier for r in j.rows], self.ROWS)
        self.assertEqual([r.index for r in j.rows], [0, 1, 2, 3, 4])

    def test_g5_a_row_on_two_pages_keeps_the_first(self):
        j = join(manifest("0049", ["0049_EQ0001"]),
                 ["", "0049_EQ0001", "0049_EQ0001"])
        self.assertEqual(j.rows[0].page, 2)

    def test_g7_every_manifest_row_appears_exactly_once_in_order(self):
        m = manifest("0049", ["0049_EQ0001"],
                     ["0049_FO0001", "0049_FO0002"])
        j = join(m, ["0049_FO0002 0049_EQ0001 0049_FO0001"])
        self.assertEqual([(r.table, r.index) for r in j.rows],
                         [(1, 0), (2, 0), (2, 1)])


class T597_3_Diagnostics(unittest.TestCase):
    def test_g6_a_row_on_no_page_is_reported_not_omitted(self):
        """A short result and a complete one must not look alike."""
        j = join(manifest("0049", ["0049_EQ0001", "0049_EQ0002"]),
                 ["0049_EQ0001"])
        self.assertEqual(j.missing, ["0049_EQ0002"])
        self.assertEqual(len(j.rows), 2)
        self.assertIsNone(j.rows[1].page)

    def test_g2_unknown_tokens_are_returned_and_this_caught_trap_one(self):
        """The diagnostic, asserted because it is the thing that made
        the first trap visible at all."""
        j = join(manifest("0049", ["0049_EQ0001"]),
                 ["0049_EQ0001 0049_DIA_0001 0049_DIA_0001"])
        self.assertEqual(j.unknown, {"0049_DIA_0001": 2})

    def test_g2_no_unknowns_when_the_manifest_covers_the_page(self):
        """The accepting side of the same diagnostic -- a permanently
        non-empty `unknown` would be noise nobody reads."""
        j = join(manifest("0049", ["0049_EQ0001"]), ["0049_EQ0001"])
        self.assertEqual(j.unknown, {})

    def test_a_manifest_with_no_identifiers_is_refused(self):
        with self.assertRaises(ValueError):
            join(manifest("0049", []), ["text"])

    def test_g1_the_join_is_pure_over_the_text_it_is_given(self):
        """No path, no process: the same inputs twice give equal
        results, which is what lets the traps be tested without a PDF."""
        m = manifest("0049", ["0049_EQ0001"])
        self.assertEqual(join(m, ["0049_EQ0001"]).rows,
                         join(m, ["0049_EQ0001"]).rows)


class T597_4_Shape(unittest.TestCase):
    def test_by_table_groups_in_row_order(self):
        m = manifest("D", ["D_EQ0001"], ["D_FO0001", "D_FO0002"])
        j = join(m, ["D_FO0002 D_EQ0001 D_FO0001"])
        bt = j.by_table()
        self.assertEqual(sorted(bt), [1, 2])
        self.assertEqual([r.identifier for r in bt[2]],
                         ["D_FO0001", "D_FO0002"])

    def test_page_of_omits_the_rows_no_page_carried(self):
        j = join(manifest("D", ["D_EQ0001", "D_EQ0002"]), ["D_EQ0001"])
        self.assertEqual(j.page_of(), {"D_EQ0001": 1})

    def test_a_row_is_a_named_tuple_of_table_index_identifier_page(self):
        j = join(manifest("D", ["D_EQ0001"]), ["D_EQ0001"])
        self.assertEqual(j.rows[0], Row(1, 0, "D_EQ0001", 1))
