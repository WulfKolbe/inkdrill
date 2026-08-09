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

**Companion documents.** [`state.md`](state.md) is the map — goals, unit
status, and the single next step. [`algorithms.md`](algorithms.md) is the
algorithm and inner-loop performance reference, written by the project
auditor, with a ranked improvement list. This file remains the
authoritative per-unit record and the home of every measurement.

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
~~Contract: tasks `(page, axis, band)` with priority `(page_index,
band_index)`; … band count per page large for page 1 …
`multiprocessing.shared_memory` for the mask.~~ **Three parts of that
specification were measured before this unit was written and did not
survive — see §3 "U8 premise check".**

Contract as built: tasks `(page, axis)`; workers pull lowest key first;
results ordered by key, never by completion. `RunReport` reports measured
wall time, busy time, utilisation and the Amdahl ceiling.
**No band tier** — band parallelism only touches the sweep, which is
5–15% of per-page work, so its ceiling is 1.17× on the target workload.
**No shared memory** — serialization was measured at 0.08–0.21 MB per
page against a 2.7–3.7 MB mask, so it is not the constraint.
**`workers=1` uses no pool at all**, which is what makes it the oracle
the parallel paths are checked against.
Tests: identical output at every worker count including 1; the task that
finishes *last* still appears first if its key says so; duplicate keys
refused; a raising job surfaces rather than yielding a short result list;
utilisation and Amdahl ceiling reported. Both re-sorting and
failure-surfacing are mutation-tested.
**Status: 22 tests passed.**

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
Type 3, width-only, and scanned pages fall back to U11. Measured cost of
that limit: **0.5–2% of glyph instances**, not the 5% the per-font view
suggests or the 83% the per-document view suggests — see §3.

**BUILT SO FAR: the inventory half only.** `font.py` covers identifying
fonts via `pdffonts`, resolving a glyph's font name to a record, and
glyph-weighted coverage with every rejection naming its reason. Measured
against 25 real documents and 1,276,504 glyph instances: 93.93% on the
fast path, against 95.90% from the premise check's independent 40-document
sample.
**NOT BUILT: rasterization.** No CFF or TrueType outline parsing, no scan
conversion, no reference blob, no `BASE`/`MATH` table access. In pure
standard library that is a substantially larger piece than any unit so
far and it needs its own contract and its own premise check. It is named
here rather than half-built, and the split is not arbitrary: everything
in the inventory half is exactly and hermetically testable against
fixture text, while a rasterizer needs its own oracle.
**Status: 52 tests passed (inventory half).**

**U10 `gold.py` — pdfminer alignment and the many-to-many matcher.**
*Depends: U1, U9.*
Contract: build the `SpaceGraph` from the reconstructed per-character CTM
plus MediaBox, `/Rotate`, dpi and any crop — **composition, not a
formula**; match ink components to glyphs; report the four residual
classes (1↔1, 1↔N, N↔1, unmatched) rather than discarding them; export
`GoldGlyph` in COCO/PAGE form.
Contract note from the premise check: **the matcher does not split
blobs.** One ink blob straddling two glyphs is 0.02% of assignments at
400 dpi, so it is reported and left to the caller. A component matches a
glyph when its CENTRE lies in the glyph box — pdfminer's box is the
ADVANCE box, so overlap against it is systematically wrong.
Tests: corner-to-corner page mapping, the y flip, crop and `/Rotate`,
invertibility and further composition; every component and every glyph in
exactly one class over 100 random layouts; centres beating overlap on a
straddling component and on a narrow glyph in a wide advance box; COCO
export carrying the match class and component ids.
**Scope limit:** no rasterization, so this compares ink to the *advance*
box, not ink to ink. That comparison needs U9's rasterizer half.
Two defects surfaced after the auditor's algorithm review and were
reproduced exactly: `rows()` seeded from the MAXIMUM height, so one 50 px
brace spanning three body lines collapsed `[8,8,8]` into `[25]` — **fixed**,
it now seeds from the modal height; and `group()` absorbs a display big
operator's limits into the operator — **confirmed, not fixed**, because a
display limit does not vertically overlap its operator so `detect_scripts`
never classifies it, and telling an accent from a limit geometrically is
symbol identity again. Pinned by
`test_a_display_operator_absorbs_its_limits_KNOWN_DEFECT`.
**Status: 35 tests passed.**

### Application

**U11 `coverage.py` — MathPix cross-check.** *Depends: U3, U5.*
The four residual classes: ink with no region, region with no ink,
**blob straddling a region edge** (the case that clips tall `∫` and `∑`
limits), ink under overlapping regions. Independent of U4–U10 — can be
built in parallel with the topology track for an early result.

**Containment, not centres — the opposite of U10's rule, and the
inversion is the point.** U10 matches on centres because pdfminer gives
an *advance* box. Here a region is a real boundary another tool drew, so
a blob crossing it IS the finding; centres would call a clipped `∫`
comfortably inside and report nothing.

Measured on real scanned pages with line-level OCR, two samples (6 pages,
then 8 independent):

| Class | agg. | per-page median | per-page max |
|---|---|---|---|
| ink inside one region | 89.2% | — | — |
| **ink with no region** | 8–10% | **0.53%** | **100.00%** |
| **ink straddling a region edge** | 0.8–2.3% | 2.05% | 33.63% |
| ink under overlapping regions | 0.0–0.3% | — | — |
| region with no ink | 0.00–0.03% | — | — |

**The aggregates are stable and nearly useless; the spread is the
finding.** One page reports 100% missed — 3 regions against 950 ink
components, an OCR failure the aggregate would bury — and another 33.63%
straddle on a diagram where regions cut through content. Those pages are
the deliverable. Fourth time a small-sample aggregate has misled here,
after U0's colour fraction, U7's density dependence and U10's residual
rates.

Tests: containment vs centres, with a fixture whose centre is inside and
whose body overflows; every component and every region in exactly one
class over 120 random layouts; overlapping regions as their own class;
degenerate and sub-threshold boxes dropped with the count showing it;
regions transformed by composing an affine. Branch sweep: 8 conditions,
0 survivors.
**Status: 24 tests passed.**

**U12 `domains.py` — conceptual-space feature domains.**
*Depends: U4, U5, U6, U9.*
Separable domains: shape, size, position, **transform** (its own domain,
so rotation and shear stop contaminating shape), topology, typographic.
Design test per Gärdenfors: a dimension earns its place when the concepts
of interest become **convex** in it.

**The design test is shipped, not described.** `convexity()` and
`mutual_information()` are part of the unit, so a future dimension is
added by measuring it. Every dimension carries its measured score, and an
unmeasured one is visibly unmeasured.

Measured on 5,436 real glyph instances over 23 character classes with 40+
examples each; random baseline 0.043, H(class) = 4.524 bits:

| dimension | domain | nmi | distinct | ceiling | **efficiency** |
|---|---|---|---|---|---|
| aspect | size | 0.634 | 166 | 0.968 | 0.65 |
| elongation | shape | 0.627 | 440 | 0.968 | 0.65 |
| width | size | 0.584 | 53 | 0.956 | 0.61 |
| fill | shape | 0.561 | 359 | 0.969 | 0.58 |
| area | size | 0.544 | 272 | 0.975 | 0.56 |
| height | size | 0.418 | 42 | 0.759 | 0.55 |
| splits | topology | 0.375 | 6 | 0.423 | **0.89** |
| merges | topology | 0.322 | 5 | 0.402 | **0.80** |
| births | topology | 0.255 | 5 | 0.332 | **0.77** |
| cycles | topology | 0.246 | 3 | 0.257 | **0.96** |
| depth | topology | 0.220 | 2 | 0.229 | **0.96** |

**CORRECTED 2026-08-08.** An earlier revision concluded from the `nmi`
column that "every topological dimension ranks below every geometric one"
and read that as a reason to demote the topological channel in U13. That
conclusion was wrong.

Normalised MI is bounded by `H(X)/H(class)`, so against 23 classes a
3-valued dimension cannot exceed **0.350** however perfectly it separates,
and a 2-valued one 0.221. The raw ranking cannot distinguish *carries
little information* from *has few values* — and `cycles` has three values,
`depth` two. **Corrected for that ceiling the ordering inverts:** topology
is the most efficient per available bit (0.77–0.96), geometry the least
(0.55–0.65). Topology is narrow, not weak.

