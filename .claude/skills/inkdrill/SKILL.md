---
name: inkdrill
description: Use when working on the inkdrill codebase — building or changing a unit, quoting a measured figure, or reviewing a change. Carries the project's goals, its current state, and the four review disciplines it learned by getting them wrong.
---

# Working on inkdrill

Scan-event topology for document layout analysis and mathematics
expression recognition. Pure standard library — no numpy, no GPU, no
build step, no installer.

**The purpose is to support high-quality scanning by locating errors and
areas other tools have missed.** A cross-check, not an OCR engine.

## Read first

| file | what it holds |
|---|---|
| `docs/state.md` | goals, unit status, what is measured, what is next |
| `docs/units.md` | the authoritative per-unit record; §3 measurements, §4 assumptions |
| `docs/algorithms.md` | algorithms, inner-loop performance, ranked improvements |
| `CLAUDE.md` | conventions and the review disciplines |

## Commands

```sh
python3 -m unittest discover -s tests -t .        # full suite; -t . is required
python3 -m unittest tests.test_sweep              # one module
INKDRILL_CORPUS=~/pdfdrill-library python3 -m unittest tests.test_pngio_corpus
python3 tools/premise/measure.py --corpus <dir> <subcommand>
```

The default suite is hermetic — it builds its own PNGs in memory and reads
nothing outside the repo. Only the env-gated corpus module touches disk.

## The four disciplines

Each of these exists because it was violated and an audit caught it.

### 1. Measure the premise before writing the plan

Before planning a unit, measure the single claim its design rests on. This
has repeatedly changed what got built: U8's band tier was cancelled
(1.17× ceiling), U13 does not escalate beyond 1-NN, U14's structure tree
was not built. A premise check that changes nothing is cheap; one that
changes the plan saves a unit.

### 2. State the population and the split rule beside every number

Five findings shared one shape — the instrument was right and the
conclusion wider than its reach. Four were about **population** (U0's
colour fraction, U9's per-document vs per-glyph, U10's three pages, U12's
cardinality ceiling); one about **protocol** (U13's 97.1% became 43.8%
when train and test stopped sharing documents).

Ask, before quoting anything:

- What population is this measured over, and what is it claimed of?
- How were the samples divided, and does the division leak?
- What is the maximum this number could be?

**Filters are decisions too.** U13's `count >= 12` silently excluded every
maths symbol, so a conclusion about "classification" was really about body
text. Print what a filter kept and dropped. If a split rule changes the
answer, make it a harness argument, not a constant.

### 3. Mutate before claiming a guarantee is held

Six guarantees were stated in a docstring, argued in prose, and asserted
by nothing. Delete the line the guarantee rests on; if the suite passes,
the guarantee is prose. Force each non-trivial branch to `True` and
`False`.

Run with `PYTHONDONTWRITEBYTECODE=1` — a size-preserving mutation can
leave a stale `.pyc` and produce a failure reading `'box' != 'box'`.

**A survivor is a lead, not a finding.** Three ways one survives without
indicating a gap: *incompetent* (breaks at import — filter with a canary),
*equivalent* (provably behaviour-preserving, unkillable, reason about it
individually), *misapplied* (patched the wrong occurrence). Expect about
half of any batch to be noise.

### 4. Record what a measurement refuted

`units.md` §4 struck through seven assumptions and refuted three. When a
measurement contradicts the plan, strike the plan through and put the
number beside it — do not silently overwrite. The superseded figure is
usually more instructive than the correct one.

## Conventions inherited by every unit

- **Contract before implementation** — a module docstring stating the
  contract and numbered guarantees G1–G7, written first.
- **The core stores no angles.** Directions are unit vectors;
  `space.angle_deg_ccw` (y-up) and `angle_deg_screen` (y-down) are the
  only producers, each naming its convention.
- **Mask encoding is `0xFF` ink / `0x00` background, package-wide** — so
  `bytes.translate` binarizes and `bytes.find` extracts runs at C speed.
- **Everything downstream operates on runs, not pixels.** A glyph is
  ~190 px and ~9 runs.
- **Pixel (i,j) covers `[i,i+1) × [j,j+1)`, centre `(i+.5, j+.5)`.**
- **Connectivity is paired**: 8 foreground, 4 background, always.
- **Independent oracles over golden files** — `sweep` against flood fill,
  `nest` against cycle rank, `pngio` against a naive decoder.
- Test classes are `T<unit>_<n>_<Name>`; test names are quoted verbatim in
  the status report.

## Deliberate gaps — do not "fix" without re-measuring

- **U9's rasterizer half** — the highest-value next step. Unblocks maths
  classification, which unblocks U14's structure tree. `docs/state.md` §5.
- **U14's structure tree, fences, big operators, LaTeX** — need symbol
  identity, which has no measurement behind it.
- **U8's band tier and shared memory** — measured into the ground;
  conditional on decode continuing to dominate.
- **`group()` absorbing a display operator's limits** — a known defect,
  pinned by a test. The obvious remedy does not reach it.
