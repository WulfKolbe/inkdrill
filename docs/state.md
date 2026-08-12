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

**One weakness in my own row, and the data says it is the whole
story.** The baseline nudge was 128 → 160, 32 levels, where the
rendered-page precedent used ±2.

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
