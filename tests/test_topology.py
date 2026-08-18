"""T24/T25: the `topology` subcommand and its synthetic anchors.

The ring and the blob pin chi at both values the formula can take for
one component, and the HOLE cross-check is two computations sharing no
code: the sweep's cycle rank (what `topology` emits) against `nest`'s
background-region count. The CLI test runs the real entry point on a
built PNG, not the helper.
"""

import io
import json
import pathlib
import tempfile
import unittest
from contextlib import redirect_stdout

from inkdrill.raster import InkMask


def _ring(W=30, H=30, r0=6, r1=12):
    buf = bytearray(W * H)
    cx, cy = W / 2, H / 2
    for y in range(H):
        for x in range(W):
            d2 = (x + .5 - cx) ** 2 + (y + .5 - cy) ** 2
            if r0 * r0 <= d2 <= r1 * r1:
                buf[y * W + x] = 0xFF
    return InkMask(bytes(buf), W, H)


def _blob(W=20, H=16):
    buf = bytearray(W * H)
    for y in range(3, 13):
        for x in range(4, 16):
            buf[y * W + x] = 0xFF
    return InkMask(bytes(buf), W, H)


class T24_1_ComponentTopology(unittest.TestCase):

    def test_ring_chi_0_one_hole_blob_chi_1_none(self):
        from inkdrill.emit import component_topology
        ring, = component_topology(_ring())
        blob, = component_topology(_blob())
        self.assertEqual((ring["holes"], ring["chi"]), (1, 0))
        self.assertEqual((blob["holes"], blob["chi"]), (0, 1))

    def test_the_two_hole_routes_agree(self):
        """Sweep cycle rank against nest's background count -- no
        shared code. On the ring both must say 1; on the blob 0; and
        on a two-hole figure (8-shape) both must say 2, so agreement
        is not an artifact of small numbers."""
        from inkdrill.emit import component_topology
        from inkdrill.nest import nest
        W = 26
        eight = bytearray(W * 46)
        for cy in (12, 33):
            for y in range(46):
                for x in range(W):
                    d2 = (x + .5 - 13) ** 2 + (y + .5 - cy) ** 2
                    if 25 <= d2 <= 100:
                        eight[y * W + x] = 0xFF
        for name, mask, want in (("ring", _ring(), 1),
                                 ("blob", _blob(), 0),
                                 ("eight", InkMask(bytes(eight), W, 46), 2)):
            with self.subTest(name=name):
                comps = component_topology(mask)
                sweep_holes = sum(c["holes"] for c in comps)
                n = nest(mask)
                nest_holes = sum(
                    len(n.holes_of(r.id)) for r in n.regions.values()
                    if r.kind.value == "ink")
                self.assertEqual(sweep_holes, want)
                self.assertEqual(nest_holes, want)

    def test_termini_and_reeb_carry_the_ring_shape(self):
        """A ring has no stroke ends at all -- every terminus count is
        the two extremes of the closed contour -- and its Reeb cycles
        entry must be 1. Asserted so the crop painting cannot rot into
        bbox cropping: a neighbour painted into the crop would change
        these."""
        from inkdrill.emit import component_topology
        ring, = component_topology(_ring())
        self.assertEqual(ring["termini"], [1, 1, 1, 1])
        self.assertEqual(ring["reeb"][1], 1)      # cycles

    def test_a_neighbour_inside_the_bbox_does_not_leak(self):
        """A dot INSIDE the ring's hole shares the ring's bbox. The
        ring's record must be unchanged by its presence, and the dot
        is its own component."""
        from inkdrill.emit import component_topology
        m = _ring()
        buf = bytearray(m.data)
        buf[15 * 30 + 15] = 0xFF          # dot in the hole's centre
        both = component_topology(InkMask(bytes(buf), 30, 30))
        self.assertEqual(len(both), 2)
        ring = max(both, key=lambda c: c["area"])
        self.assertEqual((ring["holes"], ring["termini"]),
                         (1, [1, 1, 1, 1]))


