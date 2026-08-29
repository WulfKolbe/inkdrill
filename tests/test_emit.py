"""T1: inkdrill findings as a MathPix-shaped `lines.json`.

Hermetic. Masks are built from ASCII pictures, so a table fixture is
readable as a table in the source.
"""

import json
import unittest
from unittest import mock

from inkdrill.emit import glyph_line  # noqa: F401
from inkdrill.emit import free_rules, is_rule  # noqa: F401
from inkdrill.emit import (NoResolution, cell_grid, diagram_line,
                           ink_regions, is_rule, lines_json, page_lines,
                           page_record, rule_record, rule_width_pt,
                           table_lines)
from inkdrill.raster import InkMask

DPI = (400.0, 400.0)
PT = 72.0 / 400.0


def grid_mask(rows, cols, cell=6, rule=1):
    """A ruled table: `rows` x `cols` cells with a 1 px rule between."""
    w = cols * (cell + rule) + rule
    h = rows * (cell + rule) + rule
    buf = bytearray(w * h)
    for r in range(rows + 1):
        y = r * (cell + rule)
        buf[y * w:(y + 1) * w] = b"\xff" * w
    for c in range(cols + 1):
        x = c * (cell + rule)
        for y in range(h):
            buf[y * w + x] = 0xFF
    return InkMask(bytes(buf), w, h)


def lines_for(mask, tol=1.0):
    return table_lines(mask, pt=PT, tol=tol)


class T1_1_Coordinates(unittest.TestCase):
    """G1, G2: points from pHYs, or nothing."""

    def test_regions_are_in_points(self):
        p = page_record(page=1, width_px=3400, height_px=4400, dpi=DPI)
        self.assertAlmostEqual(p["page_width"], 3400 * PT)
        self.assertAlmostEqual(p["page_height"], 4400 * PT)

    def test_a_missing_pHYs_raises_rather_than_guessing(self):
        """The failure this exists to prevent: a file whose coordinates
        are silently in the wrong space cannot be detected downstream."""
        for bad in (None, (0.0, 0.0), (None, None)):
            with self.subTest(dpi=bad):
                with self.assertRaises(NoResolution):
                    page_record(page=1, width_px=10, height_px=10, dpi=bad)

    def test_nominal_A4_would_have_given_a_different_answer(self):
        """Why `pHYs` and not the page size. On `e12s39` the MediaBox is
        595 x 842, not A4's nominal 595.32 x 841.92, and the nominal
        derivation is wrong by 0.071 pt -- the size of the residual
        being measured at the time."""
        from_phys = 974 * (72.0 / 399.9992)
        from_nominal = 974 * 595.32 / 3306
        self.assertAlmostEqual(from_phys, 175.320, places=3)
        self.assertGreater(abs(from_nominal - from_phys), 0.05)

    def test_a_region_is_in_the_same_space_as_its_page(self):
        mask = grid_mask(2, 2)
        lines = lines_for(mask)
        p = page_record(page=1, width_px=mask.width, height_px=mask.height,
                        dpi=DPI, lines=lines)
        for ln in p["lines"]:
            r = ln["region"]
            self.assertLessEqual(r["top_left_x"] + r["width"],
                                 p["page_width"] + 1e-9)
            self.assertLessEqual(r["top_left_y"] + r["height"],
                                 p["page_height"] + 1e-9)


class T1_2_Wrapper(unittest.TestCase):
    """The document shape, and G5."""

    def test_the_ocr_block_declares_the_space(self):
        d = lines_json([], render_dpi=400.0)
        self.assertEqual(d["ocr"]["units"], "pt")
        self.assertEqual(d["ocr"]["render_dpi"], 400.0)
        # A2: what wrote this. Asserted by KEY, not by whole-dict
        # equality -- the previous form pinned the block exactly and
        # would have to be edited for every field added to it, which
        # makes it a change detector rather than a contract.
        self.assertEqual(d["ocr"]["producer"], "inkdrill")
        self.assertTrue(d["ocr"]["version"])
        self.assertEqual(d["source"], "inkdrill")

    def test_it_round_trips_through_json(self):
        mask = grid_mask(3, 2)
        d = lines_json([page_record(page=1, width_px=mask.width,
                                    height_px=mask.height, dpi=DPI,
                                    lines=lines_for(mask))],
                       render_dpi=400.0)
        self.assertEqual(json.loads(json.dumps(d)), d)


class T1_3_Cells(unittest.TestCase):
    """G3: the lattice gives row and column directly."""

    def test_a_13_by_4_lattice_recovers_its_grid(self):
        mask = grid_mask(13, 4)
        lines = lines_for(mask)
        cells = [l for l in lines if l["type"] == "simple_cell"]
        self.assertEqual(len(cells), 52)
        self.assertEqual(lines[0]["ink"]["rows"], 13)
        self.assertEqual(lines[0]["ink"]["columns"], 4)

    def test_the_pairs_are_exactly_the_rectangle_with_no_gaps(self):
        """The strong form of G3, and what `table_structure.check`
        validates on the other side -- so a disagreement between them is
        informative rather than redundant."""
        for rows, cols in ((2, 2), (5, 3), (13, 4)):
            with self.subTest(rows=rows, cols=cols):
                mask = grid_mask(rows, cols)
                lines = lines_for(mask)
                pairs = [(l["cell_row"], l["cell_column"])
                         for l in lines if l["type"] == "simple_cell"]
                self.assertEqual(sorted(pairs),
                                 sorted((r, c) for r in range(rows)
                                        for c in range(cols)))

    def test_every_cell_carries_both_indices(self):
        mask = grid_mask(3, 3)
        for l in lines_for(mask):
            if l["type"] == "simple_cell":
                self.assertIsNotNone(l["cell_row"])
                self.assertIsNotNone(l["cell_column"])
                self.assertEqual((l["cell_row_span"], l["cell_col_span"]),
                                 (1, 1))

    def test_A_PARTIALLY_MERGED_GRID_REPORTS_THE_SPAN_END_TO_END(self):
        """The `\\cline` case, through the real path and not `cell_grid`.

        A 2x3 grid with ONE interior vertical segment undrawn: the
        top-left two cells merge. Before spans this reported a 2x2 table
        -- a valid exact rectangle, so G3 passed on the wrong shape.
        """
        m = grid_mask(2, 3)
        w = m.width
        buf = bytearray(m.data)
        for y in range(1, 7):
            buf[y * w + 7] = 0
        lines = lines_for(InkMask(bytes(buf), w, m.height))
        cells = [(l["cell_row"], l["cell_column"],
                  l["cell_row_span"], l["cell_col_span"])
                 for l in lines if l["type"] == "simple_cell"]
        self.assertEqual(cells[0], (0, 0, 1, 2), "merged cell lost its span")
        self.assertEqual(len(cells), 5)
        self.assertEqual((lines[0]["ink"]["rows"],
                          lines[0]["ink"]["columns"]), (2, 3))

    def test_a_FULLY_merged_axis_emits_nothing_KNOWN_LIMIT(self):
        """Where spans do NOT reach, recorded rather than claimed.

        Remove a 2x2's middle horizontal rule entirely and the interior
        becomes ONE connected region -- the lattice is destroyed, not
        reduced -- so the two-hole threshold rejects it and no table is
        emitted at all.

        That is a MISSED table, not a wrong one, which is the failure
        this project prefers: nothing is asserted about a shape the ink
        cannot support. Spans fix the partial case (above); recovering
        this one needs the rules themselves, which is the deferred
        run-structure work.
        """
        m = grid_mask(2, 2)
        w = m.width
        buf = bytearray(m.data)
        buf[7 * w + 1:7 * w + w - 1] = b"\x00" * (w - 2)
        self.assertEqual(lines_for(InkMask(bytes(buf), w, m.height)), [])

    def test_a_single_hole_is_a_frame_and_not_a_1x1_table(self):
        """A hollow rectangle encloses its interior, so it always has
        ONE hole. Calling that a lattice would make every plot frame a
        1x1 table -- true, useless, and it hands the consumer a table
        where it expected a figure. Two holes is the smallest thing that
        can carry a row or column index."""
        buf = bytearray(20 * 20)
        for x in range(20):
            buf[x] = 0xFF
            buf[19 * 20 + x] = 0xFF
        for y in range(20):
            buf[y * 20] = 0xFF
            buf[y * 20 + 19] = 0xFF
        mask = InkMask(bytes(buf), 20, 20)
        self.assertEqual(lines_for(mask), [])

    def test_a_hole_region_id_is_refused_rather_than_returning_nothing(self):
        """The two-id-spaces trap, made unrepresentable.

        `nest` numbers regions in its own space and `moments_per_component`
        keys by `Component.root`; they are unrelated. Passing the wrong
        one used to return an empty hole list and an empty table -- no
        exception, just a silently missing lattice, which is how the
        `root` vs `nodes[0]` trap cost 1,293 of 1,310 components.
        """
        from inkdrill.nest import Kind, nest
        mask = grid_mask(2, 2)
        n = nest(mask)
        hole = next(r.id for r in n.regions.values() if r.kind is Kind.HOLE)
        with self.assertRaises(ValueError):
            table_lines(mask, hole, pt=PT, tol=1.0)

    def test_ink_regions_lists_what_may_be_passed(self):
        from inkdrill.nest import Kind, nest
        n = nest(grid_mask(2, 2))
        got = ink_regions(n)
        self.assertTrue(got)
        self.assertTrue(all(r.kind is Kind.INK for r in got))

    def test_cell_grid_clusters_within_tolerance(self):
        boxes = [(0, 0, 5, 5), (10, 0, 15, 5), (0, 10, 5, 15), (10, 10, 15, 15)]
        self.assertEqual(cell_grid(boxes, tol=1.0),
                         [(0, 0, 1, 1), (0, 1, 1, 1),
                          (1, 0, 1, 1), (1, 1, 1, 1)])

    def test_A_MERGED_CELL_REPORTS_ITS_SPAN(self):
        """The defect this exists for, and G3 cannot see it.

        A grid with an internal rule undrawn has a hole covering two
        bands. Reporting only the index reduces the table to whatever
        grid the holes happen to tile -- and that reduced grid is still
        an exact rectangle, so G3 PASSES on the wrong shape.
        """
        # Three columns; the top-left two are merged into one hole.
        boxes = [(0, 0, 21, 10),            # spans columns 0 and 1
                 (22, 0, 32, 10),
                 (0, 11, 10, 21), (11, 11, 21, 21), (22, 11, 32, 21)]
        got = cell_grid(boxes, tol=1.0)
        self.assertEqual(got[0], (0, 0, 1, 2), "merged cell lost its span")
        self.assertEqual(got[1], (0, 2, 1, 1))
        self.assertEqual(got[2:], [(1, 0, 1, 1), (1, 1, 1, 1), (1, 2, 1, 1)])

    def test_a_row_span_is_reported_the_same_way(self):
        boxes = [(0, 0, 10, 21),            # spans rows 0 and 1
                 (11, 0, 21, 10), (11, 11, 21, 21)]
        got = cell_grid(boxes, tol=1.0)
        self.assertEqual(got[0], (0, 0, 2, 1))
        self.assertEqual(got[1:], [(0, 1, 1, 1), (1, 1, 1, 1)])

    def test_the_grid_extent_counts_spans_not_just_indices(self):
        """`ink.rows` must be the table's real height, which a merged
        cell in the last row would otherwise understate.

        The left column supplies the evidence for two bands; the right
        cell spans both. Without a second band START somewhere, a merely
        TALLER hole is not a span -- there is nothing to say the table
        has two rows -- and the first version of this test asserted a
        span the lattice had no grounds for.
        """
        boxes = [(0, 0, 10, 10), (0, 11, 10, 21), (11, 0, 21, 21)]
        got = cell_grid(boxes, tol=1.0)
        self.assertEqual(got[2], (0, 1, 2, 1))
        self.assertEqual(max(r + rs for r, _, rs, _ in got), 2)

    def test_a_tolerance_that_is_too_large_merges_columns(self):
        """The tolerance is a decision, so its failure mode is asserted:
        set it wider than the cell pitch and two columns become one."""
        boxes = [(0, 0, 5, 5), (10, 0, 15, 5)]
        self.assertEqual(cell_grid(boxes, tol=99.0),
                         [(0, 0, 1, 1), (0, 0, 1, 1)])


class T1_4_Rules(unittest.TestCase):
    """G4 and the one number T2 needs."""

    def test_stroke_width_from_area_over_the_long_side(self):
        # A 100 x 3 px rule at 400 dpi.
        self.assertAlmostEqual(rule_width_pt(300, 100, 3, PT), 3 * PT)

    def test_orientation_does_not_change_the_answer(self):
        self.assertAlmostEqual(rule_width_pt(300, 3, 100, PT),
                               rule_width_pt(300, 100, 3, PT))

    def test_a_rule_with_no_extent_raises(self):
        with self.assertRaises(ValueError):
            rule_width_pt(0, 0, 0, PT)

    def test_no_line_entry_is_a_rule_or_a_glyph(self):
        """G4: the emitted types are the ones a consumer can act on."""
        mask = grid_mask(4, 3)
        kinds = {l["type"] for l in lines_for(mask)}
        self.assertTrue(kinds <= {"table", "simple_cell"})

    def test_text_is_empty_on_every_line(self):
        """G6: inkdrill does not read text and must not appear to."""
        mask = grid_mask(3, 2)
        for l in lines_for(mask):
            self.assertEqual((l["text"], l["text_display"]), ("", ""))


def hline(buf, w, y, x0, x1, thick):
    for t in range(thick):
        buf[(y + t) * w + x0:(y + t) * w + x1] = b"\xff" * (x1 - x0)


