# inkdrill — Algorithms, Structure and Inner-Loop Performance

*Written by the project auditor against `origin/main` @ `6a4869d` — all
fifteen units present, 517 tests. Every performance
figure below was measured on that tree, single core, CPython 3.12, on a
synthetic 2.2 Mpx text-like page or on real Latin Modern glyph renders as
noted. Absolute numbers will differ on your hardware and on 3.14; the
ratios are the point.*

**Format note.** This is Markdown with LaTeX math, deliberately: `pandoc`
turns it into Beamer for the short version and into HTML for
pdfdrill.github.io without a second source of truth.

---

## 1. What the pipeline actually is

Three representations, in order of decreasing size and increasing
structure. Every stage converts one into the next and nothing ever goes
back.

| | representation | size on a 600 dpi A4 text page | module |
|---|---|---|---|
| 1 | **grey buffer** | 34.8 MB | `pngio` |
| 2 | **ink mask**, `0xFF`/`0x00` | 34.8 MB | `raster` |
| 3 | **run list**, maximal ink intervals | ~0.5 MB | `raster` |
| 4 | **run adjacency graph** (RAG) | ~1 MB | `sweep` |
| 5 | **Reeb graph**, moments, nesting | ~20 kB | `reeb`, `aggregate`, `nest` |

The single design decision the whole thing rests on: **the run list is the
pixel set, compressed, and everything downstream operates on runs rather
than pixels.** A typical glyph is ~190 px and ~9 runs, so anything phrased
in runs is an order of magnitude cheaper than the same thing phrased in
pixels — and §7 shows the one place where that discipline was dropped and
what it costs.

---

## 2. Stage 1 — binarisation and run extraction

### 2.1 Mask encoding

One encoding package-wide: `0xFF` ink, `0x00` background, `bytes`,
row-major. This is not cosmetic. It exists so that both hot operations are
single C calls:

```python
mask = gray.translate(lut)      # binarise: one bytes.translate over the page
s    = data.find(b"\xff", pos, end)   # run start: one memchr-class scan
```

`binarize` builds a 256-entry lookup table once per (threshold, polarity)
and caches it. The threshold comparison is strict — ink iff
$g < \theta$ — so $\theta = 0$ yields an empty mask and $\theta = 256$ a
full one, with no off-by-one at the ends.

### 2.2 Run extraction

```python
def _iter_runs_row(mask):
    data, w, h = mask.data, mask.width, mask.height
    find = data.find
    for y in range(h):
        base = y * w; end = base + w; pos = base
        while True:
            s = find(b"\xff", pos, end)
            if s < 0: break
            e = find(b"\x00", s + 1, end)
            if e < 0: e = end
            yield Run(y, s - base, e - base - 1)
            pos = e + 1
```

Two `find` calls per run and **zero interpreted work per pixel**. Cost is
$O(\text{pixels})$ in C plus $O(\text{runs})$ in Python. Blank regions cost
essentially nothing because `find` skips them at memory bandwidth.

Column scanning uses `data[x::w]` — a C-level strided slice into a fresh
`bytes` — then the same two-`find` loop. That copies the column, which is
the price of not maintaining a transposed mask.

**Measured: 116 Mpx/s.** This is the fastest stage in the pipeline by an
order of magnitude and it is the reason the mask encoding is what it is.

A `Run` is `(line, lo, hi)` in *scan* space with inclusive bounds, and the
only sanctioned converter to image space is `Run.image_span(axis)`. Nothing
downstream indexes the tuple positionally — that convention is what makes
the row and column sweeps interchangeable at all.

---

## 3. Stage 2 — the sweep

This is the core, and it is where your original design idea lives.

### 3.1 The run adjacency graph

Nodes are runs. An edge joins two runs on **consecutive** scan lines that
touch:

$$
p \sim r \iff p.\mathit{hi} \ge r.\mathit{lo} - d \;\wedge\; p.\mathit{lo} \le r.\mathit{hi} + d,
\qquad d = \begin{cases} 1 & \text{8-connectivity} \\ 0 & \text{4-connectivity} \end{cases}
$$

The connectivity slack $d$ is the *entire* difference between 4- and
8-connected labelling. Nothing else in the algorithm changes.

Adjacency is found by a two-pointer merge over the previous line's runs,
both sorted by `lo`:

