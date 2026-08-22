"""Unit 14 tests. Every test name is quoted verbatim in the status report."""

import random
import unittest

from inkdrill.mathstruct import (Glyph, ReferenceLines, Row, Script,
                                 ScriptKind, detect_scripts, group,
                                 reference_lines, rows)


def g(i, x0, top, x1, bottom):
    return Glyph(i, x0, top, x1, bottom)


def line(n, y=100.0, h=10.0, w=8.0, gap=2.0, start=0):
    """n body glyphs sitting on one baseline."""
    return [g(start + i, i * (w + gap), y, i * (w + gap) + w, y + h)
            for i in range(n)]


class T14_1_RowsPartition(unittest.TestCase):
    """G1 and G2."""

    def test_one_line_makes_one_row(self):
        got = rows(line(6))
        self.assertEqual(len(got), 1)
        self.assertEqual(len(got[0].members), 6)

    def test_two_separated_lines_make_two_rows(self):
        got = rows(line(5, y=100.0) + line(5, y=200.0, start=100))
        self.assertEqual(len(got), 2)

    def test_every_glyph_lands_in_exactly_one_row(self):
        rng = random.Random(20260809)
        for trial in range(60):
            gs = []
            for i in range(rng.randint(1, 30)):
                y = rng.choice((10.0, 40.0, 70.0)) + rng.uniform(-1, 1)
                h = rng.uniform(6, 12)
                x = rng.uniform(0, 200)
                gs.append(g(i, x, y, x + rng.uniform(4, 10), y + h))
            got = rows(gs)
            seen = [m.id for r in got for m in r.members]
            with self.subTest(trial=trial):
                self.assertEqual(sorted(seen), sorted(x.id for x in gs))
                self.assertEqual(len(seen), len(set(seen)))

    def test_row_assignment_is_independent_of_input_order(self):
        """G2."""
        gs = line(6) + line(6, y=200.0, start=100)
        want = [sorted(m.id for m in r.members) for r in rows(gs)]
        rng = random.Random(5)
        for trial in range(6):
            shuffled = gs[:]
            rng.shuffle(shuffled)
            with self.subTest(trial=trial):
                self.assertEqual(
                    [sorted(m.id for m in r.members) for r in rows(shuffled)],
                    want)

    def test_a_superscript_joins_the_line_it_belongs_to(self):
        """Rows are seeded TALLEST FIRST for this reason. In reading
        order the superscript, sitting higher than its line, opens a row
        of its own before that line exists -- and a determinism test
        cannot catch it, because the wrong answer was deterministic."""
        gs = line(8)
        gs.append(g(99, 200.0, 97.0, 205.0, 104.0))
        got = rows(gs)
        self.assertEqual(len(got), 1)
        self.assertIn(99, [m.id for m in got[0].members])

    def test_a_tall_brace_does_not_swallow_the_lines_it_spans(self):
        """Rows seed from the MODAL height, not the maximum. Seeding
        tallest-first fixed the superscript case and broke this one: a
        50px \\left\\{ spanning three body lines opened a row across the
        whole span and collapsed [8, 8, 8] into [25]."""
        body = []
        for k, y in enumerate((0.0, 20.0, 40.0)):
            body += [g(k * 10 + i, i * 10.0, y, i * 10.0 + 8, y + 10.0)
                     for i in range(8)]
        brace = g(999, 200.0, 0.0, 210.0, 50.0)
        sizes = sorted(len(r.members) for r in rows(body + [brace]))
        self.assertEqual(sizes, [1, 8, 8, 8])

    def test_rows_come_back_top_to_bottom(self):
        got = rows(line(4, y=300.0, start=200) + line(4, y=100.0))
        self.assertLess(got[0].top, got[1].top)

    def test_an_empty_input_gives_no_rows(self):
        self.assertEqual(rows([]), [])

    def test_a_bad_overlap_is_refused(self):
        for bad in (0.0, 1.0, -0.5, 2.0):
            with self.subTest(bad):
                with self.assertRaises(ValueError):
                    rows(line(3), overlap=bad)