def frame(buf, w, x0, y0, x1, y1, thick=1):
    for t in range(thick):
        buf[(y0 + t) * w + x0:(y0 + t) * w + x1] = b"\xff" * (x1 - x0)
        buf[(y1 - 1 - t) * w + x0:(y1 - 1 - t) * w + x1] = b"\xff" * (x1 - x0)
    for y in range(y0, y1):
        for t in range(thick):
            buf[y * w + x0 + t] = 0xFF
            buf[y * w + x1 - 1 - t] = 0xFF


class T1_5_Rules(unittest.TestCase):
    """Step 4: ink.rules[], the measurement T2 needs."""

    def test_a_solid_long_component_is_a_rule(self):
        class R:
            id, area, x0, y0, x1, y1 = 0, 300, 0, 0, 99, 2
        self.assertTrue(is_rule(R))

    def test_a_square_block_is_not_a_rule(self):
        class R:
            id, area, x0, y0, x1, y1 = 0, 100, 0, 0, 9, 9
        self.assertFalse(is_rule(R))

    def test_a_zero_extent_region_is_refused_rather_than_dividing_by_zero(self):
        class R:
            id, area, x0, y0, x1, y1 = 0, 0, 5, 5, 4, 4    # x1 < x0
        self.assertFalse(is_rule(R))

    def test_a_long_but_sparse_component_is_not_a_rule(self):
        """Aspect alone admits a hairline that is mostly gaps; the fill
        condition is what excludes it."""
        class R:
            id, area, x0, y0, x1, y1 = 0, 60, 0, 0, 99, 2
        self.assertFalse(is_rule(R))

    def test_a_rule_attaches_to_the_INNERMOST_container_only(self):
        """One measurement, one entry. The first form attached a rule to
        every containing line, so a rule inside a frame inside a frame
        arrived three times. Both sides asserted: exactly one entry in
        total, and it sits on the SMALLER container."""
        w, h = 600, 400
        buf = bytearray(w * h)
        frame(buf, w, 5, 5, 595, 395)
        frame(buf, w, 100, 100, 500, 300)
        hline(buf, w, 200, 130, 470, 3)
        buf[50 * w + 50] = 0xFF              # content, so both frames
        buf[150 * w + 150] = 0xFF            # survive containment
        lines = page_lines(InkMask(bytes(buf), w, h), pt=PT, tol=1.0)
        carrying = [l for l in lines if l.get("ink", {}).get("rules")]
        self.assertEqual(len(carrying), 1)
        self.assertEqual(len(carrying[0]["ink"]["rules"]), 1)
        widths = [l["region"]["width"] for l in lines
                  if l["type"] in ("diagram", "block")]
        self.assertEqual(carrying[0]["region"]["width"], min(widths))

    def test_a_rule_attaches_to_TABLE_OR_DIAGRAM_lines_only(self):
        """`block` and `glyph` boxes come from other partitions -- the
        white route, the cluster union -- and can share a box with a
        diagram, so admitting them as targets makes ownership an
        iteration-order accident. Measured on 2409.18839 p7: the frame's
        rule moved from the diagram to a block and back depending on
        which types competed.

        The fixture is that page's shape: a frame (diagram) containing a
        text-like block (white route) with a rule inside it. The block
        is the SMALLER container, so innermost-of-anything picks the
        block and innermost-of-table-or-diagram picks the frame -- the
        two answers differ, which is what lets the mutant die.

        Three earlier fixtures could not produce the block at all, and
        each taught the same lesson at a different scale: the gap floor
        is ~2x a text height on a real page, so marks must be SMALLER
        than the floor with sub-floor gaps (real letters), rows must
        overlap the pitch (real ascenders/descenders interrupt the
        inter-line band), and a free-standing rule always cuts its
        block in two -- the pieces rejoin only because `merge_boxes`
        runs, which is the same mechanism that lifted the corpus
        measurement from 6 to 8 matched.
        """
        w, h = 600, 400
        buf = bytearray(w * h)
        frame(buf, w, 5, 5, 595, 395)
        rows = [100, 122, 144, 166, 194, 216, 238]
        for i, ry in enumerate(rows):             # brick-staggered marks,
            off = 14 if i % 2 else 0              # taller than the pitch
            for c in range(10):
                for y in range(ry, ry + 24):
                    for x in range(150 + off + c * 28,
                                   170 + off + c * 28):
                        buf[y * w + x] = 0xFF
        hline(buf, w, 191, 160, 420, 2)           # the rule, 1px clear
        m = InkMask(bytes(buf), w, h)
        lines = page_lines(m, pt=0.3, tol=1.0)
        kinds = [l["type"] for l in lines]
        self.assertIn("diagram", kinds)
        self.assertIn("block", kinds)
        carrying = [l for l in lines if l.get("ink", {}).get("rules")]
        self.assertEqual([l["type"] for l in carrying], ["diagram"])
        self.assertEqual(len(carrying[0]["ink"]["rules"]), 1)

    def test_TWO_RULE_WEIGHTS_GIVE_DISTINCT_WIDTHS(self):
        """The acceptance criterion, on a BOOKTABS table.

        The fixture matters and the first one was wrong. In a `|l|l|`
        table the rules ARE the frame -- one connected component -- so
        no rule is a separate region and `is_rule` finds nothing. A
        booktabs table draws disjoint horizontal rules, which is also
        the only place `\\toprule` versus `\\midrule` is a question at
        all. Rules inside a connected frame need extraction from the run
        structure and are a separate piece of work; see the module note.
        """
        # Realistic proportions: the aspect test is 20:1 and a real
        # booktabs rule at 400 dpi is nearer 250:1, so a 56 x 4 rule in
        # a toy fixture is 14:1 and correctly refused.
        w, h = 240, 44
        buf = bytearray(w * h)
        hline(buf, w, 4, 4, 236, 4)        # toprule, heavy
        hline(buf, w, 20, 4, 236, 2)       # midrule, light
        hline(buf, w, 36, 4, 236, 4)       # bottomrule, heavy
        # A hollow box so there is a parent to attach them to.
        frame(buf, w, 0, 0, 240, 44)
        mask = InkMask(bytes(buf), w, h)
        lines = page_lines(mask, pt=PT, tol=1.0)
        rules = [r for l in lines for r in l.get("ink", {}).get("rules", [])]
        widths = sorted({round(r["width_pt"], 6) for r in rules})
        self.assertGreaterEqual(len(widths), 2,
                                f"one weight only: {widths}")
        self.assertAlmostEqual(max(widths) / min(widths), 2.0, delta=0.6)

    def test_a_rule_carries_a_measurement_and_never_a_name(self):
        """G7: no `kind`, because the toprule/midrule call needs the
        table's context and is made on the other side."""
        class R:
            id, area, x0, y0, x1, y1 = 0, 300, 0, 0, 99, 2
        rec = rule_record(R, PT)
        self.assertEqual(set(rec),
                         {"x0", "y0", "x1", "y1", "width_pt", "orient"})
        self.assertEqual(rec["orient"], "h")

    def test_a_rule_is_never_a_line_of_its_own(self):
        """G4, asserted by COUNT. Checking only that the types are
        allowed lets a rule through as a `diagram`; three rules inside
        one frame must give one line, not four. 140 ticks on a plot page
        would otherwise drown a consumer expecting readable regions."""
        w, h = 240, 44
        buf = bytearray(w * h)
        for y in (4, 20, 36):
            hline(buf, w, y, 4, 236, 2)
        frame(buf, w, 0, 0, 240, 44)
        lines = page_lines(InkMask(bytes(buf), w, h), pt=PT, tol=1.0,
                           diagram_scale=0.0)
        self.assertEqual(len(lines), 1)
        self.assertEqual(len(lines[0]["ink"]["rules"]), 3)

    def test_a_vertical_rule_is_reported_as_vertical(self):
        w, h = 44, 240
        buf = bytearray(w * h)
        for y in range(4, 236):
            for t in range(2):
                buf[y * w + 20 + t] = 0xFF
        frame(buf, w, 0, 0, 44, 240)
        lines = page_lines(InkMask(bytes(buf), w, h), pt=PT, tol=1.0,
                           diagram_scale=0.0)
        rules = lines[0]["ink"]["rules"]
        self.assertEqual([r["orient"] for r in rules], ["v"])

    def test_a_rule_attaches_to_its_OWN_parent_only(self):  # noqa: D401
        """Containment, not "every rule on the page". Two frames side by
        side with a rule in one: the other must come back with none."""
        w, h = 520, 60
        buf = bytearray(w * h)
        frame(buf, w, 0, 0, 250, 60)
        frame(buf, w, 260, 0, 510, 60)
        hline(buf, w, 28, 10, 240, 2)          # inside the LEFT frame
        buf[30 * w + 380] = 0xFF               # and something in the RIGHT
        lines = page_lines(InkMask(bytes(buf), w, h), pt=PT, tol=1.0,
                           diagram_scale=0.0)
        counts = sorted(len(l.get("ink", {}).get("rules", [])) for l in lines)
        self.assertEqual(counts, [0, 1])

    def test_rules_are_in_the_same_space_as_the_regions(self):
        class R:
            id, area, x0, y0, x1, y1 = 0, 300, 0, 0, 99, 2
        rec = rule_record(R, PT)
        self.assertAlmostEqual(rec["x1"] - rec["x0"], 100 * PT)


class T1_6_Diagrams(unittest.TestCase):
    """Step 4: hollow rectangles that are not tables."""

    def test_A_PLOT_FRAME_IS_A_DIAGRAM_NOT_A_TABLE(self):
        """The acceptance criterion. Four separated frames must arrive
        as four `diagram` lines -- a plot frame reaching a consumer as a
        1x1 table is the failure this threshold exists for.

        `diagram_scale=0` because this page is nothing BUT frames: its
        median ink region is a frame, so a frame cannot be 3x it. A page
        with no text cannot supply a text scale, which is the fixture
        having nothing to measure against rather than the rule being
        wrong.

        EACH FRAME HAS SOMETHING IN IT, because a real plot does. An
        empty rectangle is not a diagram under the containment rule and
        should not be -- there is nothing in it to be a diagram OF. The
        fixture used to be four bare rectangles, which is the "a
        synthetic grid has no letters in it" mistake in another costume.
        """
        w, h = 90, 90
        buf = bytearray(w * h)
        for ox, oy in ((2, 2), (48, 2), (2, 48), (48, 48)):
            frame(buf, w, ox, oy, ox + 38, oy + 38)
            for k in range(3):                    # plot data inside it
                buf[(oy + 10 + k * 8) * w + ox + 10 + k * 6] = 0xFF
        lines = page_lines(InkMask(bytes(buf), w, h), pt=PT, tol=1.0,
                           diagram_scale=0.0)
        self.assertEqual([l["type"] for l in lines], ["diagram"] * 4)

    def test_a_textured_region_is_a_diagram_with_its_ground(self):
        w, h = 40, 40
        buf = bytearray(w * h)
        frame(buf, w, 0, 0, 40, 40)
        buf[20 * w + 20] = 0xFF
        mask = InkMask(bytes(buf), w, h)
        from inkdrill.nest import nest
        n = nest(mask)
        rid = max(ink_regions(n), key=lambda r: r.area).id
        lines = page_lines(mask, pt=PT, tol=1.0, diagram_scale=0.0,
                           grounds={rid: "textured"})
        self.assertEqual(lines[0]["type"], "diagram")
        self.assertEqual(lines[0]["ink"]["border_ground"], "textured")

    def test_the_diagram_reports_WHAT_IT_CONTAINS(self):
        """Found by mutation: the `contains` key could be dropped
        entirely and nothing failed.

        It is the EVIDENCE for the call, not decoration. A consumer that
        wants a stricter cut than "at least one" applies it to this
        number instead of re-running `nest`, so a wrong or missing value
        silently removes that option.
        """
        w, h = 60, 60
        buf = bytearray(w * h)
        frame(buf, w, 0, 0, 60, 60)
        for k in range(3):                       # exactly three inside
            buf[(15 + k * 12) * w + 30] = 0xFF
        line = page_lines(InkMask(bytes(buf), w, h), pt=PT, tol=1.0,
                          diagram_scale=0.0)[0]
        self.assertEqual(line["type"], "diagram")
        self.assertEqual(line["ink"]["contains"], 3)

    def test_a_letter_sized_hollow_region_is_NOT_a_diagram(self):
        """The Heim failure, pinned. A scanned German page emitted 319
        lines, every one a `diagram`, median 5.3 x 7.4 pt -- every `o`,
        `e`, `a` and `ue` on the page. `diagram` had no size floor at
        all while `table` had one, so hollow glyphs fell through the
        table branch straight into it.

        A CELL is bounded below because it CONTAINS text; a DIAGRAM is
        bounded below because it REPLACES text. Different arguments,
        same threshold shape.
        """
        w, h = 240, 60
        buf = bytearray(w * h)
        for i in range(12):                      # a row of hollow "o"s
            ox = 4 + i * 19
            for x in range(ox, ox + 12):
                buf[20 * w + x] = 0xFF
                buf[39 * w + x] = 0xFF
            for y in range(20, 40):
                buf[y * w + ox] = 0xFF
                buf[y * w + ox + 11] = 0xFF
        m = InkMask(bytes(buf), w, h)
        # Size alone admits them once the floor is removed ...
        self.assertGreater(len(page_lines(m, pt=PT, tol=1.0,
                                          diagram_scale=0.0,
                                          require_content=False)), 0)
        # ... the size floor rejects them ...
        self.assertEqual(page_lines(m, pt=PT, tol=1.0, diagram_scale=3.0,
                                    require_content=False), [])
        # ... and CONTAINMENT rejects them with no threshold at all,
        # because the counter of an `o` holds nothing. That is the rule
        # that needs no retuning when the text size changes.
        self.assertEqual(page_lines(m, pt=PT, tol=1.0,
                                    diagram_scale=0.0), [])

    def test_a_solid_blob_is_neither_table_nor_diagram(self):
        """G4: a bare component is not a line."""
        buf = bytearray(b"\xff" * (20 * 20))
        self.assertEqual(page_lines(InkMask(bytes(buf), 20, 20),
                                    pt=PT, tol=1.0), [])

    def test_a_blank_mask_returns_nothing_rather_than_raising(self):
        """Guards `max(inks)` on an empty sequence -- a page with no ink
        is a legitimate input and must not raise."""
        blank = InkMask(bytes(20 * 20), 20, 20)
        self.assertEqual(table_lines(blank, pt=PT), [])
        self.assertEqual(page_lines(blank, pt=PT), [])

    def test_a_diagram_without_a_ground_omits_the_key(self):
        """Absent, not `None`. A key present with a null value says the
        ground was measured and found to be nothing, which is not what
        happened -- it was not measured."""
        w, h = 40, 40
        buf = bytearray(w * h)
        frame(buf, w, 0, 0, 40, 40)
        buf[20 * w + 20] = 0xFF          # a diagram is a diagram OF something
        line = page_lines(InkMask(bytes(buf), w, h), pt=PT, tol=1.0,
                          diagram_scale=0.0)[0]
        self.assertNotIn("border_ground", line["ink"])

    def test_an_object_with_no_rules_omits_the_array(self):
        """Same rule one level up: no `rules` key rather than `[]`."""
        w, h = 40, 40
        buf = bytearray(w * h)
        frame(buf, w, 0, 0, 40, 40)
        buf[20 * w + 20] = 0xFF
        line = page_lines(InkMask(bytes(buf), w, h), pt=PT, tol=1.0,
                          diagram_scale=0.0)[0]
        self.assertNotIn("rules", line["ink"])

    def test_a_lattice_still_wins_over_diagram(self):
        """`cell_scale` is relative to the page's own text, and this
        fixture has no text -- its median ink region IS the frame, so a
        6 px cell cannot clear 3x it. Passing 0 disables the floor,
        which is what a fixture with nothing to measure against needs.
        A real page supplies its own scale."""
        lines = page_lines(grid_mask(3, 3), pt=PT, tol=1.0, cell_scale=0.0)
        self.assertEqual(lines[0]["type"], "table")

    def test_the_cell_floor_is_RELATIVE_to_the_page_text(self):
        """A glyph counter is smaller than its glyph; a table cell is
        larger than the text inside it. Measured on real pages, a
        figure page falls from 284 false cells to 4 while a real 13x4
        grid holds at exactly 52 across a 3x range of the parameter."""
        m = grid_mask(3, 3)
        self.assertGreater(len(page_lines(m, pt=PT, tol=1.0, cell_scale=0.0)),
                           len(page_lines(m, pt=PT, tol=1.0, cell_scale=9.0)))


