# inkdrill — goals and current state

Written 2026-08-09. The authoritative per-unit record is
[`units.md`](units.md); the algorithm and performance reference is
[`algorithms.md`](algorithms.md). This file is the map: what the project is
for, what exists, and what the next move is.

---

## 1. What this is for

Scan-event topology for document layout analysis and mathematics
expression recognition. Pure standard library — no numpy, no GPU, no
build step.

The stated purpose, in the owner's words, is to **support high-quality
scanning by locating errors and areas other tools have missed.** That is
not a paraphrase of "do OCR". It is a cross-check: given a page and
another tool's opinion of it, say what that tool did not see.

Two consequences run through every unit:

- **The residual is the product.** `coverage.py` reports ink with no
  region; `gold.py` reports the four alignment classes rather than one
  agreement rate. A single accuracy number would discard the finding.
- **Topology before recognition.** Holes, branches and nesting are
  computed from ink alone, before anything is named. They are what let a
  wrong answer be *detected* rather than confidently returned.

## 2. Architecture in one page

Three representations, each strictly smaller and more structured than the
last. Nothing ever goes back.

| | representation | 600 dpi A4 | module |
|---|---|---|---|
| 1 | grey buffer | 34.8 MB | `pngio` |
| 2 | ink mask, `0xFF`/`0x00` | 34.8 MB | `raster` |
| 3 | run list | ~0.5 MB | `raster` |
| 4 | run adjacency graph | ~1 MB | `sweep` |
| 5 | Reeb graph, moments, nesting | ~20 kB | `reeb`, `aggregate`, `nest` |

**The run list is the pixel set, compressed, and everything downstream
operates on runs.** A glyph is ~190 px and ~9 runs, so anything phrased in
runs is an order of magnitude cheaper. See `algorithms.md` §7.2 for the
one place that discipline was dropped and what it costs.

The design decision the project is built on: **the RAG is retained rather
than consumed.** Components, hole counts, the join tree, the Reeb graph
and the branch skeleton all come from one enumeration of the same edges,
and split events survive — which a union-find-only formulation
structurally cannot do.

## 3. Units

| unit | module | state |
|---|---|---|
| U0 | `pngio` | complete |
| U1 | `space` | complete |
| U2 | `raster` | complete |
| U3 | `sweep` | complete |
| U4 | `reeb` | complete |
| U5 | `aggregate` | complete |
| U6 | `nest` | complete |
| U7 | `band` | complete |
| U8 | `sched` | complete — band tier deliberately not built |
| U9 | `font` | inventory: complete |
| U9 | `type1` | outlines: font -> charstring bytes |
| U9 | `charstring` | charstrings -> closed contours |
| U9 | `scan` | contours -> InkMask — **rasterizer complete** |
| U10 | `gold` | complete |
| U11 | `coverage` | complete |
| U12 | `domains` | complete |
| U13 | `classify` | complete |
| U14 | `mathstruct` | **geometry only** — no structure tree |

One unit is deliberately partial and one tier was deliberately dropped;
both are recorded with the measurement that decided them. U9 is partial
because it is in progress, not by decision.

## 4. What the measurements settled

Every figure below is reproducible via `tools/premise/measure.py`.

**Confirmed:**

- run extraction 105 Mpx/s, sweep 19 Mpx/s, `Capture.GRAPH` +13%
- Reeb contraction reduces the graph to 14–19% of its nodes
- row and column sweeps give *identical* moments — exactly, because the
  sums are integers
- `nest`'s hole count equals `sweep`'s cycle rank on 222 real components,
  100%, by two computations sharing no code
- band stitching is indistinguishable from a single sweep at every K
- four sweep orientations cost two scans
- maths font families are **100%** on U9's embedded-outline fast path
- **94.61% of maths glyph mass resolves to a Type 1 `.pfb` in the TeX
  tree** — including everything a producer embedded as Type 1C, so the
  outline route needs one parser and no PDF handling at all
- `type1.py` parses **7,616 fonts / 3,413,996 charstrings** with none in
  the wrong class and no file rejected

**Refuted, and the design changed:**

- **Band parallelism.** Decode is 85–95% of per-page work, so
  parallelising the sweep ceilings at **1.17×**. The tier was not built.
  *Conditional:* if decode ever stops dominating, re-take this.
- **Scheduler utilisation.** 3.26× on 16 cores, not near-linear — a 185×
  per-page cost spread means the slowest page sets the floor.
- **Reeb signature rotation invariance.** Survives ±3° only 41–78% of the
  time; `cycles` survives 80–99%. Exactly translation-invariant.
- **`pdfminer` boxes agree closely with ink.** 85% 1:1 — the rest is
  structure, not error.

## 5. The single highest-value next step

**Maths-symbol classification has never been measured**, and two partial
units are blocked on it. Every accuracy figure in the repository is body
text: U13's class filter (≥12 instances) excluded every `∑ ∫ √ ± ≤ ∈`,
and the only non-ASCII survivors were `“”ﬁ`.

It reads like a deadlock — the structure tree needs symbol identity, and
symbol identity needs something to classify against — but it is not one.
`algorithms.md` §11.1 has the resolution and it is already scoped:

> **For maths symbols the template comes from the font, not the corpus.**
> U9 measured maths font families at 100% on the embedded-outline fast
> path. A template for `∑` is one rasterisation of one glyph from the
> document's own font; the corpus only has to supply *queries*.

The corpus **cannot** supply templates — `∑` may appear three times in a
paper, and selecting pages for maths content raises density, not count per
class. So the dependency is a chain, not a cycle:

```
U9 rasterizer → maths templates → maths classification → U14 structure tree
```

**Progress, 2026-08-09.** The route through that chain is now measured
and its first link is built. `measure.py outlines` asked which format a
maths glyph's outline is actually in, and the joint distribution
overturned the marginals: reading only "48.13% Type 1C, 46.48% Type 1"
gives a plan of two charstring interpreters behind a PDF extractor,
while **94.61% of the same glyph mass resolves to a Type 1 `.pfb` in the
TeX tree**, Type 1C included, because the producer converted at embed
time. So the route is one parser, from disk, with no PDF handling —
`inkdrill/type1.py`, tested against 7,616 real fonts.

What remains of the rasterizer is the charstring **interpreter** (the
Type 1 stack machine: `hsbw`, the path operators, `callsubr`, `seac`,
flex) and **scan conversion** to an `InkMask`. The 2.166% of charstrings
that open `n callsubr` are exactly the ones only the interpreter can
verify, so it also closes the parser's own oracle.

~~**The U9 rasterizer is the unblocking move.** It also inherits the
self-validating property the design was built for: a query matched to a
template must agree on hole count and Reeb signature, so a mismatch is a
*detected* error rather than a confident wrong answer.~~

**Built, and the second half is REFUTED.** `measure.py maths`, the
first maths measurement in the repository: over 647 classes from five
TeX maths families, all channels read **70.94% correct, 2.01% wrong and
detected, 27.05% wrong and ACCEPTED.** The verifier catches 6.9% of
wrong answers. The signature is a 4-tuple of small counts, so hundreds
of maths glyphs share one and `agrees` accepts 91.19% of everything —
**a verifier must be INDEPENDENT of the classifier's failure mode, not
finer** -- `agrees(extents_tol=0.4)` cuts silently-wrong to 0.31%. More than a quarter of queries get a confident wrong answer
that nothing flags, which is precisely the failure this project exists
to prevent.

