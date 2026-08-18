"""T29/T30: `locate` and its page-sweep cache.

The cache tests assert BOTH directions: a (corrupted) cache is
actually read -- the result moves with it -- and a changed page
invalidates it -- the result moves back. Either assertion alone
would pass with the cache disabled or with staleness unchecked.
"""

import io
import json
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, str(pathlib.Path(__file__).parent))


def _blob(g, x, y, w=12, h=14):
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            g[yy][xx] = (0, 0, 0)


def _ring(g, x, y, w=14, h=14):
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            if not (y + 4 <= yy < y + h - 4 and x + 4 <= xx < x + w - 4):
                g[yy][xx] = (0, 0, 0)


def _page_bytes():
    from test_pngio import build_png
    g = [[(255, 255, 255)] * 300 for _ in range(120)]
    for i in range(4):
        _blob(g, 20 + i * 40, 20)          # row 1: four blobs
    _blob(g, 20, 70)                        # row 2: blob ring blob
    _ring(g, 60, 70)
    _blob(g, 100, 70)
    return build_png(g)


def _cand_bytes(ring=True):
    from test_pngio import build_png
    c = [[(255, 255, 255)] * 70 for _ in range(30)]
    (_ring if ring else _blob)(c, 5, 8)
    _blob(c, 40, 8)
    return build_png(c)


def _locate(page, cand):
    from inkdrill.__main__ import main
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["locate", "--page", str(page),
                   "--candidate", str(cand), "--dpi", "72"])
    out = buf.getvalue().strip()
    return rc, (json.loads(out) if rc == 0 else out)


class T29_1_Locate(unittest.TestCase):

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        (self.tmp / "P.png").write_bytes(_page_bytes())

    def test_the_hole_steers_the_match_to_the_ring_row(self):
        """Two windows of two components exist in both rows; only the
        ring row carries a hole. The ring candidate must land on a
        window containing the ring; the all-blob candidate must not
        pay the hole distance."""
        (self.tmp / "C.png").write_bytes(_cand_bytes(ring=True))
        rc, doc = _locate(self.tmp / "P.png", self.tmp / "C.png")
        self.assertEqual(rc, 0)
        self.assertEqual(doc["distance"], 0)
        x0, y0, x1, y1 = doc["rect_px"]
        self.assertTrue(y0 >= 70, doc)             # the ring row
        self.assertTrue(x0 <= 60 <= x1, doc)       # contains the ring
        self.assertEqual(doc["rect_pt"], [x0 * 1.0, y0 * 1.0,
                                          (x1 + 1) * 1.0, (y1 + 1) * 1.0])

    def test_points_actually_scale_with_dpi(self):
        """At --dpi 72 the scale is 1.0 and a dropped conversion is
        invisible -- the first mutation round proved it. 144 dpi
        halves every point value."""
        from inkdrill.__main__ import main
        (self.tmp / "C.png").write_bytes(_cand_bytes(ring=True))
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["locate", "--page", str(self.tmp / "P.png"),
                       "--candidate", str(self.tmp / "C.png"),
                       "--dpi", "144"])
        self.assertEqual(rc, 0)
        doc = json.loads(buf.getvalue())
        x0, y0, x1, y1 = doc["rect_px"]
        self.assertEqual(doc["rect_pt"], [x0 / 2, y0 / 2,
                                          (x1 + 1) / 2, (y1 + 1) / 2])

    def test_no_match_is_explicit_not_best_of_bad(self):
        from test_pngio import build_png
        c = [[(255, 255, 255)] * 300 for _ in range(30)]
        for i in range(9):
            _blob(c, 5 + i * 32, 8)
        (self.tmp / "C9.png").write_bytes(build_png(c))
        rc, out = _locate(self.tmp / "P.png", self.tmp / "C9.png")
        self.assertEqual(rc, 1)
        self.assertIn("NO MATCH", out)

    def test_the_cache_is_read_and_staleness_invalidates_it(self):
        (self.tmp / "C.png").write_bytes(_cand_bytes(ring=True))
        page = self.tmp / "P.png"
        _locate(page, self.tmp / "C.png")
        side = self.tmp / "P.png.inkcache.json"
        self.assertTrue(side.exists())
        # corrupt the cache: strip every hole; mtime/size still valid
        store = json.loads(side.read_text())
        key = next(iter(store))
        for c in store[key]["components"]:
            c[6] = 0
        side.write_text(json.dumps(store))
        rc, doc = _locate(page, self.tmp / "C.png")
        self.assertEqual(rc, 0)
        self.assertGreater(doc["distance"], 0)     # the lie was used
        # touch the page: mtime changes, cache must be recomputed
        page.write_bytes(_page_bytes())
        rc, doc = _locate(page, self.tmp / "C.png")
        self.assertEqual(doc["distance"], 0)       # truth is back


if __name__ == "__main__":
    unittest.main()