```python
while pi < len(prevline) and prevline[pi][1] < r.lo - slack:
    pi += 1                       # monotone: never rewinds
pj = pi
while pj < len(prevline) and prevline[pj][0] <= r.hi + slack:
    adj.append(prevline[pj][2])
    pj += 1
```

`pi` advances monotonically across the whole line, so the total cost of the
adjacency scan for one line is $O(|\text{prev}| + |\text{cur}|)$, not
$O(|\text{prev}| \cdot |\text{cur}|)$. There is no label image anywhere —
this is the significant departure from the classical Rosenfeld-style
two-pass labeller, which carries a full-width label row and probes it per
pixel.

### 3.2 Union-find

Standard, with the two optimisations that matter and neither of the ones
that don't:

```python
def find(self, i):
    p = self.parent
    while p[i] != i:
        p[i] = p[p[i]]        # path halving, one write per step
        i = p[i]
    return i
```

Path *halving* rather than full compression: one pass, one store per step,
no recursion and no second walk. Union by size. `parent` is a flat `list`
indexed by run id, so `make()` is an append and ids are dense — no dict, no
hashing.

The amortised bound is the usual $O(\alpha(n))$, but at these sizes the
real behaviour is "almost always one or two steps", because runs are
unioned to their immediate predecessor as they are created.

### 3.3 Events — the Morse structure

A row-down sweep computes the connected components of the sublevel sets of
$h(x,y) = y$. That makes the algorithm a filtration, and the interesting
moments are the critical points of $h$:

| event | detected as | Morse meaning |
|---|---|---|
| **birth** | run with no edge upward | local minimum |
| **merge** | run joining $\ge 2$ previously distinct roots | join saddle |
| **cycle** | edge whose endpoints were already in one component | a 1-cycle is born — a hole |
| **split** | previous-line run with $\ge 2$ edges downward | fork saddle |
| **close** | component absent from the current line | local maximum |

Two things are worth stating explicitly.

**Splits are invisible to union-find.** The structure is monotone; it never
splits. Sweeping an `A` downward, the fork into two legs produces no union
event at all. This is precisely why the RAG is retained rather than a merge
log: a merge log records the crossbar joining the stems of an `H` and loses
the fork below it.

**Holes are detected as they happen.** An edge whose two endpoints already
share a root closes a loop. Counting those gives the cycle rank

$$|C| = |E| - |V| + |\text{components}|$$

incrementally, at no extra cost, for free during the sweep. The alternative
— which the previous code base did — is to rebuild the same graph
afterwards to count `adj8`. The edges were being enumerated either way.

### 3.4 Capture levels

`Capture.NONE` / `EVENTS` / `GRAPH` control what is *retained*, never what
is *computed*. Component partition, edge counts and cycle counts are
produced at all three, because they are counters. **Measured cost of
retention: +11% for events, +13% for the full graph.**

### 3.5 The four orientations, for two scans

The RAG is undirected — adjacency is symmetric. So row-up is the row RAG
with the orientation reversed: minima become maxima, joins become forks. No
second scan. Only row-vs-column is a genuinely independent sweep, because
the node sets differ (horizontal vs vertical runs).

$$\text{2 scans} \longrightarrow \text{4 orientations}$$

And because both sweeps must agree on the component partition, running both
is also a free correctness oracle.

---

## 4. Stage 3 — derived structures

### 4.1 Reeb contraction (`reeb.py`)

Maximal chains of *regular* runs collapse into one arc:

```python
if not _junction(run) and len(run.up) == 1:
    up = by_id[run.up[0]]
    if not _junction(up) and up.down == [run.id]:
        # continue the predecessor's arc
```

A run is a junction when $|{\uparrow}| \ge 2$ or $|{\downarrow}| \ge 2$.
The subtlety, which cost a round of rework: the split must be on
**junctions**, not on degree-2. A birth has $|{\uparrow}| = 0$ and a close
has $|{\downarrow}| = 0$, so neither is degree-2 — but neither is a
branch point either, and cutting there turns a plain vertical bar into
three nodes and breaks persistence as $h_{\text{close}} - h_{\text{birth}}$.

**Measured: 5–7× node reduction on real ink** (3,947 runs → 566 arcs).

### 4.2 Moments (`aggregate.py`)

Accumulated from runs in closed form, never per pixel. For a horizontal run
$[x_0, x_1]$ at height $y$ with $n = x_1 - x_0 + 1$:

$$
\sum x = \frac{(x_0+x_1)\,n}{2}, \qquad
\sum x^2 = \sigma(x_1) - \sigma(x_0 - 1), \qquad
\sum xy = y \sum x
$$

with $\sigma(n) = n(n+1)(2n+1)/6$. The last identity holds because $y$ is
constant within a row-run — which is exactly why runs are the right unit.

Everything follows by pure addition, so component merging is addition and
band stitching (§5) is addition. Centroid, central moments, principal axis
and elongation are derived at the end.

**No angles are stored anywhere in the core.** Directions are unit vectors;
`angle_deg_ccw` (y-up) and `angle_deg_screen` (y-down) are the only
producers, each naming its convention. This is a direct response to the
sign drift that existed between `blobtrack.angle_deg` and
`blobcc.orientation_deg` — a vector cannot silently disagree with itself.

### 4.3 Nesting (`nest.py`)

Holes are background components of the blob's own inverted local mask, run
through **the same sweep** with `conn=4`. The tracker is recursively its
own hole-finder, and depth beyond 1 is recursion on the result — the bbox
strictly shrinks, so it terminates.

The connectivity pair is constrained, not free: 8-connected foreground
implies 4-connected background.

---

## 5. Stage 4 — banding and scheduling

`band.stitch` merges independently swept horizontal bands. It works because
the moment aggregates add and the seam test is the same adjacency predicate
as §3.1 applied across the boundary. Two properties make it cheap:

- a band boundary **is** a line boundary, so a run is never split — the
  node count needs no repair
- concatenating bands in $y_0$ order is *already* globally sorted, so the
  renumbering pass is skipped after an $O(V)$ check

**Measured:** stitch/sweep ratio depends on run density. At ~1,700–5,000
runs/Mpx the ratio is 0.31–0.38 (speedup ceiling 2.6–3.3×); at ~12,600
runs/Mpx it is 0.64–0.92 (ceiling 1.1–1.6×). The mechanism: the sweep is
$O(\text{pixels})$ via `iter_runs` plus $O(\text{runs})$, while stitch is
$O(\text{runs})$ only.

`sched.py` is a deterministic priority scheduler: tasks carry a sort key,
are dispatched in ascending key order, and results are re-sorted by key so
completion order never leaks. `workers=1` uses no pool at all, deliberately
— it is the oracle the parallel path is checked against.

The band tier was measured and **dropped**: PNG decode is 85–95% of
per-page work in the current ingest, so parallelising the sweep has an
Amdahl ceiling of 1.17×. That ceiling is a property of the ingest path, not
of the algorithm.

---

## 6. Stage 5 — fonts, gold standard, classification

- `space.py` — a transform graph of named coordinate spaces joined by
  affines in PDF row-vector order. Conversion is composition along a
  declared path, never a hand-written formula. This is what makes the
  glyph → text → user → page → render chain auditable.
- `font.py` — `pdffonts` inventory, subset-tag stripping, glyph-weighted
  coverage. 94.6–95.9% of glyph instances are on the embedded-outline fast
  path; math font families are at 100%.
- `gold.py` — pdfminer glyph boxes matched to ink components by
  **centre-in-box**, not overlap, because pdfminer's box is the *advance*
  box. Reports four residual classes rather than one agreement rate.
- `classify.py` — 1-NN over three separable channels. See §6.1: the
  channels' worth is entirely a function of how the corpus is split.
- `mathstruct.py` — rows, reference lines, script detection, component
  grouping. See §6.2 for what is deliberately not built and why.

### 6.1 What the classification channels are actually worth

The single most instructive measurement in the project, because the answer
changes by 35 points depending on how the corpus is divided — and nothing
about the code changes at all.

| split rule | signature | extents | bitmap | all three |
|---|---|---|---|---|
| by **component** (leaky) | 11.8% | 93.7% | 95.7% | 96.0% |
| by **document** | 11.2% | 43.8% | **94.0%** | 95.7% |
| by **font** (44 groups) | 9.2% | 29.5% | **61.5%** | **86.3%** |

Three things fall out, and each overturned a stated conclusion.

**Extents were almost entirely leakage.** 93.7% → 43.8% between the
component and document splits. Absolute height and width identify the
*document's body size*, not the character; with one document on both sides
the channel is close to a lookup table.