**That note is now measured and was wrong.** `measure.py rasterisers`
compared `scan` against Ghostscript on `cmr10` at four sizes: topology
agrees 19–20 of 20, the bitmap differs by **15 bits in 1024** at
body-text size, and Ghostscript lays down 18.8% more ink with the
excess shrinking as strokes thicken. A cross-*rasteriser* comparison
perturbs only a glyph's edge; a cross-*font* one changes the letterform.
They are not comparable, so do not expect the 61.5% row. The Reeb
signature, expected to be the robust channel, is the least robust of the
three.

## 6. Other open work, ranked

From `algorithms.md` §9, with status:

1. **`normalise` from the run list** — 6.7×, exact, ~25 lines. Also the
   only place violating the run discipline. *Open.*
2. **Struct-of-arrays `RunNode` store** — the largest remaining CPython
   win, invasive, measure first. *Open.*
3. **Cache `len(prevline)`** out of the two-pointer loop. Trivial. *Open.*
4. **Transposed mask** vs 4,960 strided column slices. Unmeasured. *Open.*
5. **`rows()` modal-height seeding** — **fixed 2026-08-09.**
6. **`group()` absorbing big-operator limits** — confirmed, **not fixed**;
   the proposed remedy does not reach it, and the real fix is symbol
   identity. Pinned by a test.
7. Native port sites. *Open.*

## 6a. Findings from the 2026-08-09 external audit

Reproduced in `measure.py boxes`; full record in `units.md`.

- **Box detection works, at a tenth of the proposed threshold.** The
  audit's `fill < 0.35` yields 125 false positives across nine text
  pages; `fill < 0.10` yields **0** and recovers exactly the same 29 of
  34 declared images. Its "zero false positives" claim came from
  looking at two control pages out of nine.
- **The reported depth-2 layer is glyphs.** Page 6's 21x21 "boxes" are
  italic zeros, established by rendering the pixels. The deepest chains
  built on them do not exist.
- **`pdfdrill`'s `images_layer` is a free independent oracle** — 29/34
  recovered to 1.72 pt, the border thickness. But a declared image only
  yields a rectangle when the figure is *drawn with a border*; on a
  random corpus sample recovery is 0/13 and the detector is not wrong.
- **`nest()` is 15.0x slower** than the two sweeps it is equivalent to.
  Recorded, not changed.
- **`Component.root` != `Component.nodes[0]`** on 1293 of 1310 real
  components. Now pinned by a test; see the conventions in `CLAUDE.md`.
- **The corpus now has a fixture with a declared answer.** `e12s39`
  is 1995 PostScript through Ghostscript, and its geometry is stated as
  arithmetic in the source. Panel width agrees to **0.072 pt** and tick
  pitch to **0.0007 pt** over 348 intervals. The ink sweep finds **0**
  of those 24 panels and the white sweep finds all 24 identically.
  Pinned by `tests/test_source_truth_corpus.py`.
- **U13's +24.8 signature figure is unverified and does not reproduce.**
  `m_classify` used four of the signature's six fields. Fixed and
  re-run by font, the signature adds **+4.4 points at n=6 and +0.3 at
  n=20**, against a recorded +24.8. The original run's `--n`/`--seed`
  were never published beside it, so it cannot be reproduced exactly —
  which is itself the finding. Treat the figure as open.
- **A non-LaTeX counterexample now stands on the record.** The Infineon
  handbook (Word 2016, 110 pages) sends U9's route B to **0 of 19
  fonts** — 100% TrueType, CambriaMath the only maths family — so the
  94.61% is arXiv-specific exactly as its stated population said. Its
  `images_layer` is **51.2% one repeated header logo**, and both layout
  detectors score 0/28 there because borderless JPEGs need the third
  polarity, **solid fill**, whose threshold was wrong by a wide margin
  (`fill > 0.9` recovers 1 of 34; `> 0.5` recovers 10). LaTeX draws
  frames and leaves gutters; Word pastes rasters.
- **White-run layout beats the ink detector at its own job.** Building
  layout from ink-bounded white runs recovers **33/34** declared image
  rectangles to 0.3 pt, against the ink detector's 29/34 to 1.72 pt —
  an ink frame's bbox carries its own stroke width as error. But the
  proposal's central claim inverts: white wants threshold **240**, not
  128 (19/34 -> 28/34 -> 33/34), because a white rectangle needs an ink
  BOUNDARY, not a white interior. Both detectors want the same
  threshold, so the "bracket" is retired. `measure.py white`.
- **Border colour per blob works, but not as costed or classified.**
  Sampling the 2 pixels outside each run is +28% on the sweep and 3% of
  decode+sweep+sample — but it needs RGB, which `pngio` discards, and
  retaining it costs ~3x decode on the NEUTRAL fast path where the
  answer is grey anyway. Quantising the samples was **refuted**: at
  step 32 the textured class collapses 2653 -> 25 and 2374 blobs
  promote to false "boundaries". And 2 colours is not a frame test —
  22.85% of blobs land there. `measure.py border`.
- **MathPix ignores non-white backgrounds** — 0 regions inside the
  tinted panels of pages 2 and 4, but 89 of 104 inside page 7's
  white-background screenshot. A blind spot with a stateable trigger,
  and its own residual class for U11.

## 6b. Maths classification, as of 2026-08-10

The chain `type1 -> charstring -> scan -> templates` is built and the
measurement it existed for is done.

| protocol | correct | wrong and ACCEPTED |
|---|---|---|
| 647-class open set, signature-only verifier | 88.10% | 11.90% |
| 647-class open set, `extents_tol 0.4` | 88.10% | 0.31% |
| **53-class candidate set (corpus median), `extents_tol 0.4`** | **96.45%** | **0.15%** |

The candidate-set model was checked against real co-occurrence rather
than left hedged: documents use a **median 4 of the 5** maths families,
and restricting the draw that way gives an **identical 96.45% / 0.15%**.
Even a single-family draw costs 1.4 points.

Two changes got there and neither was a model change: a verifier that is
*independent* of the classifier's failure mode rather than finer, and
the deployment protocol rather than the open set. Both cost false
rejection — ~14.4%, flat — which is the price and is stated with them.

## 6c. The maths layer — M1.1 done, 2026-08-10

The plan's one new measurement, taken before any graph exists.
`measure.py spacing`. The spacing residual `x0(b) - (x0(a) + adv(a))`
in em, against TeX's DEFINED math spaces.

**Typography explains the geometry for exactly one space.** The thin
space (3/18 em) is enriched **33x** in maths pairs over text pairs,
11.22% against 0.34%. Medium, thick and quad are not distinguishable
from the text distribution — so a relation graph gets one usable
spacing feature, not four, and should be built expecting that.

MI reads 0.059 efficiency and is the wrong summary: the classes are
imbalanced 225:1, so a feature sharp on 0.44% of the data cannot move
an aggregate. The likelihood ratio fits, and it is 33.

### T1 rule coverage is the open gap

`measure.py tables`: **72.1%** of table objects in a 20-document sample
are CONNECTED GRIDS, whose rules `emit` cannot see — it finds a rule
only when it is a separate component. Their cells are already emitted.
Extracting rules from a connected frame means reading the run structure
near the bbox edge; that is the next piece of work and it is the
majority case, not a completeness item.

