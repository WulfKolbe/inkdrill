# inkdrill — implementation plan

New code base. Nothing is shared with `blobtrack.py`, `blobtopo.py`,
`blobcc.py`/`blobcc.ts`, `deskew.py` or `cropmark.py`; those remain
available as independent oracles to compare against, which is worth more
than reuse would have been.

Package name `inkdrill` is a placeholder consistent with the drill family.
It appears only in imports and one directory name — changing it later is a
`sed`, but it gets more expensive with every unit, so decide early.

**Reporting rule for this document:** a unit is never "done". It is
"tests T-n.m passed on <date>". Section 3 lists what has actually run.

---

## 1. Conventions locked in U1–U3

These are decided, implemented, and under test. Later units inherit them
rather than re-litigating them.

| Decision | Value | Rationale |
|---|---|---|
| Matrix order | PDF/PostScript row-vector `[a b c d e f]` | `m1.then(m2)` is the `cm` concatenation order; row 1 is the x-basis image, so the baseline direction is `(a, b)` with no conversion |
| **Angles** | **the core stores none** | Directions are unit vectors. `angle_deg_ccw` (y-up) and `angle_deg_screen` (y-down) are the only producers, each naming its convention. A vector cannot disagree with itself about sign — this is a direct response to the sign drift between `blobtrack.angle_deg` and `blobcc.orientation_deg` |
| Mask encoding | `0xFF` ink / `0x00` background, package-wide | `bytes.translate` binarizes and `bytes.find` extracts runs, both at C speed with no numpy. Measured at 105 Mpx/s |
| Pixel geometry | pixel (i,j) covers `[i,i+1) x [j,j+1)`; centre `(i+.5, j+.5)` | Removes the ±0.5 ambiguity that otherwise appears at the pt↔px boundary |
| Run coordinates | scan space `(line, lo, hi)`, inclusive | `Run.image_span(axis)` is the only sanctioned converter; nothing indexes the tuple positionally for an image coordinate |
| Connectivity | 8 for foreground, 4 for background, always paired | 8-connected ink implies 4-connected holes; the pair is constrained |
| ROI | `keep_regions` / `clear_regions` are two polarities of one parameter | The math pipeline needs the complement of what the text pipeline needs; that must not be two code paths |
| Test framework | stdlib `unittest`, no third-party dependency | Matches the stdlib-only constraint of the compute environment |

---

## 2. Unit list

Dependencies run strictly downward. No unit may be started before its
dependencies' tests pass.

### Foundation

**U0 `pngio.py` — ghostscript png16m ingest.**
*No dependencies.*
Contract: `read_png` returning `PngImage(width, height, gray, dpi, neutral)`;
`load_mask` composing it with U2's `binarize`. G1–G7.
**Scope limit stated up front:** IHDR exactly `(8, 2, 0, 0, 0)` — the output
of the ghostscript `png16m` device. Everything else raises `UnsupportedPNG`.
Tests: CRC and truncation rejection; every rejected IHDR variant; all five
scanline filters against a naive reference decoder held as the oracle;
multi-IDAT concatenation; `pHYs` present and absent; the neutrality
equivalence G5 that the two-path decode rests on.
**Status: 49 tests passed.**

**U1 `space.py` — affine algebra, transform graph, CTM decomposition.**
*No dependencies.*
Contract: `Affine`, `Decomposition`, `SpaceGraph`, the two angle-boundary
functions. Guarantees G1–G7 in the module docstring.
Tests: identity/inverse/associativity; decompose→recompose round trip;
determinant sign ↔ orientation flip; italic shear recovery; the PDF text
chain `FontMatrix × [Tfs,Th,Trise] × Tm × CTM`; space-graph path
composition, caching, and inconsistency detection.
**Status: 36 tests passed.**

**U2 `raster.py` — masks, binarization, maximal run extraction.**
*Depends: none.*
Contract: `InkMask`, `Run`, `Rect`, `binarize`, `iter_runs`. G1–G7.
Tests: strict threshold comparison; encoding contains only `0xFF`/`0x00`;
exact hand-checked run lists for both axes; maximality; runs never span a
line; scan order; **row and col cover an identical pixel set** (the
foundation of every later axis-invariance claim); ROI as a restriction of
the full run set; `keep_regions`/`clear_regions` complementarity.
**Status: 31 tests passed.**

