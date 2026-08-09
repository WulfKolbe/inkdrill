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
| U9 | `type1` | outlines: **font -> charstring bytes**; no interpreter yet |
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

**The U9 rasterizer is the unblocking move.** It also inherits the
self-validating property the design was built for: a query matched to a
template must agree on hole count and Reeb signature, so a mismatch is a
*detected* error rather than a confident wrong answer — which matters far
more for `∑` vs `Σ` than for `e` vs `c`.

One design note for that measurement: font-rendered templates against
page-rendered queries is a *cross-rasteriser* comparison, so expect
U13's cross-font row (61.5% bitmap-only, 86.3% all channels), not its
within-document row.

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