The split is `booktabs` versus `\hline`, not LaTeX versus Word: pdfTeX
documents show connected grids too.

### T1 done — the writer exists

`inkdrill/emit.py` produces `lines.json` with `ocr.units = "pt"` from
`pHYs`, `table` + `simple_cell` with `cell_row`/`cell_column` from the
hole lattice, and `rule_width_pt` — which is what unblocks the rule
weights on the consumer side. Steps 4-5 of the spec (`diagram`, the
remaining `ink.*`) are open.

### M3 done (against synthetic graphs)

`inkdrill/rewrite.py` — relation graph to symbol layout tree.
Productions for `SupSub`, `Limits`, `Fraction`, `Root`; a refused match
becomes a `PLACEHOLDER` keeping its children, mirroring M2.3 one level
up. **Confluence is tested by permutation, not asserted** — 60 random
graphs at 24 orders each — and that test rejected the first
implementation, which ranked matches by node index rather than by
geometry. Scoring waits on M0's gold set.

### M2.1 done

`inkdrill/relate.py` — line-of-sight candidate edges. Measured on this
corpus before building: **LOS 99.95% reading-order recall at 0.96
edges/node**, against 6NN's 99.83% at 3.29 and 40,706 occluded pairs.
Best recall and fewest edges at once. Relation LABELS (M2.2) are the
other CLI's.

**M2.3 decided**: an unresolved node keeps its geometry and its edges,
and is refused only by rules keyed on symbol identity. `Symbol.label`
raises rather than returning a sentinel — two unidentified glyphs must
not compare equal — and carries the reason, because the 14.4%
abstention is the QC surface, not a gap.

### Open defect: spans are not raster-route-invariant

`emit`'s `cell_row_span` moves under a 16.7-per-million pixel
difference between the `png16m` and `pgmraw` routes — 254 of 761 lines
on `e12s39`. Band starts are exact hole `y0` values clustered at `tol`,
so a one-pixel shift can cross the tolerance and move every span past
it. Topology and the authored geometry are unaffected. Pinned by
`T11_3`; the invariance boundary is unmeasured.

### Unit 12 — the segmentation conventions already align

Answered without downloading anything, without the Infty licence and
without spending a page of credit: `mathgold` is on this machine, so
pdfdrill's own SLT convention can be read directly.

`parse_latex_slt` on four expressions:

```
x_i^2          nodes x, i, 2            edges  i->2 Sup,  x->i Sub
rac{a}{b}    nodes rac, a, b        edges  rac->a Above, ->b Below
\sqrt{x+1}     nodes \sqrt, x, +, 1     edges  x->+ Right, +->1 Right,
                                               \sqrt->x Inside
```

**Segmentation matches.** One node per symbol, and `rac` and `\sqrt`
are nodes in their own right — a rule and a radical are ink, so
`relate.py`'s components map to them one for one.

**The relation vocabulary is 1:1**, six against six:

| mathgold | `rewrite.Relation` |
|---|---|
| Right | HORIZONTAL |
| Sup | SUPERSCRIPT |
| Sub | SUBSCRIPT |
| Above | ABOVE |
| Below | BELOW |
| Inside | CONTAINS |

**One real mismatch, and it is in the attachment, not the vocabulary.**
For `x_i^2` mathgold CHAINS: `x -> i` (Sub) then `i -> 2` (Sup), so the
superscript hangs off the subscript. `rewrite.py`'s `SupSub` production
expects both scripts on the SAME root — `x -> 2` and `x -> i`. Scoring
against this gold without reconciling that would report every
sub-and-superscript pair as wrong for a reason that has nothing to do
with the labeller.

That is exactly the trade the audit warned about — an alignment problem
swapped for a different one — found here for the price of reading a
file. It is a small fix in one direction or the other, and it has to be
made before any number is quoted.

### Unit 12 coordination — inkdrill must NOT write `.lg`

The proposed deliverable was "both sides emit and consume the same `.lg`
representation, through `mathgold.slt.slt_to_lg`". `mathgold` is pure
stdlib, so importing it breaks no dependency rule — but it lives in
**pdfdrill's `src/`**, and inkdrill is standalone: no installer, no
build step, no sibling repo on the path.

The three options, and only one is good:

| | |
|---|---|
| inkdrill imports pdfdrill's `src/` | cross-repo coupling; breaks standalone |
| vendor `mathgold` into inkdrill | **two writers** — the exact trap this was meant to avoid |
| **inkdrill never writes `.lg`** | one writer, no coupling |

**inkdrill emits relations as `ink.*` additive keys in `lines.json`;
pdfdrill is the only `.lg` writer.** That preserves the one-writer
property *better* than the original proposal, because inkdrill then has
no `.lg` code path that could drift at all — and it needs no new
interface, since `lines.json` with namespaced additive keys is the
contract already agreed for tables and rules.

Unblocking Unit 12 therefore needs no coordination artefact beyond that
sentence. What it does still need, and what is NOT settled here:

- **Infty's licence**, checked directly rather than through the AGPL
  wrapper that fetches it. The dataset is not on this machine (only
  InftyReader, a different and commercial product), so this is
  unanswered.
- **Whether Infty's segmentation convention matches** what `relate.py`
  produces. If it does not, the alignment problem has been traded for a
  different one rather than removed.

### S4 — the DocReal bench cannot run as specified

Rows 1 and 2 only; no warp model was involved and none was needed.
Selection fixed before any result: first 8 originals by numeric id.

```
BASELINE  same original, threshold 128 vs 160 agree:  0/8
FLOOR     distorted vs original, no dewarp:           0/8
          component-count drift: median 95.6%, max 1158%
```

**The baseline fails, so the bench measures binarisation and not
transport.** The same page at two thresholds gives (1758, 391) against
(1016, 555) — the topology gate is not stable on these inputs at all,
and a transport-versus-resample comparison run on top of it would be
comparing noise.

The cause is the input class, not the gate. `topology_preserved` is
stable on RENDERED pages — 910/1011 across the `png16m` and `pgmraw`
routes despite 259 differing pixels. DocReal is **photographs of
paper**: uneven illumination, so a single global threshold moves
component counts by a factor of two.

**Consequence: A6/A7 cannot be validated on DocReal until a local
binarisation exists**, which is a separate unit and does not exist. The
alternatives are rendered warps with a known field, or a gate that does
not rest on raw counts.

**The histogram answers it in one pass, and overturns my explanation.**
DocReal's scans are **not** valley-filled: ink peaks at 68–71, paper at
255, and the valley sits at **165–186**. I binarised at **128** — on the
ink-side shoulder, where mass is still falling. 0.05–0.09% of samples
lie in the 126–130 band I nudged, which on a 34 Mpx page is tens of
thousands of pixels, quite enough to move 6% of components.

So the drift was mostly an artefact of **my threshold choice**, not of
the scans — and re-measuring at the valley confirms it:

| binarised at | exact | component drift median | max |
|---|---|---|---|
| 128, the ink-side shoulder | 0/8 | 6.04% | 11.89% |
| **175, the valley** | 1/8 | **0.38%** | **1.19%** |
| floor: distorted, no dewarp | 0/8 | 95.6% | 1158% |

**Ten times better, and the headroom against the floor goes from 8x to
80x.** A tolerance of 2% sits clear above the worst baseline page
(1.19%) and two orders below the floor, so `topology_within(tol=0.02)`
separates them on this sample where `topology_preserved` cannot —
exact agreement is still only 1/8.

