# inkdrill

Scan-event topology for document layout analysis and mathematics
expression recognition. Pure standard library — no numpy, no GPU, no
build step, no installer.

    python3 -m unittest discover -s tests -t .        # 740 tests, 23 skip

The purpose is to **support high-quality scanning by locating errors and
areas other tools have missed** — a cross-check, not an OCR engine.
Given a page and another tool's opinion of it, say what that tool did
not see. Two consequences run through every module: the *residual* is
the product, and topology comes *before* recognition.

## Where things are

| | |
|---|---|
| goals, current state, what is next | [`docs/state.md`](docs/state.md) |
| per-unit record and every measured figure | [`docs/units.md`](docs/units.md) |
| algorithms, inner loops, ranked improvements | [`docs/algorithms.md`](docs/algorithms.md) |
| conventions and review disciplines | [`CLAUDE.md`](CLAUDE.md) |

Every measured number is re-runnable from `tools/premise/measure.py`,
which carries one subcommand per claim.

## Modules

| unit | module | what it does |
|---|---|---|
| U0 | [`pngio.py`](inkdrill/pngio.py) | ghostscript `png16m` ingest |
| U1 | [`space.py`](inkdrill/space.py) | affine algebra; the core stores no angles |
| U2 | [`raster.py`](inkdrill/raster.py) | `InkMask`, runs, `binarize` |
| U3 | [`sweep.py`](inkdrill/sweep.py) | the run adjacency graph — the central object |
| U4 | [`reeb.py`](inkdrill/reeb.py) | Reeb contraction and signature |
| U5 | [`aggregate.py`](inkdrill/aggregate.py) | exact integer moments |
| U6 | [`nest.py`](inkdrill/nest.py) | **holes and the containment forest** |
| U7 | [`band.py`](inkdrill/band.py) | band splitting and seam stitching |
| U8 | [`sched.py`](inkdrill/sched.py) | deterministic scheduler |
| U9 | [`font.py`](inkdrill/font.py) | font inventory, glyph-weighted coverage |
| U9 | [`type1.py`](inkdrill/type1.py) | Type 1 font programs → charstrings |
| U9 | [`charstring.py`](inkdrill/charstring.py) | charstrings → closed contours |
| U9 | [`scan.py`](inkdrill/scan.py) | contours → `InkMask` |
| U10 | [`gold.py`](inkdrill/gold.py) | pdfminer alignment, four residual classes |
| U11 | [`coverage.py`](inkdrill/coverage.py) | cross-check another tool's regions |
| U12 | [`domains.py`](inkdrill/domains.py) | conceptual-space dimensions |
| U13 | [`classify.py`](inkdrill/classify.py) | 1-NN over separable channels |
| U14 | [`mathstruct.py`](inkdrill/mathstruct.py) | rows, reference lines, scripts |
| M2 | [`relate.py`](inkdrill/relate.py) | line-of-sight candidate edges |
| M3 | [`rewrite.py`](inkdrill/rewrite.py) | relation graph → symbol layout tree |
| T1 | [`emit.py`](inkdrill/emit.py) | findings as a MathPix-shaped `lines.json` |

## State

U9's rasterizer is **complete**: `type1 → charstring → scan` gets from a
font file to a glyph bitmap, and maths classification has been measured
on it — 96.45% correct at 0.15% silently wrong on the corpus-median
53-candidate set, against 88.10% / 0.31% open-set over 647 classes.

Deliberate gaps, each with the measurement that decided it: U8's band
tier (decode dominates, so parallelising ceilings at 1.17×), U14's
structure tree, and rules inside a *connected* table frame — 72.1% of
table objects, and the largest open item.

`docs/state.md` is the authoritative version of this paragraph.

## Reading the source

Every module opens with its contract as a docstring, written *before*
the implementation, stating numbered guarantees `G1`–`G8`. The tests
exist to hold those specific guarantees, so a test named for `G4` is not
incidental. Start with the contract, not the code.