if __name__ == "__main__":
    unittest.main()


class T1_8_Glyphs(unittest.TestCase):
    """T2: the blobs exist and nothing emitted them.

    A `glyph` line describes a component and names nothing. Every class
    of the decision is asserted to fire -- the standing rule after five
    "a class that could not occur" defects.
    """

    @staticmethod
    def _letters(w=200, h=60, n=6):
        """`n` hollow rings, so holes are non-zero and the components
        are letter-shaped rather than solid blocks."""
        buf = bytearray(w * h)
        for i in range(n):
            ox = 4 + i * 30
            for x in range(ox, ox + 16):
                buf[18 * w + x] = 0xFF
                buf[41 * w + x] = 0xFF
            for y in range(18, 42):
                buf[y * w + ox] = 0xFF
                buf[y * w + ox + 15] = 0xFF
        return InkMask(bytes(buf), w, h)

    def test_a_text_page_never_builds_the_forest(self):
        """T4's gate, asserted by counting rather than by timing.

        Skipping the background sweep cannot change the output, so
        "always nest" is an equivalent mutant and no output test
        reaches it. What can be checked is that the work does not
        happen -- and the opposite case, that a page with a table does
        build the forest, so the gate is not simply always closed.

        The spy has to sit on `nest._build`, which BOTH paths go
        through. Patching `emit.nest` was the first attempt and could
        not fail: the code reaches the forest via `InkPass.complete()`,
        so that spy never fired whatever the gate did.
        """
        import unittest.mock as mock
        import inkdrill.nest as N
        with mock.patch.object(N, "_build", wraps=N._build) as spy:
            page_lines(self._letters(), pt=PT, tol=1.0, glyphs=True)
        self.assertEqual(spy.call_count, 0)

    def test_a_page_with_a_table_DOES_build_the_forest_and_the_spy_fires(self):
        """The other side, on the SAME spy -- otherwise the assertion
        above passes on a spy that could never fire."""
        import unittest.mock as mock
        import inkdrill.nest as N
        with mock.patch.object(N, "_build", wraps=N._build) as spy:
            page_lines(self._grid(), pt=PT, tol=1.0, cell_scale=0.0)
        self.assertEqual(spy.call_count, 1)

    @staticmethod
    def _grid():
        w, h = 400, 200
        buf = bytearray(w * h)
        for x in range(10, 390):
            for t in range(3):
                buf[(10 + t) * w + x] = 0xFF
                buf[(100 + t) * w + x] = 0xFF
                buf[(190 + t) * w + x] = 0xFF
        for y in range(10, 193):
            for t in range(3):
                buf[y * w + 10 + t] = 0xFF
                buf[y * w + 200 + t] = 0xFF
                buf[y * w + 389 + t] = 0xFF
        return InkMask(bytes(buf), w, h)

    def test_a_page_with_a_table_still_emits_it(self):
        lines = page_lines(self._grid(), pt=PT, tol=1.0, cell_scale=0.0)
        self.assertIn("table", [l["type"] for l in lines])

    def test_glyphs_are_OFF_by_default(self):
        """Opt-in, because it changes what every existing consumer
        receives. The negative side of the switch, asserted."""
        m = self._letters()
        self.assertEqual(page_lines(m, pt=PT, tol=1.0), [])

    def test_one_line_per_component_with_its_holes(self):
        m = self._letters(n=6)
        lines = page_lines(m, pt=PT, tol=1.0, glyphs=True)
        self.assertEqual([l["type"] for l in lines], ["glyph"] * 6)
        self.assertEqual([l["ink"]["holes"] for l in lines], [1] * 6)

    def test_the_axis_of_a_TALL_component_differs_from_a_WIDE_one(self):
        """The axis is measured, not copied. A fixture of one shape
        could not tell a real principal axis from a constant."""
        w, h = 80, 80
        buf = bytearray(w * h)
        for y in range(5, 70):                    # a tall bar
            for x in range(8, 14):
                buf[y * w + x] = 0xFF
        for x in range(30, 75):                   # a wide bar
            for y in range(30, 36):
                buf[y * w + x] = 0xFF
        lines = page_lines(InkMask(bytes(buf), w, h), pt=PT, tol=1.0,
                           glyphs=True)
        axes = [l["ink"]["axis"] for l in lines]
        self.assertEqual(len(axes), 2)
        tall, wide = sorted(axes, key=lambda a: abs(a[0]))
        self.assertLess(abs(tall[0]), 0.2)        # points down the page
        self.assertGreater(abs(wide[0]), 0.8)     # points across it

    def test_a_region_emitted_as_a_TABLE_is_not_also_a_glyph(self):
        """One object, one line. A component that already arrived as a
        table must not arrive again as a blob."""
        w, h = 400, 200
        buf = bytearray(w * h)
        for x in range(10, 390):
            for t in range(3):
                buf[(10 + t) * w + x] = 0xFF
                buf[(190 + t) * w + x] = 0xFF
                buf[(100 + t) * w + x] = 0xFF
        for y in range(10, 193):
            for t in range(3):
                buf[y * w + 10 + t] = 0xFF
                buf[y * w + 200 + t] = 0xFF
                buf[y * w + 389 + t] = 0xFF
        lines = page_lines(InkMask(bytes(buf), w, h), pt=PT, tol=1.0,
                           glyphs=True, cell_scale=0.0)
        kinds = [l["type"] for l in lines]
        self.assertIn("table", kinds)
        table_ids = {l["ink"]["region_id"] for l in lines
                     if l["type"] == "table"}
        glyph_ids = {l["ink"]["region_id"] for l in lines
                     if l["type"] == "glyph"}
        self.assertEqual(table_ids & glyph_ids, set())

    def test_the_axis_key_is_ABSENT_not_null_when_unmatched(self):
        """`glyph_line` is reachable directly, and a key present with a
        null value would claim the axis was measured and found to be
        nothing."""
        from inkdrill.nest import Kind as K, Region
        r = Region(7, K.INK, 0, 12, 1, 2, 5, 9)
        self.assertNotIn("axis", glyph_line(r, PT)["ink"])
        self.assertIn("axis", glyph_line(r, PT, axis=(1.0, 0.0))["ink"])


if __name__ == "__main__":
    unittest.main()


class T1_9_Candidates(unittest.TestCase):
    """C3 and C4: the glyph line carries a RANKED LIST and no decision.

    This path first ran on real data and the suite passed anyway --
    nothing supplied a classifier, so `_crop` raised `NameError` on a
    missing import with 905 tests green. A branch no test reaches
    executes first on a real page, unverified.
    """

    @staticmethod
    def _dots(n=3):
        """`n` separated 6x6 squares -- one component each, so the
        number of glyph lines is known exactly."""
        w, h = 20 * n, 20
        buf = bytearray(w * h)
        for i in range(n):
            for y in range(6, 12):
                for x in range(6 + i * 20, 12 + i * 20):
                    buf[y * w + x] = 0xFF
        return InkMask(bytes(buf), w, h)

    @staticmethod
    def _clf(labels=("a", "b", "c")):
        from inkdrill.classify import Channels, Classifier, Template
        c = Classifier(channels=Channels(1.0, 0.0, 0.0))
        for i, lab in enumerate(labels):
            c.add(Template(lab, (1 << (i + 1)) - 1))
        return c

    def test_no_classifier_means_the_key_is_ABSENT(self):
        lines = page_lines(self._dots(), pt=PT, tol=1.0, glyphs=True)
        self.assertTrue(lines)
        for l in lines:
            self.assertNotIn("candidates", l["ink"])

    def test_a_classifier_yields_a_ranked_list_per_glyph(self):
        lines = page_lines(self._dots(), pt=PT, tol=1.0, glyphs=True,
                           classifier=self._clf(), top_k=3)
        self.assertEqual(len(lines), 3)
        for l in lines:
            cands = l["ink"]["candidates"]
            self.assertEqual(len(cands), 3)
            self.assertEqual([c[1] for c in cands],
                             sorted(c[1] for c in cands))

    def test_top_k_bounds_the_list(self):
        lines = page_lines(self._dots(1), pt=PT, tol=1.0, glyphs=True,
                           classifier=self._clf(tuple("abcdefgh")), top_k=2)
        self.assertEqual(len(lines[0]["ink"]["candidates"]), 2)

    def test_an_EMPTY_classifier_yields_an_EMPTY_LIST_not_a_missing_key(self):
        """The 14.4% transmitted rather than hidden. Empty and absent are
        different statements: absent means nobody asked, empty means the
        question was asked and nothing matched."""
        from inkdrill.classify import Classifier
        lines = page_lines(self._dots(1), pt=PT, tol=1.0, glyphs=True,
                           classifier=Classifier())
        self.assertEqual(lines[0]["ink"]["candidates"], [])

    def test_NO_LINE_EVER_CARRIES_A_SINGLE_LABEL(self):
        """C4, asserted rather than trusted. inkdrill has no lexicon, so
        choosing among candidates is the consumer's call; a `label` key
        would be a decision taken by the party with less information."""
        lines = page_lines(self._dots(), pt=PT, tol=1.0, glyphs=True,
                           classifier=self._clf(), top_k=3)
        for l in lines:
            self.assertNotIn("label", l)
            self.assertNotIn("label", l["ink"])
            self.assertIsInstance(l["ink"]["candidates"], list)

    def test_the_topology_pair_is_always_present(self):
        lines = page_lines(self._dots(1), pt=PT, tol=1.0, glyphs=True)
        self.assertEqual(lines[0]["ink"]["components"], 1)
        self.assertIn("holes", lines[0]["ink"])


if __name__ == "__main__":
    unittest.main()