**The answer-key bench is therefore available**, and local binarisation
is needed only for the distorted side. That is the opposite of the
conclusion drawn from the shoulder measurement, and the difference was
one badly chosen threshold.

One caveat that survives the good result: **the valley position varies
by page** — 165, 186 and 181 across three samples — so a global 175 is
itself a compromise and part of the 0.38% is 175 happening to suit these
eight. The honest form is a per-page valley, which is most of the way to
the local binarisation the floor row needs anyway.

One histogram per page found this; twenty-four sweeps only counted
failures.

**Re-run at ±2 — the conclusion was right about equality and wrong
about the bench.**

```
BASELINE at +/-2: exact agreement 0/8
  component-count drift: median 6.04%, max 11.89%
FLOOR (distorted, no dewarp):
  component-count drift: median 95.6%, max 1158%
```

Exact equality still fails on every page, so `topology_preserved` as
written cannot gate this input — that part of the original conclusion
stands, and it is not the nudge's fault.

**But baseline noise and floor drift are 16x apart**, 6% against 95.6%,
and that is the finding the 32-level nudge hid. A gate on *equality*
cannot run here; a gate on a **tolerance** has an order of magnitude of
headroom. So "the bench cannot ask the question" was too strong: it
cannot ask it with an exact-match instrument, and the instrument is the
part that has to change.

Two pages are nearly stable across ±2 — id 2 reads 1092/1095/1094 and
id 5 reads 262/262/262 — while id 1 moves 1902 → 1598. **The
instability is per-page, not uniform**, so any tolerance must be
justified against the worst page rather than the median, and 11.89% is
that number for this sample.

**The original weakness, for the record.** The baseline nudge was
128 → 160, 32 levels, where the rendered-page precedent used ±2.

The proposed explanation was that the `scanned` references are
photographs and carry illumination structure of their own. **Measured,
they do not**: quadrant grey means on three references are
248/245/246/252, 243/248/247/252 and 249/250/249/252 — a spread of
**3 to 9 levels out of 255**. They are clean flatbed scans, essentially
flat.

So the baseline failure is the 32-level nudge moving anti-aliased stroke
edges, not illumination on the reference side. **That row must be
re-run at ±2 before the answer-key version is called blocked.** The
FLOOR row's 95.6% drift stands regardless — that is the distorted side,
which is photographed.

**Data as found, both claims checked:** 50 originals, **200** distorted
PNGs, exactly 4 per original, no orphans in either direction. The
"201st file" is a non-PNG entry, not a stray variant.

#### The self-referential bench can run without the original

The thesis is transport versus resample, and neither path involves the
reference: both operate on the same distorted variant at the same
threshold, so **binarisation instability cancels**. The instability
makes the absolute count arbitrary; it does not make the COMPARISON
arbitrary.

The measurable claim weakens accordingly — not "the count is preserved"
but **"the ordering is stable"**: transport nearer the pre-transform
topology than resample, at every threshold. That is what this data can
support, and it needs a transport implementation, which does not exist.

### S4 on real ink — the hatching is fixed, the result is mixed

`transport` now moves a run as its pixel AREA — the quadrilateral
`[lo, hi+1) x [line, line+1)` mapped and scanline-filled — so
neighbouring runs still touch after the map. Re-run on the same crops:

```
       source        transport (was)        transport (now)   resample
  1   (436, 180)     (408, 2238)            (401, 213)        (337, 188)
  3   (317, 1878)    (311, 22674)           (308, 2532)       (276, 2174)
```

Cycles fall from 22,674 to 2,532 — the hatching is gone.

**The result is now genuinely mixed, 1 of 3.** And the pattern is
consistent across all three: **transport preserves COMPONENTS better,
resample preserves CYCLES better.** 401 against 337 for a source of 436;
213 against 188 for a source of 180.

`transport_is_nearer` takes the max of both drifts, so cycles decide it.
Whether that is the right summary is now the open question, and it is a
better question than the one this started with — the thesis is not
simply true or false, it is **channel-dependent**, and which channel
matters depends on what the dewarp feeds.

### S4 on real ink — the earlier run, transport lost 0/6 to a bug

```
id   source        transport        resample
 1   (436, 180)    (408, 2238)      (337, 188)
 3   (317, 1878)   (311, 22674)     (276, 2174)
 6   (1640, 7239)  (1319, 36964)    (1264, 6386)
```

**Transport multiplies holes by an order of magnitude** while the
control tracks the source. That is a defect in `warp.transport`, not
evidence about resampling.

Each run is drawn as an **independent line**, so two runs adjacent
before the rotation land as two 1-pixel lines that no longer touch. A
solid region becomes hatched and every gap is a new hole. G2 —
connectivity ALONG a run — is true and was never sufficient;
connectivity BETWEEN runs is what a solid region is.

**The synthetic fixtures hid it precisely because they were thin
rings** — almost no adjacent runs. Real text is nearly all adjacent
runs. So the fixture I declined to tune was also the fixture that
concealed the bug, and only real ink exposed it.

The fix is to transport a run as an AREA — a quadrilateral between
consecutive scan positions — rather than as a centre line. Until then
the thesis is untested.

### S4 self-referential bench — synthetic fixtures do not separate

`inkdrill/warp.py`: `transport` (map each run's endpoints, redraw the
run), `resample` (the control — bilinear then threshold), `compare`, and
`corner_affine` as the crude phi. Neither path touches an undistorted
reference, so a threshold wrong for the page is wrong for both
identically — which is what makes it runnable where the absolute count
is unstable.

**On synthetic fixtures the two paths do not differ:**

```
1 px rings, rotated      deg 0   transported (4,4)   resampled (4,4)
                         deg 3   transported (4,4)   resampled (4,4)
                         deg 7   transported (4,3)   resampled (4,3)
```

Where topology is lost at 7 degrees, **both lose the same hole** — to
the page edge, not to sampling. So the ordering claim is untested and
the machinery ships with the question open.

A fixture could be shaped until it showed a difference. That would be
choosing the answer, which is the failure this project has now found six
times, so it was not done. **The real bench is DocReal at a valley
threshold**, where the ink is real and thin strokes are not a fixture
parameter.

### T4 — skip the hole geometry when nothing needs it

A page of plain text has no table and no diagram, so it needs the hole
*count* but not the hole *geometry*. `nest.ink_only()` returns an
`InkPass`: the ink regions `nest` would produce — **ids included, not
merely equivalent** — plus each component's `cycle_count`, which **is**
its hole count (checked equal to `len(holes_of(id))` on every page
measured). `page_lines` gates the background sweep on there being a
component that could be a table or diagram.

**The ids are the whole reason this is safe.** Emitting `region_id`
from two different spaces depending on what happened to be on the page
is the trap this package has paid for twice. `nest` numbers ink
`0..n_fg-1` from the ink sweep alone and offsets the background
afterwards, so an ink region's identity never depended on the sweep
being skipped.

**The first version was a trade, not a saving**, and the measurement
caught it: `ink_only` and `nest` each ran their own ink sweep, so text
pages got 34% faster and table pages 30% slower — a **net loss** over
Infineon's 110-page mix (76 structural, 34 text). `InkPass.complete()`
now reuses the ink pass:

