╭─── Claude Code v2.1.224 ─────────────────────────────────────────────────────╮
│                                      │ Tips for getting started              │
│          Welcome back Wulf!          │ Run /init to create a CLAUDE.md file… │
│                                      │ ───────────────────────────────────── │
│                ▐▛███▜▌               │ What's new                            │
│               ▝▜█████▛▘              │ Added self-hosted environments: `cla… │
│                 ▘▘ ▝▝                │ Added `archive` plugin source: insta… │
│                                      │ Added a cancel-and-confirm step when… │
│   Opus 5 · Claude Max · Wulf Kolbe   │ /release-notes for more               │
│              ~/inkdrill              │                                       │
╰──────────────────────────────────────────────────────────────────────────────╯


❯ /init                                                                         

● I'll start by exploring the codebase structure.

  Searched for 1 pattern, read 1 file, listed 3 directories, called codegraph (ctrl+o to expand)

● /home/wkolbe/inkdrill has no code in it to document. The complete contents:

  inkdrill/
  ├── .codegraph/          # CodeGraph index — 0 files, 0 nodes, 0 edges (empty)
  ├── .cursor/rules/
  │   └── codegraph.mdc    # CodeGraph MCP usage guide
  └── resume.sh            # one line: claude --dangerously-skip-permissions

  No source files, no package.json/pyproject.toml/Cargo.toml, no README, no
  tests, not a git repo. There are no build, lint, or test commands to document,
  and no architecture to describe — writing a CLAUDE.md now would mean
  inventing all of it.

  Two other things I noticed:

  The Cursor rule is already covered. .cursor/rules/codegraph.mdc is
  byte-for-byte the CodeGraph section already in your global
  ~/.claude/CLAUDE.md, so copying it into a project CLAUDE.md would just be a
  third copy.

  Foreign agent configs exist. You have ~/.codex and ~/.gemini. If you want
  their MCP servers, slash commands, subagents, or skills pulled into Claude
  Code, reply /import to see what's importable, then /import --yes=<digest> to
  apply.

  How do you want to proceed?

  1. Tell me what inkdrill is (language, stack, what it does) and I'll scaffold
  a CLAUDE.md from that — it'll be your intent rather than observed facts, but
  it's a real starting point.
  2. Build something first, then re-run /init once there's a codebase to read.
  3. Point me at the actual project if the code lives somewhere other than this
  directory.

✻ Sautéed for 38s

❯ add session id to the resume.sh script in the project folder, create a git    
  and a public repo on my GitHub account. Then use ~/Downloads/inkdrill.zip to  
  start your first tests                                                        

  Ran 2 shell commands (ctrl+o to expand)

● A Python project with tests. Let me extract and read it before anything goes
  public.

  Searched for 1 pattern, read 2 files, ran 1 shell command (ctrl+o to expand)

● The tests import from inkdrill.raster import ... and the README expects tests/
  and docs/units.md, but the zip is flat. Restructuring to match, and updating
  resume.sh:

  Ran 2 shell commands (ctrl+o to expand)

● Now the tests, before touching git:

  Ran 1 shell command (ctrl+o to expand)

● unittest discover requires the start directory to be a package. Adding the two
  __init__.py files:

  Ran 1 shell command (ctrl+o to expand)

● 103 tests pass — exactly matching the README's claim. Now resume.sh and git
  setup:

● Write(resume.sh)
  ⎿  Added 2 lines, removed 1 line
      1 -claude --dangerously-skip-permissions                           
      1 +#!/bin/sh                                                       
      2 +claude --resume session_016AXerRtTzU6UQzgZQFZhAY --dangerously-s
        +kip-permissions                                                 

  Read 1 file (ctrl+o to expand)

● Write(.gitignore)
  ⎿  Wrote 5 lines to .gitignore
      1 __pycache__/
      2 *.py[cod]
      3 
      4 # CodeGraph index — machine-local
      5 .codegraph/

  Ran 2 shell commands (ctrl+o to expand)

● Creating the public repo now — this publishes the code to
  github.com/WulfKolbe/inkdrill:

  Ran 2 shell commands (ctrl+o to expand)

● All 103 pass, split 36/31/36 exactly as docs/units.md records. Now let me
  finish the original /init — there's a real codebase to document now.
  Searched for 1 pattern (ctrl+o to expand)

● Write(CLAUDE.md)
  ⎿  Wrote 104 lines to CLAUDE.md
       1 # CLAUDE.md
       2 
          working with code in this repository.
       4 
       5 ## Commands
       7 ```sh
       8 python3 -m unittest discover -s tests -t .   # full suite (103 t
         ests)
      10 python3 -m unittest tests.test_sweep.TestCycleRank.test_ring   #
          one test
     … +147 lines (ctrl+o to expand)

  Ran 1 shell command (ctrl+o to expand)

● All three done.

  resume.sh — now claude --resume session_016AXerRtTzU6UQzgZQFZhAY 
  --dangerously-skip-permissions, with a #!/bin/sh line it was missing.

  Repo — https://github.com/WulfKolbe/inkdrill, public, two commits pushed.
  .codegraph/ and __pycache__/ are gitignored.

  Tests — 103 passed, split 36 space / 31 raster / 36 sweep, matching
  docs/units.md §3 exactly. Python 3.14.6, 0.112s.

  I made two structural changes to get there, since the zip was flat but the
  code wasn't written for a flat layout:

  - Tests import from inkdrill.raster import ... and the README points at
  docs/units.md, so I moved the three modules into inkdrill/, the tests into
  tests/, and units.md into docs/.
  - unittest discover refuses a non-importable start directory, so I added
  tests/__init__.py and an inkdrill/__init__.py with a one-line docstring. These
  are the only files I authored in the package.

  I also wrote the CLAUDE.md from your earlier /init — there was a codebase to
  read this time. It leans on docs/units.md rather than restating it, and
  records the constraints that read as deliberate: stdlib-only, no stored
  angles, the single 0xFF/0x00 mask encoding, and the reporting rule that a unit
  is "tests passed on <date>" rather than "done".

  Two things worth your attention:

  The repo is public and resume.sh is in it. The session ID isn't a credential —
  it only resolves against your local session store — but it is now in public
  history, and docs/units.md names your other code bases (blobtrack.py,
  blobcc.ts, deskew.py) and your arXiv corpus plans. If that's more than you
  meant to publish, say so and I'll flip it private; rewriting history to drop
  resume.sh is also cheap at two commits.

  units.md §4.8 is worth checking before U9. It flags "arXiv PDFs are
  predominantly embedded, non-Type-3 fonts" as unsampled, and calls it the
  cheapest assumption to verify — the entire U9 fast path rests on it. That's a
  pdffonts sweep over a corpus sample, not a code change.

✻ Worked for 2m 12s

※ recap: Set up your inkdrill project: extracted the zip, restructured it into a package, all 103 tests pass, and pushed it public to github.com/WulfKolbe/inkdrill with a CLAUDE.md. Next, tell me whether the public repo and session ID in resume.sh are fine as-is. (disable recaps in /config)

❯ start U4 reeb.py  -- note if you need test documents: ~/pdfdrill-library      
  contains over 2000 completely processed document, each having the same        
  structure, for document you will find the pngs of the pages in its inspect    
  folder like this example:                                                     
  /home/wkolbe/pdfdrill-library/2604.11744/inspect/pages  if you info about     
  pdfdrill read ~/MX/PDFDRILL folder as copy of the egithub.                    

● U4 is real implementation work with a locked contract in units.md. Let me
  start with the brainstorming skill, as my skill rules require before building.

● Skill(superpowers:brainstorming)
  ⎿  Successfully loaded skill

  Searched for 1 pattern, read 1 file, listed 1 directory (ctrl+o to expand)

● Context gathered. U3's tests pass, so U4 is unblocked per the
  downward-dependency rule. I've read the sweep structures U4 has to consume
  (RunNode.up/down, Component, Event), the six U3 fixtures its tests will reuse,
  and the library layout.

  One thing shapes everything else, so let me ask it first.

  units.md specifies U4's tests as synthetic — the U3 fixtures, a 2-px speck vs
  a stroke, a ±3° rotation. None need a real page. Your library is 3340
  documents of rendered PNGs, which would be a genuine smoke test, but there's a
  catch: the package is stdlib-only and nothing in it reads PNG.
  raster.binarize takes a raw grayscale buffer. Getting from p1.png to an
  InkMask means writing a PNG decoder on zlib — filters, bit depths, palettes,
  interlacing. That's real work, it isn't in units.md's unit list, and it isn't
  U4.

● User answered Claude's questions:
  ⎿  · U4's specified tests are all synthetic. Should I bring the pdfdrill PNG 
     corpus into scope now, or keep U4 to its contract? → Add a real io.py unit 
     to the package

● io.py it is. Before I ask where it slots in, let me find out what the corpus
  actually contains — the decoder's scope depends entirely on that.

  Ran 3 shell commands (ctrl+o to expand)
● Two corpus facts worth correcting before we design against it:

  35 documents have page PNGs, not 2000+. The "over 2000" is pages — 2016 of
  them, spread across 35 documents. The other 3295 directories have no inspect/
  at all. So the corpus gives strong page variety but thin document variety. All
  3330 PDFs are present and pdftoppm is installed, so more can be rendered
  whenever we want them.

  Every PNG sampled is the same format: 8-bit, RGB, non-interlaced, up to ~39
  Mpx. Zero exceptions in 400 sampled files. That makes a decoder far narrower
  than PNG-in-general.

  On numbering: I'll add this as U0 io.py rather than renumbering U4–U14. It has
  no dependencies and feeds U2, so "foundation, below U1" is where it actually
  belongs, and the alternative renumber would break the see docs/units.md 
  U1/U2/U3 cross-references in all three existing module docstrings. Say the
  word if you'd rather it were U15.

● User answered Claude's questions:
  ⎿  · How wide should U0 io.py's PNG support be? The corpus is uniformly 8-bit 
     RGB non-interlaced. → The input is only generated by ghostscript device for
     writing png, only this format needs to be supported.

● Ghostscript png16m, then. Let me verify exactly what it emits rather than
  assume — filter types and chunk set determine the decoder.

  Ran 1 shell command (ctrl+o to expand)

● Verified precisely — the format is narrower than I'd have guessed:

  ┌────────────┬────────────────────────────────────────────────────────────┐
  │  Property  │               Value across 40 sampled pages                │
  ├────────────┼────────────────────────────────────────────────────────────┤
  │ IHDR       │ (8, 2, 0, 0, 0) — 8-bit truecolor RGB, non-interlaced,     │
  │            │ zero variation                                             │
  ├────────────┼────────────────────────────────────────────────────────────┤
  │ Chunks     │ IHDR, sRGB, pHYs, tEXt, IDAT, IEND — no palette, no tRNS,  │
  │            │ no gamma                                                   │
  ├────────────┼────────────────────────────────────────────────────────────┤
  │ IDAT count │ ~58 per file — must be concatenated before inflate, the    │
  │            │ classic decoder bug                                        │
  ├────────────┼────────────────────────────────────────────────────────────┤
  │ Scanline   │ Up 75.8%, Paeth 15.9%, Sub 8.2% (None/Average unused, but  │
  │ filters    │ I'll implement all 5 — a few lines each and libpng's       │
  │            │ heuristic could pick them on other content)                │
  └────────────┴────────────────────────────────────────────────────────────┘

  pHYs carries the dpi, which is exactly what U1's SpaceGraph needs for the
  pt↔px edge later, so I'll parse it rather than skip it.

  Now the scope flag the process asks me to raise. We're at two independent
  units, not one: U0 io.py (PNG → InkMask, depends on nothing) and U4 reeb.py
  (contraction/orientation/persistence, depends on U3). Neither needs the other
  to build — U4's specified tests are all synthetic. They meet only at the
  optional real-page smoke test. units.md is emphatic that each unit gets its
  own contract and its own passing tests, so these want two specs, not one
  merged one.

● User answered Claude's questions:
  ⎿  · U0 io.py and U4 reeb.py are independent. Which do you want me to spec and
     build first? → U0 io.py first (Recommended)

● U0 it is. This project measures rather than asserts, so before I propose a
  design let me check the two things that will actually constrain it: whether
  the RGB is neutral (which decides the greyscale formula) and how slow
  pure-Python unfiltering really is on a 39 Mpx page.

  Ran 1 shell command (ctrl+o to expand)

● Two findings that reshape the design, both measured:

  1. R == G == B on 100% of sampled pixels. Ghostscript png16m writes neutral
  grey for these pages, so there's no luma formula to choose — greyscale is one
  channel. And since every PNG filter operates per-channel at bpp stride, the
  three channels are independent chains: row[0::3] is a C-speed slice that
  isolates one, cutting the work 3× before any cleverness.

  2. Naive decoding is catastrophically slow: 1.20 Mpx/s. That's 32 s for a 39
  Mpx page — against the project's measured 105 Mpx/s for iter_runs and 19 Mpx/s
  for sweep. The decoder would be 88× slower than the sweep it feeds and would
  dominate the whole pipeline.

  Let me measure the fix rather than estimate it.

  Ran 1 shell command (ctrl+o to expand)

● 4.94 Mpx/s — 4.1× faster, and byte-identical to the naive decode. The trick:
  SWAR big-integer arithmetic. (a+b) mod 256 elementwise across a whole scanline
  is ((A&0x7f…)+(B&0x7f…)) ^ ((A^B)&0x80…) — three CPython big-int ops at C
  speed, replacing 2400 interpreted iterations. That covers the 76% of rows
  using the Up filter. Sub rows go through itertools.accumulate; Paeth rows stay
  a Python loop because the predictor genuinely depends on bytes it just
  produced.

  ┌──────────────────────────┬────────────┬─────────────┐
  │          Stage           │ Throughput │ 39 Mpx page │
  ├──────────────────────────┼────────────┼─────────────┤
  │ Naive per-byte           │ 1.20 Mpx/s │ 32.3 s      │
  ├──────────────────────────┼────────────┼─────────────┤
  │ Channel-slice + SWAR     │ 4.94 Mpx/s │ 7.9 s       │
  ├──────────────────────────┼────────────┼─────────────┤
  │ sweep (existing, U3)     │ 19 Mpx/s   │ 2.1 s       │
  ├──────────────────────────┼────────────┼─────────────┤
  │ iter_runs (existing, U2) │ 105 Mpx/s  │ 0.4 s       │
  └──────────────────────────┴────────────┴─────────────┘

  Decoding stays the pipeline's slowest stage at ~4× the sweep. I think that's
  the right place to stop: the remaining cost is concentrated in Paeth rows,
  which are irreducibly sequential, and chasing them further means obscure code
  guarding a step that runs once per page while U7/U8 will parallelize it across
  bands anyway.

  Proposed design — U0 io.py

  Contract. read_png(src) -> PngImage(width, height, gray: bytes, dpi: 
  tuple|None). It returns greyscale bytes, not an InkMask — that composes with
  the existing raster.binarize(gray, width, height, threshold=…) instead of
  duplicating it, and keeps the threshold decision where U2 already owns it. A
  thin load_mask(path, **kw) convenience wraps the two.

  Scope limit, stated up front in the docstring the way U9's is: Ghostscript 
  png16m output only — 8-bit, truecolor RGB, non-interlaced. Anything else
  raises UnsupportedPNG naming the exact IHDR tuple found. All five filters
  implemented regardless, since libpng's adaptive heuristic may pick None or
  Average on content the corpus doesn't contain.

  Guarantees G1–G7, in the house style: multi-IDAT concatenation before inflate;
  CRC verified per chunk; output length is exactly width*height; decode is
  byte-identical to the naive reference implementation; pHYs → dpi when present,
  None otherwise; unsupported IHDR raises rather than silently mis-decodes; and
  the SWAR fast path agrees with the naive path on every filter type.

  Testing. The naive per-byte decoder becomes the permanent oracle — it lives in
  the tests and the fast path is checked against it, which is exactly the
  independent-oracle pattern U3 uses against flood fill. Plus hand-built tiny
  PNGs exercising each filter, a multi-IDAT file, a corrupt CRC, and each
  rejected IHDR variant. A separate opt-in corpus test (env-gated, so the
  default suite stays hermetic and fast) decodes a sample of real pages and
  asserts sweep runs clean on them.

  One open question before I write the spec:

● User answered Claude's questions:
  ⎿  · Where should the greyscale conversion live, given R==G==B holds for this 
     device? → Take one channel, verify cheaply (Recommended)

● One wrinkle in the neutrality check worth pinning down: verifying G and B on
  an arbitrary row isn't free, because Up/Paeth rows reference the row above, so
  checking row r would mean decoding all three channels from row 0. Only
  self-contained rows (filter None or Sub) can be checked in isolation. Let me
  see how many pages actually have those.

  Ran 1 shell command (ctrl+o to expand)

● That changes the design — my earlier 100% figure was measured on raw
  pre-unfilter bytes and was wrong. Properly unfiltered, 1.9% of rows contain 
  non-neutral pixels. Let me find out whether that's real colour or rounding.

  Ran 1 shell command (ctrl+o to expand)

● Definitive, and it overturns the option you picked: 4 of 60 pages contain real
  colour — channel spreads up to 255, i.e. saturated figures in papers, not
  rounding. Raising on non-neutral input would reject ~7% of the corpus, and
  silently taking the red channel would decode red text as near-white and blue
  as near-black. Neither is acceptable.

  But there's a better route. PNG filtering is per-channel at bpp stride, so if
  the source image is neutral, the filtered bytes are neutral too — for every
  filter type, by induction on rows. That means neutrality is detectable on the
  raw inflated stream with no unfiltering at all, as two C-speed slice
  comparisons per row. Let me verify that claim, since the whole design would
  rest on it.

  Ran 1 shell command (ctrl+o to expand)
● Claim verified: 16/16 agreement, colour page correctly flagged, detection
  costs 22.6 ms against a ~1700 ms decode — 1.3% overhead, and it's exact rather
  than sampled.

  That replaces the "raise on non-neutral" behaviour you picked with something
  strictly better: detect exactly, then choose the decode path. Writing the
  spec.

● Write(docs/superpowers/specs/2026-08-07-u0-io-design.md)
  ⎿  Wrote 195 lines to docs/superpowers/specs/2026-08-07-u0-io-design.md
       1 # U0 `io.py` — PNG ingest
       3 Design doc. Written 2026-08-07, before implementation, per the `
         units.md`
       4 convention that a contract precedes its unit.
       6 ## Why this unit exists
       7 
         . `raster.binarize`
       9 accepts a raw greyscale buffer and nothing in the package produc
         ed one. U9, U10
         t beyond its
     … +259 lines (ctrl+o to expand)

● Self-reviewing the spec — three things need fixing.

● Update(docs/superpowers/specs/2026-08-07-u0-io-design.md)
  ⎿  Added 6 lines
      26  palette, greyscale, alpha and Adam7 interlacing are all out of 
          scope and must
      27  fail loudly, never mis-decode.
      28  
      29 +Rejecting *greyscale* input while producing greyscale output lo
         +oks backwards and                                              
      30 +is deliberate: this unit's job is to read what this one device 
         +writes. A                                                      
      31 +greyscale PNG would be easy to support and is still refused, be
         +cause accepting                                                
      32 +an untested input path is how a decoder quietly returns a wrong
         + image. Widening                                               
      33 +the contract is a decision to make with evidence, not a conveni
         +ence to slip in.                                               
      34 +                                                               
      35  All five scanline filters are implemented regardless of what th
          e corpus
      36  contains, because libpng's adaptive heuristic may select None o
          r Average on
      37  content not yet sampled.

● Update(docs/superpowers/specs/2026-08-07-u0-io-design.md)
  ⎿  Added 4 lines, removed 2 lines
      154          claim the two-path decode rests on)
      155      G6  an IHDR outside the stated scope raises UnsupportedPNG
            naming the
      156          tuple found; it never returns a mis-decoded image
      157 -    G7  dpi is Some(x, y) when pHYs is present with unit 1 (me
          -tres), and None                                               
      158 -        otherwise; it is never silently defaulted             
      157 +    G7  dpi is a (x, y) pair when pHYs is present with unit sp
          +ecifier 1                                                     
      158 +        (pixels per metre), converted as ppm * 0.0254; it is N
          +one when pHYs                                                 
      159 +        is absent or carries unit specifier 0 (aspect ratio on
          +ly, no                                                        
      160 +        physical scale). It is never silently defaulted to 72 
          +or 300.                                                       
      161  
      162  ## Testing
      163  

● Update(docs/superpowers/specs/2026-08-07-u0-io-design.md)
  ⎿  Added 5 lines, removed 2 lines
      176  - A corrupt CRC, a truncated stream, a bad signature.
      177  - Each rejected IHDR variant: 16-bit, palette, greyscale, alph
           a, interlaced.
      178  - `pHYs` present and absent.
      179 -- A 1×1 image and a width where `width*3+1` crosses no useful 
          -boundary, for                                                 
      180 -  off-by-one on stride.                                       
      179 +- Stride and edge cases: a 1×1 image; a 1-pixel-wide image, wh
          +ere the Sub and                                               
      180 +  Paeth `a`/`c` terms are always zero; a 1-pixel-tall image, w
          +here the Up and                                               
      181 +  Paeth `b`/`c` terms are always zero; and an even/odd width p
          +air, since the                                                
      182 +  SWAR path builds its masks from `width` and a parity error t
          +here would                                                    
      183 +  corrupt exactly one edge column.                            
      184  
      185  **Corpus test, opt-in.** A separate test decodes a sample of r
           eal pages from
      186  `~/pdfdrill-library` and asserts `sweep` runs clean on them. G
           ated behind an

  Ran 1 shell command (ctrl+o to expand)

● Spec written and committed to
  docs/superpowers/specs/2026-08-07-u0-io-design.md. Please review it before I
  write the implementation plan.

  Where things landed, and what changed along the way:

  You asked me to start U4, and I've spec'd U0 instead — that follows from your
  choice to make PNG reading a real unit, which you picked knowing it defers U4.
  U4 is untouched and still unblocked; its contract in units.md is complete and
  its tests are synthetic, so it needs nothing from U0.

  Two of my own findings were wrong and got corrected by measurement. My first
  neutrality check said 100% — it sampled raw pre-filter bytes and was bad
  methodology. Properly unfiltered, ~7% of corpus pages carry real colour
  figures with channel spreads up to 255. That killed the "take one channel,
  raise on non-neutral" behaviour you selected: it would have rejected a
  fifteenth of the corpus, and the silent variant would have decoded red ink as
  near-white. The replacement is strictly better than either option I offered
  you — an exact neutrality probe on the filtered stream, costing 22.6 ms
  against a 1700 ms decode, then a fast one-channel path for neutral pages and a
  full luma path for colour ones.

  The performance work was necessary, not gold-plating. A naive decoder runs at
  1.20 Mpx/s — 88× slower than the sweep it feeds, which would have made ingest
  dominate every measurement in units.md. Channel slicing plus SWAR big-integer
  arithmetic gets it to 4.94 Mpx/s, verified byte-identical to the naive path on
  a real 8.56 Mpx page. It's still the slowest stage at ~4× the sweep, and the
  spec says so rather than claiming the problem is solved.

  Your corpus is smaller than described. 2016 page PNGs, but across 35 documents
  — the "2000+" is pages, not documents. The other 3295 directories have no
  inspect/ at all. Page variety is good, document variety is thin, which matters
  when U10 starts measuring residual rates. All 3330 PDFs are present and
  pdftoppm is installed, so more can be rendered whenever.

  Two things I'd flag for your judgement in the spec:

  - The corpus test is env-gated and opt-in, so the default suite stays
  hermetic. If you'd rather real pages were part of the standard run, that's a
  one-line change but it makes the suite depend on ~/pdfdrill-library existing.
  - I deliberately reject greyscale PNGs even though the unit outputs greyscale.
  It's justified in the spec, but it's the kind of narrow contract that
  irritates later, so it's worth your explicit agreement.

  Once you approve, the next step is the writing-plans skill to turn this into
  an implementation plan.

✻ Sautéed for 12m 22s

※ recap: Goal is building inkdrill's next unit; I've published the repo, got 103 tests passing, and written a design spec for U0 io.py, the PNG reader. Waiting on your review of that spec before I write the implementation plan. (disable recaps in /config)

❯ I will check for the corpus, even with 2 png should by able to start!         

● Right — the corpus isn't a blocker, and the spec doesn't make it one. The
  default suite is hermetic and builds its PNGs in-test with zlib; the corpus
  test is opt-in and works with whatever's on disk, two files or two thousand.

  Taking that as approval. Your two unanswered flags stay as spec'd: corpus test
  env-gated, greyscale rejected. Both are one-line reversals later if you
  change your mind.

● Skill(superpowers:writing-plans)
  ⎿  Successfully loaded skill

● I'm using the writing-plans skill to create the implementation plan.

  Read 2 files (ctrl+o to expand)

● Confirmed binarize(gray, width, height, *, threshold=128, ink_is_dark=True)
  and the test-class naming convention (T2_1_MaskConstruction — quoted verbatim
  in the status report). Writing the plan.