**Marginals also cannot see joint information**, and Gärdenfors' criterion
is about a region in a *domain*, not its projection onto one axis:

| domain | dims | joint nmi | best marginal |
|---|---|---|---|
| size | 4 | 0.960 | 0.634 |
| shape | 2 | 0.913 | 0.627 |
| **topology** | 5 | **0.713** | 0.375 |
| all | 11 | 0.996 | — |

TOPOLOGY jointly reaches nearly double its best marginal — fragmented
across five narrow dimensions, not uninformative. **U13 should weight the
topological channel on the joint figure, not the marginal ranking.**

What survives: extents and aspect carry the most marginal bits and U13
should still weight them heavily. What does not survive: any reading of
the marginal ranking as grounds for demoting topology.

**Stability is a third property.** `cycles` is 98.7–100% consistent within
a class (U4), 0.96 efficient, and 0.246 in absolute terms. Reliable,
narrow, low-information — the profile of a **verifier, not a
discriminator**.

**Scope limits, stated:** TYPOGRAPHIC is declared and **empty** — it needs
U9's reference lines, which are not built. TRANSFORM is declared and
empty — it needs a per-character CTM from U10. Both are named rather than
populated with guesses. No Morton code: it encodes two dimensions already
present and belongs to a consumer wanting spatial locality.
Tests: domain partitioning; `describe()` total over missing inputs; the
design test scoring 1.0 on a separating dimension and near baseline on a
random one; outlier robustness; every recorded score beating baseline.
Branch sweep: 3 survivors, all confirmed equivalent mutants.
**Status: 40 tests passed.**

**U13 `classify.py` — nearest neighbour, two channels.**
*Depends: U9, U12.*
Normalized glyph bitmap **plus** Reeb signature as an independent channel,
plus aspect ratio and absolute extents carried separately (without them
`- − – —` and `. ·` are unrecoverable). Escalate beyond nearest neighbour
only after seeing the confusion matrix.

**The confusion matrix was the premise check — and the SPLIT RULE turned
out to be the experiment.** An earlier revision reported "half train half
test" without saying half by *what*. The answer was: by component, over
pages appearing on both sides, so nearly every test glyph had a
near-identical twin — same document, page, font and size — in training.
Measured both ways on the same 8 pages, changing only the split rule:

| channel | by component (leaky) | by document | **by font** |
|---|---|---|---|
| signature only | 11.8% | 11.2% | 9.2% |
| **extents only** | 93.7% | **43.8%** | 29.5% |
| **bitmap only** | 95.7% | **94.0%** | **61.5%** |
| bitmap + extents | 95.8% | 95.8% | 68.8% |
| **all three** | 96.0% | 95.7% | **86.3%** |

**Extents was almost entirely leakage — 93.7% → 43.8%.** Absolute height
and width identify the document's body size, not the character. The
previously reported 97.1% was an artefact of the protocol.

**The bitmap is document-independent but not font-independent — 94.0%
across documents, 61.5% across fonts.** Normalised shape survives a
change of paper and of body size; it does not survive a change of
typeface. (An external PIL probe independently found 62.1% cross-size and
72.2% cross-font; the corpus reproduces this at 61.5% over 44 font
groups, so the axis is testable from data already in hand.)

**The channels only earn their keep when the problem is hard.** Across
documents they add +1.7pp to the bitmap; across fonts they add **+24.8**,
61.5% → 86.3%. A previous revision concluded from the easy split that the
signature "adds nothing measurable" — also protocol-dependent. `units.md`
was right to specify several channels and the easy protocol hid why.

**So the escalation decision splits by population.** Within a document,
do not escalate. Across fonts, 1-NN is not enough — and that is the
condition for the ~5% of glyphs U9 found without a usable embedded font,
and for the whole scanned corpus.

**The measured population is BODY TEXT.** 59 classes survived an
"at least 12 instances" filter over 8 pages; the only non-ASCII survivors
are `“”` and `ﬁ`. **Not one mathematics symbol.** So none of these
numbers speak to maths symbol classification, which is this project's
first application. More pages will not fix it — a rare symbol stays rare;
it needs pages selected for maths content. The class filter was one line
and a decision, so the harness now prints the surviving class list beside
the accuracy table.

**Every residual error is structural**, not a modelling failure:
`i . : 1 l` are the multi-component and thin-stroke cluster a
per-component classifier sees half of (U4 and U10 hit the same thing; the
fix is grouping, in U14), and `s/S X/x k/h` are case pairs separated only
by absolute size — which is why extents still earns +1.8pp on top of the
bitmap even though it does not generalise alone.

Tests: scale invariance; each distance a metric; runner-up and finite
margin; deterministic tie-breaking; channels independently disable-able;
the signature as verifier; confusion reporting pairs not just accuracy.
Branch sweep: 24 probed, 3 real gaps closed, 5 equivalent mutants.
Re-run: `measure.py classify --split document|component|page|font` — the
split rule is an explicit argument because it moves the answer by 50
points, and the harness prints the surviving class list because the class
filter is a decision too.
**Scope limit:** templates come from labelled page ink via U10, not from
font-rendered references — that needs U9's rasterizer half.
**Status: 31 tests passed.**

**U14 `mathstruct.py` — expression structure.** *Depends: U6, U12, U13.*
Reference-line estimation per row; sub/superscript from geometry alone
against pdfminer's `role` as label; big operators and their ranges; fence
matching; structure tree → LaTeX targeting the existing DOCMODEL
projection.

**BUILT: rows, reference lines, script detection, component grouping.
NOT BUILT: big operators, fence matching, structure tree, LaTeX.** All
four of the latter need reliable symbol identity for `∑ ∫ ( [`, and U13's
measured population contained **no mathematics symbols at all** — its
class filter excluded every one as too rare. Fence matching on a
classifier never measured on a fence would be a structure tree resting on
nothing. The geometry is measurable now; the rest is named.

**`units.md` specified "against pdfminer's `role` as label". There is no
`role` field in `chars.json`.** The label used instead is `size` — the
PDF's own font metric, which the geometry side never sees, so the test is
not circular. Measured on 37,759 glyphs over 12 pages:

| | |
|---|---|
| precision | **100.0%** (0 false positives in 37,759) |
| recall | 13.5% |
| positives in population | 2.04% |

**The precision figure is trustworthy and the recall figure is not.** The
label is a proxy — "smaller than the row's modal size" catches captions,
footnotes and mixed-size headings, not only scripts — so most misses are
probably not scripts at all. 13.5% is a lower bound against an
over-inclusive label, not a count of missed scripts. `detect_scripts` is
therefore documented as a high-precision *detector*, not a classifier.

Three faults surfaced during construction, all real:
**rows must be seeded tallest-first** — in reading order a superscript
opens a row of its own before the line it belongs to exists, and a
determinism test cannot catch it because the wrong answer is perfectly
deterministic; **grouping needs stacking, not width** — horizontal
overlap alone merges a narrow letter sitting inside a wide one, since
parts of one glyph sit *above* each other while adjacent letters sit
*beside* each other; and **row overlap must be measured against the
joining glyph's own height**, or the threshold that suits body text
excludes exactly the scripts this unit exists to find.

Tests: row partition over 60 random layouts; modal reference lines
resisting a descender and a tall bracket, with a fixture where mode and
median differ; both script signals required; grouping of `i` and `:` but
not of adjacent letters. Branch sweep: 28 probed, 3 real gaps closed, 3
equivalent.
Two defects surfaced after the auditor's algorithm review and were
reproduced exactly: `rows()` seeded from the MAXIMUM height, so one 50 px
brace spanning three body lines collapsed `[8,8,8]` into `[25]` — **fixed**,
it now seeds from the modal height; and `group()` absorbs a display big
operator's limits into the operator — **confirmed, not fixed**, because a
display limit does not vertically overlap its operator so `detect_scripts`
never classifies it, and telling an accent from a limit geometrically is
symbol identity again. Pinned by
`test_a_display_operator_absorbs_its_limits_KNOWN_DEFECT`.
**Status: 35 tests passed.**

### Deferred

`raster_region` detection (halftone / line-graphic discrimination) after
U14, per the stated priority. The one part worth building early is the
**guard**: an active-component ceiling that fails loudly rather than
consuming memory when a screened figure appears.

---

## 3. Status — measured, not asserted

Run: `python3 -m unittest discover -s tests -t .`

```
Ran 612 tests in 2.5s
OK (skipped=21)
```

