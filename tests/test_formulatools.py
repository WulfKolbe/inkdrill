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
           # the id-cell suffixes pdfdrill writes, copied from real rows:
           # gilmore EQ0584 (eqnum + lowconf) and mielke FO0431 (refined).
           # The page match allowed only a lone \lowconf and gave 3,745
           # equation rows no page.
           + _row(r"gilmore-lie-groups\_\allowbreak{}FO0007}~\eqnum{(11.4)}"
                  r"\lowconf{0.001", 188, r"\confcell{confred}{0.001}",
                  r"{\ttfamily\footnotesize \textbackslash{}left[\allowbreak{}"
                  r"\textbackslash{}begin\{array\}\{cc\} 1 \& \textbackslash{}\_ "
                  r"\allowbreak{}\textbackslash{}\{x\textasciicircum{}\{2\}}",
                  r"\emph{(not rendered)}", _img("A_FO0007"))
           + _row(r"A\_FO0008}~{\tiny\textbf{[refined: census]}", 100,
                  r"\confcell{confamber}{0.590}",
                  r"{\ttfamily\footnotesize \textbackslash{}xi \textbackslash{}rfloor D}",
                  r"\FitMath{$\displaystyle \xi \rfloor D$}", _img("A_FO0008"))
           # the producer's placeholder INSIDE \FitMath, from johnston FO5033
           + _row(r"A\_FO0009", 483, r"\confcell{confamber}{0.741}",
                  r"{\ttfamily\footnotesize \textbackslash{}boldsymbol\{l\}}",
                  r"\FitMath{\emph{(not rendered)}}", _img("A_FO0009"))
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
                         [f"A_FO000{i}" for i in (1, 2, 3, 4, 5, 6, 8, 9)]
                         + ["gilmore-lie-groups_FO0007"])

    def test_a_placeholder_in_fitmath_is_not_a_reading(self):
        r = self.rows["A_FO0009"]
        self.assertIsNone(r["math"])
        self.assertEqual(r["placeholder"], r"\emph{(not rendered)}")
        self.assertEqual(r["source"], r"\boldsymbol{l}")
        # and real maths is untouched
        self.assertEqual(self.rows["A_FO0008"]["math"], r"\xi \rfloor D")
        self.assertIsNone(self.rows["A_FO0008"]["placeholder"])

    def test_the_page_survives_every_id_cell_suffix(self):
        r = self.rows["gilmore-lie-groups_FO0007"]
        self.assertEqual((r["page"], r["eqnum"], r["lowconf"], r["conf"]),
                         ("188", "(11.4)", True, "0.001"))
        r = self.rows["A_FO0008"]
        self.assertEqual((r["page"], r["refined"], r["eqnum"]), ("100", "census", None))
        # and a row with no suffix at all still has none
        r = self.rows["A_FO0001"]
        self.assertEqual((r["page"], r["eqnum"], r["refined"]), ("3", None, None))

    def test_the_source_cell_is_unescaped_in_one_pass(self):
        r = self.rows["gilmore-lie-groups_FO0007"]
        self.assertIsNone(r["math"])                 # not rendered
        self.assertEqual(r["source"], r"\left[\begin{array}{cc} 1 & \_ \{x^{2}")
        self.assertEqual(self.rows["A_FO0006"]["source"], r"\xrightarrow")
        self.assertEqual(self.rows["A_FO0008"]["source"], r"\xi \rfloor D")

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

    def _fake_run(self, finder_body):
        """formulamarks.run against a stand-in formulafind, on the
        fixture table. Returns (rc, the JSON it printed)."""
        import contextlib, io, sys as _sys
        with tempfile.TemporaryDirectory() as td:
            lib = pathlib.Path(td)
            (lib / "X").mkdir()
            (lib / "X" / "evidence-formula.tex").write_text(FIXTURE)
            (lib / "X" / "X.lines.json").write_text('{"pages": []}')
            finder = lib / "finder.py"
            finder.write_text(finder_body)
            old = fm.FINDER
            fm.FINDER = finder
            out, err = io.StringIO(), io.StringIO()
            try:
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    rc = fm.run(lib, "X", lib / "work", 1)
            finally:
                fm.FINDER = old
        return rc, json.loads(out.getvalue().splitlines()[0])

    def test_a_crashed_vote_is_refused_as_a_crash(self):
        rc, d = self._fake_run("import sys\nprint('Traceback')\nsys.exit(1)\n")
        self.assertEqual(rc, 2)
        self.assertIn("crashed", d["refused"])

    def test_a_vote_with_no_scale_is_refused_as_such(self):
        rc, d = self._fake_run("print('no row could establish a scale')\n")
        self.assertEqual(rc, 2)
        self.assertIn("no row could vote", d["refused"])

    def _marks_on(self, edit_tex=None, edit_lines=False):
        """formulamarks.marks over a finished run of ten real-shaped rows,
        after optionally changing the evidence or the lines."""
        import contextlib, io
        with tempfile.TemporaryDirectory() as td:
            lib = pathlib.Path(td); doc = lib / "X"; work = lib / "work"
            doc.mkdir(); work.mkdir()
            tex = _HEAD + "".join(
                _row(rf"X\_FO{i:04d}", 3, r"\confcell{confgreen}{1.000}", "s",
                     rf"\FitMath{{$\displaystyle x_{{{i}}}+y$}}", _img(f"X_FO{i:04d}"))
                for i in range(1, 11)) + r"\end{longtable}"
            (doc / "evidence-formula.tex").write_text(tex)
            (doc / "X.lines.json").write_text('{"pages": []}')
            recs = [dict(id=f"X_FO{i:04d}", page=3, host_page=3, math=f"x_{{{i}}}+y",
                         region=dict(top_left_x=100, top_left_y=60 * i, width=125, height=46),
                         frame=(1.6, 1.6, 0.0, 0.0), rect=[10, 5, 60, 40], crop_w=200,
                         crop_h=74, conf=1.0, gaps=9, margin=0.3, score=0.95,
                         edge_cuts=0, blobs_in_rect=5, formula_blobs=5, crop=None)
                    for i in range(1, 11)]
            (work / "shard0.json").write_text(json.dumps(recs))
            (work / "meta.json").write_text(json.dumps(dict(
                measured_against=fm._inputs(doc, "X"), jobs=1, scale=0.665,
                inkdrill="test")))
            if edit_tex:
                (doc / "evidence-formula.tex").write_text(edit_tex(tex))
            if edit_lines:
                (doc / "X.lines.json").write_text('{"pages": [], "x": 1}')
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                rc = fm.marks(lib, "X", work)
        return rc, json.loads(out.getvalue())

    def test_unchanged_evidence_keeps_every_mark(self):
        rc, d = self._marks_on()
        self.assertEqual((rc, d["refused"], len(d["rows"])), (0, None, 10))
        self.assertEqual(d["rows"][0]["math"], "x_{1}+y")

    def test_a_changed_reading_drops_that_row_only(self):
        """pdfdrill republishes the evidence -- one corrected row must not
        cost the other nine their marks."""
        rc, d = self._marks_on(edit_tex=lambda t: t.replace("x_{3}+y", "x_{3}+z"))
        self.assertEqual((rc, d["refused"], len(d["rows"])), (0, None, 9))
        self.assertIn("reading changed", d["not_measured"]["X_FO0003"])
        self.assertEqual(d["counts"]["reading_changed"], 1)

    def test_changed_lines_refuse_the_document(self):
        rc, d = self._marks_on(edit_lines=True)
        self.assertEqual(rc, 2)
        self.assertIn("lines.json", d["refused"])

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


