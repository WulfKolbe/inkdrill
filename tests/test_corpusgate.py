"""P18/P19: the corpus gate and the finding vocabulary.

Both sides of every refusal are asserted -- a guard tested only by
`assertRaises` can be made unconditional and still pass.
"""

import io
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent
                       / "tools"))

import corpusgate                                          # noqa: E402
import inkfit                                              # noqa: E402,F401
from findings import FLAGS, flag_of                        # noqa: E402

ITEMS = [f"doc{i:03d}" for i in range(200)]


def run(items=ITEMS, limit="3", yes=False, pages=None, ask=None,
        interactive=False):
    out = io.StringIO()
    got = corpusgate.gate("t", items, limit, yes, count_pages=pages,
                          stream=out, ask=ask, interactive=interactive)
    return got, out.getvalue()


class P18_1_LimitIsRequired(unittest.TestCase):

    def test_missing_limit_refuses_and_a_given_limit_runs(self):
        with self.assertRaises(SystemExit) as cm:
            run(limit=None)
        self.assertIn("--limit is required", str(cm.exception))
        self.assertIn(str(corpusgate.DEFAULT_SAMPLE), str(cm.exception))
        got, _ = run(limit="3")                    # the accepting side
        self.assertEqual(got, ITEMS[:3])

    def test_all_is_the_explicit_corpus_opt_in(self):
        got, _ = run(limit="all", yes=True)
        self.assertEqual(len(got), len(ITEMS))

    def test_a_nonsense_limit_refuses(self):
        for bad in ("many", "0", "-2"):
            with self.assertRaises(SystemExit):
                run(limit=bad)


class P18_2_PlanIsPrinted(unittest.TestCase):

    def test_plan_names_documents_pages_and_the_threshold(self):
        _, txt = run(limit="3", pages=lambda i: 7)
        self.assertIn("3 of 200 documents", txt)
        self.assertIn("21 pages", txt)
        self.assertIn(str(corpusgate.CONFIRM_DOCS), txt)

    def test_a_large_page_count_is_marked_as_an_estimate(self):
        """Exact up to EXACT_PAGES_UPTO, estimated above -- and the
        estimate must SAY so, never print as a bare number."""
        calls = []

        def pages(i):
            calls.append(i)
            return 10
        _, exact = run(limit="100", yes=True, pages=pages)
        self.assertIn("1000 pages", exact)
        self.assertNotIn("~", exact)
        self.assertEqual(len(calls), 100)
        calls.clear()
        _, est = run(limit="200", yes=True, pages=pages)
        self.assertIn("~2000 pages", est)
        self.assertIn("estimated", est)
        # and the estimate is cheap: a sample, not every document
        self.assertLessEqual(len(calls), corpusgate.ESTIMATE_SAMPLE)


class P18_3_ConfirmationAboveTheThreshold(unittest.TestCase):

    def test_small_runs_never_ask(self):
        asked = []
        got, _ = run(limit="3", ask=lambda q: asked.append(q) or "n")
        self.assertEqual(got, ITEMS[:3])
        self.assertEqual(asked, [])

    def test_large_non_interactive_refuses_instead_of_hanging(self):
        """`ask` must never be reached without a terminal. Asserting
        that explicitly turns a dropped guard into a FAILURE instead
        of a hang -- with the guard forced off, the mutant blocked on
        input() and the sweep read as a stalled suite."""
        def never(_q):
            self.fail("asked for confirmation with no terminal")
        with self.assertRaises(SystemExit) as cm:
            run(limit="200", interactive=False, ask=never)
        self.assertIn("--yes", str(cm.exception))
        got, _ = run(limit="200", yes=True)         # the accepting side
        self.assertEqual(len(got), 200)

    def test_large_interactive_honours_the_answer_both_ways(self):
        got, _ = run(limit="200", interactive=True, ask=lambda q: "y")
        self.assertEqual(len(got), 200)
        with self.assertRaises(SystemExit) as cm:
            run(limit="200", interactive=True, ask=lambda q: "n")
        self.assertIn("not confirmed", str(cm.exception))

    def test_the_page_threshold_triggers_it_too(self):
        """Few documents, many pages: the threshold is either/or, so a
        3-document run of huge books still needs confirmation."""
        def never(_q):
            self.fail("asked for confirmation with no terminal")
        with self.assertRaises(SystemExit):
            run(limit="3", interactive=False, ask=never,
                pages=lambda i: corpusgate.CONFIRM_PAGES)


