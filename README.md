# inkdrill

Scan-event topology for document layout analysis and math expression
recognition. Pure standard library, no numpy, no GPU.

    python3 -m unittest discover -s tests -t .

The implementation plan, the locked conventions, the measured performance
numbers and the list of unverified assumptions are in `docs/units.md`.

Status: U0 `pngio`, U1 `space`, U2 `raster`, U3 `sweep`, U4 `reeb`, U5 `aggregate`, U6 `nest`, U7 `band`, U8 `sched`, U9 `font` (inventory half), U10 `gold`, U11 `coverage`, U12 `domains`, U13 `classify`, U14 `mathstruct` — 513 tests passed (517 collected, 4 corpus tests skip by default).