| page | before T2 | naive gate | reusing gate |
|---|---|---|---|
| Heim p229 (text) | 1.22 s | 0.76 s | **0.85 s** |
| Infineon p19 (table) | 0.95 s | 1.24 s | **1.05 s** |
| 1408.0838 p8 | — | 3.80 s | **3.23 s** |

**Both surviving mutants were performance-only, and that is the
signature of a correct optimisation** — doing work that was not needed
cannot change the output, so no output test can reach it. The only
killable mutant is the one that *skips* work it needed. The mechanism
is therefore asserted by COUNTING: `complete()` must do exactly one
further sweep, and a text page must not call `_build` at all.

One of those counting tests could not fail on its first draft: it spied
on `emit.nest`, but the code reaches the forest through
`InkPass.complete()`, so the spy never fired whatever the gate did. It
now spies on `nest._build`, which both paths go through, and the
opposite case is asserted on the same spy.

### T3 — stdin and concatenated PNM: no temp file in the pipeline

`gs -sDEVICE=pgmraw -sOutputFile=%stdout | python3 -m inkdrill - --dpi 400`
now runs with nothing touching disk. Both details of the format are
handled: Ghostscript writes a `#` comment line after the magic (already
skipped by `_token`), and a multi-page render arrives **concatenated**
rather than as one image.

    $ gs ... -dLastPage=4 -sOutputFile=%stdout doc.pdf \
        | python3 -m inkdrill - --dpi 60 --glyphs --stats
    <stdin>  4 pages @ 60 dpi
      load   0.08s   emit   0.98s   2663 KB
      lines 6872: {'glyph': 6869, 'simple_cell': 2, 'table': 1}

Four pages in, four page records out, numbered from `--page-number` so
a caller rendering pages 7–9 gets the document's own numbering.

**`read_pnm` still refuses trailing bytes.** That refusal is how a
caller learns it passed something other than what it thought, so the
stream is a *different function* — `read_pnm_stream` — rather than a
relaxed flag on the old one. Both halves are asserted: the single
reader raises on a two-image buffer, and the stream reads it.

Four mutants, all killed: the trailing-byte refusal, the stream
terminating after one image, the end index, and the inter-image
whitespace skip.

### T2 — a `glyph` line type: a text page emits 1,162 instead of 0

The blobs existed and nothing emitted them, so a scanned text page
produced an empty `lines.json`. `page_lines(..., glyphs=True)` now
emits one line per ink component — box in points, ink area, hole count,
principal axis. **No classification and no name**: that needs symbol
identity, which this project records as a gap rather than guesses at.

| page | time | lines |
|---|---|---|
| Heim scan p229 | 1.22 s | **1,162 glyph** |
| Infineon p19 | 0.95 s | 1 table, 52 cells, **941 glyph** |

Every glyph carried an axis; none fell back.

**No size filter, and that is measured rather than assumed.** On the
Heim page 1,161 of 1,164 components lie inside any reasonable size
bound (heights p1=4, p50=44, p99=90 px against a 44 px text scale), so
a bound would be a threshold that changes nothing except what a future
dpi silently retunes. A consumer filters on the emitted `area`.

**Two id spaces, joined on exact geometry.** Moments come from `sweep`
and are keyed by `Component.root`; `table`/`diagram` lines are keyed by
`Region.id`. Rather than carry both into one file they are joined on
`(x0, y0, x1, y1, area)` — exact, because `nest` now labels with that
very sweep, so the two are the same partition. A region with no unique
match keeps its geometry and loses only the axis, which is **absent
rather than null**.

Opt-in, because it changes what every existing consumer receives.
`python3 -m inkdrill page.png --dpi 400 --glyphs`.

Five mutants, four killed (the switch, the already-emitted guard, the
hole count, the axis key). One survives and is recorded rather than
defended with a contrived fixture: the ambiguous-geometry guard, since
two 8-connected components sharing an exact box *and* area is possible
in principle and no fixture reaches it.

### T1 — `nest()` relabelled by two sweeps: 10.7x to 29.9x, identical

The recorded per-pixel flood-fill defect, fixed. `nest()` now labels
with `sweep(m, conn=8)` for ink and `sweep(m.inverted(), conn=4)` for
holes-plus-outside — the same partition, because the connectivity pair
is the same — and the parent lookup binary-searches a per-line run
index rather than reading a label array.

| page | before | after | speedup | identical |
|---|---|---|---|---|
| Heim scan p229 | 21.83 s | 0.80 s | **27.3x** | yes |
| Infineon p19 | 18.23 s | 0.61 s | **29.9x** | yes |
| 1408.0838 p8 | 18.20 s | 1.70 s | **10.7x** | yes |

**Byte-identical, ids included.** Two things had to be reproduced
rather than merely computed, both about identity: ids are assigned in
**raster order of each region's first pixel**, because that is what the
flood fill's `for s in range(w * h)` did and `Nesting.roots` is ordered
by id; and the parent is the region directly above a region's
topmost-leftmost pixel. Getting ids right is what makes this an
equality rather than an isomorphism, so a caller keying on `roots`
order is unaffected.

`_label` is kept as the **reference oracle**, exercised only by
`T6_8_TwoSweepsEqualTheFloodFill` — the project's usual shape, a second
independent computation rather than a golden file. The two share no
code: one walks pixels with a stack, the other unions runs. Four
mutants, all killed: id order, the parent row, background connectivity,
and the unpadding.

**F2 closes with it**, since 97% of `page_lines` was `nest`:

| page | `page_lines` before | after |
|---|---|---|
| Heim scan p229 | 21.80 s | **0.76 s** |
| Infineon p7 | 18.02 s | **0.60 s** |
| Infineon p19 | 17.93 s | **0.61 s** |
| 1408.0838 p8 | 17.72 s | **1.69 s** |

`load_mask` is now the dominant cost at 8–11 s — the PNG decode, which
is the already-recorded 85–95% and the reason the PNM route exists.

### S1 — merging lifts the white-run route to 8/14, still not enough

The fragmentation was the whole result, so the hypothesis was that it
is a GROUPING problem: seven fragments of one figure are adjacent gap
blobs that should have merged. `_merge_boxes` unions boxes whose
rectangles touch within a tolerance, to a fixed point, **before** the
size filter — dropping sub-`min_block` pieces first would discard
exactly the fragments that need joining.

**The first run looked like a clean refutation and was an ordering
bug.** 285 boxes collapsed to 12 at a tolerance of *one pixel*, and all
14 figures came back `missed`. The cause: the page-spanning block was
excluded *after* merging, and it touches every other box, so it
swallowed the page. Excluding it before merging fixed it. A refuted
hypothesis and an order-of-operations bug read identically from the
output.

| `merge_tol` | matched | fragmented | missed | spurious |
|---|---|---|---|---|
| 0 (baseline) | 6 | 7 | 1 | 0 |
| **4 – 30** | **8** | **5** | 1 | 3 |
| 60 | 8 | 5 | 1 | 5 |
| 120 | 9 | 4 | 1 | 8 |

Stable across 4–30 px, which is an invariance rather than a tuned
value. But it lifted **2 of 7** fragmented cases, not the half the
acceptance criterion asked for, and it introduced 3 spurious blocks
while the worst matched side error rose from 195 px to 681 px. Beyond
30 px, matched climbs 8 → 9 while spurious climbs 3 → 8: no clean
operating point.