**The bitmap channel is document-independent but not font-independent.**
94.0% across documents, 61.5% across fonts. Normalised shape survives a
change of paper; it does not survive a change of typeface. An independent
probe rendering Latin Modern against DejaVu Serif gave 62.1–72.2%, which
reproduces from corpus data as 61.5%.

**The channels are complementary, and the easy protocol hid it.** On the
document split the signature adds $+0.1$ points and looks redundant.
Across fonts, the three channels together beat the bitmap alone by
**+24.8 points** — 61.5% → 86.3%. What the signature contributes is
exactly what the design predicted: a topological description that does not
care about stroke weight or typeface, carrying information precisely where
a normalised bitmap is weakest. Measured on the easy split, that
contribution is invisible.

The operational rule this produced: *if a split rule changes the answer, it
must be a harness argument rather than a constant.*

**The population, stated plainly.** The class filter keeps classes with
$\ge 12$ instances over the sampled pages. The surviving non-ASCII classes
are `"` `"` and `ﬁ` — **not one `∑ ∫ √ ± ≤ ∈`**. Every accuracy figure above
is therefore measured on body text, and none of it speaks to maths-symbol
classification, which is this project's first application.

### 6.2 `mathstruct.py` — built where measurable, named where not

The plan asked for five things: reference lines per row, sub/superscript
from geometry, big operators and their ranges, fence matching, and a
structure tree emitting LaTeX. **Two are built; three are deliberately not.**

Built:

- `rows()` — glyphs grouped into text lines by vertical overlap, measured
  against **the glyph's own height** rather than the smaller of the two. A
  superscript overlaps its line by only a third of the *line's* height, so
  a rule measured against the line excludes exactly what the unit exists to
  find.
- `reference_lines()` — estimated from the ink's **modal** extremes, not
  its extremes, so one tall bracket does not move the top of a line.
- `detect_scripts()` — requires both a height reduction and a vertical
  offset, relative to the glyph's own row.
- `group()` — joins components belonging to one glyph (`i`, `j`, `:`, `=`)
  by three conditions: horizontal overlap, **stacking**, and a bounded gap.
  The stacking test is the whole distinction: parts of one glyph sit *above*
  each other, adjacent letters sit *beside* each other.

Not built, with the reason recorded: big operators, fence matching, the
structure tree and the LaTeX projection all need **symbol identity** for
`∑ ∫ ( [`, and §6.1 shows there is no measurement of maths-symbol
classification at all. Building them would be unfalsifiable.

**The label problem.** The premise was "sub/superscript from geometry alone
against pdfminer's `role` as label". There is no `role` field, so the label
became the PDF's own font `size` — genuinely independent of geometry, which
is what makes the test non-circular. Result: **precision 100.0%, zero false
positives in 37,759 glyphs; recall 13.5% and not interpretable**, because
"smaller than the row's modal size" also catches captions, footnotes and
mixed-size headings. The label over-claims; the geometry does not. So the
unit is a *detector*, not a classifier, and says so.

Three faults that no passing test would have shown, all found by the
failures rather than by review:

1. **Rows must seed tallest-first.** In reading order a superscript opens
   its own row before the line it belongs to exists, and nothing can merge
   them afterwards. A determinism test cannot catch this — the wrong answer
   was perfectly deterministic.
2. **Grouping needs stacking, not width.** The original justification was
   simply wrong.
3. **Row overlap must be measured against the glyph's own height**, or the
   threshold that suits body text excludes the scripts.

Plus two branch-sweep survivors that were real gaps rather than equivalent
mutants, and both are a sub-species worth naming:

4. **Every reference-line fixture had `mode == median`.** `_mode` falls
   back to the median when all values are distinct, so the two code paths
   produced identical output on every fixture and neither was ever
   distinguished from the other. Nothing was unguarded; the *fixtures* were
   degenerate.
5. **The horizontal-overlap test was unreachable**, because `group()`'s
   x-ordered early break (`gb.x0 > ga.x1`) rejected the pair before the
   overlap condition was evaluated. The test named a condition it never
   reached.

Neither is an unguarded branch, and neither is caught by asking "is this
guarantee asserted?" — the assertion exists and passes. They are caught by
mutating the branch and watching nothing fail.


---

## 7. Inner-loop performance, measured

### 7.1 Where the time goes

