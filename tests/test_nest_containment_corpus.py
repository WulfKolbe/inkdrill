"""nest's forest against the containment oracle, on REAL page ink.

Opt-in, like the other corpus modules: set `INKDRILL_CORPUS` to a
directory of rendered pages (`<doc>/inspect/pages/p<N>.png`).

Why framed windows. On this corpus, depth >= 2 -- ink INSIDE a hole, the
case nest's four relations exist to separate -- occurs only inside
page-wide frames and ruled grids, 1,779 and 1,822 px on the two pages
measured, and a pixel oracle over 3 Mpx costs hundreds of MB in Python
sets. A window cut from such a frame is not enclosed: the rule crosses
the window edge and its interior stops being a hole. So one test frames
REAL GLYPH INK in a modest window: the glyphs, their counters and their
positions are the page's, the enclosing rectangle is drawn. That reaches
depth 3 (frame / its hole / glyphs / their counters) at 288 px.
"""
import os
import pathlib
import subprocess
import tempfile
import unittest

from inkdrill import pnmio
from inkdrill.nest import Kind, nest
from inkdrill.raster import InkMask

from tests._containment import forest

CORPUS = os.environ.get("INKDRILL_CORPUS")
#: (document prefix, page, window origin) -- chosen for ink density, and
#: including a SCAN (penev_A), whose ink is greyscale before binarize.
WINDOWS = [("0902.0431", 125, (1200, 1800)),
           ("penev_A", 20, (2000, 3000)),
           ("Introduction to Linear", 196, (2000, 3000))]


def _nest_forest(rows):
    n = nest(InkMask.from_rows(rows))
    keys, out = {}, {}
    for r in n.regions.values():
        if r.kind is Kind.OUTSIDE:
            continue
        keys[r.id] = ("ink" if r.kind is Kind.INK else "hole",
                      r.x0, r.y0, r.x1, r.y1, r.area)
    for rid, key in keys.items():
        parent = n.regions[rid].parent
        out[key] = keys.get(parent) if parent is not None else None
    return out


def _depths(f):
    out = {}
    for k in f:
        d, cur = 0, f[k]
        while cur is not None:
            d += 1
            cur = f[cur]
        out[k] = d
    return out


@unittest.skipUnless(CORPUS and pathlib.Path(CORPUS).is_dir(),
                     "INKDRILL_CORPUS is not a directory of rendered pages")
class TNC_1_RealInk(unittest.TestCase):
    @staticmethod
    def _window(prefix, page, origin, size):
        root = pathlib.Path(CORPUS)
        doc = next((d for d in sorted(root.iterdir())
                    if d.is_dir() and d.name.startswith(prefix)), None)
        if doc is None:
            return None
        src = doc / "inspect" / "pages" / f"p{page}.png"
        if not src.exists():
            return None
        with tempfile.TemporaryDirectory() as td:
            pgm = pathlib.Path(td) / "p.pgm"
            subprocess.run(["magick", str(src), "-colorspace", "Gray",
                            "-depth", "8", str(pgm)],
                           check=True, capture_output=True)
            m = pnmio.load_mask(str(pgm), dpi=400)
        ox, oy = origin
        if ox + size > m.width or oy + size > m.height:
            return None
        return [["#" if m.data[(oy + y) * m.width + ox + x] else "."
                 for x in range(size)] for y in range(size)]

    def test_page_windows(self):
        ran = 0
        for prefix, page, origin in WINDOWS:
            g = self._window(prefix, page, origin, 224)
            if g is None:
                continue
            ran += 1
            rows = ["".join(r) for r in g]
            with self.subTest(doc=prefix, page=page, origin=origin):
                self.assertEqual(_nest_forest(rows), forest(rows))
        if not ran:
            self.skipTest("no window of the listed pages is in this corpus")

    def test_real_ink_inside_a_drawn_frame_reaches_depth_three(self):
        """The depth >= 2 case: glyphs inside a hole, counters inside them."""
        ran = 0
        for prefix, page, origin in WINDOWS:
            n = 288
            g = self._window(prefix, page, origin, n)
            if g is None:
                continue
            ran += 1
            for i in range(n):                      # frame inside the margin
                g[2][i] = g[n - 3][i] = "#"
                g[i][2] = g[i][n - 3] = "#"
            for i in (0, 1, n - 2, n - 1):          # clear the margin itself
                for j in range(n):
                    g[i][j] = g[j][i] = "."
            rows = ["".join(r) for r in g]
            want = forest(rows)
            depth = _depths(want)
            with self.subTest(doc=prefix, page=page):
                self.assertEqual(_nest_forest(rows), want)
                self.assertGreaterEqual(max(depth.values(), default=0), 3)
                self.assertTrue([k for k, d in depth.items()
                                 if d == 2 and k[0] == "ink"])
        if not ran:
            self.skipTest("no window of the listed pages is in this corpus")


if __name__ == "__main__":
    unittest.main()