class T24_3_AxisDistinction(unittest.TestCase):

    def test_a_U_separates_the_row_pair_from_the_col_pair(self):
        """Every other fixture here is symmetric, so swapping the col
        sweep for a second row sweep survived the first mutation
        round. A U has (top, bottom) = (2, 1) and (left, right) =
        (1, 1): the 4-tuple carries the axis or this fails."""
        from inkdrill.emit import component_topology
        W, H = 20, 16
        buf = bytearray(W * H)
        for y in range(2, 14):
            for x in range(3, 6):
                buf[y * W + x] = 0xFF
            for x in range(14, 17):
                buf[y * W + x] = 0xFF
        for y in range(11, 14):
            for x in range(3, 17):
                buf[y * W + x] = 0xFF
        u, = component_topology(InkMask(bytes(buf), W, H))
        self.assertEqual(u["termini"], [2, 1, 1, 1])


class T24_2_TopologyCLI(unittest.TestCase):

    def test_the_subcommand_end_to_end(self):
        import sys
        sys.path.insert(0, str(pathlib.Path(__file__).parent))
        from test_pngio import build_png
        from inkdrill.__main__ import main
        g = [[(255, 255, 255)] * 40 for _ in range(30)]
        for y in range(8, 22):
            for x in range(8, 30):
                if not (12 <= y <= 18 and 14 <= x <= 24):
                    g[y][x] = (0, 0, 0)
        tmp = pathlib.Path(tempfile.mkdtemp())
        (tmp / "p.png").write_bytes(build_png(g))
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["topology", str(tmp / "p.png")])
        self.assertEqual(rc, 0)
        doc = json.loads(buf.getvalue())
        self.assertEqual(len(doc["components"]), 1)
        c = doc["components"][0]
        self.assertEqual((c["holes"], c["chi"]), (1, 0))
        self.assertEqual(c["bbox"], [8, 8, 29, 21])
        self.assertEqual(c["area"], 22 * 14 - 11 * 7)


if __name__ == "__main__":
    unittest.main()


class T26_1_GlyphTopology(unittest.TestCase):
    """`ink.topology` on the --glyphs route: {holes, chi, reeb,
    termini} per CLUSTER, member-filtered so foreign ink inside the
    crop bbox stays out. The default route must not carry the key --
    that is what keeps the T23 non-glyph oracle byte-identical."""

    @staticmethod
    def _run(flags):
        import sys
        sys.path.insert(0, str(pathlib.Path(__file__).parent))
        from test_pngio import build_png
        from inkdrill.__main__ import main
        g = [[(255, 255, 255)] * 60 for _ in range(40)]
        for y in range(8, 28):
            for x in range(10, 30):
                if not (13 <= y <= 23 and 15 <= x <= 25):
                    g[y][x] = (0, 0, 0)               # ring
        g[18][20] = (0, 0, 0)                          # dot in its hole
        for y in range(10, 26):
            for x in range(38, 50):
                g[y][x] = (0, 0, 0)                    # blob
        tmp = pathlib.Path(tempfile.mkdtemp())
        (tmp / "p.png").write_bytes(build_png(g))
        out = tmp / "o.json"
        rc = main([str(tmp / "p.png"), "--dpi", "96",
                   "-o", str(out)] + flags)
        assert rc == 0
        d = json.loads(out.read_text())
        pg = d["pages"][0] if "pages" in d else d
        return pg["lines"]

    def test_glyphs_route_carries_member_filtered_topology(self):
        lines = self._run(["--glyphs"])
        topos = {l["ink"]["area"]: l["ink"]["topology"]
                 for l in lines if l.get("type") == "glyph"}
        ring = topos[max(topos)]
        self.assertEqual((ring["holes"], ring["chi"]), (1, 0))
        # the dot shares the ring's crop; member filtering keeps it out
        self.assertEqual(ring["termini"], [1, 1, 1, 1])
        blob = topos[16 * 12]
        self.assertEqual((blob["holes"], blob["chi"]), (0, 1))
        # the two hole routes agree inside every emitted line
        for l in lines:
            if l.get("type") == "glyph":
                self.assertEqual(l["ink"]["holes"],
                                 l["ink"]["topology"]["holes"])

    def test_default_route_carries_no_topology_key(self):
        for l in self._run([]):
            self.assertNotIn("topology", l.get("ink", {}))
