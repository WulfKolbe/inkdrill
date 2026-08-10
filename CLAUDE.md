# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is for

Scan-event topology for document layout analysis and mathematics
expression recognition. Pure standard library.

**The purpose is to support high-quality scanning by locating errors and
areas other tools have missed.** That is a cross-check, not an OCR
engine: given a page and another tool's opinion of it, say what that tool
did not see. Two consequences run through every unit —

- **The residual is the product.** `coverage.py` reports ink with no
  region; `gold.py` reports four alignment classes rather than one
  agreement rate. A single accuracy number would throw the finding away.
- **Topology before recognition.** Holes, branches and nesting come from
  ink alone, before anything is named. They are what let a wrong answer
  be *detected* rather than confidently returned.

**Orientation, in reading order:** [`docs/state.md`](docs/state.md) for
goals and current state, [`docs/units.md`](docs/units.md) for the
authoritative per-unit record and every measurement, and
[`docs/algorithms.md`](docs/algorithms.md) for the algorithms, the
inner-loop performance analysis and the ranked improvement list.

**Current state.** All fifteen units exist. U14 is its geometry only (no
structure tree) and U8's band tier was deliberately not built; both are
recorded with the measurement that decided them. U9's rasterizer is
**under way**: `type1.py` reads Type 1 font programs (font -> charstring
bytes); the charstring interpreter and scan conversion are not built
yet. See `docs/state.md` §5 for why that chain unblocks maths
classification and the structure tree.

## Commands

```sh
python3 -m unittest discover -s tests -t .   # full suite: 635, of which 23 skip
python3 -m unittest tests.test_sweep          # one module
python3 -m unittest tests.test_sweep.T3_2_CycleRank.test_ring_has_one_hole
INKDRILL_CORPUS=~/pdfdrill-library python3 -m unittest tests.test_pngio_corpus
INKDRILL_TYPE1=/usr/share/texmf-dist/fonts/type1 python3 -m unittest tests.test_type1_corpus
INKDRILL_CORPUS=~/pdfdrill-library python3 -m unittest tests.test_source_truth_corpus
```

The last two are opt-in: the default suite is hermetic and the corpus tests
skip unless `INKDRILL_CORPUS` names a directory of rendered pages, or
`INKDRILL_TYPE1` a directory of `.pfb` fonts.

`-t .` is required: it sets the top-level directory to the repo root so the
`inkdrill` package is importable from `tests/`.

Developed and tested on Python 3.14. The code itself requires nothing newer
than 3.7 syntax — `from __future__ import annotations`, the newest feature in
use, is itself a 3.7 import — so don't treat 3.14 as a hard floor if your
environment has an older interpreter; it hasn't been an issue in practice
because 3.14 is simply what this project runs on day to day. The constraint
that actually binds is standard library only: no numpy, no GPU, no
third-party test runner, no build step, no installer. Do not add a
dependency without saying so explicitly — stdlib-only is a constraint of the
target compute environment, not a preference.

## The plan document is the source of truth

`docs/units.md` holds the implementation plan, the conventions locked in U1–U3,
measured performance numbers, and a numbered list of assumptions that remain
unverified. Read it before designing anything. Two of its rules govern how work
is reported here:

- **A unit is never "done".** It is "tests T-n.m passed on `<date>`". Section 3
  of `units.md` lists what has actually run. Update it with measured results,
  never with assertions.
- **Section 4 lists the assumptions.** Seven are now struck through with
  the measurement that closed them and three were *refuted*, changing the
  design. If your work bears on one, say which number, and move it only
  when a test proves it.

**Every measured figure is re-runnable.** `tools/premise/measure.py`
carries one subcommand per claim — `neutrality colour throughput skew
premise contraction rotation moments nesting banding stitchcost schedcost
fonts outlines boxes border white charstrings rasterisers residuals
missed convexity classify`. If you quote a
number, quote
the subcommand that produces it. If a measurement decides whether to
build something, the harness must be committed *before* the decision is
acted on — that rule exists because it was broken twice.

