# Test drive — the functions added 2026-09-04..06

Plain commands only. Nothing here asks you to write code, and no
document name is hardcoded — §0 tells you which names your corpus has.

Run from the repo root.

## Set the library path once

```sh
cd ~/inkdrill
export LIB=~/pdfdrill-library
```

If that directory is not there, find it and set `LIB` to it:

```sh
ls -d ~/*library* ~/*drill* 2>/dev/null
```

Every command below passes `--library "$LIB"`, so once this is right
the rest follows.

---

## 0. What does this corpus hold?

```sh
python3 tools/inventory.py --library "$LIB"
```

Prints the library path it used, how many documents have each artefact,
and a few names of each. **Use those names in the commands below** —
they are the only names that will work.

The three counts decide what you can run: §2 needs
`report.tables.json`, §3 needs `pdfdrill-rows.json`, §8 needs
`report-crops`. If a count is 0, skip that section.

---

## 1. Suite — the floor everything else stands on

```sh
python3 -m unittest discover -s tests -t .
```

**Good:** `OK (skipped=37)`, 1,188 tests.
**Bad:** anything else — do not interpret §2 onward on a red suite.

---

## 2. The row join — does every manifest row find its page?

Use a name from §0's second list.

```sh
python3 tools/tablejoin.py 0049 --library "$LIB"
```

**Good:** for every table, `expected` equals `matched` and `missing` is
`0`.

The runs table above it is worth reading: one run holding two tables,
or one table spread over several runs, is normal — that is why the join
exists and why an ordinal cannot do this.

| symptom | meaning |
|---|---|
| `N identifier-shaped tokens NOT in the manifest` | the pattern is too narrow, or the manifest is of another build |
| `N manifest rows on NO page` | report.pdf and report.tables.json were not built together |
| `identifiers on 0 of N pages` | the manifest's bibkey is empty or wrong |

Then run it on the largest listing §0 named, where a table really does
span many pages. Quote the name exactly, in quotes if it has spaces.

---

## 3. The cell rect — does the emitted geometry match the lattice?

**This is the acceptance test for the emitter.** Use a name from §0's
third list.

```sh
python3 tools/manifestcheck.py 0049 --library "$LIB"
```

**Good:** `sha MATCH`, then all four edges with median `0.0` and
`<=1px` at `100.0%`.

**`sha MISMATCH` stops the run.** The manifest does not describe that
PDF and nothing measured against it means anything.

**The residual is the finding — read its shape, never a pass:**

| shape | meaning | where the fix goes |
|---|---|---|
| a constant on every cell (`median` = `min` = `max`) | a converter bug: an origin offset or an off-by-one | arithmetic, in the emitter or in `cellrect` |
| scattered, no constant | a real difference between the two detections | the spec, not the code |
| x constant `0`, y `0` or `-1` | what a correct build looks like | nothing |
| one row far out, the rest fine | that row took the header's rule instead of its own | the emitter |

A row listed under `refused (rules_on_one_page false)` is correct
behaviour: its two rules are on different pages, so it has no rectangle.

Two independent cross-checks. These read the PDF's own vector content
instead of the manifest, so they say which SIDE is wrong:

```sh
python3 tools/rulediff.py 0049 --library "$LIB"
python3 tools/cellcheck.py 0049 2 --rows 20 --library "$LIB"
```

`rulediff` uses no raster and no dpi, so its delta is the emitter's
error alone. **Good: both lines within ±0.002 bp.** A y delta near
`±0.199` means edges were emitted where centrelines were asked for —
that is half of `rule_width_bp`. A large constant x delta is an origin
offset.

---

## 4. `compare`'s new geometry columns

Renders one page twice, then compares. Replace `0049` and the page
number if you like.

```sh
gs -q -dNOPAUSE -dBATCH -sDEVICE=pgmraw -r300 -dFirstPage=2 -dLastPage=2 -sOutputFile=/tmp/a.pgm "$LIB/0049/report.pdf"
gs -q -dNOPAUSE -dBATCH -sDEVICE=pgmraw -r600 -dFirstPage=2 -dLastPage=2 -sOutputFile=/tmp/b.pgm "$LIB/0049/report.pdf"
python3 -m inkdrill compare /tmp/a.pgm /tmp/b.pgm --page-number 2 | head -5
```

