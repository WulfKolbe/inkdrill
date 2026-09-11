# HANDOVER — inkdrill

Written 2026-08-21, last revised 2026-09-06. Read `docs/state.md` for
the full record; this is the page you need to resume.

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

**Three modules are off the CLI path on purpose** and recorded with
their reason in `tests/test_reachability.py`'s `OFF_THE_CLI_PATH`:

| module | what it is |
|---|---|
| `skeleton.py` | Zhang-Suen thinning, the junction count and `parts()` (491, 498). Measured across 20 font-blocks and NOT wired in — 26% of glyphs change their junction count with size |
| `rowjoin.py` | a report's table manifest joined to its text layer: `(table, row) -> (page, identifier)` (597). Takes TEXT, not a path |
| `cellrect.py` | a cell's rect from emitted rule positions (602). Numbers in, `Rect` out; no raster |

**Suite:** 1,188 tests, 37 skipped (opt-in corpus/font modules).

## The measured constants — quote the population with the number

| constant | value | population it was measured on |
|---|---|---|
| `NOISE_DISTANCE` | **7** | p95 of 813 rows where the MathPix LaTeX equals the author's AND carries no multi-line/array environment, render-vs-scan |
| `NOISE_COMP_DELTA` | **2** | same control; 1.6% false positives |
| cell floor | 3× median component height | a cell is bigger than the text in it |
| stacked gap bound | 1.5× median component height | without it the count measures line spacing |
| column floor | 2% of table span, **content-decided** | width is a pre-filter only |
| report lattice dpi | **≥200** | below it, scan cells merge with their rules |
| MathPix's render | **250 dpi** | derived from page raster / MediaBox, exactly 250.0 on four of four comparable documents (591). NOT 300, and a crop carries no usable density of its own |
| ring channel floor | **p99 0.890 holes/component** | 400 crops from 93,028 across 856 documents; not one reaches 2.0, against the ~3.4 where hole counts become speckle (591) |
| `\mathcal` junction cut | **4** | derived from the exception (txfonts G) not the gap; holds on CM, LM and XITS, fails on txfonts (495, 497) |

Current findings, 49 of 49 P13 documents: **4,262 rows, ~399 findings
(9.4%), 228 in the component channel.** STALE — see open item 9: 32 of
37 sampled documents have a compare TSV older than their report.pdf,
so this describes a corpus that has since been rebuilt more than once.
Treat it as history until a fresh pass lands.

**Every measured figure since 495 is in `out/NNN.txt`, 63 files, one
per task, each carrying its population, its split rule and the command
that reproduces it.** `git log --diff-filter=A -- out/NNN.txt` dates
one; do not use `git log -1` on it, which returns whatever retrofit
last touched the file.

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
6. ~~The compare probe still selects 5-column pages~~ **CLOSED.**
   `pagedetect.target_columns` reads the count from each document's
   own `report.tex` (the header carrying both `Rendered` and `Scan
   image`), so both eras work. 496 measured 843 documents at 6 and
   492 with no scan column at all. **And 595 then made the whole
   mechanism unnecessary** — see the manifest section below: a run's
   column count cannot identify a table anyway, and 601 §4 showed the
   count is not even stable, reading 6 at 300 dpi where it reads 5 at
   150.
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

9. **The corpus figures are stale against the corpus.** 496 found
   **32 of 37** sampled documents with a `report.compare.tsv` OLDER
   than their `report.pdf`, and the corpus-wide `A_eq_B` rate of
   58.6% therefore describes a previous build. Any number quoted from
   `report.compare.tsv` needs its freshness checked first;
   `tools/comparestale.py` does it.

10. **`warp.py`'s docstring prints the numbers of the defect it
    fixed**, under a heading reading `FIXED`. It has now been read as
    current twice, once as the premise of a whole task. The table is
    marked in place and points at `out/581.txt`, but the general
    lesson is in the failure classes below.

11. **The five-tuple's stability is measured and it is not good.**
    496: at 300 vs 600 dpi, **36.2% of rows** change their hole count
    and **16.6% change their finding class**. It concentrates at the
    weakest boundary — 96% of class changes are noise/clean or
    noise/weak, and the `component` class keeps its verdict on 94.3%.
    The cause is the render, not the resolution: the rendered column
    is drawn with anti-aliasing OFF (2 grey levels against the scan's
    256), and turning it on takes hole instability from 75.0% to
    9.4%. **Not acted on** — it moves every recorded distance in the
    corpus, and whether it moves them toward the scan is unmeasured.

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