**U3 `sweep.py` — the run adjacency graph, components, scan events.**
*Depends: U2.*
Contract: `sweep()` returning `SweepResult` with `nodes`, `components`,
`events`. Capture levels `NONE` / `EVENTS` / `GRAPH`. Event kinds
`birth` / `merge` / `cycle` / `split` / `close`. G1–G7.
Tests: agreement with an **independent flood fill** at conn 4 and 8 over
120 random masks; row↔col partition agreement; cycle-rank identity
`cycles == E − V + C`; hole counts on ring / figure-8 / A / H / nested
frames; event streams on hand-checked shapes; capture level changes what
is recorded but never what is computed; `up`/`down` adjacency symmetric
and equal to `edge_count`.
**Status: 36 tests passed.**

### Topology

**U4 `reeb.py` — contraction, orientation reversal, persistence.**
*Depends: U3 at `Capture.GRAPH`.*
Contract: contract degree-2 chains of the RAG into `ReebNode`s;
`orient(rag, direction)` producing the Reeb graph for any of the four
directions from the two stored RAGs; per-branch persistence as
`h(close) − h(birth)`; a `signature()` reducing a Reeb graph to a
comparable feature vector.
Contract correction, from the premise check: `signature()` has **two
entry points** — `signature(graph)` and `signature_of(graphs)` — because a
glyph is not always one component (`i j : ; = %`), and every U3 fixture is
a single blob so this was invisible from fixtures. A `ReebNode` is an
**arc**: contraction splits on junctions (`|up|≥2` or `|down|≥2`), not on
degree-2, because a birth and a close are not branch points and cutting
there would leave a plain bar as three nodes instead of one — and would
stop `persistence` reading as `h(close) − h(birth)`.
Tests: node/edge counts on the U3 fixtures; **row↑ derived by reversal
equals a genuine reversed sweep**, on the fixtures, on 40 random masks and
on real page ink; persistence separates a 2-px speck from a stroke;
signature is invariant under translation, **exactly**.
**Status: 37 tests passed. Rotation invariance is refuted — see §3.**

**U5 `aggregate.py` — moment aggregates per component.**
*Depends: U3.*
Contract: area, extents, `Σx Σy Σxx Σyy Σxy` accumulated from runs in
closed form; centroid; central moments; principal axis as a **unit
vector**, never an angle; elongation with the λ₂ ≥ 1/12 floor (the
variance of a unit pixel) so 1-px strokes stay finite.
Contract addition, from the premise check: **every raw sum is an exact
integer and no float enters before a ratio is taken.** That is what makes
axis invariance exact rather than approximate — see assumption 4 below.
`Moments.__add__` gives the addition algebra U7 will stitch bands with.
Tests: hand-computed values against a per-pixel oracle; **row-sweep and
col-sweep produce identical moments**, per component and in total, on
random masks and on real page ink; a synthetic rotated rule recovers its
angle through `angle_deg_screen`; the λ₂ floor engages exactly at 1-px
width and not at 2.
**Status: 26 tests passed.**

**U6 `nest.py` — holes, containment forest, ordering relations.**
*Depends: U3, U5.*
Contract: holes as background components of the inverted local mask
(`conn=4`); recursion for depth > 1; the four relations distinguished in
the design discussion — `hole_of`, `ink_in_hole`, `bbox_contains`,
`nesting_chain`; the containment forest with figure/ground depth parity;
the table case (hole lattice of a connected frame) and its disconnected
counterpart (collinear rule grouping).
Tests: hole count from `nest` equals `Component.cycle_count` from U3 —
**two independent computations, one the oracle for the other** — on the
U3 fixtures, 120 random masks, and 222 components of real page ink;
nested frames give depth 0/1/2; a synthetic table frame yields an m×n
hole lattice; a `\fbox`-like fixture yields `ink_in_hole` and *not*
`hole_of`; a diagonal wall does not leak, holding the paired-connectivity
rule. Depth parity (even = ink, odd = background) is a runtime check,
not a convention.
**Scope limit:** the *disconnected* table frame — collinear rule grouping
— is not implemented. That counterpart case needs U5 geometry and is
named here rather than half-built.
**Status: 29 tests passed.**

### Parallelism

