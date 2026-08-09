# inkdrill

Scan-event topology for document layout analysis and math expression
recognition. Pure standard library, no numpy, no GPU.

    python3 -m unittest discover -s tests -t .

Goals and current state: `docs/state.md`. The implementation plan, locked
conventions, measured performance numbers and assumption list:
`docs/units.md`. Algorithms, inner-loop performance and the ranked
improvement list: `docs/algorithms.md`. Conventions and review
disciplines for contributors: `CLAUDE.md`.

All fifteen units exist. U9 is its inventory half only and U14 its
geometry only; U8's band tier was deliberately not built. Each gap
carries the measurement that decided it. The highest-value next step is
the U9 rasterizer — see `docs/state.md` section 5.

Status: U0 `pngio`, U1 `space`, U2 `raster`, U3 `sweep`, U4 `reeb`, U5 `aggregate`, U6 `nest`, U7 `band`, U8 `sched`, U9 `font` (inventory half), U10 `gold`, U11 `coverage`, U12 `domains`, U13 `classify`, U14 `mathstruct` — 515 tests passed (519 collected, 4 corpus tests skip by default).