- **A number in a comment is not a measurement, and it outlives the
  code it described.** `warp.py`'s docstring carries a table of the
  hatching defect — (436, 180) → (408, 2238), an order of magnitude of
  new holes — under a heading reading `FIXED: transport used to hatch
  solid regions`. The heading is accurate and the table is the
  *before*. It was read as current by two readers, and a task (581 A2)
  was written to explain growth that has not existed since the fix:
  transport now *shrinks* cycles on every page and angle measured.
  A comment describing a defect should not print the defect's numbers
  without printing the fixed ones beside them, and a measurement that
  matters belongs in `out/` with a re-runnable subcommand, not only in
  a docstring. Ask of any number in prose: which commit produced it,
  and has the code it measured changed since?

- **A guessed pattern reports a whole class as absent.** 597's first
  identifier regex was `<bibkey>_[A-Z]{2,4}[0-9a-f]+`, which misses
  `0049_DIA_0001` — an underscore before the digits — and reported all
  six rows of that table as MISSING. Nothing distinguished a reader
  bug from a report finding. The fix is not a better guess: extract
  permissively and let the MANIFEST decide membership, then RETURN the
  leftovers. `Join.unknown` exists for exactly that and is asserted
  on both sides, because a permanently non-empty diagnostic is noise
  nobody reads.
- **A long identifier wraps and disappears.** `0049_EQ0001` fits a
  report's Identifier column; `Geometric_topology_EQ0145` does not and
  breaks after the underscore. `pdftotext` plain found 0 on such a
  page, `-layout` found 0 — it preserves the visual row, so the halves
  are separated by the rest of the line — and `-raw` found 14. Without
  the un-wrap, **6,485 of 6,717 rows read as missing**, and did.
- **Reading order is not row order.** Plain `pdftotext` returned
  0049's image rows as 1, 3, 4, 5, 2: the right SET in the wrong
  SEQUENCE, which mispairs every row while the counts look perfect.
  Take the sequence from the manifest, never from the page.
- **A raw byte scan cannot tell a stripped attachment from a
  compressed one.** 580's first probe reported ghostscript stripping
  an embedded file in the same row where `pdfdetach` said the file was
  still there. Three of seven passes were false strips, and the
  conclusion "write the channel after the last PDF pass" would have
  been drawn from a reader artefact. Extract and compare the BYTES.