## Measure the premise before writing the plan

The standing rule, and the one that has paid off most. Before planning a
unit, measure the single claim its design rests on. It has repeatedly
changed what got built:

- U8's band tier was **not built** — decode is 85–95% of per-page work, so
  parallelising the sweep ceilings at 1.17×.
- U13 does **not** escalate beyond 1-NN — the confusion matrix said so.
- U14's structure tree was **not built** — it needs symbol identity, which
  has no measurement behind it.
- U5's contract gained "integer accumulation" because that is *why* axis
  invariance is exact rather than approximate.

A premise check that changes nothing is cheap. One that changes the plan
saves a unit.

## Architecture

A dependency chain of numbered units, each a single module with a contract
written as a docstring *before* the implementation. Every module states
guarantees `G1`–`G7` at the top of that docstring; the tests exist to hold those
specific numbered guarantees, so a test named for `G4` is not incidental.

Built (U0–U14), all independent of each other except `reeb`/`aggregate`/`nest`/`band` → `sweep` → `raster` and
`pngio.load_mask` → `raster.binarize`:

- **`inkdrill/pngio.py`** — ghostscript `png16m` ingest. `read_png` → `PngImage`,
  `load_mask`. Reads only what that one device writes; anything else raises.
- **`inkdrill/space.py`** — affine algebra. `Affine`, `Decomposition`,
  `SpaceGraph`, `angle_deg_ccw`, `angle_deg_screen`.
- **`inkdrill/raster.py`** — `InkMask`, `Run`, `Rect`, `binarize`, `iter_runs`.
- **`inkdrill/sweep.py`** — `sweep()` → `SweepResult` with `nodes`,
  `components`, `events`.
- **`inkdrill/reeb.py`** — Reeb contraction. `contract`, `orient`,
  `signature`, `signature_of`. A `ReebNode` is an arc; `signature()` is a
  stable partition, **not** a classifier, and is not rotation invariant.
- **`inkdrill/aggregate.py`** — moment aggregates. `Moments`,
  `moments_of_mask`, `moments_per_component`. Raw sums are exact
  integers; that is what makes axis invariance exact. Moments add.
- **`inkdrill/nest.py`** — holes and the containment forest. `nest()` →
  `Nesting`. Computes holes independently of `sweep`, so the two check
  each other. `hole_of` and `ink_in_hole` are deliberately distinct.
- **`inkdrill/band.py`** — band splitting and seam stitching. `split`,
  `sweep_bands`, `stitch`, `sweep_banded`. Output is indistinguishable
  from one sweep at any K. Band arrival order must never matter.
- **`inkdrill/sched.py`** — deterministic priority scheduler. `Task`,
  `run`, `RunReport`. Same answer at any worker count; `workers=1` uses
  no pool. Task key is `(page, axis)` — there is no band tier, and that
  is a measured decision, not an omission.
- **`inkdrill/font.py`** — font inventory and glyph-weighted coverage.
  `inventory`, `resolve`, `usability`, `coverage`. Coverage is
  glyph-weighted on purpose; per-document it reads ~17% and per-glyph
  ~95%.
- **`inkdrill/type1.py`** — Type 1 font programs. `load`, `parse`,
  `decrypt`, `encrypt`, `Type1Font`. Reads from a FILE, never searches
  for one, and knows nothing about PDF — `measure.py outlines` showed
  94.61% of maths glyph mass resolves to a `.pfb` in the TeX tree,
  including everything a producer embedded as Type 1C. `first_ops()`
  reports four classes, not a pass rate; see units.md for why that
  distinction was load-bearing twice.
- **`inkdrill/charstring.py`** — run a Type 1 charstring, get closed
  contours. `run`, `outline`, `Glyph`, `Segment`. Sized by
  `measure.py charstrings`; `seac` and `callothersubr` are built because
  the alternative is a plausible wrong glyph. 119,800 real glyphs run
  with 0 errors and 0 unclosed contours. Scan conversion is NOT here.
