# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```sh
python3 -m unittest discover -s tests -t .   # full suite: 484, of which 4 skip
python3 -m unittest tests.test_sweep          # one module
python3 -m unittest tests.test_sweep.T3_2_CycleRank.test_ring_has_one_hole
INKDRILL_CORPUS=~/pdfdrill-library python3 -m unittest tests.test_pngio_corpus
```

The last one is opt-in: the default suite is hermetic and the corpus tests skip
unless `INKDRILL_CORPUS` names a directory of rendered pages.

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
- **Section 4 lists 10 unverified assumptions.** If your work bears on one,
  say which number, and move it to Section 3 only when a test proves it.

## Architecture

A dependency chain of numbered units, each a single module with a contract
written as a docstring *before* the implementation. Every module states
guarantees `G1`–`G7` at the top of that docstring; the tests exist to hold those
specific numbered guarantees, so a test named for `G4` is not incidental.

Built (U0–U13), all independent of each other except `reeb`/`aggregate`/`nest`/`band` → `sweep` → `raster` and
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
  `inventory`, `resolve`, `usability`, `coverage`. **Inventory half of U9
  only** — rasterization is not built. Coverage is glyph-weighted on
  purpose; per-document it reads ~17% and per-glyph ~95%.
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

### Mutate before you claim a guarantee is held

Five times now a guarantee has been stated in a docstring, argued for in
prose, and asserted by nothing — U4's rotation invariance, U7's per-node
re-sort, U8's dispatch order, and U9's parser fallback branch. Each was
found by an audit, not by the suite, and each looked covered because a
*neighbouring* test appeared to exercise it.

They are all findable the same way, in minutes:

- **Delete the line the guarantee rests on.** If the suite still passes,
  the guarantee is prose.
- **Force every non-trivial branch to a constant.** `if True` / `if False`
  on each side. A branch that no test reaches will first execute on real
  data, unverified, and its failure mode is usually a silently wrong
  value rather than an exception.

Do this per unit, before recording a status line — not at the final review,
which is where these have been surfacing.

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

## CodeGraph

`.codegraph/` is a machine-local tree-sitter index, gitignored. `.cursor/rules/codegraph.mdc`
carries the tool-selection guide; it duplicates the global `~/.claude/CLAUDE.md`
section, so update both or neither.
