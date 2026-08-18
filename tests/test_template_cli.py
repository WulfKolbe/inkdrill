"""T27: the `template` subcommand. OPT-IN like every font test --
skips unless INKDRILL_TYPE1 (default TeX tree) holds the fonts."""

import io
import json
import os
import pathlib
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

_TREE = pathlib.Path(os.environ.get("INKDRILL_TYPE1",
                                    "/usr/share/texmf-dist/fonts/type1"))


def _pfb(name):
    return next(_TREE.rglob(name + ".pfb"), None) if _TREE.is_dir() else None


@unittest.skipUnless(_TREE.is_dir(), "set INKDRILL_TYPE1")
class T27_1_TemplateCLI(unittest.TestCase):

    def test_o_has_one_hole_and_the_pgm_round_trips(self):
        font = _pfb("cmr10")
        if font is None:
            self.skipTest("cmr10 not under INKDRILL_TYPE1")
        from inkdrill.__main__ import main
        from inkdrill.pnmio import load_mask
        out = pathlib.Path(tempfile.mkdtemp()) / "o.pgm"
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(io.StringIO()):
            rc = main(["template", "--font", str(font), "--glyph", "o",
                       "-o", str(out)])
        self.assertEqual(rc, 0)
        doc = json.loads(buf.getvalue())
        self.assertEqual(len(doc["components"]), 1)
        c = doc["components"][0]
        self.assertEqual((c["holes"], c["chi"]), (1, 0))
        # ink BLACK in the PGM: pnmio's default polarity reads it back
        m = load_mask(out, dpi=(72.0, 72.0))
        self.assertEqual((m.width, m.height),
                         (doc["width"], doc["height"]))
        self.assertEqual(m.ink_count, c["area"])