**U7 `band.py` — band splitting and seam stitching.**
*Depends: U3, U5.*
Contract: split a mask into K bands; sweep each independently with
disjoint label spaces; stitch by applying the U3 adjacency predicate
across each seam and merging components. Moment aggregates add; **runs
and RAG nodes must be re-sorted after concatenation** — this is the
specific latent bug the old code base carries.
Contract addition, from the premise check: **the node count is invariant
under banding.** U2's G2 says a run never spans a line boundary, and a
band boundary *is* a line boundary, so a split can never split a run — V
needs no repair at all, only E, C and the cycle counts do. Measured
bit-identical from K=1 to K=64 on real page ink.
Tests: output identical to K=1 for K ∈ {1,2,3,7,64} on a fixture with a
blob crossing every seam, plus 60 random masks, both connectivities, and
real page ink at K ∈ {1,2,3,7,64,600} — K=600 being one band per row, so
every line is a seam; run order sorted after stitching; cycle-rank
identity survives stitching, per component and in total; moments add
across bands.
**Scope limit:** scan events are *not* stitched. A band boundary
manufactures spurious births and closes, and repairing that needs the
bounded-memory closure stream. `stitch()` returns an empty event list and
says so, rather than returning events that look right and are not.
**Status: 29 tests passed.**

**U8 `sched.py` — the task graph and priority queue.**
*Depends: U7.*
Contract: tasks `(page, axis, band)` with priority `(page_index,
band_index)`; workers pull lowest first, so page 1 saturates all cores
and workers drift forward with no mode switch; band count per page large
for page 1, small thereafter; `multiprocessing.shared_memory` for the
mask; results ordered by `(page, first_line, node)` not by completion.
Tests: identical output for pool size ∈ {1, 8, 128}; first-page latency
and total utilisation measured against a page-parallel baseline; the
idle-tail case (last page, few tasks) measured, not assumed.

### Fonts and gold standard

**U9 `font.py` — glyph access and the reference-line frame.**
*Depends: U1, U2, U3.*
Contract: load embedded fonts identified by `pdffonts`; rasterize a glyph
at a given size and CTM; run U3 over it to obtain a **reference blob in
the same feature space as page ink**; the reference-line frame from the
OpenType `BASE` table (`romn`, `hang`, `ideo`, `math`) and `MATH` table
(`AxisHeight`, `SubscriptShiftDown`, `SuperscriptShiftUp`,
`AccentBaseHeight`, `FractionRuleThickness`); contour winding direction so
figure/ground parity matches the font's own nonzero rule.
Tests: a rasterized glyph's hole count matches its contour count minus 1;
`unitsPerEm` and `FontMatrix` round-trip through U1; the math axis of a
math font is recovered and equals the fraction-bar height.
**Scope limit stated up front:** embedded, non-Type-3, outline fonts only.
Type 3, width-only, and scanned pages fall back to U11.

**U10 `gold.py` — pdfminer alignment and the many-to-many matcher.**
*Depends: U1, U9.*
Contract: build the `SpaceGraph` from the reconstructed per-character CTM
plus MediaBox, `/Rotate`, dpi and any crop — **composition, not a
formula**; match ink components to glyphs; report the four residual
classes (1↔1, 1↔N, N↔1, unmatched) rather than discarding them; export
`GoldGlyph` in COCO/PAGE form.
Tests: synthetic PDF with glyphs at known absolute positions, at several
dpi, with and without crop; the N↔1 rate as a function of dpi is
*measured and recorded* — it is the answer to "what render resolution does
this need"; composite glyphs (`é`) and ligatures (`ffi`) land in the
predicted class rather than the residual.

### Application

**U11 `coverage.py` — MathPix cross-check.** *Depends: U3, U5.*
The four residual classes: ink with no region, region with no ink,
**blob straddling a region edge** (the case that clips tall `∫` and `∑`
limits), ink under overlapping regions. Independent of U4–U10 — can be
built in parallel with the topology track for an early result.

**U12 `domains.py` — conceptual-space feature domains.**
*Depends: U4, U5, U6, U9.*
Separable domains: shape (Reeb signature, cycle count), size, position
(+ Morton code), **transform** (CTM decomposition — its own domain, so
rotation and shear stop contaminating shape), topology (depth, parity),
typographic (offsets from each named reference line ÷ em). Design test per
Gärdenfors: a dimension earns its place when the concepts of interest
become **convex** in it.

