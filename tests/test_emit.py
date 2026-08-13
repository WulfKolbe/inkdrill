"""T1: inkdrill findings as a MathPix-shaped `lines.json`.

Hermetic. Masks are built from ASCII pictures, so a table fixture is
readable as a table in the source.
"""

import json
import unittest

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
        self.assertEqual(d["ocr"], {"units": "pt", "render_dpi": 400.0})
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