- **`inkdrill/scan.py`** — contours to an `InkMask`. `flatten`,
  `rasterize`, `render`. Non-zero winding (Type 1's rule), centre
  sampling per `raster`'s pixel convention, one y flip. **Completes
  U9's rasterizer.** Its oracle is that `charstring`'s contour count
  equals `sweep`'s components + holes — two computations sharing no
  code.
- **`inkdrill/relate.py`** — candidate edges for a symbol relation
  graph. `candidates`, `blocked`, `Symbol`, `partition`. Line-of-sight,
  chosen by measurement
  on this corpus rather than on the published benchmark: 99.95% recall
  at 0.96 edges/node against 6NN's 99.83% at 3.29. Produces candidates
  and labels none of them. An UNRESOLVED symbol keeps its geometry and
  its edges; `Symbol.label` raises rather than yielding a sentinel two
  unidentified glyphs would compare equal on.
- **`inkdrill/gold.py`** — pdfminer alignment. `page_transform`, `match`,
  `to_coco`. The four residual classes are the product, not the
  leftovers: only 66.9% of real assignments are 1:1. Matches on component
  centres, because pdfminer gives the advance box.
- **`inkdrill/coverage.py`** — cross-check another tool's regions against
  real ink. `check()` → `CoverageReport`. Uses CONTAINMENT, the opposite
  of `gold.py`'s centres, because a blob crossing a region edge is the
  finding. Read the per-page spread, never the aggregate.
- **`inkdrill/domains.py`** — conceptual-space dimensions. `describe`,
  `convexity`, `mutual_information`, `joint_mutual_information`. Ships the
  Gärdenfors design test, so a dimension is added by measuring it. Compare
  `efficiency`, not raw `nmi` — the latter is capped by cardinality.
- **`inkdrill/classify.py`** — 1-NN over separable channels. `normalise`,
  `Classifier`, `confusion`. The bitmap channel alone reaches 99.1%; the
  confusion matrix says do not escalate. The signature is a verifier
  (`agrees`), not a discriminator.
- **`inkdrill/mathstruct.py`** — rows, reference lines, script detection,
  component grouping. `rows`, `reference_lines`, `detect_scripts`,
  `group`. Rows seed tallest-first; grouping needs stacking, not width.
  Big operators, fences and the structure tree are NOT built.

Planned U4–U14 (`reeb`, `aggregate`, `nest`, `band`, `sched`, `font`, `gold`,
`coverage`, `domains`, `classify`, `mathstruct`) are specified in `units.md`
§2 with their contracts and tests. Dependencies run strictly downward: **no
unit may be started before its dependencies' tests pass.**

### The run adjacency graph is the central object

`sweep` builds a graph whose nodes are maximal runs and whose edges join runs on
consecutive scan lines that touch under the active connectivity. Components,
hole counts, the join tree, the Reeb graph and the branch skeleton are all
derived from it, and every edge is enumerated exactly once per sweep.

A prior code base enumerated those edges, consumed them in `union()`, discarded
them, then rebuilt the same graph to count holes. This one keeps them. Retaining
the full graph was measured at +13% over `Capture.NONE` — that question is
settled, do not re-open it on speculation.

### Conventions that later units inherit

These are decided and under test. Inherit them rather than re-litigating.

- **The core stores no angles.** Directions are unit vectors. `angle_deg_ccw`
  (y-up) and `angle_deg_screen` (y-down) are the only producers, each naming its
  convention. This is a direct response to sign drift between two functions in
  the previous code base. Do not introduce a stored angle.
- **Matrix order** is PDF/PostScript row-vector `[a b c d e f]`; `m1.then(m2)`
  is `cm` concatenation order, and row 1 `(a, b)` is the x-basis image.
- **Mask encoding is `0xFF` ink / `0x00` background, package-wide** — chosen so
  `bytes.translate` binarizes and `bytes.find` extracts runs at C speed without
  numpy (105 Mpx/s). Convert at the boundary; accept and produce nothing else.
- **Pixel (i,j) covers `[i,i+1) × [j,j+1)`, centre `(i+.5, j+.5)`.**
- **Runs are scan-space `(line, lo, hi)`, inclusive.** `Run.image_span(axis)` is
  the only sanctioned converter — never index the tuple positionally to get an
  image coordinate.
- **Connectivity is paired**: 8 for foreground, 4 for background, always.
- **`keep_regions` / `clear_regions` are two polarities of one parameter**, not
  two code paths.
- **A component's identity is `Component.root`. `nodes[0]` is not it.**
  `moments_per_component` keys by `root`; `SweepResult.components` is
  *ordered* by `nodes[0]`. On one real page 1293 of 1310 components had
  `root != nodes[0]`, so a caller keying its own lookup by `nodes[0]` hit
  17 of 1310 and silently took the default for the rest — reporting zero
  holes everywhere and finding no boxes on a page with fourteen. Nothing
  raises: both are valid ints and `dict.get` has a default. Pinned by
  `T5_7_ComponentIdentityIsRootNotFirstNode`.

### Testing style

The suite leans on independent oracles rather than recorded output: `sweep`
components are checked against a separate flood fill over 120 random masks; row
and col sweeps must agree; the cycle-rank identity `cycles == E − V + C` is
checked per component. When adding a unit, prefer a second independent
computation over a golden file — `units.md` names the intended oracle for each
planned unit.

Axis invariance (row sweep == col sweep) is the foundation of later claims and
is asserted at every level. Any change that breaks it is a real bug, not a test
that needs relaxing.

### The corpus is arXiv. Say so, and check the counterexample

Every figure in this project was measured on LaTeX-produced papers
until the Infineon handbook (Word 2016) was added, and it inverted three
conclusions at once: U9's TeX-tree route reaches **0 of 19** fonts,
`images_layer` is **51.2%** one repeated header logo, and both layout
detectors score 0/28 because a pasted raster has neither a drawn frame
nor a gutter. Before generalising a layout or font result, run it on
`Infineon-motorcontrol_handbook-...` — it is kept for that purpose.

### State the population and the split rule beside every measured number

Five findings so far were the same shape: the instrument was right and
the conclusion was wider than what it could see. Four were about
POPULATION — U0's colour fraction (sampled self-contained rows only),
U9's font coverage (per-document vs per-glyph), U10's residual rates
(three pages, one figure-heavy), U12's MI ranking (capped by
cardinality). One was about PROTOCOL — U13's 97.1% extents accuracy,
which was 43.8% the moment train and test stopped sharing documents.

