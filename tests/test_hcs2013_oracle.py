"""sweep against an independent algorithm (He/Chao/Suzuki 2013).

Checks totals only: component count and the SUM of cycle_count per mask.
Per-component hole attribution is NOT covered here (the paper gives totals).
"""
import random
import unittest

from inkdrill.raster import InkMask
from inkdrill.sweep import sweep

from tests._hcs2013 import count

HAND = {  # name: (rows, (ncc, nh)) -- answers computed by hand
    "empty": (["...", "...", "..."], (0, 0)),
    "dot": (["#"], (1, 0)),
    "ring": (["###", "#.#", "###"], (1, 1)),
    "diamond": ([".#.", "#.#", ".#."], (1, 1)),      # 8-conn ink, 4-conn hole
    "diag": (["#.", ".#"], (1, 0)),
    "two_holes": (["#####", "#.#.#", "#####"], (1, 2)),
    "two_rings": (["###.###", "#.#.#.#", "###.###"], (2, 2)),
    "open_to_border": (["###", "#..", "###"], (1, 0)),
    "full_height_bar": (["..#..", "..#..", "..#.."], (1, 0)),
    "corner_ink": (["#....", "..#..", "....."], (2, 0)),
}


def checker(n, phase=0):
    return ["".join("#" if (x + y + phase) % 2 == 0 else "." for x in range(n))
            for y in range(n)]


def checker_truth(n, phase=0):
    """One 8-connected component; every non-border background pixel is a hole."""
    bg = [(x, y) for y in range(n) for x in range(n) if (x + y + phase) % 2]
    inner = [p for p in bg if 0 < p[0] < n - 1 and 0 < p[1] < n - 1]
    return 1, len(inner)


def noise(seed, n, density):
    rng = random.Random(seed)
    return ["".join("#" if rng.random() < density else "." for _ in range(n))
            for _ in range(n)]


def sweep_counts(rows):
    r = sweep(InkMask.from_rows(rows), conn=8)
    return len(r.components), sum(c.cycle_count for c in r.components)


class OracleSelfCheck(unittest.TestCase):
    def test_hand_fixtures(self):
        for name, (rows, want) in HAND.items():
            with self.subTest(name=name):
                self.assertEqual(count(rows), want)

    def test_checkerboard_needs_half_label_range(self):
        # Regression for departure D2: fails with the paper's N*M/4 bound.
        for n, phase in ((16, 0), (17, 0), (17, 1)):
            with self.subTest(n=n, phase=phase):
                self.assertEqual(count(checker(n, phase)), checker_truth(n, phase))


class SweepAgreesWithOracle(unittest.TestCase):
    def test_hand_fixtures(self):
        for name, (rows, _) in HAND.items():
            with self.subTest(name=name):
                self.assertEqual(sweep_counts(rows), count(rows))

    def test_checkerboards(self):
        for n, phase in ((16, 0), (17, 0), (17, 1)):
            with self.subTest(n=n, phase=phase):
                rows = checker(n, phase)
                self.assertEqual(sweep_counts(rows), count(rows))

    def test_seeded_noise(self):
        # The paper's stress set, scaled down: densities 0.1..0.9.
        for seed in range(3):
            for d in range(1, 10):
                with self.subTest(seed=seed, density=d / 10):
                    rows = noise(seed, 48, d / 10)
                    self.assertEqual(sweep_counts(rows), count(rows))


if __name__ == "__main__":
    unittest.main()