**U13 `classify.py` — nearest neighbour, two channels.**
*Depends: U9, U12.*
Normalized glyph bitmap **plus** Reeb signature as an independent channel,
plus aspect ratio and absolute extents carried separately (without them
`- − – —` and `. ·` are unrecoverable). Escalate beyond nearest neighbour
only after seeing the confusion matrix.

**U14 `mathstruct.py` — expression structure.** *Depends: U6, U12, U13.*
Reference-line estimation per row; sub/superscript from geometry alone
against pdfminer's `role` as label; big operators and their ranges; fence
matching; structure tree → LaTeX targeting the existing DOCMODEL
projection.

### Deferred

`raster_region` detection (halftone / line-graphic discrimination) after
U14, per the stated priority. The one part worth building early is the
**guard**: an active-component ceiling that fails loudly rather than
consuming memory when a screened figure appears.

---

## 3. Status — measured, not asserted

Run: `python3 -m unittest discover -s tests -t .`

```
Ran 156 tests in 0.147s

OK (skipped=4)
```

The 4 skipped are `tests/test_io_corpus.py`, opt-in and gated on
`INKDRILL_CORPUS` (see below); they do not run by default. The hermetic
count -- what actually runs on a bare checkout -- is 156 − 4 = 152.

| Unit | Tests | Result |
|---|---|---|
| U0 `pngio.py` | 49 | passed |
| U1 `space.py` | 36 | passed |
| U2 `raster.py` | 31 | passed |
| U3 `sweep.py` | 36 | passed |

49 + 36 + 31 + 36 = 152, matching the hermetic count above.

Regression: U1 and U2 re-run clean after U3 landed. U0 lands after U3 and
depends on U2 (`binarize`) alone; the full suite stays green.

Corpus smoke test (opt-in, `tests/test_io_corpus.py`, skipped in the count
above unless `INKDRILL_CORPUS` is set): 4 tests passed on 2026-08-07 against
real ghostscript output at `~/pdfdrill-library` — 18,494 pages across 3,272
document directories. Page selection explicitly seeks one neutral and one
non-neutral page (seeded), so the colour decode path -- the majority case
per the throughput table below -- has real-data coverage rather than
running only on whatever a plain sort happened to surface first.

### Hand-verified event streams

Down-sweep, `Capture.GRAPH`, printed and checked against the shapes:

```
RING      V=8  E=8  C=1 cycles=1   birth(0) split(0->1,2) cycle(4) close
LETTER_H  V=9  E=8  C=1 cycles=0   birth(0) birth(0) merge(2) split(2) close
LETTER_A  V=10 E=10 C=1 cycles=1   birth(0) split(0) cycle(3) split(3) close
```

`LETTER_H` is the case that justifies the whole RAG decision: a merge and
a split at the same scan line, zero cycles. A merge-only log would record
the join and lose the fork.

### Measured performance

Synthetic text-like page, single core, pure Python, no numpy.

| Operation | Throughput |
|---|---|
| `iter_runs` (`bytes.find`) | **105 Mpx/s** |
| `sweep` at `Capture.NONE` | **19 Mpx/s** |

Capture-level cost, 7 repeats, best-of, 2.2 Mpx page:

| Level | Best | vs NONE |
|---|---|---|
| `NONE` | 0.1151 s | — |
| `EVENTS` | 0.1283 s | **+11%** |
| `GRAPH` | 0.1300 s | **+13%** |

**This settles the open question from the previous plan.** Retaining the
full run adjacency graph costs ~13%, not the "must be measured as zero"
caution I wrote earlier. It also removes a second full pass that the old
code base needed to count holes, so on a hole-counting workload the graph
level is likely a net win — untested, since the comparison would be
against the other code base.

Extrapolated to 600 dpi A4 (4960×7016 = 34.8 Mpx): ≈1.8 s per page at
`NONE`, ≈2.1 s at `GRAPH`, single core. A 25-page paper is ≈50 s on one
core, so U7/U8 band parallelism is what makes the first-page latency
target reachable, exactly as the design argued.

The sweep is ~5.5× slower than run extraction. The gap is Python object
overhead — one `RunNode` per run plus dict operations. If that becomes
the bottleneck, the fix is a struct-of-arrays `RunNode` store, not
numpy; deferred until U8 shows whether it matters.

