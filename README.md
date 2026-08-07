# inkdrill

Scan-event topology for document layout analysis and math expression
recognition. Pure standard library, no numpy, no GPU.

    python3 -m unittest discover -s tests -t .

The implementation plan, the locked conventions, the measured performance
numbers and the list of unverified assumptions are in `docs/units.md`.

Status: U0 `pngio`, U1 `space`, U2 `raster`, U3 `sweep`, U4 `reeb` — 183 tests passed (187 collected, 4 corpus tests skip by default).