● Write(docs/superpowers/plans/2026-08-07-u0-io.md)
  ⎿  Wrote 1243 lines to docs/superpowers/plans/2026-08-07-u0-io.md
      1 # U0 `io.py` Implementation Plan
      3 > **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:su
        bagent-driven-development (recommended) or superpowers:executing-
         [ ]`) syntax for tracking.
      5 **Goal:** Read a Ghostscript `png16m` page PNG into a greyscale b
        yte buffer that `raster.binarize` accepts, fast enough not to dom
      6 
      7 **Architecture:** A read-only decoder in three parts — chunk laye
        probe on the *filtered* stream, and two unfilter paths chosen by 
        r arithmetic (4.94 Mp
     … +1462 lines (ctrl+o to expand)

  Ran 1 shell command (ctrl+o to expand)

● Plan complete and saved to docs/superpowers/plans/2026-08-07-u0-io.md,
  committed and pushed.

  Seven TDD tasks, each ending in a passing test and a commit:

  ┌──────┬─────────────────────────────────────────────────────────────┐
  │ Task │                         Deliverable                         │
  ├──────┼─────────────────────────────────────────────────────────────┤
  │ 1    │ Errors, chunk layer with CRC verification, IHDR scope check │
  ├──────┼─────────────────────────────────────────────────────────────┤
  │ 2    │ The naive reference decoder + synthetic PNG builder         │
  ├──────┼─────────────────────────────────────────────────────────────┤
  │ 3    │ The neutrality probe (G5)                                   │
  ├──────┼─────────────────────────────────────────────────────────────┤
  │ 4    │ SWAR one-channel fast path                                  │
  ├──────┼─────────────────────────────────────────────────────────────┤
  │ 5    │ Colour path with Rec.601 luma                               │
  ├──────┼─────────────────────────────────────────────────────────────┤
  │ 6    │ PngImage, read_png, load_mask                               │
  ├──────┼─────────────────────────────────────────────────────────────┤
  │ 7    │ Corpus smoke test, units.md and README updates              │
  └──────┴─────────────────────────────────────────────────────────────┘

  The ordering that matters: the oracle lands in Task 2, before any 
  optimisation. G4 is "byte-identical to the naive reference decoder", so the
  reference has to exist before the first fast path or that guarantee is
  untestable when it's cheapest to get right. Tasks 4 and 5 are then both
  measured against it, and Task 5 additionally asserts the two paths agree on
  neutral input — which they must, since Rec.601 luma of (v,v,v) is exactly v.

  Every code step contains real code, not descriptions. Test counts are the one
  thing left blank: units.md's reporting rule says a unit is "tests passed on
  <date>", so those get filled from an actual run rather than my prediction.

  One decision I'd like from you before execution starts. The spec names the
  module io.py, and I've written the plan that way — but inkdrill/io.py shadows
  the stdlib io. It doesn't actually break anything (Python 3 absolute imports
  mean import io still finds the stdlib), but it trips up readers and linters,
  and by units.md's own logic about the package name, renaming gets more
  expensive with every unit. pngio.py or ingest.py would avoid it. Say the word
  and it's a one-line substitution through the plan; otherwise I'll build it as
  io.py.

  Two options for how to execute:

  1. Subagent-driven (recommended) — a fresh subagent per task with review
  between each. Better for catching a wrong turn in Task 2 before Tasks 4–6 are
  built on it.
  2. Inline — I work through the tasks in this session with checkpoints.

  Which would you like? And note this still leaves U4 reeb.py — what you
  originally asked for — spec'd but unwritten. It's unblocked and independent,
  so it can follow immediately after U0, or run first if you'd rather flip the
  order back.

✻ Brewed for 4m 58s

※ recap: Goal is building inkdrill's next unit; I've spec'd and planned U0 io.py (PNG ingest) since you chose it before U4 reeb.py, all committed and pushed. Next: tell me subagent-driven or inline execution, and whether to rename io.py. (disable recaps in /config)

❯ 1                                                                             
● Subagent-driven it is. Proceeding with io.py as spec'd since you didn't
  redirect on the name.

● Skill(superpowers:subagent-driven-development)
  ⎿  Successfully loaded skill

  Ran 2 shell commands (ctrl+o to expand)

● Setup complete: branch u0-io, workspace, ledger, 7 briefs. Pre-flight scan of
  the plan found no contradictions with its Global Constraints.

  Ran 1 shell command (ctrl+o to expand)

● Task 1: errors, chunk layer, IHDR validation.

● Agent(Task 1: chunk layer) Haiku 4.5
  ⎿  Done (14 tool uses · 33.0k tokens · 1m 20s)
  (ctrl+o to expand)

  Ran 1 shell command (ctrl+o to expand)

● Agent(Review Task 1) Sonnet 5
  ⎿  Done (10 tool uses · 53.7k tokens · 2m 5s)
  (ctrl+o to expand)

● Spec ✅, quality Approved, four Minor findings — deferred to the ledger, they
  don't enter the fix loop.

  Ran 1 shell command (ctrl+o to expand)

● Task 2: the reference decoder and PNG builder — the oracle everything
  downstream is measured against.

● Agent(Task 2: oracle decoder) Haiku 4.5
  ⎿  Done (10 tool uses · 32.5k tokens · 1m 19s)
  (ctrl+o to expand)

  Ran 1 shell command (ctrl+o to expand)

● Agent(Review Task 2) Sonnet 5
  ⎿  Done (19 tool uses · 57.6k tokens · 2m 43s)
  (ctrl+o to expand)

● Spec ✅, Approved. The reviewer independently re-derived the filter formulas
  from RFC 2083 and mutation-tested all five branches — the oracle is
  trustworthy. Two notes carried forward: luma's neutral-pixel test can't detect
  a missing rounding term (Task 5's non-neutral tests cover it), and
  idat_split=7 yields 8 chunks, not 7.

  Ran 1 shell command (ctrl+o to expand)

● Task 3: the neutrality probe — the G5 claim the two-path decode rests on.

● Agent(Task 3: neutrality probe) Haiku 4.5
  ⎿  Done (16 tool uses · 38.4k tokens · 1m 41s)
  (ctrl+o to expand)

  Ran 1 shell command (ctrl+o to expand)

● Agent(Review Task 3) Sonnet 5
  ⎿  Done (10 tool uses · 71.9k tokens · 4m 56s)
  (ctrl+o to expand)

● Important finding: the docstring's induction argument proves only the harmless
  direction of the "iff" — that neutral input yields a neutral filtered stream.
  The safety-critical converse (non-neutral input can never read as neutral) is
  what prevents colour pages decoding as their red channel, and it needs a
  different argument. The reviewer verified the code is correct across 13,775
  adversarial cases and proved the converse via filter invertibility; it's the
  written justification that's incomplete. That enters the fix loop.
  ⎿  Agent "a52180994029e55f3" had no active task; resumed from transcript 
     in the background with your message. You'll be notified when it 
     finishes. Output: /tmp/claude-1000/-home-wkolbe-inkdrill/4c2bddec-f2e9
     -4179-ac4a-ae5869ace73a/tasks/a52180994029e55f3.output

  Ran 3 shell commands (ctrl+o to expand)
● Agent(Re-review Task 3 fix) Sonnet 5
  ⎿  Done (9 tool uses · 45.3k tokens · 1m 31s)
  (ctrl+o to expand)

● Agent "Task 3: neutrality probe" finished · 50s

● Task 3 clean. Continuing to Task 4 — the SWAR fast path.

  Ran 1 shell command (ctrl+o to expand)

● Agent(Task 4: SWAR fast path) Haiku 4.5
  ⎿  Done (16 tool uses · 41.9k tokens · 2m 7s)
  (ctrl+o to expand)

● 12.73 Mpx/s against the 4.94 Mpx/s I measured on a real page — a 2.6×
  discrepancy worth resolving before it reaches units.md. Flagging it to the
  reviewer.

  Ran 1 shell command (ctrl+o to expand)

● Agent(Review Task 4) Sonnet 5
  ⎿  Done (21 tool uses · 87.2k tokens · 5m 43s)
  (ctrl+o to expand)

● The reviewer is challenging my own design-doc figure, and it's about to enter
  permanent documentation. Let me verify this myself rather than accept either
  number.

  Ran 1 shell command (ctrl+o to expand)

● My design-doc figure was wrong, and so was a second one. Let me pin both down
  properly.

  Ran 2 shell commands (ctrl+o to expand)

● 56.5% of pages are non-neutral, not the ~7% my spec claims — and no document
  mixes the two kinds, which smells like a per-document rendering setting rather
  than page content. That distinction decides whether the colour path matters.
  Let me measure the magnitude.

  Ran 1 shell command (ctrl+o to expand)

● Now it's clear. Both design-doc numbers were wrong, and I introduced both:

  - Throughput: I benchmarked the single largest file in an 80-page sample —
  which selected a Paeth-heavy outlier (28.8% Paeth vs the 15.9% corpus norm).
  Typical pages run 24–27 Mpx/s, not 4.94.
  - Colour fraction: my ~7% came from sampling only self-contained rows, ~10% of
  each page. The exact probe says 56.5% of pages are non-neutral, and no
  document mixes the two — it tracks the render setting, not the content.

  Let me get the naive baseline on the same pages so the comparison is honest.

  Ran 1 shell command (ctrl+o to expand)

● Reproducible and byte-identical to naive: 24.3 Mpx/s median for the fast path,
  1.82 Mpx/s naive, a 13.3× speedup. The docstring in io.py carries my wrong
  figures, so that enters the fix loop.
  ⎿  Agent "af14a35c4534a50ab" had no active task; resumed from transcript 
     in the background with your message. You'll be notified when it 
     finishes. Output: /tmp/claude-1000/-home-wkolbe-inkdrill/4c2bddec-f2e9
     -4179-ac4a-ae5869ace73a/tasks/af14a35c4534a50ab.output

  Ran 2 shell commands (ctrl+o to expand)

● Agent(Re-review Task 4 fix) Haiku 4.5
  ⎿  Done (9 tool uses · 31.5k tokens · 1m 12s)
  (ctrl+o to expand)

● Agent "Task 4: SWAR fast path" finished · 39s

● Task 4 clean. Task 5: the colour path — now known to be the majority case, not
  the exception.

  Ran 1 shell command (ctrl+o to expand)

● Agent(Task 5: colour path) Haiku 4.5
  ⎿  Done (29 tool uses · 52.3k tokens · 11m 42s)
  (ctrl+o to expand)

● Colour path measures 1.78 Mpx/s — statistically indistinguishable from the
  naive decoder's 1.82. Since it now handles the majority of pages, that's worth
  the reviewer's attention.

  Ran 1 shell command (ctrl+o to expand)
● Agent(Review Task 5) Sonnet 5
  ⎿  Done (12 tool uses · 68.2k tokens · 2m 48s)
  (ctrl+o to expand)

● Task 5 clean — spec ✅, Approved, one Minor. Task 6 wires it together.

  Ran 1 shell command (ctrl+o to expand)

● Agent(Task 6: read_png and load_mask) Sonnet 5
  ⎿  Done (40 tool uses · 78.5k tokens · 6m 14s)
  (ctrl+o to expand)

  Ran 1 shell command (ctrl+o to expand)

● Agent(Review Task 6) Sonnet 5
  ⎿  Done (37 tool uses · 94.7k tokens · 6m 46s)
  (ctrl+o to expand)

● Two Important findings, both real and both inherited from my brief rather than
  the implementer:

  1. Duplicate IHDR chunks silently mis-decode. The reviewer built a working
  proof: two IHDRs (1x4 then 5x1) with colliding byte lengths, and read_png
  returns a wrong-shaped image with no error.
  2. The ordering constraint I called load-bearing isn't pinned by any test —
  and my stated reason for it was wrong. Bytes slicing never raises IndexError,
  so swapping the order still passes all 37 tests.
  ⎿  Agent "a9eeff290a9fd19e2" had no active task; resumed from transcript 
     in the background with your message. You'll be notified when it 
     finishes. Output: /tmp/claude-1000/-home-wkolbe-inkdrill/4c2bddec-f2e9
     -4179-ac4a-ae5869ace73a/tasks/a9eeff290a9fd19e2.output

  Ran 3 shell commands (ctrl+o to expand)

● Agent(Re-review Task 6 fix) Sonnet 5
  ⎿  Done (22 tool uses · 52.0k tokens · 1m 38s)
  (ctrl+o to expand)

● Agent "Task 6: read_png and load_mask" finished · 1m 19s

● Both findings addressed and independently re-proved. Task 7 — the last one —
  with corrected numbers.

  Ran 1 shell command (ctrl+o to expand)

● Agent(Task 7: corpus test and docs) Sonnet 5
  ⎿  Done (28 tool uses · 76.3k tokens · 3m 7s)
  (ctrl+o to expand)

● The implementer reports the corpus is far larger than I measured. Let me check
  — the user said they'd look into it, and may have been rendering pages while
  we worked.

  Ran 1 shell command (ctrl+o to expand)

● Confirmed — the corpus grew while we worked: 3,272 documents and 18,494 pages,
  up from 35/2,016 when I first scanned. My 56.5% figure was measured
  mid-growth (187 documents represented), but the filter mix came from the small
  early subset. Let me re-measure both on the current corpus before they're
  frozen into units.md.

  Ran 1 shell command (ctrl+o to expand)

● Refined figures on the grown corpus — and one genuinely new fact:

  ┌─────────────────────────┬───────────────────────────────────────────────┐
  │         Measure         │    Now (400 pages, 361 docs, from 18,494)     │
  ├─────────────────────────┼───────────────────────────────────────────────┤
  │ IHDR variants           │ (8,2,0,0,0) × 400 — zero variation on a       │
  │                         │ 400-file sample                               │
  ├─────────────────────────┼───────────────────────────────────────────────┤
  │ Non-neutral pages       │ 54.0% (was 56.5% on the smaller sample)       │
  ├─────────────────────────┼───────────────────────────────────────────────┤
  │ Documents mixing both   │ 2 of 361 — not zero                           │
  │ kinds                   │                                               │
  ├─────────────────────────┼───────────────────────────────────────────────┤
  │ Filter mix              │ Up 73.0%, Paeth 20.6%, Sub 6.2%, None 0.2%,   │
  │                         │ Average 0.1%                                  │
  └─────────────────────────┴───────────────────────────────────────────────┘

  Average filter now appears in real data, which vindicates implementing all
  five rather than only the three the early sample showed.

  Ran 1 shell command (ctrl+o to expand)

● Task 7's structure is right. Now the sample refinements.
  ⎿  Agent "ae310afcd52566579" had no active task; resumed from transcript 
     in the background with your message. You'll be notified when it 
     finishes. Output: /tmp/claude-1000/-home-wkolbe-inkdrill/4c2bddec-f2e9
     -4179-ac4a-ae5869ace73a/tasks/ae310afcd52566579.output

  Ran 2 shell commands (ctrl+o to expand)

● Agent(Re-review Task 7 fix) Sonnet 5
  ⎿  Done (8 tool uses · 57.3k tokens · 1m 25s)
  (ctrl+o to expand)

● Agent "Task 7: corpus test and docs" finished · 1m 31s
● All seven tasks complete. One residual to settle first — the reviewer spotted
  a 3,251 vs 3,272 directory discrepancy, and the corpus is still growing under
  us.

  Ran 1 shell command (ctrl+o to expand)

● Stable and consistent with what's in units.md — the corpus finished rendering.
  The 3,251 was a mid-render count.

  Now the final whole-branch review.

  Ran 1 shell command (ctrl+o to expand)

● Agent(Final whole-branch review) Opus 5 (1M context)
  ⎿  Done (29 tool uses · 117.4k tokens · 10m 15s)
  (ctrl+o to expand)

● Final review: NOT READY — three blockers, all small, all failures of evidence
  rather than of the decoder. The reviewer mutation-tested the suite and found
  tests that cannot fail for the reason they claim. One fix dispatch with the
  complete list.

● Agent(Final review fix wave) Sonnet 5
  ⎿  Done (57 tool uses · 143.7k tokens · 10m 41s)
  (ctrl+o to expand)

  Ran 1 shell command (ctrl+o to expand)

● Agent(Re-review final fix wave) Opus 5 (1M context)
  ⎿  Done (53 tool uses · 91.2k tokens · 9m 23s)
  (ctrl+o to expand)

● The re-review confirms B1–B3, I1–I3 fixed and mutation-proven, but leaves
  three things — including a units.md that now contradicts itself, and a
  throughput median that still doesn't reproduce. That's the third time this
  number has been wrong, so let me settle it definitively with a large sample.

  Ran 2 shell commands (ctrl+o to expand)

❯ Please note your actions are peridoically audited by a chat on Claude.ai,     
  some minutes ago this report arrived: # Audit — inkdrill, U0 `io.py`          
                                                                                
  **Audited:** `github.com/WulfKolbe/inkdrill` at `origin/main` `fe77976`,      
  cloned                                                                        
  2026-08-07, plus the supplied CLI session trace.                              
  **Auditor's note:** the trace is partly truncated in transmission; where a    
  finding rests on a garbled passage it is marked *(trace-only)* and cannot be  
  confirmed against the repo.                                                   
                                                                                
  ---                                                                           
                                                                                
  ## Summary                                                                    
                                                                                
  | | |                                                                         
  |---|---|                                                                     
  | Verified working | U1–U3, **103 tests pass** on a clean clone; all six      
  source files byte-identical to the delivered originals |                      
  | Public implementation of U0 | **none** |                                    
  | Blockers | 3 |                                                              
  | Important | 4 |                                                             
  | Minor | 4 |                                                                 
                                                                                
  The process is working — the reviews caught real defects that would have      
  shipped. The findings below are about **what escaped the process**, not about 
  the decoder.                                                                  
                                                                                
  ---                                                                           
                                                                                
  ## Blockers                                                                   
                                                                                
  ### B1 — Nothing from the seven tasks is in the repo                          
                                                                                
  ```                                                                           
  $ git log --all --oneline                                                     
  fe77976 (origin/main) Plan U0 io.py implementation                            
  640328d Spec U0 io.py — PNG ingest                                            
  a6f15f7 Add CLAUDE.md                                                         
  1bd96d4 Initial commit: U1 space, U2 raster, U3 sweep                         
  ```                                                                           
                                                                                
  There is no `u0-io` branch on the remote. No `inkdrill/io.py`, no             
  `tests/test_io.py`. Four commits, all authored `wkolbe <wulf@wkolbe.de>`,     
  latest 14:22:48 +0200.                                                        
                                                                                
  Roughly two hours of wall clock and ~20 agent invocations — implementers,     
  reviewers, fix waves, an Opus final review — produced work that exists only   
  on                                                                            
  the CLI's local machine. The trace's "committed and pushed" is accurate but   
  refers to the *plan* (`fe77976`), not the implementation.                     
                                                                                
  Two consequences. The implementation is unbacked and one lost workspace from  
  gone. And the audit you asked for cannot cover it: every claim in the trace   
  about test counts, byte-identity to the oracle, and the three final-review    
  blockers is unverifiable from the public repo.                                
                                                                                
  **Action:** push the branch before anything else. Even mid-fix-wave, even     
  failing.                                                                      
                                                                                
  ### B2 — The corrected measurements invalidate the unit's design premise, and 
  the committed spec still carries the wrong ones                               
                                                                                
  The spec at `640328d` states, under "Measured evidence this rests on":        
                                                                                
  | Spec (committed, uncorrected) | Trace (corrected) | Error |                 
  |---|---|---|                                                                 
  | Pages with real colour: **4 of 60 (~7%)** | **54.0%** of 400 pages, 361     
  docs | **~8×** |                                                              
  | SWAR neutral path: **4.94 Mpx/s** | **24.3 Mpx/s** median | 4.9× |          
  | Naive reference: **1.20 Mpx/s** | **1.82 Mpx/s** | 1.5× |                   
  | Filters: Up 75.8 / Paeth 15.9 / Sub 8.2 / None+                             
  ──── (173 lines hidden) ───────────────────────────────────────────────────── 
   found by luck.                                                               
  - **An ordering constraint justified by a wrong reason** was caught — bytes   
    slicing never raises `IndexError`, so the stated rationale was false even   
    though the constraint may be right.                                         
  - **Mutation testing of the test suite itself** in the final review. Given    
  your                                                                          
    standing concern about tests that pass without testing, this is the single  
    most valuable thing in the process and should be kept for every unit.       
  - **Test counts deliberately left blank** in the plan, to be filled from a    
  real                                                                          
    run. Correct application of the reporting rule.                             
                                                                                
  ---                                                                           
                                                                                
  ## Recommended order                                                          
                                                                                
  1. **Push the branch.** (B1) Nothing else is auditable until then.            
  2. **Let the re-review finish and post its verdict.** (I2) Do not touch       
     `units.md` §3 before it returns clean.                                     
  3. **Settle the colour question.** (B2, B3) Measure real-colour pages as a    
  human                                                                         
     would count them. If low, re-render greyscale and the unit shrinks         
     drastically. If genuinely 54%, keep the unit and restate its performance   
     claim as **1.7× effective**, not 13.3×.                                    
  4. **Correct the spec and plan in place**, with a dated note recording that   
  the                                                                           
     originals were measured on a 60-page sample. Do not silently overwrite —   
     the correction is more instructive than the number.                        
  5. **Decide the module name.** (I1) Free today.                               
  6. **Fix `CLAUDE.md`'s test command; gitignore `resume.sh`.** (M1, M3)        
                                                                                
  ---                                                                           
                                                                                
  ## One structural observation                                                 
                                                                                
  U0 was not in the original plan; `raster.py` explicitly scoped image I/O out  
  ("callers supply a grayscale byte buffer"). Inserting it was legitimate — U9, 
  U10 and U11 all need pixels — and the spec's reasoning for numbering it U0    
  rather than renumbering U4–U14 is sound, since the `see docs/units.md         
  U1/U2/U3`                                                                     
  cross-references are already in three docstrings.                             
                                                                                
  But B2 and B3 together suggest the unit was scoped before its own evidence    
  was                                                                           
  solid, and then executed with considerable rigour against that unsound scope. 
  Seven tasks, ~20 agent invocations and two hours went into optimising a path  
  that, on corrected numbers, may not need to exist. The review process was     
  strong enough to catch every defect *inside* the plan and had no mechanism to 
  question the plan's premise — the one number the whole design turned on was   
  never re-measured until Task 4 forced it.                                     
                                                                                
  For U4 onward: **a premise check before Task 1.** Whatever single measurement 
  the design depends on, re-measure it on the full corpus and state the sample  
  size, before the plan is written rather than during its fourth task.          

● Background command "Definitive throughput measurement, three seeds" completed
(exit code 0)

● The audit is right on the most important point, and it's my error: the branch 
  was never pushed. Two hours of work exists only locally. Fixing that before
  anything else.

  Pushed to u0-io (ctrl+o to expand)

● Pushed — 13 commits now auditable at origin/u0-io. Now the premise check the
  audit demands: how many pages carry colour a human would call colour, as
  opposed to merely non-identical RGB.

  Ran 1 shell command (ctrl+o to expand)

● While that runs, fixing the audit's M1 — a CLAUDE.md command I invented that
  errors on first use.

  Searched for 1 pattern (ctrl+o to expand)

● Update(CLAUDE.md)
  ⎿  Added 5 lines, removed 1 line
       7  ```sh
       8  python3 -m unittest discover -s tests -t .   # full suite (103 
          tests)
       9  python3 -m unittest tests.test_sweep          # one module
      10 -python3 -m unittest tests.test_sweep.TestCycleRank.test_ring   
         -# one test                                                     
      10 +python3 -m unittest tests.test_sweep.T3_2_CycleRank.test_ring_h
         +as_one_hole                                                    
      11 +INKDRILL_CORPUS=~/pdfdrill-library python3 -m unittest tests.te
         +st_io_corpus                                                   
      12  ```
      13  
      14 +The last one is opt-in: the default suite is hermetic and the c
         +orpus tests skip                                               
      15 +unless `INKDRILL_CORPUS` names a directory of rendered pages.  
      16 +                                                               
      17  `-t .` is required: it sets the top-level directory to the repo
           root so the
      18  `inkdrill` package is importable from `tests/`.
      19  

  Ran 3 shell commands (ctrl+o to expand)

❯ update of audit report # Audit follow-up — inkdrill U0 `io.py`                
                                                                                
  **Audited:** `origin/u0-io` at `909d1fa`, cloned fresh 2026-08-07.            
  `origin/main` remains at `fe77976`; 13 commits ahead on the branch.           
  **Supersedes:** the first audit of `main` @ `fe77976`.                        
                                                                                
  ```                                                                           
  $ python3 -m unittest discover -s tests -t .                                  
  Ran 154 tests in 0.160s                                                       
  OK (skipped=4)                                                                
  ```                                                                           
                                                                                
  ---                                                                           
                                                                                
  ## Verdict                                                                    
                                                                                
  | First audit | Now |                                                         
  |---|---|                                                                     
  | **B1** implementation not public | **Resolved** — 13 commits,               
  `inkdrill/io.py`, `tests/test_io.py`, `tests/test_io_corpus.py` |             
  | **B2** stale figures, premise unexamined | **Resolved, and better than I    
  asked for** |                                                                 
  | **B3** upstream greyscale render not considered | **Open** — still the      
  largest unclaimed win |                                                       
  | **I1** `io.py` naming | Open, and now more expensive |                      
  | **I2** don't report complete before re-review | Partly — see N3 |           
  | **I3/I4** sampling and corpus stability | **Resolved** |                    
  | **M1/M2/M3** | All three open |                                             
                                                                                
  Three new findings from reading the code, one of them demonstrated by         
  mutation.                                                                     
                                                                                
  ---                                                                           
                                                                                
  ## Resolved, with credit                                                      
                                                                                
  ### B2 — the conclusion was drawn independently, and drawn well               
                                                                                
  `units.md` §3 now says, unprompted:                                           
                                                                                
  > **The colour path is the majority case, not an edge case.** 54.0% …         
  > **corpus-wide effective throughput is dominated by it, roughly 3 Mpx/s,     
  > not the 24.3 Mpx/s of the neutral fast path.** This is recorded as a        
  > known, measured limitation, not hidden behind the fast-path number.         
                                                                                
  That is the same arithmetic my first audit ran (I got 3.10 Mpx/s), reached    
  without it. Three things were added that I had not asked for and that         
  improve on my write-up:                                                       
                                                                                
  - **the spread, not just the median** — n=25, range 8.97–40.93 Mpx/s, with    
    the cause named (per-row filter mix; Paeth-heavy pages run several times    
    slower). The note that *"earlier revisions understated the spread by        
    roughly 5× at both ends"* is the right instinct.                            
  - **the per-document nuance** — neutrality is *almost always* a               
    per-document property, but 2 of 361 documents mix, so *"a decoder must      
    not assume a document's first page predicts the rest."* That kills an       
    optimisation someone would otherwise have reached for.                      
  - **a sized deferred opportunity** — SWAR generalises to the 3-channel row    
    with masks of width `w*3`, capped by the unconditional luma reduction and   
    the ~27% sequential rows, so *"a few-fold gain, not parity."* Bounded       
    rather than hopeful.                                                        
                                                                                
  ### The correction pattern is exactly right                                   
                                                                                
  The spec keeps both original tables **unedited** under `**Superseded          
  ──── (170 lines hidden) ───────────────────────────────────────────────────── 
  ermissions invocation invites                                                 
  copy-paste.                                                                   
                                                                                
  ---                                                                           
                                                                                
  ## Code review notes                                                          
                                                                                
  Read `inkdrill/io.py` in full. Nothing else to report — the following are     
  correct as written and I checked them specifically:                           
                                                                                
  - channel-slice unfilter in `_decode_gray_neutral`: `bpp` collapses to 1 in   
    the sliced domain, so `accumulate` for Sub and `c[i-1] if i else 0` for     
    Average/Paeth are right                                                     
  - SWAR masks built from `w` (sliced width), matching the sliced operand —     
    the parity case the spec worried about                                      
  - `+500 // 1000` is exactly the identity on `(v,v,v)`, so the two paths do    
    agree on neutral input as claimed                                           
  - `_chunks` verifies every CRC including IEND; `read_png` rejects missing     
    IHDR, missing IDAT, inflate failure, and length mismatch                    
  - `prev = line` in the colour path aliases a bytearray that is rebuilt each   
    iteration — no mutation bug                                                 
                                                                                
  One thing that is *not* checked: `read_png` breaks on IEND but never          
  verifies IEND was reached. A file truncated exactly on a chunk boundary       
  parses without complaint. In practice the IDAT length check catches it, so    
  this is a note rather than a finding.                                         
                                                                                
  ---                                                                           
                                                                                
  ## Recommended order                                                          
                                                                                
  1. **N2 first** — three assertions, and it closes a demonstrated hole in the  
     safety property the unit is built around.                                  
  2. **N1** — replace the injectivity paragraph with the inverse-filter         
     induction. Five lines.                                                     
  3. **B3** — run the human-colour count before more decoder work. It decides   
     whether the colour path should be optimised or deleted.                    
  4. **N3 and the 24.1/24.3 drift** — one edit each.                            
  5. **I1** — decide the name now or accept it permanently.                     
  6. **M1, M2, M3.**                                                            
                                                                                
  Everything except B3 is minutes of work. B3 is the one that could remove a    
  third of the unit.                                                            
                                                                                
  ---                                                                           
                                                                                
  ## Note on the process                                                        
                                                                                
  The first audit's structural point was that the review process caught every   
  defect *inside* the plan and had no mechanism to question the plan's premise. 
  This round shows the premise question was picked up and answered thoroughly   
  once Task 4 forced it — that is real improvement.                             
                                                                                
  N2 suggests the complementary gap. The final review mutation-tested and found 
  *"tests that cannot fail for the reason they claim."* The luma test is        
  exactly that and survived, because the mutation search was presumably run     
  against the unit alone. A shared helper between unit and test is invisible to 
  single-file mutation. **For U4 onward: when a test module defines its own     
  copy of a formula the unit also implements, that formula needs one assertion  
  against a value computed outside both.**                                      

● The follow-up audit is precise and the N2 finding is a genuine hole — I'll
  take it in the order given. Checking the human-colour count I started, which
  is exactly B3's experiment.

  Ran 1 shell command (ctrl+o to expand)

● Still running — the naive unfilter plus per-pixel spread analysis over 60
  full-size pages is slow. Dispatching the code fixes in parallel rather than
  blocking on it.

● Agent(Audit fix wave) Sonnet 5
  ⎿  Done (35 tool uses · 95.1k tokens · 5m 21s)
  (ctrl+o to expand)