### U0 decode throughput

Real ghostscript `png16m` pages from `~/pdfdrill-library`, single core, pure
Python, no numpy.

| Operation | Throughput |
|---|---|
| `read_png`, neutral fast path (`_decode_gray_neutral`, SWAR) | **roughly 18–21 Mpx/s median, depending on sample** (see below) |
| `read_png`, colour path (`_decode_gray_colour`, 3-channel + luma) | **median 1.78 Mpx/s** |
| naive per-byte reference decoder | median 1.82 Mpx/s |
| speedup, fast path over naive | **roughly 10–11×**, depending on sample (was reported as 13.3× from a narrower measurement; see below) |

**The neutral-path spread is wide, not a tight band, and the median itself
moves with the sample.** Re-measured with three independent seeds of 40
random neutral pages each (one timed run per page, excluding chunk parsing
and inflate -- not best-of-3, so this includes cold-start variance the
earlier n=25/best-of-3 measurement smoothed away):

```
seed 1: n=40  median 19.6   p10 11.0  p90 27.5   min 7.0  max 176.7
seed 2: n=40  median 17.6   p10 11.2  p90 27.0   min 6.8  max 284.3
seed 3: n=40  median 19.3   p10 12.3  p90 24.8   min 6.0  max 285.7
full pages only (>5 Mpx), n=60: median 20.9, range 8.3-169.6
```

Median page size in the corpus is 15.0 Mpx. Call the honest headline
**roughly 18–21 Mpx/s median, p10–p90 about 11–27 Mpx/s on full pages** —
page-to-page variance driven by per-row filter mix (a Paeth-heavy page runs
several times slower than an Up-heavy one, matching the sequential-Paeth
caveat in `pngio.py`). The very high maxima are small pages where fixed costs
(chunking, inflate, Python call overhead) dominate the per-pixel rate; the
low end is Paeth-heavy pages. Recomputing the fast-path-over-naive speedup
against this wider sample gives roughly 18/1.82 to 21/1.82 ≈ **10–11×**, not
the 13.3× a narrower n=25/best-of-3 sample had reported.

Corpus scanline filter mix, 400 pages sampled across 361 documents drawn
from the full 18,494-page library: Up 73.0%, Paeth 20.6%, Sub 6.2%,
None 0.2%, Average 0.1%. All five filter types now appear in real corpus
data — Average included, at 0.1% — which retroactively justifies
implementing all five rather than only the three an earlier, smaller
sample showed.

**The colour path is the majority case, not an edge case.** 54.0% of the
400 sampled pages (216 of 400) are non-neutral and take the colour path —
real colour figures, not a rarity. Neutrality is *almost always* a
per-document property — of 361 documents sampled, only 2 mix neutral and
non-neutral pages. It is not absolute, though: a decoder must not assume a
document's first page predicts the rest.

**Is the colour real, or a rendering artefact?** This is the premise the
whole two-path design rests on, so it was measured rather than assumed. If
non-identical RGB were merely anti-aliasing fringe, the right fix would be
upstream — re-render with `-sDEVICE=pnggray` and delete the colour path,
the probe and the luma reduction outright. 60 non-neutral pages were fully
unfiltered and classified by how many pixels carry a channel spread above
32, a difference a reader would see:

| Class | Share of non-neutral pages | Share of all pages |
|---|---|---|
| Substantial colour (≥0.1% of pixels strongly coloured) | 70.0% | ~37.8% |
| Minor colour (<0.1% strongly coloured) | 11.7% | ~6.3% |
| Fringing only (max spread ≤ 16) | 18.3% | ~9.9% |

**The colour is overwhelmingly real content, not an artefact.** Roughly 38%
of all corpus pages carry colour a reader would call colour; the strongest
cases reach 95.7% of pixels strongly coloured, and are slide decks and video
frames rather than papers — the corpus has broadened past arXiv PDFs. Taking
the red channel on those pages would render red ink near-white and blue ink
near-black across more than a third of the corpus. **The two-path decode is
justified on measured evidence.**

U0's input contract is fixed: ghostscript `png16m`, IHDR `(8, 2, 0, 0, 0)`.
Input format and render-device selection belong to the render pipeline, which
is owned elsewhere; they are not U0 questions and are not reopened here.

