"""nest's containment forest against a pure-containment oracle.

out/680 left nest unchecked: its parent rule (the pixel above a region's
topmost-leftmost) is the same family as `_hole_attribution`'s (the pixel
left of a hole's first), so neither refutes the other.
`tests/_containment.py` decides parenthood by ENCLOSURE instead -- flood
the complement inward, take the innermost enclosing region -- and so can.
"""
import random
import unittest

from inkdrill.nest import Kind, nest
from inkdrill.raster import InkMask

from tests._containment import forest

FIXTURES = {
    # the four relations nest's docstring says must stay distinct
    "ring": ["#####", "#...#", "#####"],
    "fbox_with_text": ["#######",            # hole_of the box, and the dot
                       "#.....#",            # inside is ink_in_hole --
                       "#..#..#",            # NOT a hole of the box
                       "#.....#",
                       "#######"],
    "nested_frames": ["#########",           # depth 0 / 1 / 2 / 3
                      "#.......#",
                      "#.#####.#",
                      "#.#...#.#",
                      "#.#####.#",
                      "#.......#",
                      "#########"],
    "two_holes": ["#######", "#..#..#", "#######"],
    "two_components": ["###.###", "#.#.#.#", "###.###"],
    "open_to_border": ["###", "#..", "###"],   # background, not a hole
    "diamond": [".#.", "#.#", ".#."],          # 8-conn ink, 4-conn hole
    "diagonal_wall": ["..#", ".#.", "#.."],    # no hole: the wall is 8-conn
    "full": ["###", "###", "###"],
    "empty": ["...", "...", "..."],
    "one_px_hole": ["###", "#.#", "###"],
    "island_with_hole": ["#########",          # ink in a hole, with its own
                         "#.......#",          # hole: depth 0/1/2/3
                         "#..###..#",
                         "#..#.#..#",
                         "#..###..#",
                         "#.......#",
                         "#########"],
}


def _nest_forest(rows):
    """nest's forest in the oracle's key space: {key: parent key or None}."""
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


def noise(seed, n, density):
    rng = random.Random(seed)
    return ["".join("#" if rng.random() < density else "." for _ in range(n))
            for _ in range(n)]


class TN_1_OracleSelfCheck(unittest.TestCase):
    """The oracle's own answers, by hand, on the cases that separate the
    four relations."""

    def test_a_hole_belongs_to_the_ring_around_it(self):
        f = forest(FIXTURES["ring"])
        hole = [k for k in f if k[0] == "hole"]
        self.assertEqual(len(hole), 1)
        self.assertEqual(f[hole[0]][0], "ink")

    def test_ink_inside_a_hole_is_not_a_hole_of_the_box(self):
        f = forest(FIXTURES["fbox_with_text"])
        holes = [k for k in f if k[0] == "hole"]
        inks = [k for k in f if k[0] == "ink"]
        self.assertEqual(len(holes), 1)          # the box has ONE hole
        self.assertEqual(len(inks), 2)           # box and dot
        dot = min(inks, key=lambda k: k[5])      # the dot is the small one
        self.assertEqual(f[dot], holes[0])       # its parent is the hole
        self.assertIsNone(f[max(inks, key=lambda k: k[5])])

    def test_depth_alternates_through_a_nested_island(self):
        f = forest(FIXTURES["island_with_hole"])
        depth = {}
        for k in f:
            d, cur = 0, f[k]
            while cur is not None:
                d += 1
                cur = f[cur]
            depth[k] = d
        for k, d in depth.items():
            self.assertEqual(k[0], "ink" if d % 2 == 0 else "hole", (k, d))
        self.assertEqual(max(depth.values()), 3)

    def test_a_background_region_touching_the_border_is_not_a_hole(self):
        self.assertFalse([k for k in forest(FIXTURES["open_to_border"])
                          if k[0] == "hole"])

    def test_a_diagonal_wall_encloses_nothing(self):
        self.assertFalse([k for k in forest(FIXTURES["diagonal_wall"])
                          if k[0] == "hole"])
        self.assertEqual(len([k for k in forest(FIXTURES["diamond"])
                              if k[0] == "hole"]), 1)


class TN_2_NestAgreesWithContainment(unittest.TestCase):
    def test_fixtures(self):
        for name, rows in FIXTURES.items():
            with self.subTest(name=name):
                self.assertEqual(_nest_forest(rows), forest(rows))

    def test_seeded_noise(self):
        for seed in range(4):
            for d in (0.2, 0.35, 0.5, 0.65, 0.8):
                with self.subTest(seed=seed, density=d):
                    rows = noise(seed, 40, d)
                    self.assertEqual(_nest_forest(rows), forest(rows))

    def test_checkerboard(self):
        for n in (9, 16):
            rows = ["".join("#" if (x + y) % 2 == 0 else "." for x in range(n))
                    for y in range(n)]
            with self.subTest(n=n):
                self.assertEqual(_nest_forest(rows), forest(rows))


if __name__ == "__main__":
    unittest.main()