class T1_10_ProducerVersion(unittest.TestCase):
    """A2: "same bytes" must not be ambiguous between nothing changed
    and the change could not reach this path."""

    def test_the_version_is_reported_and_non_empty(self):
        from inkdrill.emit import lines_json
        ocr = lines_json([], render_dpi=600.0)["ocr"]
        self.assertEqual(ocr["producer"], "inkdrill")
        self.assertIsInstance(ocr["version"], str)
        self.assertTrue(ocr["version"])

    def test_the_version_matches_the_checkout(self):
        """It is the git commit when there is one. Compared against the
        repository rather than against itself, so a constant that never
        moves cannot pass."""
        import pathlib as _p
        import subprocess
        from inkdrill.version import UNKNOWN, resolve
        root = _p.Path(__file__).resolve().parents[1]
        if not (root / ".git").exists():
            self.skipTest("not a git checkout")
        want = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                              capture_output=True, text=True)
        if want.returncode:
            self.skipTest("git unavailable")
        got = resolve()
        self.assertNotEqual(got, UNKNOWN)
        self.assertTrue(want.stdout.strip().startswith(got))

    def test_outside_a_checkout_it_is_UNKNOWN_not_a_made_up_number(self):
        """`unknown` is the truthful answer with no `.git` to read. A
        fabricated constant would claim "same code" and be wrong, which
        is worse than admitting ignorance."""
        import inkdrill.version as V
        saved = V._cached
        try:
            V._cached = None
            with mock.patch.object(
                    V.pathlib.Path, "is_dir", lambda self: False), \
                 mock.patch.object(
                     V.pathlib.Path, "is_file", lambda self: False):
                self.assertEqual(V.resolve(), V.UNKNOWN)
        finally:
            V._cached = saved

    def test_it_is_resolved_once_and_cached(self):
        """G4: emitting a document must not cost a file read per page."""
        import inkdrill.version as V
        saved = V._cached
        try:
            V._cached = None
            first = V.resolve()
            with mock.patch.object(
                    V, "_head_of", side_effect=AssertionError("re-read")):
                self.assertEqual(V.resolve(), first)
        finally:
            V._cached = saved


class T1_11_GlyphsAreClusters(unittest.TestCase):
    """A1: one line per GLYPH, not per component."""

    @staticmethod
    def _page():
        """A line of prose with an `i` in it: an ascender establishes the
        row band, without which the tittle is its own row."""
        w, h = 300, 60
        buf = bytearray(w * h)

        def box(x0, y0, x1, y1):
            for y in range(y0, y1):
                for x in range(x0, x1):
                    buf[y * w + x] = 0xFF
        box(10, 10, 18, 46)                       # an `l`, the ascender
        for k in range(4):
            box(40 + k * 20, 22, 48 + k * 20, 46)  # body letters
        box(140, 14, 146, 18)                      # the tittle
        box(140, 22, 146, 46)                      # its stem
        return InkMask(bytes(buf), w, h)

    def test_the_i_arrives_as_ONE_line_with_two_components(self):
        lines = [l for l in page_lines(self._page(), pt=PT, tol=1.0,
                                       glyphs=True) if l["type"] == "glyph"]
        multi = [l for l in lines if l["ink"]["components"] > 1]
        self.assertEqual(len(multi), 1)
        self.assertEqual(multi[0]["ink"]["components"], 2)
        self.assertEqual(len(multi[0]["ink"]["parts"]), 2)

    def test_the_cluster_box_is_the_UNION_of_its_members(self):
        """A glyph's box must cover its tittle, or a consumer cropping
        by it hands the classifier a stem."""
        lines = [l for l in page_lines(self._page(), pt=PT, tol=1.0,
                                       glyphs=True) if l["type"] == "glyph"]
        i_line = next(l for l in lines if l["ink"]["components"] == 2)
        top = i_line["region"]["top_left_y"] / PT
        bottom = top + i_line["region"]["height"] / PT
        self.assertLessEqual(top, 14.0)
        self.assertGreaterEqual(bottom, 46.0)

    def test_a_single_component_glyph_omits_parts(self):
        """`parts` would repeat `region_id` on every line of a page of
        prose; absent rather than trivially present."""
        lines = [l for l in page_lines(self._page(), pt=PT, tol=1.0,
                                       glyphs=True) if l["type"] == "glyph"]
        singles = [l for l in lines if l["ink"]["components"] == 1]
        self.assertTrue(singles)
        for l in singles:
            self.assertNotIn("parts", l["ink"])

    def test_the_axis_comes_from_the_SUMMED_moments(self):
        """A cluster's axis is the axis of the whole glyph, not of
        whichever member happened to come first.

        The fixture gives the upper part a WIDE, flat shape whose own
        axis is horizontal, above a tall stem. The union is tall, so
        summed moments give a vertical axis and the first member's give
        a horizontal one -- the two answers are opposite, which is what
        makes this able to fail. Raw moment sums are integers and
        moments add, so the summed value is exact rather than a proxy.
        """
        w, h = 200, 80
        buf = bytearray(w * h)

        def box(x0, y0, x1, y1):
            for y in range(y0, y1):
                for x in range(x0, x1):
                    buf[y * w + x] = 0xFF
        box(10, 10, 18, 60)                      # ascender, sets the row
        box(60, 14, 96, 20)                      # a WIDE flat mark
        box(74, 26, 82, 60)                      # a tall stem below it
        lines = [l for l in page_lines(InkMask(bytes(buf), w, h), pt=PT,
                                       tol=1.0, glyphs=True)
                 if l["type"] == "glyph"]
        pair = next(l for l in lines if l["ink"]["components"] == 2)
        ax = pair["ink"]["axis"]
        self.assertGreater(abs(ax[1]), abs(ax[0]),
                           "the cluster axis is the wide mark's, not the "
                           "whole glyph's")

    def test_region_id_is_the_LOWEST_member_id(self):
        lines = [l for l in page_lines(self._page(), pt=PT, tol=1.0,
                                       glyphs=True) if l["type"] == "glyph"]
        for l in lines:
            if "parts" in l["ink"]:
                self.assertEqual(l["ink"]["region_id"], min(l["ink"]["parts"]))


if __name__ == "__main__":
    unittest.main()


class T1_12_FreeRules(unittest.TestCase):
    """A4: a booktabs table draws no frame, so its rules are enclosed by
    nothing and `page_lines` attached them to nothing.

    Measured across seven corpus pages before the fix: 33 rules found,
    0 reaching the file.
    """

    @staticmethod
    def _booktabs():
        """Three disjoint horizontal rules with text between them. The
        aspect is taken from a real rule at 400 dpi -- about 250:1 --
        because a 14:1 fixture is correctly refused by `is_rule` and
        would measure zero."""
        w, h = 520, 120
        buf = bytearray(w * h)
        for y0 in (10, 40, 100):
            for y in range(y0, y0 + 2):
                for x in range(10, 510):
                    buf[y * w + x] = 0xFF
        for k in range(6):                        # cell text
            for y in range(60, 76):
                for x in range(30 + k * 70, 44 + k * 70):
                    buf[y * w + x] = 0xFF
        return InkMask(bytes(buf), w, h)

    def test_disjoint_rules_reach_the_page_record(self):
        m = self._booktabs()
        got = free_rules(m, pt=PT)
        self.assertEqual(len(got), 3)
        for r in got:
            self.assertEqual(r["orient"], "h")
            self.assertGreater(r["width_pt"], 0.0)

    def test_they_arrive_in_reading_order(self):
        got = free_rules(self._booktabs(), pt=PT)
        self.assertEqual([r["y0"] for r in got],
                         sorted(r["y0"] for r in got))

    def test_a_rule_INSIDE_A_FRAME_is_not_reported_here(self):
        """The other class, and the reason this is not just "every
        rule". A framed table encloses its rules, `page_lines` already
        attaches them to that table, and reporting them again would
        double-count.

        THE FIXTURE MUST CONTAIN AN ENCLOSED RULE. The first version
        was a bare frame -- one component, no rule region at all -- so
        the containment guard was never reached and deleting it kept
        the test green. A fixture must hold both classes the rule
        separates.
        """
        w, h = 400, 200
        buf = bytearray(w * h)
        for x in range(10, 390):                  # a hollow frame
            for t in range(3):
                buf[(10 + t) * w + x] = 0xFF
                buf[(190 + t) * w + x] = 0xFF
        for y in range(10, 193):
            for t in range(3):
                buf[y * w + 10 + t] = 0xFF
                buf[y * w + 389 + t] = 0xFF
        for y in range(100, 102):                 # a rule INSIDE it,
            for x in range(30, 370):              # not touching the frame
                buf[y * w + x] = 0xFF
        for y in range(150, 152):                 # and a second one
            for x in range(30, 370):
                buf[y * w + x] = 0xFF
        m = InkMask(bytes(buf), w, h)
        from inkdrill.nest import ink_only as _ink
        inks = _ink(m).regions
        self.assertEqual(sum(1 for r in inks if is_rule(r)), 2,
                         "the fixture must contain enclosed rules or it "
                         "cannot exercise the guard")
        self.assertEqual(free_rules(m, pt=PT), [])

    def test_a_page_with_no_rules_omits_the_key(self):
        """Absent rather than an empty array: a page of prose was not
        asked about rules and found to have none, it simply has none."""
        rec = page_record(page=1, width_px=100, height_px=100,
                          dpi=(400.0, 400.0), lines=[], rules=[])
        self.assertNotIn("ink", rec)

    def test_G9_the_documented_key_path_holds_end_to_end(self):
        """`page["ink"]["rules"]` -- the exact path the contract names,
        asserted through the full document rather than on a helper's
        return value. This key shipped undocumented and the consumer,
        contractually correct, never looked for it; the contract now
        names it and this test holds the contract to the file."""
        from inkdrill.emit import lines_json
        m = self._booktabs()
        doc = lines_json([page_record(page=1, width_px=m.width,
                                      height_px=m.height,
                                      dpi=(400.0, 400.0), lines=[],
                                      rules=free_rules(m, pt=PT))],
                         render_dpi=400.0)
        page = doc["pages"][0]
        self.assertEqual(len(page["ink"]["rules"]), 3)
        for r in page["ink"]["rules"]:
            self.assertEqual(set(r), {"x0", "y0", "x1", "y1",
                                      "width_pt", "orient"},
                             "the page-level entry shape must equal the "
                             "per-line one -- one shape, two locations")

    def test_G9_a_rule_reaches_the_file_EXACTLY_once(self):
        """Enclosed -> the line's `ink.rules[]` and NOT the page key;
        free -> the page key and NOT any line. Both directions on one
        fixture: a framed rule plus a free rule outside the frame."""
        w, h = 700, 300
        buf = bytearray(w * h)
        frame(buf, w, 10, 10, 400, 290)
        hline(buf, w, 150, 40, 370, 2)            # enclosed rule
        buf[80 * w + 200] = 0xFF                  # content for the frame
        hline(buf, w, 150, 430, 690, 2)           # free rule, outside
        m = InkMask(bytes(buf), w, h)
        lines = page_lines(m, pt=PT, tol=1.0)
        attached = [r for l in lines
                    for r in l.get("ink", {}).get("rules", [])]
        free = free_rules(m, pt=PT)
        self.assertEqual(len(attached), 1)
        self.assertEqual(len(free), 1)
        # and they are different rules, not one rule twice
        self.assertNotEqual(attached[0]["x0"], free[0]["x0"])

    def test_a_page_with_rules_carries_them(self):
        m = self._booktabs()
        rec = page_record(page=1, width_px=m.width, height_px=m.height,
                          dpi=(400.0, 400.0), lines=[],
                          rules=free_rules(m, pt=PT))
        self.assertEqual(len(rec["ink"]["rules"]), 3)


if __name__ == "__main__":
    unittest.main()


class T1_13_PolarityGuard(unittest.TestCase):
    """The ink-fraction polarity guard (CLI level, function here).

    The failure it prevents is not an exception but a confident wrong
    STRUCTURE: on a chalkboard video frame the dark board becomes one
    component with 250 holes and page_lines emits a table with 121
    cells -- the letter counters as a cell lattice. The cut is 0.5:
    the densest measured legitimate pages are ~8% ink (figure-heavy
    Infineon scans) and every measured inverted frame is 68-100%.
    """

    def test_a_mostly_dark_page_reads_inverted(self):
        from inkdrill.raster import looks_inverted
        dark = InkMask(b"\xff" * 70 + b"\x00" * 30, 10, 10)
        self.assertTrue(looks_inverted(dark))

    def test_a_normal_page_does_NOT(self):
        """Both sides. A dense figure page at 40% must not flip --
        flipping a legitimate page is the same failure in the other
        direction."""
        from inkdrill.raster import looks_inverted
        page = InkMask(b"\xff" * 40 + b"\x00" * 60, 10, 10)
        self.assertFalse(looks_inverted(page))

    def test_the_record_carries_the_polarity_key_only_when_flipped(self):
        """`page["ink"]["polarity"]` -- named, per the contract-gap
        lesson. Present only for light-on-dark; absent for the print
        convention, where it would restate the default on every page."""
        rec = page_record(page=1, width_px=10, height_px=10,
                          dpi=(400.0, 400.0), lines=[],
                          polarity="light-on-dark")
        self.assertEqual(rec["ink"]["polarity"], "light-on-dark")
        rec2 = page_record(page=1, width_px=10, height_px=10,
                           dpi=(400.0, 400.0), lines=[])
        self.assertNotIn("ink", rec2)