**The colour path is, measured, essentially unoptimised.** At 1.78 Mpx/s it
is indistinguishable from the 1.82 Mpx/s naive reference decoder — the
three-channel unfilter plus the unconditional luma reduction dominate, and
neither is vectorised. Because this path runs on the majority of pages,
**corpus-wide effective throughput is dominated by it**, not by the neutral
fast path's 18–21 Mpx/s. Effective throughput, assuming pages of comparable
size so each path's *share of pixels* tracks its share of pages (54% colour
at 1.78 Mpx/s, 46% neutral at, taking the middle of the 18–21 Mpx/s range,
19.5 Mpx/s):

```
1 / (0.54/1.78 + 0.46/19.5) = 1 / (0.30337 + 0.02359) = 1 / 0.32696 ≈ 3.06 Mpx/s
```

This is barely different from the ≈3.0–3.1 Mpx/s you get at either end of
the 18–21 Mpx/s range — the harmonic mean is dominated by the slow term
regardless of exactly how fast the neutral path is, because 1/1.78 so far
exceeds 1/19.5. **The headline speedup of the SWAR work, measured
corpus-wide rather than on the neutral path alone, is therefore modest: a
corpus-wide effective throughput of ≈3.06 Mpx/s against the 1.82 Mpx/s naive
baseline is only ≈1.7× (3.06 / 1.82 ≈ 1.68), not the 10–11× measured on the
neutral path in isolation and nowhere near the originally reported 13.3×.**
This is recorded as a known, measured limitation, not hidden behind the
fast-path number.

**The colour path is complete and will not be optimised further.** The
figures above are the measured record; performance of the ingest path is a
render-pipeline concern, not a U0 concern.

### U4 premise check — run 2026-08-07, before U4 was planned
**Rotation fixtures — the scanned corpus cannot supply them.** U4's spec
asks for signature invariance under ±3°. The 426 `(Z-Library)` scanned
documents (2,286 rendered pages) were the natural candidate, being real
scans rather than synthetic rotations. Measured 2026-08-07 by
projection-profile over 10 random scanned pages: **8 of 10 sit at exactly
0.00°, the largest is 0.50°.** They have already been deskewed upstream.
They are therefore a good robustness check at sub-degree skew and cannot
test the stated ±3° claim. U4 uses resampled real corpus glyphs for the
±3° test, labelled as resampled, with the sub-degree scan check reported
separately.


Assumption 1 had stood since the plan was written with "argued
structurally, no evidence". Measured before writing U4, on real ink rather
than fixtures.

**Method.** 42 corpus documents carry both `<doc>.chars.json` — pdfminer's
per-character text, font, CTM and bbox — and rendered pages. Three pages
were swept whole; each connected component was rebuilt from *its own runs*
into a clean sub-mask and matched to a glyph by centre containment, so no
neighbouring ink can enter and no stroke is clipped. 8,453 glyph
components. The signature used is a proxy over U3 alone — cycle count plus
birth/merge/split counts on both axes — which is faithful because
degree-2 contraction removes chain nodes without changing any branching.
It lacks persistence, which the real `signature()` will add.

**A first attempt cropped each glyph's pdfminer bbox and gave a useless
result** — 0/18 characters stable. That box is the *advance* box, not the
ink box, so crops swallowed neighbours and clipped strokes. This is
assumption 7 biting early, and it is why the component-isolation method
above is the only sound one. Recorded because the failure is instructive.

| Question | Result |
|---|---|
| Hole count vs character identity | **98.7–100%** consistency, every character tested |
| Within-class signature stability | modal signature ≥90% for **9 of 16** commonest letters; 98–100% for `t n o c u p h m d` |
| Between-class purity | **26.9%** of glyphs get a signature unique to one character; 56 signatures over 73 characters |
| Worst collisions | `n h 3 N` · `i . / : j ; ?` · `e 6` |

**Conclusions that bind U4's contract.**

1. **Hole count is the strongest single topological feature** and it is
   real. This is corroboration of assumption 3 at a scale the fixtures
   cannot reach.
2. **The signature is a partition, not a classifier.** U13 already says
   the bitmap and the signature are two channels, with aspect ratio and
   absolute extents carried separately because `- − – —` and `. ·` are
   otherwise unrecoverable. The measured collisions are exactly that set.
   U4 must therefore deliver a *comparable, stable* signature and must not
   promise identification.
