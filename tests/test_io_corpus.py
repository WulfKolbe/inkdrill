"""Unit 0 corpus smoke test. OPT-IN.

The default suite is hermetic -- it builds its PNGs in memory and reads
nothing outside the repo. This module reads real ghostscript output and is
skipped unless INKDRILL_CORPUS names a directory.

    INKDRILL_CORPUS=~/pdfdrill-library python3 -m unittest discover -s tests -t .

Two files are enough to be useful; it uses whatever it finds. Page
selection seeks one neutral and one non-neutral page explicitly (a plain
`sorted(...)[:_MAX_PAGES]` deterministically picked four pages from a
single document, all neutral -- the colour path, the MAJORITY case per
docs/units.md, had zero real-data coverage). The rest of the quota, if
any, is filled with a seeded random sample.
"""

import os
import pathlib
import random
import unittest

from inkdrill.io import read_png
from inkdrill.raster import binarize
from inkdrill.sweep import Capture, sweep

_ROOT = os.environ.get("INKDRILL_CORPUS")
_MAX_PAGES = int(os.environ.get("INKDRILL_CORPUS_PAGES", "4"))
_SEED = 20260807
_SCAN_CAP = 200          # bound the cost of seeking one of each kind


def _pages():
    """Up to _MAX_PAGES real pages, seeking at least one neutral and one
    non-neutral page (in a random, seeded order) when the corpus has
    both, then filling any remaining quota with more random pages."""
    if not _ROOT:
        return []
    root = pathlib.Path(_ROOT).expanduser()
    if not root.is_dir():
        return []
    all_pages = sorted(root.glob("*/inspect/pages/*.png"))
    if not all_pages:
        return []

    order = all_pages[:]
    random.Random(_SEED).shuffle(order)

    neutral_page = colour_page = None
    for p in order[:_SCAN_CAP]:
        try:
            neutral = read_png(p).neutral
        except Exception:
            continue
        if neutral and neutral_page is None:
            neutral_page = p
        elif not neutral and colour_page is None:
            colour_page = p
        if neutral_page is not None and colour_page is not None:
            break

    chosen = [p for p in (neutral_page, colour_page) if p is not None]
    for p in order:
        if len(chosen) >= _MAX_PAGES:
            break
        if p not in chosen:
            chosen.append(p)
    return chosen[:_MAX_PAGES]


@unittest.skipUnless(_ROOT, "set INKDRILL_CORPUS to run the corpus smoke test")
class T0_10_Corpus(unittest.TestCase):

    def setUp(self):
        self.pages = _pages()
        if not self.pages:
            self.skipTest(f"no pages under {_ROOT}")

    def test_pages_decode_to_the_declared_length(self):
        for p in self.pages:
            with self.subTest(p.name):
                img = read_png(p)
                self.assertEqual(len(img.gray), img.width * img.height)

    def test_dpi_is_present_and_plausible(self):
        """Real corpus pages carry pHYs universally (measured
        (399.9992, 399.9992) on sampled pages) -- assert presence rather
        than guarding on it, so a regression that returns None for every
        page cannot pass silently."""
        for p in self.pages:
            with self.subTest(p.name):
                dpi = read_png(p).dpi
                self.assertIsNotNone(dpi)
                self.assertGreater(dpi[0], 50)
                self.assertLess(dpi[0], 2400)

    def test_sweep_runs_clean_and_the_cycle_rank_identity_holds(self):
        for p in self.pages:
            with self.subTest(p.name):
                img = read_png(p)
                mask = binarize(img.gray, img.width, img.height)
                res = sweep(mask, capture=Capture.GRAPH)
                self.assertTrue(res.check_cycle_rank())
                self.assertGreater(res.component_count, 0)

    def test_row_and_col_agree_on_component_count(self):
        """G6 of U3, exercised on real ink rather than a fixture."""
        for p in self.pages:
            with self.subTest(p.name):
                img = read_png(p)
                mask = binarize(img.gray, img.width, img.height)
                self.assertEqual(sweep(mask, axis="row").component_count,
                                 sweep(mask, axis="col").component_count)