class TF_5_Update(unittest.TestCase):
    """A refined row is hosted by MathPix's reading, and `update` measures
    it at the stored scale without moving any row it did not measure
    (out/670: a re-vote 0.64 -> 0.65 flipped 8 unchanged mielke marks)."""

    def test_a_refined_row_is_hosted_by_the_mathpix_reading(self):
        first = TF_2_HostLineRule.first
        A = TF_2_HostLineRule.A
        refined = dict(id="r1", page="1", math=r"G'", host_math="G")
        self.assertEqual(ff.match_rows_first([refined], first), {"r1": (1, A)})
        # without MathPix's reading the shown one is looked up, and misses
        self.assertEqual(ff.match_rows_first([dict(refined, host_math=None)], first), {})

    def test_mathpix_readings_come_from_exactly_one_tiddlers_file(self):
        with tempfile.TemporaryDirectory() as td:
            lib = pathlib.Path(td); (lib / "X").mkdir()
            t = [{"title": "X_FO0001", ff.MATHPIX_FIELD: r"\left.a\right\rfloor b",
                  "latex_refined": r"a\rfloor b"}, {"title": "X_FO0002"}]
            (lib / "X" / "x.tiddlers.json").write_text(json.dumps(t))
            self.assertEqual(ff.mathpix_readings(lib, "X"),
                             {"X_FO0001": r"\left.a\right\rfloor b"})
            (lib / "X" / "y.tiddlers.json").write_text("[]")
            self.assertEqual(ff.mathpix_readings(lib, "X"), {})

    def test_a_pinned_line_height_decides_line_like(self):
        base = dict(conf=1.0, blobs_in_rect=5, formula_blobs=5, score=0.95,
                    rect=[0, 0, 10, 10], crop=None, gaps=9, margin=0.3, edge_cuts=0)
        rows = ([dict(base, id=f"s{i}", crop_h=74) for i in range(3)]
                + [dict(base, id=f"t{i}", crop_h=300) for i in range(5)])
        cal, _ = fr.calibrate(rows, fm.MIN_MARGIN)
        fr.classify(rows, cal, fm.MIN_MARGIN)                  # median 300
        self.assertTrue(all(r["line_like"] for r in rows))
        fr.classify(rows, cal, fm.MIN_MARGIN, line_h=74)       # pinned
        self.assertFalse(any(r["line_like"] for r in rows if r["crop_h"] == 300))
        self.assertTrue(all(r["line_like"] for r in rows if r["crop_h"] == 74))

    def _finished(self, lib, tex_edit=None, finder=None):
        doc, work = lib / "X", lib / "work"
        doc.mkdir(); work.mkdir()
        tex = _HEAD + "".join(
            _row(rf"X\_FO{i:04d}", 3, r"\confcell{confgreen}{1.000}", "s",
                 rf"\FitMath{{$\displaystyle x_{{{i}}}+y$}}", _img(f"X_FO{i:04d}"))
            for i in range(1, 11)) + r"\end{longtable}"
        (doc / "evidence-formula.tex").write_text(tex)
        (doc / "X.lines.json").write_text('{"pages": []}')
        recs = [dict(id=f"X_FO{i:04d}", page=3, host_page=3, math=f"x_{{{i}}}+y",
                     region=dict(top_left_x=100, top_left_y=60 * i, width=125, height=46),
                     frame=(1.6, 1.6, 0.0, 0.0), rect=[10, 5, 60, 40], crop_w=200,
                     crop_h=74, conf=1.0, gaps=9, margin=0.3, score=0.95,
                     edge_cuts=0, blobs_in_rect=5, formula_blobs=5, crop=None)
                for i in range(1, 11)]
        (work / "shard0.json").write_text(json.dumps(recs))
        (work / "meta.json").write_text(json.dumps(dict(
            measured_against=fm._inputs(doc, "X"), jobs=1, scale=0.665,
            inkdrill="test")))
        if tex_edit:
            (doc / "evidence-formula.tex").write_text(tex_edit(tex))
        return doc, work

    def _call(self, fn, *a):
        import contextlib, io
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            rc = fn(*a)
        return rc, json.loads(out.getvalue().splitlines()[-1])

    # the stand-in finder records its argv and places each asked row at
    # x 20..70 with the evidence's CURRENT reading
    FINDER = r'''import json, sys
a = sys.argv
open(sys.argv[0] + ".argv", "w").write(json.dumps(a))
ids = a[a.index("--ids") + 1].split(",")
new = {"X_FO0003": "x_{3}+z"}
recs = [dict(id=i, page=3, host_page=3, math=new[i],
             region=dict(top_left_x=100, top_left_y=180, width=125, height=46),
             frame=[1.6, 1.6, 0.0, 0.0], rect=[20, 5, 70, 40], crop_w=200, crop_h=74,
             conf=1.0, gaps=9, margin=0.3, score=0.95, edge_cuts=0,
             blobs_in_rect=5, formula_blobs=5, crop=None) for i in ids if i in new]
for i in ids:
    if i not in new:
        print(i.split("_")[-1] + "   NO LINE MATCH")
json.dump(recs, open(a[a.index("--json") + 1], "w"))
'''

    def test_update_measures_only_the_changed_row_at_the_stored_scale(self):
        with tempfile.TemporaryDirectory() as td:
            lib = pathlib.Path(td)
            doc, work = self._finished(lib)
            _, plain = self._call(fm.marks, lib, "X", work)
        with tempfile.TemporaryDirectory() as td:
            lib = pathlib.Path(td)
            doc, work = self._finished(lib, lambda t: t.replace("x_{3}+y", "x_{3}+z"))
            finder = lib / "finder.py"; finder.write_text(self.FINDER)
            old, fm.FINDER = fm.FINDER, finder
            try:
                rc, d = self._call(fm.update, lib, "X", work)
            finally:
                fm.FINDER = old
            argv = json.loads((lib / "finder.py.argv").read_text())
            _, again = self._call(fm.marks, lib, "X", work)
        self.assertEqual((rc, d["refused"], len(d["rows"])), (0, None, 10))
        self.assertEqual(argv[argv.index("--ids") + 1], "X_FO0003")
        self.assertEqual(argv[argv.index("--scale") + 1], "0.665")
        by = {r["id"]: r for r in d["rows"]}
        self.assertEqual(by["X_FO0003"]["math"], "x_{3}+z")
        self.assertNotEqual(by["X_FO0003"]["rect"], {r["id"]: r for r in plain["rows"]}["X_FO0003"]["rect"])
        # every row the update did not measure is exactly what `marks` gave
        for r in plain["rows"]:
            if r["id"] != "X_FO0003":
                self.assertEqual(by[r["id"]], r, r["id"])
        self.assertEqual(again["rows"], d["rows"])     # a re-emit is stable
        self.assertEqual(d["updated"], dict(rows=1, attempted=1))

    def test_an_attempted_row_the_update_cannot_place_says_why(self):
        with tempfile.TemporaryDirectory() as td:
            lib = pathlib.Path(td)
            doc, work = self._finished(lib, lambda t: t.replace("x_{5}+y", "x_{5}+w"))
            finder = lib / "finder.py"; finder.write_text(self.FINDER)
            old, fm.FINDER = fm.FINDER, finder
            try:
                rc, d = self._call(fm.update, lib, "X", work)
            finally:
                fm.FINDER = old
        self.assertEqual(d["not_measured"]["X_FO0005"], "no line match")
        self.assertEqual(d["counts"]["reading_changed"], 0)
        self.assertEqual(len(d["rows"]), 9)

    def test_an_attempted_row_with_no_record_is_attempted_again(self):
        """johnston FO1528: an earlier update left no record (placeholder),
        then the reading came back. It must be measured, not reported with
        the stale reason."""
        with tempfile.TemporaryDirectory() as td:
            lib = pathlib.Path(td)
            doc, work = self._finished(lib, lambda t: t.replace("x_{3}+y", "x_{3}+z"))
            (work / "update_meta.json").write_text(json.dumps(dict(ids=["X_FO0003"])))
            (work / "update.log").write_text("FO0003   NO LINE MATCH\n")
            finder = lib / "finder.py"; finder.write_text(self.FINDER)
            old, fm.FINDER = fm.FINDER, finder
            try:
                rc, d = self._call(fm.update, lib, "X", work)
            finally:
                fm.FINDER = old
            argv = json.loads((lib / "finder.py.argv").read_text())
        self.assertEqual(argv[argv.index("--ids") + 1], "X_FO0003")
        self.assertEqual({r["id"]: r for r in d["rows"]}["X_FO0003"]["math"], "x_{3}+z")
        self.assertNotIn("X_FO0003", d["not_measured"])

    def test_a_placeholder_row_is_not_rendered_even_with_a_leftover_record(self):
        """johnston FO5033: the Rendered cell became `\\emph{(not rendered)}`
        and an update had measured those words. The row reports "not
        rendered", never "reading changed", and no other row moves."""
        with tempfile.TemporaryDirectory() as td:
            lib = pathlib.Path(td)
            doc, work = self._finished(
                lib, lambda t: t.replace(r"\FitMath{$\displaystyle x_{3}+y$}",
                                         r"\FitMath{\emph{(not rendered)}}"))
            (work / "update.json").write_text(json.dumps([dict(
                id="X_FO0003", page=3, host_page=3, math=r"\emph{(not rendered)}",
                region=dict(top_left_x=100, top_left_y=180, width=125, height=46),
                frame=[1.6, 1.6, 0.0, 0.0], rect=[20, 5, 70, 40], crop_w=200, crop_h=74,
                conf=1.0, gaps=9, margin=0.3, score=0.95, edge_cuts=0,
                blobs_in_rect=5, formula_blobs=5, crop=None)]))
            (work / "update_meta.json").write_text(json.dumps(dict(ids=["X_FO0003"])))
            rc, d = self._call(fm.marks, lib, "X", work)
        self.assertEqual(d["not_measured"]["X_FO0003"],
                         "not rendered by the producer (\\FitMath placeholder)")
        self.assertEqual(d["counts"]["reading_changed"], 0)
        self.assertEqual(sorted(r["id"] for r in d["rows"]),
                         [f"X_FO{i:04d}" for i in range(1, 11) if i != 3])


if __name__ == "__main__":
    unittest.main()
