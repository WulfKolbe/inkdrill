"""T23: the regression oracle. Two real pages, four captured outputs.

The four JSONs under `tests/fixtures/` are the CLI's output on an
arXiv page (1408.0838 p8) and a Heim scan page (bh2 p96), with and
without `--glyphs`, captured 2026-08-18. Every later task must leave
them byte-identical; a change is either a found regression or a
deliberate contract change, and a deliberate change is made by
RE-CAPTURING the fixture in the same commit that changes the code,
never by loosening this test.

`ocr.version` is the git HEAD by design (version.py G2), so verbatim
byte-identity across commits is achieved by pinning the resolver's
cache to the version RECORDED in the fixture before regenerating --
one field, the one whose change is the point, and the pin lives in
the test rather than in any production path.

The Heim base capture has 0 lines: the scan has no drawn tables,
rules or detected blocks, and an honest oracle records that rather
than swapping pages until something appears.
"""

import json
import pathlib
import tempfile
import unittest

FIX = pathlib.Path(__file__).parent / "fixtures"

CASES = [
    ("arxiv_1408_0838_p8.png", "arxiv_1408_0838_p8.lines.json", []),
    ("arxiv_1408_0838_p8.png", "arxiv_1408_0838_p8.glyphs.lines.json",
     ["--glyphs"]),
    ("heim_bh2_p96.png", "heim_bh2_p96.lines.json", []),
    ("heim_bh2_p96.png", "heim_bh2_p96.glyphs.lines.json", ["--glyphs"]),
]


class T23_1_RegressionOracle(unittest.TestCase):

    def tearDown(self):
        from inkdrill import version
        version._cached = None

    def test_all_four_captures_are_reproduced_byte_identically(self):
        from inkdrill import version
        from inkdrill.__main__ import main
        for png, fixture, flags in CASES:
            with self.subTest(fixture=fixture):
                want = (FIX / fixture).read_bytes()
                version._cached = json.loads(want)["ocr"]["version"]
                out = pathlib.Path(tempfile.mkdtemp()) / "out.json"
                rc = main([str(FIX / png), "-o", str(out)] + flags)
                self.assertEqual(rc, 0)
                self.assertEqual(out.read_bytes(), want, fixture)

    def test_the_version_pin_pins_the_field_it_claims_to(self):
        """The oracle normalises exactly ONE field. Assert the pin is
        load-bearing: an unpinned run in this checkout produces the
        HEAD version, and the fixture's version is a fixed string --
        so if the two happen to be equal the pin is untested and this
        test says so instead of passing silently."""
        from inkdrill import version
        version._cached = None
        head = version.resolve()
        recorded = json.loads(
            (FIX / "arxiv_1408_0838_p8.lines.json").read_bytes()
        )["ocr"]["version"]
        if head == recorded:
            self.skipTest("HEAD is the capture commit; pin untestable")
        self.assertNotEqual(head, recorded)


if __name__ == "__main__":
    unittest.main()
