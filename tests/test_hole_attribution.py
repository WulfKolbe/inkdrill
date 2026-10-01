"""G3 per component: sweep's cycle_count against an independent flood fill.

Components are matched by their first pixel in raster order (y, then x),
so a hole credited to the wrong component fails even when totals agree.
"""
import random
import unittest

from inkdrill.raster import InkMask
from inkdrill.sweep import sweep

from tests._hole_attribution import holes_per_component

HAND = {  # name: (rows, {first_pixel: holes}) -- by hand
    "empty": (["...", "..."], {}),
    "ring": (["###", "#.#", "###"], {(0, 0): 1}),
    "diamond": ([".#.", "#.#", ".#."], {(0, 1): 1}),
    "island_in_hole": (["#####", "#...#", "#.#.#", "#...#", "#####"],
                       {(0, 0): 1, (2, 2): 0}),
    "ring_in_ring": (["#######", "#.....#", "#.###.#", "#.#.#.#", "#.###.#",
                      "#.....#", "#######"], {(0, 0): 1, (2, 2): 1}),
    "two_owners": (["###.###", "#.#.#.#", "###.###"], {(0, 0): 1, (0, 4): 1}),
    "figure_8": (["###", "#.#", "###", "#.#", "###"], {(0, 0): 2}),
    "open_to_border": (["###", "#..", "###"], {(0, 0): 0}),
    "hole_left_of_owner_start": ([".###", "#..#", ".###"], {(0, 1): 1}),
}


def sweep_holes(rows, axis):
    res = sweep(InkMask.from_rows(rows), axis=axis, conn=8)
    out = {}
    for c in res.components:
        firsts = []
        for nid in c.nodes:
            n = res.nodes[nid]
            x0, y0, _, _ = n.as_run().image_span(axis)
            firsts.append((y0, x0))
        out[min(firsts)] = c.cycle_count
    return out


def noise(seed, n, density):
    rng = random.Random(seed)
    return ["".join("#" if rng.random() < density else "." for _ in range(n))
            for _ in range(n)]


def checker(n, phase):
    return ["".join("#" if (x + y + phase) % 2 == 0 else "." for x in range(n))
            for y in range(n)]


class OracleSelfCheck(unittest.TestCase):
    def test_hand(self):
        for name, (rows, want) in HAND.items():
            with self.subTest(name=name):
                self.assertEqual(holes_per_component(rows), want)


class SweepPerComponent(unittest.TestCase):
    def check(self, rows):
        want = holes_per_component(rows)
        for axis in ("row", "col"):
            with self.subTest(axis=axis):
                self.assertEqual(sweep_holes(rows, axis), want)

    def test_hand(self):
        for name, (rows, _) in HAND.items():
            with self.subTest(name=name):
                self.check(rows)

    def test_checkerboards(self):
        for n, phase in ((16, 0), (17, 1)):
            with self.subTest(n=n, phase=phase):
                self.check(checker(n, phase))

    def test_seeded_noise(self):
        for seed in range(5):
            for d in range(1, 10):
                with self.subTest(seed=seed, density=d / 10):
                    self.check(noise(seed, 40, d / 10))


if __name__ == "__main__":
    unittest.main()
