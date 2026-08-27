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
6. **The compare probe still selects 5-column pages; the reports are
   now 6.** pdfdrill's task 099 added a Confidence column, so a
   display-equation table with crops is **6 columns with crops, 5
   without** (inline formulas 5, tables 4, diagrams 4, each section
   preceded by `\clearpage` so no page mixes two). The fix is
   `reportcompare.py`'s probe; the fix is MINE and the change
   ORIGINATES in 099, which matters because **it will move row counts
   corpus-wide.** If someone later asks why the counts moved, the
   answer is a column that was added, not a change in what the ink
   found. Write that beside the new numbers when they land.
7. **`0902.0431`'s render cache has a 16-page hole** (113–115,
   118–130), so `overrun.py` withholds identifiers for its 320
   flagged rows and three of the four cases pdfdrill confirmed by eye
   are unverifiable. Every one of those pages carries maths objects —
   the gap is the cache, not the document. Sixteen ghostscript calls.
8. **`out/102.txt` is measured against the render cache as it stood
   at 14:11 on 2026-08-22.** pdfdrill's tail-split fix (their open
   item 9) changes crop rectangles corpus-wide; when it lands those
   numbers describe a corpus that no longer exists and must be
   re-measured. There is no mtime to compare here — **an artifact can
   be stale against its source and a RESULT can be stale against the
   artifact it was measured on**, and only the first has a guard. It
   is held by a message between sessions, which is why it is written
   down.

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
- **Warn or refuse is decided by what the failure costs, not by how
  bad it sounds.** The same staleness condition: the producer WARNS
  (the user asked for a `.tex` and got one; refusing a successful
  command over a neighbouring file is the tool overriding the
  instruction) and the consumer REFUSES (a stale input silently
  corrupts a two-hour batch). Same rule, opposite output, three times
  in one day — it also settled whether an absent file is named
  (expected for a producer's first run, a real problem for a
  consumer) and whether a message may scroll past.
- **Ask "is there a report to measure", not "is there a file here".**
  `pdf.is_file()` refuses a directory named `report.pdf`;
  `pdf.exists()` calls an old one stale and sends the reader to
  recompile it. The phrasing of the question excluded a case the
  other phrasing admits — accident here, not foresight, and recorded
  as accident because that is the useful part.
- **A fixture must contain the class the rule discriminates against**,
  and its dimensions must come from a measured value.
- **A pooled ratio and a per-unit paired test can point opposite
  ways.** 117: the deficit near a rule was 17.2% against an 11.5%
  null — enrichment — and per row against each row's OWN density it
  inverted, sign test z = -4.88, below its null on 80 rows of 110.
  Sixteen rows carrying 10% of the deficit and 60% of the near count
  is the mechanism. A row with one rule and two missing marks scores
  1.000 by arithmetic, not by evidence. Ask the paired question
  before quoting the pooled one.
- **A ratio whose denominator excludes most of the population is a
  subgroup, not a rate.** 316 of 117's 426 rows had no rule to be
  near. Counting and naming them is what made the 17.2% readable at
  all; dropping them would have quoted a quarter of the population as
  the corpus.
- **Measure the null before quoting the rate.** "17% of missing
  components are near a rule" is unreadable without "and 11.5% of all
  components are". Inherited from pdfdrill's variant B, where 1 of 19
  crops contained the notation the hint addressed, so its +196
  measured the cost of an irrelevant hint rather than the hint.
- **An absence reported as a result is always the reassuring one.**
  Three instances in one day, each a tempting collapse of two states
  that look alike from one end: a table region found with NO SURVIVING
  CELL is not "no table on this page" (it was an empty dict past a
  `is None` guard, and it raised `ValueError` four frames down); a
  ZERO-VS-ZERO comparison is not "clean" (distance 0, the best
  possible score, from a comparison that did not happen); a file
  measured BEFORE a provenance stamp existed is not "verified
  current". Every time, the collapsed reading is the flattering one,
  and every time it is invisible from inside the artifact. Name the
  two states separately even when one of them is rare.
- **Guard the derived side, not only the source side.**
  `check_fresh` refuses a `report.pdf` older than its `report.tex` --
  the source direction -- and nothing compared the DERIVED
  `report.compare.tsv` against the pdf it came from. 100 of 352 were
  stale, carrying `report_page` indices into a build that no longer
  existed, all of them in range and plausible. An asymmetric guard
  looks complete from either end on its own; ask which direction is
  unwatched.
- **Identity claims need an identity, and position does not supply
  one.** Per-component correspondence between a LaTeX render and a
  scan of the same expression is not recoverable by position:
  residual p5 -34, p50 -6, p95 +16, agreeing on 61 of 426 rows, even
  with a threshold-free overlap test. Different typeface, different
  scale, and ink decomposes differently — a scanned `i` merges its
  dot into its stem. Count claims survive this; identity claims do
  not, so say which one you are making.

## Every report opens with a UTC timestamp and a commit hash

`tools/reportstamp.py`, one line, first line, before any prose:

    2026-08-27T08:56:07Z  commit ccc61c5  +dirty

The commit is the one that PRODUCED the numbers -- `HEAD` when the
report was written -- not the commit that later contains the file.
Those differ by one, and the difference is the difference between
"which code measured this" and "which code shipped this"; only the
first is re-runnable. `+dirty` when the tree had uncommitted changes,
because then the numbers came from code in no commit at all.

Existing reports were retrofitted from `git log` with the commit that
ADDED each, and say so in the line rather than borrowing today's date.

The reason is not tidiness. A report arriving after a newer one is
otherwise indistinguishable from a current one, and that happened
twice in one session: a three-builds-stale figure quoted for three
exchanges, and a peer's audit that attributed a displacement to the
wrong defect because the artifact it read had been superseded.

## Two sessions consume this project's output format

Recorded here because neither side wrote it down and each assumed the
other held it. Nothing is frozen — a QC instrument that cannot change
its classes is worse than one that breaks consumers who fail loudly —
but a rename is now a DELIBERATE act with a known blast radius.

| consumer | reads | fails how |
|---|---|---|
| pdfdrill-7b's refine metric | `ink.components`, `ink.holes` from `emit`'s lines.json | asserts on key PRESENCE, not value: `"holes": 0` is a hole-free page, a missing key raises `InkUnavailable` naming the field |
| pdfdrill.github.io deploy gate | `rows` and each row's `flag` from `report.ink.json` | a sixth flag value fails the deploy by name, telling whoever sees it the legend needs updating in the same commit |

The flag vocabulary they depend on is `tools/findings.py`'s `FLAGS`,
exactly five: **component, weak, stable, noise, clean**. That tuple
is the published legend of a website. Adding a class is allowed and
breaks the deploy loudly; it must not be added silently.

Key presence over key value is the distinction worth keeping: a
genuinely hole-free page and a renamed field are the same number and
different keys, and only the second is a defect.

## Coordination

pdfdrill runs in `~/MX/PDFDRILL` as a peer session, owns the reports
and the corpus, and holds regeneration while a compare is in flight.
Standing contract: it runs this project's probe as its acceptance test
before handing reports over; neither session edits a shared artifact
the other is reading.