None is caught by a mutation sweep, because the code is correct in every
case. What catches them is asking, before quoting any number:

- **What population is this measured over, and what is it claimed of?**
- **How were the samples divided, and does the division leak?**
- **What is the maximum this number could be?** (U12's ceiling.)

A measured figure without its population and its split rule is not a
result. Quote both in the same sentence, and make the split rule an
argument to the harness rather than a constant inside it — if it changes
the answer, a reader must be able to change it.

**Filters are decisions too, and they hide in the same way.** U13's
`if count >= 12` silently excluded every maths symbol, so a conclusion
about "classification" was really about body text. The split rule and the
class filter were three lines apart, both written once and correctly, and
both stopped being read as choices. Print what a filter kept and what it
dropped, beside the result.

### Mutate before you claim a guarantee is held

Five times now a guarantee has been stated in a docstring, argued for in
prose, and asserted by nothing — U4's rotation invariance, U7's per-node
re-sort, U8's dispatch order, and U9's parser fallback branch. Each was
found by an audit, not by the suite, and each looked covered because a
*neighbouring* test appeared to exercise it.

They are all findable the same way, in minutes:

- **A tolerance is a guarantee too.** `delta=0.15` with a docstring
  naming a 0.143 pt error admits it. Compute the wrong value in the
  test, assert it falls outside the *same shared constant*, and the
  tolerance can no longer be widened past the mistake it exists for.
- **Delete the line the guarantee rests on.** If the suite still passes,
  the guarantee is prose.
- **Force every non-trivial branch to a constant.** `if True` / `if False`
  on each side. A branch that no test reaches will first execute on real
  data, unverified, and its failure mode is usually a silently wrong
  value rather than an exception.

Do this per unit, before recording a status line — not at the final review,
which is where these have been surfacing.

**A branch that survives in BOTH directions means the oracle is blind,
not that the branch is dead.** `closepath` could be deleted or inverted
with nothing failing, because every test watched how a charstring opened
and none watched the geometry that came out. Assert the output exactly
somewhere, or a whole class of behaviour is untested no matter how many
tests exist.

**A survivor is a lead, not a finding.** Confirm each by hand before
writing a test. There are three ways a mutant survives without indicating a
gap:

- **Incompetent** — the mutation breaks the module at import, so the suite
  never reaches an assertion. Filter these mechanically with an import
  canary before running the tests.
- **Equivalent** — the mutation is provably behaviour-preserving, so it is
  *unkillable* and no test can or should be written. `if not values:`
  guarding a fallthrough that returns the same value is one; a guard
  already implied by a later one is another. These cannot be filtered
  mechanically and must be reasoned about one at a time.
- **Misapplied** — the patch hit a different occurrence than intended.

Over `font.py` the sweep reported eight survivors: six real, two
misfiring — one of which fails 18 tests when mutated correctly. Over
`domains.py` it reported three, and all three were equivalent mutants.
Expect roughly half of any batch to be noise.

**Run the sweep with `PYTHONDONTWRITEBYTECODE=1`, or clear `__pycache__`
after it.** The sweep rewrites a module many times per second, and Python
invalidates cached bytecode on `(mtime, size)` — a mutation that happens to
preserve the file size can leave a stale `.pyc` behind. That produced a
test failing with `'box' != 'box'`, which costs real time to diagnose and
looks like a logic bug in whatever you touched last.

**Reconcile scope if two sweeps disagree on the count.** A regex over
`if …:` lines misses ternaries, `while`, and comprehension conditions; two
sweeps that cover different constructs will report different totals for the
same file and neither is wrong.

## Where the deliberate gaps are

Three things are missing on purpose, each with the measurement that
decided it. Do not "fix" them without re-taking that measurement.

- **Maths templates and maths classification.** U9's rasterizer is now
  complete (`type1` -> `charstring` -> `scan`), so the templates are
  reachable and the next step is to measure classification on them.
  Note the route: outlines come from the TeX tree, NOT from the PDF,
  and it reaches **0 of 19** fonts on a Word document — see the
  Infineon counterexample.
- **U14's structure tree, fences, big operators, LaTeX.** All need symbol
  identity for `∑ ∫ ( [`, and U13's measured population contained no
  maths symbols at all.
- **U8's band tier and shared memory.** Measured into the ground;
  conditional on decode continuing to dominate.

One known performance defect is recorded rather than fixed: **`nest()`
is 15.0x slower than the two sweeps it is equivalent to** (19.70 s vs
1.31 s on a 3400x4400 page, byte-identical output — 3,390 ink regions,
1,190 holes). It flood-fills per pixel and accumulates extents in a
per-pixel Python loop, the same run-discipline violation as
`classify.normalise`. `measure.py boxes` uses the two-sweep form
directly, so the cost is avoided where it was measured.

One known correctness defect is pinned rather than fixed: `group()` absorbs a display
big operator's limits into the operator. The obvious remedy does not
reach it, and the real fix is symbol identity again.

## CodeGraph

`.codegraph/` is a machine-local tree-sitter index, gitignored. `.cursor/rules/codegraph.mdc`
carries the tool-selection guide; it duplicates the global `~/.claude/CLAUDE.md`
section, so update both or neither.
