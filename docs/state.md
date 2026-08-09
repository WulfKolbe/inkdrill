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
| U9 | `font` | **inventory half only** — no rasterizer |
| U10 | `gold` | complete |
| U11 | `coverage` | complete |
| U12 | `domains` | complete |
| U13 | `classify` | complete |
| U14 | `mathstruct` | **geometry only** — no structure tree |

Two units are deliberately partial and one tier was deliberately dropped.
All three are recorded with the measurement that decided them.

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

## 7. Not measured, and load-bearing

- maths-symbol classification (§5)
- script-detection **recall** — precision is 100.0% over 37,759 glyphs,
  but the size-based label also fires on captions and footnotes, so 13.5%
  is a lower bound against an over-inclusive label, not a count of misses
- Reeb signature rotation under a gentle, anti-aliased rasteriser rather
  than nearest-neighbour resampling
- anything downstream of U13's 61.5% cross-font figure

## 8. How to work here

Read [`CLAUDE.md`](../CLAUDE.md) first — it carries the conventions and,
more importantly, the review disciplines this project learned the hard
way. In short: measure the premise before writing the plan; state the
population and the split rule beside every number; and mutate before
claiming a guarantee is held.