The 21 skipped are the four opt-in corpus modules:
`tests/test_pngio_corpus.py` (4) and `tests/test_source_truth_corpus.py`
(5), both gated on `INKDRILL_CORPUS`, and `tests/test_type1_corpus.py`
(6) and `tests/test_charstring_corpus.py` (6), both gated on
`INKDRILL_TYPE1`. Neither
runs by default. The hermetic count -- what actually runs on a bare
checkout -- is 612 - 21 = 591.

`test_type1_corpus` is gated rather than defaulted to the system TeX
tree deliberately. Defaulting it would have been free coverage on most
machines, and would have made the count in this table depend on which
fonts a machine happens to have installed.

| Unit | Tests | Result |
|---|---|---|
| U0 `pngio.py` | 49 | passed |
| U1 `space.py` | 36 | passed |
| U2 `raster.py` | 31 | passed |
| U3 `sweep.py` | 36 | passed |
| U4 `reeb.py` | 37 | passed |
| U5 `aggregate.py` | 30 | passed |
| U6 `nest.py` | 29 | passed |
| U7 `band.py` | 29 | passed |
| U8 `sched.py` | 22 | passed |
| U9 `font.py` | 52 | passed |
| U9 `type1.py` | 39 | passed 2026-08-09 |
| U9 `charstring.py` | 33 | passed 2026-08-09 |
| U10 `gold.py` | 38 | passed |
| U11 `coverage.py` | 24 | passed |
| U12 `domains.py` | 40 | passed |
| U13 `classify.py` | 31 | passed |
| U14 `mathstruct.py` | 35 | passed |

49 + 36 + 31 + 36 + 37 + 30 + 29 + 29 + 22 + 52 + 39 + 33 + 38 + 24 + 40 + 31 + 35 = 591,
matching the hermetic count above.

Regression: U1 and U2 re-run clean after U3 landed. U0 lands after U3 and
depends on U2 (`binarize`) alone; the full suite stays green.