Synthetic 2.2 Mpx page, 27,488 runs, 546 components:

| stage | throughput | note |
|---|---|---|
| `iter_runs` | **116 Mpx/s** | two `bytes.find` per run, zero interpreted per-pixel work |
| `sweep(GRAPH)` | 15.6 Mpx/s | **197k runs/s** — this is the real unit |
| stitch (K=64) | ~0.2 s | $O(\text{runs})$, flat in $K$ |

Profile of the sweep, by self time:

```
  0.242 s   sweep            (the loop body itself)
  0.048 s   _UF.find         210,371 calls
  0.046 s   list.append      275,478 calls
  0.028 s   _iter_runs_row    27,489 calls
  0.025 s   len              189,426 calls
  0.020 s   dict.pop         107,768 calls
```

Nothing is dominated by one call. It is spread across interpreted bytecode
in the loop body — which is the finding, and §8 explains why that matters
more than it looks.

### 7.2 The one place the run discipline was dropped

`classify.normalise` resamples a component to a $12\times12$ bitmap by
scanning **every pixel of every cell**:

```python
for j in range(grid):
    for i in range(grid):
        for y in range(y0, min(y1, h)):
            if any(data[row + x] for x in range(x0, min(x1, w))):
```

That is $O(\text{pixels})$ interpreted, in a code base whose entire premise
is that runs are the pixel set compressed. Rewriting it from the run list —
one shift-and-mask per run, with the cell spans tabulated once per
$(n, \text{grid})$ so that glyphs narrower than the grid are handled
exactly:

```python
rf, rl = spans(h, grid); cf, cl = spans(w, grid)
for r in iter_runs(mask, "row"):
    band = ((1 << (cl[r.hi] - cf[r.lo] + 1)) - 1) << cf[r.lo]
    for j in range(rf[r.line], rl[r.line] + 1):
        v |= band << (j * grid)
```

**Measured on 339 real Latin Modern glyph crops at 12–44 px, including the
narrow `. , ; : ' -`:**

| | throughput | 17,008 glyphs |
|---|---|---|
| current, per-pixel | 6,775 glyphs/s | 2.51 s |
| run-based | **45,657 glyphs/s** | **0.37 s** |
| | **6.74×** | **0 disagreements / 339** |

The tabulation matters: the forward cell definition uses
`max(y0+1, (j+1)*h//grid)`, so when a glyph is narrower than the grid the
cells *overlap* and one source column lights several. A naive inverse
mapping gets 139/339 wrong. Tabulating the exact forward spans once per
size — and sizes repeat heavily across a corpus — makes it exact and still
$O(\text{runs})$.

### 7.3 The packed-int bitmap

`normalise` returns a Python `int`, so Hamming distance is

```python
def bitmap_distance(a, b): return (a ^ b).bit_count()
```

one C-level popcount instead of 144 interpreted comparisons. This is not
micro-optimisation: with per-bit comparison the confusion-matrix run did
not finish in 30 minutes; with popcount it finished in five. A classifier
nobody can afford to run produces no confusion matrix, and then the
question it was built to answer cannot be asked.

---

## 8. Your branch-prediction question, answered directly

You spent significant effort 20 years ago crafting an if/else topology
ladder for the branch predictor of that era. That was the right
optimisation for a compiled inner loop where the CPU executes your branches
directly. **It is not the right optimisation here, and the measurement says
why.**

Measured, 2M-element ladder over a 90/7/2/1 distribution:

| variant | time | ratio |
|---|---|---|
| ladder ordered common-first, random input | 0.058 s | 1.00× |
| ladder ordered common-**last**, random input | 0.078 s | 1.34× |
| ladder ordered common-first, **sorted** input | 0.051 s | 0.88× |

Sorting the input makes every branch perfectly predictable and buys **12%**.
Reordering the ladder buys 34% — and that 34% is not misprediction, it is
*executing fewer comparison bytecodes*. In CPython the interpreter's own
dispatch swamps the CPU's branch predictor: the predictor is busy
predicting the eval loop's computed goto, not your `if`.

The comparison that does matter:

| | time for 1 MB | ratio |
|---|---|---|
| `bytes.count(0xFF)` | 0.95 ms | 1× |
| interpreted `sum(1 for x in buf if x == 0xFF)` | 13.58 ms | **14×** |