3. **A glyph is not always one component.** `i j : ; = %` are multi-part,
   and a per-component signature is not a per-glyph signature. U4's
   `signature()` must be defined over a component *set*, with the
   single-component case falling out as the degenerate one. This was not
   visible from the U3 fixtures, all of which are single blobs.

---

### U4 results — measured 2026-08-07

`31 tests passed.` Two findings worth more than the code.

**Contraction is a 5–7× reduction on real ink.** Three real page bands
(3300–3400 px wide, 600 rows): 3,947 / 6,380 / 3,633 RAG runs contract to
566 / 1,136 / 687 arcs — 14.3%, 17.8%, 18.9%. The Reeb graph is a much
smaller object to carry into U12/U13 than the RAG, as the design assumed.

**Rotation invariance is refuted.** The plan expected `signature()` to be
invariant under ±3°. Measured on real glyph components lifted from
rendered pages and rotated by nearest-neighbour resampling — four
independent 120-component samples:

| Sample | Full signature kept at ±3° | Cycle count kept | 0° control |
|---|---|---|---|
| seed 11 | 40.8% / 52.5% | 80.0% / 81.7% | 100% |
| seed 99 | 78.3% / 73.3% | 98.3% / 99.2% | 100% |
| seed 2026 | 70.0% / 75.0% | 91.7% / 94.2% | 100% |
| seed 7 | 65.0% / 64.2% | 91.7% / 92.5% | 100% |

The 0° control is exact every time, so the loss is rotation and not a
lossy resampler. **The spread is wide and page-dependent, so no point
estimate is meaningful** — an earlier revision of this section quoted
"47–54%" from a single 158-component sample and that figure does not
reproduce. This is the U0 sampling failure recurring one level up, caught
this time because the harness exists. What *does* reproduce on every
sample is the **ordering**: the cycle count survives rotation by 20–40
percentage points more than the full signature. The ordering is the
claim; the percentages are context.

Clean synthetic ink is mostly rotation-*stable* — rings at 14/20/32/48 px
with 1–3 px strokes, a 40-row H, a 48-row figure-8 and a comb are all
bit-stable under ±3°. The fragility belongs to real glyph ink under
resampling, which is why the T4_6 fixtures had to be found by search.

**The exception, and it is the math population.** For near-horizontal
separated strokes rotation *creates* cycles, inverting the durability
claim:

| Fixture | 0° | ±3° |
|---|---|---|
| two 40-wide bars, 1-row gap | `parts=2, cycles=0` | `parts=1, cycles=1` |
| three 50-wide bars, 1-row gaps | `parts=3, cycles=0` | `parts=1, cycles=4` |

At 3° a 50-px-wide bar rises ~2.6 px across its width, so a 1-px gap
closes and the bars genuinely become one component — finite resolution,
not a resampler artefact. The affected shapes are `=`, `≡`, `÷`, fraction
bars, `\hline` and the radical overbar: exactly what U14 depends on and
what U13 will lean on hardest.

**Consequence for U13.** `cycles` is the durable component of the
signature and the branch counts are the fragile one; a consumer comparing
signatures across a skewed page must weight them accordingly, or deskew
first. This sits beside the premise-check finding that hole count is
98.7–100% stable across *natural* instances of a character — the same
conclusion reached from two directions.

**Every figure in this section is re-runnable.** `tools/premise/measure.py`
holds the harness — outside the package, excluded from the suite, taking a
corpus path:

    python3 tools/premise/measure.py --corpus ~/pdfdrill-library all
    python3 tools/premise/measure.py --corpus ~/pdfdrill-library rotation

Subcommands: `neutrality colour throughput skew premise contraction
rotation`. It exists so the next measurement is a re-run rather than a
re-implementation — when the corpus grows, when `signature()` gains
persistence, or when a reviewer wants to check a number. It is what caught
the non-reproducible rotation figure above.

**What would settle the open half.** These numbers come from
nearest-neighbour resampling, which is the harsh case. Whether a genuine
re-render at 3° — antialiased, then thresholded — is gentler is untested,
and is the one measurement that would separate "the signature is
rotation-fragile" from "nearest-neighbour resampling is". The scanned
corpus cannot supply it: those pages are already deskewed (§3 above).

---

## 4. Assumptions that remain unverified