- **An incidental refusal stops working when the numbers line up.**
  `cell_rect` refused a page-break row because its two y values came
  from different pages and so were not ordered — the ordering guard
  caught it, not the page-break flag. A row breaking near the top of a
  page would have passed. Refuse by name (602's G7), then the refusal
  survives the coincidence ending.
- **The header and the row are built in two places.** Reordering
  `compare`'s header list alone, leaving the row-building untouched,
  passed the whole suite while every label pointed at another
  column's data. Assert position AND name together.
- **A tolerance asserted as an equality fails honestly.** 602's first
  test asserted the emitted y edges EQUAL to the lattice's; the
  measurement said 0 or -1. Pin the exact part exactly, the tolerant
  part to its measured tolerance, and the SIGN separately — three
  claims of different strength rather than one standing in for all.
- **A number in a comment outlives the code it described.** See open
  item 10.
- **`pkill -f` matches the shell running it.** It killed this session
  twice (exit 144), orphaning children both times. Collect PIDs with
  `pgrep`, then `kill` them.
- **Wait on process exit, not on log growth.** 589's analysis ran when
  six logs had stopped growing; one row finished afterwards and the
  published figures were one row short. `while ps -eo args | grep -q
  <pattern>; do sleep N; done` is the form. Launch it ONCE — layering
  a fresh waiter at each progress check left four orphans for one job.

## Chat reports open and close with a Berlin timestamp

    2026-08-27 10:56 (MESZ, +02:00)
       ... the report ...
    2026-08-27 11:14 (MESZ, +02:00)

CONSOLE OUTPUT ONLY. Nothing under `out/` carries a stamp -- files
are dated by git, and stamping them was a misread that cost three
rounds of work and displaced the measurement eleven documents were
waiting on.

The pair gives the duration, which the harness's "Worked for 6m 55s"
line does not, because that does not survive being pasted. The offset
follows daylight saving and the abbreviation follows it too: MEZ at
+01:00 from late October to late March, MESZ at +02:00 otherwise.

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
now **six: absent, clean, noise, weak, stable, component**. That tuple
is the published legend of a website. Adding a class is allowed and
breaks the deploy loudly; it must not be added silently.

`absent` was added by 238 and this page said "exactly five" until
2026-09-06 — a stale count in the one place that documents a
published contract. If you add a seventh, change this line in the
same commit as `FLAGS`, or the next reader inherits the same defect.

**`absent` before `clean` is the whole point of it.** A row with no
ink on either side scores distance 0 and component delta 0 —
arithmetically a perfect match, from a comparison that did not
happen. Reading it as `clean` reports an absence as the best possible
result.

Key presence over key value is the distinction worth keeping: a
genuinely hole-free page and a renamed field are the same number and
different keys, and only the second is a defect.

## The row manifest — the interface being built with pdfdrill

A live piece of work, spread over out/590, 595, 597, 598, 601, 602,
606, 608, 610, 624, 626. The state on 2026-09-06:

**WHY.** `inkmeasure` had to infer which table a lattice run belonged
to, and could not: 595 measured a run holding TWO tables (0049's
equations and formulas are both 5 columns and contiguous) and a table
spanning TWO runs. 608 of 717 documents have two tables sharing a
column count, so an ordinal has nothing to fall back on.

**THE JOIN, which needs nothing new.** `rowjoin.join(manifest, pages)`
takes `report.tables.json` — 717 documents already have one — and the
identifiers in `report.pdf`'s text layer, and returns every row's
page. 6,717 of 6,717 rows on a 300-page report, 34 of 34 on a 4-page
one, zero missing. Reading the TEXT LAYER is not a G6 violation: G6
forbids reading text off a RASTER.

**THE RECT SPEC** (601, 602, 610). Per TABLE `column_rules_bp`
(ncols+1, ascending, once); per ROW `page`, `rule_above_bp`,
`rule_below_bp`; per document `page_height_bp` and `rule_width_bp`.

| decided | because |
|---|---|
| **centrelines**, not edges | a derived number must not sit where a measured one belongs, and an edge cannot afterwards be told from a centreline half a rule away. `cell_rect` insets by `rule_width_bp/2` |
| **bp**, not sp or px | `bp = sp / 65536 * 72 / 72.27`. Skipping the 72/72.27 is worth 13 px at 300 dpi and is PROPORTIONAL, so it looks right at the top of a page and drifts down it |
| **rule positions**, not content | the lattice cell is the hole BETWEEN rules; emitting rules makes the two sides agree by construction rather than within a tolerance |
| **per row**, not per cell | column boundaries are constant across every page a table occupies, measured to the pixel |
| **no `run`** | 601 §4: the same pages are 2 runs at 150 dpi and 1 at 300. A run is not a property of the document |

**THE RESIDUAL METHOD.** Four signed per-edge deltas in raster px,
reported as median/min/max and fraction within 1 px, **never as a
pass**. A SYSTEMATIC offset is a converter bug and fixable; a
SCATTERED one is a real difference between the detections and a reason
to change the spec. That distinction found a constant -1 in
inkdrill's own consumer over 60 cells, and later a +6.177 bp origin
error and a missing rightmost rule in the emitter.

**TOOLS.** `tools/tablejoin.py` (join over a document),
`tools/manifestcheck.py` (residual against an emitted manifest, pairing
rows to lattice rows BY GEOMETRY because a page's lattice includes the
printed header and the manifest does not), `tools/cellcheck.py` and
`tools/pdfrules.py` (the same against the PDF's own vector content —
an independent source, which is the point), `tools/rulediff.py`
(emitted bp against the PDF's, no raster and no dpi).

**WHAT REMAINS.** The join places a row on a PAGE, not on a lattice
ROW. Within a run the pairing of the k-th identifier to the k-th
lattice row is still positional, and pages are 28 rows deep on
Geometric_topology. A manifest carrying the CELL rect closes it; that
is 598 #4 and #2's remaining half.

## Formula evidence — the marks contract with pdfdrill

Built over out/630–659; the state on 2026-09-11.

**WHAT PDFDRILL PUBLISHES.** `evidence-formula.tex`: one row per
DISTINCT inline formula — id, page, the producer's confidence, the
maths rendered (`\FitMath`), and a crop of the line it first occurs on
(`report-crops/`, scaled copies in `report-crops-b/`). 21 documents,
37,610 rows.

**WHAT INKDRILL ADDS: where the expression sits in its line.**
`tools/formulafind.py` renders the maths, cuts the host line LOSSLESS
from `inspect/pages` and places the rendering along it (blob ink/gap
profiles, a bigint Jaccard scan, a document scale voted by rows with
≥ 6 gaps, a per-row refit). Never measured on a published crop: those
are downsampled, and out/641 measured what that moves. The user's
rule: a residual report is a few rows and never holds downsampled data.

`tools/formularesidual.py` classifies and HOLDS THE MARKING POLICY,
closed in out/658 on 155 eye verdicts over two documents. A rectangle
is drawn only if the host region is a line (≤ `NON_LINE`=3 median line
heights), gaps ≥ 2, margin ≥ `MARK_MARGIN`=0.15, and NOT (gaps ≤
`MARK_GAPS`=7 and edge cuts ≥ `MARK_CUTS`=1): 66.2% of rows marked,
~1.7 wrong marks in 2,240, a mark right 99.89%. The RED flags are
evidence-table detail, not the residual report: every error they found
in those 155 verdicts was inkdrill's own placement. The residual
report is the producer's own low confidence (`LOW_CONFIDENCE`=0.80).

**THE INTERFACE** is `tools/formulamarks.py` — `run <bibkey> --work
DIR` measures, `marks` re-emits — one JSON document on stdout, the
`reportpages` convention. Per row: `mark`, `why_no_mark` (the clause),
`rect` (MathPix px relative to the host region's top-left, i.e. a
pixel of pdfdrill's full-size crop), `rect_frac`, `host_page`,
`region`, `flags`.

| decided | because |
|---|---|
| **pdfdrill's host-line rule**, copied (`first_occurrence_lines` = `inlinectx.load_spans` + `first_occurrences`) | a rectangle is meaningless on another line. The copy and inkdrill's old per-page cursor agree on 37,503 of 37,503 rows both place, but a copy can drift: **pdfdrill must compare `region` with its own host line and draw nothing on a mismatch** |
| **MathPix frame**, not inkdrill page px | pdfdrill's crop is the region resized to its MathPix pixel size |
| **page frames per page and per axis, CropBox-aware** (`page_frames`, `frame_of`) | MathPix's page is the CropBox, `inspect/pages` the MediaBox. 4 of 21 documents are inset (cardona, voloshin, gilmore, kohlhase-omdoc); one width ratio cut the wrong strip there, correlation −0.014 against +0.924 once mapped |
| **staleness: `lines.json` per document, the reading per ROW** — not the bytes of `evidence-formula.tex`, and not a digest over all rows | pdfdrill rewrites that file to insert the marks and to render rows it once could not; a byte hash, or a digest over every row, would refuse every mark for one corrected row. A changed row goes to `not_measured` as "reading changed"; each row carries the `math` it was measured on |

**NOT INKDRILL'S: stale published crops.** pdfdrill's `render_crops`
caches by TITLE (`if f.is_file() and f.stat().st_size > 500: cached`),
so a crop rendered under the old host-line join (before their
`42b92d15`) is never re-rendered. 0902.0431 FO0068 is the right
rectangle cut from page 177 instead of page 4. `tools/cropcheck.py`
finds them by CONTENT — a size check passes FO0068 — and the corpus
count is in out/659.

**THE TOOLS' OWN DEFECTS, fixed and pinned** by
`tests/test_formulatools.py`: `rows()` let a crop-less row steal the
next row's picture and swallow that row, and let `\lowconf{…}` into
ids; the width-only ratio above; rows split on `\\ \hline`, which an
`array` in the maths holds too.

**OPEN, in the four workstreams out/658 separated.** (1) marking: the
placement edges lean left (7 of 12 eye errors); and out/660 found two
limits the books expose. `margin` is blind when an expression fills
more than half its line (no non-overlapping rival fits, so margin =
score), and one document scale cannot serve a book set in two type
sizes (johnston's refit scales peak at 0.50 and 0.60). The user
DECIDED (2026-09-11): publish as measured — 658 stands, the two
limits are known and not acted on. The corpus marks and their work
directories are in `~/inkdrill-marks/` (`index.json`, `README.md` for
pdfdrill, `stale-crops.json`); re-emit with `formulamarks marks
<bibkey> --work <dir>`. (2) MathPix errors:
none found yet. (3) whitespace in large open expressions — with
MathPix, who fixed a de-tokenizer bug inventing invisible brackets;
re-run `tools/fuzzyalign.py` on their next build. (4) matrix-arrangement
repair, for low-confidence equations only.

## Coordination

pdfdrill runs in `~/MX/PDFDRILL` as a peer session, owns the reports
and the corpus, and holds regeneration while a compare is in flight.
Standing contract: it runs this project's probe as its acceptance test
before handing reports over; neither session edits a shared artifact
the other is reading.

**A manifest must name the build it describes.** 606 measured one 14
seconds OLDER than the `report.pdf` beside it, whose rows were not in
that PDF at all. `pdfdrill-rows.json` now carries
`measured_against: {pdf, sha256}` and `manifestcheck` refuses on a
mismatch. This is the same class as `report.compare.source`: an
artifact can be stale against its source AND a result stale against
the artifact, and only the first had a guard.

**Tasks arriving here that are pdfdrill's** (563, 564, 66, 483-485)
are reported as theirs rather than executed. `ListAgents` shows no
pdfdrill session reachable from this one, so relaying is not possible
and saying so is the useful answer.