**Decision unchanged: NOT wired into `page_lines`.** 8 of 14 with 5
still fragmented would emit multiple lines per figure plus three
objects that are not there.

### S2 — F2 is not a filtering problem, it is `nest()`

Re-measured on comparable pages after F1 and the containment change:

| page | `load_mask` | `nest` | `page_lines` | lines |
|---|---|---|---|---|
| Heim scan p229 | 1.24 s | 21.19 s | **21.80 s** | 0 |
| Infineon p7 (figures) | 10.74 s | 18.12 s | **18.02 s** | 99 |
| Infineon p19 (table) | 7.83 s | 17.69 s | **17.93 s** | 53 |
| 1408.0838 p8 | 8.35 s | 17.96 s | **17.72 s** | 3 |

It fell from 31.7 s to ~18–22 s, so removing the spurious lines helped.
But **`page_lines` ≈ `nest()` + 0.6 s** — 97% of it is `nest`, which is
the already-recorded defect: `nest()` is 15.0x slower than the two
sweeps it is equivalent to, because it flood-fills per pixel.

**F2 does not close, and no amount of further filtering will close it.**
The remaining cost is one known defect with a known, measured-equivalent
replacement. That is its own piece of work on a core unit, not a
continuation of this one.

### S3 — the grey-histogram route rule is NOT supported

The proposal was that the routes are equivalent on bimodal pages and
not on tonal ones, so the grey histogram says which. Measured, at each
page's own threshold:

| page | distinct greys | mass within ±8 of threshold | diff / 1e6 |
|---|---|---|---|
| e12s39 p1 | **2** | **0.0** | **16.7** |
| 1408.0838 p8 | 4 | 123.7 | **0.0** |
| 1408.0838 p13 | 6 | 68.0 | 1265.6 |
| 1809.09528 p6 | 3 | 0.0 | 0.0 |
| 1809.09528 p9 | 2 | 0.0 | 0.0 |

Neither statistic predicts the disagreement. **e12s39 p1 is the
counterexample: 2 distinct greys, zero mass anywhere near the
threshold, and 259 samples still differ** — which directly contradicts
"on bimodal ink there is nothing to convert and the routes are
bit-identical". And p8 has the most mass near the threshold of any page
here and disagrees on nothing.

The reason the histogram cannot predict it: **`png16m` and `pgmraw` are
two independent Ghostscript renders, not two conversions of one
buffer.** Colour reduction is one contributor; device-level rasterisation
and anti-aliasing is another, and on bimodal line art it is the only
one left. A histogram of one render says nothing about how the other
render drew its edges.

So the rule is **not** put in the contract. The non-claim stands as it
was: the routes are not interchangeable, and `1408.0838` p13 is the
named page. Three of five pages here do agree exactly, so a cheap
predictor may well exist — it is not this one.

### F4 re-measured — the amplification is closed, by F1's cell floor

Found by re-running the opt-in corpus suite after a crashed session:
`test_emit_is_NOT_route_invariant_KNOWN_DEFECT` **failed**, because the
two routes now agree. Its own docstring said that if they ever agreed
the test should become an equality assertion.

**The input perturbation is unchanged** — 259 samples of 15,465,468
differ between the PNG and PGM routes, 16.7 per million, exactly as
recorded. What changed is that it no longer moves the output.

**The cause was NOT what I first wrote.** The first explanation blamed
the `diagram` containment rule; the test passed with that rule off, so
the explanation was wrong. Sweeping the cell floor on the page, every
other filter off:

| `cell_scale` | lines | differing |
|---|---|---|
| 0.0 | **761** | **254** ← the recorded defect, reproduced exactly |
| 1.0 | 166 | 1 |
| 2.0 | 98 | 0 |
| 3.0 (default) | 81 | 0 |

**F1's cell floor closed F4.** The 761 lines were overwhelmingly
spurious cells and the unstable spans were spans *between* them.
Removing the population removed the instability — the chain was never
made more robust, and the instability would return with the
population. That is a filter holding a guarantee, not a guarantee.

**Route interchangeability is still NOT claimed, and the counterexample
is named.** On `1408.0838` p13, an anti-aliased figure page at
threshold 128:

| page | samples differing | per million | topology |
|---|---|---|---|
| e12s39 p1 (line art, th240) | 259 / 15.5M | 16.7 | identical |
| 1408.0838 p8 (th128) | 0 | 0.0 | identical |
| 1408.0838 p13 (figure, th128) | 18,934 / 15.0M | **1,265.6** | **2633 vs 2656** |

p13 is 76× the perturbation and the *topology itself* differs, so the
PNG route emits two diagrams there and the PGM route none. That is not
the chain amplifying a small difference; it is the two masks not being
the same page, and no emit-level guarantee can repair it.

The test now asserts equality **and** asserts the input perturbation is
still non-zero and still under 100 per million — so it cannot pass by
the renderers quietly converging, which would make the equality prove
nothing.

### The white-run half — measured, and NOT wired in

p10 was the named failing case for the containment rule: a figure whose
plot data touches its own frame, so nothing is enclosed and `nest`
sees nothing. `measure.py blocks` measures whether the white-run route
recovers it.

**The computation is the COMPLEMENT, and getting that wrong first cost
a run.** A white *gap* blob is the background AROUND content, so
comparing its size to a figure's compares two different objects — it
read 30–100% error. The content blocks are the complement of the gap
mask (Baird 1994, Breuel 2002 in run form), and those land within a few
percent.

**On the named case it works.** p10's chart matches a single block at
**IoU 0.80**; p7's at **0.97**.

**On the population it does not generalise.** Infineon handbook, 12
pages MathPix labels with a figure/chart/diagram, 14 figures,
`min_len=60`, IoU ≥ 0.5:

| | |
|---|---|
| matched | **6** |
| fragmented | 7 |
| missed | 1 |
| merged / split | 0 / 0 |
| spurious | 0 |

Matched blocks carry a median side error of 116 px (max 195). Raising
`min_len` is monotonically worse — at 300 px, matched falls to 3 and
spurious explodes to 32.

**Decision: NOT wired into `page_lines`.** Half the figures come back
fragmented, and emitting seven fragments as seven `diagram` lines is
worse than the current silence on p10. The route detects better than it
delimits, and `page_lines` needs a delimiter. Recorded like U8's band
tier: measured, decided, not built.

**Two harness defects on the way, both the same shape — a class that
could not occur.**

1. The first classifier counted ANY overlap as coverage, so a figure
   overlapping its own inner blocks read as `split`. It reported **10
   of 11 split** with the single "match" carrying a whole-page error.
   That number was a harness artefact, not a finding.
2. A **page-spanning block** stayed in the candidate list. It overlaps
   every truth, so a figure covered by nothing real read as
   `fragmented` rather than `missed` — and `missed` read **0 at every
   setting**. A zero that cannot be anything else is not evidence.

Both are now pinned by tests that assert each class *fires*, and the
classifier is extracted so it can be tested at all. This is the third
harness defect in the project and the second of the empty-class shape.

**And the run was killed by the OOM killer** at `Capture.GRAPH` over
three `min_len` values in one process. `moments_per_component` needs
the nodes, not the adjacency — `Capture.NONE` brings it to 254 MB.

### The diagram floor replaced by CONTAINMENT — no threshold at all

