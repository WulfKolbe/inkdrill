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

**U0 `io.py` — ghostscript png16m ingest.**
*No dependencies.*
Contract: `read_png` returning `PngImage(width, height, gray, dpi, neutral)`;
`load_mask` composing it with U2's `binarize`. G1–G7.
**Scope limit stated up front:** IHDR exactly `(8, 2, 0, 0, 0)` — the output
of the ghostscript `png16m` device. Everything else raises `UnsupportedPNG`.
Tests: CRC and truncation rejection; every rejected IHDR variant; all five
scanline filters against a naive reference decoder held as the oracle;
multi-IDAT concatenation; `pHYs` present and absent; the neutrality
equivalence G5 that the two-path decode rests on.
**Status: 47 tests passed.**

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
Tests: node/edge counts on the U3 fixtures; **row↑ derived by reversal
equals a genuine reversed sweep**; persistence separates a 2-px speck from
a stroke; signature is invariant under translation and under a ±3° rotation
of the fixture.

**U5 `aggregate.py` — moment aggregates per component.**
*Depends: U3.*
Contract: area, extents, `Σx Σy Σxx Σyy Σxy` accumulated from runs in
closed form; centroid; central moments; principal axis as a **unit
vector**, never an angle; elongation with the λ₂ ≥ 1/12 floor (the
variance of a unit pixel) so 1-px strokes stay finite.
Tests: hand-computed values on a 20×20 fixture; **row-sweep and col-sweep
produce identical moments**; a synthetic rotated rule recovers its angle
through `angle_deg_screen`; the λ₂ floor engages exactly at 1-px width.

**U6 `nest.py` — holes, containment forest, ordering relations.**
*Depends: U3, U5.*
Contract: holes as background components of the inverted local mask
(`conn=4`); recursion for depth > 1; the four relations distinguished in
the design discussion — `hole_of`, `ink_in_hole`, `bbox_contains`,
`nesting_chain`; the containment forest with figure/ground depth parity;
the table case (hole lattice of a connected frame) and its disconnected
counterpart (collinear rule grouping).
Tests: hole count from `nest` equals `Component.cycle_count` from U3 —
**two independent computations, one the oracle for the other**; nested
frames give depth 0/1/2; a synthetic table frame yields an m×n hole
lattice; a `\fbox`-like fixture yields `ink_in_hole` and *not* `hole_of`.

### Parallelism

**U7 `band.py` — band splitting and seam stitching.**
*Depends: U3, U5.*
Contract: split a mask into K bands; sweep each independently with
disjoint label spaces; stitch by applying the U3 adjacency predicate
across each seam and merging components. Moment aggregates add; **runs
and RAG nodes must be re-sorted after concatenation** — this is the
specific latent bug the old code base carries.
Tests: output identical to K=1 for K ∈ {1,2,3,7,64} on a fixture with a
blob crossing every seam; run order sorted after stitching; cycle-rank
identity survives stitching.

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
Ran 150 tests — OK
```

| Unit | Tests | Result |
|---|---|---|
| U0 `io.py` | 47 | passed |
| U1 `space.py` | 36 | passed |
| U2 `raster.py` | 31 | passed |
| U3 `sweep.py` | 36 | passed |

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
| `read_png`, neutral fast path (`_decode_gray_neutral`, SWAR) | **median 24.1 Mpx/s** (n=25 random neutral pages, range 8.97–40.93 -- wide, see below) |
| `read_png`, colour path (`_decode_gray_colour`, 3-channel + luma) | **median 1.78 Mpx/s** |
| naive per-byte reference decoder | median 1.82 Mpx/s |
| speedup, fast path over naive | **13.3×** |

**The neutral-path spread is wide, not a tight band.** An independent sample
of 25 random neutral pages (best-of-3 timing of `_decode_gray_neutral` per
page, excluding chunk parsing and inflate) measured median 24.1 Mpx/s with
range 8.97–40.93 Mpx/s across the sample — page-to-page variance driven by
per-row filter mix (a Paeth-heavy page runs several times slower than an
Up-heavy one, matching the sequential-Paeth caveat in `io.py`) and by page
size. Earlier revisions of this row understated the spread by roughly 5x at
both ends; stated plainly here rather than hidden behind the median.

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
non-neutral pages — consistent with it tracking a render setting rather
than page content. It is not absolute, though: a decoder must not assume a
document's first page predicts the rest.

**The colour path is, measured, essentially unoptimised.** At 1.78 Mpx/s it
is indistinguishable from the 1.82 Mpx/s naive reference decoder — the
three-channel unfilter plus the unconditional luma reduction dominate, and
neither is vectorised. Because this path runs on the majority of pages,
**corpus-wide effective throughput is dominated by it, roughly 3 Mpx/s, not
the 24.3 Mpx/s of the neutral fast path.** This is recorded as a known,
measured limitation, not hidden behind the fast-path number.

**Deferred optimisation opportunity, not implemented.** The Up filter is
byte-position-agnostic, so the SWAR trick used in the neutral path
generalises directly to the three-channel row using masks of width `w*3`
— no channel separation needed. That would accelerate the ~73.0% of colour
rows that are Up-filtered. It is capped by the unconditional per-pixel luma
reduction and by the remaining ~27% Sub/Average/Paeth rows, which stay
sequential, so the expectation is a few-fold gain on the colour path, not
parity with the neutral path's 24.3 Mpx/s. Out of scope for this task.

---

## 4. Assumptions that remain unverified

1. **Reeb signatures discriminate math symbols.** Argued structurally,
   no evidence. U4 and U13 are where it gets tested; if it fails, U12's
   shape domain loses its most interesting dimension.
2. **Row↑ is derivable from the row RAG without rescanning.** Follows
   from adjacency being symmetric, but the implementation is U4 and
   untested. This is the claim that makes four orientations cost two
   scans.
3. **Cycle rank equals hole count for conn-8 foreground.** The identity
   `cycles == E − V + C` is verified (it is arithmetic). That it counts
   *holes* is verified only on the fixtures — ring, figure-8, A, nested
   frames — plus the duality argument. U6 provides the independent
   oracle.
4. **Moment aggregates will be axis-invariant.** U2 proves the *pixel
   sets* agree; that the moments agree is U5's test and does not follow
   automatically, since the accumulation order differs.
5. **Band stitching preserves everything but `closed_at`.** The moment
   algebra adds by construction; run and node re-sorting is the open
   part and is U7's main risk.
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
