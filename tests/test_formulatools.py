"""The formula-evidence harness, checked hermetically.

Three defects were found on 2026-09-11 in the TOOLS that measure the
published formula evidence -- not in a module -- and each produced a
plausible wrong number rather than an error:

  * `rows()` matched the whole table body with one lazy regex, so a row
    with no published crop took the NEXT row's picture and swallowed
    that row, and `\\lowconf{...}` leaked into 35 ids of 1510.06699.
  * rows were then split on `\\\\ \\hline`, which an `array` inside the
    maths contains too, and johnston FO2040 lost its maths and its crop.
  * the MathPix -> page-image mapping read ONE ratio off page 1's width.
    MathPix's page is the CropBox and `inspect/pages` the MediaBox, so on
    the four books whose CropBox is inset it cut the wrong strip of page.

`tools/` holds scripts, not a package, so they are loaded by path.
Nothing here reads the corpus; the fixture NUMBERS are real, measured on
cardona-qft-methods p94 and 0902.0431.
"""

import importlib.util
import json
import pathlib
import tempfile
import unittest

_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(
        "_" + name, _ROOT / "tools" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


ff = _load("formulafind")
fm = _load("formulamarks")
fr = fm.fr                  # the policy module formulamarks itself uses

_HEAD = r"""\begin{longtable}{llllll}
ID & Page & Conf & Source & Rendered & Scan \\ \hline
\endhead
"""


def _row(ident, page, conf, source, rendered, image):
    return (rf"\ident{{{ident}}} & {page} & {conf} & {source} & {rendered}"
            rf" & {image} \\ \hline" + "\n")


def _img(name):
    return (r"\raisebox{-0.5ex}{\includegraphics[width=31.2mm]"
            rf"{{report-crops-b/{name}.jpg}}}}")


FIXTURE = (_HEAD
           + _row(r"A\_FO0001", 3, r"\confcell{confgreen}{0.996}", "src",
                  r"\FitMath{$\displaystyle \{x \mid x>0\}$}", _img("A_FO0001"))
           # no published crop: the old parser gave this row FO0003's
           # picture and dropped FO0003
           + _row(r"A\_FO0002", 3, r"\confcell{confgreen}{1.000}", "src",
                  r"\FitMath{$\displaystyle y$}", "---")
           + _row(r"A\_FO0003", 3, r"\confcell{confgreen}{0.990}", "src",
                  r"\FitMath{$\displaystyle w_{3}$}", _img("A_FO0003"))
           + _row(r"A\_FO0004}\lowconf{0.000", 4, r"\confcell{confred}{0.000}",
                  "src", r"\FitMath{$\displaystyle z$}", _img("A_FO0004"))
           # the maths itself holds the row terminator
           + _row(r"A\_FO0005", 5, r"\confcell{confgreen}{1.000}", "src",
                  r"\FitMath{$\displaystyle \left[\begin{array}{c|c} 1 & 0 "
                  r"\\ \hline 0 & 1 \end{array}\right]$}", _img("A_FO0005"))
           # not rendered by the producer, and no confidence
           + _row(r"A\_FO0006", 6, "---",
                  r"{\ttfamily\footnotesize \textbackslash{}xrightarrow}",
                  r"{\ttfamily\footnotesize not rendered}", _img("A_FO0006"))
           + r"\end{longtable}")


class TF_1_RowsParser(unittest.TestCase):
    """One record per `\\ident`, and a missing cell is None -- never the
    neighbour's."""

    @classmethod
    def setUpClass(cls):
        td = tempfile.TemporaryDirectory()
        cls.addClassCleanup(td.cleanup)
        p = pathlib.Path(td.name) / "evidence-formula.tex"
        p.write_text(FIXTURE)
        cls.rows = {r["id"]: r for r in ff.rows(p)}

    def test_every_ident_is_one_record(self):
        self.assertEqual(sorted(self.rows),
                         [f"A_FO000{i}" for i in range(1, 7)])

    def test_a_row_without_a_crop_does_not_take_the_next_rows(self):
        self.assertIsNone(self.rows["A_FO0002"]["crop"])
        self.assertEqual(self.rows["A_FO0003"]["crop"],
                         "report-crops-b/A_FO0003.jpg")
        self.assertEqual(self.rows["A_FO0003"]["math"], "w_{3}")

    def test_lowconf_stays_out_of_the_id(self):
        r = self.rows["A_FO0004"]
        self.assertTrue(r["lowconf"])
        self.assertEqual(r["conf"], "0.000")
        self.assertFalse(self.rows["A_FO0001"]["lowconf"])

    def test_an_hline_inside_the_maths_does_not_end_the_row(self):
        r = self.rows["A_FO0005"]
        self.assertTrue(r["math"].endswith(r"\end{array}\right]"), r["math"])
        self.assertEqual(r["crop"], "report-crops-b/A_FO0005.jpg")

    def test_escaped_braces_are_literal(self):
        self.assertEqual(self.rows["A_FO0001"]["math"], r"\{x \mid x>0\}")

    def test_not_rendered_and_no_confidence_are_none(self):
        r = self.rows["A_FO0006"]
        self.assertIsNone(r["math"])
        self.assertIsNone(r["conf"])
        self.assertEqual(r["page"], "6")


class TF_2_HostLineRule(unittest.TestCase):
    """pdfdrill's rule: the FIRST span in document order, by equality."""

    @classmethod
    def setUpClass(cls):
        td = tempfile.TemporaryDirectory()
        cls.addClassCleanup(td.cleanup)
        lib = pathlib.Path(td.name)
        (lib / "B").mkdir()
        A = dict(top_left_x=10, top_left_y=20, width=300, height=40)
        M = dict(top_left_x=10, top_left_y=90, width=300, height=80)
        Bx = dict(top_left_x=10, top_left_y=20, width=500, height=40)
        cls.A, cls.Bx = A, Bx
        (lib / "B" / "B.lines.json").write_text(json.dumps({"pages": [
            {"page": 1, "lines": [
                {"type": "text", "region": A,
                 "text": r"see \(G\) and $x$, costs \$5 and \$6"},
                {"type": "math", "region": M, "text": r"\(H\)"}]},
            {"page": 2, "lines": [
                {"type": "text", "region": Bx,
                 "text": r"\(G\) again, \(H\) and \( y \)"}]}]}))
        cls.first = ff.first_occurrence_lines(lib, "B")

    def test_the_first_occurrence_wins(self):
        self.assertEqual(self.first["G"], (1, self.A))

    def test_both_delimiters_and_the_body_is_stripped(self):
        self.assertEqual(self.first["x"], (1, self.A))
        self.assertEqual(self.first["y"], (2, self.Bx))

    def test_a_display_line_is_not_a_host(self):
        self.assertEqual(self.first["H"], (2, self.Bx))

    def test_an_escaped_dollar_is_not_a_delimiter(self):
        self.assertFalse([k for k in self.first if "5" in k])

    def test_rows_match_by_equality_and_ignore_their_page_column(self):
        got = ff.match_rows_first(
            [dict(id="r1", page="7", math=" G "),
             dict(id="r2", page="1", math="Gx"),
             dict(id="r3", page="1", math=None)], self.first)
        self.assertEqual(got, {"r1": (1, self.A)})


class TF_3_PageFrame(unittest.TestCase):
    """MathPix page px -> inspect/pages px. The expected values come from
    DPI ARITHMETIC (MathPix 250, pages 400, 72 pt per inch), not from the
    formula under test."""

    MEDIA = [0.0, 0.0, 595.0, 842.0]
    CROP = [90.72, 133.90, 501.40, 753.40]          # cardona p94
    REGION = dict(top_left_x=142, top_left_y=680, width=807, height=46)

    def frame(self):
        return ff.frame_of(self.MEDIA, self.CROP, 3306, 4678, 1426, 2152)

    def test_an_inset_cropbox_moves_the_origin(self):
        x, y, w, h = ff.frame_rect(self.REGION, self.frame())
        k = 400 / 72
        self.assertAlmostEqual(x, 90.72 * k + 142 * 1.6, delta=2)
        self.assertAlmostEqual(y, (842 - 753.40) * k + 680 * 1.6, delta=2)
        self.assertAlmostEqual(w, 807 * 1.6, delta=2)
        self.assertAlmostEqual(h, 46 * 1.6, delta=2)

    def test_the_old_width_ratio_missed_by_hundreds_of_pixels(self):
        """Pins the defect: one ratio off the width put this line ~400 px
        left, five line heights -- a different part of the page that
        still looks like a line."""
        x, _, _, h = ff.frame_rect(self.REGION, self.frame())
        old_x = 142 * 3306 / 1426
        self.assertGreater(x - old_x, 5 * h)

    def test_no_inset_is_a_pure_scale(self):
        f = ff.frame_of([0, 0, 612, 792], [0, 0, 612, 792], 3400, 4400,
                        2125, 2750)                   # 0902.0431
        for got, want in zip(f, (1.6, 1.6, 0.0, 0.0)):
            self.assertAlmostEqual(got, want, places=9)

    def test_a_page_image_that_is_not_the_mediabox_is_refused(self):
        # the same page rendered from its CropBox at 400 dpi
        self.assertIsNone(ff.frame_of(self.MEDIA, self.CROP, 2282, 3442,
                                      1426, 2152))
        self.assertIsNotNone(self.frame())


class TF_4_MarksContract(unittest.TestCase):
    """What formulamarks hands pdfdrill."""

    def test_rect_is_region_relative_mathpix_pixels(self):
        f = ff.frame_of(TF_3_PageFrame.MEDIA, TF_3_PageFrame.CROP,
                        3306, 4678, 1426, 2152)
        reg = TF_3_PageFrame.REGION
        px, frac, y_from = fm.to_region(dict(region=reg, frame=f,
                                             rect=[160, 8, 480, 66]))
        self.assertEqual(y_from, "ink")
        for got, want in zip(px, [100, 5, 300, 41.25]):   # crop px / 1.6
            self.assertAlmostEqual(got, want, delta=1.0)
        self.assertAlmostEqual(frac[2], 300 / 807, delta=0.002)

    def test_no_ink_in_the_rectangle_spans_the_line_and_says_so(self):
        f = ff.frame_of([0, 0, 612, 792], [0, 0, 612, 792], 3400, 4400,
                        2125, 2750)
        reg = dict(top_left_x=100, top_left_y=200, width=900, height=40)
        px, _, y_from = fm.to_region(dict(region=reg, frame=f,
                                          rect=[16, None, 32, None]))
        self.assertEqual(y_from, "line")
        self.assertAlmostEqual(px[1], 0, delta=1)
        self.assertAlmostEqual(px[3], 40, delta=1)

    def test_staleness_follows_the_rows_not_the_file_bytes(self):
        """pdfdrill republishes evidence-formula.tex to insert the marks.
        A guard on its bytes would refuse every mark set it produced."""
        with tempfile.TemporaryDirectory() as td:
            doc = pathlib.Path(td) / "X"
            doc.mkdir()
            (doc / "X.lines.json").write_text('{"pages": []}')
            tex = doc / "evidence-formula.tex"
            tex.write_text(FIXTURE)
            before = fm._inputs(doc, "X")
            tex.write_text(FIXTURE.replace("{0.996}", "{0.500}")
                           .replace("A_FO0003.jpg", "A_FO0003-new.jpg"))
            self.assertEqual(fm._inputs(doc, "X"), before)
            tex.write_text(FIXTURE.replace("w_{3}", "w_{4}"))
            self.assertNotEqual(fm._inputs(doc, "X"), before)

    @staticmethod
    def _rows():
        base = dict(conf=1.0, crop_h=74, blobs_in_rect=5, formula_blobs=5,
                    score=0.95, rect=[0, 0, 10, 10], crop=None)
        good = [dict(base, id=f"g{i}", gaps=9, margin=0.30, edge_cuts=0)
                for i in range(8)]
        return good + [
            dict(base, id="tall", gaps=9, margin=0.30, edge_cuts=0, crop_h=400),
            dict(base, id="short", gaps=1, margin=0.30, edge_cuts=0),
            dict(base, id="notunique", gaps=9, margin=0.12, edge_cuts=0),
            dict(base, id="cut", gaps=5, margin=0.30, edge_cuts=1),
            dict(base, id="longcut", gaps=8, margin=0.30, edge_cuts=1)]

    def test_every_suppression_clause_fires_and_agrees_with_classify(self):
        rows = self._rows()
        cal, _ = fr.calibrate(rows, fm.MIN_MARGIN)
        fr.classify(rows, cal, fm.MIN_MARGIN)
        by = {r["id"]: r for r in rows}
        for r in rows:
            self.assertEqual(fm.why_no_mark(r) is None, r["mark"], r["id"])
        want = {"tall": "host region is not a line",
                "short": "too short", "notunique": "position not unique",
                "cut": "short expression cut"}
        for rid, reason in want.items():
            self.assertFalse(by[rid]["mark"], rid)
            self.assertTrue(fm.why_no_mark(by[rid]).startswith(reason), rid)
        # the positive side of each clause
        self.assertTrue(by["g0"]["mark"])
        self.assertTrue(by["longcut"]["mark"])     # gaps > MARK_GAPS

    def test_lines_group_by_host_region_and_none_is_not_a_line(self):
        reg = dict(top_left_x=1, top_left_y=2, width=3, height=4)
        rows = self._rows()
        rows[0].update(host_page=5, region=dict(reg), rect=[0, 0, 50, 10])
        rows[1].update(host_page=5, region=dict(reg), rect=[40, 0, 90, 10])
        cal, _ = fr.calibrate(rows, fm.MIN_MARGIN)
        fr.classify(rows, cal, fm.MIN_MARGIN)
        self.assertIn("OVERLAP", rows[0]["flags"])
        self.assertIn("OVERLAP", rows[1]["flags"])
        # rows with neither a region nor a crop are not one shared line
        self.assertFalse([r for r in rows[2:] if "OVERLAP" in r["flags"]])


if __name__ == "__main__":
    unittest.main()