And for the fuller pipeline case, `iter_runs` at 116 Mpx/s against
`normalise`'s per-pixel scan at ~1.3 Mpx/s is a **90× gap**.

So the modern analogue of your ladder is not *branch ordering* but **branch
elimination**: get the loop across the interpreter boundary into a C bulk
primitive, where the branches are somebody else's problem and are already
well-predicted. That is exactly what the mask encoding (`translate`,
`find`), the packed-int bitmap (`bit_count`) and the run-based `normalise`
above all do. The pattern is consistent and it is worth naming as the
project's actual optimisation discipline.

**Where your original technique becomes relevant again:** the moment any of
this is ported to C, Rust or Cython, the calculus inverts. Three places in
the current code would then need exactly the treatment you remember:

1. **The adjacency predicate** (§3.1) — two comparisons per candidate run,
   executed $O(\text{runs})$ times, with a highly skewed outcome
   distribution (most candidates fail the first test). Branchless via
   arithmetic on the comparison results.
2. **The Paeth predictor** in `pngio` — the textbook branchy PNG filter,
   20.6% of real corpus rows. `abs()` three times and a three-way
   comparison, per byte. This is *the* classic case and there are known
   branchless formulations.
3. **`_UF.find`** — an unpredictable pointer chase. Path halving already
   minimises the trip count, which is the right structural answer; the
   remaining branch is data-dependent and mispredicts by nature.

None of these is worth touching in CPython, because in CPython none of them
is where the time goes.

---

## 9. Concrete improvements, ranked

> **Status note added on integration (2026-08-09).** Items 5 and 6 below
> were reproduced exactly and acted on. **Item 5 was a real bug and is
> fixed:** `rows()` now seeds from the modal height, and a 50 px brace
> spanning three body lines gives `[1, 8, 8, 8]` rather than `[25]`.
> **Item 6 is confirmed and NOT fixed**, because the proposed remedy does
> not reach it: a display limit does not vertically overlap its operator,
> so `rows()` separates them and `detect_scripts` never classifies them.
> Excluding detected scripts changes no case that can be constructed, so
> the parameter was removed rather than shipped unexercised, and the
> defect is pinned by
> `test_a_display_operator_absorbs_its_limits_KNOWN_DEFECT`. Items 1-4
> and 7 remain open as written.



**1. `normalise` from the run list — 6.7×, exact, ~25 lines.** §7.2. It is
also the only place in the code base that violates the run discipline, so
the fix is a consistency repair as much as a speed one.

**2. Move the sweep's per-run object construction off the hot path.**
275,478 `list.append` calls and a `RunNode` dataclass per run. A
struct-of-arrays store — parallel `array('i')` for line/lo/hi/up/down
offsets — would cut allocation and indirection substantially. This is the
single largest remaining CPython win and it is invasive; worth measuring
before committing.

**3. Cache `len(prevline)` out of the two-pointer loop condition.** 189,426
`len` calls at 0.025 s. Trivially safe, small, free.

**4. Reconsider the column sweep's strided copy.** `data[x::w]` allocates a
fresh `bytes` per column — $w$ allocations of $h$ bytes each per page. For
a 4960-wide page that is 4,960 allocations. A transposed mask built once
with one bulk operation may be cheaper than 4,960 strided slices; it costs
one extra page of memory. Unmeasured.

**5. `rows()` — seed from the modal height, not the maximum.**
"Tallest first" is not "body text first". Measured: three body lines at
y = 0-10, 20-30, 40-50 give `[8, 8, 8]`; adding one 50 px brace spanning
them gives **`[25]`** — a single row. The brace seeds first, opens a row
spanning the whole span, and every body glyph's own-height overlap then
clears the threshold. The failing shapes are `\\left\\{` over a case
distinction, display `∫` and `∑`, matrix delimiters, multi-line fractions —
exactly what the unit is for. `_mode` already exists in the module; seeding
from glyphs near the modal height keeps the superscript fix and removes
this. No fixture catches it because none has a glyph spanning two lines.

**6. `group()` — run script detection before grouping.** The stacking rule
absorbs big-operator limits into the operator: a `∑` with limits above and
below groups as `[[10, 11, 12]]`, one glyph. A limit sits directly above
its operator with near-total x-overlap, is stacked, and its gap is small
relative to the operator's height, so all three conditions hold. `i`+dot,
`\\hat{x}` and `x^2` are all classified correctly; only the operator case
fails. Refusing to group anything `detect_scripts` has already classified
would close it.