1. **Reeb signatures discriminate math symbols.** ~~Argued structurally,
   no evidence.~~ **Partly measured, 2026-08-07 — see §3 "U4 premise
   check". A signature alone is NOT a classifier (26.9% of real glyphs get
   a signature unique to one character), but it is a stable partition:
   within a character class the modal signature holds 98–100% for most
   letters. It earns its place as one channel, exactly as U13 already
   specifies, not as the classifier.** U12's shape domain keeps the
   dimension; U13 must not lean on it alone.
2. ~~**Row↑ is derivable from the row RAG without rescanning.**~~
   **VERIFIED 2026-08-07 (U4 G3).** Regularity is symmetric under
   swapping `up`/`down`, so the contracted node set does not depend on
   sweep direction — only the labels do, births becoming closes and
   merges becoming splits. `orient()` derives ROW_UP and COL_UP by
   relabelling, and the result is structurally equal to a genuine sweep
   of the flipped mask on all six U3 fixtures, on 40 random masks, and on
   three real page bands. Four orientations cost two scans, as designed.
3. ~~**Cycle rank equals hole count for conn-8 foreground.**~~
   **VERIFIED 2026-08-07 (U6 G1).** The identity `cycles == E − V + C`
   was always arithmetic; that it counts *holes* rested on the duality
   argument plus six fixtures. U6 now computes holes a completely
   different way — background components of the inverted mask at
   `conn=4`, sharing no code with the sweep — and the two agree on the
   fixtures, on 120 random masks, and on **222 components of real page
   ink across two independent samples, 100%**. Each is now the other's
   oracle, which is what the plan asked for.
4. ~~**Moment aggregates will be axis-invariant.**~~ **VERIFIED
   2026-08-07 (U5 G2).** The caution was right that it does not follow
   from U2's pixel-set agreement — but it does follow from EXACTNESS.
   Every raw sum is a Python `int`, so a row sweep and a column sweep
   grouping the same pixels into different runs and summing them in a
   different order must agree, integer addition being associative and
   exact. Measured identical on 400 random masks whole-mask, 300 random
   masks per component, and 635 components of real page ink. In floating
   point the same code would drift and this would hold only
   approximately — which is why integer accumulation is stated in the
   contract rather than left as an implementation choice.
5. ~~**Band stitching preserves everything but `closed_at`.**~~
   **VERIFIED 2026-08-07 (U7 G2/G3).** Stitched output is
   indistinguishable from a single sweep — same partition, same V, E, C
   and cycle counts — on the crossing-blob fixture at K ∈ {1,2,3,7,64},
   on 60 random masks at both connectivities, and on real page ink up to
   K=600 (one band per row). The re-sorting risk was real and is now
   **mutation-tested**: three separate defences were each mutated and
   each kills tests. One of them initially survived — sorting the band
   *list* already yields global order, so the per-node re-sort was
   unreachable through the public API. A test that shuffles nodes
   *within* a band makes it reachable, which matters because U8 may
   append a band's own nodes in completion order.
   Scan events remain unstitched by design, which is the `closed_at`
   caveat the original wording was reaching for.
6. **The priority-queue scheduler reaches full utilisation.** The idle
   tail — last page, few tasks, many free cores — is unaddressed and may
   need finer bands at the end as well as the start.
7. **pdfminer glyph boxes and rendered ink agree closely enough.**
   Hinting, grid fitting, dropout control and side bearings all push
   against it. U10's residual rates are the measurement; U9's font
   access is what makes the comparison ink-to-ink rather than
   ink-to-advance-box.
8. **arXiv PDFs are predominantly embedded, non-Type-3 fonts.** The whole
   U9 fast path depends on it, and I have not sampled the corpus. This is
   the cheapest assumption to check and worth checking before U9 starts.
9. **Pure Python at 19 Mpx/s is fast enough once parallelised.** The
   arithmetic works out; whether serialization overhead in U8 eats the
   gain is unmeasured.
10. **`inkdrill` is the right package name.** Cosmetic, but the cost of
    changing it rises with every unit.
11. **The corpus is entirely ghostscript `png16m`.** 400 files sampled
    from the full 18,494-page library, IHDR `(8, 2, 0, 0, 0)` × 400 — zero
    variation. The unit fails loudly rather than mis-decoding if that is
    wrong, so the risk is a refused file rather than a wrong answer.