class T1_14_CompareCLI(unittest.TestCase):
    """`python3 -m inkdrill compare A.png B.png` (I1): per table row,
    the structural five-tuple of the last two columns of each page.

    Hermetic: pages are built as png16m bytes. The two columns are
    reported SIDE BY SIDE (L/R five-tuples), and `A=B` is the
    scale-invariance assertion between the two input computations --
    asserted in both directions: differing inputs read NO, identical
    inputs read yes.
    """

    @staticmethod
    def _page(shift=0):
        from tests.test_pngio import build_png
        W, H = 260, 160
        g = [[(255, 255, 255)] * W for _ in range(H)]

        def box(x0, y0, x1, y1):
            for y in range(y0, y1):
                for x in range(x0, x1):
                    g[y][x] = (0, 0, 0)
        for x in (0, 64, 128, 192):
            box(x, 0, x + 2, H)
        box(254, 0, 256, H)
        for y in (0, 52, 104):
            box(0, y, 256, y + 2)
        box(0, 156, 256, 158)
        for r in range(3):
            box(20, 14 + r * 52, 40, 30 + r * 52)          # label marks
            y0 = 10 + r * 52
            box(140, y0, 152, y0 + 8)                       # col2 pair
            box(140, y0 + 14, 152, y0 + 22)
            box(204, y0, 216, y0 + 8)                       # col3 pair
            box(204 + shift, y0 + 14, 216 + shift, y0 + 22)
        return build_png(g)

    def _run(self, a, b):
        import io
        from contextlib import redirect_stdout
        from inkdrill.__main__ import main
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["compare", str(a), str(b),
                       "--threshold", "128", "--tol", "6"])
        self.assertEqual(rc, 0)
        return [[c.strip() for c in l.split("|")[1:-1]]
                for l in buf.getvalue().splitlines() if l.startswith("| 1 |")]

    def test_both_columns_reported_and_the_difference_lands_in_A_eq_B(self):
        import tempfile, pathlib as pl
        tmp = pl.Path(tempfile.mkdtemp())
        (tmp / "A.png").write_bytes(self._page(0))
        (tmp / "B.png").write_bytes(self._page(4))
        rows = self._run(tmp / "A.png", tmp / "B.png")
        self.assertEqual(len(rows), 3)
        for cells in rows:
            # L and R are A's per-column five-tuples, side by side
            self.assertEqual(cells[3:8], ["2", "0", "1", "1", "0"], cells)
            self.assertEqual(cells[8:13], ["2", "0", "1", "1", "0"], cells)
            self.assertEqual(cells[13], "NO")     # B's R pair reads offset
            self.assertEqual(cells[14], "yes")

    def test_identical_inputs_agree_so_the_assert_can_pass_too(self):
        import tempfile, pathlib as pl
        tmp = pl.Path(tempfile.mkdtemp())
        (tmp / "A.png").write_bytes(self._page(0))
        rows = self._run(tmp / "A.png", tmp / "A.png")
        for cells in rows:
            self.assertEqual(cells[13], "yes")

    def test_a_broken_rule_does_not_leak_the_neighbour_into_the_cell(self):
        """bh2 report p1: the scan JPEG overprinted a stretch of the
        rule below the header WHITE, so the two cells' background
        holes MERGED and the header cell read 42 components for two
        words. (A blob merely crossing an intact rule does not merge
        holes -- the first version of this fixture proved that by
        killing nothing.) Cells are median-lattice spans now, immune
        to the one merged hole; the row-1 content behind the gap must
        not be counted in row 0."""
        import tempfile, pathlib as pl
        from tests.test_pngio import build_png
        g = [list(r) for r in
             [[(255, 255, 255)] * 260 for _ in range(160)]]

        def box(x0, y0, x1, y1, v=(0, 0, 0)):
            for y in range(y0, y1):
                for x in range(x0, x1):
                    g[y][x] = v
        for x in (0, 64, 128, 192):
            box(x, 0, x + 2, 160)
        box(254, 0, 256, 160)
        for y in (0, 52, 104):
            box(0, y, 256, y + 2)
        box(0, 156, 256, 158)
        for r in range(3):
            box(20, 14 + r * 52, 40, 30 + r * 52)
            box(140, 14 + r * 52, 160, 30 + r * 52)
        box(210, 10, 222, 20)                     # row 0 own content
        box(200, 52, 240, 54, (255, 255, 255))    # rule OVERPRINTED white
        box(210, 70, 222, 95)                     # row 1 content that must
        #                                           NOT leak into row 0
        tmp = pl.Path(tempfile.mkdtemp())
        (tmp / "A.png").write_bytes(build_png(g))
        rows = self._run(tmp / "A.png", tmp / "A.png")
        # row 0's R column: exactly its own 1 blob
        self.assertEqual(rows[0][8], "1", rows[0])

    def test_table_debug_marks_the_fragmented_cell(self):
        """T28: the broken-rule page has exactly one lattice slot with
        no conforming hole (the two merged cells yield ONE hole, which
        backs one slot); --table-debug must mark it MEDIAN-FILLED and
        count it, with every per-cell line carrying components, holes
        and chi."""
        import io, re, tempfile, pathlib as pl
        from contextlib import redirect_stdout, redirect_stderr
        from tests.test_pngio import build_png
        from inkdrill.__main__ import main
        g = [list(r) for r in
             [[(255, 255, 255)] * 260 for _ in range(160)]]

        def box(x0, y0, x1, y1, v=(0, 0, 0)):
            for y in range(y0, y1):
                for x in range(x0, x1):
                    g[y][x] = v
        for x in (0, 64, 128, 192):
            box(x, 0, x + 2, 160)
        box(254, 0, 256, 160)
        for y in (0, 52, 104):
            box(0, y, 256, y + 2)
        box(0, 156, 256, 158)
        for r in range(3):
            box(20, 14 + r * 52, 40, 30 + r * 52)
        box(200, 52, 240, 54, (255, 255, 255))    # rule overprinted
        box(80, 115, 100, 135)                    # ring in cell (2,1):
        box(85, 120, 95, 130, (255, 255, 255))    # 1 comp, 1 hole, chi 0
        box(150, 20, 162, 32)                     # content in col 2 and
        box(210, 120, 222, 132)                   # col 3 -- P15 drops a
        #                                           column with NO glyphs,
        #                                           as a real empty column
        #                                           is indistinguishable
        #                                           from a phantom
        tmp = pl.Path(tempfile.mkdtemp())
        (tmp / "A.png").write_bytes(build_png(g))
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            rc = main(["compare", str(tmp / "A.png"), str(tmp / "A.png"),
                       "--threshold", "128", "--tol", "6",
                       "--table-debug"])
        self.assertEqual(rc, 0)
        text = err.getvalue()
        self.assertIn("lattice 3 rows x 4 cols", text)
        self.assertIn("11 hole-backed, 1 median-filled", text)
        filled = re.findall(r"cell \((\d),(\d)\) MEDIAN-FILLED", text)
        self.assertEqual(len(filled), 2)          # once per input A/B
        self.assertEqual(filled[0][1], "3")       # last column
        self.assertRegex(
            text, r"MEDIAN-FILLED: components \d+ holes \d+ chi -?\d+")
        self.assertIn("cell (2,1) hole-backed: components 1 holes 1 "
                      "chi 0", text)

    def test_a_phantom_sliver_column_is_dropped(self):
        """0803.2924's report: a tall stroke touching both rules split
        a cell's hole and the 1 mm fragment (0.24% of the table span)
        clustered as its own column, shifting "last two columns" onto
        garbage. Columns narrower than 2% of the span are lattice
        artifacts. Fixture proportions are derived from the measured
        page (the first version's sliver was 4.4% of the span and sat
        ABOVE the floor, killing nothing): the stroke leaves an 8 px
        fragment in a ~690 px table, 1.2%."""
        import tempfile, pathlib as pl
        from tests.test_pngio import build_png
        W, H = 700, 160
        g = [list(r) for r in [[(255, 255, 255)] * W for _ in range(H)]]

        def box(x0, y0, x1, y1):
            for y in range(y0, y1):
                for x in range(x0, x1):
                    g[y][x] = (0, 0, 0)
        for x in (0, 164, 328, 492):
            box(x, 0, x + 2, H)
        box(692, 0, 694, H)
        for y in (0, 52, 104):
            box(0, y, W - 6, y + 2)
        box(0, 156, W - 6, 158)
        for r in range(3):
            box(30, 14 + r * 52, 60, 30 + r * 52)
            box(200, 14 + r * 52, 220, 30 + r * 52)
            box(360, 10 + r * 52, 372, 18 + r * 52)
            box(360, 24 + r * 52, 372, 32 + r * 52)    # col2 pair
            box(520, 10 + r * 52, 532, 18 + r * 52)
            box(520, 24 + r * 52, 532, 32 + r * 52)    # col3 pair
        box(682, 0, 684, H)      # stroke in the LAST column: leaves an
        #                          8 px sliver that must not become the
        #                          new last column
        tmp = pl.Path(tempfile.mkdtemp())
        (tmp / "A.png").write_bytes(build_png(g))
        rows = self._run(tmp / "A.png", tmp / "A.png")
        self.assertEqual(len(rows), 3)
        for cells in rows:
            self.assertEqual(cells[3:8], ["2", "0", "1", "1", "0"], cells)
            self.assertEqual(cells[8:13], ["2", "0", "1", "1", "0"], cells)

    def test_a_WIDE_phantom_with_no_content_is_dropped(self):
        """P15: the width floor is a pre-filter, not the decider -- a
        background fragment can be arbitrarily wide (this one is 4.4%
        of the span, above the 2% floor) and only the content test
        catches it: no glyph-sized region centres inside it."""
        import tempfile, pathlib as pl
        from tests.test_pngio import build_png
        g = [list(r) for r in
             [[(255, 255, 255)] * 260 for _ in range(160)]]

        def box(x0, y0, x1, y1):
            for y in range(y0, y1):
                for x in range(x0, x1):
                    g[y][x] = (0, 0, 0)
        for x in (0, 64, 128, 192):
            box(x, 0, x + 2, 160)
        box(254, 0, 256, 160)
        for y in (0, 52, 104):
            box(0, y, 256, y + 2)
        box(0, 156, 256, 158)
        for r in range(3):
            box(20, 14 + r * 52, 40, 30 + r * 52)
            box(140, 10 + r * 52, 152, 18 + r * 52)
            box(140, 24 + r * 52, 152, 32 + r * 52)    # col2 pair
            box(204, 10 + r * 52, 216, 18 + r * 52)
            box(204, 24 + r * 52, 216, 32 + r * 52)    # col3 pair
        box(240, 0, 242, 160)      # stroke in the LAST column: leaves
        #                            an 11 px (4.4%) EMPTY fragment
        tmp = pl.Path(tempfile.mkdtemp())
        (tmp / "A.png").write_bytes(build_png(g))
        rows = self._run(tmp / "A.png", tmp / "A.png")
        self.assertEqual(len(rows), 3)
        for cells in rows:
            self.assertEqual(cells[3:8], ["2", "0", "1", "1", "0"], cells)
            self.assertEqual(cells[8:13], ["2", "0", "1", "1", "0"], cells)

    def test_the_width_prefilter_short_circuits_the_content_test(self):
        """The 2% floor is performance-only under P15 (the content
        test alone decides correctly), so it is asserted by counting:
        a sub-2% fragment must be dropped WITHOUT a content lookup."""
        import tempfile, pathlib as pl
        from unittest import mock
        from tests.test_pngio import build_png
        import inkdrill.__main__ as M
        W, H = 700, 160
        g = [list(r) for r in [[(255, 255, 255)] * W for _ in range(H)]]

        def box(x0, y0, x1, y1):
            for y in range(y0, y1):
                for x in range(x0, x1):
                    g[y][x] = (0, 0, 0)
        for x in (0, 164, 328, 492):
            box(x, 0, x + 2, H)
        box(692, 0, 694, H)
        for y in (0, 52, 104):
            box(0, y, W - 6, y + 2)
        box(0, 156, W - 6, 158)
        for r in range(3):
            box(30, 14 + r * 52, 60, 30 + r * 52)
            box(200, 14 + r * 52, 220, 30 + r * 52)   # col 1 content
            box(360, 10 + r * 52, 372, 18 + r * 52)
            box(360, 24 + r * 52, 372, 32 + r * 52)
            box(520, 10 + r * 52, 532, 18 + r * 52)
            box(520, 24 + r * 52, 532, 32 + r * 52)
        box(682, 0, 684, H)                        # 8 px sliver, 1.2%
        tmp = pl.Path(tempfile.mkdtemp())
        (tmp / "A.png").write_bytes(build_png(g))
        from inkdrill.pngio import read_png, auto_mask
        img = read_png(tmp / "A.png")
        m = auto_mask(img.gray, img.width, img.height, 128)[0]
        with mock.patch.object(M, "_column_has_content",
                               wraps=M._column_has_content) as spy:
            cells = M._table_cells(m, 6.0)
            ncols = max(c for _, c in cells) + 1
        self.assertEqual(ncols, 4)
        # 4 surviving columns tested; the sub-2% sliver never was
        self.assertEqual(spy.call_count, 4)

    def test_a_page_without_a_table_is_an_error_not_a_guess(self):
        import tempfile, pathlib as pl
        from tests.test_pngio import build_png
        from inkdrill.__main__ import main
        tmp = pl.Path(tempfile.mkdtemp())
        blank = build_png([[(255, 255, 255)] * 40 for _ in range(30)])
        (tmp / "A.png").write_bytes(blank)
        (tmp / "B.png").write_bytes(blank)
        rc = main(["compare", str(tmp / "A.png"), str(tmp / "B.png")])
        self.assertEqual(rc, 1)