**Good:** the header ends `| row h | row y0 | row y1 |`, and on every
row `row y1` minus `row y0` equals `row h`. Values are pixels of the
300 dpi raster, y downward, both ends inclusive.

**Bad:** a row where that subtraction does not give `row h` — both come
from one lattice row and cannot disagree. Missing columns means an old
checkout.

---

## 5. The matrix grid skeleton

Needs a `.pgm` crop of a matrix with visible brackets or parentheses.

```sh
python3 tools/gridskel.py /path/to/crop.pgm --cells
```

**Good:** `ROWS x COLS` matching what the picture shows, then the
`&&&\\` skeleton and a rect per cell.

Read the two `how` lines. `break at K (xR)` means K separators with a
step of R between separator and intra-cell white; R should be 3 or
more. `no break -- every gap is a separator` is correct for a matrix of
single symbols.

**Known failure — do not report it as new:** a `\vdots` or `\ddots` row
inflates the ROW count, because every column has its dots at the same
height so the white between them runs the full width. Columns are
unaffected.

`REFUSED: no pair of tall outer components` is correct for an aligned
display. That is not a matrix, and a grid there would be invented.

---

## 6. Font measurements

Needs a TeX tree. Skip if the second command says `FONT NOT FOUND`
throughout.

```sh
python3 tools/calfonts.py --library "$LIB" | head
```

**Good:** about 10% of documents `rebound` — they load a package that
redraws `\mathcal`. `unreadable` means an e-print would not open; it is
not a finding.

```sh
INKDRILL_TYPE1=/usr/share/texmf-dist/fonts/type1 python3 tools/famjunctions2.py /tmp/fam.json | tail -30
```

**Good:** `\mathcal` reads 1 junction on CM, LM and XITSMathR;
`\mathscr` reads 3 or more everywhere. txfonts G at 3/2/2 is the known
exception, and the reason the cut is 4 rather than 3.

It also prints instability across sizes — expect roughly 15% of glyphs
to change hole count and 25% to change junction count. **Those are
meant to be non-zero.** 0% means the size sweep is not varying.

---

## 7. Resolution stability — slow, 20 minutes or more

```sh
python3 tools/dpiclass.py --docs 8 --seed 496 --library "$LIB" -o /tmp/rows.tsv
python3 tools/dpisummary.py /tmp/rows.tsv
```

**Good means the numbers reproduce, not that they are small:** holes
move on about 36% of rows, the finding class changes on about 17%, and
`component` keeps its verdict on about 94%. The rendered column moves
far more than the scan column, because it is drawn without
anti-aliasing — 2 grey levels against the scan's 256.

**`absent` and `stable` retaining 100% is a tautology, not evidence.**
`scale_stable` is an input to the flag, so a `stable` row uses
identical inputs at both resolutions and cannot be reclassified.

---

## 8. The ring channel floor

Needs `report-crops` and ImageMagick.

```sh
python3 tools/ringfloor.py --n 200 --seed 591 --library "$LIB"
```

**Good:** p99 below 1.0 holes per component, and nothing at or above
2.0. The speckle regime is about 3.4, so a p99 near it means hole
counts in that population are noise and any topology claim over them is
unsafe.

---

## 9. The PDF side channel

Self-contained — builds its own test PDF, needs no corpus.

```sh
python3 tools/pdfchannel.py --work /tmp/pdfchan
```

**Good:** the attachment `KEPT` on all eight passes; `/PieceInfo`
`gone` on the two ghostscript rows and `KEPT` on the rest.

Read the second table too. It is the raw byte scan, printed under a
heading saying it is not the answer, and it disagrees with the
structural table on three rows. That gap is the point: a marker inside
a recompressed stream is present and invisible to a substring search.

---

## What to send back

The command, the whole output block, and the document name.

For §3 especially, send the per-edge table rather than a verdict. The
shape of the residual is what says where the fix goes, and "pass" or
"fail" throws that away.