class P19_1_FindingVocabulary(unittest.TestCase):

    def test_every_flag_fires_and_the_measured_floors_gate_them(self):
        import findings as F
        self.assertEqual(flag_of(0, 0, True), "clean")
        # inside BOTH measured bands -> not a finding
        self.assertEqual(flag_of(F.NOISE_DISTANCE, F.NOISE_COMP_DELTA,
                                 True), "noise")
        self.assertEqual(flag_of(1, 0, False), "noise")
        # one step past either band is a finding again
        self.assertEqual(flag_of(99, F.NOISE_COMP_DELTA + 1, False),
                         "component")
        self.assertEqual(flag_of(F.NOISE_DISTANCE + 1, 0, True),
                         "stable")
        self.assertEqual(flag_of(F.NOISE_DISTANCE + 1, 0, False),
                         "weak")
        # every class reachable
        self.assertEqual(set(FLAGS),
                         {flag_of(0, 0, True), flag_of(1, 0, False),
                          flag_of(99, 9, False),
                          flag_of(F.NOISE_DISTANCE + 1, 0, True),
                          flag_of(F.NOISE_DISTANCE + 1, 0, False)})

    def test_the_floors_are_arguments_not_baked_constants(self):
        """A caller measuring its own corpus passes its own numbers;
        with the floor at zero the same row is a finding again."""
        self.assertEqual(flag_of(3, 1, False), "noise")
        self.assertEqual(flag_of(3, 1, False, noise_distance=0,
                                 noise_comp_delta=0), "component")


if __name__ == "__main__":
    unittest.main()


class Q1_1_MathOverlap(unittest.TestCase):
    """The excess-fraction metric and its attribution rule."""

    class B:
        def __init__(self, x0, y0, x1, y1, area=None):
            self.id = 0
            self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1
            self.area = area if area is not None else \
                (x1 - x0 + 1) * (y1 - y0 + 1)

    def test_fraction_is_zero_inside_and_grows_with_the_excess(self):
        import inkfit
        region = (0, 0, 100, 10)                    # area 1000
        self.assertEqual(inkfit.excess_fraction((10, 2, 90, 8), region), 0.0)
        # 100x10 of ink, half of it outside -> excess 500 of 1000
        self.assertAlmostEqual(
            inkfit.excess_fraction((50, 0, 150, 10), region), 0.5)

    def test_a_region_with_no_ink_measures_nothing_not_zero(self):
        import inkfit
        self.assertEqual(inkfit.overlaps([("k", (0, 0, 10, 10))], []), [])
        self.assertIsNone(inkfit.ink_bbox([]))

    def test_a_crossing_rule_is_not_the_expressions_ink(self):
        """0802.3344 p9: a 795x2 page rule centred in a 391 px region
        drove the fraction to 0.994 -- an attribution artifact, not
        under-coverage. A rule LONGER than the region is dropped; a
        glyph of the same span is not, and a short bar (a fraction
        rule) stays."""
        import inkfit
        region = (100.0, 0.0, 200.0, 20.0)
        rule = self.B(0, 9, 400, 10)                # 401x2, aspect 200
        glyph = self.B(0, 0, 400, 20, area=200)     # same span, not solid
        bar = self.B(120, 9, 180, 10)               # fraction bar, fits
        self.assertEqual(inkfit.assign([rule], region), [])
        self.assertEqual(len(inkfit.assign([glyph], region)), 1)
        self.assertEqual(len(inkfit.assign([bar], region)), 1)
        # and the filter is what does it, not the centre test
        self.assertEqual(
            len(inkfit.assign([rule], region,
                              exclude_crossing_rules=False)), 1)

    def test_ink_outside_the_region_is_not_assigned_by_centre(self):
        import inkfit
        region = (100.0, 0.0, 200.0, 20.0)
        far = self.B(300, 5, 320, 15)
        self.assertEqual(inkfit.assign([far], region), [])