class S4_1_EvidenceTravelsWithTheType(unittest.TestCase):
    """Every semantic type carries the measured facts that produced
    it. The facts must be TRUE of the branch actually taken -- the
    first version printed the RAW hole count on a diagram, so a region
    with ten glyph counters claimed `holes 10 < 2`."""

    @staticmethod
    def _page():
        """Dimensions derived from the rule they must satisfy, not
        chosen: the cell floor is 3x the median component height, so
        with 14 px content the floor is ~42 px. The page carries all
        three outcomes -- a table whose cells clear the floor, a
        hollow frame with ONE hole, and a grid whose nine holes are
        all BELOW the floor. That last one is what separates the raw
        hole count from the post-floor count in the evidence."""
        from tests.test_pngio import build_png
        g = [[(255, 255, 255)] * 400 for _ in range(440)]

        def box(x0, y0, x1, y1, v=(0, 0, 0)):
            for y in range(y0, y1):
                for x in range(x0, x1):
                    g[y][x] = v
        # 2x2 table: cells 178x88, well above the floor
        box(20, 20, 380, 22); box(20, 198, 380, 200)
        box(20, 20, 22, 200); box(378, 20, 380, 200)
        box(20, 108, 380, 110); box(198, 20, 200, 200)
        for cx, cy in ((60, 50), (240, 50), (60, 140), (240, 140)):
            box(cx, cy, cx + 30, cy + 14)
        # hollow frame, ONE hole, content inside -> diagram
        box(20, 230, 380, 232); box(20, 298, 380, 300)
        box(20, 230, 22, 300); box(378, 230, 380, 300)
        box(80, 255, 110, 269)
        # 3x3 grid of 28x28 cells: nine RAW holes, none of them a cell
        for i in range(4):
            box(20 + i * 30, 330, 22 + i * 30, 420)
        for j in range(4):
            box(20, 330 + j * 30, 112, 332 + j * 30)
        box(28, 338, 44, 352)      # INSIDE a cell: must not touch a rule
        return build_png(g)

    def _lines(self):
        import json, tempfile, pathlib as pl
        from inkdrill.__main__ import main
        tmp = pl.Path(tempfile.mkdtemp())
        (tmp / "p.png").write_bytes(self._page())
        out = tmp / "o.json"
        self.assertEqual(main([str(tmp / "p.png"), "--dpi", "96",
                               "-o", str(out)]), 0)
        d = json.loads(out.read_text())
        pg = d["pages"][0] if "pages" in d else d
        return pg["lines"]

    def test_table_cell_and_diagram_each_name_their_facts(self):
        seen = {}
        for l in self._lines():
            seen.setdefault(l["type"], l)
        for kind in ("table", "simple_cell", "diagram"):
            self.assertIn(kind, seen, f"{kind} never fired")
            why = seen[kind]["ink"]["because"]
            self.assertTrue(why, f"{kind} carries no evidence")
            self.assertTrue(all(isinstance(f, str) for f in why))
        self.assertTrue(any(f.startswith("holes ")
                            for f in seen["table"]["ink"]["because"]))
        self.assertTrue(any(f.startswith("rule_widths_px")
                            for f in seen["table"]["ink"]["because"]))
        self.assertTrue(any(f.startswith("fill ")
                            for f in seen["diagram"]["ink"]["because"]))
        self.assertTrue(any(f.startswith("contains ")
                            for f in seen["simple_cell"]["ink"]["because"]))

    def test_the_diagrams_hole_fact_is_the_one_the_branch_TESTED(self):
        """The diagram branch turns on the holes that pass the CELL
        FLOOR, not the raw count. The grid region has NINE raw holes
        and none that clears the floor, so its evidence must read
        `holes 0 < 2`; printing the raw count there would state
        `holes 9 < 2`, which is false. Asserting on the grid (not the
        hollow frame, where raw and post-floor are both 1) is what
        makes the two counts distinguishable."""
        from inkdrill.emit import lattice_holes
        from inkdrill.nest import nest
        from inkdrill.pngio import auto_mask, read_png
        import tempfile, pathlib as pl
        lines = self._lines()
        dias = [l for l in lines if l["type"] == "diagram"]
        self.assertEqual(len(dias), 2, "both diagram cases must fire")
        grid = min(dias, key=lambda l: l["region"]["width"])
        fact = [f for f in grid["ink"]["because"]
                if f.startswith("holes ")][0]
        self.assertEqual(fact, "holes 0 < 2", grid["ink"]["because"])

        tmp = pl.Path(tempfile.mkdtemp())
        (tmp / "p.png").write_bytes(self._page())
        img = read_png(tmp / "p.png")
        m = auto_mask(img.gray, img.width, img.height, 200)[0]
        n = nest(m)
        kept, raw = lattice_holes(n, grid["ink"]["region_id"], 42.0)
        self.assertEqual((len(kept), raw), (0, 9),
                         "the fixture must separate raw from post-floor")


class S6_1_ColumnsAreDisjoint(unittest.TestCase):
    """A column whose x-span lies INSIDE another's is not a column.

    Measured on 1602.07462 p4 (inline formulas, declared with four
    columns): the raw lattice has eight, four of them nested inside
    col3, because short variable-width cells leave long white tails
    that cluster into extra groups over 56 dense rows. The width
    floor and the content test remove three of the four; the fourth
    holds real ink and survives both, so only containment catches it.
    """

    @staticmethod
    def _page(nested_ink):
        """Built from the REAL mechanism: content touching both rules
        of a cell SPLITS that cell's hole, and the fragments cluster
        as extra columns whose spans lie inside the full column's.
        The first version used a 2 px strip, which the width floor
        removed on its own -- so containment decided nothing and its
        deletion killed no test."""
        from tests.test_pngio import build_png
        W, H = 700, 320
        g = [[(255, 255, 255)] * W for _ in range(H)]

        def box(x0, y0, x1, y1):
            for y in range(y0, y1):
                for x in range(x0, x1):
                    g[y][x] = (0, 0, 0)
        for x in (0, 164, 328, 492):
            box(x, 0, x + 2, H)
        box(692, 0, 694, H)
        for y in (0, 60, 120, 180, 240):
            box(0, y, W - 6, y + 2)
        box(0, 316, W - 6, 318)
        for r in range(5):
            for cx in (30, 200, 360, 520):
                box(cx, 20 + r * 60, cx + 30, 34 + r * 60)
            if r in (1, 3):
                # a bar touching BOTH rules splits this cell's hole in
                # two; each fragment's span sits inside the column's
                box(600, 2 + r * 60, 603, 60 + r * 60)
                if nested_ink:
                    box(620, 20 + r * 60, 650, 34 + r * 60)
        return build_png(g)

    def _cols(self, nested_ink):
        import tempfile, pathlib as pl
        from inkdrill.__main__ import _table_cells
        from inkdrill.pngio import auto_mask, read_png
        tmp = pl.Path(tempfile.mkdtemp())
        (tmp / "p.png").write_bytes(self._page(nested_ink))
        img = read_png(tmp / "p.png")
        m = auto_mask(img.gray, img.width, img.height, 128)[0]
        cells = _table_cells(m, 6.0)
        return max(c for _, c in cells) + 1 if cells else 0

    def test_a_nested_span_is_dropped_even_when_it_holds_ink(self):
        """With ink the content test passes it, so containment is the
        ONLY filter that can drop it -- assert both, or the test
        cannot tell which filter fired."""
        self.assertEqual(self._cols(nested_ink=True), 4)
        self.assertEqual(self._cols(nested_ink=False), 4)


class T1_15_RuleContext(unittest.TestCase):
    """116: what a rule DOES, from the ink around it.

    Dimensions are measured, not chosen. `ink.rules[]` on
    arxiv_1408_0838_p8 at 300 dpi holds rules 20 and 28 px long and
    1 px thick; the Heim scan pages carry rules 160 and 222 px long.
    This fixture uses a 100 px rule 2 px thick, inside that range, on
    a page big enough for a full band above and below.

    All four classes fire in this class and each from its own
    fixture, so no branch of the classification can be deleted
    without a failure -- and `rule_context` itself returns no class,
    which is the point: the caller supplies the presence cut.
    """

    W, H = 400, 260
    RX0, RX1 = 150, 250          # rule spans x 150..249, length 100
    RY0, RY1 = 130, 132          # 2 px thick, so the band is 100 px

    def _page(self, *, above=False, below=False, vertical=False):
        from inkdrill.raster import InkMask
        buf = bytearray(self.W * self.H)

        def box(x0, y0, x1, y1):
            for y in range(max(0, y0), min(self.H, y1)):
                for x in range(max(0, x0), min(self.W, x1)):
                    buf[y * self.W + x] = 0xFF
        if vertical:
            box(200, 80, 202, 180)               # 100 px tall, 2 wide
        else:
            box(self.RX0, self.RY0, self.RX1, self.RY1)
        if above:                                 # inside the 100 px band
            box(180, 60, 220, 120)
        if below:
            box(180, 145, 220, 205)
        return InkMask(bytes(buf), self.W, self.H)

    @staticmethod
    def _ctx(mask):
        from inkdrill.emit import free_rules, rule_context, _pt_per_px
        pt = _pt_per_px((72.0, 72.0))            # 1 px == 1 pt, so the
        rules = free_rules(mask, pt=pt)          # fixture reads directly
        assert len(rules) == 1, f"fixture gave {len(rules)} rules"
        return rule_context(mask, rules[0], pt=pt), rules[0]

    def test_all_four_classes_fire(self):
        """Each class from its own fixture. A classification whose
        fourth branch never occurs is the defect this project has
        recorded five times."""
        seen = {}
        for above, below, name in ((True, True, "fraction"),
                                   (True, False, "overline"),
                                   (False, True, "underline"),
                                   (False, False, "separator")):
            c, _ = self._ctx(self._page(above=above, below=below))
            cut = 0.01
            seen[name] = (c["above"] > cut, c["below"] > cut)
        self.assertEqual(seen["fraction"], (True, True))
        self.assertEqual(seen["overline"], (True, False))
        self.assertEqual(seen["underline"], (False, True))
        self.assertEqual(seen["separator"], (False, False))

    def test_the_band_scales_with_the_rule_not_with_the_page(self):
        """A fraction bar under a 12 pt numerator and a booktabs rule
        spanning a table must get the same test. Doubling every
        dimension must leave the coverages unchanged; a band fixed in
        pixels would not."""
        from inkdrill.emit import free_rules, rule_context, _pt_per_px
        from inkdrill.raster import InkMask

        def page(s):
            W, H = 400 * s, 260 * s
            buf = bytearray(W * H)
            for x0, y0, x1, y1 in ((150, 130, 250, 132),
                                   (180, 60, 220, 120),
                                   (180, 145, 220, 205)):
                for y in range(y0 * s, y1 * s):
                    for x in range(x0 * s, x1 * s):
                        buf[y * W + x] = 0xFF
            return InkMask(bytes(buf), W, H)
        pt = _pt_per_px((72.0, 72.0))
        out = []
        for s in (1, 2):
            m = page(s)
            r = free_rules(m, pt=pt)[0]
            c = rule_context(m, r, pt=pt)
            out.append((round(c["above"], 3), round(c["below"], 3)))
        self.assertEqual(out[0], out[1])
        self.assertGreater(out[0][0], 0.0)      # and it is not zero
                                                # on both, which would
                                                # make equality vacuous

    def test_reach_changes_the_answer_and_is_not_inert(self):
        """`reach` is load-bearing: on the real page the three 20 px
        rules read `separator` at reach 1 and `overline` at reach 4,
        because a 4x band reaches the previous text line. Asserted
        here so the argument cannot be dropped."""
        from inkdrill.emit import free_rules, rule_context, _pt_per_px
        from inkdrill.raster import InkMask
        buf = bytearray(self.W * self.H)
        for y in range(self.RY0, self.RY1):
            for x in range(self.RX0, self.RX1):
                buf[y * self.W + x] = 0xFF
        for y in range(10, 25):                 # far above: outside a
            for x in range(180, 220):           # 100 px band, inside 400
                buf[y * self.W + x] = 0xFF
        m = InkMask(bytes(buf), self.W, self.H)
        pt = _pt_per_px((72.0, 72.0))
        r = free_rules(m, pt=pt)[0]
        self.assertEqual(rule_context(m, r, pt=pt, reach=1.0)["above"],
                         0.0)
        self.assertGreater(rule_context(m, r, pt=pt, reach=4.0)["above"],
                           0.0)

    def test_a_vertical_rule_is_flagged_not_reinterpreted(self):
        """The bands are defined off the long axis; for a vertical
        rule they would lie beside it, not above and below. It must
        say so rather than return a number that reads like an
        answer."""
        c, _ = self._ctx(self._page(vertical=True))
        self.assertTrue(c["vertical"])
        self.assertEqual((c["above"], c["below"]), (0.0, 0.0))

    def test_a_band_clipped_by_the_page_edge_reports_its_real_height(self):
        """A rule near the top has no room for a full band. The
        coverage must be over the band that EXISTS, not over the one
        that was asked for, or a rule at the margin reads as empty."""
        from inkdrill.emit import free_rules, rule_context, _pt_per_px
        from inkdrill.raster import InkMask
        buf = bytearray(self.W * self.H)
        for y in range(10, 12):                 # rule 10 px from the top
            for x in range(self.RX0, self.RX1):
                buf[y * self.W + x] = 0xFF
        for y in range(0, 9):                   # ink filling that gap
            for x in range(self.RX0, self.RX1):
                buf[y * self.W + x] = 0xFF
        m = InkMask(bytes(buf), self.W, self.H)
        pt = _pt_per_px((72.0, 72.0))
        c = rule_context(m, free_rules(m, pt=pt)[0], pt=pt)
        self.assertEqual(c["band_above_px"], 10)   # not 100
        self.assertAlmostEqual(c["above"], 0.9, places=2)