**7. If a native port ever happens**, the three sites in §8 in that order,
and the run list becomes a flat `int32` array with no per-run object at
all — at which point the whole sweep is a tight loop over two integer
arrays and your original craft applies directly.

---

## 10. What is genuinely novel here

Worth being precise, because the classical literature covers most of the
component parts.

Connected-component labelling by run adjacency with union-find is old.
Reeb graphs, Morse filtrations and persistence are standard computational
topology. Moment-based orientation is textbook. Nearest-neighbour glyph
matching predates all of it.

What is unusual is the **combination and the ordering**:

- the RAG is *retained* rather than consumed, so components, hole counts,
  the join tree, the Reeb graph and the branch skeleton all come from one
  enumeration of the same edges
- **split events are captured**, which a union-find-only formulation
  structurally cannot do
- four sweep orientations for two scans, via the symmetry of adjacency
- the same sweep is its own hole-finder, recursively, by connectivity duality
- and every claim in the repository carries the measurement that produced
  it, including the ones that refuted the design

That last point is not an algorithm, but on the evidence of fifteen units
it is the part that has mattered most.

---

## 11. What is measured, and what is not

Stated together because the gap is the most important thing a reader of
this document should take away.

**Measured, on real corpus data:** run extraction and sweep throughput;
capture-level cost; contraction ratio; band-stitch cost against run
density; scheduler utilisation and the stage split that killed the band
tier; font coverage, glyph-weighted and stratified; pdfminer alignment
residuals and their dpi dependence; classification accuracy under three
split rules; script detection precision.

**Not measured, and load-bearing:**

- **Maths-symbol classification.** §6.1: the evaluated classes are body
  text, non-ASCII survivors `"` `"` `ﬁ`, not one `∑ ∫ √ ± ≤ ∈`. Every
  accuracy figure in this document is body text. This is the single
  highest-value next measurement, and it needs pages *selected for maths
  content* — raising the page count will not help, because a rare symbol
  stays rare.
- **Script-detection recall.** Precision is 100.0% over 37,759 glyphs.
  Recall reads 13.5% but is not interpretable, because the size-based
  label also fires on captions, footnotes and mixed-size headings.
- **Rotation robustness of the Reeb signature** under a gentle
  (anti-aliased) rasteriser rather than nearest-neighbour resampling.
- **Cross-font behaviour of everything downstream of §6.1's 61.5%.**

Two units are deliberately partial for the same reason: U9's rasterizer
half, and U14's structure tree and LaTeX projection. Both need symbol
identity, and symbol identity is the thing with no measurement behind it.

### 11.1 The deadlock is only apparent

Read as "both blocked on a missing measurement", that is a circle: the
structure tree needs maths-symbol classification, and maths-symbol
classification needs something to classify against.

It resolves, and the resolution is already scoped. **For maths symbols the
template set comes from the font, not from the corpus.** U9 measured maths
font families at **100%** on the embedded-outline fast path — better
covered than body text, because TeX maths fonts are always embedded subsets
while standard text faces often are not. So a template for `∑` is one
rasterisation of one glyph from the document's own font, and the corpus
only has to supply *queries*.

That matters because the corpus cannot supply templates. The
$\ge 12$-instances filter is not an accident of this harness: `∑` may
appear three times in a paper, and raising the page count does not help
because a rare symbol stays rare. Selecting pages for maths content raises
the *density* of maths glyphs but not the count per symbol class. Any
corpus-template protocol runs into the same wall.

So the dependency is a chain, not a cycle:

$$
\text{U9 rasteriser} \longrightarrow \text{maths templates}
\longrightarrow \text{maths classification measurement}
\longrightarrow \text{U14 structure tree}
$$

and the first link is the unblocking move. It also inherits the
self-validating property the design was built for: a query matched to a
template must agree on hole count and Reeb signature, so a mismatch is a
*detected* error rather than a confident wrong answer — which matters more
for `∑` versus `Σ` than for `e` versus `c`.

One design note for that measurement when it happens: §6.1 shows the
channels are complementary **across fonts** (+24.8 points) and near-
redundant within one. Font-rendered templates versus page-rendered queries
is a cross-rasteriser comparison — different hinting, different grid
fitting — so the cross-font row, not the document row, is the one to expect.
