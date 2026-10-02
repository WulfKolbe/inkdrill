"""`formulamarks.py verify` -- the delivery check.

Every condition it tests for is one that actually happened on
2026-10-02, and every one was invisible to the obvious test. Dates said
the set was complete: 20 of 21 evidence PDFs had been built WITHOUT the
marks, one document had never been delivered at all, and the index
carried counts from an emission three weeks earlier.

So each class below has a fixture that reaches it. A check whose
failure branch no test enters is a check that first runs on real data.
"""
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest


def _tool():
    p = (pathlib.Path(__file__).resolve().parent.parent
         / "tools" / "formulamarks.py")
    spec = importlib.util.spec_from_file_location("_fm", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_fm"] = mod
    spec.loader.exec_module(mod)
    return mod


FM = _tool()
MARKED = FM.MARKED_CROPS


def marks_doc(marked=3, inkdrill="aaaaaaaaaaaa", extra=None):
    d = {"bibkey": "doc", "inkdrill": inkdrill,
         # a MAPPING of input -> sha256, as the artifact has it. This
         # said "pdfdrill-1234" and crashed the first check that read it:
         # the second fixture-shape defect in this file today.
         "measured_against": {"evidence rows (id, math)": "abc123"},
         "counts": {"marked": marked, "evidence_rows": 10},
         # "rows", as the real artifact spells it. This fixture said
         # "marks" and nothing noticed until a check read the array:
         # a fixture whose shape came from nowhere.
         "rows": [{"id": f"doc_FO{i:04d}", "mark": i < marked}
                  for i in range(10)]}
    if extra:
        d.update(extra)
    return d


class TM_1_Verify(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        self.marks = root / "marks"
        self.lib = root / "library"
        self.addCleanup(self.tmp.cleanup)

    def build(self, name="doc", *, local=None, delivered="same",
              crops_dir=MARKED, n_refs=3, n_crops=3, flat=False, tex=True):
        """One document on disk. `delivered=None` omits the library copy."""
        local = marks_doc() if local is None else local
        (self.marks / name).mkdir(parents=True)
        (self.marks / name / "marks.json").write_text(json.dumps(local))
        doc = self.lib / name
        doc.mkdir(parents=True)
        if delivered is not None:
            payload = local if delivered == "same" else delivered
            (doc / "marks.json").write_text(json.dumps(payload))
        if tex:
            body = "".join(f"\\includegraphics{{{crops_dir}/{name}_FO{i:04d}.jpg}}\n"
                           for i in range(n_refs))
            if flat:
                (doc / "evidence-formula.tex").write_text(body)
            else:
                (doc / "evidence-formula").mkdir()
                (doc / "evidence-formula" / "evidence-formula.tex").write_text(body)
        cd = doc / MARKED
        cd.mkdir()
        for i in range(n_crops):
            (cd / f"{name}_FO{i:04d}.jpg").write_bytes(b"\xff\xd8")
        return doc

    def row(self, name="doc", index=None):
        return FM.verify_document(name, self.marks, self.lib, index)

    # ---- the clean case, so the checks can be shown to be falsifiable
    def test_a_delivered_and_marked_document_passes(self):
        self.build()
        r = self.row()
        self.assertEqual(r["fail"], [])
        self.assertEqual(r["warn"], [])
        self.assertEqual(r["embedded"], 3)

    def test_the_flat_layout_passes_too(self):
        """Both layouts are in the library. Assuming the subdirectory
        reported four documents as missing evidence that was there."""
        self.build(flat=True)
        self.assertEqual(self.row()["fail"], [])

    # ---- each failure class
    def test_not_delivered(self):
        self.build(delivered=None)
        self.assertIn("not delivered to the library", self.row()["fail"])

    def test_delivered_content_differs(self):
        self.build(delivered=marks_doc(marked=2))
        self.assertTrue(any("differs in content" in f
                            for f in self.row()["fail"]))

    def test_provenance_only_difference_is_a_WARNING_not_a_failure(self):
        """Three documents differed only in the emitting commit. Failing
        those sends someone re-delivering to change one hex string."""
        self.build(delivered=marks_doc(inkdrill="bbbbbbbbbbbb"))
        r = self.row()
        self.assertEqual(r["fail"], [])
        self.assertTrue(any("different inkdrill build" in w for w in r["warn"]))

    def test_evidence_built_without_the_marks(self):
        """The one that caught 20 of 21: the build succeeded, is newer
        than the marks, and references the UNMARKED crops."""
        self.build(crops_dir="report-crops-b")
        r = self.row()
        self.assertTrue(any("built WITHOUT the marks" in f for f in r["fail"]))
        self.assertIn("report-crops-b", r["fail"][0])
        self.assertEqual(r["embedded"], 0)

    def test_no_evidence_at_all(self):
        self.build(tex=False)
        self.assertIn("no evidence-formula.tex", self.row()["fail"])

    def test_no_local_marks(self):
        (self.marks / "doc").mkdir(parents=True)
        (self.lib / "doc").mkdir(parents=True)
        self.assertIn("no local marks.json", self.row()["fail"])

    def test_when_both_layouts_exist_the_NEWER_is_read(self):
        """pdfdrill promoted 17 of 21 documents' evidence into a nested
        folder and today's build writes flat, so a rebuild leaves a stale
        nested copy beside the fresh one. A fixed preference reports a
        correct rebuild as 'built without marks'."""
        import os, time
        doc = self.build(crops_dir="report-crops-b")          # nested, stale
        flat = doc / "evidence-formula.tex"
        flat.write_text("\\includegraphics{%s/doc_FO0000.jpg}\n" % MARKED)
        nested = doc / "evidence-formula" / "evidence-formula.tex"
        old = time.time() - 3600
        os.utime(nested, (old, old))
        r = self.row()
        self.assertEqual(r["fail"], [])                       # the flat one wins
        self.assertEqual(r["embedded"], 1)
        self.assertTrue(any("two evidence trees" in w for w in r["warn"]))

    def test_a_single_layout_warns_about_nothing(self):
        self.build()
        self.assertFalse(any("two evidence trees" in w
                             for w in self.row()["warn"]))

    def test_a_SPLIT_evidence_set_sums_its_parts(self):
        """Cardona is 22.3 MB against a 20 MB publishing ceiling and is
        already floored at scale 0.60/q72, so the user's answer was to
        split it. Anything reading the evidence by one exact name goes
        blind the moment that happens and reports a complete document as
        having no evidence."""
        doc = self.build(n_refs=2)                       # part 1: 2 marks
        (doc / "evidence-formula-2.tex").write_text(
            "".join(f"\\includegraphics{{{MARKED}/doc_FO{i:04d}.jpg}}\n"
                    for i in (2, 3, 4)))                 # part 2: 3 marks
        r = self.row()
        self.assertEqual(r["parts"], 2)
        self.assertEqual(r["embedded"], 5)
        self.assertEqual(r["fail"], [])

    def test_a_part_with_no_marks_is_not_a_failure(self):
        """A part covering a stretch of unmarked rows legitimately
        carries none; requiring marks in every part would fail a correct
        split."""
        doc = self.build(n_refs=3)
        (doc / "evidence-formula-2.tex").write_text(
            "\\includegraphics{report-crops/doc_FO0009.jpg}\n")
        r = self.row()
        self.assertEqual(r["parts"], 2)
        self.assertEqual(r["embedded"], 3)
        self.assertEqual(r["fail"], [])

    def test_a_split_where_NO_part_carries_marks_still_fails(self):
        doc = self.build(crops_dir="report-crops-b", n_refs=2)
        (doc / "evidence-formula-2.tex").write_text(
            "\\includegraphics{report-crops-b/doc_FO0009.jpg}\n")
        r = self.row()
        self.assertEqual(r["parts"], 2)
        self.assertTrue(any("built WITHOUT the marks" in f for f in r["fail"]))

    def test_every_evidence_row_must_be_accounted_for(self):
        """`rows` + `not_measured` == `evidence_rows`, exactly. The
        identity that distinguishes a row the instrument DECLINED from
        one that silently went missing -- both sessions misread 116 of
        the first as the second."""
        bad = marks_doc()
        bad["counts"]["evidence_rows"] = 12      # 10 rows, 0 not measured
        self.build(local=bad)
        self.assertTrue(any("does not account for every evidence row" in f
                            for f in self.row()["fail"]))

    def test_not_measured_closes_the_gap(self):
        """The same document is CORRECT once the declined rows are
        counted: 10 measured + 2 not placed = 12."""
        good = marks_doc()
        good["counts"]["evidence_rows"] = 12
        good["counts"]["not_measured"] = {"not placed (too short)": 2}
        self.build(local=good)
        r = self.row()
        self.assertEqual(r["fail"], [])
        self.assertEqual(r["not_placed"], 2)

    def test_a_reading_rewritten_after_measurement_fails(self):
        """`measured_against` names the inputs by hash. A reading
        rewritten afterwards leaves the mark set looking perfect while
        every rect points into a page the reader no longer describes."""
        import hashlib
        doc = self.build()
        reading = doc / "doc.lines.json"
        reading.write_text('{"pages": []}')
        m = marks_doc()
        m["measured_against"] = {"doc.lines.json":
                                 hashlib.sha256(reading.read_bytes()).hexdigest()}
        (self.marks / "doc" / "marks.json").write_text(json.dumps(m))
        (doc / "marks.json").write_text(json.dumps(m))
        self.assertEqual(self.row()["fail"], [])          # unchanged: passes
        reading.write_text('{"pages": [1]}')              # rewritten
        self.assertTrue(any("has changed since this mark set was measured" in f
                            for f in self.row()["fail"]))

    def test_a_non_file_key_in_measured_against_is_skipped(self):
        """`evidence rows (id, math)` is a digest of content, not a file
        beside the document; hashing it as a path would fail every set."""
        doc = self.build()
        m = marks_doc()
        m["measured_against"] = {"evidence rows (id, math)": "deadbeef"}
        (self.marks / "doc" / "marks.json").write_text(json.dumps(m))
        (doc / "marks.json").write_text(json.dumps(m))
        self.assertEqual(self.row()["fail"], [])

    # ---- the warnings
    def test_crops_on_disk_say_rebuild_not_remeasure(self):
        self.build(crops_dir="report-crops-b", n_crops=7)
        self.assertTrue(any("rebuild, not a re-measure" in w
                            for w in self.row()["warn"]))

    def test_drawn_count_against_the_file(self):
        self.build(n_refs=2)           # file says 3 marked, evidence draws 2
        self.assertTrue(any("draws 2 marks" in w for w in self.row()["warn"]))

    def test_index_disagreeing_with_the_file(self):
        """15 of 21 did, by up to 94 marks, because the index predated
        the eye verdicts."""
        self.build()
        r = self.row(index={"doc": {"marked": 99}})
        self.assertTrue(any("index says 99" in w for w in r["warn"]))

    # ---- the set, and the exit code
    def test_a_set_is_not_delivered_when_one_document_is_not(self):
        self.build("good")
        self.build("bad", delivered=None)
        rows = FM.verify(self.marks, self.lib)
        self.assertEqual(len(rows), 2)
        self.assertEqual(FM.verify_cmd(self.marks, self.lib), 1)

    def test_a_clean_set_exits_zero(self):
        self.build("good")
        self.build("also-good")
        self.assertEqual(FM.verify_cmd(self.marks, self.lib), 0)


if __name__ == "__main__":
    unittest.main()
