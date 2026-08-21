# HANDOVER — inkdrill

Written 2026-08-21. Read `docs/state.md` for the full record; this is
the page you need to resume.

## What this is now

Scan-event topology, stdlib only. Beyond the fifteen units, the working
surface is a **findings channel**: given a formula report (pdfdrill's
`report.pdf`) it compares each equation's *rendered* cell against its
*scan* cell and reports where a conversion and the printed page
disagree. The residual is the product.

**CLI:** `compare`, `topology`, `template`, `locate`, `residual`
(`python3 -m inkdrill <cmd>`). **Harnesses:** `tools/reportcompare.py`,
`mathpixcoverage.py`, `noisefloor.py`, `abdiff.py`, `bookprofile.py`,
`inkfit.py`, `punctprofile.py`, `threeway.py`, gated by
`tools/corpusgate.py`, vocabulary in `tools/findings.py`.

**Suite:** 1,072 tests, 37 skipped (opt-in corpus/font modules).

## The measured constants — quote the population with the number

| constant | value | population it was measured on |
|---|---|---|
| `NOISE_DISTANCE` | **7** | p95 of 813 rows where the MathPix LaTeX equals the author's AND carries no multi-line/array environment, render-vs-scan |
| `NOISE_COMP_DELTA` | **2** | same control; 1.6% false positives |
| cell floor | 3× median component height | a cell is bigger than the text in it |
| stacked gap bound | 1.5× median component height | without it the count measures line spacing |
| column floor | 2% of table span, **content-decided** | width is a pre-filter only |
| report lattice dpi | **≥200** | below it, scan cells merge with their rules |

Current findings, 49 of 49 P13 documents: **4,262 rows, ~399 findings
(9.4%), 228 in the component channel.** Stale by one regeneration —
42 previously-demoted rows now render and belong back in the
measurement; a fresh pass is ~2 hours.

## Open items

1. **`tools/threeway.py` hardcodes a session `/tmp` path** (lines
   51–52). Broken for any other session; give it `reportcompare.py`'s
   `$INKDRILL_WORK` treatment. Until then `scratchpad/p13cmp` (1.4G)
   cannot be deleted. See `out/074.txt`.
2. **`docs/units.md` states 635 tests** (now 1,072) and documents none
   of the five subcommands. See `out/076.txt`.
3. **`docs/state.md` S5 states the retired floor of 6 in the present
   tense.** Correct as history, wrong as a claim; mark it superseded,
   do not delete it.
4. **`1511.08771` is still in `~/pdfdrill-library/P13-arxiv-reports.txt`**
   so every consumer filters it at use. Whether the roster should mean
   the operative corpus is the user's call; neither session edits it
   unilaterally.
5. **`prune()` unused by `emit`**; CFG parser undecided; `group()`
   absorbs an inline limit — all need symbol identity.

## Known failure classes — every one cost real time here

- **A control group is only as good as the rule that built it.** The
  floor of 23 survived a doubled sample, 42 documents and an
  independent render route, and was still wrong: 45% of its
  "content-identical" rows were `\begin{aligned}` blocks that another
  tool's metric could not compare. Strong corroboration, about the
  wrong thing.
- **Measure the noise of the comparison you gate, not a neighbouring
  one.** The floor of 6 came from rasterizer-vs-rasterizer.
- **A row with no rendering is not a finding.** Demoted rows print
  `(not rendered)` — 13 components, 6 holes, whatever the equation was
  — and produced 16% of the component class, including its largest
  value. Detect them from the report **tex**, not a compile counter:
  the counter sees 5 of 51.
- **Correct on the small case, wrong on the large one.** Four
  instrument defects this week, each caught by reading data rather
  than a summary: a `(page,row)` diff key reporting reflow as ink, a
  five-field unpack, an `^!` error counter, a brace-blind regex.
- **A pattern verified on a sample lacking the disambiguating case
  cannot fail.** Anchor on something stable; read the residue bucket.
- **Two subtractions of equal size are not a chain** (93−21=72,
  72−21=51; the two 21s are unrelated).
- **An empty result is a defect, not a silence** — P16; and **an
  unexplained delta is a finding** (a +15% page count was a bug).
- **A fixture must contain the class the rule discriminates against**,
  and its dimensions must come from a measured value.

## Coordination

pdfdrill runs in `~/MX/PDFDRILL` as a peer session, owns the reports
and the corpus, and holds regeneration while a compare is in flight.
Standing contract: it runs this project's probe as its acceptance test
before handing reports over; neither session edits a shared artifact
the other is reading.