The audit was right that the size floor is a threshold needing
per-corpus retuning, and that the exact test was already computed.
**A table cell contains 91 ink components; the counter of an `o`
contains none.** `nest.ink_in_hole` is that relation, and it is
deliberately distinct from `hole_of` for exactly this reason.

`page_lines` gained `require_content=True`: a region becomes a
`diagram` only when one of its holes holds a **separate** ink
component. The size floor stays as a cheap pre-filter.

**Measured against MathPix's own page labels**, Infineon handbook, six
pages of each kind:

| MathPix says | pages fired, size | pages fired, containment | objects, size → containment |
|---|---|---|---|
| HAS figure | 6/6 | **5/6** | 548 → 12 |
| HAS table | 6/6 | **6/6** | 18 → 6 |
| NEITHER | 6/6 | **1/6** | **1549 → 1** |

End to end, with `diagram_scale` left at its default:

| page | size only | + containment |
|---|---|---|
| Heim p229 (scanned text) | 3 diagrams | **0** |
| Infineon p19 (table) | 2 diag, 1 table | **0 diag, 1 table** |
| Infineon p3 (MathPix: nothing) | 24 diagrams | **0** |
| Infineon p7 (MathPix: figure) | 57 diag, 5 tab | **1 diag, 5 tab** |
| Infineon p10 (MathPix: figure) | 2 diag, 1 tab | 0 diag, 1 tab |

**The cost is real and is one page in six.** p10's figure is a single
connected component — the plot data touches the frame — so nothing is
loose inside it and containment cannot see it. The page is not silent
(its table still emits), but the figure is lost. That is the honest
residual and it is the same gap named below: an **unenclosed** figure
is what the white-run gap analysis finds, and that half is built and
not wired into `page_lines`.

**The fixtures had to change, and the change is the lesson.** Four
tests were bare rectangles, and a bare rectangle is not a diagram under
this rule — correctly, there is nothing in it to be a diagram *of*.
They now have plot data inside them, which is what a real figure has.
This is "a synthetic grid has no letters in it" in another costume, and
it is the third time that fixture mistake has surfaced.

Five mutants, one survivor, now killed: the `ink.contains` count could
be dropped entirely with nothing failing. It is the **evidence** for
the call — a consumer wanting a stricter cut than "at least one"
applies it to that number instead of re-running `nest` — so a missing
value silently removes the option.

### A — the font route, and topology's blind set is REFLECTIONS

`measure.py separability` runs the whole font route on a real
document's own embedded font — `mutool extract` → `type1.load` →
`charstring.outline` → `scan.render` → `sweep` — and reads the
partition it produces.

**How far the route reaches, measured first** (`measure.py fontmix`,
60 corpus documents, one PDF each, seed 20260807):

| | |
|---|---|
| only CFF/TrueType/CID | 35/60 — **58%** |
| Type 1 text face, parses | 16/60 — **27%** |
| no embedded font at all | 8/60 — 13% |
| Type 1 present, no usable text face | 1/60 — 2% |

The route runs on the second class only. This is a demonstration on a
**minority of the corpus** and is not a coverage claim. The last class
is the scanned document — Heim, WDorg4 — where there is no font to read
and the image path is the whole of what inkdrill has.

**What the partition says.** Three documents' own faces, 96 px/em:

| document | inked glyphs | classes | largest class |
|---|---|---|---|
| 1408.0838 | 82 | 5 | 55 (**67%**) |
| 1809.09528 | 80 | 5 | 53 (**66%**) |
| Meta-Learning_with_GNN | 84 | 4 | 55 (**65%**) |

**Two thirds of a real text face lands in one topology class** —
`(1, 0)`, one component and no hole: `C E F G H I J K L M N S T U …`.
This is `reeb.signature`'s docstring claim ("a stable partition, **not**
a classifier") measured on real embedded fonts rather than argued.

**The named maths pairs, and the structural reason.** cmsy10 and
cmex10, by glyph name:

| pair | | verdict |
|---|---|---|
| union / intersection | (1,0) vs (1,0) | BLIND |
| lessequal / greaterequal | (2,0) vs (2,0) | BLIND |
| lessmuch / greatermuch | (2,0) vs (2,0) | BLIND |
| unionsq / intersectionsq | (1,0) vs (1,0) | BLIND |
| plusminus / minusplus | (1,0) vs (1,0) | BLIND |
| summationdisplay / productdisplay | (1,0) vs (1,0) | BLIND |
| uniondisplay / intersectiondisplay | (1,0) vs (1,0) | BLIND |
| circleplus / circleminus | (1,4) vs (1,2) | SEPARABLE |
| integraldisplay / contintegraldisplay | (1,0) vs (1,2) | SEPARABLE |

**Reflection was the wrong explanation — corrected below.** It is true
that `(components, cycles)` is reflection-invariant, but that is not
what binds: `F` and `E` are not reflections of each other and are blind
anyway.

### A, corrected — cardinality binds, and it is NOT irreducible

`measure.py alphabet`. Two corrections in one measurement, and one of
them is against the audit that prompted it.

**The audit is right that CARDINALITY binds, not reflection.** U12's
ceiling arriving in a third place. But quote **efficiency**, never the
class count — four classes bound two bits only if they are equal in
size, and 40 of 62 characters land in `(1, 0)`:

| face / population | channel | classes | largest | efficiency |
|---|---|---|---|---|
| DejaVuSans, ASCII | (components, cycles) | 4 | 40/62 = 65% | **22%** |
| | reeb signature, row | 16 | 16/62 = 26% | 56% |
| | reeb signature, **row+col** | 29 | 6/62 = 10% | **75%** |
| FreeSerifb, ASCII | (components, cycles) | 4 | 40/62 = 65% | **22%** |
| | reeb signature, **row+col** | 45 | 5/62 = 8% | **89%** |

So the channel carries **1.3 bits of the 5.95 needed, not 2.0** — the
cardinality bound overstates it, which is exactly U12's lesson.

**The population is a decision and it changes the answer.** Adding the
Latin-1 accented forms this corpus actually contains raises
`(components, cycles)` from 22% to 33%, because an accent is a *second
component* and the invariant can see it. A Latin-only figure
understates the channel on German text and a German figure overstates
it on English. Both are reported; neither alone is the number.

**Where this parts company with the audit: the ceiling is NOT
irreducible by a better invariant of the same kind.** The audit
concluded it "can't be reduced by a better invariant of the same kind,
only by a different channel". A finer invariant of exactly that kind,
already in this package, lifts it — and running the sweep on **both
axes** lifts it to 75–89%, largest class 65% → 8%.

**The two axes are complementary, and that is the transferable part:**

| pair | row | col |
|---|---|---|
| union / intersection | SEPARABLE | blind |
| lessequal / greaterequal | blind | SEPARABLE |
| summationdisplay / productdisplay | SEPARABLE | SEPARABLE |
| plusminus / minusplus | blind | blind |

A **vertical** reflection falls to the row sweep; a **horizontal** one
falls to the column sweep. **Six of the seven pairs** that
`(components, cycles)` calls blind are separated by running both.
`reeb.signature` is documented as *not rotation invariant* — that
recorded limitation is precisely what does the work, and axis
disagreement is information rather than a defect. Only
`plusminus/minusplus` survives both.

**Scope.** Clean rendered glyphs at 96 px/em — a ceiling on a ceiling.
U13 already measured that the signature degrades on scanned ink, so
this says what the channel can carry at best, not what it delivers on a
page. It does not license dropping the extents channel.