class T1_16_CompareRefusesAnUnusablePage(unittest.TestCase):
    """`compare` on a page it cannot read must REFUSE, by name.

    Two failure modes, reported from pages 9 and 8 of
    1605.05775/report.pdf -- the "Unrecovered image regions" pages,
    which every document with unrecovered regions has, so this is the
    common case in that corpus and not an edge.

      EMPTY LATTICE   `_table_cells` has two empty answers: None ("no
                      ink region has >= 2 holes") and an empty dict
                      ("a region was found, no cell survived the
                      filters"). Only the first was guarded, so the
                      second reached `max()` on an empty generator and
                      raised ValueError four frames down.
      ONE COLUMN      worse, because it did NOT raise. `--cols`
                      defaults to `(nc - 2, nc - 1)`, which at nc == 1
                      is `(-1, 0)`: a negative index wrapping to the
                      last column, compared against the first. It
                      emitted a full table whose left five-tuple was
                      all zeroes and whose `A=B` said NO on every row.
                      A confident, complete-looking, meaningless
                      answer, which is worse than a crash.

    Both sides asserted: a two-column lattice must still WORK, or the
    guard could be made unconditional and the suite would not notice.

    Grid dimensions are measured, not chosen: 1605.05775 p1 at 300 dpi
    is a 6-column lattice whose rows run about 100 px.
    """

    @staticmethod
    def _grid(cols, rows=3, cw=140, ch=100, t=4):
        from tests.test_pngio import build_png
        W = cols * cw + t
        H = rows * ch + t
        g = [[(255, 255, 255)] * W for _ in range(H)]

        def box(x0, y0, x1, y1):
            for y in range(y0, min(H, y1)):
                for x in range(x0, min(W, x1)):
                    g[y][x] = (0, 0, 0)
        for i in range(cols + 1):
            box(i * cw, 0, i * cw + t, H)
        for j in range(rows + 1):
            box(0, j * ch, W, j * ch + t)
        for r in range(rows):                      # ink inside each cell
            for cidx in range(cols):
                x = cidx * cw + 30
                y = r * ch + 30
                box(x, y, x + 20, y + 20)
        return build_png(g)

    def _run(self, png_bytes):
        import io, tempfile, pathlib as pl
        from contextlib import redirect_stdout, redirect_stderr
        from inkdrill.__main__ import main
        tmp = pl.Path(tempfile.mkdtemp())
        (tmp / "A.png").write_bytes(png_bytes)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = main(["compare", str(tmp / "A.png"), str(tmp / "A.png"),
                       "--threshold", "128", "--tol", "6"])
        return rc, out.getvalue(), err.getvalue()

    def test_a_two_column_lattice_is_accepted(self):
        rc, out, err = self._run(self._grid(2))
        self.assertEqual(rc, 0, err)
        self.assertIn("| page | line |", out)

    def test_a_one_column_lattice_is_refused_not_answered(self):
        rc, out, err = self._run(self._grid(1))
        self.assertEqual(rc, 1)
        self.assertIn("column", err)
        self.assertNotIn("| page | line |", out)

    def test_a_blank_page_is_refused_by_name_not_by_ValueError(self):
        from tests.test_pngio import build_png
        blank = build_png([[(255, 255, 255)] * 200 for _ in range(200)])
        rc, out, err = self._run(blank)
        self.assertEqual(rc, 1)
        self.assertIn("no cells", err)
        self.assertNotIn("| page | line |", out)


class T1_17_BothCellsEmptyIsNotClean(unittest.TestCase):
    """A row with no ink in either compared cell scores distance 0 and
    reads CLEAN -- the best possible result from a comparison that did
    not happen.

    Reported by pdfdrill-github-io-a2 across seven documents: exactly
    one such row per page, always LAST on its page, never on the final
    page. Reproduced here on 1605.05775/report.pdf, where it is a real
    lattice row and not a phantom -- a longtable page-break
    CONTINUATION FOOTER, 49 px tall at 300 dpi, which clears the 40 px
    sliver floor and survives every filter.

    MARKED, NEVER DROPPED. Callers pair rows to identifiers by
    position, so removing one shifts every row after it. The same
    defect produced 501 phantom changes in a peer's output and 320
    mislabelled rows in this project's overrun harness. And an empty
    pair is not always a footer -- an equation whose render AND scan
    are both missing looks identical and DOES own an identifier, so
    dropping it would mis-pair. The row keeps its slot and says what
    it is.

    Both sides asserted: a row with ink in either cell must NOT be
    marked, or the column would be a constant.
    """

    @staticmethod
    def _page(*, last_row_empty):
        """A 3-row, 3-column grid. Row heights come from the measured
        report: 1605.05775 at 300 dpi has body rows of 100-800 px and
        a 49 px continuation footer."""
        from tests.test_pngio import build_png
        cw, t = 140, 4
        heights = [100, 100, 49]
        W = 3 * cw + t
        H = sum(heights) + t
        g = [[(255, 255, 255)] * W for _ in range(H)]

        def box(x0, y0, x1, y1):
            for y in range(y0, min(H, y1)):
                for x in range(x0, min(W, x1)):
                    g[y][x] = (0, 0, 0)
        for i in range(4):
            box(i * cw, 0, i * cw + t, H)
        y = 0
        tops = []
        for h in heights:
            box(0, y, W, y + t)
            tops.append(y)
            y += h
        box(0, y, W, y + t)
        for r, y0 in enumerate(tops):
            if r == len(tops) - 1 and last_row_empty:
                continue
            for cidx in range(3):
                box(cidx * cw + 30, y0 + 20, cidx * cw + 50, y0 + 40)
        return build_png(g)

    def _rows(self, png_bytes):
        import io, tempfile, pathlib as pl
        from contextlib import redirect_stdout, redirect_stderr
        from inkdrill.__main__ import main
        tmp = pl.Path(tempfile.mkdtemp())
        (tmp / "A.png").write_bytes(png_bytes)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = main(["compare", str(tmp / "A.png"), str(tmp / "A.png"),
                       "--threshold", "128", "--tol", "6"])
        self.assertEqual(rc, 0, err.getvalue())
        rows = [[c.strip() for c in l.split("|")[1:-1]]
                for l in out.getvalue().splitlines()
                if l.startswith("| 1 |")]
        return rows, err.getvalue()

    def test_an_empty_last_row_is_marked_and_keeps_its_slot(self):
        rows, err = self._rows(self._page(last_row_empty=True))
        self.assertEqual(rows[-1][-1], "BOTH-EMPTY")
        # its five-tuples really are the all-zero pair that reads clean
        self.assertEqual(rows[-1][3:13], ["0"] * 10)
        # and it was NOT removed: the row count is unchanged
        self.assertEqual(len(rows), 3)
        self.assertIn("NO INK", err)

    def test_a_row_with_ink_is_not_marked(self):
        rows, err = self._rows(self._page(last_row_empty=False))
        self.assertEqual([r[-1] for r in rows], ["", "", ""])
        self.assertNotIn("NO INK", err)


class T1_18_RowCoverageCatchesAMissingRow(unittest.TestCase):
    """A row whose content touches the rules on both sides stops being
    an enclosed hole and is not detected at all.

    Reported by pdfdrill-github-io-a2 from 0902.0431 pages 13 and 19 --
    a single oversized aligned block beside a 113 mm crop, where the
    lattice finds ONLY the 49 px header and covers 1.5% of a 3,296 px
    table region. It is not a height threshold, which was the offered
    hypothesis: it is ENCLOSURE. The cell background escapes to the
    outside region, so there is no hole to cluster into a row.

    Worse than a crash and worse than a false clean: a row missing
    MID-SEQUENCE does not truncate the pairing, it SHIFTS it, so every
    row after lands on the following equation. It shipped, and an
    audit misattributed the displacement to a different defect before
    measurement separated them.

    THE FLOOR IS A SEPARATION, NOT A TUNED CONSTANT. Over 50 corpus
    pages the minimum coverage is 0.891 and the median 0.986, against
    0.015 on the failing page -- two orders of magnitude, so any value
    in the gap is safe and 0.5 is free.

    Both sides asserted: a fully-detected lattice must still pass.
    """

    @staticmethod
    def _page(*, bridge):
        """A 3-row grid. With `bridge`, the middle row's content spans
        rule to rule, so its background is not enclosed and the row
        cannot be found. Row heights are the measured ones: 0902.0431
        at 300 dpi has a 49 px header and body rows of 400-1,400 px,
        scaled down here by 10."""
        from tests.test_pngio import build_png
        cw, t = 140, 4
        heights = [49, 140, 49]
        W = 3 * cw + t
        H = sum(heights) + t
        g = [[(255, 255, 255)] * W for _ in range(H)]

        def box(x0, y0, x1, y1):
            for y in range(max(0, y0), min(H, y1)):
                for x in range(max(0, x0), min(W, x1)):
                    g[y][x] = (0, 0, 0)
        for i in range(4):
            box(i * cw, 0, i * cw + t, H)
        y, tops = 0, []
        for h in heights:
            box(0, y, W, y + t)
            tops.append(y)
            y += h
        box(0, y, W, y + t)
        for r, y0 in enumerate(tops):
            for cidx in range(3):
                box(cidx * cw + 30, y0 + 12, cidx * cw + 50, y0 + 32)
        if bridge:
            # the middle row's ink reaches BOTH horizontal rules, so
            # its background joins the outside and stops being a hole
            mid = tops[1]
            for cidx in range(3):
                box(cidx * cw + t, mid, cidx * cw + cw, mid + heights[1] + t)
        return build_png(g)

    def _run(self, png_bytes):
        import io, tempfile, pathlib as pl
        from contextlib import redirect_stdout, redirect_stderr
        from inkdrill.__main__ import main
        tmp = pl.Path(tempfile.mkdtemp())
        (tmp / "A.png").write_bytes(png_bytes)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = main(["compare", str(tmp / "A.png"), str(tmp / "A.png"),
                       "--threshold", "128", "--tol", "6"])
        return rc, out.getvalue(), err.getvalue()

    def test_a_fully_detected_lattice_passes_and_reports_its_shape(self):
        rc, out, err = self._run(self._page(bridge=False))
        self.assertEqual(rc, 0, err)
        self.assertIn("row coverage", err)
        self.assertIn("rows x 3 cols", err)

    def test_a_row_that_cannot_be_enclosed_is_refused(self):
        rc, out, err = self._run(self._page(bridge=True))
        self.assertEqual(rc, 1)
        self.assertIn("rows are MISSING", err)
        self.assertNotIn("| page | line |", out)