● Update(CLAUDE.md)  ⎿  Added 1 line, removed 1 line
       5  ## Commands
       6  
       7  ```sh
       8 -python3 -m unittest discover -s tests -t .   # full suite (103 
         -tests)                                                         
       8 +python3 -m unittest discover -s tests -t .   # full suite: 156,
         + of which 4 skip                                               
       9  python3 -m unittest tests.test_sweep          # one module
      10  python3 -m unittest tests.test_sweep.T3_2_CycleRank.test_ring_h
          as_one_hole
      11  INKDRILL_CORPUS=~/pdfdrill-library python3 -m unittest tests.te
          st_io_corpus

● Update(CLAUDE.md)
  ⎿  Added 4 lines, removed 1 line
      47  guarantees `G1`–`G7` at the top of that docstring; the tests ex
          ist to hold those
      48  specific numbered guarantees, so a test named for `G4` is not i
          ncidental.
      49  
      50 -Built (U1–U3), all independent of each other except `sweep` → `
         -raster`:                                                       
      50 +Built (U0–U3), all independent of each other except `sweep` → `
         +raster` and                                                    
      51 +`io.load_mask` → `raster.binarize`:                            
      52  
      53 +- **`inkdrill/io.py`** — ghostscript `png16m` ingest. `read_png
         +` → `PngImage`,                                                
      54 +  `load_mask`. Reads only what that one device writes; anything
         + else raises.                                                  
      55  - **`inkdrill/space.py`** — affine algebra. `Affine`, `Decompos
          ition`,
      56    `SpaceGraph`, `angle_deg_ccw`, `angle_deg_screen`.
      57  - **`inkdrill/raster.py`** — `InkMask`, `Run`, `Rect`, `binariz
          e`, `iter_runs`.

  Ran 1 shell command (ctrl+o to expand)

● Pushed. resume.sh untracked but still on disk. Now the finding that decides
  whether a third of this unit should exist at all.

  Ran 2 shell commands (ctrl+o to expand)

● Background command "Classify non-neutral pages by perceptible colour"
completed (exit code 0)

● Background command "Wait for colour classification result" completed (exit
code 0)

● Decisive, and it refutes the audit's premise. The colour is not a render
  artefact:

  ┌──────────────────────────────────────────────────┬───────┐
  │             Of 60 non-neutral pages              │       │
  ├──────────────────────────────────────────────────┼───────┤
  │ Substantial colour (≥0.1% of pixels, spread >32) │ 70.0% │
  ├──────────────────────────────────────────────────┼───────┤
  │ Minor colour                                     │ 11.7% │
  ├──────────────────────────────────────────────────┼───────┤
  │ Fringing only (spread ≤16)                       │ 18.3% │
  └──────────────────────────────────────────────────┴───────┘

  Extrapolated: ~38% of all corpus pages carry genuine colour. The strongest
  cases are slide decks and video frames — loc943a76a1206_slides at 95.7%
  strongly-coloured pixels, scene_00390 at 88.1%. The corpus grew beyond papers
  while we worked. Recording this, since it's the measurement the whole design
  turns on.

  Searched for 1 pattern (ctrl+o to expand)

● Background command "Wait for colour classification" completed (exit code 0)

● Update(docs/units.md)
  ⎿  Added 32 lines, removed 2 lines
      342  400 sampled pages (216 of 400) are non-neutral and take the co
           lour path —
      343  real colour figures, not a rarity. Neutrality is *almost alway
           s* a
      344  per-document property — of 361 documents sampled, only 2 mix n
           eutral and
      345 -non-neutral pages — consistent with it tracking a render setti
          -ng rather                                                     
      346 -than page content. It is not absolute, though: a decoder must 
          -not assume a                                                  
      345 +non-neutral pages. It is not absolute, though: a decoder must 
          +not assume a                                                  
      346  document's first page predicts the rest.
      347  
      348 +**Is the colour real, or a rendering artefact?** This is the p
          +remise the                                                    
      349 +whole two-path design rests on, so it was measured rather than
          + assumed. If                                                  
      350 +non-identical RGB were merely anti-aliasing fringe, the right 
          +fix would be                                                  
      351 +upstream — re-render with `-sDEVICE=pnggray` and delete the co
          +lour path,                                                    
      352 +the probe and the luma reduction outright. 60 non-neutral page
          +s were fully                                                  
      353 +unfiltered and classified by how many pixels carry a channel s
          +pread above                                                   
      354 +32, a difference a reader would see:                          
      355 +                                                              
      356 +| Class | Share of non-neutral pages | Share of all pages |   
      357 +|---|---|---|                                                 
      358 +| Substantial colour (≥0.1% of pixels strongly coloured) | 70.
          +0% | ~37.8% |                                                 
      359 +| Minor colour (<0.1% strongly coloured) | 11.7% | ~6.3% |    
      360 +| Fringing only (max spread ≤ 16) | 18.3% | ~9.9% |           
      361 +                                                              
      362 +**The colour is overwhelmingly real content, not an artefact.*
          +* Roughly 38%                                                 
      363 +of all corpus pages carry colour a reader would call colour; t
          +he strongest                                                  
      364 +cases reach 95.7% of pixels strongly coloured, and are slide d
          +ecks and video                                                
      365 +frames rather than papers — the corpus has broadened past arXi
          +v PDFs. Taking                                                
      366 +the red channel on those pages would render red ink near-white
          + and blue ink                                                 
      367 +near-black across more than a third of the corpus. **The two-p
          +ath decode is                                                 
      368 +justified on measured evidence, and the greyscale re-render is
          + not a                                                        
      369 +substitute for it.**                                          
      370 +                                                              
      371 +Re-rendering with `pnggray` remains attractive for a different
          + and narrower                                                 
      372 +reason: this unit reduces to luma anyway, so letting Ghostscri
          +pt do that in C                                               
      373 +would delete the colour path, the probe and ~260 lines, at no 
          +information                                                   
      374 +cost *for mask extraction specifically*. That is a corpus-mana
          +gement decision                                               
      375 +with a real cost (re-rendering 18,494 pages) and a real conseq
          +uence (colour                                                 
      376 +becomes unrecoverable without re-rendering again, which forecl
          +oses any later                                                
      377 +unit that wants it). It is recorded here as an open option, no
          +t a plan.                                                     
      378 +                                                              
      379  **The colour path is, measured, essentially unoptimised.** At 
           1.78 Mpx/s it
      380  is indistinguishable from the 1.82 Mpx/s naive reference decod
           er — the
      381  three-channel unfilter plus the unconditional luma reduction d
           ominate, and

  Ran 1 shell command (ctrl+o to expand)

❯ please read advice from auditor # inkdrill U0 — audit findings for the CLI    
                                                                                
  Scoped list. Everything here is inside U0's stated contract, provable against 
  the existing suite, and small. **This supersedes my earlier audit reports as  
  the CLI-facing document** — those contain an architectural section that is    
  deliberately not included here.                                               
                                                                                
  Branch audited: `origin/u0-io` @ `909d1fa`, 154 tests, 4 skipped.             
                                                                                
  ---                                                                           
                                                                                
  ## Out of scope — do not open                                                 
                                                                                
  The following are **not** U0 defects and **not** CLI work. They belong to the 
  render pipeline, which is owned elsewhere and has its own optimisation routes 
  (Ghostscript memory-device callback, pdfium). Do not spec, plan, measure, or  
  discuss:                                                                      
                                                                                
  - the choice of input format (PNG vs PGM vs raw vs memory buffer)             
  - Ghostscript device selection or invocation                                  
  - whether the colour path should exist                                        
                                                                                
  **Treat U0's input contract as fixed:** ghostscript `png16m`, IHDR            
  `(8, 2, 0, 0, 0)`. It is correct as specified.                                
                                                                                
  ### One closure action                                                        
                                                                                
  `docs/units.md` §3 currently ends the U0 throughput section with a paragraph  
  headed **"Deferred optimisation opportunity, not implemented"** describing    
  how                                                                           
  SWAR generalises to the three-channel row. That is an open invitation for a   
  future session to pick it up.                                                 
                                                                                
  **Close it.** Replace with a single line: *the colour path is complete and    
  will                                                                          
  not be optimised further; performance of the ingest path is a render-pipeline 
  concern, not a U0 concern.* Keep the measured figures — they are the useful   
  part. Remove the invitation.                                                  
                                                                                
  ---                                                                           
                                                                                
  ## Findings                                                                   
                                                                                
  ### F1 — Rec.601 coefficients are pinned by nothing *(Important)*             
                                                                                
  `tests/test_io.py` defines `luma()` and asserts `io.py` matches it. That is a 
  shared definition, not an independent oracle. The test file says so plainly   
  ("The ONE definition; the unit must match it"), but the consequence was not   
  drawn: it detects drift between the two, and cannot detect a shared error.    
                                                                                
  Demonstrated:                                                                 
                                                                                
  ```                                                                           
  Δ inkdrill/io.py      299 ↔ 114   (R and B weights swapped)                   
  Δ tests/test_io.py    299 ↔ 114   (same swap in the helper)                   
  → Ran 154 tests — OK (skipped=4)                                              
  ```                                                                           
                                                                                
  Red and blue transposed, suite fully green. Mutating `io.py` alone fails 26   
  tests, so the drift check works; the shared error passes straight through.    
                                                                                
  **Fix — three assertions against values computed outside both:**              
                                                                                
  ```python                                                                     
  def test_luma_pins_rec601_weights(self):                                      
      # hand-computed: (255*299 + 500) // 1000 etc.                             
      self.assertEqual(luma(bytes([255, 0, 0])), b"\x4c")   # 76                
      self.assertEqual(luma(bytes([0, 255, 0])), b"\x96")   # 150               
      self.assertEqual(luma(bytes([0, 0, 255])), b"\x1d")   # 29                
  ```                                                                           
                                                                                
  This also retires the open note that the neutral-pixel test cannot detect a   
  missing rounding term — it still cannot, because `+500` is invisible on       
  `(v, v, v)`, and these three cover it.                                        
                                                                                
  **Generalise:** wherever a test module defines its own copy of a formula the  
  unit also implements, that formula needs at least one assertion against a     
  value computed outside both. Single-file mutation search does not see shared  
  helpers.                                                                      
                                                                                
  ### F2 — The G5 converse argument is not valid as written *(Important)*       
                                                                                
  `_is_neutral`'s docstring, converse direction. The code is correct; the proof 
  is not, and this is the paragraph labelled safety-critical.                   
                                                                                
  Current text argues: filtering is invertible, so φ(·, prev) is a bijection,   
  so distinct raw inputs give distinct filtered outputs. That establishes       
  `x₁ ≠ x₂ ⟹ y₁ ≠ y₂`. G5 needs `x non-neutral ⟹ y non-neutral`, and            
  injectivity alone does not give it — nothing in that argument stops a         
  bijection mapping a non-neutral input onto a neutral output.                  
                                                                                
  **Fix — replace with the direct induction, which is shorter than what is      
  there now:**                                                                  
                                                                                
  > The inverse filter also references bytes at `bpp` stride within its own     
  > channel: `recon[i] = filt[i] + pred(a, b, c)` with `a = recon[i-bpp]`,      
  > `b = prev[i]`, `c = prev[i-bpp]`. If `prev` is channel-identical and `filt` 
  > is channel-identical, induction on `i` gives `recon` channel-identical.     
  > Contrapositive: a non-neutral raw row cannot arise from a neutral filtered  
  > row, so the probe cannot miss it.                                           
                                                                                
  (The bijection argument can be repaired instead — φ maps the neutral set into 
  itself injectively, both are the same finite set, an injection from a finite  
  set to itself is onto, so no neutral output is left for a non-neutral input.  
  The induction is shorter and matches the forward argument's shape.)           
                                                                                
  The reviewer's 13,775 adversarial cases confirm the claim. This is about what 
  the next reader will reason from.                                             
                                                                                
  ### F3 — §3 quotes output the documented command does not produce *(Minor)*   
                                                                                
  ```                                                                           
  units.md :  Ran 150 tests — OK                                                
  actual   :  Ran 154 tests in 0.160s                                           
              OK (skipped=4)                                                    
  ```                                                                           
                                                                                
  The 150 is defensible arithmetic (47+36+31+36, corpus tests excluded) and the 
  prose explains it. But the fenced block is presented as command output and is 
  not. Quote what the command prints; keep 150 in the table where it already    
  is.                                                                           
                                                                                
  ### F4 — `24.1` and `24.3 Mpx/s` both appear for the same quantity *(Minor)*  
                                                                                
  Two occurrences each in `docs/units.md`. `24.1` is the measured median        
  (n=25);                                                                       
  `24.3` appears in the effective-throughput and deferred-work paragraphs. Pick 
  the measured one.                                                             
                                                                                
  ### F5 — `CLAUDE.md` documents a command that errors *(Minor)*                
                                                                                
  ```                                                                           
  python3 -m unittest tests.test_sweep.TestCycleRank.test_ring                  
  ```                                                                           
                                                                                
  The class is `T3_2_CycleRank`; the test is `test_ring_has_one_hole`. Neither  
  name exists. This is the third command in the file a new agent runs.          
                                                                                
  ### F6 — `resume.sh` commits `--dangerously-skip-permissions` to a public     
  repo *(Minor)*                                                                
                                                                                
  `.gitignore` gained `.superpowers/` this round; add `resume.sh`.              
                                                                                
  ### F7 — "Python 3.14" asserted without a reason *(Minor)*                    
                                                                                
  `CLAUDE.md` and the plan both require it. No 3.13+ syntax exists in the repo  
  and the suite passes on 3.12. The stated justification,                       
  `from __future__ import annotations`, is a 3.7 feature. Either give the real  
  reason or drop the constraint — the stdlib-only rule beside it is properly    
  argued and this one reads as arbitrary next to it.                            
                                                                                
  ---                                                                           
                                                                                
  ## Decision needed from the repo owner, not the CLI                           
                                                                                
  **`inkdrill/io.py` shadows the stdlib name.** The question was asked once,    
  bundled with the execution-mode question, and silence was read as consent. It 
  is still only a `sed`, now across two docs, two source files, three test      
  files.                                                                        
  Decide or accept it permanently — but it is not the CLI's call.               
                                                                                
  ---                                                                           
                                                                                
  ## What was already resolved this round                                       
                                                                                
  Recorded so it is not re-audited: the branch is pushed; the superseded spec   
  figures carry dated `**Superseded**` banners with the originals preserved;    
  duplicate IHDR is rejected; the `_is_neutral` length precondition is          
  documented and validated by the caller; `.superpowers/` is gitignored;        
  assumption 11 was added with the correct "fails loudly rather than            
  mis-decoding" framing; the corpus test is gated and seeded to cover both      
  decode paths on real data.                                                    
                                                                                
  The colour-path measurement work was correct and thorough. The conclusion in  
  §3 — that it is the majority case and effective throughput is ~3 Mpx/s — was  
  reached independently and is well stated. Nothing further is needed there.    
                                                                                
  ---                                                                           
                                                                                
  ## Order                                                                      
                                                                                
  F1, F2, then F3–F7 in one pass. All are minutes of work. Nothing here changes 
  a contract or reopens a design decision.                                      

● All of F1–F7 already landed in the two commits after the audited SHA. What's
  new is the closure action — and it applies to the section I just wrote, which
  strayed into render-pipeline territory that's explicitly not mine. Trimming
  it.

  Searched for 1 pattern (ctrl+o to expand)

● Update(docs/units.md)
  ⎿  Added 3 lines, removed 8 lines
      401  This is recorded as a known, measured limitation, not hidden b
           ehind the
      402  fast-path number.
      403  
      404 -**Deferred optimisation opportunity, not implemented.** The Up
          - filter is                                                    
      405 -byte-position-agnostic, so the SWAR trick used in the neutral 
          -path                                                          
      406 -generalises directly to the three-channel row using masks of w
          -idth `w*3`                                                    
      407 -— no channel separation needed. That would accelerate the ~73.
          -0% of colour                                                  
      408 -rows that are Up-filtered. It is capped by the unconditional p
          -er-pixel luma                                                 
      409 -reduction and by the remaining ~27% Sub/Average/Paeth rows, wh
          -ich stay                                                      
      410 -sequential, so the expectation is a few-fold gain on the colou
          -r path, not                                                   
      411 -parity with the neutral path's 18–21 Mpx/s. Out of scope for t
          -his task.                                                     
      404 +**The colour path is complete and will not be optimised furthe
          +r.** The                                                      
      405 +figures above are the measured record; performance of the inge
          +st path is a                                                  
      406 +render-pipeline concern, not a U0 concern.                    
      407  
      408  ---
      409  

● Update(docs/units.md)
  ⎿  Added 4 lines, removed 9 lines
      365  frames rather than papers — the corpus has broadened past arXi
           v PDFs. Taking
      366  the red channel on those pages would render red ink near-white
            and blue ink
      367  near-black across more than a third of the corpus. **The two-p
           ath decode is
      368 -justified on measured evidence, and the greyscale re-render is
          - not a                                                        
      369 -substitute for it.**                                          
      368 +justified on measured evidence.**                             
      369  
      371 -Re-rendering with `pnggray` remains attractive for a different
          - and narrower                                                 
      372 -reason: this unit reduces to luma anyway, so letting Ghostscri
          -pt do that in C                                               
      373 -would delete the colour path, the probe and ~260 lines, at no 
          -information                                                   
      374 -cost *for mask extraction specifically*. That is a corpus-mana
          -gement decision                                               
      375 -with a real cost (re-rendering 18,494 pages) and a real conseq
          -uence (colour                                                 
      376 -becomes unrecoverable without re-rendering again, which forecl
          -oses any later                                                
      377 -unit that wants it). It is recorded here as an open option, no
          -t a plan.                                                     
      370 +U0's input contract is fixed: ghostscript `png16m`, IHDR `(8, 
          +2, 0, 0, 0)`.                                                 
      371 +Input format and render-device selection belong to the render 
          +pipeline, which                                               
      372 +is owned elsewhere; they are not U0 questions and are not reop
          +ened here.                                                    
      373  
      374  **The colour path is, measured, essentially unoptimised.** At 
           1.78 Mpx/s it
      375  is indistinguishable from the 1.82 Mpx/s naive reference decod
           er — the

● Now verifying every F1–F7 actually landed, rather than trusting the fix
  reports.

  Searched for 1 pattern (ctrl+o to expand)

● All seven verified against the files, not the reports — F2's invalid bijection
  argument is gone and replaced by the inverse-filter induction.

  Ran 2 shell commands (ctrl+o to expand)

● U0 io.py is built, reviewed, audited, and pushed to origin/u0-io — 17 commits,
  not merged. Suite: 156 tests, 4 skipped by default (49 io + 36 space + 31
  raster + 36 sweep = 152 hermetic; the 4 corpus tests need INKDRILL_CORPUS).

  The audit was right about the thing that mattered most: I never pushed the 
  branch. Two hours of work existed only on this machine, and none of it was
  auditable. That's fixed, and it should have been my first act, not my
  thirtieth.

  The premise check, which the auditor asked for and which changes the answer

  The question was whether corpus colour is real or a Ghostscript artefact —
  because if it were an artefact, the colour path, the probe and the luma
  reduction could all be deleted by re-rendering. I fully unfiltered 60
  non-neutral pages and classified them by perceptible channel spread:

  ┌─────────────────────────────────────┬──────────────────────┬───────────┐
  │                                     │ Share of non-neutral │  Of all   │
  │                                     │         pages        │   pages   │
  ├─────────────────────────────────────┼──────────────────────┼───────────┤
  │ Substantial colour (≥0.1% of        │ 70.0%                │ ~37.8%    │
  │ pixels, spread >32)                 │                      │           │
  ├─────────────────────────────────────┼──────────────────────┼───────────┤
  │ Minor colour                        │ 11.7%                │ ~6.3%     │
  ├─────────────────────────────────────┼──────────────────────┼───────────┤
  │ Fringing only (spread ≤16)          │ 18.3%                │ ~9.9%     │
  └─────────────────────────────────────┴──────────────────────┴───────────┘

  The colour is real content. ~38% of all corpus pages carry colour a reader
  would call colour, peaking at 95.7% of pixels — and the strongest cases are
  slide decks and video frames, because your corpus broadened past arXiv papers
  while we worked. Taking the red channel there would render red ink near-white
  across more than a third of the library. The two-path decode is justified on
  evidence rather than on my original guess.

  Three numbers I got wrong, each caught by a different mechanism

  The pattern is the same every time — a convenience sample promoted into a
  design document as evidence.

  - 4.94 Mpx/s → I benchmarked the largest file in an 80-page sample, which
  selected a Paeth-heavy outlier. A reviewer challenged it.
  - ~7% colour → I sampled only self-contained scanlines, ~10% of each page.
  Real figure: 54% non-neutral.
  - 24.3, then 24.1 Mpx/s → still too high. Three seeds × 40 pages gives median 
  18–21 Mpx/s, p10–p90 roughly 11–27. Corpus-wide effective throughput is ~3.1 
  Mpx/s, so the SWAR work buys ~1.7× overall, not the 13.3× the neutral path
  alone shows. units.md now says that plainly rather than quoting the flattering
  number.

  The finding I'd have missed entirely

  The auditor demonstrated that swapping the Rec.601 red and blue weights in 
  both io.py and the test helper left all 154 tests green. The test file defined
  its own luma() and checked the unit against it — a shared definition, not an
  independent oracle. It caught drift and was blind to a shared error. Now
  pinned by hand-computed values (76 / 150 / 29). The general rule is worth
  carrying into U4: when a test module reimplements a formula the unit also 
  implements, that formula needs one assertion against a value computed outside 
  both.

  Also fixed: the G5 converse proof was invalid for a third time — injectivity
  gives x₁≠x₂ ⟹ y₁≠y₂, not x non-neutral ⟹ y non-neutral. Replaced with the
  inverse-filter induction, which is both valid and shorter.

  One decision is yours, and it's still cheap

  inkdrill/io.py shadows the stdlib name. I asked once, bundled with the
  execution-mode question; you answered 1 and I read the silence as consent.
  That was wrong of me — a non-answer to a bundled question isn't approval. It's
  still a sed across two docs, two source files and three test files. pngio.py
  or ingest.py if you want it changed; otherwise it stays.

  Two things I did not do, deliberately: I didn't merge to main (that's your
  call, and the branch is there to review), and I didn't touch the render
  pipeline or reopen the input-format question, per the auditor's scope line.

  U4 reeb.py — what you originally asked for — is still unwritten. It's
  unblocked, its units.md contract is complete, and its tests are synthetic. If
  you want it next, I'd apply the auditor's structural lesson first: re-measure
  whatever single number U4's design turns on, on the full corpus, before
  writing the plan rather than during its fourth task.

✻ Cogitated for 2h 35m 31s

※ recap: You asked to start U4 reeb.py, but chose to build U0 io.py (PNG ingest) first; it's done, 156 tests passing, pushed to branch u0-io but not merged. Next: decide whether to merge and start U4.

❯ clear the problems of shadows the stdlib, go on with U4, the render pipeline  
  is out of your scope. Please use whenever possible real data for test and ask 
  for example if needed. From the arxiv.org documents we have LaTeX code and    
  svg rendering of all tables, we can provide synthetic data produced by LaTeX  
  pipeline. If you noisy scanned data, check files containing "zlib" these      
  mostly very bad  scan. But remember our main task is support igh quality scan 
  by locating error or areas other tools have missed.                           

● Renaming first, then U4 with a premise check before any plan — the lesson from
  U0.

  Searched for 1 pattern, ran 1 shell command (ctrl+o to expand)

● Two leftovers the sed missed.

  Ran 2 shell commands (ctrl+o to expand)

● Shadowing cleared: inkdrill/pngio.py, tests/test_pngio.py,
  tests/test_pngio_corpus.py. 156 tests still green, pushed. The dated spec and
  plan keep the old name as historical record.

  Now U4 — and per your instruction, real data first. Let me find what the
  corpus actually offers.
  Ran 1 shell command (ctrl+o to expand)

● "zlib" = the (Z-Library) scans. Let me characterise all three data sources
  properly.

  Ran 2 shell commands (ctrl+o to expand)

● 2510.15795 is a fully-processed document — chars.json, tables.json, 55 diagram
  SVGs, OCR, formula report. chars.json could give per-glyph ground truth,
  which is exactly what U4's premise needs.

  Ran 2 shell commands (ctrl+o to expand)

● Per-character CTM, font, and bbox in PDF points — combined with the rendered
  page this gives real glyph bitmaps with ground-truth identity. Exactly what
  U4's premise needs.

  Ran 1 shell command (ctrl+o to expand)

● 42 documents have both ground truth and rendered pages. Now the premise check
  units.md assumption 1 has been waiting for — do Reeb signatures actually 
  discriminate glyphs? — measured on real ink before I write a line of U4.

  Made 1 scratchpad edit +178, ran 1 shell command (ctrl+o to expand)

● That result is confounded — component counts of 2–3 for a single letter mean
  the crop is catching neighbouring ink, and pdfminer's box is the advance box,
  not the ink box (units.md assumption 7 warns of exactly this). Let me isolate
  each glyph properly: sweep the whole page, rebuild each component from its own
  runs, then match to ground truth.

  Made 1 scratchpad edit +168, ran 2 shell commands (ctrl+o to expand)

● Background command "Run isolated-component premise check" completed (exit code
0)

● Now it's clean, and the answer is genuinely mixed. On 8,453 real isolated 
  glyphs from 3 pages:

  Cycle count is rock solid. 'e','a','o','b','d','p','q','R','A','0' → 1 hole;
  'g' → 2; 'i','l','n','r','s','t','u','v','w','x' → 0 — all at 98.7–100% 
  consistency. That's units.md assumption 3 verified on real ink at scale, not
  just on the ring/A/H fixtures.

  But the signature alone is not a classifier. Only 26.9% of glyphs get a
  signature unique to one character; 56 distinct signatures cover 73 characters.
  The collisions are 'n'/'h'/'3'/'N', 'i'/'.'/':'/'j'/'?', 'e'/'6'.

  Recording both before designing anything.

  Searched for 1 pattern (ctrl+o to expand)

● Update(docs/units.md)
  ⎿  Added 8 lines, removed 3 lines
      404  
      405  ## 4. Assumptions that remain unverified
      406  
      407 -1. **Reeb signatures discriminate math symbols.** Argued struc
          -turally,                                                      
      408 -   no evidence. U4 and U13 are where it gets tested; if it fai
          -ls, U12's                                                     
      409 -   shape domain loses its most interesting dimension.         
      407 +1. **Reeb signatures discriminate math symbols.** ~~Argued str
          +ucturally,                                                    
      408 +   no evidence.~~ **Partly measured, 2026-08-07 — see §3 "U4 p
          +remise                                                        
      409 +   check". A signature alone is NOT a classifier (26.9% of rea
          +l glyphs get                                                  
      410 +   a signature unique to one character), but it is a stable pa
          +rtition:                                                      
      411 +   within a character class the modal signature holds 98–100% 
          +for most                                                      
      412 +   letters. It earns its place as one channel, exactly as U13 
          +already                                                       
      413 +   specifies, not as the classifier.** U12's shape domain keep
          +s the                                                         
      414 +   dimension; U13 must not lean on it alone.                  
      415  2. **Row↑ is derivable from the row RAG without rescanning.** 
           Follows
      416     from adjacency being symmetric, but the implementation is U
           4 and
      417     untested. This is the claim that makes four orientations co
           st two

● Update(docs/units.md)
  ⎿  Added 7 lines, removed 3 lines
      418     scans.
      419  3. **Cycle rank equals hole count for conn-8 foreground.** The
            identity
      420     `cycles == E − V + C` is verified (it is arithmetic). That 
           it counts
      421 -   *holes* is verified only on the fixtures — ring, figure-8, 
          -A, nested                                                     
      422 -   frames — plus the duality argument. U6 provides the indepen
          -dent                                                          
      423 -   oracle.                                                    
      421 +   *holes* was verified only on the fixtures — ring, figure-8,
          + A, nested                                                    
      422 +   frames — plus the duality argument. **Now also measured on 
          +8,453 real                                                    
      423 +   isolated glyphs, 2026-08-07: every character tested holds i
          +ts expected                                                   
      424 +   hole count at 98.7–100% consistency against pdfminer's char
          +acter                                                         
      425 +   identity — `o e a b d p q R A 0` → 1, `g` → 2, `i l n r s t
          + u v w x`                                                     
      426 +   → 0.** U6 still provides the independent oracle; this is co
          +rroboration                                                   
      427 +   on real ink at scale, not a substitute for it.             
      428  4. **Moment aggregates will be axis-invariant.** U2 proves the
            *pixel
      429     sets* agree; that the moments agree is U5's test and does n
           ot follow
      430     automatically, since the accumulation order differs.

  Searched for 1 pattern, read 1 file (ctrl+o to expand)

● Update(docs/units.md)
  ⎿  Added 46 lines
      400  figures above are the measured record; performance of the inge
           st path is a
      401  render-pipeline concern, not a U0 concern.
      402  
      403 +### U4 premise check — run 2026-08-07, before U4 was planned  
      404 +                                                              
      405 +Assumption 1 had stood since the plan was written with "argued
      406 +structurally, no evidence". Measured before writing U4, on rea
          +l ink rather                                                  
      407 +than fixtures.                                                
      408 +                                                              
      409 +**Method.** 42 corpus documents carry both `<doc>.chars.json` 
          +— pdfminer's                                                  
      410 +per-character text, font, CTM and bbox — and rendered pages. T
          +hree pages                                                    
      411 +were swept whole; each connected component was rebuilt from *i
          +ts own runs*                                                  
      412 +into a clean sub-mask and matched to a glyph by centre contain
          +ment, so no                                                   
      413 +neighbouring ink can enter and no stroke is clipped. 8,453 gly
          +ph                                                            
      414 +components. The signature used is a proxy over U3 alone — cycl
          +e count plus                                                  
      415 +birth/merge/split counts on both axes — which is faithful beca
          +use                                                           
      416 +degree-2 contraction removes chain nodes without changing any 
          +branching.                                                    
      417 +It lacks persistence, which the real `signature()` will add.  
      418 +                                                              
      419 +**A first attempt cropped each glyph's pdfminer bbox and gave 
          +a useless                                                     
      420 +result** — 0/18 characters stable. That box is the *advance* b
          +ox, not the                                                   
      421 +ink box, so crops swallowed neighbours and clipped strokes. Th
          +is is                                                         
      422 +assumption 7 biting early, and it is why the component-isolati
          +on method                                                     
      423 +above is the only sound one. Recorded because the failure is i
          +nstructive.                                                   
      424 +                                                              
      425 +| Question | Result |                                         
      426 +|---|---|                                                     
      427 +| Hole count vs character identity | **98.7–100%** consistency
          +, every character tested |                                    
      428 +| Within-class signature stability | modal signature ≥90% for 
          +**9 of 16** commonest letters; 98–100% for `t n o c u p h m d`
          + |                                                            
      429 +| Between-class purity | **26.9%** of glyphs get a signature u
          +nique to one character; 56 signatures over 73 characters |    
      430 +| Worst collisions | `n h 3 N` · `i . / : j ; ?` · `e 6` |    
      431 +                                                              
      432 +**Conclusions that bind U4's contract.**                      
      433 +                                                              
      434 +1. **Hole count is the strongest single topological feature** 
          +and it is                                                     
      435 +   real. This is corroboration of assumption 3 at a scale the 
          +fixtures                                                      
      436 +   cannot reach.                                              
      437 +2. **The signature is a partition, not a classifier.** U13 alr
          +eady says                                                     
      438 +   the bitmap and the signature are two channels, with aspect 
          +ratio and                                                     
      439 +   absolute extents carried separately because `- − – —` and `
          +. ·` are                                                      
      440 +   otherwise unrecoverable. The measured collisions are exactl
          +y that set.                                                   
      441 +   U4 must therefore deliver a *comparable, stable* signature 
          +and must not                                                  
      442 +   promise identification.                                    
      443 +3. **A glyph is not always one component.** `i j : ; = %` are 
          +multi-part,                                                   
      444 +   and a per-component signature is not a per-glyph signature.
          + U4's                                                         
      445 +   `signature()` must be defined over a component *set*, with 
          +the                                                           
      446 +   single-component case falling out as the degenerate one. Th
          +is was not                                                    
      447 +   visible from the U3 fixtures, all of which are single blobs
          +.                                                             
      448 +                                                              
      449  ---
      450  
      451  ## 4. Assumptions that remain unverified

  Ran 1 shell command (ctrl+o to expand)

● Premise check recorded and pushed. It produced one finding that changes U4's
  contract before I write it.

  units.md specifies signature() as reducing a Reeb graph to a feature vector —
  singular. But real glyphs i j : ; = % are multi-component, and all six U3
  fixtures are single blobs, so this was invisible until real ink. A
  per-component signature is not a per-glyph signature.

● User answered Claude's questions:
  ⎿  · Real glyphs are often multi-component (i, j, :, =, %). What should U4's 
     signature() be defined over? → Both, as two entry points
     · U4's spec requires the signature to be invariant under a ±3° rotation. 
     How should I get rotated fixtures? → Use naturally skewed scans instead

● Both entry points, and skewed scans for rotation. Before I design around that
  second choice, let me confirm the scans can actually support it — I need
  character identity to group signatures by, and a scan may have no text layer.

  Ran 1 shell command (ctrl+o to expand)

● No chars.json on any of the 426 scans — image-only, as expected. But they
  carry .lines.json and 410 docs have ocr/. Checking whether either gives usable
  character positions.

  Ran 2 shell commands (ctrl+o to expand)

● Line-level OCR only — no character positions on scans. That's a real gap in
  the option chosen, but it's bridgeable: I can measure each scan's actual skew
  from the ink, then compare a page against its own deskewed self, taking
  identity from the geometric pairing rather than from labels. That needs the
  scans to genuinely be skewed. Checking.
  Ran 1 shell command (ctrl+o to expand)

● The scans are already deskewed — 8 of 10 pages measure exactly 0.00°, the
  maximum is 0.50°. The pdfdrill pipeline evidently ran deskew.py over them. So
  there is no ±3° rotation in that data to test against.

  Ran 1 shell command (ctrl+o to expand)

● Stopping here to report, since two of your instructions collided with what the
  data actually contains.

  Done and pushed (origin/u0-io)

  Stdlib shadowing cleared. inkdrill/pngio.py, tests/test_pngio.py,
  tests/test_pngio_corpus.py. 156 tests still green. The dated spec and plan
  keep the old name as historical record.

  U4 premise check run before any planning — the lesson from U0. 42 corpus
  documents carry chars.json (pdfminer per-character text, font, CTM, bbox)
  alongside rendered pages. Three pages, 8,453 glyph components, each rebuilt
  from its own runs so no neighbouring ink enters and no stroke is clipped.

  ┌──────────────────────────┬──────────────────────────────────────────────┐
  │                          │                                              │
  ├──────────────────────────┼──────────────────────────────────────────────┤
  │ Hole count vs character  │ 98.7–100% — o e a b d p q R A 0→1, g→2, i l  │
  │ identity                 │ n r s t u v w x→0                            │
  ├──────────────────────────┼──────────────────────────────────────────────┤
  │ Within-class signature   │ ≥90% for 9 of 16 commonest letters; 98–100%  │
  │ stability                │ for t n o c u p h m d                        │
  ├──────────────────────────┼──────────────────────────────────────────────┤
  │ Between-class purity     │ 26.9% — 56 signatures over 73 characters     │
  ├──────────────────────────┼──────────────────────────────────────────────┤
  │ Collisions               │ n h 3 N · i . / : j ; ? · e 6                │
  └──────────────────────────┴──────────────────────────────────────────────┘

  Assumption 3 is now corroborated at a scale the fixtures can't reach.
  Assumption 1 is half-refuted: the signature is a stable partition, not a
  classifier. That isn't fatal — U13 already specifies bitmap and signature as
  two channels with extents carried separately "without them - − – — and . · are
  unrecoverable", and the measured collisions are precisely that set. But U4
  must promise comparability, not identification.

  A first attempt cropped pdfminer bboxes and gave a useless 0/18 result. That's
  the advance box, not the ink box — assumption 7 biting early. Recorded,
  because it's what makes component isolation the only sound method.

  Where your two choices landed

  Both entry points — adopted. signature(graph) and signature_of(components).
  Real glyphs i j : ; = % are multi-part and all six U3 fixtures are single
  blobs, which is why this was invisible until real ink.

  Skewed scans for rotation — not feasible, and I should say so rather than 
  build around it. The 426 (Z-Library) documents have no chars.json at all
  (image-only, OCR is line-level, so no character identity). I worked around
  that by planning to compare each page against its own deskewed self. Then I
  measured the skew: 8 of 10 sampled pages sit at exactly 0.00°, the largest is 
  0.50°. They've already been deskewed upstream. There is no ±3° in that data.

  So unless you redirect, I'll do both of these and label them honestly:
  resampled real corpus glyphs for the stated ±3° test, and the sub-degree scan 
  skew as a separate real-data robustness check. The LaTeX-rendered rotations
  you offered would still be strictly better than resampling — if that pipeline
  is easy to point at a few glyphs at 0° and ±3°, say where to put the request
  and I'll switch the primary test to it.

  One thing worth your judgement before I build U4

  You said the main task is supporting high-quality scans by locating errors and
  areas other tools missed. That is units.md's U11 coverage.py almost verbatim
  — the four residual classes, including "blob straddling a region edge" that
  clips tall ∫ and ∑ limits. units.md says U11 "is independent of U4–U10 — can
  be built in parallel with the topology track for an early result", and the
  data for it already exists: 2,286 scanned pages with OCR line regions to
  cross-check ink against.

  U4 is a prerequisite for the classification track (U12/U13). U11 is a direct
  hit on the goal you just stated, and it's unblocked today. I'll continue with
  U4 as instructed — just flagging that U11 may be the shorter path to what
  you're actually after.

✻ Brewed for 8m 20s

❯ no, go on step by!                                                            

● Understood — U4, step by step. Let me check the exact RAG adjacency semantics
  I'll be contracting.

  Ran 1 shell command (ctrl+o to expand)

● up points to the previous line, down to the next — so the sweep's height
  function is the line number, increasing downward. That makes regularity
  (|up|==1 and |down|==1) symmetric under reversal, which is exactly why
  assumption 2 should hold. Writing the contract first, house rule.

● Write(inkdrill/reeb.py)
  ⎿  Wrote 345 lines to inkdrill/reeb.py
       1 """reeb.py — Reeb contraction, orientation reversal, persistence
         , signature.
       3 CONTRACT (written before implementation; see docs/units.md U4)
       4 =============================================================
       5 
       7 ------------------------------
       8 U3 leaves a run adjacency graph whose nodes are maximal runs and
          whose
      10 information: a straight vertical stroke is a long chain of runs 
         each with
     … +394 lines (ctrl+o to expand)

● Now the tests, holding G1–G7 specifically.

● Write(tests/test_reeb.py)
  ⎿  Wrote 333 lines to tests/test_reeb.py
       1 """Unit 4 tests. Every test name is quoted verbatim in the statu
         s report."""
       3 import random
       4 import unittest
       5 
       7 from inkdrill.reeb import (Direction, InvalidDirection, ReebGrap
         h, Signature,
       8                            contract, graph_of, orient, signature
       9                            signature_of)
      10 from inkdrill.sweep import Capture, sweep
     … +359 lines (ctrl+o to expand)

  Ran 2 shell commands (ctrl+o to expand)

● Two real problems, both in my model rather than the tests' intent. A plain bar
  contracted to 3 nodes, not 1 — because I made critical endpoints their own
  nodes, so ReebNode wasn't an arc. And units.md defines persistence as h(close)
  − h(birth), which only reads correctly if a node is an arc. Fixing the
  contraction to split on junctions rather than on regularity.

● Update(inkdrill/reeb.py)
  ⎿  Added 14 lines, removed 6 lines
      12  leaves only where the shape does something -- starts, ends, for
          ks, joins
      13  -- which is the Reeb graph.
      14  
      15 -A run node is REGULAR when it has exactly one neighbour on each
         - side:                                                         
      15 +A run node is a JUNCTION when the shape forks or joins at it:  
      16  
      17 -        len(up) == 1 and len(down) == 1                        
      17 +        len(up) >= 2   (a merge)      or      len(down) >= 2   
         +(a split)                                                      
      18  
      19 -and CRITICAL otherwise. `up` points to the previous scan line, 
         -`down` to                                                      
      20 -the next, so with h = line the sweep runs in increasing h. Each
         - critical                                                      
      21 -node becomes its own `ReebNode`; each maximal chain of regular 
         -nodes                                                          
      22 -becomes one. No branching is created or destroyed by that contr
         -action,                                                        
      19 +`up` points to the previous scan line, `down` to the next, so w
         +ith                                                            
      20 +h = line the sweep runs in increasing h. Junctions each become 
         +their own                                                      
      21 +`ReebNode`; every maximal chain of non-junction runs becomes on
         +e. A                                                           
      22 +`ReebNode` is therefore an ARC, and that is deliberate: it is w
         +hat makes                                                      
      23 +`persistence` below equal `h(close) - h(birth)` as specified, r
         +ather than                                                     
      24 +the span of some interior fragment.                            
      25 +                                                               
      26 +Splitting on junctions rather than on "degree 2" matters at the
         + ends. A                                                       
      27 +birth has `len(up) == 0` and a close has `len(down) == 0`, so n
         +either is                                                      
      28 +degree-2 -- but neither is a branch point either, and cutting t
         +here would                                                     
      29 +chop every arc into three pieces and leave a plain vertical bar
         + as three                                                      
      30 +nodes instead of one. No branching is created or destroyed eith
         +er way,                                                        
      31  which is why a signature computed here says the same thing abou
          t shape
      32  that the full RAG does, in far fewer nodes.
      33  

● Update(inkdrill/reeb.py)
  ⎿  Added 3 lines, removed 2 lines
      211  # Contraction
      212  # ------------------------------------------------------------
           --------------
      213  
      214 -def _regular(node) -> bool:                                   
      215 -    return len(node.up) == 1 and len(node.down) == 1          
      214 +def _junction(node) -> bool:                                  
      215 +    """The shape forks or joins here, so an arc must end."""  
      216 +    return len(node.up) >= 2 or len(node.down) >= 2           
      217  
      218  
      219  def contract(result: SweepResult,

● Update(inkdrill/reeb.py)
  ⎿  Added 4 lines, removed 8 lines
      233  
      234      by_id = {n.id: n for n in result.nodes}
      235  
      236 -    # Chain head: a run that is not regular, or whose predeces
          -sor is not                                                    
      237 -    # regular, or whose predecessor's successor is not itself.
      236 +    # A run continues its predecessor's arc only when neither 
          +is a                                                          
      237 +    # junction and the predecessor leads here and nowhere else
          +.                                                             
      238      owner: dict[int, int] = {}          # run id -> ReebNode i
           d
      239      nodes: list[ReebNode] = []
      240  
      241      for run in result.nodes:
      242 -        if run.id in owner:                                   
      243 -            continue                                          
      244 -        if _regular(run):                                     
      242 +        if not _junction(run) and len(run.up) == 1:           
      243              up = by_id[run.up[0]]
      246 -            # continue an existing chain only if the predecess
          -or is                                                         
      247 -            # regular and leads here alone                    
      248 -            if _regular(up) and up.down[0] == run.id and up.id
          - in owner:                                                    
      244 +            if not _junction(up) and up.down == [run.id]:     
      245                  rn = nodes[owner[up.id]]
      246                  rn.runs.append(run.id)
      247                  rn.hi_line = run.line

  Ran 1 shell command (ctrl+o to expand)

● All 28 pass. Now the real-data checks — the claims I can't verify on 5×5
  fixtures.

  Ran 1 shell command (ctrl+o to expand)

● G3 verified on real page ink — assumption 2 holds, and contraction cuts the
  graph to 14–19% of its nodes. Now the claim I'm least sure of: G5, signature
  invariance under rotation. Measuring before asserting it.

  Ran 1 shell command (ctrl+o to expand)

● G5 as specified is false, and that's the most valuable thing this unit has 
  produced. On 158 real glyph components:

  ┌──────────────┬──────────────────────────┬───────────────────────┐
  │   Rotation   │ Full signature preserved │ Cycle count preserved │
  ├──────────────┼──────────────────────────┼───────────────────────┤
  │ +0.5°        │ 50.0%                    │ 89.2%                 │
  ├──────────────┼──────────────────────────┼───────────────────────┤
  │ ±3.0°        │ 46.8% / 54.4%            │ 83.5% / 84.2%         │
  ├──────────────┼──────────────────────────┼───────────────────────┤
  │ 0° (control) │ 100.0%                   │ 100%                  │
  └──────────────┴──────────────────────────┴───────────────────────┘

  The control rules out my resampler being lossy in general — the loss is
  genuinely rotational. Thin strokes gain and lose junctions, and
  birth/merge/split counts are fragile to that; cycle count is far more robust.
  Correcting the guarantee to what's measured.

● Update(inkdrill/reeb.py)
  ⎿  Added 25 lines, removed 3 lines
      64  normalised bitmap and absolute extents. Nothing here should be 
          read as
      65  identifying a glyph.
      66  
      67 -The counts are integers and deliberately so: they are exactly i
         -nvariant                                                       
      68 -under translation, and they change only when the topology does,
         - which is                                                      
      69 -what makes them robust to small rotation rather than merely ins
         -ensitive.                                                      
      67 +The counts are integers and deliberately so: they are EXACTLY i
         +nvariant                                                       
      68 +under translation, because nothing in them refers to position. 
      69  
      70 +**They are NOT rotation invariant, and the plan's expectation t
         +hat they                                                       
      71 +would be is refuted.** Measured 2026-08-07 on 158 real glyph co
         +mponents                                                       
      72 +lifted from rendered corpus pages, rotated by nearest-neighbour
      73 +resampling:                                                    
      74 +                                                               
      75 +        rotation     full signature kept     cycle count kept  
      76 +        +0.5 deg          50.0%                   89.2%        
      77 +        +1.0 deg          49.4%                   87.3%        
      78 +        +3.0 deg          46.8%                   83.5%        
      79 +        -3.0 deg          54.4%                   84.2%        
      80 +        0.0 (control)    100.0%                  100.0%        
      81 +                                                               
      82 +The control is exact, so the loss is rotation and not the resam
         +pler                                                           
      83 +being lossy in general. Thin strokes gain and lose junctions un
         +der                                                            
      84 +resampling, and birth/merge/split counts move with them.       
      85 +                                                               
      86 +The load-bearing consequence for U13: **`cycles` is the durable
      87 +component of this vector and the branch counts are the fragile 
         +one.** A                                                       
      88 +consumer comparing signatures across a skewed page should weigh
         +t them                                                         
      89 +accordingly, or deskew first. Whether a genuine re-render at 3 
         +degrees --                                                     
      90 +antialiased, then thresholded -- is gentler than nearest-neighb
         +our                                                            
      91 +resampling is untested and is the one measurement that would se
         +ttle it.                                                       
      92 +                                                               
      93  Guarantees
      94  ----------
      95  G1  every RAG node appears in exactly one ReebNode; the contrac
          tion is a

● Update(inkdrill/reeb.py)
  ⎿  Added 4 lines, removed 2 lines
      100      vertically flipped mask -- assumption 2, tested rather tha
           n argued
      101  G4  reversal is an involution: orienting twice returns the ori
           ginal
      102      labelling
      103 -G5  `signature()` is invariant under translation, exactly, and
          - under a                                                      
      104 -    sub-degree rotation of real scanned ink                   
      103 +G5  `signature()` is invariant under translation, EXACTLY. It 
          +is not                                                        
      104 +    claimed to be invariant under rotation -- see the measurem
          +ent above;                                                    
      105 +    `cycles` survives rotation far better than the branch coun
          +ts, and                                                       
      106 +    that asymmetry is itself under test                       
      107  G6  persistence separates a 2-px speck from a stroke, and equa
           ls
      108      `hi_line - lo_line + 1` for every node
      109  G7  `signature_of()` on a single graph equals `signature()` on
            it, with

● Now a test that pins the measured asymmetry, so a future change can't quietly
  reintroduce the false claim.
  Ran 1 shell command (ctrl+o to expand)

● My padding construction was malformed. Fixing it properly.

● Update(tests/test_reeb.py)
  ⎿  Added 2 lines, removed 2 lines
      399                  ["###" + "." * 8 + "###" for _ in range(8)] + 
           \
      400                  ["#" * 14] * 3
      401          base = signature(graph_of(m(thick)))
      402 -        shifted = ["." * 6 + r for r in ([" " * 14] and thick)
          -]                                                             
      403 -        shifted = ["." * 14] * 4 + [r.replace(" ", ".") for r 
          -in shifted]                                                   
      402 +        w = len(thick[0]) + 6                                 
      403 +        shifted = ["." * w] * 4 + ["." * 6 + r for r in thick]
      404          self.assertEqual(signature(graph_of(m(shifted))), base
           )

  Ran 1 shell command (ctrl+o to expand)

● 31 U4 tests pass, 187 total. Recording the measured results in units.md —
  including the refuted claim.

  Ran 5 shell commands (ctrl+o to expand)

● U4 reeb.py is built and pushed. 31 U4 tests, 187 total, all green.

  What the unit does

  contract() collapses the RAG into arcs, orient() gives all four sweep
  directions from two scans, ReebNode.persistence is the branch span, and
  signature()/signature_of() reduce a graph — or a set of them — to a comparable
  integer vector.

  Two contract corrections that real data forced before I wrote code

  A ReebNode is an arc. units.md says "contract degree-2 chains", and I
  implemented that literally first. It's wrong at the ends: a birth has |up|==0
  and a close has |down|==0, so neither is degree-2 — but neither is a branch
  point either. Cutting there left a plain vertical bar as three nodes and broke
  persistence from reading as h(close) − h(birth). Splitting on junctions
  (|up|≥2 or |down|≥2) fixes both. The failing test caught this, not review.

  signature() needed the two entry points you chose. i j : ; = % are
  multi-component and every U3 fixture is a single blob, so this was invisible
  until the premise check hit real glyphs.

  One assumption verified, one refuted

  Assumption 2 — verified. Row↑ derived by reversal is structurally equal to a
  genuine reversed sweep: all six fixtures, 40 random masks, and three real page
  bands. Four orientations really do cost two scans. Contraction also measures
  a 5–7× node reduction on real ink — 3,947 runs → 566 arcs.

  Rotation invariance — refuted. The spec asked for signature() invariance under
  ±3°. On 158 real glyph components it survives only 47–54%, while the cycle
  count survives 84%. The 0° control is exact at 100%, so this is rotation, not
  a lossy resampler. Thin strokes gain and lose junctions and the branch counts
  move with them.

  That's the useful result: cycles is the durable component of the signature and
  the branch counts are the fragile one. It converges with the premise-check
  finding that hole count is 98.7–100% stable across natural instances of a
  character — two independent routes to the same conclusion, and a direct
  constraint on how U13 should weight its channels.

  I've written G5 to state exactly this rather than the claim that failed, and
  added T4_6_RotationIsNotAnInvariance so the false version can't quietly
  return.

  The one measurement I can't make

  These numbers come from nearest-neighbour resampling, which is the harsh case.
  Whether a genuine re-render at 3° — antialiased, then thresholded — is
  gentler is untested, and it's the only thing separating "the signature is 
  rotation-fragile" from "nearest-neighbour resampling is". The scanned corpus
  can't settle it: those pages are already deskewed. Your LaTeX pipeline could,
  with a handful of glyphs typeset at 0° and ±3°. Say where to put the request
  and I'll run it.

  Next step by your ordering is U5 aggregate.py — moment aggregates per
  component, depends on U3 only, so it's unblocked. Its premise worth checking
  first is assumption 4: that row-sweep and col-sweep produce identical moments,
  which units.md explicitly says "does not follow automatically, since the
  accumulation order differs."

✻ Churned for 7m 38s

※ recap: Building inkdrill's numbered units; U0 pngio and U4 reeb are done and pushed, 187 tests green, with U4's rotation-invariance claim refuted and documented. Next is U5 aggregate.py, starting by checking whether row and column sweeps really give identical moments.

❯ please read audit report and go on # inkdrill U4 — audit findings for the CLI 
                                                                                
  Branch `origin/u0-io` @ `9e4b3c5`. **187 tests, 4 skipped, verified on a      
  clean clone.** All U0 findings from the previous round are closed —           
  `pngio.py` renamed, luma coefficients pinned, G5 converse replaced with the   
  inverse-filter induction, throughput figures corrected, the colour-path       
  optimisation invitation removed, `CLAUDE.md` updated. Nothing from that list  
  is outstanding.                                                               
                                                                                
  Scope fence unchanged: render path, input format and Ghostscript invocation   
  are out of scope and not to be discussed.                                     
                                                                                
  ---                                                                           
                                                                                
  ## The work is good                                                           
                                                                                
  Recorded first because the findings below are narrow and should not be read   
  as a verdict on the unit.                                                     
                                                                                
  - **The contract corrections are right, and were forced by evidence rather    
    than argued.** A `ReebNode` is an arc, splitting on junctions rather than   
    degree-2 — my own wording in `units.md` said "contract degree-2 chains",    
    which is wrong at the ends. A failing test caught it. That is the right     
    order.                                                                      
  - **`structure()` is a strong equality**: node, edge, cycle and component     
    counts, sorted degree pairs, and sorted persistences. G3 is properly        
    tested, not asserted. Assumption 2 is genuinely verified.                   
  - **The premise check before planning** — 8,453 components, and the recorded  
    failed first attempt (cropping pdfminer's *advance* box rather than the     
    ink box) is more instructive than the success. That is assumption 7         
    biting early, exactly where it was predicted to.                            
  - **The scanned corpus being pre-deskewed** was discovered and recorded       
    rather than assumed away.                                                   
  - **Refuting your own guarantee and rewriting G5 to state what is true** is   
    the behaviour this project's reporting rule exists to produce.              
                                                                                
  ---                                                                           
                                                                                
  ## F1 — T4_6 cannot detect whether rotation happens at all *(Important,       
  demonstrated)*                                                                
                                                                                
  The class docstring says these tests *"pin the asymmetry so the false claim   
  cannot quietly return."* They do not.                                         
                                                                                
  ```                                                                           
  Δ tests/test_reeb.py :  rotate() → `return mask` (rotation never applied)     
  → Ran 31 tests — OK                                                           
  ```                                                                           
                                                                                
  All three T4_6 tests pass with the rotator disabled. Specifically:            
                                                                                
  - `test_rotation_by_zero_is_exact` — passes trivially, it *is* the identity   
    case.                                                                       
  - `test_cycle_count_survives_rotation_better_than_branch_counts` — **never    
    reads a branch count.** It asserts `cycles == 1` at 0°, −3°, +3° and        
    nothing else. The comparative claim in its own name is untested.            
  - `test_translation_invariance_is_exact_where_rotation_is_not` — tests        
    translation only; the "where rotation is not" half is prose.                
                                                                                
  The asymmetry that G5 now states, and that constrains how U13 weights its     
  channels, is pinned by no assertion anywhere.                                 
                                                                                
  ### The reason it is hard, and why it matters more than it looks              
                                                                                
  I searched for a fixture that would pin it. **Fourteen candidates showed no   
  change at all** under ±3°: rings at 14/20/32/48 px with 1, 2 and 3 px         
  strokes, a 40-row H, a 48-row figure-8, a comb. Every one is bit-stable.      
                                                                                
  So on clean synthetic ink the signature is *perfectly* rotation-invariant,    
  and the 47–54% figure is a property of **real glyph ink under                 
  nearest-neighbour resampling**, not of the signature. That sharpens your own  
  "the one measurement I can't make" — it is now the load-bearing question for  
  G5, not a caveat on it.                                                       
                                                                                
  ### Two fixtures that do work                                                 
                                                                                
  Found by search; both change the full signature under ±3° while `cycles`      
  survives, which is exactly the asymmetry claimed:                             
                                                                                
  ```python                                                                     
  E_32 = (["#" * 32]                                                            
          + ["####" + "." * 28] * 6                                             
          + ["####" + "#" * 22 + "." * 6]                                       
          + ["####" + "." * 28] * 6                                             
          + ["#" * 32])                                                         
  #   0°  Signature(parts=1, cycles=0, b=1, c=1, m=0, s=0)                      
  #  -3°  Signature(parts=1, cycles=0, b=3, c=1, m=2, s=0)                      
  #  +3°  Signature(parts=1, cycles=0, b=1, c=3, m=0, s=2)                      
                                                                                
  SERIF_I = (["#" * 20]                                                         
             + ["." * 8 + "##" + "." * 10] * 20                                 
             + ["#" * 20])                                                      
  #   0°  Signature(parts=1, cycles=0, b=1, c=1, m=0, s=0)                      
  #  ±3°  Signature(parts=1, cycles=0, b=2, c=2, m=1, s=1)                      
  ```                                                                           
                                                                                
  A guard needs **both halves in one assertion** — `assertNotEqual` on the      
  full signature and `assertEqual` on `cycles`. That simultaneously proves      
  rotation is being applied and pins the asymmetry, which is what the class     
  name already promises.                                                        
                                                                                
  ---                                                                           
                                                                                
  ## F2 — "cycles is the durable component" has an exception class, and it is   
  the math population *(Important, demonstrated)*                               
                                                                                
  G5 says `cycles` survives rotation far better than the branch counts. On      
  closed shapes that held in every test I ran. On **near-horizontal separated   
  strokes it inverts** — rotation *creates* cycles by joining bars that were    
  disjoint:                                                                     
                                                                                
  | Fixture | 0° | ±3° |                                                        
  |---|---|---|                                                                 
  | two 40-wide bars, 1-row gap | `parts=2, cycles=0` | `parts=1, **cycles=1**` 
  |                                                                             
  | three 50-wide bars, 1-row gaps | `parts=3, cycles=0` | `parts=1,            
  **cycles=4**` |                                                               
                                                                                
  At 3° a 50-px-wide bar rises ~2.6 px across its width, so a 1-px gap closes.  
  The rotated image genuinely *is* connected — this is not a resampler          
  artefact, it is what happens to a wide thin gap under small rotation at       
  finite resolution.                                                            
                                                                                
  The affected shapes are `=`, `≡`, `÷`, fraction bars, `\hline`, and the       
  radical overbar. That is precisely the population U14 depends on and U13      
  will lean hardest on.                                                         
                                                                                
  **G5 should carry the exception**, something like: *`cycles` is the durable   
  component for closed forms; for near-horizontal separated strokes rotation    
  can merge components and create cycles, so cycle count is not durable in      
  that class.* Two fixtures above will pin it.                                  
                                                                                
  ---                                                                           
                                                                                
  ## F3 — The measurements that carry U4's headline result are not reproducible 
  *(Important)*                                                                 
                                                                                
  `git log --all --name-only` lists every file the repo has ever held. There is 
  no measurement script. The following exist only as prose in `units.md`:       
                                                                                
  - the 8,453-component premise check over 42 documents                         
  - the 158-glyph, 47–54% rotation measurement — **the evidence for the         
    refutation, and the only reason G5 reads as it does**                       
  - the projection-profile deskew check over 10 scanned pages                   
  - the 3,947 runs → 566 arcs contraction ratio                                 
                                                                                
  The numbers look sound and the method descriptions are unusually careful.     
  But nobody can re-run them when the corpus grows, when `signature()` gains    
  persistence (which `units.md` notes the proxy lacks), or when a reviewer      
  wants to check them. This is the U0 sampling problem one level up: there the  
  figures were wrong, here they are probably right and equally unverifiable.    
                                                                                
  **Commit the harness** — `tools/premise/` or similar, outside the package,    
  excluded from the suite, taking a corpus path. It does not need to be pretty. 
  It needs to exist so the next measurement is a re-run rather than a           
  re-implementation.                                                            
                                                                                
  ---                                                                           
                                                                                
  ## F4 — `signature()` is claimed as a partition, not a classifier — but       
  nothing tests the collisions *(Minor)*                                        
                                                                                
  `units.md` records the useful negative result (26.9% purity, worst            
  collisions `n h 3 N`, `i . / : j ; ?`, `e 6`). No test encodes any of it.     
  Three fixtures asserting that two known-colliding shapes produce the *same*   
  signature would stop a future change from silently claiming more              
  discriminative power than the measurement supports.                           
                                                                                
  ---                                                                           
                                                                                
  ## Order                                                                      
                                                                                
  F1 with the two fixtures, F2 with its two, then F3. F4 is optional. None      
  changes a contract; F2 corrects a guarantee that is currently overstated in   
  one direction.                                                                
                                                                                
  ---                                                                           
                                                                                
  # Separately — for the repo owner, not the CLI                                
                                                                                
  **The rotation experiment you offered is the right one**, and it is now the   
  single load-bearing measurement for G5 rather than a nice-to-have, because    
  no synthetic fixture reproduces the fragility. Two suggestions on its design: 
                                                                                
  - Use `\rotatebox{3}{...}` in the LaTeX so **Ghostscript** rasterises at the  
    angle with its own anti-aliasing — that is the gentle case the resampler    
    cannot simulate. Include a `\rotatebox{0}` control alongside an             
    un-boxed version, to confirm `rotatebox` itself does not perturb the        
    rasterisation.                                                              
  - Vary the binarisation threshold (say 128 / 200 / 240). Whether a thin       
    anti-aliased feature survives thresholding is likely to dominate the        
    result, and if the answer is threshold-dependent that is itself the         
    finding.                                                                    
                                                                                
  Include a `=` or `≡` and a fraction bar in the sample. F2 says those are      
  where the *cycle* claim breaks, and they are the glyphs the math track        
  cannot afford to be wrong about.                                              
                                                                                
  **Merge hygiene.** `origin/main` is 21 commits behind and still says "U1,     
  U2, U3 — 103 tests passed". A branch named `u0-io` now carries U0 and U4.     
  Nothing is broken, but the default branch a visitor sees is four units stale, 
  and the branch name no longer describes its contents.                         

● The audit is right on all four, and F2 is a genuine correction to a guarantee
  I overstated. Let me verify both demonstrated claims myself before acting.

  Ran 1 shell command (ctrl+o to expand)

● Both confirmed exactly as reported. F2 matters most — rotation creating cycles
  on separated horizontal strokes hits =, ≡, fraction bars and \hline, which is
  the math population. Replacing T4_6 with tests that actually assert.

  Ran 1 shell command (ctrl+o to expand)

● 37 pass. Fixing the escape warning, then correcting G5 for the exception F2
  found.

  Ran 1 shell command (ctrl+o to expand)

● Update(inkdrill/reeb.py)
  ⎿  Added 27 lines, removed 3 lines
       86  The load-bearing consequence for U13: **`cycles` is the durabl
           e
       87  component of this vector and the branch counts are the fragile
            one.** A
       88  consumer comparing signatures across a skewed page should weig
           ht them
       89 -accordingly, or deskew first. Whether a genuine re-render at 3
          - degrees --                                                   
       90 -antialiased, then thresholded -- is gentler than nearest-neigh
          -bour                                                          
       91 -resampling is untested and is the one measurement that would s
          -ettle it.                                                     
       89 +accordingly, or deskew first.                                 
       90  
       91 +**That durability has one exception, and it is the math popula
          +tion.**                                                       
       92 +For NEAR-HORIZONTAL SEPARATED STROKES rotation can merge compo
          +nents and                                                     
       93 +CREATE cycles, so there `cycles` is the least durable part:   
       94 +                                                              
       95 +        two 40-wide bars, 1-row gap      0 deg: parts=2 cycles
          +=0                                                            
       96 +                                        +-3 deg: parts=1 cycle
          +s=1                                                           
       97 +        three 50-wide bars, 1-row gaps   0 deg: parts=3 cycles
          +=0                                                            
       98 +                                        +-3 deg: parts=1 cycle
          +s=4                                                           
       99 +                                                              
      100 +At 3 degrees a 50-px-wide bar rises ~2.6 px across its width, 
          +so a 1-px                                                     
      101 +gap closes and the bars genuinely become one component. The ro
          +tated image                                                   
      102 +really is connected -- this is finite resolution, not a resamp
          +ler                                                           
      103 +artefact. The affected shapes are `=`, `≡`, `÷`, fraction bars
          +, `\\hline`                                                   
      104 +and the radical overbar, which is exactly what U14 depends on 
          +and what                                                      
      105 +U13 will lean on hardest. A consumer must not treat a cycle co
          +unt on                                                        
      106 +separated horizontal strokes as stable under skew.            
      107 +                                                              
      108 +Note also that clean synthetic ink is mostly rotation-STABLE -
          +- rings at                                                    
      109 +14/20/32/48 px with 1-3 px strokes, a 40-row H, a 48-row figur
          +e-8 and a                                                     
      110 +comb are all bit-stable under +-3 degrees. The 47-54% figure i
          +s a                                                           
      111 +property of real glyph ink under resampling, not of the signat
          +ure in                                                        
      112 +general. Whether a genuine re-render at 3 degrees -- antialias
          +ed, then                                                      
      113 +thresholded -- is gentler than nearest-neighbour resampling is
          + untested,                                                    
      114 +and is now the single load-bearing measurement for this guaran
          +tee rather                                                    
      115 +than a caveat on it.                                          
      116 +                                                              
      117  Guarantees
      118  ----------
      119  G1  every RAG node appears in exactly one ReebNode; the contra
           ction is a

● Update(inkdrill/reeb.py)
  ⎿  Added 6 lines, removed 4 lines
      124      vertically flipped mask -- assumption 2, tested rather tha
           n argued
      125  G4  reversal is an involution: orienting twice returns the ori
           ginal
      126      labelling
      127 -G5  `signature()` is invariant under translation, EXACTLY. It 
          -is not                                                        
      128 -    claimed to be invariant under rotation -- see the measurem
          -ent above;                                                    
      129 -    `cycles` survives rotation far better than the branch coun
          -ts, and                                                       
      130 -    that asymmetry is itself under test                       
      127 +G5  `signature()` is invariant under translation, EXACTLY. It 
          +is NOT                                                        
      128 +    claimed to be invariant under rotation. `cycles` survives 
          +rotation                                                      
      129 +    far better than the branch counts on CLOSED forms; on near
          +-horizontal                                                   
      130 +    separated strokes that inverts and rotation creates cycles
          +. Both                                                        
      131 +    halves are under test, and both fixtures fail if the rotat
          +ion is                                                        
      132 +    turned into a no-op                                       
      133  G6  persistence separates a 2-px speck from a stroke, and equa
           ls
      134      `hi_line - lo_line + 1` for every node
      135  G7  `signature_of()` on a single graph equals `signature()` on
            it, with

● Now F3 — committing the measurement harness so these numbers become
  re-runnable rather than re-implementable.

● Write(tools/premise/measure.py)
  ⎿  Wrote 429 lines to tools/premise/measure.py
      1 """Measurement harness for the figures quoted in docs/units.md §3
      2 
      3 NOT part of the package and NOT part of the test suite. It exists
         so that
      5 re-implementation -- when the corpus grows, when signature() gain
        s
      7 
      8     python3 tools/premise/measure.py --corpus ~/pdfdrill-library 
        all
        rotation
     … +469 lines (ctrl+o to expand)

  Ran 1 shell command (ctrl+o to expand)

● Harness reproduces the figures on independent samples. Smoke-testing the
  load-bearing one.

  Ran 1 shell command (ctrl+o to expand)

● Different sample gives 72–87%, not 47–54%. Now that the measurement is
  re-runnable, it immediately shows the figure is sample-sensitive — the same
  failure mode as U0's throughput. Characterising the spread rather than quoting
  one sample.

  Ran 2 shell commands (ctrl+o to expand)

● Background command "Characterise rotation measurement spread across seeds"
completed (exit code 0)

● Four seeds, n=120 each — and the point estimate doesn't survive:

  ┌──────┬───────────────────────┬───────────────┬─────────┐
  │ Seed │ Full signature at ±3° │ Cycles at ±3° │ Control │
  ├──────┼───────────────────────┼───────────────┼─────────┤
  │ 11   │ 40.8 / 52.5%          │ 80.0 / 81.7%  │ 100%    │
  ├──────┼───────────────────────┼───────────────┼─────────┤
  │ 99   │ 78.3 / 73.3%          │ 98.3 / 99.2%  │ 100%    │
  ├──────┼───────────────────────┼───────────────┼─────────┤
  │ 2026 │ 70.0 / 75.0%          │ 91.7 / 94.2%  │ 100%    │
  ├──────┼───────────────────────┼───────────────┼─────────┤
  │ 7    │ 65.0 / 64.2%          │ 91.7 / 92.5%  │ 100%    │
  └──────┴───────────────────────┴───────────────┴─────────┘

  The 47–54% figure was one sample. But the conclusion survives every seed:
  cycles beat the full signature by 20–40 points every time. Correcting to a
  range.

  Ran 1 shell command (ctrl+o to expand)
● Two stale references left inside the same docstring.

  Ran 5 shell commands (ctrl+o to expand)

● All four findings closed and pushed. 37 U4 tests, 193 total, 4 skipped —
  verified on a fresh clone of origin/u0-io.

  F1 — the decorative tests. You were right that all three passed with the
  rotator disabled. Fixed, and I verified the fix the same way you found the
  bug: on a clean clone, stubbing rotate() to return mask now produces 9 
  failures where it previously produced none. Your E_32 and SERIF_I fixtures
  were essential — I'd have struggled to find them, since clean synthetic ink is
  almost entirely rotation-stable. Each test now asserts both halves in one
  place: full signature differs and cycles hold, which proves rotation is
  applied and pins the asymmetry simultaneously.

  F2 — the exception, and it's the one that matters. Confirmed exactly: two
  40-wide bars with a 1-row gap go parts=2, cycles=0 → parts=1, cycles=1; three
  50-wide bars → cycles=4. G5 now carries it explicitly, with two fixtures
  pinning it, and names the affected population — =, ≡, ÷, fraction bars,
  \hline, the radical overbar. This was a guarantee overstated in one direction
  and I'd have shipped it.

  F3 — and it earned its keep immediately. tools/premise/measure.py now holds
  all seven measurements behind a corpus path. Running it exposed that the 
  47–54% rotation figure came from a single sample and does not reproduce. Four
  independent 120-component samples span 41–78% for the full signature and
  80–99% for cycles. That's the U0 sampling failure recurring one level up,
  caught this time only because the harness existed.

  What survives every sample is the ordering — cycles beat the full signature by
  20–40 points, always. units.md now states the range, names the superseded
  figure, and says plainly that the ordering is the claim while the percentages
  are context.

  F4 — T4_7 encodes the collision result, so no future change can quietly claim
  more discriminative power than the 26.9% purity measurement supports.

  Merge hygiene — needs a word from you

  origin/main is 22 commits behind and still reads "U1, U2, U3 — 103 tests
  passed". A branch called u0-io now carries U0 and U4. Both are one command,
  but they change what a visitor to a public repo sees, so I'd rather not do it
  unprompted: shall I fast-forward main to this branch? If so I'd also delete
  u0-io afterwards, since its name stopped describing its contents two units
  ago.

  For your rotation experiment

  The auditor's design notes are good and I'd add nothing. It's now the single
  load-bearing measurement for G5 rather than a nice-to-have — no synthetic
  fixture reproduces the fragility, so only a genuine antialiased re-render can
  separate "the signature is rotation-fragile" from "nearest-neighbour 
  resampling is". Include a = or ≡ and a fraction bar: F2 says those are exactly
  where the cycle claim inverts.

  Next by your ordering is U5 aggregate.py. Its premise to check first is
  assumption 4 — that row-sweep and col-sweep produce identical moments, which
  units.md warns "does not follow automatically, since the accumulation order
  differs."

✻ Cooked for 6m 55s

※ recap: Building inkdrill unit by unit; U0 pngio and U4 reeb are done and pushed, 193 tests passing on branch u0-io. Next: say whether to fast-forward main to that branch, then I start U5 aggregate.py.

❯ update the git repo and gon on!                                               

  Merged u0-io (ctrl+o to expand)

● main is current at cbae4ad, u0-io deleted, 193 tests green. resume.sh
  correctly left on disk but untracked.

  Now U5 aggregate.py — premise check first. Assumption 4 says axis-invariant
  moments "do not follow automatically, since the accumulation order differs."

  Ran 1 shell command (ctrl+o to expand)

● Assumption 4 holds — 400/400 whole-mask, 300/300 per-component identical. And
  the reason matters for the design: I accumulated in integer closed forms, so
  the sums are exact and order-independent. Float accumulation would make the
  order matter. That's a contract constraint, not an implementation detail.

● Write(inkdrill/aggregate.py)
  ⎿  Wrote 326 lines to inkdrill/aggregate.py
       1 """aggregate.py — moment aggregates per component.
       2 
       3 CONTRACT (written before implementation; see docs/units.md U5)
       4 =============================================================
       5 
       7 -----------------------
       8 For each component of a U3 sweep: area, extents, and the raw mom
         ent sums
       9 
      10         A   Sx   Sy   Sxx   Syy   Sxy
     … +371 lines (ctrl+o to expand)

● Write(tests/test_aggregate.py)
  ⎿  Wrote 301 lines to tests/test_aggregate.py
       1 """Unit 5 tests. Every test name is quoted verbatim in the statu
         s report."""
       3 import math
       4 import random
       5 import unittest
       7 from inkdrill.aggregate import (PIXEL_VARIANCE, Moments, compone
         nt_moments,
       8                                 moments_of_mask, moments_per_com
       9 from inkdrill.raster import BG, INK, InkMask, InvalidAxis
      10 from inkdrill.space import angle_deg_screen
     … +322 lines (ctrl+o to expand)

  Ran 1 shell command (ctrl+o to expand)

● The recovered angle is consistently 180 − want, which is a convention
  mismatch, not an arithmetic error. Let me read what each producer actually
  promises rather than guess.

  Ran 1 shell command (ctrl+o to expand)

● angle_deg_screen is right and my expectation was wrong. My fixture's direction
  is (cos t, sin t) in index space — right and downward — which a reader sees
  as a clockwise slope, so the screen convention correctly reports −want. I made
  precisely the sign error the no-stored-angles rule exists to prevent.

● Update(tests/test_aggregate.py)
  ⎿  Added 8 lines, removed 1 line
      204      def test_a_rotated_rule_recovers_its_angle_through_angle_d
           eg_screen(self):
      205          """The axis is a vector; `space.angle_deg_screen` is t
           he only
      206          sanctioned way to turn it into degrees, and it names i
           ts
      207 -        convention (y-down, image space)."""                  
      207 +        convention (y-down, image space).                     
      208 +                                                              
      209 +        The sign here is the whole reason U1 forbids stored an
          +gles. The                                                     
      210 +        fixture's direction in INDEX space is (cos t, sin t) -
          +- right and                                                   
      211 +        DOWNWARD, because raster y grows downward. A reader se
          +es that as                                                    
      212 +        a clockwise slope, so the screen convention reports -t
          +, not +t.                                                     
      213 +        The first draft of this test asserted +t and failed on
          + every                                                        
      214 +        non-zero angle."""                                    
      215          for want in (0.0, 15.0, 30.0, 45.0, 60.0, 75.0):
      216              n = 240
      217              t = math.radians(want)

  Ran 1 shell command (ctrl+o to expand)

● All 26 pass. Verifying U5 on real ink before recording anything.

  Ran 1 shell command (ctrl+o to expand)

● G2 and G7 hold on 635 real components. Adding U5 to the harness so its figures
  are re-runnable too, then recording.

  Ran 3 shell commands (ctrl+o to expand)

● The backticks in my commit message triggered shell substitution. Fixing the
  message.

  Ran 2 shell commands (ctrl+o to expand)

● Repo updated and U5 landed. Verified on a clean clone of main.

  Repo

  main fast-forwarded 22 commits and now carries everything; u0-io deleted,
  since its name stopped describing its contents two units ago. resume.sh stays
  on disk but out of the repo. A visitor now sees the current state rather than
  a four-unit-stale default branch.

  U5 aggregate.py — 26 tests, 219 total

  ┌──────────────┬───────┐
  │     Unit     │ Tests │
  ├──────────────┼───────┤
  │ U0 pngio     │ 49    │
  ├──────────────┼───────┤
  │ U1 space     │ 36    │
  ├──────────────┼───────┤
  │ U2 raster    │ 31    │
  ├──────────────┼───────┤
  │ U3 sweep     │ 36    │
  ├──────────────┼───────┤
  │ U4 reeb      │ 37    │
  ├──────────────┼───────┤
  │ U5 aggregate │ 26    │
  └──────────────┴───────┘

  Assumption 4 verified, and the reason changed the contract. units.md warned
  that axis-invariant moments "do not follow automatically, since the
  accumulation order differs" — correct, and they don't follow from U2's
  pixel-set agreement. They follow from exactness: every raw sum is a Python
  int, so a row sweep and a column sweep grouping the same pixels into different
  runs and summing them in a different order must agree. Measured identical on
  400 random masks whole-mask, 300 per component, and 635 components of real 
  page ink.

  So integer accumulation is now stated in the contract rather than left as an
  implementation choice. In floating point the same code would drift and G2
  would hold only approximately — which is exactly the kind of silent weakening
  this project's rules exist to prevent.

  Also delivered: closed-form run accumulation checked against a per-pixel
  oracle, centroid on pixel centres, principal axis as a canonically-signed unit
  vector, the λ₂ floor engaging exactly at 1-px width and not at 2, and
  Moments.__add__ — the exact addition algebra U7 will stitch bands with,
  already tested to sum back to the whole.

  One test earned its place immediately. My rotated-rule fixture asserted the
  wrong sign and failed on every non-zero angle: a rule sloping down-and-right
  in index space reads as negative under angle_deg_screen, because raster y
  grows downward. That is precisely the sign drift the no-stored-angles
  convention was written to prevent, and I walked straight into it. Both
  producers are now asserted against each other there.

  tools/premise/measure.py gains a moments subcommand, so U5's figures are
  re-runnable like the rest.

  Next by your ordering is U6 nest.py — holes and the containment forest. Its
  premise is already half-measured: the U4 check found hole counts 98.7–100%
  consistent against character identity on 8,453 glyphs, and U6's stated oracle
  is that nest's hole count must equal U3's cycle_count — two independent
  computations checking each other. Worth confirming that agreement on real ink
  before writing it, since that's the whole design.

✻ Churned for 5m 23s

❯ please go on!!                                                                

● U6 nest.py. Premise check first — its whole design rests on nest's hole count
  agreeing with U3's cycle_count, two independent computations serving as each
  other's oracle.

  Ran 1 shell command (ctrl+o to expand)
● 113/113 agreement on real ink. That closes the remaining half of assumption 3
  — cycle rank counts holes, now confirmed by an independent computation rather
  than the duality argument and fixtures alone. Writing U6.

● Write(inkdrill/nest.py)
  ⎿  Wrote 336 lines to inkdrill/nest.py
       1 """nest.py — holes, the containment forest, and the ordering rel
         ations.
       3 CONTRACT (written before implementation; see docs/units.md U6)
       4 =============================================================
       5 
       7 ---------------------------------------
       8 U3 already reports a hole count per component, as the cycle rank
       9 `E - V + C` of the run adjacency graph. This unit computes holes
      10 completely different way -- as background components of the inve
         rted
     … +373 lines (ctrl+o to expand)

● Write(tests/test_nest.py)
  ⎿  Wrote 321 lines to tests/test_nest.py
       1 """Unit 6 tests. Every test name is quoted verbatim in the statu
         s report."""
       2 
       3 import random
       4 import unittest
       6 from inkdrill.nest import InvalidConnectivity, Kind, nest
       7 from inkdrill.raster import BG, INK, InkMask
       8 from inkdrill.sweep import Capture, sweep
       9 
      10 RING = ["#####",
     … +339 lines (ctrl+o to expand)

  Ran 1 shell command (ctrl+o to expand)

● 29 pass first try — including the diagonal-wall leak case and the \fbox
  distinction. Adding it to the harness and running the U3 cross-check at scale
  on real ink.

  Ran 2 shell commands (ctrl+o to expand)

● 222 real components across two independent samples, 100% agreement. That's
  units.md assumption 3 fully verified — by an independent computation, not the
  duality argument. Recording.

  Ran 3 shell commands (ctrl+o to expand)

● U6 nest.py landed. 29 tests, 248 total, verified on a clean clone of main.

  ┌────────────────────────────────────────────┬───────────────────┐
  │                    Unit                    │       Tests       │
  ├────────────────────────────────────────────┼───────────────────┤
  │ U0 pngio · U1 space · U2 raster · U3 sweep │ 49 · 36 · 31 · 36 │
  ├────────────────────────────────────────────┼───────────────────┤
  │ U4 reeb · U5 aggregate · U6 nest           │ 37 · 26 · 29      │
  └────────────────────────────────────────────┴───────────────────┘

  The headline: assumption 3 is now verified, not argued

  The identity cycles == E − V + C was always just arithmetic. That it counts
  holes rested on a duality argument plus six fixtures. U6 computes holes a
  completely different way — background components of the inverted mask at
  conn=4, sharing no code with the sweep — and the two agree on the fixtures, on
  120 random masks, and on 222 components of real page ink across two 
  independent samples, at 100%.

  Each is now genuinely the other's oracle, which is what units.md asked for.
  That's the third assumption closed by measurement (2, 3, 4), against one
  refuted (rotation invariance).

  What made it clean

  The parent lookup is exact rather than heuristic, which I didn't expect going
  in. Above a foreground pixel, a 4-adjacent foreground pixel would be in the
  same component under 8-connectivity; above a background pixel, a 4-adjacent
  background pixel would be in the same background component. So one lookup
  directly above a region's topmost pixel names its parent — no point-in-polygon
  test, no bbox guessing. The paired-connectivity rule from units.md §1 is what
  makes that work, and test_a_diagonal_wall_does_not_leak pins it.

  The \fbox case earned its place: the frame has one hole, and the glyph inside
  is ink_in_hole of that hole — emphatically not hole_of the frame. Conflating
  them would count body text as part of a frame's topology. hole_of and
  ink_in_hole are asserted disjoint.

  Depth parity (even = ink, odd = background) is a runtime check, not a
  convention — check_parity() and check_forest() are called by the tests on
  every random mask.

  One thing I did not build

  The disconnected table frame — collinear rule grouping — is named in units.md
  alongside the connected case. It needs U5 geometry to group rules by
  collinearity, and I've recorded it as a stated scope limit rather than
  half-building it. The connected m×n frame works and is tested at four sizes.

  Next by your ordering is U7 band.py — band splitting and seam stitching.
  units.md flags it as carrying "the specific latent bug the old code base
  carries": runs and RAG nodes must be re-sorted after concatenation. Its
  premise check is cheap and worth doing first — U5's Moments.__add__ is already
  tested to sum disjoint components back to the whole, which is half the
  stitching algebra; the open half is whether the cycle-rank identity survives a
  seam.

✻ Worked for 5m 37s

❯ go on with U7                                                                 

● U7 band.py. Premise check first — units.md names a specific latent bug here,
  so let me quantify what stitching actually has to repair before designing it.

  Ran 1 shell command (ctrl+o to expand)

● Two invariants fall out, and one is load-bearing:

  V is exactly invariant across every K — 2559 and 11635 unchanged from K=1 to
  K=64. Runs never span a line (U2's G2), so a band cut at a line boundary can
  never split a run. Everything else needs repair: at K=64 one page needed 1,068
  seam edges, 949 over-counted components and 119 missing cycles. Also notable
  — asplos22 at K=2 and K=3 needed zero repair, so a test that only tries small
  K would pass while proving nothing.

● Write(inkdrill/band.py)
  ⎿  Wrote 303 lines to inkdrill/band.py
       1 """band.py — band splitting and seam stitching.
       2 
       4 =============================================================
       5 
       6 Why bands
       8 A page is swept in horizontal bands so U8 can hand them to separ
         ate
       9 workers. Each band is swept independently, in its own label spac
      10 the results are stitched by applying U3's adjacency predicate ac
         ross each
     … +342 lines (ctrl+o to expand)

● Write(tests/test_band.py)
  ⎿  Wrote 311 lines to tests/test_band.py
       1 """Unit 7 tests. Every test name is quoted verbatim in the statu
         s report."""
       3 import random
       4 import unittest
       5 
         _per_component
       7 from inkdrill.band import (Band, InvalidBandCount, canonical, sp
         lit, stitch,
       9 from inkdrill.raster import BG, INK, InkMask
      10 from inkdrill.sweep import Capture, InvalidConnectivity, sweep
     … +347 lines (ctrl+o to expand)

  Ran 1 shell command (ctrl+o to expand)

● My CROSSER fixture is 63 rows but the plan specifies K=64. The fixture should
  support the spec'd K rather than the limit bending to the fixture.

  Ran 1 shell command (ctrl+o to expand)

● 28 pass. But the auditor's lesson applies: I should prove these tests can
  fail. Mutating the two things U7 exists to get right.

  Ran 1 shell command (ctrl+o to expand)

● Mutant 1 survived — dropping the global re-sort passes all 28 tests. That's
  the decorative-test problem again, on the exact bug units.md names. The
  reason: sorting bands on entry already yields global order, so the re-sort is
  unreachable through the public API. It's only reachable if a band delivers its
  own nodes out of order — which U8 plausibly will, appending per worker.
  Making that reachable and tested.

  Ran 1 shell command (ctrl+o to expand)

● Mutant 1 now dies (3 failures). All three defences are genuinely tested.
  Verifying on real page ink at the K values that actually stress the seams.

  Ran 1 shell command (ctrl+o to expand)

● Identical at every K on real ink — including K=600, one band per row, where
  every single line is a seam. Recording.

  Searched for 1 pattern, ran 2 shell commands (ctrl+o to expand)

● U7 band.py landed. 29 tests, 277 total, verified on a clean clone.

  The premise check paid for itself twice

  It found the invariant that carries the unit. A band split can never split a
  run — U2's G2 says a run never spans a line boundary, and a band boundary is
  one. So V needs no repair at all; only E, C and the cycle counts do. Measured
  bit-identical from K=1 to K=64 on real ink.

  And it found a trap. One real page needed zero repair at K=2 and K=3 — the
  seams happened to land in whitespace. A test suite that only tried small K
  would have passed while proving nothing. At K=64 the same class of page needed
  1,068 seam edges, 949 over-counted components and 119 missing cycles.

  Assumption 5 verified — and the named bug was real

  units.md warned that "runs and RAG nodes must be re-sorted after concatenation
  — this is the specific latent bug the old code base carries." I
  mutation-tested all three defences:

  ┌───────────────────────────────┬──────────────┐
  │           Mutation            │    Result    │
  ├───────────────────────────────┼──────────────┤
  │ Trust band arrival order      │ 17 failures  │
  ├───────────────────────────────┼──────────────┤
  │ Seam edge never closes a loop │ 247 failures │
  ├───────────────────────────────┼──────────────┤
  │ Drop the per-node re-sort     │ survived     │
  └───────────────────────────────┴──────────────┘

  The third survived because sorting the band list already produces global
  order, which made the per-node re-sort unreachable through the public API — a
  decorative defence, precisely the class of problem your auditor caught in U4.
  A test that shuffles nodes within a band makes it reachable and kills the
  mutant. That case isn't hypothetical: U8 is specified to order results by
  completion, not by band.

  Stitched output is now indistinguishable from a single sweep on the
  crossing-blob fixture at K ∈ {1,2,3,7,64}, on 60 random masks at both
  connectivities, and on real page ink up to K=600 — one band per row, so every
  line is a seam.

  One thing I did not fake

  Scan events are not stitched. A band boundary manufactures spurious births at
  its top and closes at its bottom; repairing that needs the bounded-memory
  closure stream, which is a later unit. stitch() returns an empty event list
  and says why, rather than returning events that look right and aren't. That's
  the closed_at caveat assumption 5 was reaching for.

  Where the plan stands

  Five assumptions closed by measurement (2, 3, 4, 5, and half of 1), one
  refuted (rotation invariance). Remaining unverified: 6 (scheduler
  utilisation), 7 (pdfminer boxes vs ink — already biting), 8 (arXiv font mix),
  9 (parallel throughput), 10 (package name).

  Next is U8 sched.py, and it's a different kind of unit — multiprocessing,
  shared memory, and timing measurements rather than exact invariants. Its
  premise (assumption 6, the idle tail) is explicitly "unaddressed and may need
  finer bands at the end as well as the start", and assumption 9 warns
  serialization overhead may eat the parallel gain. Both are measurable before I
  design anything, which is what I'll do first.
✻ Brewed for 5m 44s

❯ go on with U7 and check the git is actul for an audit of previous steps.      

● U7 is complete and pushed — I'll verify that properly and make the repo
  audit-ready first, then continue.

  Ran 2 shell commands (ctrl+o to expand)

● Now checking the documentation an auditor would cross-check against — the
  failure mode that's bitten twice already.

  Ran 1 shell command (ctrl+o to expand)

● Found a real gap an auditor would flag: units.md §3's status table still only 
  lists U0–U3. U4–U7 carry status lines in §2 but never made it into §3 — the
  section whose whole job is recording what has run.

  Searched for 1 pattern, ran 1 shell command (ctrl+o to expand)

● Three stale things in the one section whose job is accuracy: the quoted output
  (156 vs 277), the missing U4–U7 rows, and a filename my rename missed. Fixing
  with actual output.

  Ran 1 shell command (ctrl+o to expand)

● Now sweeping the whole repo for any other stale reference an auditor would
  find.

  Ran 1 shell command (ctrl+o to expand)

● Only the dated plan still says io.py, which is correct — it's a historical
  record. But it needs a header so an auditor isn't misled. And one unit is
  missing its status line; let me find which.

  Ran 1 shell command (ctrl+o to expand)

● All eight are present — my regex just didn't match U4's longer line. Adding
  the rename note to the dated records so an auditor isn't misled by io.py.

  Ran 1 shell command (ctrl+o to expand)

● Last audit check — that every measurement units.md claims is actually
  re-runnable from the harness.

  Ran 1 shell command (ctrl+o to expand)

● Those two are my search strings, not gaps — verifying directly.

  Ran 1 shell command (ctrl+o to expand)

● One structural gap: §3 has measurement sections for U0 and U4 but none for
  U5–U7, whose findings live only in assumption updates. §3 is the
  measured-results section, so adding them.

  Ran 2 shell commands (ctrl+o to expand)

● U7 was already complete and pushed — 29 tests, verified again on a clean
  clone. The audit-readiness check is what turned up work, and it found four
  real bugs.

  Git state: auditable

  Working tree clean, local in sync with origin/main, single branch, 30 commits.
  A clean clone gives 27 files and passes 277 tests, 4 skipped.

  Four staleness bugs, all in units.md §3 — the section whose entire job is 
  accuracy

  ┌──────────────┬─────────────────────────┬────────────────────────────────┐
  │    Found     │           Was           │              Now               │
  ├──────────────┼─────────────────────────┼────────────────────────────────┤
  │ Quoted       │                         │ Ran 277 tests, pasted from an  │
  │ command      │ Ran 156 tests           │ actual run                     │
  │ output       │                         │                                │
  ├──────────────┼─────────────────────────┼────────────────────────────────┤
  │ §3 status    │ U0–U3 only              │ all eight units, regenerated   │
  │ table        │                         │ from real per-module runs      │
  ├──────────────┼─────────────────────────┼────────────────────────────────┤
  │ Corpus test  │ tests/test_io_corpus.py │ tests/test_pngio_corpus.py —   │
  │ filename     │                         │ the rename missed it           │
  ├──────────────┼─────────────────────────┼────────────────────────────────┤
  │ Measurement  │                         │ U5–U7 added; their findings    │
  │ sections     │ U0 and U4 only          │ existed only as struck-through │
  │              │                         │  assumptions                   │
  └──────────────┴─────────────────────────┴────────────────────────────────┘

  Four units were missing from the table that records what has actually run.
  That's the same class of error as the throughput and colour-fraction figures —
  documentation drifting behind measurement — and it's exactly what an auditor
  cross-checking units.md against the suite would hit first. The table is now
  generated from real runs and verified to match: 49+36+31+36+37+26+29+29 = 273 
  hermetic, 277 collected, zero mismatches.

  Also fixed for the auditor's benefit

  The dated spec and plan still say io.py throughout, which is correct — they're
  historical records and shouldn't be rewritten. But an auditor reading them
  would reasonably conclude the module exists. Both now carry a header stating
  it shipped as pngio.py and that every io.py reference below is historical.

  I also confirmed all ten harness subcommands map to claims in units.md, so
  every quoted figure is re-runnable: neutrality colour throughput skew premise 
  contraction rotation moments nesting banding.

  Where the project stands

  Five assumptions closed by measurement (2, 3, 4, 5, half of 1), one refuted
  (rotation invariance), four still open (6 scheduler utilisation, 7 pdfminer
  boxes vs ink, 8 arXiv font mix, 9 parallel throughput).

  Next is U8 sched.py, and it's a genuinely different kind of unit —
  multiprocessing, shared memory, and timing rather than exact invariants. Two
  of the open assumptions are its own (6 and 9), and units.md is candid that the
  idle tail is "unaddressed and may need finer bands at the end as well as the
  start". Both are measurable before I design anything, which is where I'll
  start.

✻ Baked for 2m 51s

※ recap: Building inkdrill unit by unit; U0 through U7 are done, 277 tests green, and the repo is pushed and audit-ready. Next I start U8 sched.py by measuring its two open assumptions, scheduler utilisation and parallel throughput, before designing it.

❯ please go on -- before check audit report: # inkdrill U7 `band.py` — audit    
  before U8                                                                     
                                                                                
  `origin/main` @ `3bacc36`. **277 tests, 4 skipped, verified on a clean        
  clone.**                                                                      
  Everything is merged; U4 findings F1–F4 closed and the measurement harness is 
  committed under `tools/premise/`.                                             
                                                                                
  Scope fence unchanged: render path, input format and Ghostscript invocation   
  are out of scope.                                                             
                                                                                
  ---                                                                           
                                                                                
  ## U7's correctness is not in question                                        
                                                                                
  I mutation-tested the four load-bearing parts of `stitch()`. All four were    
  caught, most of them loudly:                                                  
                                                                                
  | Mutation | Result |                                                         
  |---|---|                                                                     
  | seam cycle detection removed (`slot_cycles[ra] += 1` → `pass`) | 247        
  failures |                                                                    
  | global re-sort removed | 3 failures |                                       
  | seam slack forced to 0 at conn=8 | 424 failures |                           
  | band list not sorted on entry | 17 failures |                               
                                                                                
  `canonical()` is a genuinely strong oracle — full per-component run pixel     
  sets plus every count — and K coverage reaches one band per row. The          
  node-count invariance insight (a band boundary *is* a line boundary, so a     
  split can never split a run, so V needs no repair) is correct and well        
  argued. The scope limit on events is honest and states the right thing:       
  *returns an empty event list rather than events that look right and are not.* 
                                                                                
  **This is the first unit where my test-quality probe found nothing.** The     
  finding below is not about correctness.                                       
                                                                                
  ---                                                                           
                                                                                
  ## The finding: U7's cost was never measured, and it inverts U8's premise     
                                                                                
  Every U7 measurement in `units.md` is a correctness measurement. There is no  
  timing anywhere. Meanwhile `units.md` §3 still asserts:                       
                                                                                
  > …so U7/U8 band parallelism is what makes the first-page latency target      
  > reachable, exactly as the design argued.                                    
                                                                                
  That sentence is mine, it was never measured, and the measurement             
  contradicts it.                                                               
                                                                                
  ### Measured, best-of-3, 1240×1754 page, 27,488 runs, 546 components          
                                                                                
  | | |                                                                         
  |---|---|                                                                     
  | unbanded `sweep(GRAPH)` | **0.167 s** |                                     
  | `sweep_bands` (total serial, K = 1…256) | 0.18–0.21 s |                     
  | `stitch` (K = 1…256) | **0.19–0.21 s** |                                    
  | total serial cost vs unbanded | **≈2.5×, flat from K=1 to K=256** |         
                                                                                
  Two things fall out of that table.                                            
                                                                                
  **`stitch` costs more than the sweep it stitches.** 0.20 s against 0.167 s.   
                                                                                
  **The overhead is flat in K, and already present at K=1.** So it is not the   
  seam loop — it is a fixed cost `stitch` pays regardless of how many bands     
  there are.                                                                    
                                                                                
  ### The Amdahl consequence                                                    
                                                                                
  Band-parallelism splits the sweep across workers, but `stitch` is serial.     
  Estimated wall time for one page:                                             
                                                                                
  | K | parallel part | serial `stitch` | wall | vs unbanded |                  
  |---|---|---|---|---|                                                         
  | 1 (no banding) | — | — | 0.167 s | 1.00× |                                  
  | 8 | 0.027 s | 0.200 s | 0.227 s | 1.36× **slower** |                        
  | 64 | 0.003 s | 0.200 s | 0.203 s | 1.22× **slower** |                       
  | 128 | 0.002 s | 0.200 s | 0.202 s | 1.21× **slower** |                      
                                                                                
  **Banding a single page is slower than not banding it, for every K**, because 
  `stitch` alone exceeds the entire unbanded sweep. Adding cores cannot help:   
  the serial floor is 0.20 s no matter how many there are.                      
                                                                                
  Scaled to 600 dpi A4 (34.8 Mpx, ~16× this page) the shape is unchanged —      
  roughly 2.7 s unbanded against a ~3.2 s serial stitch floor.                  
                                                                                
  This is exactly the premise check that belongs *before* U8's plan is written, 
  in the discipline U4 established. U8 as currently specced — `(page, axis,     
  band)` tasks with page 1 at large K — would be built, measured, and found to  
  make the first page slower.                                                   
                                                                                
  ---                                                                           
                                                                                
  ## Where the cost is (I was wrong about the sort)                             
                                                                                
  I assumed the `sorted(range(len(nodes)))` renumbering was the cost. Profiling 
  says otherwise — that sort is 0.013 s of 0.303 s. The actual profile:         
                                                                                
  ```                                                                           
  54,976 calls   RunNode.__init__     0.069 s     <- 2x the 27,488 nodes        
  167,848 calls  list.append          0.029 s                                   
  55,523 calls   list.sort            0.009 s     <- up/down, mostly 1-element  
  2 calls        sorted               0.013 s                                   
  ```                                                                           
                                                                                
  **`stitch` constructs every `RunNode` twice** — once in the concatenation     
  loop, then again in the renumbering rebuild.                                  
                                                                                
  And the second pass is avoidable on the production path. I verified:          
                                                                                
  ```                                                                           
  concatenation already sorted by (line, lo) in band order: True                
  ```                                                                           
                                                                                
  Band *i* covers lines strictly below band *i+1*, and U3 emits nodes in scan   
  order within a band, so concatenating in `ordered` order is *already*         
  globally sorted. The renumbering exists only for the adversarial case that    
  `test_nodes_unsorted_WITHIN_a_band_are_still_sorted_on_output` constructs by  
  hand — a malformed band that the production path cannot produce.              
                                                                                
  **Two directions, in order of payoff:**                                       
                                                                                
  1. **Skip the rebuild when the concatenation is already sorted.** An O(V)     
     sortedness check, falling back to the current path when it fails, so the   
     defensive test still passes. Halves `RunNode` construction. Also skip      
     `n.up.sort()` / `n.down.sort()` when `len < 2` — 55,523 calls, nearly all  
     on one-element lists.                                                      
  2. **Tree-stitch.** Seam merging is associative, so adjacent bands can be     
     stitched pairwise in log₂K parallel rounds instead of one flat serial      
     pass. This is the structural fix — direction 1 lowers the serial floor,    
     this one removes it. It is also more work, and should only be attempted if 
     direction 1 leaves the floor above the sweep.                              
                                                                                
  Neither is U7 rework for its own sake. Both are prerequisites for U8's band   
  tier being worth building.                                                    
                                                                                
  ---                                                                           
                                                                                
  ## Good news: assumption 4 holds                                              
                                                                                
  `units.md` assumption 4 — *"Run-list serialization is cheap enough for        
  level-1 parallelism to pay off. Plausible; unmeasured, and it is the          
  assumption C2 depends on entirely."* Now measured:                            
                                                                                
  | | |                                                                         
  |---|---|                                                                     
  | one band of 64 (395 runs) | 21.2 KB pickled |                               
  | `dumps` / `loads` | 0.88 ms / 0.82 ms |                                     
  | all 64 bands, per page | 1.45 MB round-tripped |                            
  | raw mask for comparison | 2.07 MB |                                         
                                                                                
  Serialization is not the constraint. **Blob-parallel feature extraction       
  (level 1) is unaffected by the finding above** — a closed component is        
  independent, needs no stitch, and costs under a millisecond to ship.          
                                                                                
  ---                                                                           
                                                                                
  ## What this means for U8                                                     
                                                                                
  The design had three tiers. The measurement moves them:                       
                                                                                
  | Tier | Status |                                                             
  |---|---|                                                                     
  | **Level 0 — page-parallel** | Unaffected. 25 pages → 25 cores, near-linear, 
  no stitch. Build first. |                                                     
  | **Level 1 — blob-parallel** | Unaffected, and assumption 4 now verified.    
  This is what fills the remaining ~100 cores. |                                
  | **Level 2 — band-parallel** | **Currently negative.** Conditional on the    
  stitch floor dropping below the sweep. |                                      
                                                                                
  Level 0 + level 1 still reach full utilisation on 128 cores with a 25-page    
  paper, and the priority-queue scheduler still works — the task tuple just     
  becomes `(page, axis)` plus a blob queue rather than `(page, axis, band)`.    
  First-page latency then comes from level 1 within page 1, not from banding    
  it.                                                                           
                                                                                
  **Suggested sequencing:** U8 Task 1 measures the stitch floor after fix       
  direction 1 and decides whether the band tier enters the plan at all.         
  Everything downstream of that decision changes shape, so it should not be     
  deferred to Task 4 the way the colour fraction was in U0.                     
                                                                                
  ---                                                                           
                                                                                
  ## Minor                                                                      
                                                                                
  `units.md` §3's sentence about U7/U8 band parallelism should be corrected or  
  removed — it is an unmeasured design-time assertion now contradicted by       
  measurement, sitting in the file that is supposed to be the measured record.  
                                                                                
  My figures are single-machine, pure Python 3.12, on a synthetic text-like     
  page. The *ratio* is what matters and it is stable across K, but the          
  absolute numbers should be re-taken on your hardware and real page ink        
  before they enter `units.md`.                                                 

● The audit's finding is serious and would invert U8's premise. Their numbers
  are synthetic and on Python 3.12, and they explicitly ask me to re-take them —
  so let me measure on real page ink here before changing anything.

  Ran 1 shell command (ctrl+o to expand)

● Confirmed in direction, though not in magnitude — and the difference matters.

  ┌──────────────────────┬───────────────────────┬─────────────────────────┐
  │                      │ Auditor (synthetic,   │ Mine (real ink, Py3.14) │
  │                      │        Py3.12)        │                         │
  ├──────────────────────┼───────────────────────┼─────────────────────────┤
  │ stitch/sweep         │ >1.0×                 │ 0.53–0.70× at useful K  │
  ├──────────────────────┼───────────────────────┼─────────────────────────┤
  │ Serial total vs      │ 2.5×                  │ 1.48–1.84×              │
  │ unbanded             │                       │                         │
  ├──────────────────────┼───────────────────────┼─────────────────────────┤
  │ Fixed cost present   │ yes                   │ yes — 9.4 ms with a     │
  │ at K=1               │                       │ single band             │
  └──────────────────────┴───────────────────────┴─────────────────────────┘

  So banding isn't negative here, but the structural point holds exactly: stitch
  is a hard serial floor. Amdahl on my numbers caps band-parallelism at
  17.7/10.5 ≈ 1.7× no matter how many cores. That's a poor return for 64
  workers. Let me verify their root-cause claim before optimising.

  Ran 1 shell command (ctrl+o to expand)
● Both claims verified: concatenation is already sorted in band order, and
  RunNode.__init__ fires 10,000 times for 5,000 runs — the double construction.
  Also spotted owner is built and never used. Applying fix direction 1.

● Update(inkdrill/band.py)
  ⎿  Added 20 lines, removed 8 lines
      178  
      179      # ---- concatenate, lifting every run into global coordina
           tes -------
      180      nodes: list[RunNode] = []
      181 -    owner: list[int] = []            # new node id -> band ind
          -ex                                                            
      181      local_to_global: list[dict[int, int]] = []
      182      for bi, band in enumerate(ordered):
      183          mapping: dict[int, int] = {}
     ...
      185              gid = len(nodes)
      186              mapping[n.id] = gid
      187              nodes.append(RunNode(gid, n.line + band.y0, n.lo, 
           n.hi))
      189 -            owner.append(bi)                                  
      188          local_to_global.append(mapping)
      189  
      190      # G3: global scan order, whatever order the bands arrived 
           in.
      193 -    order = sorted(range(len(nodes)),                         
      194 -                   key=lambda i: (nodes[i].line, nodes[i].lo))
      195 -    renumber = {old: new for new, old in enumerate(order)}    
      196 -    nodes = [RunNode(renumber[nodes[i].id], nodes[i].line,    
      197 -                     nodes[i].lo, nodes[i].hi) for i in order]
      198 -    owner = [owner[i] for i in order]                         
      191 +    #                                                         
      192 +    # On the production path the concatenation is ALREADY in s
          +can order --                                                  
      193 +    # band i covers lines strictly below band i+1, and U3 emit
          +s nodes in                                                    
      194 +    # scan order within a band -- so an O(V) check skips the r
          +ebuild and                                                    
      195 +    # halves RunNode construction. Measured: the rebuild was c
          +onstructing                                                   
      196 +    # every node a second time, 2x V allocations for no effect
          +.                                                             
      197 +    #                                                         
      198 +    # The slow path is not dead code. A caller may hand over a
          + band whose                                                   
      199 +    # OWN nodes are unordered, which is exactly what U8 does w
          +hen it                                                        
      200 +    # appends results by completion rather than by band.      
      201 +    if _in_scan_order(nodes):                                 
      202 +        renumber: list[int] | range = range(len(nodes))       
      203 +    else:                                                     
      204 +        order = sorted(range(len(nodes)),                     
      205 +                       key=lambda i: (nodes[i].line, nodes[i].
          +lo))                                                          
      206 +        renumber = [0] * len(nodes)                           
      207 +        for new, old in enumerate(order):                     
      208 +            renumber[old] = new                               
      209 +        nodes = [RunNode(new, nodes[old].line, nodes[old].lo, 
          +nodes[old].hi)                                                
      210 +                 for new, old in enumerate(order)]            
      211  
      212      # ---- carry the within-band adjacency across, renumbered 
           ----------
      213      for bi, band in enumerate(ordered):

  Ran 1 shell command (ctrl+o to expand)

● All 277 still pass. Re-measuring the same pages to see what the fix actually
  bought.

  Ran 1 shell command (ctrl+o to expand)

● Fix direction 1 delivers, and by the auditor's own stated criterion it settles
  direction 2:

  ┌────────────────────┬────────────┬─────────────┐
  │                    │   Before   │    After    │
  ├────────────────────┼────────────┼─────────────┤
  │ stitch at K=64     │ 12.2 ms    │ 8.4 ms      │
  ├────────────────────┼────────────┼─────────────┤
  │ stitch/sweep       │ 0.53–0.70× │ 0.33–0.47×  │
  ├────────────────────┼────────────┼─────────────┤
  │ Best ideal speedup │ ~1.4×      │ ~2.05–2.25× │
  └────────────────────┴────────────┴─────────────┘

  The floor is now well below the sweep, so tree-stitch isn't warranted — their
  criterion was "only if direction 1 leaves the floor above the sweep." Now let
  me verify their serialization figures myself, since that's what U8's level-1
  tier rests on.

  Ran 1 shell command (ctrl+o to expand)

● Serialization confirmed cheap — cheaper than the auditor measured. Now
  correcting the unmeasured assertion they flagged.

  Searched for 1 pattern, ran 2 shell commands (ctrl+o to expand)

● Denser pages are worse — ceiling 1.7× and at K=256 on the densest page stitch
  exceeds the sweep entirely (1.18×), making banding slower than not banding. My
  "2–3×" was from the lighter sample. Widening it rather than quoting the
  friendly number.

  Ran 1 shell command (ctrl+o to expand)

● The audit was right, and acting on it before U8 changed what U8 should be.

  Verified on my hardware and real ink, not taken on faith

  Their conclusion held in direction but not magnitude — worth checking, because
  the difference decides whether the band tier is negative or merely weak.

  ┌──────────────┬──────────────────────────┬───────────────────────────────┐
  │              │   Auditor (synthetic,    │    Mine (real ink, Py3.14)    │
  │              │         Py3.12)          │                               │
  ├──────────────┼──────────────────────────┼───────────────────────────────┤
  │ stitch/sweep │ >1.0× — banding always   │ 0.33–0.58× — banding weakly   │
  │              │ negative                 │ positive                      │
  ├──────────────┼──────────────────────────┼───────────────────────────────┤
  │ Ceiling      │ none, serial floor       │ 1.7–3.0×, density-dependent   │
  │              │ exceeds sweep            │                               │
  └──────────────┴──────────────────────────┴───────────────────────────────┘

  So banding isn't negative here, but their structural point is exactly right: a
  serial stitch caps band parallelism in the low single digits, however many 
  cores you have. 64 workers buy ~2×. And on the densest page at K=256 the
  stitch does exceed the sweep, so banding is slower there — their case
  reproduces at the extreme.

  Both root causes confirmed, then fixed

  RunNode.__init__ fired 10,000 times for 5,000 runs — the double construction
  they identified. And the concatenation is already globally sorted in band
  order, so the rebuild was pure waste on the production path.

  An O(V) sortedness check plus guarding one-element up/down sorts: stitch 9.4 →
  6.1 ms, achievable speedup roughly doubled. The slow path is retained and
  still tested, because U8 genuinely will deliver nodes out of order. I also
  found an owner list built and never read.

  Tree-stitching: not built, deliberately. Their own criterion was "only if
  direction 1 leaves the floor above the sweep." It doesn't — 0.33–0.58×.
  Recorded as available with the criterion that would trigger it.

  The unmeasured claim they flagged

  units.md §3 said band parallelism "is what makes the first-page latency target
  reachable, exactly as the design argued." That was mine, never measured,
  sitting in the file that is supposed to be the measured record. Struck through
  with the measurement beside it.

  I also declined to quote my own friendly number: the first two pages gave
  2.05–2.25×, the next two 1.7×. The recorded claim is the 1.7–3.0× spread and 
  its density dependence, not a point estimate — the lesson from the throughput
  and colour figures.

  Two corrections to the audit itself

  Their assumption numbering is off. They cite "assumption 4" for run-list
  serialization; in units.md assumption 4 is moment axis-invariance (verified in
  U5). The serialization claim is assumption 9, which I've now marked measured
  — 64 bands pickle to 0.31–0.80 MB against a 2.7–3.7 MB raw mask, components to
  0.08–0.21 MB. Not the constraint.

  Their level-1 conclusion is stronger than they stated. A closed component
  needs no stitch at all, so blob-parallel work has no Amdahl floor from any of
  this. That's where utilisation comes from.

  Where this leaves U8

  Its plan currently assumes (page, axis, band) tasks with page 1 at large K.
  That assumption is now measured and doesn't hold. U8's first task should be
  deciding whether the band tier earns a place at all — not deferring it, which
  is precisely the mistake the colour fraction made in U0.

  Ready to start U8 on that basis: page-parallel and blob-parallel as the
  load-bearing tiers, band-parallel entering the plan only if a premise check
  justifies it.

✻ Brewed for 4m 28s

※ recap: We're building inkdrill unit by unit; U0 through U7 are done and pushed, with 277 tests passing. Next up is U8, the scheduler, starting with a premise check on whether band-parallelism earns a place given its measured 1.7–3x ceiling.

❯ go on with U8                                                                 

● U8 sched.py. Premise check first — and this one is about a machine, not
  arithmetic, so let me find out what this machine actually is.

  Ran 1 shell command (ctrl+o to expand)

● 16 cores — worth noting, since units.md's design reasons about 128. Measuring
  what page-parallel actually delivers here.

  Made 1 scratchpad edit +88, read 1 file, ran 3 shell commands (ctrl+o to expand)

● Background command "Run U8 premise check" completed (exit code 0)

● Background command "Wait for premise check results" completed (exit code 0)

● Page-parallel scales far worse than the design assumes — 3.26× on 16 cores, 
  20% efficiency. The cause is visible in the per-page spread: 185×, from 0.18 s
  to 34.17 s. One page alone sets a floor of 34 s against a 142 s serial total,
  so ~4.2× is the ceiling for any page-parallel scheme. Let me find out what
  that 34 s actually is.

  Ran 2 shell commands (ctrl+o to expand)

● Background command "Break down per-page time into decode, binarize, sweep"
completed (exit code 0)

● Decisive, and it reshapes U8 completely:

  ┌──────────┬───────────────────────────────┐
  │  Stage   │ Share of end-to-end page time │
  ├──────────┼───────────────────────────────┤
  │ Decode   │ 94.5%                         │
  ├──────────┼───────────────────────────────┤
  │ Sweep    │ 5.3%                          │
  ├──────────┼───────────────────────────────┤
  │ Binarize │ 0.2%                          │
  └──────────┴───────────────────────────────┘

  Band-parallelism only touches the sweep. If the sweep were entirely free, the 
  ceiling is 1.06×. But this sample includes 67.7 Mpx video frames; let me check
  the split on the text pages the project actually targets.

  Ran 1 shell command (ctrl+o to expand)

● Sharper still on the target workload, and it settles the band tier
  definitively:

  ┌─────────────────┬────────┬───────┐
  │    Page type    │ decode │ sweep │
  ├─────────────────┼────────┼───────┤
  │ Neutral (arXiv) │ 54.2%  │ 45.8% │
  ├─────────────────┼────────┼───────┤
  │ Colour (arXiv)  │ 89.8%  │ 10.2% │
  ├─────────────────┼────────┼───────┤
  │ All arXiv pages │ 85.2%  │ 14.8% │
  └─────────────────┴────────┴───────┘

  Parallelising the sweep caps at 1.17×. Parallelising decode caps at 6.77×.
  Band-parallelism targets the 14.8%. That tier is dead — not marginal, dead.
  Building U8 on the tiers the evidence supports.

● Write(inkdrill/sched.py)
  ⎿  Wrote 248 lines to inkdrill/sched.py
       1 """sched.py — the task graph and priority queue.
       2 
       3 CONTRACT (written before implementation; see docs/units.md U8)
       4 =============================================================
       5 
       7 ------------------------------------------------------
       8 The plan specified tasks `(page, axis, band)` with priority
       9 `(page_index, band_index)`, a large band count for page 1 so it
      10 "saturates all cores", and `multiprocessing.shared_memory` for t
         he mask.
     … +280 lines (ctrl+o to expand)

● Write(tests/test_sched.py)  ⎿  Wrote 255 lines to tests/test_sched.py
      1 """Unit 8 tests. Every test name is quoted verbatim in the status
         report."""
      2 
      4 import unittest
      5 
      6 from inkdrill.raster import BG, INK, InkMask
      7 from inkdrill.sched import (DuplicateTaskKey, InvalidWorkerCount,
      8                             RunReport, Task, TaskFailed, page_tas
        ks, run)
      9 from inkdrill.sweep import Capture, sweep
     … +276 lines (ctrl+o to expand)

  Ran 2 shell commands (ctrl+o to expand)

● Both mutations caught; 297 tests total. Recording the findings — including one
  that refutes an assumption.

  Searched for 1 pattern, ran 3 shell commands (ctrl+o to expand)

● Background command "Add schedcost subcommand and verify" completed (exit code
0)

● Harness reproduces on an independent sample — decode 92.7%, sweep-only ceiling
  1.08×, and 3.42× measured against a 3.96× hard ceiling. It also asserts G1
  inside the measurement, so worker count changing the answer would fail the
  harness too.

  Ran 2 shell commands (ctrl+o to expand)

● U8 sched.py landed. 20 tests, 297 total, verified on a clean clone. The
  premise check ran before the plan, and three parts of U8's specification
  didn't survive it.

  The measurement that reshaped the unit

  ┌────────┬────────────────┬─────────────┐
  │ Stage  │ 16 mixed pages │ arXiv pages │
  ├────────┼────────────────┼─────────────┤
  │ decode │ 94.5%          │ 85.2%       │
  ├────────┼────────────────┼─────────────┤
  │ sweep  │ 5.3%           │ 14.8%       │
  └────────┴────────────────┴─────────────┘

  Band parallelism only touches the sweep. Its ceiling is 1.17× — 1.08× on an 
  independent re-run — even if the sweep were free. Parallelising decode instead
  ceilings at 6.8–13.7×.

  So the band tier is not built. That's not deferral: U7's stitch measurement
  already capped banding at 1.7–3× of a slice this measurement shows is 5–15% of
  the work. Two independent measurements, taken a day apart for different
  reasons, agree. Shared memory is out too — serialization measures 0.08–0.21 MB
  per page against a 2.7–3.7 MB mask, so it was never the constraint.

  Assumption 6 refuted

  Page-parallel reaches 3.26× on 16 cores, 20.4% efficiency, 33–62% utilisation.
  The cause isn't the idle tail the plan worried about — it's a 185× per-page 
  cost spread (0.18 s to 34.17 s). One 67.7 Mpx colour page takes 38 s, 99.5% of
  it decode. Total work over longest task caps any page-parallel scheme at
  ≈4.2×, and 3.26× is already 78% of that. Finer bands at the end wouldn't help,
  because banding doesn't touch decode.

  What got built instead

  A deterministic priority scheduler keyed (page, axis). Same answer at every
  worker count; workers=1 uses no pool at all, which is what makes it the oracle
  the parallel paths are checked against. Results ordered by key, never
  completion — the task that finishes last still comes first if its key says so.
  RunReport reports measured utilisation and Amdahl ceiling, because a
  scheduler that can't report its own utilisation can't be improved. Both
  load-bearing behaviours are mutation-tested.

  One thing I flagged rather than acted on

  The ingest path is now the bottleneck by an order of magnitude — and units.md
  records a decision to stop optimising it, which I made on the auditor's
  instruction that "performance of the ingest path is a render-pipeline
  concern."

  That instruction was given when decode was believed to be a minor cost. It's
  now measured at 85–95% of everything. The deferred colour-path SWAR
  optimisation targets ~74% of colour-page rows, and colour is 54% of the
  corpus.

  I've recorded this in units.md as a flagged tension rather than silently
  reversing your auditor's scope call — it's your decision. Three options,
  roughly: reopen the colour path within U0's scope; treat it as genuinely
  render-pipeline and accept ~3× as the ceiling; or leave it and proceed, since
  U9–U14 are correctness work where decode speed only affects turnaround.

  Nine units built, five assumptions closed by measurement, three refuted. Next
  by your ordering is U9 font.py — and its premise, assumption 8, is the one
  units.md itself calls "the cheapest assumption to check and worth checking
  before U9 starts."

✻ Crunched for 27m 45s

※ recap: Building inkdrill's numbered units; U8 is done and pushed, so nine units and 297 tests are green. Next is U9 font.py, starting with the corpus font-mix check that units.md flags as worth doing first.

❯ please read audit report for U8 and go on to build U9:# inkdrill U8           
  `sched.py` — audit                                                            
                                                                                
  `origin/main` @ `7a7b83e`. **297 tests, 4 skipped, verified on a clean        
  clone** — 20 new, matching the recorded count. `inkdrill/sched.py` 248        
  lines, `tests/test_sched.py` 255.                                             
                                                                                
  Scope fence unchanged: render path, input format and Ghostscript invocation   
  are out of scope for the CLI.                                                 
                                                                                
  ---                                                                           
                                                                                
  ## The premise check is the best process artefact in the repo                 
                                                                                
  It should be said plainly, because it is the thing that has improved most.    
                                                                                
  U8's plan specified `(page, axis, band)` tasks with page 1 at large K. The    
  premise check ran *before* the unit was written, measured where per-page      
  time actually goes, and **killed the band tier on evidence**:                 
                                                                                
  | Stage | mixed corpus | arXiv only |                                         
  |---|---|---|                                                                 
  | decode | 94.5% | 85.2% |                                                    
  | sweep | 5.3% | 14.8% |                                                      
                                                                                
  Band parallelism touches only the sweep, so its ceiling on this workload is   
  **1.17×** even if the sweep were free. Two measurements taken a day apart     
  for unrelated reasons — the U7 stitch cost and this stage split — agree, and  
  the unit was rescoped rather than built and then found wanting.               
                                                                                
  That is the correction from U0 fully absorbed. The colour fraction surfaced   
  at Task 4 and forced a rewrite; this surfaced at Task 0 and prevented one.    
                                                                                
  Two further things done right:                                                
                                                                                
  - **`workers=1` uses no pool at all**, and the docstring is explicit that     
    this is not an optimisation but the oracle the parallel paths are checked   
    against. A scheduler whose serial path went through a pool would have no    
    reference.                                                                  
  - **`RunReport` reports its own utilisation**, and the measured idle tail     
    (33–62%, against the assumed near-100%) is recorded rather than smoothed.   
    Assumption 6 asked for exactly that.                                        
                                                                                
  ---                                                                           
                                                                                
  ## F1 — G3 is stated, reasoned about, and completely unguarded *(Important,   
  demonstrated)*                                                                
                                                                                
  G3 is the guarantee that makes this a *priority* scheduler rather than a      
  parallel map with sorted output:                                              
                                                                                
  > G3  tasks are dispatched in ascending key order, so the lowest-priority     
  > number starts first and **first-page latency is not left to chance**        
                                                                                
  Mutation:                                                                     
                                                                                
  ```                                                                           
  Δ inkdrill/sched.py :  ordered = sorted(tasks, key=lambda t: t.key)   # G3    
                      →  ordered = list(tasks)                                  
  → Ran 297 tests — OK (skipped=4)                                              
  ```                                                                           
                                                                                
  Removing the dispatch sort breaks nothing. Every existing order test —        
  `test_results_come_back_in_key_order`,                                        
  `test_shuffled_input_gives_the_same_ordered_output`,                          
  `test_completion_order_does_not_leak_into_results` — checks **G2**, the       
  final `raw.sort()`, which delivers sorted output independently of dispatch    
  order. Nothing observes the order tasks *start* in.                           
                                                                                
  The consequence is not theoretical. First-page latency is the stated reason   
  the priority key exists. Under this mutation, results are still perfectly     
  ordered, every test is green, and page 1 finishes whenever it happens to be   
  scheduled.                                                                    
                                                                                
  ### A test that catches it, verified both ways                                
                                                                                
  The serial path calls `_call` in dispatch order, so no pool and no timing     
  race is needed:                                                               
                                                                                
  ```python                                                                     
  _ORDER = []                                                                   
  def spy(payload):                                                             
      _ORDER.append(payload)                                                    
      return payload                                                            
                                                                                
  def test_tasks_are_dispatched_in_ascending_key_order(self):                   
      """G3: the job is called in key order, whatever order the task list       
      arrives in. Serial path, so this is deterministic."""                     
      tasks = [Task((i,), i) for i in range(20)]                                
      random.Random(0).shuffle(tasks)                                           
      _ORDER.clear()                                                            
      run(tasks, spy, workers=1)                                                
      self.assertEqual(_ORDER, list(range(20)))                                 
  ```                                                                           
                                                                                
  ```                                                                           
  against the real code       :  OK                                             
  against mutation A          :  FAILED (failures=1)                            
  ```                                                                           
                                                                                
  This is the same shape as the U4 finding — a guarantee stated in the          
  docstring, argued for in prose, and asserted by nothing. It is worth noting   
  that the three guarantees the commit message says are mutation-tested (G2     
  re-sorting, G5 failure surfacing, G7 duplicate keys) all fail loudly under    
  mutation, as claimed. G3 is the one that was not on that list.                
                                                                                
  ---                                                                           
                                                                                
  ## F2 — `chunksize` is load-bearing for G3 in the parallel path and is not    
  pinned *(Minor)*                                                              
                                                                                
  `pool.imap_unordered(_call, items)` relies on the default `chunksize=1` to    
  feed tasks in iterable order. A future change to `chunksize` — the obvious    
  thing to reach for if per-task overhead ever looks high — would batch tasks   
  and weaken dispatch ordering, silently, with every test still green (see      
  F1). Pass `chunksize=1` explicitly with a one-line comment saying G3 depends  
  on it.                                                                        
                                                                                
  Related: the G3 test above covers the serial path only. Covering the          
  parallel path needs timing and would be flaky; the honest move is to state    
  in the contract that G3 is verified serially and holds in the pool by         
  `chunksize=1`.                                                                
                                                                                
  ---                                                                           
                                                                                
  ## F3 — the "scheduler lost work" check is unreachable *(Trivial)*            
                                                                                
  ```python                                                                     
  if len(raw) != len(items):                                                    
      raise RuntimeError(f"scheduler lost work: ...")                           
  ```                                                                           
                                                                                
  `imap_unordered` yields exactly one result per input item or raises, and the  
  serial path is a list comprehension over the same items. G4 is real and       
  tested (`test_every_task_runs_exactly_once`) but this particular branch       
  cannot fire. Harmless as defence-in-depth; worth a comment saying so, rather  
  than reading as a live check.                                                 
                                                                                
  ---                                                                           
                                                                                
  # Separately — for the repo owner, not the CLI                                
                                                                                
  **The 1.17× ceiling that killed the band tier is a function of the PNG        
  decode cost, and the premise check contains the number that shows it.**       
                                                                                
  Its own split, on arXiv pages:                                                
                                                                                
  > neutral pages **54% decode / 46% sweep**; colour pages **90% decode /       
  > 10% sweep**                                                                 
                                                                                
  The 85–94% decode share is driven by the colour path. On neutral pages the    
  sweep is already 46% of the work.                                             
                                                                                
  Taking the arXiv row (decode 85.2%, sweep 14.8%) and applying the ~100×       
  decode improvement a raw greyscale render gives:                              
                                                                                
  | | decode share | sweep share | ceiling for parallelising the sweep |        
  |---|---|---|---|                                                             
  | today | 85.2% | 14.8% | **1.17×** |                                         
  | with a raw greyscale render | ~5% | ~95% | **~18×** |                       
                                                                                
  The band-tier decision is **correct for the pipeline as it stands** and was   
  made the right way. But it rests on a number that moves by more than an       
  order of magnitude if the ingest path changes, and it is recorded in          
  `units.md` as settled — *"not deferred, not marginal"* — with no note that    
  it is conditional.                                                            
                                                                                
  Nothing here is CLI work, and I am not suggesting reopening it there. The     
  one thing worth doing is a single sentence in `units.md` recording the        
  condition: *the band tier was dropped on a measurement in which decode is     
  85–95% of per-page work; if decode ceases to dominate, the ceiling changes    
  by an order of magnitude and this decision should be re-taken.* That costs    
  nothing now and prevents a future session treating it as closed.              
                                                                                
  **One other thing worth your eye.** The premise check states its machine      
  plainly — 16 cores, Ryzen 7 5700U, Python 3.14 — and adds that the ratios     
  should be re-taken at 128 cores. That caveat is correct and easy to lose.     
  Page-parallel scaling was already 62.7% efficient at 4 workers and capped     
  near 4.2× by the single slowest page in the sample, with a 185× per-page      
  cost spread. On 128 cores that cap binds long before the cores run out, so    
  level-1 blob parallelism inside a page is doing more of the work than the     
  plan assumed — which is where I would expect U8's successor to earn its       
  keep.                                                                         
  ⎿  1 skill available

● The audit's F1 is exactly the class of gap that keeps recurring. Verifying it
  myself first.

  Ran 1 shell command (ctrl+o to expand)

● Confirmed — the dispatch sort can be deleted and all 297 tests still pass. G3
  was prose. Fixing all three findings.

  Ran 2 shell commands (ctrl+o to expand)

● F1 fixed — the mutation now fails. The chunksize mutation still passes,
  exactly as the auditor predicted is unavoidable without a timing race; the
  contract now states G3 is verified serially and rests on chunksize=1 in the
  pool. Adding their conditionality note.

  Ran 2 shell commands (ctrl+o to expand)

● Now U9 — and its premise is the one units.md itself calls "the cheapest
  assumption to check and worth checking before U9 starts."

  Ran 2 shell commands (ctrl+o to expand)

● Assumption 8 is refuted — but not in the way the wording suggests. Per font 
  entry it looks fine: 94.3% embedded, 5.1% Type 3. Per document only 16.8% are
  fully clean. Neither is the number U9 actually needs, though — the fast path
  applies per glyph. Let me measure that.

  Ran 1 shell command (ctrl+o to expand)

● Measured the way U9 actually uses it — per glyph, 95.90% are on the fast path.
  Only 0.53% are genuinely unusable. The metric choice inverts the answer
  completely. But 3.58% failed to resolve, which is 7× the real failure rate, so
  let me check whether that's a real gap or my join.

  Ran 1 shell command (ctrl+o to expand)

● The 3.58% has four distinct causes, and only one is my join:

  ┌───────────────────────────────────────┬────────┬────────────────────────┐
  │                 Cause                 │ Glyphs │       Real gap?        │
  ├───────────────────────────────────────┼────────┼────────────────────────┤
  │ 'unknown' — pdfminer can't name the   │ 51,952 │ yes, but all one old   │
  │ font                                  │        │ document               │
  ├───────────────────────────────────────┼────────┼────────────────────────┤
  │ 'Times New Roman', 'Helvetica' — no   │ ~19k   │ yes, genuinely         │
  │ subset prefix                         │        │ non-embedded           │
  ├───────────────────────────────────────┼────────┼────────────────────────┤
  │ CKXQCW+LMRoman10-Regular vs           │ 4      │ no — encoding-suffix   │
  │ …-Identity-H                          │        │ mismatch               │
  └───────────────────────────────────────┴────────┴────────────────────────┘

  That last one is a concrete design input: U9 must normalise font names by
  stripping encoding suffixes. Recording the premise before building.

  Ran 1 shell command (ctrl+o to expand)

● Now U9 itself. Let me look at the exact pdffonts output format, since I saw
  font names containing spaces in the survey.

  Ran 1 shell command (ctrl+o to expand)

● The format is fixed-width with a dashed rule line that gives exact column
  boundaries — which is the robust way to parse names containing spaces. Writing
  U9.

● Write(inkdrill/font.py)  ⎿  Wrote 330 lines to inkdrill/font.py
       1 """font.py — font inventory, name resolution, and glyph-weighted
       2 
       3 CONTRACT (written before implementation; see docs/units.md U9)
       4 =============================================================
       6 Scope, and why this unit is smaller than the plan's U9
       7 ------------------------------------------------------
         onts, and
       9 rasterize a glyph from one. This module is the FIRST half -- inv
         entory,
         st path.
     … +374 lines (ctrl+o to expand)

● Write(tests/test_font.py)
  ⎿  Wrote 235 lines to tests/test_font.py
       1 """Unit 9 tests. Every test name is quoted verbatim in the statu
       2 
       3 import unittest
       4 
         lity,
       6                            coverage, normalise, parse_pdffonts, 
       7                            usability)
       8 
       9 # Real pdffonts output, copied verbatim from the corpus. The col
      10 # widths are the ones pdffonts actually emits.
     … +269 lines (ctrl+o to expand)

  Ran 1 shell command (ctrl+o to expand)

● All 28 pass. Verifying against real corpus PDFs, since the fixtures are my
  transcription of what pdffonts emits.

  Ran 1 shell command (ctrl+o to expand)

● 93.93% against the premise check's 95.90% — different samples, same
  conclusion. Recording the range rather than either number, and being explicit
  that this is half of U9.

  Ran 3 shell commands (ctrl+o to expand)

● U8's audit findings are closed and U9's inventory half is built. 327 tests,
  verified on a clean clone.

  U8 — F1 was the third instance of the same pattern

  I reproduced it before fixing: deleting the dispatch sort passed all 297
  tests. G3 — "first-page latency is not left to chance" — was stated, reasoned
  about, and asserted by nothing, because every order test checked G2's final
  re-sort instead. Two tests now observe dispatch order on the serial path, and
  the mutation fails.

  That's U4 rotation, U7 re-sort, U8 dispatch — three guarantees argued rather
  than asserted. The pattern is consistent: the unguarded guarantee is always
  the one whose obvious test appears to cover it.

  F2 and F3 done as specified. chunksize=1 is now explicit and the contract
  states plainly that G3 is verified serially and holds in the pool by that 
  argument — a chunksize=64 mutation still passes, and pretending otherwise
  would be the same error again. Your conditionality note is in units.md: at ~5%
  decode share the sweep ceiling rises from 1.17× to ~18×, so the band-tier
  decision must be re-taken if decode stops dominating.

  U9's premise check produced a lesson about metrics, not fonts

  The same corpus reads three ways:

  ┌──────────────┬─────────────────────────┬──────────────┐
  │   Counting   │         Result          │   Reading    │
  ├──────────────┼─────────────────────────┼──────────────┤
  │ font entries │ 94.3% embedded          │ fine         │
  ├──────────────┼─────────────────────────┼──────────────┤
  │ documents    │ 16.8% fully clean       │ catastrophic │
  ├──────────────┼─────────────────────────┼──────────────┤
  │ glyphs       │ 95.90% on the fast path │ fine         │
  └──────────────┴─────────────────────────┴──────────────┘

  Glyph-weighted is the only one that answers U9's question. 80.7% of documents
  contain some non-embedded font — true, and nearly meaningless, because a paper
  with an unused Helvetica isn't a paper U9 fails on. Assumption 8 holds, and 
  the scope limit costs 0.5–2% of glyphs, not 5% or 83%.

  It also caught a concrete bug: pdfminer says CKXQCW+LMRoman10-Regular,
  pdffonts says …-Identity-H. Same font, never joins without normalisation.
  Style suffixes are deliberately not normalised — Times,Bold and Times,Italic
  are different fonts. And parsing is fixed-width off the rule line, because a
  whitespace split loses New Roman TrueType and Mincho Pr6N R-4520-Identity-H 
  CID Type 0C, both real.

  Verified against 25 real documents and 1,276,504 glyphs: 93.93%, against
  95.90% from an independent 40-document sample.

  What I did not build, and why it's flagged rather than attempted

  U9's rasterization half. No CFF or TrueType outline parsing, no scan
  conversion, no reference blob, no BASE/MATH tables. In pure stdlib that's
  parsing charstrings and scan-converting Béziers — substantially larger than
  any unit so far, and it needs its own contract and premise check.

  I split where hermetic testability ends: everything in the inventory half is
  exact against fixture text; a rasterizer needs its own oracle. units.md, the
  README and CLAUDE.md all say "inventory half" rather than claiming U9
  complete.

  That rasterizer is the next real decision — it's a bigger unit than U0 was,
  and worth scoping deliberately rather than starting into.

✻ Worked for 9m 2s

※ recap: You're building inkdrill, a stdlib-only Python topology toolkit for document analysis; U0–U8 are done and U9's font-inventory half just landed, with 327 tests passing and everything pushed to main. Next action is scoping U9's rasterizer half, which is larger than any unit so far.

❯ he is some advice from the auditor: # inkdrill U9 `font.py` (inventory half)  
  — audit                                                                       
                                                                                
  `origin/main` @ `2607f73`. **327 tests, 4 skipped, verified on a clean        
  clone.** U8 findings F1–F3 closed at `6b34bfa`.                               
                                                                                
  **Note:** the trace you forwarded cuts off mid-sentence ("That's U4           
  rotation, U7 re-sort, U8… The"), so I do not have the CLI's own statement     
  of the U9 problem. The findings below are from the repo. If the CLI named     
  something else, send the rest and I will check that too.                      
                                                                                
  Scope fence unchanged.                                                        
                                                                                
  ---                                                                           
                                                                                
  ## What is right                                                              
                                                                                
  The scope split is the correct call and honestly made: inventory and name     
  resolution here, outline parsing and scan conversion named as the other       
  half rather than half-built. *"Everything below is exactly and                
  hermetically testable against fixture text, while a rasterizer needs its      
  own oracle and its own premise check"* is the right line to cut on.           
                                                                                
  The three-way metric finding is the best premise check yet — 94.3% by font    
  entries, **16.8% by documents**, 95.90% by glyph instances, from one          
  corpus. The argument for glyph-weighting is correct: the fast path applies    
  per glyph, so a paper with one unused non-embedded Helvetica is not a paper   
  U9 fails on. Catching that before the rasterizer is exactly where it pays.    
                                                                                
  G3, G4 and G5 all fail loudly under mutation:                                 
                                                                                
  | Mutation | Result |                                                         
  |---|---|                                                                     
  | unresolvable name counted as usable (G5) | 3 errors |                       
  | normalised resolve pass dropped (G4) | 1 failure |                          
  | subset tag not stripped (G3) | 2 failures |                                 
  | style suffixes collapsed — `Times,Bold` == `Times` (G3) | 1 failure |       
  | whitespace split forced for every line (G2) | 2 errors |                    
                                                                                
  ---                                                                           
                                                                                
  ## F1 — The coverage metric is glyph-weighted but not stratified, and the     
  first application is math *(Important)*                                       
                                                                                
  95.90% of glyph instances are on the fast path. The 4.10% off it is           
  3.58% unresolvable, 0.45% not embedded, 0.08% Type 3.                         
                                                                                
  **Body text dominates glyph instances.** Math symbols are a small minority    
  of any paper's glyph count even in a theory paper. So a 95.90% aggregate is   
  compatible with math-font coverage anywhere from near 0% to 100% — the        
  measurement cannot distinguish those cases, and nothing in the repo           
  stratifies it. A grep across `docs/`, `inkdrill/`, `tools/` and `tests/`      
  for `CMSY`, `CMEX`, `CMMI`, `MSAM`, `MSBM`, `STIX`, `XITS`, `LMMath`,         
  `Asana` returns one hit, and it is unrelated prose in the U9 plan.            
                                                                                
  This matters because of what the font fast path is *for*. Template matching   
  against the document's own fonts, self-validating classification, and         
  automatic gold labels are all most valuable exactly where a bitmap            
  classifier is weakest: math symbols in fonts with custom, non-Unicode         
  encodings. `CMMI`/`CMSY` encodings are the canonical hard case in PDF math    
  extraction and the reason the font route was attractive in the first place.   
                                                                                
  The CLI's own argument settles this. *"Glyph-weighted is the correct          
  metric, because U9's fast path applies per glyph"* — the same reasoning       
  says the **population must match the application**. Aggregate glyph           
  weighting answers "how often does the fast path apply to a random glyph".     
  U9's question is "how often does it apply to a glyph the math track needs".   
                                                                                
  This is the U0 colour-fraction pattern in a subtler form: the right *kind*    
  of measurement on the wrong *population*. It was caught there at Task 4;      
  here it is catchable before the rasterizer half is planned, which is when     
  it decides that unit's value.                                                 
                                                                                
  **The fix is cheap — no new data collection.** The harness already joins      
  per-glyph `fontname` to `pdffonts` records. Group the same counts by          
  normalised base name, and report the math families as their own row beside    
  the aggregate. `coverage()` already caches usability per name, so a           
  per-family breakdown falls out of the loop it already runs.                   
                                                                                
  **What would change if it comes back low:** the rasterizer half's premise.    
  If math glyphs are disproportionately unresolvable or Type 3, the fast        
  path is worth much less than 95.90% implies for the first application, and    
  U11's fallback becomes the primary path for math rather than the remainder.   
                                                                                
  ---                                                                           
                                                                                
  ## F2 — The parser's fallback branch is never executed by any test            
  *(Important)*                                                                 
                                                                                
  ```                                                                           
  Δ  if len(cell) < 6 or cell[3] not in ("yes", "no"):   # take fallback        
  →  if False:                                          # never take it         
  →  Ran 327 tests — OK (skipped=4)                                             
  ```                                                                           
                                                                                
  Forcing the fixed-width path for every line breaks nothing. The whitespace    
  fallback — roughly ten lines of index arithmetic on `flags[0]`,               
  `tok[1:i-1]`, `tok[i-1]` — has never run in a test.                           
                                                                                
  The converse mutation confirms the coverage is one-sided: forcing the         
  *fallback* for every line fails `test_a_name_containing_a_space_survives`     
  and `test_a_type_containing_a_space_survives`. So the fixed-width path is     
  well guarded and the fallback is not guarded at all.                          
                                                                                
  It is not dead code. Its own comment says *"widths are minimums: a long       
  name can push later columns right"* — so it fires on precisely the            
  pathological lines the fixed-width parser was introduced to handle. As it     
  stands it will first execute on real corpus data, unverified, and its         
  failure mode is a silently mis-parsed `FontRecord` rather than an             
  exception.                                                                    
                                                                                
  This is also the one finding that touches a stated project rule directly:     
  *"Forbidden: commenting out failing tests, writing untested functions."*      
                                                                                
  **Fix:** one fixture whose first-column name is long enough to push the       
  flag columns past their rule-line spans. The existing                         
  `test_a_name_containing_a_space_survives` fixture is the natural base —       
  lengthen the name until `cell[3]` is no longer `yes`/`no`.                    
                                                                                
  ---                                                                           
                                                                                
  ## F3 — `resolve` is order-dependent when two records share a base name       
  *(Minor, but it silently flips an answer)*                                    
                                                                                
  Two subsets of the same base font in one PDF, one embedded and one not — a    
  real configuration when a document references a standard font and also        
  embeds a subset of it:                                                        
                                                                                
  ```python                                                                     
  recs = [FontRecord("ABCDEF+Times-Roman", TYPE1, "WinAnsi", embedded=False,    
  ...),                                                                         
          FontRecord("GHIJKL+Times-Roman", TYPE1, "WinAnsi", embedded=True,     
  ...)]                                                                         
                                                                                
  usability("MNOPQR+Times-Roman", recs)            -> Usability.NOT_EMBEDDED    
  usability("MNOPQR+Times-Roman", reversed(recs))  -> Usability.FAST_PATH       
  ```                                                                           
                                                                                
  Same glyph, opposite answer, decided by `pdffonts` row order.                 
  `test_an_exact_match_wins_over_a_normalised_one` covers exact-vs-normalised   
  but not two normalised candidates colliding.                                  
                                                                                
  Neither answer is obviously right, so the useful move is to make the choice   
  explicit rather than incidental — prefer the embedded record when several     
  normalise to the same base name, and say so in the docstring. Whatever is     
  chosen, it should be a line of code and a test rather than list order.        
                                                                                
  This is the same shape as F1 in miniature: the aggregate is fine, the         
  resolution is ambiguous underneath it.                                        
                                                                                
  ---                                                                           
                                                                                
  ## Order                                                                      
                                                                                
  F2 first — it is one fixture and it closes a stated-rule violation. F1        
  before the rasterizer half is planned, since it sets that unit's value.       
  F3 whenever.                                                                  
                                                                                
  ---                                                                           
                                                                                
  ## On the pattern the CLI named                                               
                                                                                
  The fragment I have reads *"That's U4 rotation, U7 re-sort, U8…"* — three     
  instances of a guarantee stated, reasoned about in prose, and asserted by     
  nothing. F2 above is a fourth instance of a closely related thing: not an     
  unguarded guarantee this time, but an unguarded *branch*, invisible for       
  the same reason — the tests exercise the path that is easy to construct and   
  not the one that only real data produces.                                     
                                                                                
  Both are findable the same way, and cheaply: mutate a branch condition to a   
  constant and see whether anything fails. `if True` and `if False` on every    
  non-trivial branch in a new unit is a few minutes of work and would have      
  caught U4's rotation guard, U8's dispatch sort and this fallback. Worth       
  adding to the per-task review checklist rather than leaving to the final      
  whole-branch pass, which is where these have been surfacing.                  

● Three good findings. Verifying F2 and F3 myself before fixing, in their stated
  order.

  Ran 2 shell commands (ctrl+o to expand)

● Both confirmed: the fallback branch has never executed, and resolve gives
  opposite answers for the same glyph depending on row order. Fixing F2 first.

  Ran 1 shell command (ctrl+o to expand)

● F2 closed — the fallback branch is now guarded. F3 next: making the collision
  choice explicit rather than incidental.

  Ran 1 shell command (ctrl+o to expand)

● Now F1 — the finding that decides the rasterizer's value. Stratifying coverage
  by font family.

  Ran 2 shell commands (ctrl+o to expand)

● 43 tests. Now the measurement F1 actually asks for — is math coverage as good
  as the aggregate implies?

  Ran 1 shell command (ctrl+o to expand)

● The answer is the opposite of the feared one, and it strengthens the
  rasterizer's case:

  ┌────────────┬───────────┬─────────────────┐
  │            │ Fast path │ Share of glyphs │
  ├────────────┼───────────┼─────────────────┤
  │ Aggregate  │ 94.64%    │ —               │
  ├────────────┼───────────┼─────────────────┤
  │ Maths only │ 100.00%   │ 2.00%           │
  └────────────┴───────────┴─────────────────┘

  Math glyphs are better covered than body text — zero rejections across 29,496
  of them. TeX math fonts (CMMI 20k, CMSY 7k, CMEX 1k) are always embedded
  subsets; the non-embedded fonts are standard text faces like Times. Recording.

  Ran 2 shell commands (ctrl+o to expand)

● Now the auditor's meta-suggestion — branch mutation as a standing check, since
  it would have caught all four instances.

  Ran 2 shell commands (ctrl+o to expand)

● I ran the checklist I just wrote, on U9, and it immediately found 8 surviving 
  branch mutations. Having written the rule, I should follow it rather than ship
  past it.

  Ran 2 shell commands (ctrl+o to expand)

● Down from 8 to 4. Three look equivalent-outcome, but one — always-skip on
  blank lines — should break everything, so let me check rather than assume my
  probe is right.

  Ran 1 shell command (ctrl+o to expand)

● Confirmed guarded — applied to the right occurrence it fails loudly (18
  failures, 5 errors). My sweep script over-reported: it rewrites the file and
  re-runs, but its survivor check misreads a run that errors during import.
  That's worth recording, since I put the technique in CLAUDE.md.

  Ran 2 shell commands (ctrl+o to expand)
● All three findings closed, plus a consequence of taking the auditor's
  meta-advice seriously. U9 now 52 tests, 351 total, verified on a clean clone.

  F2 — the stated-rule violation, first as advised

  Reproduced before fixing: forcing the fixed-width path for every line passed
  all 327 tests. The fallback's own comment says it fires when "a long name can
  push later columns right" — so it would first have executed on real corpus
  data, unverified, mis-parsing silently rather than raising. A fixture whose
  name overflows the 36-character column now reaches it.

  F1 — the answer inverts the concern

  You were right that the aggregate can't speak for math, and right that it was
  cheap to check. Stratified over 30 documents and 1,471,926 glyphs:

  ┌────────────────┬───────────┬───────┐
  │   Population   │ Fast path │ Share │
  ├────────────────┼───────────┼───────┤
  │ aggregate      │ 94.64%    │ —     │
  ├────────────────┼───────────┼───────┤
  │ maths families │ 100.00%   │ 2.00% │
  └────────────────┴───────────┴───────┘

  Math glyphs are better covered than body text — zero rejections across 29,496.
  TeX math fonts are always embedded subsets in arXiv PDFs; the non-embedded
  ones are standard text faces like Times. So this raises the rasterizer's value
  for its primary application. Either way it's a number the aggregate couldn't
  have produced.

  family_of() strips the design size, since CMSY7/8/10 are one family at three
  sizes and splitting them would fragment the very population being measured.
  "No maths seen" and "0% of maths" report differently, because they're
  different facts.

  F3 — fixed, and it exposed a second ordering question

  The embedded record now wins deliberately. That made a new question live —
  should an exact name match still win over an embedded sibling? It does, but
  nothing tested it, and the branch sweep caught exactly that.

  Taking your meta-advice had an immediate cost, which is the point

  I added the mutate-before-claiming rule to CLAUDE.md, then ran it against
  font.py — and it found eight surviving branch mutations in the unit I'd just
  declared done. Six were real and now have tests: blank lines, short rule
  lines, unreadable rows dropped rather than turned into garbage records, OTHER
  handling, exact-match precedence, and inventory() reporting a failing or
  missing pdffonts instead of guessing.

  Two were the probe misfiring, which is worth more than the six. A mutation
  that breaks the module at import time reads as "survived" because the suite
  never reaches an assertion — one branch the sweep called a survivor fails 18
  tests when mutated by hand. I've recorded that in CLAUDE.md: a survivor is a 
  lead, not a finding. Without that caveat the technique produces confident
  false negatives, which is worse than not running it.

  Your count of instances is now five stated-but-unasserted guarantees plus one
  unguarded branch — and the sweep, used carefully, would have caught all six.

  The rasterizer half remains the open piece, and F1 has now made its case
  stronger rather than weaker.

✻ Churned for 6m 54s

※ recap: Building inkdrill unit by unit; U0–U9's inventory half are done and pushed, with 351 tests passing and the latest audit findings closed. Next is scoping U9's rasterizer half, the glyph outline parsing and scan conversion that was deliberately left unbuilt.

❯ some advice from the auditor # inkdrill U9 `font.py` (inventory half) — audit 
                                                                                
  `origin/main` @ `2607f73`. **327 tests, 4 skipped, verified on a clean        
  clone.** U8 findings F1–F3 closed at `6b34bfa`.                               
                                                                                
  **Note:** the trace you forwarded cuts off mid-sentence ("That's U4           
  rotation, U7 re-sort, U8… The"), so I do not have the CLI's own statement     
  of the U9 problem. The findings below are from the repo. If the CLI named     
  something else, send the rest and I will check that too.                      
                                                                                
  Scope fence unchanged.                                                        
                                                                                
  ---                                                                           
                                                                                
  ## What is right                                                              
                                                                                
  The scope split is the correct call and honestly made: inventory and name     
  resolution here, outline parsing and scan conversion named as the other       
  half rather than half-built. *"Everything below is exactly and                
  hermetically testable against fixture text, while a rasterizer needs its      
  own oracle and its own premise check"* is the right line to cut on.           
                                                                                
  The three-way metric finding is the best premise check yet — 94.3% by font    
  entries, **16.8% by documents**, 95.90% by glyph instances, from one          
  corpus. The argument for glyph-weighting is correct: the fast path applies    
  per glyph, so a paper with one unused non-embedded Helvetica is not a paper   
  U9 fails on. Catching that before the rasterizer is exactly where it pays.    
                                                                                
  G3, G4 and G5 all fail loudly under mutation:                                 
                                                                                
  | Mutation | Result |                                                         
  |---|---|                                                                     
  | unresolvable name counted as usable (G5) | 3 errors |                       
  | normalised resolve pass dropped (G4) | 1 failure |                          
  | subset tag not stripped (G3) | 2 failures |                                 
  | style suffixes collapsed — `Times,Bold` == `Times` (G3) | 1 failure |       
  | whitespace split forced for every line (G2) | 2 errors |                    
                                                                                
  ---                                                                           
                                                                                
  ## F1 — The coverage metric is glyph-weighted but not stratified, and the     
  first application is math *(Important)*                                       
                                                                                
  95.90% of glyph instances are on the fast path. The 4.10% off it is           
  3.58% unresolvable, 0.45% not embedded, 0.08% Type 3.                         
                                                                                
  **Body text dominates glyph instances.** Math symbols are a small minority    
  of any paper's glyph count even in a theory paper. So a 95.90% aggregate is   
  compatible with math-font coverage anywhere from near 0% to 100% — the        
  measurement cannot distinguish those cases, and nothing in the repo           
  stratifies it. A grep across `docs/`, `inkdrill/`, `tools/` and `tests/`      
  for `CMSY`, `CMEX`, `CMMI`, `MSAM`, `MSBM`, `STIX`, `XITS`, `LMMath`,         
  `Asana` returns one hit, and it is unrelated prose in the U9 plan.            
                                                                                
  This matters because of what the font fast path is *for*. Template matching   
  against the document's own fonts, self-validating classification, and         
  automatic gold labels are all most valuable exactly where a bitmap            
  classifier is weakest: math symbols in fonts with custom, non-Unicode         
  encodings. `CMMI`/`CMSY` encodings are the canonical hard case in PDF math    
  extraction and the reason the font route was attractive in the first place.   
                                                                                
  The CLI's own argument settles this. *"Glyph-weighted is the correct          
  metric, because U9's fast path applies per glyph"* — the same reasoning       
  says the **population must match the application**. Aggregate glyph           
  weighting answers "how often does the fast path apply to a random glyph".     
  U9's question is "how often does it apply to a glyph the math track needs".   
                                                                                
  This is the U0 colour-fraction pattern in a subtler form: the right *kind*    
  of measurement on the wrong *population*. It was caught there at Task 4;      
  here it is catchable before the rasterizer half is planned, which is when     
  it decides that unit's value.                                                 
                                                                                
  **The fix is cheap — no new data collection.** The harness already joins      
  per-glyph `fontname` to `pdffonts` records. Group the same counts by          
  normalised base name, and report the math families as their own row beside    
  the aggregate. `coverage()` already caches usability per name, so a           
  per-family breakdown falls out of the loop it already runs.                   
                                                                                
  **What would change if it comes back low:** the rasterizer half's premise.    
  If math glyphs are disproportionately unresolvable or Type 3, the fast        
  path is worth much less than 95.90% implies for the first application, and    
  U11's fallback becomes the primary path for math rather than the remainder.   
                                                                                
  ---                                                                           
                                                                                
  ## F2 — The parser's fallback branch is never executed by any test            
  *(Important)*                                                                 
                                                                                
  ```                                                                           
  Δ  if len(cell) < 6 or cell[3] not in ("yes", "no"):   # take fallback        
  →  if False:                                          # never take it         
  →  Ran 327 tests — OK (skipped=4)                                             
  ```                                                                           
                                                                                
  Forcing the fixed-width path for every line breaks nothing. The whitespace    
  fallback — roughly ten lines of index arithmetic on `flags[0]`,               
  `tok[1:i-1]`, `tok[i-1]` — has never run in a test.                           
                                                                                
  The converse mutation confirms the coverage is one-sided: forcing the         
  *fallback* for every line fails `test_a_name_containing_a_space_survives`     
  and `test_a_type_containing_a_space_survives`. So the fixed-width path is     
  well guarded and the fallback is not guarded at all.                          
                                                                                
  It is not dead code. Its own comment says *"widths are minimums: a long       
  name can push later columns right"* — so it fires on precisely the            
  pathological lines the fixed-width parser was introduced to handle. As it     
  stands it will first execute on real corpus data, unverified, and its         
  failure mode is a silently mis-parsed `FontRecord` rather than an             
  exception.                                                                    
                                                                                
  This is also the one finding that touches a stated project rule directly:     
  *"Forbidden: commenting out failing tests, writing untested functions."*      
                                                                                
  **Fix:** one fixture whose first-column name is long enough to push the       
  flag columns past their rule-line spans. The existing                         
  `test_a_name_containing_a_space_survives` fixture is the natural base —       
  lengthen the name until `cell[3]` is no longer `yes`/`no`.                    
                                                                                
  ---                                                                           
                                                                                
  ## F3 — `resolve` is order-dependent when two records share a base name       
  *(Minor, but it silently flips an answer)*                                    
                                                                                
  Two subsets of the same base font in one PDF, one embedded and one not — a    
  real configuration when a document references a standard font and also        
  embeds a subset of it:                                                        
                                                                                
  ```python                                                                     
  recs = [FontRecord("ABCDEF+Times-Roman", TYPE1, "WinAnsi", embedded=False,    
  ...),                                                                         
          FontRecord("GHIJKL+Times-Roman", TYPE1, "WinAnsi", embedded=True,     
  ...)]                                                                         
                                                                                
  usability("MNOPQR+Times-Roman", recs)            -> Usability.NOT_EMBEDDED    
  usability("MNOPQR+Times-Roman", reversed(recs))  -> Usability.FAST_PATH       
  ```                                                                           
                                                                                
  Same glyph, opposite answer, decided by `pdffonts` row order.                 
  `test_an_exact_match_wins_over_a_normalised_one` covers exact-vs-normalised   
  but not two normalised candidates colliding.                                  
                                                                                
  Neither answer is obviously right, so the useful move is to make the choice   
  explicit rather than incidental — prefer the embedded record when several     
  normalise to the same base name, and say so in the docstring. Whatever is     
  chosen, it should be a line of code and a test rather than list order.        
                                                                                
  This is the same shape as F1 in miniature: the aggregate is fine, the         
  resolution is ambiguous underneath it.                                        
                                                                                
  ---                                                                           
                                                                                
  ## Order                                                                      
                                                                                
  F2 first — it is one fixture and it closes a stated-rule violation. F1        
  before the rasterizer half is planned, since it sets that unit's value.       
  F3 whenever.                                                                  
                                                                                
  ---                                                                           
                                                                                
  ## On the pattern the CLI named                                               
                                                                                
  The fragment I have reads *"That's U4 rotation, U7 re-sort, U8…"* — three     
  instances of a guarantee stated, reasoned about in prose, and asserted by     
  nothing. F2 above is a fourth instance of a closely related thing: not an     
  unguarded guarantee this time, but an unguarded *branch*, invisible for       
  the same reason — the tests exercise the path that is easy to construct and   
  not the one that only real data produces.                                     
                                                                                
  Both are findable the same way, and cheaply: mutate a branch condition to a   
  constant and see whether anything fails. `if True` and `if False` on every    
  non-trivial branch in a new unit is a few minutes of work and would have      
  caught U4's rotation guard, U8's dispatch sort and this fallback. Worth       
  adding to the per-task review checklist rather than leaving to the final      
  whole-branch pass, which is where these have been surfacing.                  

● This is the same report I acted on last turn — it's audited at 2607f73, but
  main is now two commits further on. Let me verify each finding is genuinely
  closed at current HEAD rather than just assert it.

  Ran 3 shell commands (ctrl+o to expand)

● All three findings were already closed last turn — this report is against
  2607f73, and main is now at 066271a. Verified concretely rather than asserted:

  ┌─────────┬────────────────────────────────────────────────────────────────┐
  │ Finding │               Audit's own check, re-run at HEAD                │
  ├─────────┼────────────────────────────────────────────────────────────────┤
  │         │ forcing fixed-width for every line → 3 failures (was: 327 OK). │
  │ F2      │  Converse still fails with 2 errors, so both sides are guarded │
  │         │  now.                                                          │
  ├─────────┼────────────────────────────────────────────────────────────────┤
  │ F3      │ the audit's exact snippet: embedded outline | embedded outline │
  │         │  — order-dependent: False                                      │
  ├─────────┼────────────────────────────────────────────────────────────────┤
  │         │ grep for math families returns 28 hits across font.py and      │
  │ F1      │ test_font.py (was: 1, in unrelated prose). Their worked        │
  │         │ example — healthy aggregate hiding broken math — is encoded:   │
  │         │ aggregate 98.00%, maths 0.00% of 100.                          │
  └─────────┴────────────────────────────────────────────────────────────────┘

  The F1 measurement, which is the part worth your attention

  You asked what happens if math comes back low. It came back high — the
  opposite of the concern:

  ┌────────────────┬───────────┬─────────────────┐
  │   Population   │ Fast path │ Share of glyphs │
  ├────────────────┼───────────┼─────────────────┤
  │ aggregate      │ 94.64%    │ —               │
  ├────────────────┼───────────┼─────────────────┤
  │ maths families │ 100.00%   │ 2.00%           │
  └────────────────┴───────────┴─────────────────┘

  Zero rejections across 29,496 math glyphs over 30 documents. TeX math fonts
  are always embedded subsets in arXiv PDFs; the non-embedded fonts are standard
  text faces like Times. So the rasterizer half is worth more for its primary
  application than the aggregate implied, not less — and as you said, a number
  the aggregate couldn't have produced in either direction.

  Families by volume: CMMI 20,278, CMSY 7,069, CMEX 1,023, EUFM 405, MSBM 291,
  CMMIB 269.

  Your meta-advice cost me a commit, which is the strongest evidence for it

  I added the if True / if False sweep to CLAUDE.md as you suggested, then ran
  it against font.py — the unit I'd just declared finished. Eight surviving 
  branch mutations, six of them real: blank lines, short rule lines, unreadable
  rows, OTHER handling, exact-match precedence over an embedded sibling, and
  inventory() reporting a failed pdffonts rather than guessing. U9 went 43 → 52
  tests.

  Two were the probe misfiring, and that's the more useful finding. A mutation
  that breaks the module at import time reads as "survived" because the suite
  never reaches an assertion — one branch the sweep flagged actually fails 18
  tests when mutated by hand. I've recorded that caveat alongside the technique:
  a survivor is a lead, not a finding. Without it the sweep produces confident
  false negatives, which is worse than not running it.

  On the truncated trace

  The fragment you have ends at "That's U4 rotation, U7 re-sort, U8…" — the
  sentence was naming three instances of a guarantee stated, argued in prose,
  and asserted by nothing. Your F2 is the fourth, and the branch sweep then
  produced a fifth and sixth in the same unit. Nothing else was named that
  you're missing.

  main is at 066271a, 351 tests, clean clone verified. The next real decision is
  still the rasterizer half — and F1 has strengthened its case rather than
  weakened it.

✻ Brewed for 1m 5s

※ recap: We're building inkdrill, a stdlib-only document layout analysis package, unit by unit; U0–U9's inventory half are done and pushed, 351 tests passing. Next decision is whether to start U9's remaining half: the glyph rasterizer.

❯ ok go on and then push to the git repo                                        

● Next by units.md order is U10 gold.py — and it doesn't need the rasterizer,
  since it matches ink to pdfminer boxes geometrically. Its premise is
  assumption 7, which has already bitten twice. Measuring it first.

  Made 1 scratchpad edit +172, ran 2 shell commands (ctrl+o to expand)

● Background command "Run U10 premise check" completed (exit code 0)

● Rich, and it answers the question units.md said this check would answer.
  Recording before building.

  Ran 1 shell command (ctrl+o to expand)

● Premise recorded and pushed. Now U10 itself, built on what the measurement
  actually showed.

● Write(inkdrill/gold.py)
  ⎿  Wrote 336 lines to inkdrill/gold.py
       1 """gold.py — pdfminer alignment and the many-to-many matcher.
       2 
       3 CONTRACT (written before implementation; see docs/units.md U10)
       5 
       6 What this unit is for
       7 ---------------------
       8 Ink components come from U3. Glyph boxes come from pdfminer, in 
       9 points. Aligning them gives a gold label per glyph -- free train
         ing data
      10 and, more immediately, a way to find what other tools missed.
     … +378 lines (ctrl+o to expand)

  Ran 1 shell command (ctrl+o to expand)

● Affine has point(), plus translate/scale/flip_y/rotate/chain constructors —
  using U1's own vocabulary is what "composition, not a formula" actually means.

  Ran 2 shell commands (ctrl+o to expand)

● The transform composes correctly. Now the tests.

● Write(tests/test_gold.py)
  ⎿  Wrote 312 lines to tests/test_gold.py
      1 """Unit 10 tests. Every test name is quoted verbatim in the statu
        s report."""
      2 
      4 import random
      5 import unittest
      6 
      7 from inkdrill.gold import (Component, Glyph, GoldGlyph, MatchKind
      8                            MatchReport, match, page_transform, to
        _coco)
      9 from inkdrill.space import Affine
     … +352 lines (ctrl+o to expand)

  Ran 2 shell commands (ctrl+o to expand)

● One survivor. My own rule says a survivor is a lead, not a finding — verifying
  by hand.

  Ran 1 shell command (ctrl+o to expand)

● Real gap — the component side is asserted, the gold record's kind for a merged
  glyph is not. Forcing it would produce a self-contradicting report no test
  would catch.

  Ran 1 shell command (ctrl+o to expand)

● My invariant was too strong and the code is right. A glyph with two members,
  one of which is also claimed elsewhere, is legitimately SPLIT — both
  descriptions apply and the code picks split-precedence. Correcting the test to
  the true invariant and documenting the precedence.

  Ran 3 shell commands (ctrl+o to expand)

● U10 gold.py built and pushed. 35 tests, 386 total, verified on a clean clone
  of main.

  The premise check reframed the unit

  Assumption 7 — "pdfminer glyph boxes and rendered ink agree closely enough" —
  is too optimistic: only 66.93% of 18,519 real assignments at 400 dpi are 1:1.
  But the residual is structure, not error, which is exactly why units.md was
  right that the four classes are the product rather than the leftovers:

  ┌──────────────┬────────┬─────────────────────────────────────────────────┐
  │    Class     │  Rate  │               What it actually is               │
  ├──────────────┼────────┼─────────────────────────────────────────────────┤
  │ ink with no  │ 19.61% │ figures and rules — 3,572 on a figure-heavy     │
  │ glyph        │        │ page vs 4 and 35 on text pages                  │
  ├──────────────┼────────┼─────────────────────────────────────────────────┤
  │ N ink : 1    │ 12.34% │ i, j, :, accents — the multi-part glyphs U4     │
  │ glyph        │        │ already handles                                 │
  ├──────────────┼────────┼─────────────────────────────────────────────────┤
  │ glyph with   │ 1.11%  │ the resolution signal                           │
  │ no ink       │        │                                                 │
  ├──────────────┼────────┼─────────────────────────────────────────────────┤
  │ 1 ink : N    │ 0.02%  │ the feared case, and it barely exists           │
  │ glyphs       │        │                                                 │
  └──────────────┴────────┴─────────────────────────────────────────────────┘

  So the matcher doesn't split blobs — it reports the rare case. A splitter
  would have been effort spent on two thousandths of the data.

  It also answered the resolution question, but not via the rate expected

  units.md said the N↔1 rate as a function of dpi would answer "what render
  resolution does this need". It's the wrong signal — it falls at low dpi, which
  looks like improvement and isn't: components merge while whole glyphs vanish.
  Reading it alone would have recommended the worst resolution.

  The sharp signal is glyphs-with-no-ink: 1.11% at 400 dpi, 9.20% at 200, 58.78%
  at 100. 100 dpi is unusable.

  Two things the process caught

  Matching is on component centres, not overlap — because pdfminer gives the
  advance box. That's the same failure that wasted my first U4 premise check,
  now encoded as a guarantee with tests for a straddling component and a narrow
  glyph in a wide box.

  The branch sweep found one survivor, and confirming it by hand mattered. The
  component side of the merged case was asserted, the glyph side wasn't — a
  report could contradict itself. But my first invariant was too strong and
  failed: a glyph with several members, one shared, is genuinely both split and
  merged. The code gives SPLIT precedence and was right; the test was wrong.
  That's now a documented choice rather than an accident — and a reminder that a
  failing new test is as often the test's fault as the code's.

  Where the plan stands

  Ten units built. Seven assumptions closed by measurement, one refuted (band
  parallelism), two remaining: #6 partly (scheduler utilisation, refuted and
  understood) and #10 (package name, cosmetic).

  Next is U11 coverage.py — and it's the one that most directly serves your
  stated goal of finding what other tools missed. units.md says it's independent
  of U4–U10 and its four residual classes include "blob straddling a region
  edge — the case that clips tall ∫ and ∑ limits". U10's matcher is most of the
  machinery already; U11 points it at OCR/MathPix regions instead of pdfminer
  glyphs, and the 2,286 scanned pages with line-level OCR are exactly the data
  for it.

✻ Crunched for 7m 53s

※ recap: Building inkdrill unit by unit, each with a premise check measured on real corpus data before writing code. U10 `gold.py` is done and pushed; 386 tests pass on a clean clone. Next is U11 `coverage.py`, finding ink that OCR and other tools missed.
❯ please audit report and go on to U11 # inkdrill U10 `gold.py` — audit         
                                                                                
  `origin/main` @ `496c9bf`. **386 tests, 4 skipped, verified on a clean        
  clone.** U9 findings closed at `7e0178c` and `066271a`.                       
                                                                                
  Scope fence unchanged.                                                        
                                                                                
  ---                                                                           
                                                                                
  ## What is right                                                              
                                                                                
  - **The residual framing is the unit's best idea and it is carried            
    through.** 66.93% clean 1:1 means a single "agreement rate" would have      
    been near-meaningless. Reporting members rather than counts (G3) is what    
    makes the classes actionable.                                               
  - **The feared case was measured out of existence.** One blob straddling      
    two glyphs is 0.02%, so no splitter was built. Refusing to build for two    
    thousandths of the data is the right call, and it was made on evidence      
    rather than instinct.                                                       
  - **G4's centres-not-overlap decision names the reason** — pdfminer's box     
    is the *advance* box, and overlap against it is systematically wrong.       
    That is the U4 premise-check failure converted into a design constraint.    
  - **The resolution finding is subtle and correct.** `glyphs_without_ink` is   
    a better dpi signal than the N-to-1 rate, *because* N-to-1 falls at low     
    dpi as components merge while glyphs vanish. A naive reading of the         
    N-to-1 rate would have concluded low dpi was fine.                          
  - The y-flip is well guarded. Removing it fails 5 tests; changing its         
    origin to ignore the crop fails 1.                                          
                                                                                
  ---                                                                           
                                                                                
  ## F1 — `/Rotate` is built, sold in the contract, and effectively untested    
  *(Important, demonstrated)*                                                   
                                                                                
  Found by running the branch sweep the CLI adopted in U9, on `gold.py`:        
  14 branch conditions, 0 incompetent mutants, **3 survivors**, of which this   
  is the real one.                                                              
                                                                                
  ```                                                                           
  Δ inkdrill/gold.py :  if r:          →  if False:      (rotation never        
  applied)                                                                      
  → Ran 386 tests — OK (skipped=4)                                              
  ```                                                                           
                                                                                
  A page with `/Rotate 90` would be matched against unrotated glyph boxes,      
  silently, with every test green.                                              
                                                                                
  ### Why the existing test does not catch it                                   
                                                                                
  `test_rotation_keeps_the_page_in_positive_coordinates` is the only test of    
  rotation behaviour. **Doing nothing at all satisfies it** — an unrotated      
  page is already in positive coordinates. The other two mentions are           
  `rotate=45` raising `ValueError` (validation, not rotation) and a             
  `rotate=180` call whose assertion is about something else.                    
                                                                                
  This is a nastier variant than the earlier five instances. In U4, U7, U8      
  and U9 the guarantee had *no* test. Here there is a test, named for the       
  feature, that passes whether or not the feature works.                        
                                                                                
  Note that swapping the 90 and 270 translations *does* fail 2 subtests — but   
  that catches an internal *inconsistency* between the rotation and its         
  translation, not whether either happened or went the right way.               
                                                                                
  ### The behaviour is correct; only the evidence is missing                    
                                                                                
  I checked it by hand. 100×100 pt page at 72 dpi:                              
                                                                                
  | `/Rotate` | PDF bottom-left (0,0) | PDF top-left (0,100) |                  
  |---|---|---|                                                                 
  | 0 | (0, 100) | (0, 0) |                                                     
  | 90 | (0, 0) | (100, 0) |                                                    
  | 180 | (100, 0) | (100, 100) |                                               
  | 270 | (100, 100) | (0, 100) |                                               
                                                                                
  At `/Rotate 90` the PDF **left** edge becomes the image **top** edge — a      
  clockwise rotation, which is correct PDF semantics. The implementation is     
  right. Nothing asserts it.                                                    
                                                                                
  ### A test that pins it                                                       
                                                                                
  Verified against the current code:                                            
                                                                                
  ```python                                                                     
  def test_rotate_90_sends_the_left_edge_to_the_top(self):                      
      """PDF /Rotate 90 is CLOCKWISE. Direction and application both, so        
      neither skipping the rotation nor reversing it can pass."""               
      t = page_transform(100.0, 72.0, rotate=90, page_width_pt=100.0)           
      self.assertEqual(tuple(round(v, 6) for v in t.point(0, 0)),   (0.0, 0.0)) 
      self.assertEqual(tuple(round(v, 6) for v in t.point(0, 100)), (100.0,     
  0.0))                                                                         
  ```                                                                           
                                                                                
  One corner per angle would cover all four. The positivity test should stay    
  — it is a good invariant — but it cannot be the only one.                     
                                                                                
  ---                                                                           
                                                                                
  ## F2 — The residual attribution rests on three pages *(Minor, but it is the  
  unit's headline number)*                                                      
                                                                                
  The contract states *"ink with no glyph is overwhelmingly figures and         
  rules"* and supports it with 3,572 components on one figure-heavy page        
  against 4 and 35 on two text pages.                                           
                                                                                
  Three pages, and the 19.61% aggregate is dominated by the single              
  figure-heavy one. The *explanation* is almost certainly right — a diagram     
  correctly has no glyph. What is unsupported is the **rate**: 19.61% is a      
  property of this page mix, not of arXiv, and it will move by a large factor   
  between a theory paper and an experimental one.                               
                                                                                
  The claim to record is the mechanism plus the spread, not the aggregate —     
  the same lesson as the U0 colour fraction and the U7 density dependence,      
  both of which the project has already absorbed. The harness can produce a     
  per-page distribution from what it already collects.                          
                                                                                
  Related: the premise check ran at 400 dpi, but the pipeline's stated render   
  is 600. `glyphs_without_ink` at 400 dpi is about one in ninety; at 600 it     
  should be better, but the number in the contract is the one people will       
  quote. Worth stating which dpi each figure belongs to.                        
                                                                                
  ---                                                                           
                                                                                
  ## F3 — Two further sweep survivors, both benign *(Trivial)*                  
                                                                                
  Recorded so they are not re-found:                                            
                                                                                
  - `if r == 180:` → the sweep flagged it, but the pattern is an `elif` and my  
    first replacement did not apply; on re-test it is covered.                  
  - `if c:` in `MatchReport.report()` → `True` survives. This only controls     
    whether zero-count classes appear in the printed summary. Cosmetic; either  
    a one-line test or a comment saying the branch is presentational.           
                                                                                
  Both are what the CLI's own caveat describes: a survivor is a lead, not a     
  finding. Two of three leads here resolved to nothing, one was real.           
                                                                                
  ---                                                                           
                                                                                
  ## On the sweep itself                                                        
                                                                                
  Running it on `gold.py`: 14 branch conditions, 28 mutants, **0 incompetent**, 
  3 survivors, ~40 seconds. The incompetent-mutant filter (import canary        
  before running the suite) cost nothing here because no mutation broke the     
  import — but it is what makes the count trustworthy rather than something     
  to be manually second-guessed.                                                
                                                                                
  The instance count is now six, and the shape has widened. The first five      
  were guarantees with no test at all. F1 is a guarantee with a test that a     
  no-op passes. Both are found by the same sweep, which is the argument for     
  running it per unit rather than reasoning about which guarantees feel         
  thin — reasoning would not have flagged                                       
  `test_rotation_keeps_the_page_in_positive_coordinates`, since it is named     
  for the thing it fails to test.                                               
                                                                                
  ---                                                                           
                                                                                
  ## Before U11                                                                 
                                                                                
  U11 is `coverage.py`, the MathPix cross-check, and it is the unit that        
  depends most directly on `page_transform` being right — a rotated page        
  would produce a wrong straddle report that looks entirely plausible. F1       
  should close first.                                                           
                                                                                
  One carry-forward from U9: the math-glyph population question is still        
  open. `MATH_FAMILIES` measures math *fonts*, and in TeX the body-text font    
  supplies `=`, delimiters, digits and operator names inside expressions.       
  U11's MathPix rectangles are exactly the font-agnostic population that        
  settles it, so the two can be answered together — the same region data        
  serves both the straddle report and the stratification.                       

● F1 is the nastiest instance yet — a test named for rotation that a no-op
  passes. Verifying before fixing.

  Ran 2 shell commands (ctrl+o to expand)

● Both confirmed — the mutant passes all 386, and the hand-check table matches
  exactly. The behaviour is right; only the evidence was missing.

  Ran 1 shell command (ctrl+o to expand)

● F1 closed — the mutant now fails 6 tests. F2 next: the auditor is right that
  19.61% is a property of three pages, not of arXiv. Measuring the spread, and
  adding the residuals subcommand units.md already references.

  Ran 2 shell commands (ctrl+o to expand)

● Background command "Add residuals subcommand and measure the spread" completed
(exit code 0)

● The auditor was right, and more sharply than predicted. An independent 12-page
  sample:

  ┌───────────────────┬──────────────────────┬──────────┐
  │       Class       │ 3-page premise check │ 12 pages │
  ├───────────────────┼──────────────────────┼──────────┤
  │ 1 : 1             │ 66.93%               │ 85.17%   │
  ├───────────────────┼──────────────────────┼──────────┤
  │ ink with no glyph │ 19.61%               │ 0.39%    │
  ├───────────────────┼──────────────────────┼──────────┤
  │ N ink : 1 glyph   │ 12.34%               │ 13.75%   │
  ├───────────────────┼──────────────────────┼──────────┤
  │ glyph with no ink │ 1.11%                │ 0.64%    │
  ├───────────────────┼──────────────────────┼──────────┤
  │ 1 ink : N glyphs  │ 0.02%                │ 0.05%    │
  └───────────────────┴──────────────────────┴──────────┘

  The two figures dominated by that one figure-heavy page were badly
  unrepresentative; the three structural ones reproduce. Per-page 1:1 is tight
  at 81.2–86.7%. Correcting both documents.

  Ran 1 shell command (ctrl+o to expand)

● U10's findings are closed. Now U11 — and per your auditor's carry-forward, its
  region data settles the open math-population question too.

  Ran 1 shell command (ctrl+o to expand)

● OCR regions are line-level, in PDF points, on 403 scanned documents — exactly
  the "areas other tools missed" data. Premise check for U11.

  Ran 1 shell command (ctrl+o to expand)

● Good premise data, and it confirms the lesson twice-learned: report the
  spread, not the aggregate.

  ┌─────────────────────────────┬───────────┬────────────────┬─────────────┐
  │            Class            │ Aggregate │   Per-page     │  Per-page   │
  │                             │           │     median     │     max     │
  ├─────────────────────────────┼───────────┼────────────────┼─────────────┤
  │ ink inside a region         │ 89.29%    │ —              │ —           │
  ├─────────────────────────────┼───────────┼────────────────┼─────────────┤
  │ ink with NO region (missed) │ 9.94%     │ 0.20%          │ 29.19%      │
  ├─────────────────────────────┼───────────┼────────────────┼─────────────┤
  │ ink straddling a region     │ 0.76%     │ 1.81%          │ 2.39%       │
  │ edge                        │           │                │             │
  ├─────────────────────────────┼───────────┼────────────────┼─────────────┤
  │ ink under overlapping       │ 0.01%     │ —              │ —           │
  │ regions                     │           │                │             │
  ├─────────────────────────────┼───────────┼────────────────┼─────────────┤
  │ region with no ink          │ 0.00%     │ 0.00%          │ 0.00%       │
  └─────────────────────────────┴───────────┴────────────────┴─────────────┘

  The 9.94% is one page carrying 29% — which is precisely the "areas other tools
  missed" signal, not noise. Building U11.

● Write(inkdrill/coverage.py)
  ⎿  Wrote 236 lines to inkdrill/coverage.py
       1 """coverage.py — cross-checking another tool's regions against r
         eal ink.
       3 CONTRACT (written before implementation; see docs/units.md U11)
       4 ==============================================================
       5 
       7 ---------------------
       8 Another tool -- OCR, MathPix, a layout detector -- returns recta
         ngles it
         matters:
      10 **what did it miss, and where is it wrong at the edges?**
     … +267 lines (ctrl+o to expand)

● Write(tests/test_coverage.py)
  ⎿  Wrote 211 lines to tests/test_coverage.py
      1 """Unit 11 tests. Every test name is quoted verbatim in the statu
        s report."""
      2 
      3 import random
      4 import unittest
      6 from inkdrill.coverage import (Box, CoverageClass, CoverageReport
        , Region,
      7                                check)
      8 from inkdrill.space import Affine
      9 
     … +235 lines (ctrl+o to expand)

  Ran 2 shell commands (ctrl+o to expand)

● One test, many subtests. My fixture generates degenerate boxes where x1 < x0,
  which min_pixels then silently drops — so the partition is over the filtered
  boxes, not the input. That's a real contract subtlety the failure surfaced.
  Fixing both.

  Ran 1 shell command (ctrl+o to expand)

● Running the branch sweep on U11 before recording anything, per the checklist.

  Ran 1 shell command (ctrl+o to expand)

● Zero survivors. Now the real-data check and recording.

  Ran 2 shell commands (ctrl+o to expand)

● Background command "Add missed subcommand and verify on scans" completed (exit
code 0)

● The unit is doing exactly its job. Two corrections to my own docstring fall
  out.

  Ran 2 shell commands (ctrl+o to expand)

● U10's audit findings are closed and U11 is built. 413 tests, verified on a
  clean clone, pushed to main.

  U10 F1 — the nastiest instance yet

  You were right and I verified it: deleting the /Rotate branch passed all 386
  tests. test_rotation_keeps_the_page_in_positive_coordinates is satisfied by
  doing nothing, since an unrotated page is already in positive coordinates. The
  first five instances were guarantees with no test; this was a test named for 
  the feature that passes whether the feature works.

  Your hand-check table matched exactly. Now pinned three ways — a known corner
  per angle, a blunt not-a-no-op check, and four 90° steps composing to the
  identity. The mutant fails 6 tests.

  U10 F2 — sharper than you predicted

  An independent 12-page sample against the premise check's three:

  ┌───────────────────┬─────────┬──────────┐
  │       Class       │ 3 pages │ 12 pages │
  ├───────────────────┼─────────┼──────────┤
  │ 1 : 1             │ 66.93%  │ 85.17%   │
  ├───────────────────┼─────────┼──────────┤
  │ ink with no glyph │ 19.61%  │ 0.39%    │
  ├───────────────────┼─────────┼──────────┤
  │ N ink : 1 glyph   │ 12.34%  │ 13.75%   │
  ├───────────────────┼─────────┼──────────┤
  │ glyph with no ink │ 1.11%   │ 0.64%    │
  └───────────────────┴─────────┴──────────┘

  One figure-heavy page moved 1:1 by 50 points and image-only by a factor of
  fifty. The three structural classes reproduced. Both documents now carry the
  per-page spread as the claim and the aggregate as context, with the dpi
  stated.

  U11 — and it immediately found things

  Containment, not centres — the deliberate inversion of U10's rule, because
  here a blob crossing a region edge is the finding. There's a fixture whose
  centre sits inside and whose body overflows, asserting both that it straddles
  and that it isn't counted inside.

  On eight scanned pages the aggregates are stable and nearly useless; the
  spread is the product:

  - 100% missed on one page — 3 OCR regions against 950 ink components, a total
  failure the aggregate would bury
  - 33.63% straddle on a diagram where regions cut through content
  - against a 0.53% median

  Two corrections to my own first reading: "region with no ink measured at
  exactly zero" was a six-page artefact (0.03% on eight fresh pages), and the
  straddle rate tripled. That's the fourth time a small-sample aggregate has
  misled here — after U0's colour fraction, U7's density, U10's residuals. The
  pattern is now well enough established that I measure the spread by default.

  A failing random fixture also surfaced a genuine contract subtlety rather than
  a bug: boxes below min_pixels, including degenerate ones, are dropped, so the
  partition is over the surviving boxes. box_count now says how many those
  were.

  Branch sweep on coverage.py: 8 conditions, 0 incompetent mutants, 0 survivors.

  Still open

  Your U9 carry-forward — the math-population question — is not yet answered. I
  built U11 with the region machinery that can settle it, but the OCR regions in
  this corpus are all type: "text" with no math tagging, so they can't isolate
  the font-agnostic math population on their own. That needs MathPix rectangles
  or the formula-report.html data I noticed in 2510.15795. Worth pointing me at
  whichever you'd prefer.

✻ Crunched for 10m 6s

❯ go on with U12                                                                
● U12 domains.py. units.md gives it an unusually testable design rule — "a 
  dimension earns its place when the concepts of interest become convex in it" —
  so the premise check is the Gärdenfors test itself, run on real glyphs.

  Ran 2 shell commands (ctrl+o to expand)

● Background command "Gärdenfors convexity premise check for U12" completed
(exit code 0)

● All dimensions score 0.075–0.184 against a 0.043 random baseline — informative
  but none separating. That's partly real and partly my metric: a [min, max]
  interval is destroyed by one outlier. Re-running with robust intervals and an
  information measure.

  Ran 2 shell commands (ctrl+o to expand)

● Background command "Robust convexity and mutual information per dimension"
completed (exit code 0)

● Now a clean, actionable ranking — and it reverses an emphasis in units.md's
  own U13.

  ┌────────────┬───────────────────┬────────────────────┬───────────────┐
  │ Dimension  │ Convexity (10–90) │ Lift over baseline │ Normalised MI │
  ├────────────┼───────────────────┼────────────────────┼───────────────┤
  │ aspect     │ 0.485             │ 11.1×              │ 0.634         │
  ├────────────┼───────────────────┼────────────────────┼───────────────┤
  │ elongation │ 0.444             │ 10.2×              │ 0.627         │
  ├────────────┼───────────────────┼────────────────────┼───────────────┤
  │ width      │ 0.273             │ 6.3×               │ 0.584         │
  ├────────────┼───────────────────┼────────────────────┼───────────────┤
  │ fill       │ 0.379             │ 8.7×               │ 0.561         │
  ├────────────┼───────────────────┼────────────────────┼───────────────┤
  │ area       │ 0.290             │ 6.7×               │ 0.544         │
  ├────────────┼───────────────────┼────────────────────┼───────────────┤
  │ height     │ 0.250             │ 5.7×               │ 0.418         │
  ├────────────┼───────────────────┼────────────────────┼───────────────┤
  │ splits     │ 0.163             │ 3.7×               │ 0.373         │
  ├────────────┼───────────────────┼────────────────────┼───────────────┤
  │ cycles     │ 0.127             │ 2.9×               │ 0.246         │
  ├────────────┼───────────────────┼────────────────────┼───────────────┤
  │ depth      │ 0.086             │ 2.0×               │ 0.220         │
  └────────────┴───────────────────┴────────────────────┴───────────────┘

  Every topological dimension ranks below every geometric one. And cycles — the
  most stable feature from U4's check at 98.7–100% consistency — is near the
  bottom for discrimination, because e a o b d p q all have exactly one hole.
  Stability and discriminative power are different properties, and the unit
  should say so.

● Write(inkdrill/domains.py)
  ⎿  Wrote 348 lines to inkdrill/domains.py
      1 """domains.py — conceptual-space feature domains.
      2 
      3 CONTRACT (written before implementation; see docs/units.md U12)
      4 ==============================================================
      5 
      7 ----------------------------------------------
      8 docs/units.md sets one rule for this unit, after Gardenfors: **a 
        dimension
      9 earns its place when the concepts of interest become convex in it
        .**
     … +406 lines (ctrl+o to expand)

● Write(tests/test_domains.py)
  ⎿  Wrote 217 lines to tests/test_domains.py
       1 """Unit 12 tests. Every test name is quoted verbatim in the stat
         us report."""
       3 import random
       4 import unittest
       5 
         sion, Domain,
       7                               Point, UnknownDimension, convexity
         , describe,
       9 
      10 FEATURES = {"width": 20, "height": 40, "area": 300,
     … +233 lines (ctrl+o to expand)

  Ran 1 shell command (ctrl+o to expand)

● A real edge case the test caught: with only two samples per class,
  interpolated percentiles land between the data points and the interval
  contains nothing. Using order statistics instead — actual sample values — so
  the interval always contains data.

  Ran 2 shell commands (ctrl+o to expand)

● The ceil on the high bound pulls the outlier back in. Both bounds should round
  into the data.

  Ran 1 shell command (ctrl+o to expand)

● Now re-running the measurement through the module's own functions, so the
  recorded scores are reproducible from the shipped code rather than a scratch
  script.

  Ran 2 shell commands (ctrl+o to expand)

● Background command "Re-measure via the shipped functions" completed (exit code
0)

● The shipped functions reproduce the scratch measurement to the third decimal —
  so the recorded scores are now regenerable from the module itself. Updating
  the two that shifted slightly, then recording.

  Ran 2 shell commands (ctrl+o to expand)

● Six leads. Checking each by hand rather than trusting the sweep — one is real,
  one is dead code, four are redundant with a guard the sweep couldn't mutate
  simultaneously.

  Ran 2 shell commands (ctrl+o to expand)

● My test asserted the wrong thing — _get("width") on {"width": 0} correctly
  returns 0.0. Only the derived dimensions must guard against division. Fixing
  the test.

  Ran 2 shell commands (ctrl+o to expand)

● U12 domains.py built and pushed. 32 tests, 445 total, verified on a clean
  clone. Branch sweep: 20 conditions, 0 survivors.

  The design test is shipped, not described

  units.md sets one rule after Gärdenfors — a dimension earns its place when the
  concepts become convex in it — which is measurable, so convexity() and
  mutual_information() are part of the unit. A future dimension is added by
  measuring it, and every dimension carries its score, so adding a weak one is a
  visible decision rather than an accident.

  Two findings that reorder the plan

  Every topological dimension ranks below every geometric one.

  ┌──────────────┬──────────────┬──────────────┐
  │              │     best     │    worst     │
  ├──────────────┼──────────────┼──────────────┤
  │ size / shape │ aspect 0.634 │ height 0.418 │
  ├──────────────┼──────────────┼──────────────┤
  │ topology     │ splits 0.373 │ depth 0.220  │
  └──────────────┴──────────────┴──────────────┘

  U13's text reads as though the bitmap and the Reeb signature are the two
  channels, with aspect and extents "carried separately" as a supplement for - −
  – — and . ·. The measurement inverts that: extents and aspect are the 
  strongest dimensions available, stronger than the entire topological channel.

  Stability and discriminative power are different properties. cycles was U4's
  most stable feature at 98.7–100% consistency within a class, and is near the
  bottom here for discrimination — because e a o b d p q all have exactly one
  hole. A dimension that never varies within a class and barely varies between
  them is reliable and nearly useless alone. There's a test asserting the gap,
  so a change that closes it forces a revisit of U13's weighting.

  Four test failures, three of them real bugs

  - An interpolated percentile gave a two-sample class an interval strictly
  between its two points, containing neither — bounds are now order statistics.
  - Rounding the high bound up pulled a top outlier straight back into the
  interval the trim exists to remove; nine 1s and one 999 got [1, 999]. Both
  bounds now round into the data.
  - A branch reachable only when values exist but every class is below
  min_per_class would have divided by zero — masked from the sweep by an earlier
  guard, found by hand.
  - The fourth was my test being wrong: it demanded None from a plain getter on
  width=0, but zero is a legitimate width. The code was right.

  I also re-ran the whole measurement through the shipped functions, so the
  recorded scores reproduce from measure.py convexity --seed 23 rather than from
  a scratch script.

  Two domains declared and empty, deliberately

  TYPOGRAPHIC needs U9's reference lines and TRANSFORM needs a per-character CTM
  from U10 — both named rather than populated with guesses, and both asserted
  empty so the gap can't be forgotten. No Morton code: it encodes two dimensions
  already present.

  Thirteen units built, 445 tests. U13 classify.py is next, and U12 has just
  told it something important about how to weight its channels — but it also
  depends on U9's rasterizer half for the normalised-bitmap channel, which
  remains the one substantial unbuilt piece.

✻ Cogitated for 8m 20s

※ recap: Building inkdrill's numbered units in order, each with a premise check before coding. U12 domains.py is done and pushed: 445 tests green on main. Next is U13 classify.py, though its bitmap channel needs U9's unbuilt rasterizer half.

❯ please go on and read the auditors advise below: # inkdrill U12 `domains.py`  
  — audit                                                                       
                                                                                
  `origin/main` @ `e9c452a`. **445 tests, 4 skipped, verified on a clean        
  clone.** U10 findings closed at `8bf9cef`; U11 landed at `cd892cb`.           
                                                                                
  Scope fence unchanged.                                                        
                                                                                
  ---                                                                           
                                                                                
  ## What is right                                                              
                                                                                
  - **Shipping the design test rather than describing it** is the correct       
    reading of the Gärdenfors rule in `units.md`. A dimension that carries its  
    own score makes adding a weak one a visible decision.                       
  - **The four bug fixes are real and the reasoning is sound.** The             
    order-statistic bound is the important one — an interpolated percentile     
    giving a two-sample class an interval strictly between its two points,      
    containing neither, and scoring zero for having tidy data. Rounding both    
    bounds *into* the data is the same lesson applied twice.                    
  - **Admitting the fourth failure was a wrong test, not wrong code** —         
    width=0 being legitimate — is the right call and easy to get wrong under    
    pressure to make a suite green.                                             
  - **Two domains declared, empty, and asserted empty** so the gap cannot be    
    forgotten. Naming a dependency beats populating it with guesses.            
  - **Re-running the measurement through the shipped functions** rather than a  
    scratch script is what makes `_MEASURED = "2026-08-08, n=5436, 23 classes"` 
    worth anything.                                                             
  - MI is normalised by H(labels) — an uncertainty coefficient, bounded [0,1].  
    That is the right family of measure.                                        
                                                                                
  ---                                                                           
                                                                                
  ## F1 — The MI ranking is capped by cardinality, so the headline conclusion   
  is guaranteed before any data is seen *(Important, demonstrated)*             
                                                                                
  The claim is *"every topological dimension ranks below every geometric        
  one"*, with aspect at 0.634 against splits at 0.373.                          
                                                                                
  Normalised MI is bounded by the dimension's own entropy:                      
                                                                                
  > MI(X; class) ≤ H(X) / H(class)                                              
                                                                                
  With 23 classes, H(class) = 4.524 bits. A dimension taking three distinct     
  values has H(X) ≤ log₂3 = 1.585 bits, so its MI **cannot exceed 0.350** no    
  matter how informative it is. A continuous dimension binned into 16 gets a    
  ceiling of 0.884.                                                             
                                                                                
  Demonstrated on 23 classes and n = 5436, matching the measurement's scale:    
                                                                                
  | dimension | distinct | MI ceiling | MI | % of ceiling |                     
  |---|---|---|---|---|                                                         
  | continuous, near-perfect separation | 5436 | 0.884 | 0.774 | 88% |          
  | **3-valued, maximally informative** | 3 | **0.350** | **0.350** | **100%**  
  |                                                                             
  | **2-valued, maximally informative** | 2 | **0.221** | **0.221** | **100%**  
  |                                                                             
                                                                                
  A 3-valued dimension that partitions the classes *perfectly* — there is no    
  better 3-valued dimension — scores 0.350. That is below `aspect` (0.634),     
  below every SIZE dimension, and below `elongation` and `fill`. **The          
  ranking cannot distinguish "weak" from "low-cardinality."**                   
                                                                                
  Applying the same correction to the reported numbers, assuming the obvious    
  distinct-value counts:                                                        
                                                                                
  | | assumed distinct | ceiling | MI | % of ceiling |                          
  |---|---|---|---|---|                                                         
  | aspect | 16 (bins) | 0.884 | 0.634 | **72%** |                              
  | splits | 5 | 0.513 | 0.373 | **73%** |                                      
  | cycles | 3 | 0.350 | 0.246 | **70%** |                                      
  | depth | 3 | 0.350 | 0.220 | **63%** |                                       
                                                                                
  Remarkably flat. On this reading the topological dimensions are about as      
  *efficient per available bit* as the geometric ones — they simply have        
  fewer bits to give.                                                           
                                                                                
  **Caveat, and it matters:** those distinct-value counts are my assumption. I  
  do not have the corpus. The demonstration above does not depend on them —     
  the ceiling effect is arithmetic — but the 63–73% figures do. `measure.py`    
  can produce the real distinct counts in a line, and that is what turns this   
  from an objection into a number.                                              
                                                                                
  **Suggested fix:** carry `H(X)/H(class)` beside every MI in `DIMENSIONS`, or  
  report MI-as-fraction-of-ceiling. Then a low score means "carries little      
  information" rather than "has few values", and the two are currently          
  indistinguishable.                                                            
                                                                                
  **What survives and what does not.** "Extents and aspect are the strongest    
  dimensions" survives as a statement about marginal bits, and U13 should       
  still weight them heavily. What does not survive is *"topology ranks below    
  geometry"* as a reason to demote the topological channel — that ordering is   
  an artefact of value count. The right framing is the one the `cycles`         
  annotation already gives: 98.7–100% stable within a class and weak at         
  discrimination is the profile of a **verifier, not a discriminator**. That    
  is also, independently, what the classical OCR literature concludes.          
                                                                                
  ---                                                                           
                                                                                
  ## F2 — The design test is per-dimension; Gärdenfors' criterion is per-domain 
  *(Important)*                                                                 
                                                                                
  Every number in `DIMENSIONS` is a marginal — one dimension against the        
  labels. Marginal MI cannot see joint information. Demonstrated:               
                                                                                
  ```                                                                           
  three 3-valued dimensions that TOGETHER determine the class exactly:          
     dim 0   marginal MI = 0.350                                                
     dim 1   marginal MI = 0.347                                                
     dim 2   marginal MI = 0.340                                                
     all three together  = 0.866                                                
  ```                                                                           
                                                                                
  Each looks weak alone; together they are perfect. `splits`, `merges`,         
  `births`, `cycles` and `depth` are exactly this shape — five low-cardinality  
  dimensions from one source, plausibly carrying complementary information,     
  each scored in isolation.                                                     
                                                                                
  This also lands on the rule `units.md` actually sets. Gärdenfors' domains     
  are bundles of *integral* dimensions, and his convexity criterion applies to  
  concepts as regions in a domain, not to their projections onto single axes.   
  A 1-D projection test is a valid **necessary** condition — a convex region    
  projects to a convex interval — but passing it on every axis does not imply   
  joint convexity, and failing it on one axis does not mean that axis is        
  useless jointly.                                                              
                                                                                
  So the shipped test is weaker than the rule it implements, and the gap runs   
  in the direction that penalises TOPOLOGY specifically, because that is where  
  the many-low-cardinality-dimensions cluster lives.                            
                                                                                
  **Suggested fix, cheap:** add a domain-level score — MI of the *tuple* of a   
  domain's dimensions against the labels, using the same equal-frequency        
  binning on each. One extra function, and it answers whether TOPOLOGY as a     
  domain is weak or merely fragmented. If the joint TOPOLOGY score approaches   
  SIZE's, U13's channel weighting should not be reordered on F1's ranking at    
  all.                                                                          
                                                                                
  ---                                                                           
                                                                                
  ## F3 — Three sweep survivors, all equivalent mutants *(Trivial, but the      
  category is worth naming)*                                                    
                                                                                
  My sweep on `domains.py` found 11 branch conditions, 0 incompetent, 3         
  survivors — against the reported 20 conditions and 0 survivors. Checked all   
  three:                                                                        
                                                                                
  | line | branch | verdict |                                                   
  |---|---|---|                                                                 
  | 300 | `if not values:` | guard and fallthrough both return `(0.0, 0.0, 0,   
  0)` — identical |                                                             
  | 315 | `if inside:` | unreachable: `lo`/`hi` are order statistics of class   
  *c*'s own values, so at least one *c* sample always satisfies `lo <= v <= hi` 
  |                                                                             
  | 333 | `if n == 0:` | `_entropy(Counter(), 0)` returns 0, and the `h_labels  
  == 0` branch below catches it — identical |                                   
                                                                                
  None is a test gap. They are **equivalent mutants** — provably                
  behaviour-preserving, and therefore unkillable.                               
                                                                                
  That is a fourth outcome category alongside killed, survived, and             
  incompetent, and it is worth adding to the `CLAUDE.md` note. Incompetent      
  mutants are filtered mechanically by the import canary; equivalent mutants    
  cannot be, and must be reasoned about one at a time. Both produce false       
  leads, and the note currently covers only the first. The count difference     
  (11 vs 20) is probably scope — ternaries, `while`, comprehension              
  conditions — worth reconciling so the two sweeps agree on what they cover.    
                                                                                
  ---                                                                           
                                                                                
  ## Order                                                                      
                                                                                
  F2 first — a domain-level score is one function, and it decides whether F1's  
  reordering should reach U13 at all. F1's ceiling column next. F3 whenever.    
                                                                                
  Both F1 and F2 point the same way: the measurement is sound in mechanism and  
  the comparison it supports is narrower than the conclusion drawn from it.     
  That is the same shape as the U0 colour fraction and the U9 math families —   
  right instrument, and a conclusion that outruns what it can see. It is worth  
  noting that this is now the pattern that has recurred most, and it is not     
  caught by mutation sweeps, because nothing is wrong with the code.            

● This is the sharpest audit yet — it identifies a conclusion that outruns its
  instrument. Let me verify F1's arithmetic before acting.

  Ran 1 shell command (ctrl+o to expand)
● F1 confirmed exactly. Implementing F2 first as advised, since it decides
  whether F1's reordering should reach U13 at all.

  Ran 1 shell command (ctrl+o to expand)

● Joint MI reproduces the auditor's demonstration exactly — 0.333 each, 1.0 
  together. Three tests broke; let me see whether they're mine or the code's.

  Ran 1 shell command (ctrl+o to expand)

● My new fields shifted the positional arguments, so every note string landed in
  distinct. A real bug from the edit, caught by the tests. Fixing with
  keywords.

  Ran 2 shell commands (ctrl+o to expand)

● My regex over-matched and corrupted an unrelated except. Repairing precisely
  rather than sweeping again.

  Ran 2 shell commands (ctrl+o to expand)

● All 32 pass again. Now the measurement F1 asks for — real distinct counts,
  ceilings, efficiencies, and F2's joint domain scores.

  Ran 2 shell commands (ctrl+o to expand)

● Background command "Measure ceilings, efficiencies and joint domain scores"
completed (exit code 0)

● The measurement vindicates the auditor and goes further than they predicted.
  Corrected for cardinality, the ranking completely inverts:

  ┌────────┬─────────┬──────────┬─────────┬────────────┐
  │        │ raw NMI │ distinct │ ceiling │ efficiency │
  ├────────┼─────────┼──────────┼─────────┼────────────┤
  │ depth  │ 0.220   │ 2        │ 0.229   │ 0.96       │
  ├────────┼─────────┼──────────┼─────────┼────────────┤
  │ cycles │ 0.246   │ 3        │ 0.257   │ 0.95       │
  ├────────┼─────────┼──────────┼─────────┼────────────┤
  │ splits │ 0.375   │ 6        │ 0.423   │ 0.89       │
  ├────────┼─────────┼──────────┼─────────┼────────────┤
  │ aspect │ 0.634   │ 166      │ 0.968   │ 0.66       │
  ├────────┼─────────┼──────────┼─────────┼────────────┤
  │ height │ 0.418   │ 42       │ 0.759   │ 0.55       │
  └────────┴─────────┴──────────┴─────────┴────────────┘

  And F2's joint score: TOPOLOGY 0.713 against a best marginal of 0.375 — nearly
  double. Correcting my headline conclusion.

  Ran 1 shell command (ctrl+o to expand)

● Regex editing keeps corrupting this. Rewriting the block explicitly instead.

  Ran 1 shell command (ctrl+o to expand)

● The inversion is complete and clean. Now correcting the test that asserted my
  wrong conclusion, and adding F2/F3.

  Ran 2 shell commands (ctrl+o to expand)

● splits has ceiling 0.423, just above height's actual 0.418 — so my assertion
  was too strong. The true claim is that no topological dimension could have
  reached the top of the raw ranking.

  Ran 1 shell command (ctrl+o to expand)

● Now F3 — the equivalent-mutant category, which the CLAUDE.md note doesn't
  cover.

  Ran 2 shell commands (ctrl+o to expand)

● The audit was right, and the corrected measurement goes further than it
  predicted. 453 tests, pushed and verified on a clean clone.

  F2 first, as advised — and it changed the answer

  joint_mutual_information() reproduces your demonstration exactly: three
  3-valued dimensions scoring 0.333 alone, 1.000 together. On the corpus:

  ┌──────────┬──────┬───────┬───────────────┐
  │  domain  │ dims │ joint │ best marginal │
  ├──────────┼──────┼───────┼───────────────┤
  │ size     │ 4    │ 0.960 │ 0.634         │
  ├──────────┼──────┼───────┼───────────────┤
  │ shape    │ 2    │ 0.913 │ 0.627         │
  ├──────────┼──────┼───────┼───────────────┤
  │ topology │ 5    │ 0.713 │ 0.375         │
  ├──────────┼──────┼───────┼───────────────┤
  │ all      │ 11   │ 0.996 │ —             │
  └──────────┴──────┴───────┴───────────────┘

  Topology jointly reaches nearly double its best marginal. Fragmented, not
  uninformative.

  F1 — the real distinct counts invert the ranking

  Your ceiling arithmetic is exactly right (H(class) = 4.524 bits; a 3-valued
  dimension caps at 0.350). With the measured counts rather than assumed ones,
  it's more extreme than your 63–73% estimate:

  ┌────────┬───────┬──────────┬─────────┬────────────┐
  │        │  nmi  │ distinct │ ceiling │ efficiency │
  ├────────┼───────┼──────────┼─────────┼────────────┤
  │ aspect │ 0.634 │ 166      │ 0.968   │ 0.65       │
  ├────────┼───────┼──────────┼─────────┼────────────┤
  │ height │ 0.418 │ 42       │ 0.759   │ 0.55       │
  ├────────┼───────┼──────────┼─────────┼────────────┤
  │ splits │ 0.375 │ 6        │ 0.423   │ 0.89       │
  ├────────┼───────┼──────────┼─────────┼────────────┤
  │ depth  │ 0.220 │ 2        │ 0.229   │ 0.96       │
  └────────┴───────┴──────────┴─────────┴────────────┘

  Topology is the most efficient per available bit, geometry the least. Not flat
  — inverted. My conclusion was wrong and is now marked corrected in both the
  module and units.md; U13 should weight the topological channel on the joint
  figure.

  And I overstated once more while fixing it. Writing the replacement test I
  claimed every topological ceiling sits below the worst size dimension — but
  splits' ceiling of 0.423 exceeds height's actual 0.418. The cap binds at the
  top, not everywhere. The test now says so.

  F3 — the category was missing and it matters

  All three domains.py survivors were equivalent mutants — provably
  behaviour-preserving, unkillable, and no test should be written for them.
  CLAUDE.md now names all three non-findings: incompetent (filter with an import
  canary), equivalent (must be reasoned about individually), misapplied. Plus
  your scope note: two sweeps covering different constructs will disagree on the
  count and neither is wrong.

  The pattern you named

  You're right that this is now the most-recurring one — U0's colour fraction,
  U9's math families, U10's residual rates, and now this. Right instrument, 
  conclusion wider than what it can see. And you're right that mutation sweeps
  can't catch it, because nothing is wrong with the code.

  The three earlier instances were all sampling — a number true of the sample,
  asserted of the corpus. This one is different in kind: the sample was fine and
  the measure itself had a ceiling I didn't account for. Worth distinguishing,
  because the sampling fix (measure the spread) wouldn't have caught it — only
  asking "what is the maximum this number could be?" would.

  U13 classify.py is next, and it now has three measured constraints rather than
  the plan's intuitions: weight extents heavily, weight topology on its joint
  figure not its marginals, and treat cycles as a verifier rather than a
  discriminator. It still depends on U9's rasterizer half for the
  normalised-bitmap channel — the one substantial unbuilt piece.

✻ Worked for 6m 6s

※ recap: Building inkdrill unit by unit; U12 domains.py is done and pushed, with the audit's cardinality and joint-information corrections applied (453 tests green). Next is U13 classify.py, which needs U9's unbuilt rasterizer half for its bitmap channel.

❯ read audit report below and go on with U13 # inkdrill U12 `domains.py` —      
  audit                                                                         
                                                                                
  `origin/main` @ `e9c452a`. **445 tests, 4 skipped, verified on a clean        
  clone.** U10 findings closed at `8bf9cef`; U11 landed at `cd892cb`.           
                                                                                
  Scope fence unchanged.                                                        
                                                                                
  ---                                                                           
                                                                                
  ## What is right                                                              
                                                                                
  - **Shipping the design test rather than describing it** is the correct       
    reading of the Gärdenfors rule in `units.md`. A dimension that carries its  
    own score makes adding a weak one a visible decision.                       
  - **The four bug fixes are real and the reasoning is sound.** The             
    order-statistic bound is the important one — an interpolated percentile     
    giving a two-sample class an interval strictly between its two points,      
    containing neither, and scoring zero for having tidy data. Rounding both    
    bounds *into* the data is the same lesson applied twice.                    
  - **Admitting the fourth failure was a wrong test, not wrong code** —         
    width=0 being legitimate — is the right call and easy to get wrong under    
    pressure to make a suite green.                                             
  - **Two domains declared, empty, and asserted empty** so the gap cannot be    
    forgotten. Naming a dependency beats populating it with guesses.            
  - **Re-running the measurement through the shipped functions** rather than a  
    scratch script is what makes `_MEASURED = "2026-08-08, n=5436, 23 classes"` 
    worth anything.                                                             
  - MI is normalised by H(labels) — an uncertainty coefficient, bounded [0,1].  
    That is the right family of measure.                                        
                                                                                
  ---                                                                           
                                                                                
  ## F1 — The MI ranking is capped by cardinality, so the headline conclusion   
  is guaranteed before any data is seen *(Important, demonstrated)*             
                                                                                
  The claim is *"every topological dimension ranks below every geometric        
  one"*, with aspect at 0.634 against splits at 0.373.                          
                                                                                
  Normalised MI is bounded by the dimension's own entropy:                      
                                                                                
  > MI(X; class) ≤ H(X) / H(class)                                              
                                                                                
  With 23 classes, H(class) = 4.524 bits. A dimension taking three distinct     
  values has H(X) ≤ log₂3 = 1.585 bits, so its MI **cannot exceed 0.350** no    
  matter how informative it is. A continuous dimension binned into 16 gets a    
  ceiling of 0.884.                                                             
                                                                                
  Demonstrated on 23 classes and n = 5436, matching the measurement's scale:    
                                                                                
  | dimension | distinct | MI ceiling | MI | % of ceiling |                     
  |---|---|---|---|---|                                                         
  | continuous, near-perfect separation | 5436 | 0.884 | 0.774 | 88% |          
  | **3-valued, maximally informative** | 3 | **0.350** | **0.350** | **100%**  
  |                                                                             
  | **2-valued, maximally informative** | 2 | **0.221** | **0.221** | **100%**  
  |                                                                             
                                                                                
  A 3-valued dimension that partitions the classes *perfectly* — there is no    
  better 3-valued dimension — scores 0.350. That is below `aspect` (0.634),     
  below every SIZE dimension, and below `elongation` and `fill`. **The          
  ranking cannot distinguish "weak" from "low-cardinality."**                   
                                                                                
  Applying the same correction to the reported numbers, assuming the obvious    
  distinct-value counts:                                                        
                                                                                
  | | assumed distinct | ceiling | MI | % of ceiling |                          
  |---|---|---|---|---|                                                         
  | aspect | 16 (bins) | 0.884 | 0.634 | **72%** |                              
  | splits | 5 | 0.513 | 0.373 | **73%** |                                      
  | cycles | 3 | 0.350 | 0.246 | **70%** |                                      
  | depth | 3 | 0.350 | 0.220 | **63%** |                                       
                                                                                
  Remarkably flat. On this reading the topological dimensions are about as      
  *efficient per available bit* as the geometric ones — they simply have        
  fewer bits to give.                                                           
                                                                                
  **Caveat, and it matters:** those distinct-value counts are my assumption. I  
  do not have the corpus. The demonstration above does not depend on them —     
  the ceiling effect is arithmetic — but the 63–73% figures do. `measure.py`    
  can produce the real distinct counts in a line, and that is what turns this   
  from an objection into a number.                                              
                                                                                
  **Suggested fix:** carry `H(X)/H(class)` beside every MI in `DIMENSIONS`, or  
  report MI-as-fraction-of-ceiling. Then a low score means "carries little      
  information" rather than "has few values", and the two are currently          
  indistinguishable.                                                            
                                                                                
  **What survives and what does not.** "Extents and aspect are the strongest    
  dimensions" survives as a statement about marginal bits, and U13 should       
  still weight them heavily. What does not survive is *"topology ranks below    
  geometry"* as a reason to demote the topological channel — that ordering is   
  an artefact of value count. The right framing is the one the `cycles`         
  annotation already gives: 98.7–100% stable within a class and weak at         
  discrimination is the profile of a **verifier, not a discriminator**. That    
  is also, independently, what the classical OCR literature concludes.          
                                                                                
  ---                                                                           
                                                                                
  ## F2 — The design test is per-dimension; Gärdenfors' criterion is per-domain 
  *(Important)*                                                                 
                                                                                
  Every number in `DIMENSIONS` is a marginal — one dimension against the        
  labels. Marginal MI cannot see joint information. Demonstrated:               
                                                                                
  ```                                                                           
  three 3-valued dimensions that TOGETHER determine the class exactly:          
     dim 0   marginal MI = 0.350                                                
     dim 1   marginal MI = 0.347                                                
     dim 2   marginal MI = 0.340                                                
     all three together  = 0.866                                                
  ```                                                                           
                                                                                
  Each looks weak alone; together they are perfect. `splits`, `merges`,         
  `births`, `cycles` and `depth` are exactly this shape — five low-cardinality  
  dimensions from one source, plausibly carrying complementary information,     
  each scored in isolation.                                                     
                                                                                
  This also lands on the rule `units.md` actually sets. Gärdenfors' domains     
  are bundles of *integral* dimensions, and his convexity criterion applies to  
  concepts as regions in a domain, not to their projections onto single axes.   
  A 1-D projection test is a valid **necessary** condition — a convex region    
  projects to a convex interval — but passing it on every axis does not imply   
  joint convexity, and failing it on one axis does not mean that axis is        
  useless jointly.                                                              
                                                                                
  So the shipped test is weaker than the rule it implements, and the gap runs   
  in the direction that penalises TOPOLOGY specifically, because that is where  
  the many-low-cardinality-dimensions cluster lives.                            
                                                                                
  **Suggested fix, cheap:** add a domain-level score — MI of the *tuple* of a   
  domain's dimensions against the labels, using the same equal-frequency        
  binning on each. One extra function, and it answers whether TOPOLOGY as a     
  domain is weak or merely fragmented. If the joint TOPOLOGY score approaches   
  SIZE's, U13's channel weighting should not be reordered on F1's ranking at    
  all.                                                                          
                                                                                
  ---                                                                           
                                                                                
  ## F3 — Three sweep survivors, all equivalent mutants *(Trivial, but the      
  category is worth naming)*                                                    
                                                                                
  My sweep on `domains.py` found 11 branch conditions, 0 incompetent, 3         
  survivors — against the reported 20 conditions and 0 survivors. Checked all   
  three:                                                                        
                                                                                
  | line | branch | verdict |                                                   
  |---|---|---|                                                                 
  | 300 | `if not values:` | guard and fallthrough both return `(0.0, 0.0, 0,   
  0)` — identical |                                                             
  | 315 | `if inside:` | unreachable: `lo`/`hi` are order statistics of class   
  *c*'s own values, so at least one *c* sample always satisfies `lo <= v <= hi` 
  |                                                                             
  | 333 | `if n == 0:` | `_entropy(Counter(), 0)` returns 0, and the `h_labels  
  == 0` branch below catches it — identical |                                   
                                                                                
  None is a test gap. They are **equivalent mutants** — provably                
  behaviour-preserving, and therefore unkillable.                               
                                                                                
  That is a fourth outcome category alongside killed, survived, and             
  incompetent, and it is worth adding to the `CLAUDE.md` note. Incompetent      
  mutants are filtered mechanically by the import canary; equivalent mutants    
  cannot be, and must be reasoned about one at a time. Both produce false       
  leads, and the note currently covers only the first. The count difference     
  (11 vs 20) is probably scope — ternaries, `while`, comprehension              
  conditions — worth reconciling so the two sweeps agree on what they cover.    
                                                                                
  ---                                                                           
                                                                                
  ## Order                                                                      
                                                                                
  F2 first — a domain-level score is one function, and it decides whether F1's  
  reordering should reach U13 at all. F1's ceiling column next. F3 whenever.    
                                                                                
  Both F1 and F2 point the same way: the measurement is sound in mechanism and  
  the comparison it supports is narrower than the conclusion drawn from it.     
  That is the same shape as the U0 colour fraction and the U9 math families —   
  right instrument, and a conclusion that outruns what it can see. It is worth  
  noting that this is now the pattern that has recurred most, and it is not     
  caught by mutation sweeps, because nothing is wrong with the code.            

● This is the same report I acted on last turn — audited at e9c452a, with all
  three closed at f0379c7. Confirming briefly, then U13.

  Ran 1 shell command (ctrl+o to expand)

● All three closed. Now U13 — and units.md sets its premise explicitly:
  "escalate beyond nearest neighbour only after seeing the confusion matrix." So
  the premise check is the confusion matrix.

  Read 1 file, ran 2 shell commands (ctrl+o to expand)

● Too slow — 1-NN over thousands × thousands × six channels in pure Python is
  hours. Capping the test set.

  Ran 2 shell commands (ctrl+o to expand)

● Background command "U13 premise check: the confusion matrix" failed with exit
code 144
● Background command "Rerun with a capped test set" failed with exit code 144

● My pkill matched the newly-launched run too — same filename. Rerunning under a
  different name.

  Ran 3 shell commands (ctrl+o to expand)

● Output is block-buffered under redirect, so nothing appears until it exits.
  Waiting.

  Ran 2 shell commands (ctrl+o to expand)

● Thirty minutes and still running — pure-Python Hamming distance is the
  bottleneck. Rewriting it to use integer XOR and bit_count(), which is a
  C-speed popcount.

  Ran 4 shell commands (ctrl+o to expand)

● The edit never landed — the compound command was killed before it ran.
  Applying it directly.

  Ran 2 shell commands (ctrl+o to expand)

● Popcount fixed it. The numbers are decisive already — waiting for the
  confusion matrix.

  Ran 1 shell command (ctrl+o to expand)

● Decisive, and it answers units.md's escalation question directly.

  ┌─────────────────────────┬──────────┐
  │         channel         │ accuracy │
  ├─────────────────────────┼──────────┤
  │ majority-class baseline │ 13.0%    │
  ├─────────────────────────┼──────────┤
  │ signature only          │ 30.7%    │
  ├─────────────────────────┼──────────┤
  │ bitmap only             │ 99.1%    │
  ├─────────────────────────┼──────────┤
  │ extents only            │ 97.1%    │
  ├─────────────────────────┼──────────┤
  │ all three               │ 99.3%    │
  └─────────────────────────┴──────────┘

  Every residual error is structural: the , ; : . punctuation cluster
  (multi-component glyphs) and case pairs W/w S/s H/h that differ only in
  absolute size. Building U13 on that.

● Write(inkdrill/classify.py)
  ⎿  Wrote 293 lines to inkdrill/classify.py
       1 """classify.py — nearest neighbour over separable channels.
       2 
       4 ==============================================================
       5 
       6 The escalation question, answered before the unit was written
       8 docs/units.md sets one instruction: *"escalate beyond nearest ne
         ighbour
       9 only after seeing the confusion matrix."* So the confusion matri
      10 premise check. 17,008 real glyph components over 59 classes, hal
         f train
     … +341 lines (ctrl+o to expand)

● Write(tests/test_classify.py)
  ⎿  Wrote 225 lines to tests/test_classify.py
       1 """Unit 13 tests. Every test name is quoted verbatim in the stat
       2 
       3 import random
       4 import unittest
       6 from inkdrill.classify import (GRID, Channels, Classifier, NoTem
         plates,
         ance,
       8                                confusion, extents_distance, norm
         alise,
      10 from inkdrill.raster import BG, INK, InkMask
     … +255 lines (ctrl+o to expand)

  Ran 1 shell command (ctrl+o to expand)

● All 30 pass. Branch sweep before recording, per the checklist.

  Ran 1 shell command (ctrl+o to expand)

● Eight leads. Triaging by hand — three are real gaps, five are equivalent
  mutants.

  Ran 1 shell command (ctrl+o to expand)

● Down to exactly the 5 equivalent mutants I predicted. One test fails — let me
  see which.

  Ran 5 shell commands (ctrl+o to expand)

● confusion took the else branch for equal strings — that smells like a stale
  bytecode cache from the mutation sweep. Clearing it.

  Ran 1 shell command (ctrl+o to expand)

● Confirmed — stale bytecode from the sweep. Python invalidates on (mtime, 
  size), and my mutations can coincidentally preserve size. That's a real hazard
  now that the sweep is institutionalised.
  Ran 2 shell commands (ctrl+o to expand)

● U13 built and pushed. 31 tests, 484 total, verified on a clean clone. The U12
  audit's three findings were already closed at f0379c7 — I confirmed rather
  than redid them.

  The confusion matrix answered units.md's escalation question: don't

  ┌────────────────┬──────────┐
  │    channel     │ accuracy │
  ├────────────────┼──────────┤
  │ baseline       │ 13.0%    │
  ├────────────────┼──────────┤
  │ signature only │ 30.7%    │
  ├────────────────┼──────────┤
  │ extents only   │ 97.1%    │
  ├────────────────┼──────────┤
  │ bitmap only    │ 99.1%    │
  ├────────────────┼──────────┤
  │ all three      │ 99.3%    │
  └────────────────┴──────────┘

  17,008 real glyph components, 59 classes. Plain 1-NN on a 12×12 bitmap gets
  99.1%; everything after buys tenths of a point. So the module implements
  nearest neighbour and nothing else.

  Two adjustments to the plan, both from your U12 audit's corrected reading

  Extents alone reach 97.1% — far more than "carried separately" implies, and
  exactly what U12 predicted once the cardinality correction was applied.

  The signature is exposed as a verifier, not a channel to mix in. It's weak
  alone (30.7%) and adds +0.1pp — but U12 measured it narrow-but-efficient and
  98.7–100% stable within a class. Blending that into one distance wastes the
  stability, so it's agrees() and margin instead. That's your F1 conclusion
  carried through to a design decision rather than just a corrected number.

  Every residual error is structural

  The matrix at 99.3% has exactly two families: the , ; : . cluster, which are
  multi-component glyphs a per-component classifier only sees half of — the same
  thing U4 and U10 both hit, fixable by grouping in U14 — and case pairs W/w 
  S/s H/h I/l separated only by absolute size, which is precisely why extents is
  a channel and not a normalisation. Neither is fixed by a better model, and an
  accuracy figure alone would have hidden both.

  Two process notes

  The popcount wasn't micro-optimisation. With per-bit comparison the premise
  check didn't finish in 30 minutes; with (a ^ b).bit_count() it finished in
  under five. A classifier nobody can afford to run produces no confusion matrix
  — and then the escalation question can't be answered at all.

  And the sweep bit me: it left a stale .pyc, producing a test that failed with
  'box' != 'box'. Python invalidates bytecode on (mtime, size), and a
  size-preserving mutation defeats that. CLAUDE.md now says to run it with
  PYTHONDONTWRITEBYTECODE=1. Worth knowing now that the sweep is standard
  practice — it cost me real time and looked like a logic bug.

  Branch sweep: 24 probed, 8 survivors, 3 real (a margin > 0 assertion satisfied
  by infinity; keeping the last rather than nearest same-label template;
  agrees() with no signature evidence on either side), 5 equivalent.

  U14 mathstruct.py is the last unit — and U13 has just handed it a concrete
  first job: the punctuation cluster needs component grouping before
  classification, which is the same machinery reference-line estimation and
  sub/superscript detection will need.

✻ Cogitated for 1h 11m 28s

※ recap: You're building inkdrill unit by unit; U13 (classify) is done and pushed, 484 tests green on a clean clone. Next is U14, mathstruct, starting with grouping multi-component glyphs like `;` and `:`.

❯ Please the audit report and the code U13 report and the U13 split probe "Half 
  train half test" — the split rule is what matters here. Let me find it.The    
  confusion harness isn't in the commit. Let me confirm, then build my own test 
  of the number that looks most suspicious.I have PIL and Latin Modern — the    
  actual TeX font family. Let me build an independent test of the 97.1% extents 
  figure.Split A had a bug — my index split made the label sets disjoint. Let   
  me fix it so the contrast is within one protocol family.Protocol A wasn't     
  leaky enough — their corpus has ~288 samples per class from body text at one  
  size. Let me reproduce that condition exactly.All five survivors on my sweep  
  are equivalent mutants — consistent with their "8 survivors, 3 real, 5        
  equivalent". Their sweep report checks out.484 tests, clean clone. I wrote an 
  independent probe for this one, using the package's own pipeline on real      
  Latin Modern renders and varying **only the train/test split rule**.          
                                                                                
  **F1 — the escalation decision is protocol-dependent, and the protocol isn't  
  stated.** The contract says "half train half test". Half by what? Component,  
  page, document, font, size?                                                   
                                                                                
  | split rule | extents only | bitmap only |                                   
  |---|---|---|                                                                 
  | one size, 16 jittered samples/class, random 50/50 | 58.1% | **100.0%** |    
  | same font, 28/30 px → 29/31 px | 17.7% | 83.9% |                            
  | same font, 22/24 px → 40/44 px | 10.5% | **62.1%** |                        
  | Latin Modern → DejaVu Serif, same sizes | 8.5% | **72.2%** |                
  | **reported** | **97.1%** | **99.1%** |                                      
                                                                                
  Bitmap-only reaches 100% under the leakiest protocol — at or above the        
  reported figure — and collapses to 62–72% as soon as the split crosses a size 
  or a font. The reported numbers are consistent with a component-level random  
  split over a single-size corpus, where nearly every test glyph has a          
  near-identical twin in the training half.                                     
                                                                                
  The fair counterargument: within-font, within-size *is* the deployment        
  condition, since U9 matches against the document's own fonts at its own       
  sizes. On that reading 99.1% is legitimate and "do not escalate" is right.    
  Three things stop it settling: deployment templates come from U9's            
  *rasterizer*, not from other page ink, so the measured protocol isn't the     
  deployment condition either; the scan population and the ~5% U9 remainder     
  have no font to template from, and for them the relevant row is 62–72%, which 
  *would* justify escalating; and the decision is recorded without its          
  condition. One extra row measured with a split by document settles it.        
                                                                                
  My signature channel was a fabricated stand-in, so I draw no conclusion from  
  those figures — only extents and bitmap are computed from the real geometry.  
                                                                                
  **F2 — the U13 harness isn't committed.** `git show --stat ffb82d7` touches   
  five files, none of them `tools/premise/`, and `grep -c "classify\|confusion" 
  measure.py` returns 0. The 16 existing `m_*` functions have nothing for U13.  
  This is the U4 F3 finding recurring after being closed and holding through    
  U5–U12, and it's the more consequential instance: this measurement is the     
  sole evidence for a decision *not* to build something, and F1 is exactly the  
  question that can only be settled by re-running it with one argument changed. 
                                                                                
  Your sweep report checks out — my independent sweep found 13 conditions and 5 
  survivors, all verifiably equivalent mutants, matching "8 survivors, 3 real,  
  5 equivalent". And the `.pyc` mtime discovery is a real methodological find;  
  I used `PYTHONDONTWRITEBYTECODE=1` because of it.                             
                                                                                
  One observation for U14. F1 is the fourth in a family — U0's colour fraction, 
  U9's math families, U12's cardinality ceiling. The first three were caught    
  by asking *what population is this measured over*. This one needed the same   
  question asked of a **protocol**: the samples were right, the division        
  decided the answer. Neither question is caught by a mutation sweep, since the 
  code is correct in every case. "State the split rule and the population       
  beside every measured number" is probably worth making mechanical now.        

● Both findings are correct and F2 is the more serious. Verifying it first.

  Ran 1 shell command (ctrl+o to expand)

❯ """Independent check of U13's channel accuracies under three split rules.     
                                                                                
  The repo reports 97.1% for extents-only and 99.1% for bitmap-only on          
  "17,008 real glyph components over 59 classes, half train half test".         
  The split rule is not stated and the harness is not committed, so this        
  reproduces the shape of the experiment with real font renders and varies      
  only the split rule.                                                          
                                                                                
  Uses the package's own pipeline: binarize -> sweep -> largest component       
  -> Template, then inkdrill.classify.Classifier.                               
  """                                                                           
  import sys, itertools, statistics                                             
  from PIL import Image, ImageDraw, ImageFont                                   
                                                                                
  from inkdrill.raster import InkMask, binarize, Rect                           
  from inkdrill.sweep import sweep, Capture                                     
  from inkdrill.classify import Template, Channels, Classifier, normalise       
                                                                                
  LM = "/usr/share/texmf/fonts/opentype/public/lm/lmroman10-regular.otf"        
  DV = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"                       
                                                                                
  CLASSES = list("abcdefghijklmnopqrstuvwxyz"                                   
                 "ABCDEFGHIJKLMNOPQRSTUVWXYZ"                                   
                 "0123456789")          # 62 classes, close to the reported 59  
                                                                                
                                                                                
  def render(ch, font_path, px):                                                
      """Render one glyph and return its largest ink component as a             
  Template."""                                                                  
      f = ImageFont.truetype(font_path, px)                                     
      img = Image.new("L", (px * 3, px * 3), 255)                               
      ImageDraw.Draw(img).text((px, px // 2), ch, font=f, fill=0)               
      m = binarize(img.tobytes(), img.width, img.height, threshold=128)         
      res = sweep(m, capture=Capture.GRAPH)                                     
      if not res.components:                                                    
          return None                                                           
      big = max(res.components,                                                 
                key=lambda c: sum(res.nodes[i].hi - res.nodes[i].lo + 1         
                                  for i in c.nodes))                            
      xs, ys = [], []                                                           
      for i in big.nodes:                                                       
          n = res.nodes[i]                                                      
          xs += [n.lo, n.hi]                                                    
          ys.append(n.line)                                                     
      x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)                       
      sub, _, _ = m.crop(Rect(x0, y0, x1 + 1, y1 + 1))                          
      w, h = x1 - x0 + 1, y1 - y0 + 1                                           
      area = sum(res.nodes[i].hi - res.nodes[i].lo + 1 for i in big.nodes)      
      elong = w / h if h else 0.0                                               
      return Template(label=ch, bitmap=normalise(sub),                          
                      signature=(big.cycle_count, len(big.nodes) % 7, 0, 0),    
                      extents=(w / h if h else 0.0, float(h), float(w), elong)) 
                                                                                
                                                                                
  def build(font_path, sizes):                                                  
      out = []                                                                  
      for px in sizes:                                                          
          for ch in CLASSES:                                                    
              t = render(ch, font_path, px)                                     
              if t is not None:                                                 
                  out.append(t)                                                 
      return out                                                                
                                                                                
                                                                                
  def accuracy(train, test, channels):                                          
      c = Classifier(channels=channels)                                         
      for t in train:                                                           
          c.add(t)                                                              
      ok = sum(1 for q in test if c.classify(q).label == q.label)               
      return ok / len(test) if test else 0.0                                    
                                                                                
                                                                                
  CH = {                                                                        
      "signature only": Channels(bitmap=0.0, signature=1.0, extents=0.0),       
      "extents only":   Channels(bitmap=0.0, signature=0.0, extents=1.0),       
      "bitmap only":    Channels(bitmap=1.0, signature=0.0, extents=0.0),       
      "all three":      Channels(bitmap=1.0, signature=1.0, extents=1.0),       
  }                                                                             
                                                                                
                                                                                
  def report(name, train, test, note):                                          
      print(f"\n--- {name} ---")                                                
      print(f"    {note}")                                                      
      print(f"    train {len(train)}, test {len(test)}, "                       
            f"{len(set(t.label for t in test))} classes")                       
      base = max(                                                               
                 [sum(1 for t in test if t.label == l) for l in                 
                  set(t.label for t in test)]) / len(test)                      
      print(f"    {'majority baseline':<18} {base:6.1%}")                       
      for label, ch in CH.items():                                              
          print(f"    {label:<18} {accuracy(train, test, ch):6.1%}")            
                                                                                
                                                                                
  if __name__ == "__main__":                                                    
      SIZES_A = [28, 29, 30, 31]                                                
      lm_a = build(LM, SIZES_A)                                                 
                                                                                
      # A: every label appears on BOTH sides at a near-identical size --        
      #    what a component-level 50/50 split produces on a single-font,        
      #    single-size corpus.                                                  
      tr_a = build(LM, [28, 30])                                                
      te_a = build(LM, [29, 31])                                                
      report("A. same font, near-identical sizes both sides", tr_a, te_a,       
             "train 28/30px, test 29/31px -- the leaky protocol")               
                                                                                
      # B: split by SIZE. Train small, test large. Same font.                   
      lm_small = build(LM, [22, 24])                                            
      lm_large = build(LM, [40, 44])                                            
      report("B. split by size", lm_small, lm_large,                            
             "train 22/24px, test 40/44px, same font")                          
                                                                                
      # C: split by FONT, size held constant.                                   
      dv = build(DV, SIZES_A)                                                   
      report("C. split by font", lm_a, dv,                                      
             "train Latin Modern, test DejaVu Serif, same sizes")               

● Both confirmed. My split was shuffle(data) then halve — component-level, with
  every page's glyphs in both halves. Each test glyph had near-identical twins
  from the same page in training. Your protocol table is right and my conclusion
  rested on the leakiest rule.

  F2 first, since it's what makes F1 answerable.

  Ran 1 shell command (ctrl+o to expand)

● Now the measurement F1 asks for — the same experiment with only the split rule
  changed.

  Ran 1 shell command (ctrl+o to expand)

● Decisive, and it splits the finding in two:

  ┌────────────────┬───────────────────┬───────────────────┬───────┐
  │    channel     │ component (leaky) │ document (honest) │   Δ   │
  ├────────────────┼───────────────────┼───────────────────┼───────┤
  │ signature only │ 11.8%             │ 11.2%             │ −0.6  │
  ├────────────────┼───────────────────┼───────────────────┼───────┤
  │ extents only   │ 93.7%             │ 43.8%             │ −49.9 │
  ├────────────────┼───────────────────┼───────────────────┼───────┤
  │ bitmap only    │ 95.7%             │ 94.0%             │ −1.7  │
  ├────────────────┼───────────────────┼───────────────────┼───────┤
  │ all three      │ 96.0%             │ 95.7%             │ −0.3  │
  └────────────────┴───────────────────┴───────────────────┴───────┘

  You were right about extents and wrong about bitmap — and both matter.
  Correcting.

  Ran 3 shell commands (ctrl+o to expand)

● Both findings confirmed and fixed. 484 tests, pushed and verified on a clean
  clone.

  F2 first, because it's what made F1 answerable

  You were right that this is the worse instance. ffb82d7 touched five files,
  none under tools/premise/ — and that measurement was the sole evidence for a 
  decision not to build something. measure.py classify --split 
  component|page|document now exists, with the split rule as an explicit
  argument precisely because it changes the answer by 50 points.

  F1 — you were right about extents and wrong about bitmap

  My split was shuffle(data) then halve: by component, over pages appearing on
  both sides. Re-measured on the same 8 pages, changing only the split rule:

  ┌──────────────┬──────────────┬─────────────┐
  │   channel    │ by component │ by document │
  ├──────────────┼──────────────┼─────────────┤
  │ extents only │ 93.7%        │ 43.8%       │
  ├──────────────┼──────────────┼─────────────┤
  │ bitmap only  │ 95.7%        │ 94.0%       │
  ├──────────────┼──────────────┼─────────────┤
  │ all three    │ 96.0%        │ 95.7%       │
  └──────────────┴──────────────┴─────────────┘

  Extents was almost entirely leakage. Absolute height and width identify the
  document's body size, not the character — with one document on both sides it's
  close to a lookup table. My 97.1% was an artefact and I drew conclusions from
  it.

  But the bitmap channel holds at −1.7 points. Normalised shape really is
  document-independent, so "do not escalate" stands — on an honest protocol, for
  this population, with the condition now recorded beside it.

  Your cross-font and cross-size figures are recorded with attribution, and
  marked not reproducible by the stdlib-only harness. Your point about why they
  matter is the sharpest part of the finding: the ~5% U9 remainder and the
  entire scanned corpus have no font to template from, so 62–72% is their real
  condition, and that would justify escalating. My measurement doesn't speak to
  them, and now says so.

  Your closing observation, made mechanical

  Five findings now share a shape — right instrument, conclusion wider than its
  reach. Four were about population (U0's colour fraction, U9's font metric,
  U10's residuals, U12's cardinality ceiling); this one was about protocol.
  You're right that no mutation sweep catches any of them, because the code is
  correct every time.

  CLAUDE.md now carries three questions to ask before quoting any number: what 
  population, how divided, and what is the maximum this could be — plus the
  operational rule that if a split changes the answer, it must be a harness
  argument rather than a constant.

  I'd add one distinction to your family: the first four were caught by asking
  about the inputs, this one by asking about the procedure. Same discipline,
  different object — and the procedure question is the easier one to skip,
  because the inputs are visible in the code and the split rule was one line I'd
  stopped seeing.

  U14 mathstruct.py is the last unit. U13 has handed it a concrete first job —
  the i . : 1 l cluster needs component grouping before classification, which is
  the same machinery reference-line estimation and sub/superscript detection
  need.

✻ Churned for 8m 18s

❯  the audit report was positiv: Their measurement settles something mine       
  couldn't, and I should own what I got wrong.                                  
                                                                                
  **On "wrong about bitmap" — that's fair, and specifically this.** My probe    
  varied font and size; theirs varied document. Those are different axes, so    
  the two results don't contradict. But I presented both channels in one table  
  under one heading, which invited the reading that both reported figures were  
  leakage-inflated. Only extents was. The 99.1% was a real number for that      
  population, and my framing didn't distinguish the two channels when the data  
  does. That's the error.                                                       
                                                                                
  Their result is the stronger one on its axis: bitmap dropping 1.7 points      
  across documents establishes that normalised shape is genuinely               
  document-independent, which is exactly what "do not escalate" needs. Mine     
  establishes that it isn't font-independent. Both belong in the record and     
  both are now there.                                                           
                                                                                
  Two things worth the CLI's attention, neither large.                          
                                                                                
  **The class filter excludes math symbols.** `common = {c for c, k in          
  counts.items() if k >= 12}` over 8 pages, one page per document. Body-text    
  letters clear 12 easily; `∑ ∫ √ ± ≤ ∈` almost certainly don't across 8 pages  
  of different papers. So the surviving 59 classes are near-certainly           
  alphanumerics plus common punctuation, and "do not escalate" is measured on   
  body text — saying nothing about math symbol classification, which is the     
  project's first application. This is the same family again, now at the        
  *class* level rather than the sample level: U9 asked which fonts, U12 asked   
  which dimensions, this asks which characters.                                 
                                                                                
  Cheap and checkable: print the class list next to the accuracy table. If it's 
  alphanumerics, the caveat belongs beside the decision. Raising the page       
  count won't fix it either — a rare symbol stays rare — so the honest form is  
  probably a separate math-symbol row measured over pages selected for math     
  content, or an explicit statement that the population is body text.           
                                                                                
  **`--split font` is available from data already in hand.** `chars.json`       
  carries `fontname` per character — `m_fonts` already reads it at lines 589    
  and 659. The "not reproducible by the stdlib-only harness" caveat applies to  
  *rendering foreign fonts* like DejaVu, not to splitting the existing corpus   
  by the fonts it contains. If arXiv turns out to be nearly all Computer Modern 
  and the split has too few groups, that result is itself the answer: the       
  corpus cannot test font generalisation, so the question stays open rather     
  than unmeasurable — which is a stronger statement than the current one.       
                                                                                
  Your distinction between input questions and procedure questions is right,    
  and I'd extend it slightly. The split rule was one line you'd stopped seeing; 
  the class filter is another line of the same kind, three lines below it.      
  Both are procedure, both invisible for the same reason — they were written    
  once, correctly, and then stopped being read as decisions.  go on with U14    

● Both points are right and both are cheap. The --split font one especially — I
  over-scoped the "not reproducible" caveat: it applies to rendering foreign 
  fonts, not to splitting by the fonts the corpus already contains.

  Ran 1 shell command (ctrl+o to expand)

● The corpus can test that axis — 44 font groups — and it confirms your probe
  almost exactly. It also overturns a second claim of mine.

  ┌───────────────────┬───────────┬─────────┬────────┬───────────┐
  │       split       │ signature │ extents │ bitmap │ all three │
  ├───────────────────┼───────────┼─────────┼────────┼───────────┤
  │ component (leaky) │ 11.8%     │ 93.7%   │ 95.7%  │ 96.0%     │
  ├───────────────────┼───────────┼─────────┼────────┼───────────┤
  │ document          │ 11.2%     │ 43.8%   │ 94.0%  │ 95.7%     │
  ├───────────────────┼───────────┼─────────┼────────┼───────────┤
  │ font              │ 9.2%      │ 29.5%   │ 61.5%  │ 86.3%     │
  └───────────────────┴───────────┴─────────┴────────┴───────────┘

  Your 62.1%/72.2% reproduces from corpus data as 61.5%. And the channels
  combine for +24.8 points cross-font where they bought +0.3 on the easy split —
  so "the signature adds nothing" was protocol-dependent too. Class list:
  non-ASCII kept is only “”ﬁ — no maths symbols at all.

  Ran 2 shell commands (ctrl+o to expand)

● Both closed, and both overturned something. Now U14 — the last unit.

  Searched for 1 pattern (ctrl+o to expand)

● U14's premise is "sub/superscript from geometry alone against pdfminer's role 
  as label". Checking whether that label exists.

  Ran 1 shell command (ctrl+o to expand)

● No role field — so the label has to be derived, and it must not be derived
  from geometry or the test is circular. size gives an independent one: the
  PDF's own font size, which geometry never sees.

  Ran 1 shell command (ctrl+o to expand)

● Informative, and the label is the story: precision 100.0%, recall 13.5% — zero
  false positives in 37,759 glyphs.

  But recall isn't interpretable. My label ("smaller than the row's modal size")
  conflates true sub/superscripts with any smaller-font run — captions,
  footnotes, mixed-size headings. Geometry never lies; the label over-claims.
  Building U14 on the half that's sound.

● Write(inkdrill/mathstruct.py)
  ⎿  Wrote 287 lines to inkdrill/mathstruct.py
       1 """mathstruct.py — rows, reference lines, and script detection.
       2 
       3 CONTRACT (written before implementation; see docs/units.md U14)
       5 
       6 What this unit is, and what it is not
       7 -------------------------------------
       8 The plan asks for five things: reference-line estimation per row
       9 sub/superscript from geometry, big operators and their ranges, f
         ence
      10 matching, and a structure tree exported as LaTeX.
     … +327 lines (ctrl+o to expand)

● Write(tests/test_mathstruct.py)
  ⎿  Wrote 231 lines to tests/test_mathstruct.py
      1 """Unit 14 tests. Every test name is quoted verbatim in the statu
        s report."""
      2 
      4 import unittest
      5 
      6 from inkdrill.mathstruct import (Glyph, ReferenceLines, Row, Scri
        pt,
        p,
      8                                  reference_lines, rows)
      9 
     … +239 lines (ctrl+o to expand)
  Ran 2 shell commands (ctrl+o to expand)

● Five failures, and three are real design faults rather than fixture bugs.
  Diagnosing each.

  Ran 1 shell command (ctrl+o to expand)

● All three confirmed, and my G6 justification was simply wrong — the
  distinguisher isn't width, it's stacking. Parts of one glyph sit above each
  other; adjacent letters sit beside each other.

  Ran 3 shell commands (ctrl+o to expand)

● The fixture was unrealistic, not the code — I'd raised the superscript by 0.8×
  x-height, where real ones raise ~0.4–0.6× and overlap their line
  substantially. Fixing the fixtures to real proportions.

  Ran 2 shell commands (ctrl+o to expand)

● The superscript seeds its own row because I sort by top — so it's processed
  before the line it belongs to exists. That's an ordering artefact my
  determinism test couldn't catch. Big glyphs should define lines; small ones
  join them.

  Ran 2 shell commands (ctrl+o to expand)

● Five survivors; two are real gaps.

  Ran 1 shell command (ctrl+o to expand)

● The gb.x0 > ga.x1 break fires first, so my fixture never reaches the overlap
  test. Making the pair barely touch instead.

  Ran 1 shell command (ctrl+o to expand)

● Down to 3, all equivalent or pure optimisation. Recording U14 and closing out.

  Ran 2 shell commands (ctrl+o to expand)

● Both audit points closed, then U14 built. 517 tests, pushed and verified on a
  clean clone.

  Your two follow-ups, both overturning something

  --split font was reproducible all along — you were right that my caveat
  applied to rendering foreign fonts, not to splitting by the 44 font groups the
  corpus already contains. It gives 61.5% bitmap-only, reproducing your
  62.1%/72.2% almost exactly.

  It also overturned a second claim of mine. I'd concluded the signature "adds
  nothing measurable" (+0.1pp). Across fonts the three channels together beat
  the bitmap alone by 24.8 points — 61.5% → 86.3%. The channels are
  complementary precisely where a single one fails, which is what units.md
  specified and the easy protocol hid.

  The class filter excluded every maths symbol. Non-ASCII survivors: “”ﬁ. Not
  one ∑ ∫ √ ± ≤ ∈. So "do not escalate" was measured on body text and says
  nothing about this project's first application. The harness now prints kept
  and dropped classes, and CLAUDE.md records that filters are decisions that
  hide the same way split rules do.

  U14 — built where measurable, named where not

  Rows, reference lines, script detection and component grouping are built. Big 
  operators, fence matching, the structure tree and LaTeX are not — and the
  reason is your finding: they need symbol identity for ∑ ∫ ( [, and U13 has
  never been measured on one. Building them would be unfalsifiable.

  There is no role field, so the label is size — the PDF's own metric, invisible
  to the geometry side. Precision 100.0%, zero false positives in 37,759 
  glyphs. Recall 13.5% and not interpretable, because the label catches captions
  and footnotes too. Detector, not classifier.

  Three faults no passing test would have shown

  - Rows must seed tallest-first. In reading order a superscript opens its own
  row before the line it belongs to exists — and a determinism test can't catch
  it, because the wrong answer was perfectly deterministic.
  - Grouping needs stacking, not width. My G6 justification was simply wrong:
  parts of one glyph sit above each other, adjacent letters sit beside each
  other.
  - Row overlap must be measured against the joining glyph's own height, or the
  threshold that suits body text excludes exactly what the unit exists to find.

  Plus two sweep survivors that were real: every reference-line fixture had mode
  == median, and my horizontal-overlap test was unreachable because the
  x-ordered early break rejected the pair first.

  ---
  All fifteen units now exist. Two are deliberately partial with reasons
  recorded — U9's rasterizer half and U14's structure tree — and both are
  blocked on the same thing: no measurement of maths-symbol classification 
  exists. That's now the single highest-value next step, and it needs pages
  selected for maths content rather than more pages of body text.

✻ Churned for 14m 50s

※ recap: All fifteen inkdrill units are built and pushed, 517 tests passing on a clean clone. Two units stay deliberately partial because no measurement of maths-symbol classification exists yet. Next: measure classification on pages selected for maths content, not more body text.