### C — the OCR substitution audit: 60%, not eight of eight

`measure.py substitutions` asks the whole cross-check thesis as one
number: when a real OCR engine substitutes one character for another on
a real scan, does the **topology** of the two readings differ? Where it
does, a disagreement is detectable without recognition. Where it does
not, inkdrill is silent and must say so.

**Population and split rule.** The truth is a human transcription of
chapter 1 (`Heim_ES_1/tex/chapter_01_de.tex`, 5,169 words); the OCR is
InftyReader's per-page `.tex` for the scanned pages of the same book,
290 pages from page 18. Only the **4,417 words that align** under
`difflib` contribute. Nothing is claimed about the rest — the
transcription covers part of what those pages hold, which is why the
aligned share reads 7.8% of the OCR stream and the aligned *count* is
the population, not the ratio.

**The filter, which is a decision.** Only 1:1 single-character
substitutions inside an equal-length aligned word pair are counted:
**101 kept in 33 distinct pairs, 434 dropped** (split, merged and
multi-character errors). Splits and merges are the other large OCR
class and would compare a one-glyph topology against a two-glyph one.
Do not quote the 101 without the 434.

| face | px/em | pairs separable | occurrences separable |
|---|---|---|---|
| serif (FreeSerifb) | 96 | 18/30 (60%) | 60/98 (61%) |
| serif | 48 | 17/30 (57%) | 59/98 (60%) |
| sans (DejaVuSans) | 96 | 19/33 (58%) | 61/101 (60%) |
| sans | 48 | 18/33 (55%) | 60/101 (59%) |

**The auditor expected eight of eight. The mechanical population says
60%,** stable across two faces and two sizes. Eight of eight is what a
hand-picked eight gives; this is the same population lesson as U0's
colour fraction and U13's `count >= 12`, arriving through the front
door for once.

**What it is blind to, by name** — 14 pairs, 40 occurrences in the sans
face: `I/l` ×14, `y/v` ×9, `t/r` ×4, `U/u` ×3, `F/E`, `W/w`, `f/l`,
`f/r`, `'/,`, `o/O`, `ì/i`, `í/i`, `ţ/l`, `ţ/t`. Every one is a stroke
against a stroke, or a ring against a ring. This is the boundary of
what ink alone can say, and it is the reason this is a cross-check and
not a recogniser.

The single most common error, `@`→`s` ×19, **is** separable — `@`
closes and `s` does not — so the largest class is one topology catches.

**It is a CEILING, not a detection rate.** It renders both readings
from a clean font, so it measures whether the two are *separable*. On
the page the ink is degraded, and a broken `s` can acquire the hole
that makes it look like the `@` the engine reported. Detection on the
scan needs a character-to-blob alignment this corpus has not got, and
that is the honest next measurement.

Two mutants, one real: forcing the length guard off makes the aligner
`zip` unequal blocks and **manufacture** a `y`→`z` substitution out of
words that are not each other — a fabricated pair is worse than a
missing one, and it is now pinned. The second, replacing the opaque
maths marker with a space, was **equivalent**: the whole `$...$` span
goes either way, so the marker and its filter were removed rather than
left standing as machinery that looks protective and is not.

### F1's twin fixed — a figure is not letter-sized

`diagram` had no size floor at all while `table` had one, so a hollow
glyph with fewer than two holes fell through the table branch straight
into it. A scanned German page emitted 305–319 lines, every one a
`diagram`, median 5.3 x 7.4 pt: every `o`, `e`, `a`, `ü`.

| `diagram_scale` | Heim scan, no figures | arXiv p6, real frames |
|---|---|---|
| 0.0 | 305 | 703 |
| 1.0 | 305 | 684 |
| **3.0** | **3** | **128** |
| 10.0 | 0 | 94 |

**Acceptance met**: near-zero on the text page, frames retained on the
figure page. The separation is weaker than the cell floor's — the real
page keeps falling (128 → 94) rather than holding flat — so 3.0 is
justified by the *plateau forming* rather than by invariance, and that
is a weaker warrant, stated as such.

Note the bound runs the other way from the cell floor. A **cell** is
bounded below because it CONTAINS text; a **diagram** is bounded below
because it REPLACES text — a figure occupies space a paragraph would
have. Different arguments, same threshold shape.

### F1's twin — the finding, before the fix

The Heim scans run through the CLI now. `BH1-000229.png`, a scanned
German physics page at 400 dpi, emits **305 lines, every one a
`diagram`** — on a page that is body text and equations.

Their sizes say what they are:

```
page text_scale (median ink height)   44 px = 7.9 pt
diagram width  pt   min 2.70   median  8.64   max 76.32
diagram height pt   min 7.56   median 11.52   max 42.12
```

**A median diagram is 8.6 x 11.5 pt — one letter.** A hollow glyph with
`fill < 0.35` and fewer than two holes falls straight through the table
branch into the diagram branch, which has **no size floor at all**.

So F1's fix covered `table` and `simple_cell` and left the third class
untouched. The same rule applies and for the same reason — a figure is
not letter-sized — but it needs its own acceptance pair before it
ships: a page with real plot frames kept, and this page near zero.
2409.18839 p6 emitted 648 diagrams under the same rule and is the
obvious first half.

### F1 fixed for tables — a cell is bigger than the text inside it

`page_lines` now requires a cell to clear the page's OWN median ink
height (`text_scale`), scaled by `cell_scale`, default 3.0.

| cell_scale | figure page, no tables | real 13x4 grid |
|---|---|---|
| 1.0 | 73 tables, 284 cells | 1 table, **52 cells** |
| 2.0 | 21, 57 | 1, **52** |
| **3.0** | **2, 4** | 1, **52** |

**The real grid is completely insensitive across a 3x range while the
false positives collapse 70-fold.** That is a separation, not a tuned
threshold — any value in the range is safe for the true positive, so
the strictest is free. Both halves of the agreed acceptance hold: 52
kept on Infineon p19, near-zero on 2409.18839 p6.

The earlier argument against a size floor was about RECTANGLES (hollow,
`fill < 0.35`) and remains right for those — a real depth-2 box can be
smaller than body text. A cell is the opposite object, a hole that
CONTAINS content, so it is bounded below by the text inside it.
Different object, opposite bound.

And the floor is RELATIVE to the page, so a dpi change cannot silently
retune it.

## 7. Not measured, and load-bearing

- maths-symbol classification (§5)
- script-detection **recall** — precision is 100.0% over 37,759 glyphs,
  but the size-based label also fires on captions and footnotes, so 13.5%
  is a lower bound against an over-inclusive label, not a count of misses
- Reeb signature rotation under a gentle, anti-aliased rasteriser rather
  than nearest-neighbour resampling
- anything downstream of U13's 61.5% cross-font figure
- box detection on a **screened** reproduction. Both polarities assume
  constant-colour regions and continuous strokes; a halftone screen
  turns a tint into a dot lattice and a border into a dotted line, and
  invalidates both. Deferred raster-region detection is the
  prerequisite

## 8. How to work here

Read [`CLAUDE.md`](../CLAUDE.md) first — it carries the conventions and,
more importantly, the review disciplines this project learned the hard
way. In short: measure the premise before writing the plan; state the
population and the split rule beside every number; and mutate before
claiming a guarantee is held.