Corpus smoke test (opt-in, `tests/test_pngio_corpus.py`, skipped in the count
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
core. ~~so U7/U8 band parallelism is what makes the first-page latency
target reachable, exactly as the design argued.~~

**That last clause was a design-time assertion, never measured, and the
measurement does not support it — see "U7 stitch cost" below.** Band
parallelism is capped at 2–3× by the serial stitch, however many cores
are available. First-page latency has to come from somewhere else.

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

### U5-U7 results — measured 2026-08-07

Recorded here because §3 is where measured results live; the assumptions
they close are struck through in §4.

**U5, axis invariance (assumption 4).** Row and column sweeps produce
IDENTICAL moments — 400 random masks whole-mask, 300 per component, and
635 components of real page ink. The caution in the original wording was
right that this does not follow from U2's pixel-set agreement; it follows
from exactness. Every raw sum is a Python `int`, so a different grouping
and a different summation order must still agree. In floating point the
same code would drift.
Re-run: `tools/premise/measure.py --corpus <dir> moments`

**U6, holes by an independent route (assumption 3).** `nest` computes
holes as background components of the inverted mask at `conn=4`, sharing
no code with the sweep. It agrees with U3's cycle rank on the fixtures,
on 120 random masks, and on **222 components of real page ink across two
independent samples, 100%**.
Re-run: `tools/premise/measure.py --corpus <dir> nesting`

**U7, band stitching (assumption 5).** Two findings.

*The node count is invariant under banding* — a split can never split a
run, so V needs no repair at any K. Only E, C and the cycle counts do,
and the premise check sized that: a real 600-row page band at K=64 needed
1,068 seam edges, had 949 over-counted components and 119 missing cycles.

*One page needed zero repair at K=2 and K=3* — the seams happened to fall
in whitespace. A test that only tried small K would have passed while
proving nothing, which is why the fixtures run to K=64 and the real-ink
check to K=600, one band per row.

Stitched output is indistinguishable from a single sweep at every K
tested, on both connectivities.
Re-run: `tools/premise/measure.py --corpus <dir> banding`

**The re-sorting defence is mutation-tested.** Three defences were each
mutated; two killed tests immediately (17 and 247 failures). The third —
the per-node re-sort, which is the bug `units.md` names by name —
SURVIVED, because sorting the band list already yields global order and
made the re-sort unreachable through the public API. A test that shuffles
nodes *within* a band makes it reachable and kills the mutant. That case
is not hypothetical: U8 is specified to order results by completion.

---

### U7 stitch cost — measured 2026-08-07, before U8 was planned

Every other U7 measurement is a correctness measurement. This one is
about cost, and it changes what U8 should be.

**`stitch` is serial, so it is an Amdahl floor on band parallelism.**
Measured on two real page bands (3400×800, V=5000; 3307×800, V=3761),
best-of-3, after the optimisation described below:

| K | stitch | stitch / sweep | ideal wall | speedup | ceiling |
|---|---|---|---|---|---|
| 1 | 6.1 ms | 0.34× | 23.1 ms | 0.77× | — |
| 8 | 6.9 ms | 0.39× | 9.1 ms | 1.95× | 2.59× |
| 64 | 8.4 ms | 0.47× | 8.7 ms | **2.05×** | 2.13× |
| 256 | 11.3 ms | 0.63× | 11.4 ms | 1.57× | 1.58× |

"Ideal wall" assumes perfect K-way parallelism of the sweep plus the
serial stitch, so it is an upper bound no scheduler can beat.

**The ceiling is density-dependent, and worse on denser pages.** Two
further pages, sampled independently and heavier (V=12,635 and V=6,229
against 5,000 and 3,761 above):

| page | sweep | best ceiling | K=256 |
|---|---|---|---|
| V=12,635 | 43.1 ms | 2.32× | stitch **1.18× the sweep**, speedup 0.84× |
| V=6,229 | 24.5 ms | 2.19× | speedup 1.15× |

**Band parallelism is capped at roughly 1.7–3× across the pages measured,
however many cores are available**, and it degrades with K: past K≈64 the
stitch keeps growing while the parallel part has already vanished. On the
densest page at K=256 banding is *slower* than not banding at all.
Banding at K=1 is always strictly slower, which is the shape of the whole
finding.

No point estimate is quoted here on purpose. The spread across four pages
is 1.7–3.0× and it tracks page density; the reproducible claim is the
ordering — a serial stitch caps band parallelism in the low single
digits — not any single number.

**The optimisation that got it this far.** `stitch` was constructing
every `RunNode` twice — once concatenating, once in a renumbering
rebuild. But the concatenation is *already* in global scan order on the
production path, because band *i* covers lines strictly below band *i+1*
and U3 emits nodes in scan order within a band. An O(V) sortedness check
now skips the rebuild, and one-element `up`/`down` lists skip their sort.
Measured effect: stitch 9.4 → 6.1 ms, and the achievable speedup roughly
doubled from ~1.4× to ~2.05×.

The slow path is retained and still tested — a caller may hand over a
band whose own nodes are unordered, which is precisely what U8 does when
it appends results by completion rather than by band.

**Tree-stitching is NOT implemented and is not currently warranted.**
Seam merging is associative, so bands could be stitched pairwise in
log₂K parallel rounds, removing the serial floor rather than lowering it.
The criterion for attempting it was whether the floor stayed above the
sweep after the optimisation above; it did not (0.33–0.47× of the sweep),
so the remaining gain does not justify the complexity yet.

**Consequence for U8.** The band tier is not where utilisation comes
from. Page-parallel and blob-parallel work are unaffected by any of this
— a closed component needs no stitch at all, and serialization is
measured cheap (assumption 9). U8's first task should measure whether the
band tier earns a place in its own plan, rather than assuming it as the
plan currently does.

---

### U8 premise check — measured 2026-08-08, before U8 was planned

Machine: 16 cores (AMD Ryzen 7 5700U), Python 3.14. `units.md` reasons
about 128 cores elsewhere; these ratios should be re-taken at that scale
before they are relied on for a 128-core deployment.

**Where per-page time actually goes.** This is the finding everything
else follows from.

| Stage | 16 mixed corpus pages | arXiv pages only |
|---|---|---|
| decode | **94.5%** | 85.2% |
| sweep | 5.3% | 14.8% |
| binarize | 0.2% | — |

Split by decode path, on arXiv pages: **neutral pages 54% decode / 46%
sweep; colour pages 90% decode / 10% sweep.** Since 54% of corpus pages
are colour (§3 above), decode dominates the mix.

| Parallelise… | Amdahl ceiling on arXiv pages |
|---|---|
| the sweep only (what banding does) | **1.17×** |
| decode | **6.77×** |

**So the band tier is not built.** Not deferred, not marginal — it
targets 5–15% of the work and was already capped at 1.7–3× *of that
slice* by the U7 stitch measurement. Two independent measurements, taken
a day apart for different reasons, agree.

**This decision is CONDITIONAL, and the condition is written down here so
a future session does not read it as closed.** The 1.17× ceiling is a
function of decode being 85–95% of per-page work. The same arithmetic run
against an ingest path where decode is cheap inverts it — at a ~5% decode
share the sweep becomes ~95% of the work and the ceiling for parallelising
it rises to roughly 18×. **If decode ever stops dominating, this decision
must be re-taken.** It is correct for the pipeline as it stands and only
for that.

**Page-parallel scaling, 16 real pages over 16 cores.**

| workers | wall | speedup | efficiency |
|---|---|---|---|
| 1 (serial) | 142.5 s | — | — |
| 2 | 101.7 s | 1.40× | 70.1% |
| 4 | 56.8 s | 2.51× | 62.7% |
| 8 | 51.3 s | 2.78× | 34.7% |
| 16 | 43.7 s | **3.26×** | 20.4% |

**The per-page cost spread is 185×** — 0.18 s to 34.17 s. One 67.7 Mpx
colour page takes 38 s, of which 99.5% is decode. Total work 142.5 s
over a 34.2 s longest task gives an Amdahl ceiling of ≈4.2× for any
page-parallel scheme, and the measured 3.26× is already 78% of it. Adding
cores past 16 buys almost nothing.

**The idle tail, measured rather than assumed.** Utilisation 33–62%
across N ∈ {16,17,25,31} and k ∈ {8,16}, always well below the
partition-arithmetic ideal — because the spread, not the tail, is what
idles the workers. Pool startup is 37–54 ms and is not a factor.

**Serialization is not the constraint** (assumption 9's remaining half):
64 bands of a page pickle to 0.31–0.80 MB and every component together to
0.08–0.21 MB, against a 2.7–3.7 MB raw mask.

**What this leaves.** The ingest path is the bottleneck by an order of
magnitude, and `units.md` currently records a decision to stop optimising
it — taken when decode was believed to be a minor cost. That decision was
made on different evidence and is flagged here rather than silently
reversed.

Re-run: `tools/premise/measure.py --corpus <dir> schedcost`

---

### U11 box detection — measured 2026-08-09, `measure.py boxes`

An external audit proposed a frame detector, gave numbers for arXiv
2409.18839, and asked that they be reproduced and turned into a harness.
Four of its claims reproduce exactly, three do not, and one of the three
inverts the conclusion. Everything below is `measure.py boxes`, which
takes the two parameters that changed the answer as **arguments**
because they do.

**The predicate.** Two sweeps — foreground at conn=8, the inverted mask
at conn=4 — then a component is a frame iff `fill < fill_max` and it
encloses a hole covering at least half its bbox. No `nest`, no
`min_side`.

**What reproduced.** With `--hole-measure bbox`, the audit's counts came
back to the digit, including a three-way depth histogram:

| page | threshold | audit | measured |
|---|---|---|---|
| 4 | 200 | 13 (9/4) | 13 (9/4) |
| 4 | 240 | 9 (8/1) | 9 (8/1) |
| 6 | 200 | 154 (14/131/9) | 154 (14/131/9) |
| 6 | 240 | 56 (29/27) | 56 (29/27) |

That four-cell agreement is what identified the one term the audit left
ambiguous: "hole area" is the hole's **bounding-box** area. Measured as
pixel area the same pages give 9, 6, 75 and 24.

#### The clean-control claim is false, and by a wide margin

The audit reported "zero false positives on the text-only pages (5 and
8)". Under the very predicate that produces its other four numbers,
**page 5 yields 13 rectangles and page 8 yields 7**. Both claims cannot
hold; the counts settle which.

Across all nine text pages of the document:

| `--fill-max` | declared images recovered | false positives on 9 control pages |
|---|---|---|
| **0.35** (as proposed) | 29/34 | **125** |
| **0.10** (corrected) | 29/34 | **0** |

**Recovery is identical.** The permissive cutoff buys nothing and costs
125 false positives, 32 of them on page 13 alone. The audit saw zero
because it looked at two control pages; the two it did not look at
contribute 56.

#### What the false positives are, and why no size filter separates them

Rendering the pixels rather than arguing about them: the page-5 and
page-8 rectangles are **hollow glyphs** — `O`, `D`, `o` at 400 dpi, 36
by 38 px, `fill` 0.32 to 0.35. Real frames on the same document read
`fill` **0.016 to 0.031**, an order of magnitude away.

The same rendering settles a second claim. The audit rejected a
`min_side` filter because "the depth-2 boxes on page 6 are 21 x 21 px,
smaller than the body text", and built its deepest chains on them:

```
=== 21x19 at (1822,1919) fill 0.313
   .....#############...
   .......###......####.
   ......###.........###
   .....###..........###
   ....###..........###.
   ...###........###....
   #############........
```

**They are italic zeros.** Page 6's entire depth-2 layer is glyphs, and
with it the reported chains `22x22 < 165x37 < 1024x562`. At
`--fill-max 0.10` the layer disappears and page 6 reads depth
`{0: 10, 1: 9}` while still recovering 10 of 10 declared images.

So the audit's C3 is right that `min_side` is the wrong predicate, and
right that rectangularity is the right axis — but wrong about which end
of it discriminates, and the object it offered as proof was a character.

#### The independent oracle holds

`pdfdrill` writes an `images_layer` giving every embedded XObject's
rectangle in PDF points. Comparing it to the measured ink frames on
2409.18839: **29 of 34 declared images recovered, worst size error 1.72
pt** — the border thickness, so this is agreement to the limit of the
geometry. Page 4 recovers 7/7 and page 6 recovers 10/10, both as
claimed.

**State the denominator.** A declared image yields a measurable
rectangle only when the figure is *drawn with a border*. A bare
photograph has no stroked frame, so a miss is not a detector failure —
on a random corpus sample of eight pages from four other documents,
recovery is 0/13 and the detector is not wrong. This is an upper-bound
check on bordered figures, never an accuracy, and the harness prints
that beside the ratio.

#### No single threshold suffices (audit F2, confirmed and sharpened)

Per-threshold rectangle counts on the same document:

| page | th 200 | th 240 | union |
|---|---|---|---|
| 2 | 3 | 0 | 3 (3/3 images) |
| 4 | 5 | 7 | 7 (7/7) |
| 6 | 17 | 7 | 19 (10/10) |
| 11 | 6 | 0 | 6 (8/12) |

Page 4 needs 240 and pages 2, 6 and 11 need 200. Neither threshold
recovers all 34; the union does the work, at the cost of one extra pass.
Pale pink and green borders sit at grey 200–240, which is why.

#### Both polarities exist (audit F1, confirmed)

A layout panel drawn as a translucent tint is a nearly **solid**
component, and the hollow test cannot see it at any threshold. Page 6
carries 7 such regions and page 7 carries 6. The complementary test is
the opposite end of the same axis and needs no new computation, so
`_solid_candidates` is reported beside the frames. Note it needs a
threshold of its own: page 4's tints appear only at 250, not at 200 or
240 — so three thresholds are in play, not two.

#### MathPix ignores non-white backgrounds (audit Part 4, confirmed exactly)

Counting `lines.json` regions whose centre falls inside a declared image
rectangle:

| page | images | regions | inside |
|---|---|---|---|
| 2 | 3 | 37 | **0** |
| 4 | 7 | 31 | **0** |
| 6 | 10 | 20 | 1 |
| 11 | 12 | 5 | 1 |
| **7** | 2 | 104 | **89** |

Page 7 is the counterexample that makes this a mechanism rather than a
correlation: its figure is a **white-background screenshot** of a
journal page, and MathPix reads straight through it. The coloured-tint
panels on 2, 4, 6 and 11 it collapses to a single `diagram` and reads
nothing inside.

**Consequence for U11.** "Ink with no region" over a coloured figure
panel is not a MathPix failure; it is a systematic blind spot with a
stateable trigger — non-white background — and it deserves its own
residual class, because the remedy differs. Missed text is an error; a
declined panel is the other tool behaving as designed and inkdrill
supplying what it declines to look at. Page 11 is the extreme case: 12
figures, 5 regions.

#### The boundary of all of the above

Every figure in this document is vector-drawn or smoothly compressed, so
a constant-colour fill really is constant. **A screened reproduction of
the same figure invalidates both polarities**: a filled tint becomes a
dot lattice, so `fill` collapses to the screen's tone value; a 2 px
border becomes a broken dotted line, so the frame stops being one
connected component. Not built for, recorded as the stated limit. The
deferred raster-region detection is the prerequisite, and its
active-component ceiling is what should fire on such a page rather than
a wrong box tree.

### Validation against the drawing program — e12s39, measured 2026-08-09

`e12s39.ps` is 5,093 lines of PostScript dated June 1995; `e12s39.pdf`
is that file through Ghostscript 9.05 with nothing else in the path.
**It is the only fixture in the corpus with a declared answer** — the
geometry is stated as arithmetic in the source, so this is the first
check against the drawing program rather than against another tool's
opinion. Pinned by `tests/test_source_truth_corpus.py`.

#### Two parameters, both closed

| | authored | measured | residual |
|---|---|---|---|
| panel interior | `axis.length - 2*axis.width` = 175.248 pt | **175.320 pt**, 24 panels | **0.072 pt** = 0.40 px |
| tick pitch | `axis.length / 31` = 5.6693 pt | **5.6700 pt**, 348 intervals | **0.0007 pt** = 0.004 px |

Three corrections to how those numbers were first derived, each of which
moves the answer by more than the residual it is quoted against:

**`axis.width` is defined three times and PostScript is sequential.**
Line 672 says `0.01 cm` (0.283 pt) and line 962 says `0.25` — and line
962 is immediately before the `6.2 cm` at line 964 that draws these
panels, so 0.25 is live. Using the superseded value gives a residual of
0.139 pt; the live one gives **0.072 pt**, half as much.

**Read the PNG's `pHYs`, do not derive dpi from an assumed page size.**
The PDF's MediaBox is 595 x 842 pt, not A4's nominal 595.32 x 841.92.
Deriving dpi from the nominal size gives 175.39 pt where the answer is
175.32 — an error of 0.07 pt, exactly the size of the residual being
reported. `pngio` already reads the chunk; use it.

**The ticks are at the DAY pitch, not at `label.inc`.** `label.inc` is
`axis.length/31*5` = 28.346 pt and is the *label* spacing — every fifth
day carries a number. Searching for that pitch finds text glyphs and
looks like a failed measurement. The tick marks themselves are one per
day at `axis.length/31`, and at that pitch 348 intervals agree to
0.0007 pt. **The parameter is not unmeasurable; it was the wrong
parameter.**

#### The fixture's own tolerance admitted the error it names

Found by audit, not by the suite, and it is the sixth instance of the
same shape. `test_panel_width_matches_the_authored_axis_length` was
written with `delta=0.15` and a docstring explaining that reading the
PNG's `pHYs` matters because a nominal-A4 derivation "gives 175.39 pt
where the answer is 175.32". Both statements are true; together they do
not hold:

| | pt | vs authored 175.248 |
|---|---|---|
| measured, pHYs dpi | 175.320 | 0.072 |
| measured, nominal-A4 dpi | 175.391 | **0.143** |
| the tolerance | | 0.15 |

**0.143 < 0.15, so the wrong derivation passed.** The guard was prose.

Tightened to **0.10**, which rejects the A4 value and keeps a 0.028 pt
margin on the true one. But a tolerance chosen to catch a specific
mistake is itself a claim, so the separation is now asserted directly:
`test_a_dpi_taken_from_nominal_A4_is_rejected_by_that_tolerance`
recomputes the wrong value and requires it to fall outside the *same*
shared constant. Widening the tolerance past the mistake now fails that
test instead of silently disarming the other one.

Four mutants, all killed, where two of them previously passed:

| mutation | result |
|---|---|
| dpi from nominal A4 instead of `pHYs` | 3 failures |
| tolerance widened back to 0.15 | 1 failure |
| superseded `axis.width` (0.01 cm) | 2 failures |
| tick pitch set to `label.inc` (5-day) | 1 failure |

#### The sharpest ink-versus-white result so far

The panel frames are connected to their axes, labels and traces, so
**no ink component has a panel's extent — the ink sweep finds zero.**
The white-gap sweep finds **24, all exactly 974 px wide, at two x
positions**: not a distribution around a value, the same object drawn
twenty-four times. Earlier the white detector beat the ink detector
33/34 to 29/34; here the comparison is 24 to 0.

Ticks are the complementary case to matplotlib, where each tick is its
own component: here `ticmark` is part of the axis path, so a detector
that looks for free-standing objects returns nothing. Recovering them
needs the perpendicular-protrusion reading — scan the ink row just
outside the white interior — which is four lines and is what the test
does. **Whether ticks are separate components is a property of the
drawing program, not of ticks**, and that is the same lesson as
`booktabs` versus Word tables and stroked outlines versus filled tints.

### A non-LaTeX counterexample — Infineon handbook, measured 2026-08-09

Everything measured on this project so far has been arXiv. The corpus
also holds a 110-page Infineon motor-control handbook produced by
**Microsoft Word 2016** — A4, 213 declared images, 141,033 glyph
instances — and it breaks three conclusions in three different ways. It
is kept as the standing counterexample.

#### U9's route B goes to zero

| | arXiv sample | this handbook |
|---|---|---|
| font kinds | 48% Type 1C, 46% Type 1 | **100% TrueType / CID TrueType** |
| maths families | CMMI, CMSY, CMEX, MSBM … | **CambriaMath only** |
| found in the TeX tree | 94.61% of maths glyph mass | **0 of 19 font records** |

`type1.py` reaches nothing here, and CambriaMath is a font this
project's own U9 measurement already named in its 5.39% miss list. The
94.61% is **arXiv-specific**, exactly as the contract's stated
population said, and this document is what that caveat looks like when
it fires. Serving this population needs a TrueType `glyf` parser, which
is a different module and has no measurement behind it.

U9's *inventory* half is unaffected and generalises cleanly: 140,946 of
141,033 glyph instances (99.94%) are on the embedded-outline fast path.
Note the consequence for the two routes — the fonts here are embedded,
so **route A would work where route B cannot**. The route choice is a
property of the population, not of the format.

#### The oracle is half boilerplate

`images_layer` lists XObject **placements**, not figures. Here 109 of
213 entries (**51.2%**) are one repeated header logo — `Image9`, 72.0 x
31.4 pt, on 109 of 110 pages. A recovery rate computed over the raw list
has a 49% ceiling that no detector can pass. `m_boxes` now counts each
distinct placement once and prints how many it dropped.

#### Both layout detectors are the wrong polarity here

On the eight pages carrying real figures, `boxes` (hollow frames) and
`white` (ink-bounded gaps) each recover **0 of 28**. Neither is broken:
these are borderless JPEGs dropped into Word, so there is no stroked
frame and no gutter. The figures are **solid ink components** —
page 7's `171.2 x 208.5 at (212,437)` is the declared `Image197`
`171.20 x 208.47 at (212,437)`, matching to **0.00 pt**.

The right detector is the filled polarity identified earlier as F1 —
and its threshold was badly wrong. `_solid_candidates` used `fill > 0.9`:

| `fill >` | recovered of 34 |
|---|---|
| 0.9 | 1 |
| 0.75 | 1 |
| 0.6 | 10 |
| **0.5** | **10** |

A photographic panel is not 90% ink. So the three polarities are
**hollow frame / white gap / solid fill**, and which one applies is a
property of the producing toolchain: LaTeX draws frames and leaves
gutters, Word pastes rasters.

#### A tight tolerance measures padding, not detection

Even where a figure is found, the two quantities being compared are not
the same thing. Matching by **position** and then asking how wrong the
size is:

| population | median | p90 | max |
|---|---|---|---|
| arXiv 2409.18839 | 0.92 pt | 8.44 pt | 20.05 pt |
| Infineon handbook | 2.64 pt | 20.23 pt | 163.53 pt |

**A declared rectangle is the placement box; ink gives the content
extent.** They coincide for tight vector figures, which is why the
arXiv numbers read 0.3–1.7 pt, and they differ by the raster's own white
padding otherwise. The 3 pt tolerance used earlier was calibrated on a
population where the two happen to coincide; on padded rasters it
measures the padding. `m_boxes` now reports the position-matched
distribution beside the hit count, because the distribution is the
finding and the hit count is not.

### White-run layout — measured 2026-08-09, `measure.py white`

A proposal to build layout from the page's *gaps* rather than its ink —
Baird 1994 and Breuel 2002 in run form, using the
`sweep(mask.inverted(), conn=4)` this codebase already runs for holes.
Measured before building.

**The core mechanism is confirmed, and the failure it fixes is worse
than reported.** Blobbing white with no filter gives one page-sized
component covering **71.1% to 98.6%** of the page across five pages —
the proposal said 53%. White connects around every object through the
margins. The one-line fix works exactly as claimed:

```python
if r.lo == 0 or r.hi == limit - 1: continue    # margin, not a gap
```

On page 6 that turns 2,556 blobs with a 3400x4400 largest into 439 with
a 2199x3748 largest — from an undifferentiated page to layout.

#### The central claim is refuted, and it inverts

The proposal's §4 states the two detectors want opposite thresholds:
"Ink wants it HIGH so pale strokes count as ink. White wants it LOW so
pale fills count as background", with figure panels recovered at 128 and
vanishing at 200 and 240. Measured against the declared image
rectangles on the same document:

| threshold | declared images recovered |
|---|---|
| 128 | 19/34 |
| 200 | 28/34 |
| **240** | **33/34** |

**White wants the HIGH threshold too**, and page 11 shows it starkly:
0/12 at 128, 8/12 at 200, **12/12** at 240. Nothing vanishes at 240 —
the three panels the proposal reported as threshold-sensitive are
present at 128, 200 and 240 alike, to the same 0.1 pt.

The reasoning was inverted. What a white rectangle needs is not a white
*interior* but an **ink boundary**. At 128 a pale tint counts as
background, so a tinted panel merges with the surrounding white and its
rectangle is destroyed; at 240 the tint is ink and bounds the interior
cleanly. So the "bracket" argument does not hold and the second pass is
not needed for threshold reasons — **both detectors want 240.**

#### White recovers the declared rectangles better than ink does

On the audited document, at the threshold each detector prefers:

| detector | recovered | worst size error |
|---|---|---|
| ink frames (`boxes`) | 29/34 | 1.72 pt |
| **white gaps (`white`)** | **33/34** | **0.29–0.42 pt** on four pages of five |

White is both more complete and an order of magnitude more accurate,
and the reason is structural: a white blob's bbox is the object's own
extent, while an ink frame's bbox is a stroked border with thickness, so
the ink measurement carries the stroke width as error. The proposal's
own §3 observed the two agree to the frame thickness; that thickness is
precisely the ink detector's error bar.

It also generalises better. On a random cross-document sample of
image-bearing pages, white recovers **10/28** where ink recovered 0/13:
a white gap around a figure exists far more often than a drawn border
does.

#### The cost claim is misattributed

§5 reports 2.7 s for both axes and blames a per-pixel Python loop on the
column axis, alongside `classify.normalise` and `nest._label`. **That
loop is not in this package.** `raster._iter_runs_col` already reads
columns with a C-speed step slice, and writing them back is a strided
slice assignment — `buf[lo*W + line : hi*W + line + 1 : W]`. Built that
way from the start, both axes cost **0.34–0.36 s to build plus
0.36–0.57 s to sweep**, not 2.7 s. The run-discipline violation was in
the prototype, not in the thing being measured.

#### What remains unmeasured

`--min-len` is still 60 px chosen on two pages, and it is an absolute
number where the right one almost certainly scales with body-text size;
it stays a harness argument. The ink-bounded rule discards genuine
structure at the page edge — a full-bleed figure would be missed — and
the proposal's suggestion to key it on the text block rather than the
page is untested. The gutter and column-block result could not be
reproduced at all: that document is in the corpus with a single rendered
page and it is not page 1.

### Border colour per blob — measured 2026-08-09, `measure.py border`

An external proposal: sample the pixels immediately outside each run —
`(lo-1, line)` and `(hi+1, line)`, addresses the adjacency test already
computes — and classify a component by the entropy of the resulting
histogram. Measured before building, as its own §6 asked.

**The mechanism is real, and sharper than reported.** A figure frame
comes out at exactly two border colours, the tint and the page:

```
1029x561  1116 runs  distinct 2  rgb(254,250,224) x1122 | rgb(255,255,255) x1110
1017x562  1116 runs  distinct 2  rgb(250,237,205) x1124 | rgb(255,255,255) x1108
1024x562  1116 runs  distinct 2  rgb(254,250,224) x1124 | rgb(255,255,255) x1108
```

The counts are **near-equal**, and that is the signal: a *closed* frame
borders both fields about equally. The proposal printed `x404 | x3` for
the same objects, which is a 133:1 split and would give a Shannon
entropy of 0.06 rather than the 1.00 it also reported — the two halves
of its own example disagree. The balanced split is what makes H = 1.00
exactly, and `m_border` reports the balance as its own count because it,
not the colour pair, is what distinguishes a frame from a stray edge.

#### Four claims, measured

**1. Cost — right number, wrong denominator.** Sampling is +26% to +28%
on the sweep, close to the +32% claimed. But sampling needs an RGB
buffer, and `pngio` reduces to luma and discards it:

| per colour page (3400 x 4400) | time |
|---|---|
| RGB unfilter | 5.83–6.79 s |
| sweep | 0.75–0.92 s |
| border sampling | 0.21–0.24 s |

Sampling is **3% of the three operations**. The cost that matters is
retaining RGB, and it is not uniform: on the *colour* path `pngio`
already unfilters RGB per row and throws it away, so the marginal cost
is memory (3x the page buffer). On the **neutral** path it unfilters ONE
channel by SWAR and never forms RGB at all, so retaining it there means
roughly **3x the decode** — and decode is 85–95% of per-page work.
Border colour on a neutral page is grey by construction and says
nothing. **So the feature must be conditional on `neutral is False`,
where it is also the only place it can pay.** One page in twelve sampled
was neutral and `m_border` skips it rather than pooling it.

**2. Quantisation — REFUTED, it does the opposite.** The proposal
suggested rounding each channel to 8 or 16 to absorb JPEG noise, "which
would sharpen every class". Measured on the same page:

| quantise | textured | boundary | flat-white |
|---|---|---|---|
| off | 2653 | 61 | 969 |
| 8 | 610 | 84 | 977 |
| 16 | 152 | 165 | 992 |
| 32 | **25** | **2374** | 1062 |

At 32 the textured class has collapsed by 99% and 2,374 blobs have been
promoted to clean two-colour "boundaries" — quantisation makes
photographic regions look like frames, which destroys the halftone
detector the proposal's §3 is built on. The reason is structural: the
classes are defined by *distinct colour count*, and quantisation reduces
that monotonically, so it can only compress the classes toward the flat
end. It cannot sharpen them.

The targeted variant — snap only near-white to white, leave the rest
exact — is milder but still net-negative: at eps=4 it gains 2 blobs for
flat-white and pulls 101 out of textured. The JPEG-noise contamination
it was meant to fix is real but two orders of magnitude smaller than the
damage. **Sample exact RGB.** `--quantise` defaults to 0 and stays an
argument so this stays re-runnable.

**3. "A frame knows what it separates" — true, but two colours is not a
frame test.** Over the five image-bearing pages of the audited document,
the `boundary` class holds **6,319 blobs, 22.85% of all components**.
Any small glyph straddling two flat fields lands in it. Border colour
says *what* a frame separates; it does not say a blob *is* one. The
frame test is still `fill < 0.10` from `measure.py boxes`, and border
colour is what should be attached to its output.

**4. The flat-coloured class is not "annotation over a picture".**
Rendered, the 70 such blobs on page 6 are text glyphs and fragments on a
tinted panel — sizes 1x1, 5x1, 6x18, 7x7, 8x8, and a 31x20 letter
cluster. The class is really *ink on a flat non-white field*, which
includes body text inside a coloured box. That is still useful, but the
stated separation holds only against **textured** content: a vector
picture with flat fills gives its own ink H ≈ 0 too, so annotation and
picture are indistinguishable there. The claim is sound for photographs
and screens, not for figures in general.

#### The population correction

The four-class table came from one page. Across **11 colour pages from
11 different documents**, all carrying at least one declared image:

| class | audited page 6 | 11-document sample |
|---|---|---|
| flat-white | 26.74% | **89.87%** |
| textured | 27.57% | **2.56%** |
| boundary | 22.85% | 0.85% |
| mixed | 18.46% | 2.61% |
| flat-coloured | 4.39% | 4.11% |

Every class is present and non-empty in both, so the **mechanism
generalises**; the proportions do not. A page dense with tinted panels
is not the corpus. Any threshold tuned on the first column would be
tuned on a 10x over-representation of textured ground.

### `nest()` is 15x slower than the two sweeps it is equivalent to

The audit's C2, reproduced on page 8 of the same document (3400 x 4400):

| | time | ink regions | holes |
|---|---|---|---|
| `nest()` | 19.70 s | 3,390 | 1,190 |
| `sweep(m)` + `sweep(m.inverted(), conn=4)` | **1.31 s** | 3,390 | 1,190 |

Identical output, **15.0x**. `nest` flood-fills per pixel and
accumulates extents in a per-pixel Python loop — the same
run-discipline violation as `classify.normalise`, in a more expensive
place. The cycle rank already gives the hole *count* free, so the second
sweep is only needed when hole *geometry* is wanted.

**A finding, not a change.** It touches `nest`'s internals, and
`measure.py boxes` uses the two-sweep form directly, so the cost is
already avoided where it was measured.

### U9 `charstring.py` — the interpreter, sized by measurement

Tests T9-10 to T9-19 passed on 2026-08-09: 33 hermetic, 6 opt-in.

`measure.py charstrings` counted operators over 400 fonts, 209,550
charstrings and 157,177 subroutines before the module was written, so
the interpreter is sized by what fonts use rather than by what the spec
lists. Two of the 25 operators are subsystems rather than switch cases
-- `seac` (1.89%) and `callothersubr` (0.31%) -- and both are built,
because at 1.89% `seac` is every accented character and skipping it
returns the base letter without its accent: a *plausible* wrong glyph,
which is the failure mode this project exists to prevent.

**At scale: 119,800 glyphs over 250 fonts, 0 errors, 0 unclosed
contours.** That settles the `callsubr` class `first_ops` had to defer.

**The independent oracle is letterform topology**, not "it ran". A
roman `o` has two contours in every face ever cut, and no arithmetic
error inside an interpreter produces that by accident. 21 glyph names
of `cmr10` check out exactly.

Applying the same table to `cmmi10` and `cmsy10` produced four
"failures" that were all correct answers -- `cmmi10`'s `g` is a
single-storey italic with 2 contours and `cmsy10`'s `B O P R` are
script capitals drawn in one stroke. The population again: a roman
table describes roman faces.

**Mutation sweep: 10 mutants, 10 killed** -- but one only after a fix.
`test_hint_replacement_leaves_a_value_for_its_pop` passed against an
interpreter that pushed nothing, because all four subrs in its fixture
were bare `return`s: calling subr 0 instead of subr 3 changed nothing
observable. The subrs now differ, and the wrong `pop` fails the test.

### U9 rasterizer premise check — measured 2026-08-09, before `type1.py` was planned

Re-run with `measure.py outlines`. The question was which outline format
a maths glyph's program is in, and whether reaching it needs a PDF
parser. **Population: glyph instances** — not font entries, not
documents; the same three denominators that disagreed by 78 points in
the inventory premise check below. **Split:** 30 documents sampled
without replacement, every glyph instance of each counted. **Filter:**
`is_math_family`, whose kept and dropped families the harness prints.

| Measured over maths glyph instances (n = 17,916) | Result |
|---|---|
| format the PDF embedded | 48.13% Type 1C, 46.48% Type 1 |
| format the same font has **on disk** | **94.61% a `.pfb` in the TeX tree** |
| `/FontFile*` reachable outside object streams | 20/30 documents |

**The marginals and the joint disagree about what to build.** Read the
first row alone and the plan is a CFF interpreter *and* a Type 1
interpreter, behind a PDF extractor with an object-stream decoder. The
joint says one parser and no PDF handling: every maths font in the
sample resolves to a Type 1 `.pfb`, *including* the ones a producer
embedded as Type 1C, because the producer converted at embed time.
Subsetting drops glyphs without altering the outlines of those that
remain, so the on-disk outline is the embedded outline for every glyph a
page actually used.

The 5.39% this route misses is named rather than absorbed:
LibertinusMath 872, Cambria Math 58, CambriaMath 36 — non-TeX OpenType
maths fonts, which are also the whole `CID Type 0C` column.

**Two limits stated with the figure.** `is_math_family` is
under-inclusive: it drops CMR (446,410 instances), which is where TeX
keeps maths digits and fences. The bias runs the favourable way, because
CMR is itself a `.pfb`. And 94.61% is against *one machine's* TeX tree —
without `texmf-dist` it is 0%. That is why `type1.py` never searches for
a font: the caller supplies the path and owns the missing-font class.

### U9 `type1.py` — the oracle was wrong twice before the parser was

Tests T9-1 to T9-9 passed on 2026-08-09. 39 hermetic, 6 opt-in on
`INKDRILL_TYPE1`.

The parser has no golden file. Its oracle is that a charstring opens
with `hsbw` or `sbw`, so a wrong length, offset, key or `lenIV` decodes
as something else. Run over the TeX tree that oracle read **88.33%**,
then **97.86%**, then clean — and *both* corrections were to the
instrument:

| Reading | What the gap was |
|---|---|
| 88.33% | `div`. cm-super writes every width as `<num> <den> div hsbw`, and `div` is 12-12 — below 32, like a command. Counting it as one declares all 585 charstrings of a correct font broken |
| 97.86% | **subroutinization**. Roboto, Tinos and Cascadia hold the `hsbw` inside a subr, so 436 of Roboto-Black's 1,250 glyphs correctly open `n callsubr` |

Calling `callsubr` a failure or calling it a pass would both have been
assertions, so it is a class of its own, deferred to the interpreter.
Final reading over **7,616 fonts and 3,413,996 charstrings**: 97.834%
`hsbw`, 2.166% `callsubr`, **0 in the wrong class, 0 files rejected.**

This is the "residual is the product" rule applied to an instrument
rather than to a page: a single pass rate would have made both
corrections look like parser bugs, and the second one is not fixable at
all without the interpreter.

**Mutation sweep** (per the standing rule): 20 mutants, 19 killed. Two
initially survived and both were real gaps — the phantom-entry guard was
tested with a trap in the *plaintext*, where encryption hides it, and
the PFB-trailer guard had no assertion at all. Both are now pinned, with
the note that no font in 400 sampled from the tree distinguishes either.
One equivalent mutant remains and is unkillable by design: `decrypt(enc,
EEXEC_R, 4)` → `skip=0`. Every access into the private dict is by
search, never by absolute offset, so a four-byte prefix shifts nothing.

### U9 inventory premise check — measured 2026-08-08, before U9 was planned

`units.md` called assumption 8 "the cheapest assumption to check and
worth checking before U9 starts". It was, and it produced a lesson about
metrics rather than about fonts.

**The same corpus gives three different answers depending on what you
count.** `pdffonts` over 119 arXiv PDFs, joined to per-glyph `fontname`
from `chars.json` over 40 documents and 1,979,232 glyph instances:

| Counting… | Result | Reading |
|---|---|---|
| font entries | 94.3% embedded, 5.1% Type 3 | fine |
| **documents** | **16.8%** fully embedded with no Type 3 | catastrophic |
| **glyph instances** | **95.90%** on the fast path | fine |

**Glyph-weighted is the correct metric**, because U9's fast path applies
per glyph, not per document. A paper with twenty fonts of which one is an
unused non-embedded Helvetica is not a paper U9 fails on. 80.7% of
documents contain *some* non-embedded font; that number is true and
almost meaningless.

Glyph-weighted breakdown:

| Class | Share |
|---|---|
| embedded outline — U9 fast path | **95.90%** |
| font name unresolvable | 3.58% |
| not embedded | 0.45% |
| Type 3 | 0.08% |

**Genuinely unusable is 0.53%**, an order of magnitude below the 5.1%
the per-font view suggests. 55% of documents have *every* glyph on the
fast path.

**The 3.58% unresolvable has four causes, and one is a bug U9 must
avoid.** `chars.json` reports `CKXQCW+LMRoman10-Regular` where `pdffonts`
reports `CKXQCW+LMRoman10-Regular-Identity-H` — the same embedded font,
failing to join on an encoding suffix. **U9 must normalise font names
before matching.** The rest are real: `'unknown'` where pdfminer cannot
name the font (51,952 glyphs, concentrated in a single old document), and
unprefixed standard names like `'Times New Roman'` that genuinely are not
embedded.

**Scope consequence.** U9's stated scope limit — "embedded, non-Type-3,
outline fonts only" — is the right one and costs 0.53% of glyphs, not the
5% or 83% the other two metrics imply. U11 remains the fallback for the
remainder.

**Stratified by family, 2026-08-08 — the aggregate cannot speak for
maths.** The right *kind* of measurement on the wrong *population* is the
same mistake one level down. Body text dominates glyph instances, so a
95.9% aggregate is compatible with maths coverage anywhere between 0% and
100% — and maths is the fast path's first application, because
`CMMI`/`CMSY` custom encodings are exactly where a bitmap classifier is
weakest. Measured over 30 documents and 1,471,926 glyph instances:

| Population | Fast path | Share of all glyphs |
|---|---|---|
| aggregate | 94.64% | — |
| **maths families only** | **100.00%** | 2.00% |

**Maths glyphs are better covered than body text, with zero rejections
across 29,496 of them.** TeX maths fonts are always embedded subsets in
arXiv PDFs; the non-embedded fonts are standard text faces like Times.
Families by volume: CMMI 20,278, CMSY 7,069, CMEX 1,023, EUFM 405,
MSBM 291, CMMIB 269, WASY 88, MSAM 56.

This *raises* the rasterizer half's value for its primary application
rather than lowering it, and it is a number the aggregate could not have
produced in either direction.

Re-run: `tools/premise/measure.py --corpus <dir> fonts`

---

### U10 premise check — measured 2026-08-08, before U10 was planned

Assumption 7 has already bitten twice, both times in the U4 premise
check: cropping pdfminer's ADVANCE box instead of the ink box gave a
useless result, and it is why component isolation is the only sound
method. This measures it directly.

**Method.** Three real pages with `chars.json` ground truth, at their
native 400 dpi and decimated by 2 and 4 to simulate lower render
resolution. Each ink component is assigned to the glyph boxes its centre
falls in, and the four residual classes read off. 18,519 assignments at
native resolution.

| Class | 400 dpi | 200 dpi | 100 dpi |
|---|---|---|---|
| 1 : 1 | 66.93% | 69.87% | 32.30% |
| ink with no glyph | 19.61% | 13.05% | 6.51% |
| N ink : 1 glyph | 12.34% | 7.78% | 2.20% |
| glyph with no ink | 1.11% | 9.20% | **58.78%** |
| 1 ink : N glyphs | **0.02%** | 0.09% | 0.20% |

**CORRECTED 2026-08-08: two of those five numbers were artefacts of a
three-page sample.** An independent 12-page sample at 400 dpi, all text
pages:

| Class | 3 pages | **12 pages** | per-page spread |
|---|---|---|---|
| 1 : 1 | 66.93% | **85.17%** | 81.2 – 86.7% |
| ink with no glyph | 19.61% | **0.39%** | 0.0 – 2.8% |
| N ink : 1 glyph | 12.34% | 13.75% | — |
| glyph with no ink | 1.11% | 0.64% | 0.00 – 1.86% |
| 1 ink : N glyphs | 0.02% | 0.05% | — |

**The three structural classes reproduce; the two dominated by a single
figure-heavy page did not.** That page contributed 3,572 image-only
components against 4 and 35 on the other two, and it moved the aggregate
by 50 points on 1:1 and by a factor of fifty on image-only.

The mechanism was right — a diagram correctly has no glyph — but the
*rate* was a property of that page mix, not of arXiv. This is the U0
colour fraction and the U7 density dependence recurring a third time, and
the rule it keeps teaching is the same: **record the mechanism and the
spread, never the aggregate of a small sample.** The per-page columns
above are the claim; the aggregate is context.

Every figure here is at **400 dpi**, the corpus render. The pipeline's
stated target is 600 dpi, where glyph loss should be lower still and is
unmeasured.

**The residual is structure, not error.** *Ink with no glyph* is figures
and rules — a diagram correctly has no glyph — and on ordinary text pages
it is under 1%. *N ink : 1 glyph* is `i`, `j`, `:`, accents and broken
strokes: the multi-component glyphs U4 already had to accommodate, and at
13–14% it is the largest genuine residual and the stable one.

**The feared case barely exists.** One blob straddling two glyphs is
**0.02%** at 400 dpi. Touching glyphs and ligatures are far rarer than
the design assumed, so the matcher does not need to split blobs — it
needs to *report* the rare case.

**This answers "what render resolution does this need."** `units.md` said
the N↔1 rate as a function of dpi would be that answer; the *glyph with
no ink* rate turns out to be the sharper signal:

| dpi | glyphs with no ink at all |
|---|---|
| 400 | 1.11% |
| 200 | 9.20% |
| 100 | **58.78%** |

**100 dpi is unusable — most glyphs leave no recoverable ink. 200 dpi
loses about one glyph in eleven. 400 dpi is where the loss becomes
negligible.** Note the N↔1 rate *falls* at low dpi, which looks like
improvement and is not: components merge because strokes thicken into
each other while whole glyphs vanish. Reading that rate alone would have
recommended the worst resolution.

**Per-page variance is large** and tracks content: two text pages give
82.9% and 83.7% at 1:1, a figure-heavy page 36.8%. A single aggregate
agreement rate would be nearly meaningless — the same lesson the U9
premise check produced about populations.

Re-run: `tools/premise/measure.py --corpus <dir> residuals`

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
6. ~~**The priority-queue scheduler reaches full utilisation.**~~
   **REFUTED 2026-08-08 (U8 premise check).** It does not, and the idle
   tail is not the main reason. Measured on 16 real pages over 16 cores:
   **3.26× speedup, 20.4% efficiency, 33–62% utilisation.** The cause is
   a **185× spread in per-page cost** (0.18 s to 34.17 s), so the single
   slowest page sets a floor no core count can beat — the ceiling for
   *any* page-parallel scheme on that sample is ≈4.2×. Finer bands at the
   end would not fix it, because banding only touches the sweep. The
   honest fix is finer-grained tasks *within* the expensive stage, and
   that stage is decode.
7. ~~**pdfminer glyph boxes and rendered ink agree closely enough.**~~
   **MEASURED 2026-08-08 — see §3 "U10 premise check". They agree far
   less closely than "closely enough" implies: only 66.9% of assignments
   are 1:1 at 400 dpi.** But the residual is mostly *structural and
   expected* rather than error — figures with no glyph, and multi-part
   glyphs like `i`, `j`, `:` and accents. The feared case, one ink blob
   straddling two glyphs, is **0.02%**. The assumption survives in the
   form U10 needs, which is why the four residual classes are reported
   rather than a single agreement rate.
8. ~~**arXiv PDFs are predominantly embedded, non-Type-3 fonts.**~~
   **MEASURED 2026-08-08, and the metric choice inverts the answer — see
   §3 "U9 premise check". Glyph-weighted, which is how U9 uses it:
   95.90% of glyph instances are on the fast path.** Per *document* only
   16.8% are fully clean, which looks catastrophic and is the wrong
   question. The assumption holds as stated for the work U9 actually
   does.
9. **Pure Python at 19 Mpx/s is fast enough once parallelised.** The
   arithmetic works out. **The serialization half is now measured and is
   NOT the constraint** (2026-08-07): all 64 bands of a 3400×800 page
   pickle to 0.31 MB against a 2.72 MB raw mask, and every component on
   the page together comes to 0.08 MB, mean 0.66 KB, 0.08 ms to ship the
   largest. What *is* the constraint is the serial stitch — see U7 stitch
   cost in §3. The remaining unverified half is whether the scheduler
   reaches full utilisation, which is assumption 6.
10. **`inkdrill` is the right package name.** Cosmetic, but the cost of
    changing it rises with every unit.
11. **The corpus is entirely ghostscript `png16m`.** 400 files sampled
    from the full 18,494-page library, IHDR `(8, 2, 0, 0, 0)` × 400 — zero
    variation. The unit fails loudly rather than mis-decoding if that is
    wrong, so the risk is a refused file rather than a wrong answer.