class T1_19_CrossingRulesSplit(unittest.TestCase):
    """201: split a fused rule crossing into its two rules, and refuse
    a delimiter.

    A `{c|c}` array's column rule and its horizontal rule intersect,
    so 8-connectivity merges them into one component -- fill 0.02 to
    0.07, aspect near 1 -- and `is_rule` refuses it on both counts.
    196 and 200 measured six such rules in one document, none found.

    THE DISCRIMINATOR IS MEASURED. Both a crossing and a BRACKET are
    tall components with a full-height vertical band, so the vertical
    band alone cannot separate them:

        delimiter   full-width horizontal bands at BOTH ENDS of the
                    stem -- measured at normalised 0.005 and 0.985
        crossing    ONE, interior -- measured at 0.50 (2x2 arrays)
                    and 0.743 (the 4x4)

    Fixture dimensions are the measured ones: the real crossings are
    82x103, 103x103 and 548x202 px with 3 px arms, and the brackets
    19-20 x 200 px.

    All three guards are asserted, because each closed a real false
    positive found on real ink:

      band thickness  a SOLID 28x3 bar has one full vertical band and
                      one full horizontal band whose centre is at
                      0.5 -- arithmetically identical to a crossing.
                      Ten components split before this existed,
                      including three equals signs.
      arm aspect      a 5x5 dot with a 1 px column and a 1 px row
                      satisfies every band test at a 5 px extent.
      end position    the bracket itself.
    """

    @staticmethod
    def _mask(kind, w=200, h=100, t=3):
        from inkdrill.raster import InkMask
        buf = bytearray(w * h)

        def box(x0, y0, x1, y1):
            for y in range(max(0, y0), min(h, y1)):
                for x in range(max(0, x0), min(w, x1)):
                    buf[y * w + x] = 0xFF
        if kind == "cross":                      # rule crossing at 0.75
            box(int(0.75 * w), 0, int(0.75 * w) + t, h)
            box(0, int(0.75 * h), w, int(0.75 * h) + t)
        elif kind == "cross_mid":
            box(w // 2, 0, w // 2 + t, h)
            box(0, h // 2, w, h // 2 + t)
        elif kind == "bracket":                  # stem with two serifs
            box(0, 0, t, h)
            box(0, 0, w, t)
            box(0, h - t, w, h)
        elif kind == "solid":
            box(0, 0, w, h)
        elif kind == "stem":                     # a bare vertical rule
            box(w // 2, 0, w // 2 + t, h)
        return InkMask(bytes(buf), w, h)

    def _split(self, kind, **kw):
        from inkdrill.emit import crossing_rules
        from inkdrill.nest import ink_only
        m = self._mask(kind, **kw)
        regs = list(ink_only(m).regions)
        self.assertEqual(len(regs), 1, f"{kind} is not one component")
        return crossing_rules(m, regs[0])

    def test_a_crossing_splits_into_one_vertical_and_one_horizontal(self):
        for kind in ("cross", "cross_mid"):
            out = self._split(kind)
            self.assertEqual(len(out), 2, kind)
            self.assertEqual(sorted(o["orientation"] for o in out),
                             ["horizontal", "vertical"], kind)

    def test_the_split_puts_the_rules_where_the_grid_says(self):
        """0.75 of the extent is the boundary after column 3 of 4 --
        the measured position on the 4x4 was 0.752 and 0.743."""
        out = self._split("cross", w=200, h=100)
        v = next(o for o in out if o["orientation"] == "vertical")
        hh = next(o for o in out if o["orientation"] == "horizontal")
        self.assertAlmostEqual((v["x0"] + v["x1"]) / 2 / 199, 0.75,
                               delta=0.02)
        self.assertAlmostEqual((hh["y0"] + hh["y1"]) / 2 / 99, 0.75,
                               delta=0.02)

    def test_a_bracket_is_refused(self):
        # 40 px wide, not 20: at 20 the serifs are too SHORT to be
        # rules and the arm-aspect guard refuses it first, so the
        # end-position guard would never be the thing under test. A
        # fixture that two guards both reject cannot show which one
        # works.
        self.assertEqual(self._split("bracket", w=40, h=200, t=3), [])

    def test_a_solid_block_is_refused(self):
        """Every column full-height, every row full-width, single band
        centred at 0.5. The band-thickness guard is the only thing
        that separates it from a crossing."""
        self.assertEqual(self._split("solid", w=28, h=3), [])
        self.assertEqual(self._split("solid", w=60, h=60), [])

    def test_a_tiny_dot_is_refused(self):
        """5x5 with a 1 px arm passes every band test; the arm-aspect
        floor is what refuses it."""
        from inkdrill.emit import crossing_rules
        from inkdrill.nest import ink_only
        from inkdrill.raster import InkMask
        w = h = 5
        buf = bytearray(w * h)
        for y in range(h):
            buf[y * w + 2] = 0xFF
        for x in range(w):
            buf[2 * w + x] = 0xFF
        m = InkMask(bytes(buf), w, h)
        r = list(ink_only(m).regions)[0]
        self.assertEqual(crossing_rules(m, r), [])

    def test_a_bare_stem_with_no_crossbar_is_refused(self):
        self.assertEqual(self._split("stem", w=40, h=200), [])

    def test_the_guards_are_not_inert(self):
        """Each guard relaxed in turn must admit what it was added to
        refuse -- otherwise it could be deleted and nothing would
        fail."""
        from inkdrill.emit import crossing_rules
        from inkdrill.nest import ink_only
        solid = self._mask("solid", w=60, h=60)
        rs = list(ink_only(solid).regions)[0]
        self.assertEqual(crossing_rules(solid, rs), [])
        self.assertTrue(crossing_rules(solid, rs, band=1.0,
                                       min_aspect=1.0))
        brk = self._mask("bracket", w=40, h=200, t=3)
        rb = list(ink_only(brk).regions)[0]
        self.assertEqual(crossing_rules(brk, rb), [])
        self.assertTrue(crossing_rules(brk, rb, end=0.0))

    def test_each_guard_is_isolated_by_a_fixture_only_it_refuses(self):
        """A mutation sweep found six of seven guards surviving --
        not because they are dead but because the earlier fixtures are
        refused by TWO guards at once, so removing either changes
        nothing. Each case below is refused by exactly one, so every
        guard now has a fixture that fails when it alone is deleted.
        """
        from inkdrill.emit import crossing_rules
        from inkdrill.nest import ink_only
        from inkdrill.raster import InkMask

        def cross(w, h, vt, ht):
            """A crossing with independently chosen arm thicknesses."""
            buf = bytearray(w * h)
            vx = (w - vt) // 2
            hy = (h - ht) // 2
            for y in range(h):
                for x in range(vx, vx + vt):
                    buf[y * w + x] = 0xFF
            for y in range(hy, hy + ht):
                for x in range(w):
                    buf[y * w + x] = 0xFF
            m = InkMask(bytes(buf), w, h)
            return m, list(ink_only(m).regions)[0]

        # the vertical band is too THICK for its width: 20 of 40 px
        m, r = cross(40, 400, 20, 3)
        self.assertEqual(crossing_rules(m, r), [])
        self.assertTrue(crossing_rules(m, r, band=1.0))

        # the horizontal band is too THICK for its height: 20 of 40 px
        m, r = cross(400, 40, 3, 20)
        self.assertEqual(crossing_rules(m, r), [])
        self.assertTrue(crossing_rules(m, r, band=1.0))

        # the vertical ARM is too short to be a rule: 20 px over a
        # 3 px stem is aspect 6.7
        m, r = cross(400, 20, 3, 3)
        self.assertEqual(crossing_rules(m, r), [])
        self.assertTrue(crossing_rules(m, r, min_aspect=1.0))

        # the horizontal ARM is too short: 20 px over a 3 px bar
        m, r = cross(20, 400, 3, 3)
        self.assertEqual(crossing_rules(m, r), [])
        self.assertTrue(crossing_rules(m, r, min_aspect=1.0))

        # TWO full-height vertical bands -- an H, or a `||` double
        # rule. One crossbar cannot be attributed to one stem, so the
        # component is refused rather than split on whichever stem
        # happens to come first. Without the single-band guard this
        # emits a confident wrong answer, which is why the guard is
        # not merely defensive.
        w, h, t = 200, 300, 3
        buf = bytearray(w * h)
        for y in range(h):
            for x in list(range(20, 20 + t)) + list(range(160, 160 + t)):
                buf[y * w + x] = 0xFF
        for y in range(h // 2, h // 2 + t):
            for x in range(20, 163):
                buf[y * w + x] = 0xFF
        m = InkMask(bytes(buf), w, h)
        r = list(ink_only(m).regions)[0]
        self.assertEqual(crossing_rules(m, r), [])


class T1_20_DelimiterAndOutsideClasses(unittest.TestCase):
    """203/209: `is_delimiter`, and that all three outside-classes are
    REACHABLE.

    Class 3 -- a delimited expression with nothing outside the pair --
    is EMPTY on all five books, 0 of 156 delimited equations. A zero
    in a class a measurement was built to compare against is the first
    thing to check, so the branch is exercised here on a synthetic
    region containing only `[ ... ]`. It fires. The corpus zero is
    therefore a fact about display equations, not an unreachable
    branch.

    `is_delimiter` and `crossing_rules` read the SAME band structure
    the opposite way -- a crossing has an interior horizontal band, a
    delimiter has none -- so neither can claim a component the other
    claims. Asserted, because that disjointness is what makes them
    safe to run over one page.
    """

    @staticmethod
    def _region(*, left, right, below):
        """A bracketed 2x2 matrix, with content optionally placed to
        the left of the pair, to its right, or below it. Dimensions
        follow the measured page: 200's brackets are 19-20 x 200 px
        with 3 px strokes."""
        from inkdrill.raster import InkMask
        W, H, t = 340, 240, 3
        buf = bytearray(W * H)

        def box(x0, y0, x1, y1):
            for y in range(max(0, y0), min(H, y1)):
                for x in range(max(0, x0), min(W, x1)):
                    buf[y * W + x] = 0xFF
        # `[` : stem at x=60 with serifs running RIGHT to x=95
        box(60, 20, 60 + t, 180)
        box(60, 20, 95, 23)
        box(60, 177, 95, 180)
        # `]` : stem at x=250 with serifs running LEFT to x=215
        box(250, 20, 250 + t, 180)
        box(215, 20, 253, 23)
        box(215, 177, 253, 180)
        for r in range(2):
            for c in range(2):
                box(100 + c * 70, 50 + r * 70, 120 + c * 70, 70 + r * 70)
        if left:
            box(10, 90, 40, 120)
        if right:
            box(280, 90, 320, 120)
        if below:
            box(80, 200, 200, 225)
        return InkMask(bytes(buf), W, H)

    def _classify(self, **kw):
        from inkdrill.emit import is_delimiter
        from inkdrill.nest import ink_only
        m = self._region(**kw)
        regs = list(ink_only(m).regions)
        delims = sorted((r for r in regs if is_delimiter(m, r)),
                        key=lambda r: r.x0)
        self.assertGreaterEqual(len(delims), 2, "brackets not detected")
        L, R = delims[0], delims[-1]
        bottom = max(L.y1, R.y1)
        lhs = [r for r in regs if r.x1 < L.x0]
        out = [r for r in regs if r.x0 > R.x1 or r.y0 > bottom]
        return 1 if out else (2 if lhs else 3), len(lhs), len(out)

    def test_all_three_classes_fire(self):
        self.assertEqual(self._classify(left=False, right=True,
                                        below=False)[0], 1)
        self.assertEqual(self._classify(left=False, right=False,
                                        below=True)[0], 1)
        self.assertEqual(self._classify(left=True, right=False,
                                        below=False)[0], 2)
        self.assertEqual(self._classify(left=False, right=False,
                                        below=False)[0], 3)

    def test_a_left_hand_side_alone_is_not_a_label(self):
        """The defect this split exists for: including `r.x1 < L.x0`
        put every `lhs = [...]` in class 1 and left class 3 with zero
        members across 2,135 equations."""
        cls, lhs, out = self._classify(left=True, right=False,
                                       below=False)
        self.assertEqual(cls, 2)
        self.assertGreater(lhs, 0)
        self.assertEqual(out, 0)

    def test_a_delimiter_and_a_crossing_are_never_the_same_component(self):
        from inkdrill.emit import crossing_rules, is_delimiter
        from inkdrill.nest import ink_only
        m = self._region(left=False, right=False, below=False)
        for r in ink_only(m).regions:
            self.assertFalse(is_delimiter(m, r) and crossing_rules(m, r),
                             "a component claimed by both")


class T1_21_TheTableIsTheLargestRegionNotTheHolliest(unittest.TestCase):
    """91: which ink region `_table_cells` takes as the table.

    "The one with the most holes" is wrong on any table whose cells
    contain PICTURES. On page 3 of pdfdrill's region report the frame
    has 74 holes and an embedded figure has 85, so the figure won and
    the lattice read a 4x6 grid of its internal contours -- x-spans
    154 px wide on a 4961 px page. `compare` then measured four rows
    of a diagram as table rows.

    A frame is the region its cells are holes IN, so it CONTAINS
    every competing candidate, and largest bounding box is that
    property cheaply. On the equation table both rules agree, which
    is why the old one survived until a table with pictures arrived.

    Both rules are asserted. `select` stays a parameter because
    comparing them on identically filtered output is the only way to
    show the change moves nothing else -- a first attempt compared
    raw `cell_grid` under one rule against filtered `_table_cells`
    under the other and reported 47 of 50 pages changed, which was
    the filters, not the selection.
    """

    @staticmethod
    def _page():
        """A 2x3 table frame, with a many-holed figure inside one
        cell. Dimensions scaled from the real page: the frame is
        4611x2662 there and the figure 640x311, so the figure is
        about an eighth of the frame's width."""
        from tests.test_pngio import build_png
        W, H, t = 600, 300, 3
        g = [[(255, 255, 255)] * W for _ in range(H)]

        def box(x0, y0, x1, y1):
            for y in range(max(0, y0), min(H, y1)):
                for x in range(max(0, x0), min(W, x1)):
                    g[y][x] = (0, 0, 0)
        for i in range(4):                       # 3 columns
            box(20 + i * 180, 20, 20 + i * 180 + t, 280)
        for j in range(3):                       # 2 rows
            box(20, 20 + j * 130, 560, 20 + j * 130 + t)
        # EVERY CELL NEEDS CONTENT. The lattice's column filters
        # require a glyph-sized region inside a column's span (P15's
        # content test), so a grid of empty cells collapses to one
        # column and the fixture would test nothing.
        for cx in range(3):
            for ry in range(2):
                bx = 20 + cx * 180 + 40
                by = 20 + ry * 130 + 40
                box(bx, by, bx + 24, by + 24)
        # A FIGURE IN THE LAST CELL, drawn as one CONNECTED mesh so
        # it is a single region carrying many holes. Separate closed
        # boxes would be 48 regions with one hole each and the frame
        # would still win on holes -- the fixture has to reproduce
        # the real page, where ONE figure out-holes the frame.
        fx, fy, cw, ch = 390, 160, 20, 18
        for c in range(9):
            box(fx + c * cw, fy, fx + c * cw + 2, fy + 6 * ch + 2)
        for r in range(7):
            box(fx, fy + r * ch, fx + 8 * cw + 2, fy + r * ch + 2)
        return build_png(g)

    def _cols(self, select):
        import tempfile, pathlib as pl
        from inkdrill.pngio import read_png, auto_mask
        from inkdrill.__main__ import _table_cells
        d = pl.Path(tempfile.mkdtemp())
        (d / "p.png").write_bytes(self._page())
        img = read_png(d / "p.png")
        m, _ = auto_mask(img.gray, img.width, img.height, 128)
        cells = _table_cells(m, 6.0, select=select)
        if not cells:
            return 0, 0
        return (max(r for r, _ in cells) + 1,
                max(c for _, c in cells) + 1)

    def test_the_area_rule_finds_the_frame(self):
        rows, cols = self._cols("area")
        self.assertEqual(cols, 3, f"got {rows}x{cols}")
        self.assertEqual(rows, 2)

    def test_the_holes_rule_finds_the_figure_instead(self):
        """The defect, pinned. If this ever agrees with the area rule
        the fixture has stopped containing the thing it exists for."""
        rows, cols = self._cols("holes")
        self.assertNotEqual((rows, cols), (2, 3),
                            "the fixture no longer separates the rules")

    def test_an_unknown_select_raises(self):
        """On a page that HAS candidates -- a blank mask returns None
        before the selection is reached, so it would pass whatever
        the guard did."""
        import tempfile, pathlib as pl
        from inkdrill.pngio import read_png, auto_mask
        from inkdrill.__main__ import _table_cells
        d = pl.Path(tempfile.mkdtemp())
        (d / "p.png").write_bytes(self._page())
        img = read_png(d / "p.png")
        m, _ = auto_mask(img.gray, img.width, img.height, 128)
        self.assertTrue(_table_cells(m, 6.0, select="area"))
        with self.assertRaises(ValueError):
            _table_cells(m, 6.0, select="biggest")