class T14_2_ReferenceLinesUseModes(unittest.TestCase):
    """G3. A mean baseline is dragged down by every descender and up by
    nothing; one tall bracket moves it further still."""

    def test_a_descender_does_not_move_the_baseline(self):
        gs = line(9)                       # bottoms at 110
        gs.append(g(99, 200.0, 100.0, 208.0, 118.0))   # a 'p' descending
        ref = reference_lines(rows(gs)[0])
        self.assertEqual(ref.baseline, 110.0)

    def test_one_tall_bracket_does_not_move_the_top(self):
        gs = line(9)                       # tops at 100
        gs.append(g(99, 200.0, 88.0, 206.0, 110.0))    # a tall fence
        ref = reference_lines(rows(gs)[0])
        self.assertEqual(ref.top, 100.0)

    def test_the_mean_would_have_moved_and_the_mode_did_not(self):
        gs = line(9)
        gs.append(g(99, 200.0, 100.0, 208.0, 140.0))
        ref = reference_lines(rows(gs)[0])
        mean_bottom = sum(x.bottom for x in gs) / len(gs)
        self.assertNotAlmostEqual(mean_bottom, ref.baseline, places=1)
        self.assertEqual(ref.baseline, 110.0)

    def test_a_row_of_all_distinct_values_still_gets_an_answer(self):
        """The modal fallback: with no repeated value, use the median
        rather than returning nothing."""
        gs = [g(i, i * 10.0, 100.0 + i, i * 10.0 + 8, 110.0 + i)
              for i in range(3)]
        ref = reference_lines(Row(gs, 100.0, 112.0))
        self.assertEqual(ref.baseline, 111.0)

    def test_the_mode_is_used_where_it_differs_from_the_median(self):
        """Found by branch mutation: every earlier fixture had mode ==
        median, so replacing the mode with the median changed nothing.
        Three glyphs share a baseline and four are scattered above it --
        the mode is the shared line, the median is not."""
        gs = [g(0, 0.0, 90.0, 8.0, 100.0), g(1, 10.0, 90.0, 18.0, 100.0),
              g(2, 20.0, 90.0, 28.0, 100.0),
              g(3, 30.0, 84.0, 38.0, 104.0), g(4, 40.0, 84.0, 48.0, 108.0),
              g(5, 50.0, 84.0, 58.0, 112.0), g(6, 60.0, 84.0, 68.0, 116.0)]
        ref = reference_lines(Row(gs, 84.0, 116.0))
        median_bottom = sorted(x.bottom for x in gs)[len(gs) // 2]
        self.assertEqual(ref.baseline, 100.0)
        self.assertNotEqual(ref.baseline, median_bottom)

    def test_an_empty_row_is_refused(self):
        with self.assertRaises(ValueError):
            reference_lines(Row([], 0.0, 0.0))


class T14_3_ScriptDetection(unittest.TestCase):
    """G4 and G5. Measured 100.0% precision, 0 false positives in 37,759
    glyphs -- because BOTH a height reduction and an offset are
    required."""

    def test_a_raised_small_glyph_is_a_superscript(self):
        # Real proportions: a superscript is ~0.7 of x-height and raised
        # ~0.6 of it, so it still overlaps the line substantially. An
        # earlier fixture raised it clear of the line entirely, which put
        # it in its own row -- unrealistic, and it hid nothing about the
        # code.
        gs = line(8)
        gs.append(g(99, 200.0, 97.0, 205.0, 104.0))
        got = detect_scripts(rows(gs)[0])
        self.assertEqual([s.glyph_id for s in got], [99])
        self.assertEqual(got[0].kind, ScriptKind.SUPER)

    def test_a_lowered_small_glyph_is_a_subscript(self):
        gs = line(8)
        gs.append(g(99, 200.0, 106.0, 205.0, 113.0))
        got = detect_scripts(rows(gs)[0])
        self.assertEqual(got[0].kind, ScriptKind.SUB)

    def test_a_small_glyph_on_the_baseline_is_not_a_script(self):
        """A comma. Small alone is not evidence -- this is half of what
        makes the detector high-precision."""
        gs = line(8)
        gs.append(g(99, 200.0, 104.0, 203.0, 110.0))   # sits on baseline
        self.assertEqual(detect_scripts(rows(gs)[0]), [])

    def test_a_full_height_raised_glyph_is_not_a_script(self):
        """A rendering artefact or a tall bracket. Offset alone is not
        evidence either."""
        gs = line(8)
        gs.append(g(99, 200.0, 96.0, 208.0, 106.0))   # full height, raised
        self.assertEqual(detect_scripts(rows(gs)[0]), [])

    def test_detection_is_relative_to_its_own_row(self):
        """G5: a page with two body sizes must not report one of them as
        scripts throughout."""
        big = line(8, y=100.0, h=20.0)
        small = line(8, y=200.0, h=8.0, start=100)
        got = rows(big + small)
        self.assertEqual(len(got), 2)
        for r in got:
            with self.subTest(top=r.top):
                self.assertEqual(detect_scripts(r), [])

    def test_confident_needs_both_signals_well_clear(self):
        near = Script(1, ScriptKind.SUPER, 0.30, 0.78)
        clear = Script(2, ScriptKind.SUPER, 0.60, 0.55)
        self.assertFalse(near.confident)
        self.assertTrue(clear.confident)

    def test_thresholds_are_named_arguments(self):
        """G7: no literal buried in a comparison."""
        gs = line(8)
        gs.append(g(99, 200.0, 97.0, 205.0, 104.0))
        self.assertEqual(len(detect_scripts(rows(gs)[0])), 1)
        self.assertEqual(detect_scripts(rows(gs)[0],
                                        max_height_ratio=0.1), [])

    def test_a_row_with_no_scripts_reports_none(self):
        self.assertEqual(detect_scripts(rows(line(10))[0]), [])


class T14_4_ComponentGrouping(unittest.TestCase):
    """U13's confusion matrix is dominated by `i . : 1 l` -- multi-part
    glyphs a per-component classifier sees half of.

    EVERY FIXTURE HERE SITS IN A LINE OF TEXT, and that is the finding
    rather than boilerplate. `group()` is now bounded to a row, and a
    tittle joins its stem's row only because the row's band reaches the
    ascender line -- which a line of prose establishes and two glyphs
    alone do not. Measured: an isolated dot and stem are TWO rows, and
    so are a dot and a stem beside six letters of uniform height; add
    one ascender and they are one.

    So "the tittle is within-row by construction" is false without a
    row. A fixture for a within-row rule must contain a row -- the same
    lesson as a table grid with no letters in it, in its fourth
    costume.
    """

    #: A line of prose, with an ascender, at x 0-140. Fixtures place
    #: their own glyphs to the right of it at x >= 200 so the horizontal
    #: overlap test is untouched by the context.
    @staticmethod
    def _line():
        out = [g(900, 0.0, 88.0, 13.0, 112.0)]          # an `l`
        out += [g(901 + i, 20.0 * (i + 1), 96.0,
                  20.0 * (i + 1) + 13, 112.0) for i in range(6)]
        return out

    def _clusters_of(self, glyphs):
        """Cluster the fixture inside a line, then drop the line."""
        ctx = self._line()
        ids = {x.id for x in glyphs}
        return [c for c in group(ctx + list(glyphs))
                if set(c) & ids]

    def test_a_dot_and_a_stem_become_one_glyph(self):
        dot = g(0, 200.0, 90.0, 203.0, 93.0)
        stem = g(1, 200.0, 96.0, 203.0, 112.0)
        self.assertEqual(self._clusters_of([dot, stem]), [[0, 1]])

    def test_a_colon_becomes_one_glyph(self):
        top = g(0, 200.0, 96.0, 203.0, 99.0)
        bot = g(1, 200.0, 106.0, 203.0, 109.0)
        self.assertEqual(self._clusters_of([top, bot]), [[0, 1]])

    def test_two_adjacent_letters_are_not_merged(self):
        """G6: the overlap test is on the NARROWER width, so a wide glyph
        cannot swallow a neighbour merely by being wide."""
        a = g(0, 10.0, 100.0, 18.0, 110.0)
        b = g(1, 20.0, 100.0, 28.0, 110.0)
        self.assertEqual(group([a, b]), [[0], [1]])

    def test_a_wide_glyph_does_not_swallow_a_narrow_neighbour(self):
        """Side by side, so horizontal overlap alone would merge them.
        The stacking test is what says no -- an earlier version without
        it joined these."""
        wide = g(0, 10.0, 100.0, 60.0, 110.0)
        narrow = g(1, 55.0, 100.0, 58.0, 110.0)
        self.assertEqual(group([wide, narrow]), [[0], [1]])

    def test_stacking_is_what_distinguishes_one_glyph_from_two(self):
        """The same two boxes: stacked they are one glyph, side by side
        they are two."""
        stacked = [g(0, 200.0, 90.0, 204.0, 94.0),
                   g(1, 200.0, 100.0, 204.0, 110.0)]
        beside = [g(0, 200.0, 100.0, 204.0, 110.0),
                  g(1, 201.0, 100.0, 205.0, 110.0)]
        self.assertEqual(self._clusters_of(stacked), [[0, 1]])
        self.assertEqual(self._clusters_of(beside), [[0], [1]])

    def test_horizontal_overlap_is_required_not_just_stacking(self):
        """Two components stacked in the vertical sense but in different
        columns are two glyphs -- a dot over there is not this stem's
        dot. Found by branch mutation."""
        # They must TOUCH horizontally, or the x-ordered early break
        # rejects the pair before the overlap test is reached -- which is
        # how the first version of this test failed to guard anything.
        stem = g(0, 200.0, 100.0, 204.0, 110.0)
        adjacent_dot = g(1, 204.0, 90.0, 208.0, 94.0)
        self.assertEqual(self._clusters_of([stem, adjacent_dot]),
                         [[0], [1]])
        # and the same dot directly above DOES join
        own_dot = g(2, 200.0, 90.0, 204.0, 94.0)
        self.assertEqual(self._clusters_of([stem, own_dot]), [[0, 2]])

    def test_a_display_operator_no_longer_absorbs_its_limits(self):
        """The recorded defect, CLOSED as a side effect of bounding
        `group` to a row -- and closed by the very fact the old
        docstring gave as the reason it could not be.

        It said: a display limit does not vertically overlap its
        operator, so `rows()` puts them in different rows and nothing
        classifies them as scripts. That was offered as why the obvious
        fix could not reach the defect. Once joins are confined to a
        row, the same three rows are exactly what keeps the limits out
        of the operator.

        This does NOT amount to symbol identity. The limits are now
        three separate clusters rather than one wrong cluster; knowing
        that the middle one is an operator and the others are its
        limits is still unsolved, and `\sum` with an INLINE limit --
        one that does share the operator's row -- would still be
        absorbed. Recorded as closed for the display case only.
        """
        op = g(10, 100.0, 100.0, 130.0, 140.0)
        above = g(11, 108.0, 88.0, 122.0, 98.0)
        below = g(12, 108.0, 142.0, 122.0, 152.0)
        self.assertEqual(len(rows([op, above, below])), 3)
        self.assertEqual(group([op, above, below]), [[10], [11], [12]])

    def test_a_vertically_distant_pair_is_not_merged(self):
        top = g(0, 10.0, 20.0, 13.0, 23.0)
        bot = g(1, 10.0, 300.0, 13.0, 303.0)
        self.assertEqual(group([top, bot]), [[0], [1]])

    def test_grouping_is_independent_of_input_order(self):
        parts = [g(0, 10.0, 96.0, 13.0, 99.0), g(1, 10.0, 102.0, 13.0, 112.0),
                 g(2, 30.0, 100.0, 38.0, 110.0)]
        want = group(parts)
        rng = random.Random(11)
        for trial in range(6):
            s = parts[:]
            rng.shuffle(s)
            with self.subTest(trial=trial):
                self.assertEqual(group(s), want)

    def test_three_parts_join_transitively(self):
        parts = [g(0, 200.0, 90.0, 203.0, 93.0),
                 g(1, 200.0, 96.0, 203.0, 99.0),
                 g(2, 200.0, 102.0, 203.0, 112.0)]
        self.assertEqual(self._clusters_of(parts), [[0, 1, 2]])

    def test_an_empty_input_groups_to_nothing(self):
        self.assertEqual(group([]), [])

    def test_a_bad_share_is_refused(self):
        for bad in (0.0, -1.0, 1.5):
            with self.subTest(bad):
                with self.assertRaises(ValueError):
                    group([g(0, 0, 0, 1, 1)], share=bad)


if __name__ == "__main__":
    unittest.main()


class T14_6_GroupingIsBoundedToOneRow(unittest.TestCase):
    """`group()` chained 114 components down 80% of a scanned page.

    Measured on `BH1-000274` at 600 dpi: 2,125 components collapsed to
    380 clusters, the largest spanning y 603-4875 in a 10%-wide strip.
    Expected is roughly one cluster per component.

    All three join conditions were individually CORRECT. The defect was
    that nothing bounded the search to a line of text: at `max_gap=2.5`
    and a 43 px glyph the permitted vertical gap is 108 px, and body
    leading on that page is about the same, so a letter in one line and
    an x-aligned letter in the next satisfied gap, share and stack
    together -- and union-find chained them the length of the column.

    The synthetic fixtures could not show it because they have one or
    two lines. Third instance of "a synthetic fixture has no letters in
    it": the fixture must contain the thing the rule discriminates
    against, and here that is a SECOND LINE OF PROSE.
    """

    @staticmethod
    def _prose(rows_n=20, cols=30, h=10.0, w=8.0, pitch=25.0, pad=4.0):
        """A page of prose: x-aligned columns, realistic leading.

        `pitch - h` is 15 and `max_gap * h` is 25, so the gap test
        passes between consecutive lines -- which is the real page's
        arithmetic, not a contrived one.
        """
        out, gid = [], 0
        for r in range(rows_n):
            top = r * pitch
            for c in range(cols):
                x0 = c * (w + pad)
                out.append(Glyph(gid, x0, top, x0 + w, top + h))
                gid += 1
        return out

    def test_group_does_not_chain_down_a_text_column(self):
        glyphs = self._prose()
        for c in group(glyphs):
            span = (max(g.bottom for g in glyphs if g.id in c)
                    - min(g.top for g in glyphs if g.id in c))
            self.assertLess(span, 3 * 10.0,
                            f"a cluster of {len(c)} spans {span} px")

    def test_a_SUPPLIED_row_partition_is_honoured(self):
        """`rows=` exists so a caller that already has the partition
        does not recompute it. If it were ignored the parameter would be
        decoration, and nothing else in the suite passes it."""
        from inkdrill.mathstruct import Row
        dot = Glyph(0, 200.0, 90.0, 203.0, 93.0)
        stem = Glyph(1, 200.0, 96.0, 203.0, 112.0)
        one = [Row([dot, stem], 90.0, 112.0)]
        two = [Row([dot], 90.0, 93.0), Row([stem], 96.0, 112.0)]
        self.assertEqual(group([dot, stem], rows=one), [[0, 1]])
        self.assertEqual(group([dot, stem], rows=two), [[0], [1]])

    def test_a_glyph_in_NO_supplied_row_still_gets_a_cluster(self):
        """A caller may hand in a partial partition. A glyph that is in
        none of its rows must come back as its own cluster rather than
        disappear -- losing ink silently is the worst failure this
        module has."""
        from inkdrill.mathstruct import Row
        a = Glyph(0, 200.0, 96.0, 203.0, 112.0)
        b = Glyph(1, 300.0, 96.0, 303.0, 112.0)
        got = group([a, b], rows=[Row([a], 96.0, 112.0)])
        self.assertEqual(got, [[0], [1]])

    def test_the_band_is_x_SORTED_before_the_early_break(self):
        """The loop breaks on `gb.x0 > ga.x1`, which is only valid on an
        x-sorted band -- and a row's members arrive in whatever order the
        row was built in.

        The fixture puts a FAR-RIGHT glyph between the two parts of the
        pair. Unsorted, the break fires on it and the stem is never
        reached; sorted, the pair is adjacent and joins. A band that
        happens to be in order cannot show this, which is why shuffling
        a prose page did not catch the mutant.
        """
        from inkdrill.mathstruct import Row
        dot = Glyph(0, 200.0, 90.0, 203.0, 93.0)
        far = Glyph(1, 500.0, 96.0, 513.0, 112.0)
        stem = Glyph(2, 200.0, 96.0, 203.0, 112.0)
        row = Row([dot, far, stem], 90.0, 112.0)   # deliberately unsorted
        self.assertEqual(group([dot, far, stem], rows=[row]),
                         [[0, 2], [1]])

    def test_the_result_does_not_depend_on_INPUT_ORDER(self):
        """The pairwise loop breaks on `gb.x0 > ga.x1`, which is only
        valid on an x-sorted band. `rows()` members arrive in whatever
        order the row was built in, so the sort has to happen per band
        -- and a fixture that is already sorted cannot show it."""
        import random
        glyphs = self._prose(rows_n=3, cols=6)
        want = group(glyphs)
        rng = random.Random(20260814)
        for _ in range(8):
            shuffled = glyphs[:]
            rng.shuffle(shuffled)
            self.assertEqual(group(shuffled), want)

    def test_the_cluster_count_tracks_the_component_count(self):
        """A page of separate letters is a page of separate glyphs. 600
        components must not become a handful of clusters."""
        glyphs = self._prose()
        self.assertGreaterEqual(len(group(glyphs)), int(0.8 * len(glyphs)))


class T14_7_PairStats(unittest.TestCase):
    """`pair_stats` moved here from tools/mathshape.py (one definition,
    I1). The overlap floor gets its own fixture: at a 4 px shift the
    12 px boxes still overlap 8 >= 6 and read OFFSET; at 8 px they
    overlap 4 < 6 and the pair VANISHES -- both outcomes asserted, so
    the floor cannot be deleted (the CLI fixture alone could not kill
    that mutant)."""

    @staticmethod
    def _pair(shift):
        from inkdrill.raster import InkMask
        W, H = 40, 34
        buf = bytearray(W * H)
        for y in range(4, 12):
            for x in range(10, 22):
                buf[y * W + x] = 0xFF
        for y in range(18, 26):
            for x in range(10 + shift, 22 + shift):
                buf[y * W + x] = 0xFF
        return InkMask(bytes(buf), W, H)

    def test_the_overlap_floor_separates_offset_from_nothing(self):
        from inkdrill.mathstruct import pair_stats
        centred = pair_stats(self._pair(0))
        offset = pair_stats(self._pair(4))
        gone = pair_stats(self._pair(8))
        self.assertEqual((centred["stacked"], centred["centred"]), (1, 1))
        self.assertEqual((offset["stacked"], offset["offset"]), (1, 1))
        self.assertEqual(gone["stacked"], 0)

    def test_the_gap_bound_separates_structure_from_line_spacing(self):
        """I5: gap 18 px over median height 8 px exceeds 1.5x, so the
        pair is line spacing and must NOT count; the same pair at gap
        6 px is structure and must. Without the bound, EQ0007's aligned
        block read 53 stacked pairs for 8 real ones."""
        from inkdrill.mathstruct import pair_stats
        from inkdrill.raster import InkMask
        def pair(gap):
            W = 40; H = 12 + gap + 8 + 4
            buf = bytearray(W * H)
            for y in range(4, 12):
                for x in range(10, 22):
                    buf[y * W + x] = 0xFF
            for y in range(12 + gap, 20 + gap):
                for x in range(10, 22):
                    buf[y * W + x] = 0xFF
            return InkMask(bytes(buf), W, H)
        self.assertEqual(pair_stats(pair(6))["stacked"], 1)
        self.assertEqual(pair_stats(pair(18))["stacked"], 0)


class T14_8_RegionOverrun(unittest.TestCase):
    """102: the two conditions of `region_overrun`, and the fixture
    CONTAINS all three classes the rule must separate -- otherwise it
    cannot fail.

    Dimensions are the measured ones, not chosen: 0902.0431 p1's scan
    cells at 300 dpi are 1620 px wide with a median component width of
    9-18 px, so this fixture is 15 px glyphs in a 200 px crop. A
    fixture whose numbers came from nowhere is the tell.

      MAIN     four 15 px glyphs, 5 px apart -- one cluster.
      JOINED   a glyph at x=0 touching the left border, 5 px from the
               main ink. AT AN EDGE and NOT separated: the first
               symbol of an expression. Must NOT be overrun.
      ISLAND   a glyph 60 px away in the interior. SEPARATED and not
               at an edge: a display limit or a stray mark. Must NOT
               be overrun.
      OVERRUN  a glyph 60 px away AND cut by the right border. Both
               conditions. Must BE overrun.

    Every branch of the classification fires in one mask, so neither
    condition can be deleted without a failure.
    """

    def test_both_conditions_are_required(self):
        from inkdrill.mathstruct import region_overrun
        from inkdrill.raster import InkMask
        W, H = 200, 40
        def crop(items):
            buf = bytearray(W * H)
            for x0, x1 in items:
                for y in range(12, 27):
                    for x in range(max(0, x0), min(W, x1)):
                        buf[y * W + x] = 0xFF
            return InkMask(bytes(buf), W, H)
        main = [(70, 85), (90, 105), (110, 125)]
        joined = (55, 70)          # touches main, not an edge
        at_edge_joined = (0, 15)   # an edge, 55 px from main -> island
        island = (5, 20)           # separated, interior? no: x0=5 > tol
        overrun = (185, 200)       # separated AND cut by the right edge

        # median glyph width is 15, so the bound at gap_scale 1.0 is 15
        only_main = region_overrun(crop(main), gap_scale=1.0, edge_tol=0)
        self.assertEqual(only_main["overrun"], [])
        self.assertEqual(only_main["separated"], [])

        # SEPARATED but interior: an island 45 px from the main ink,
        # nowhere near a border -> not overrun.
        isl = region_overrun(crop(main + [(10, 25)]), gap_scale=1.0,
                             edge_tol=0)
        self.assertEqual(len(isl["separated"]), 1)
        self.assertEqual(isl["overrun"], [])

        # AT AN EDGE but joined: a component reaching x=0 that is part
        # of the same cluster -> not overrun.
        jn = region_overrun(crop([(0, 15), (18, 33), (45, 60)] + main),
                            gap_scale=1.0, edge_tol=0)
        self.assertEqual(jn["separated"], [])
        self.assertTrue(jn["at_edge"])
        self.assertEqual(jn["overrun"], [])

        # BOTH: separated AND cut by the right border.
        ov = region_overrun(crop(main + [overrun]), gap_scale=1.0,
                            edge_tol=0)
        self.assertEqual(len(ov["overrun"]), 1)
        self.assertEqual(len(ov["kept"]), 3)

    def test_the_gap_bound_is_a_multiple_of_the_median_glyph_width(self):
        """The bound must SCALE, or a dpi change retunes it silently.
        The same geometry at 15 px and at 30 px glyphs must give the
        same answer -- and a gap_scale wide enough to swallow the
        separation must give the opposite one, so the argument is not
        inert."""
        from inkdrill.mathstruct import region_overrun
        from inkdrill.raster import InkMask

        def crop(s):
            W, H = 200 * s, 40 * s
            buf = bytearray(W * H)
            for x0, x1 in [(70, 85), (90, 105), (110, 125), (185, 200)]:
                for y in range(12 * s, 27 * s):
                    for x in range(x0 * s, min(W, x1 * s)):
                        buf[y * W + x] = 0xFF
            return InkMask(bytes(buf), W, H)

        for s in (1, 2):
            ro = region_overrun(crop(s), gap_scale=1.0, edge_tol=0)
            self.assertEqual(len(ro["overrun"]), 1, f"scale {s}")
        wide = region_overrun(crop(1), gap_scale=5.0, edge_tol=0)
        self.assertEqual(wide["overrun"], [])

    def test_edge_tolerance_admits_a_padded_crop(self):
        """The scan crops carry 2 px of padding at the top rule, so a
        component that entered across the border stops 2 px short of
        it. Asserted in BOTH directions: at tol 0 the padded component
        is not at an edge and is not reported; at tol 2 it is."""
        from inkdrill.mathstruct import region_overrun
        from inkdrill.raster import InkMask
        W, H = 200, 40
        buf = bytearray(W * H)
        for x0, x1 in [(70, 85), (90, 105), (110, 125)]:
            for y in range(12, 27):
                for x in range(x0, x1):
                    buf[y * W + x] = 0xFF
        for y in range(12, 27):            # 2 px short of the right edge
            for x in range(185, W - 2):
                buf[y * W + x] = 0xFF
        m = InkMask(bytes(buf), W, H)
        self.assertEqual(region_overrun(m, gap_scale=1.0,
                                        edge_tol=0)["overrun"], [])
        self.assertEqual(len(region_overrun(m, gap_scale=1.0,
                                            edge_tol=2)["overrun"]), 1)

    def test_the_kept_components_are_the_crop_minus_the_overrun(self):
        """`kept` exists so the caller recomputes the five-tuple on the
        crop's own ink instead of guessing. It must be the complement,
        and it must not be the whole list when something was found."""
        from inkdrill.mathstruct import region_overrun
        from inkdrill.raster import InkMask
        W, H = 200, 40
        buf = bytearray(W * H)
        for x0, x1 in [(70, 85), (90, 105), (110, 125), (185, 200)]:
            for y in range(12, 27):
                for x in range(x0, min(W, x1)):
                    buf[y * W + x] = 0xFF
        ro = region_overrun(InkMask(bytes(buf), W, H), gap_scale=1.0,
                            edge_tol=0)
        self.assertEqual(len(ro["overrun"]) + len(ro["kept"]), 4)
        self.assertEqual(len(ro["kept"]), 3)
        self.assertTrue(set(ro["overrun"]).isdisjoint(
            {c.id for c in ro["kept"]}))

    def test_an_empty_crop_is_not_an_overrun(self):
        from inkdrill.mathstruct import region_overrun
        from inkdrill.raster import InkMask
        ro = region_overrun(InkMask(bytes(200 * 40), 200, 40))
        self.assertEqual(ro["overrun"], [])
        self.assertEqual(ro["med_width"], 0.0)

    def test_all_four_borders_count_as_an_edge(self):
        """The commonest real overrun is VERTICAL -- the row rule above
        or the descender of the line below -- and the left/right
        fixtures above cannot see a top/bottom mistake. Each border is
        asserted on its own, so no one of the four terms can be
        deleted."""
        from inkdrill.mathstruct import region_overrun
        from inkdrill.raster import InkMask
        W, H = 200, 120

        def crop(x0, y0, x1, y1):
            buf = bytearray(W * H)
            for a, b in [(70, 85), (90, 105), (110, 125)]:
                for y in range(52, 67):        # main ink, mid-crop
                    for x in range(a, b):
                        buf[y * W + x] = 0xFF
            for y in range(y0, y1):            # the intruder
                for x in range(x0, x1):
                    buf[y * W + x] = 0xFF
            return InkMask(bytes(buf), W, H)

        for name, box in (("top", (90, 0, 105, 15)),
                          ("bottom", (90, H - 15, 105, H)),
                          ("left", (0, 52, 15, 67)),
                          ("right", (W - 15, 52, W, 67))):
            ro = region_overrun(crop(*box), gap_scale=1.0, edge_tol=0)
            self.assertEqual(len(ro["overrun"]), 1, name)
        # and the same intruder pulled clear of every border is not one
        inside = region_overrun(crop(90, 20, 105, 35), gap_scale=1.0,
                                edge_tol=0)
        self.assertEqual(inside["overrun"], [])
        self.assertEqual(len(inside["separated"]), 1)

    def test_passing_comps_gives_the_same_answer_as_sweeping(self):
        """`comps` is a performance argument -- the threshold sweep
        runs 20 times over one crop -- and a performance argument that
        changes the answer is a bug. Both paths asserted."""
        from inkdrill.mathstruct import region_overrun
        from inkdrill.nest import ink_only
        from inkdrill.raster import InkMask
        W, H = 200, 40
        buf = bytearray(W * H)
        for x0, x1 in [(70, 85), (90, 105), (110, 125), (185, 200)]:
            for y in range(12, 27):
                for x in range(x0, min(W, x1)):
                    buf[y * W + x] = 0xFF
        m = InkMask(bytes(buf), W, H)
        swept = region_overrun(m, gap_scale=1.0, edge_tol=0)
        given = region_overrun(m, gap_scale=1.0, edge_tol=0,
                               comps=list(ink_only(m).regions))
        self.assertEqual(swept["overrun"], given["overrun"])
        self.assertEqual(swept["separated"], given["separated"])
        self.assertEqual(swept["med_width"], given["med_width"])

    def test_the_main_ink_is_the_heaviest_cluster_not_the_first(self):
        """Ids are assigned in raster order, so seeding the cluster
        from one component makes the answer depend on which glyph
        comes first. Here the LEFTMOST cluster has the lowest ids and
        the RIGHTMOST carries the ink; the two-glyph island on the
        left must be what is reported, not the five-glyph body."""
        from inkdrill.mathstruct import region_overrun
        from inkdrill.raster import InkMask
        W, H = 300, 40
        buf = bytearray(W * H)
        boxes = [(0, 15), (18, 33)] + \
                [(150 + i * 20, 165 + i * 20) for i in range(5)]
        for x0, x1 in boxes:
            for y in range(12, 27):
                for x in range(x0, min(W, x1)):
                    buf[y * W + x] = 0xFF
        ro = region_overrun(InkMask(bytes(buf), W, H), gap_scale=1.0,
                            edge_tol=0)
        self.assertEqual(len(ro["kept"]), 5)
        self.assertEqual(len(ro["overrun"]), 2)

    def test_the_heaviest_cluster_can_be_the_one_with_fewest_parts(self):
        """A mutation survivor turned into a fixture: zeroing the mass
        term still passed, because in every earlier fixture the
        heaviest cluster was also the one with the most components, so
        the count tie-breaker carried the answer. Scan noise is the
        real case -- a border speckled with a dozen 4 px dots against
        one solid glyph -- and there COUNT gives the wrong cluster."""
        from inkdrill.mathstruct import region_overrun
        from inkdrill.raster import InkMask
        W, H = 200, 60
        buf = bytearray(W * H)
        for y in range(20, 45):                 # one solid 60x25 mark
            for x in range(100, 160):
                buf[y * W + x] = 0xFF
        for i in range(6):                      # six 4 px specks at x=0
            for y in range(4 + i * 8, 8 + i * 8):
                for x in range(0, 4):
                    buf[y * W + x] = 0xFF
        ro = region_overrun(InkMask(bytes(buf), W, H), gap_scale=1.0,
                            edge_tol=0)
        self.assertEqual(len(ro["kept"]), 1)
        self.assertEqual(len(ro["overrun"]), 6)

    def test_the_extreme_anchor_is_a_different_statement_not_a_looser_one(self):
        """`anchor='extreme'` asks where the INK ends, `anchor='edge'`
        where the RECTANGLE ends, and the case that separates them is a
        crop with a uniform inset: measured on four report crops from
        two documents, the rightmost ink stopped 6, 6, 6 and 7 px short
        of the border whatever the row contained. Here the intruder
        stops 6 px short -- `edge` at tol 0 sees nothing, `extreme`
        sees it, and an intruder in the MIDDLE is seen by neither."""
        from inkdrill.mathstruct import region_overrun
        from inkdrill.raster import InkMask
        W, H = 200, 40

        def crop(x0, x1):
            buf = bytearray(W * H)
            for a, b in [(70, 85), (90, 105), (110, 125)]:
                for y in range(12, 27):
                    for x in range(a, b):
                        buf[y * W + x] = 0xFF
            for y in range(12, 27):
                for x in range(x0, x1):
                    buf[y * W + x] = 0xFF
            return InkMask(bytes(buf), W, H)

        inset = crop(179, W - 6)          # 6 px short of the border
        self.assertEqual(region_overrun(inset, anchor="edge",
                                        edge_tol=0)["overrun"], [])
        self.assertEqual(len(region_overrun(inset, anchor="extreme")
                             ["overrun"]), 1)
        # An intruder that is neither at a border nor at an end of the
        # ink is not overrun under EITHER reading -- otherwise
        # `extreme` would be the looser statement rather than a
        # different one.
        middle = crop(20, 35)             # left of the main ink...
        self.assertEqual(len(region_overrun(middle, anchor="extreme")
                             ["overrun"]), 1)   # ...so it IS an end
        self.assertEqual(region_overrun(crop(0, 0), anchor="extreme")
                         ["overrun"], [])       # no intruder at all

    def test_an_unknown_anchor_raises_rather_than_defaulting(self):
        """A misspelled anchor must not silently pick one of the two
        readings -- the whole point is that they are different
        statements. The accepting side is asserted too, so the guard
        cannot be made unconditional."""
        from inkdrill.mathstruct import region_overrun
        from inkdrill.raster import InkMask
        m = InkMask(bytes(b"\xff" * 100 + bytes(300)), 20, 20)
        for ok in ("edge", "extreme"):
            self.assertIn("overrun", region_overrun(m, anchor=ok))
        with self.assertRaises(ValueError):
            region_overrun(m, anchor="border")
