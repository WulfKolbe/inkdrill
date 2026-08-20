"""The finding vocabulary shared by the compare harnesses (P19).

One definition, because a flag that means different things in two
files is worse than no flag. Ordered by strength of evidence.
"""

from __future__ import annotations

FLAGS = ("clean", "component", "stable", "soft")


def flag_of(distance: int, comp_delta: int, scale_stable: bool) -> str:
    """The finding class of one compared row.

    clean      distance 0 -- the two renditions agree exactly.
    component  the component count differs. That is the
               scale-invariant channel (identical 300<->600 dpi in
               every cell of both columns, measured 5/5 precision at
               distance > 35 on bh2), so it is the strongest class.
    stable     components agree, but the disagreement SURVIVES the
               300->600 dpi change, so it is not raster noise.
    soft       a nonzero distance in the threshold-sensitive channels
               only (holes and the pair counts).
    """
    if distance == 0:
        return "clean"
    if comp_delta > 0:
        return "component"
    return "stable" if scale_stable else "soft"
