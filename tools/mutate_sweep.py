"""mutate_sweep.py -- the mutation gate for the sweep case dispatch.

Each mutant is a single textual edit applied to the LIVE `sweep` in a
throwaway copy of the package; `_sweep_reference` is never touched, so
the equivalence harness still has its oracle. A mutant that SURVIVES
means tests/test_sweep_equiv.py does not reach that line, and it is the
fixture set that needs fixing, not the mutant.

    python3 tools/mutate_sweep.py            # run every mutant
    python3 tools/mutate_sweep.py M3         # run one

Edits are applied to the last occurrence in the file, which is the live
sweep -- _sweep_reference is the earlier copy. `apply_last` now REFUSES
an anchor whose offset is before `def sweep(`, because a shared block
that happens to end earlier would silently mutate the oracle instead;
that mistake was made twice while writing the B1 accumulators, and it
presents as seven unrelated tests erroring on a NameError.

TWO FAMILIES
------------
M1-M12   the case dispatch -- union-find, counters, events, `attach`.
MM1-MM13 CR B1's per-component moment and extent accumulators. These
         are killed by `assert_moments`, which compares against
         `aggregate.moments_per_component`; the M series is killed by
         `assert_same`, which compares against `_sweep_reference`.

ONE KNOWN EQUIVALENT MUTANT, DELIBERATELY ABSENT
------------------------------------------------
`moms_of[rn] = moms_of.pop(rp)` -> `moms_of[rn] = moms_of[rp]` on the
ATTACH path. It leaves a stale entry behind, but `rp` has just become
a child and union-find roots never become roots again, so nothing can
ever read it. Verified by digest over 27 fixtures x 4, 40 random masks
and a real 15.5 Mpx page: byte-identical. It is UNKILLABLE and must
not be added here -- it would fail the gate forever. It is not free,
though: it leaks one entry per root-move, measured at 739 stale
against 421 live components on p1, so `pop` stays and the cost is
visible only in a memory measurement.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# name -> (what it breaks, old, new)
MUTANTS = {
    "M1": (
        "union_roots size tie-break < -> <=  (renumbers roots, counts stay right)",
        "        if self.size[ra] < self.size[rb]:\n            ra, rb = rb, ra\n"
        "        self.parent[rb] = ra\n        self.size[ra] += self.size[rb]\n"
        "        return ra\n",
        "        if self.size[ra] <= self.size[rb]:\n            ra, rb = rb, ra\n"
        "        self.parent[rb] = ra\n        self.size[ra] += self.size[rb]\n"
        "        return ra\n",
    ),
    "M2": (
        "first-parent attach arguments swapped",
        "                rn = uf.attach(nid, rp)",
        "                rn = uf.attach(rp, nid)",
    ),
    "M3": (
        "first-parent edge not counted on the root-stays branch",
        "                    edges_of[rp] += 1",
        "                    edges_of[rp] += 0",
    ),
    "M3b": (
        "first-parent edge not counted on the root-moves branch",
        "                    edges_of[rn] = edges_of.pop(rp) + 1",
        "                    edges_of[rn] = edges_of.pop(rp) + 0",
    ),
    "M4": (
        "further-parents loop starts at the first parent again",
        "                for k in range(pi + 1, pj):",
        "                for k in range(pi, pj):",
    ),
    "M5": (
        "root not carried forward after a later merge",
        "                        rn = uf.union_roots(rn, rp)\n"
        "                        edges_of[rn] = e\n"
        "                        cycles_of[rn] = c",
        "                        rn2 = uf.union_roots(rn, rp)\n"
        "                        edges_of[rn2] = e\n"
        "                        cycles_of[rn2] = c",
    ),
    "M6": (
        "BIRTH counter pair given the wrong initial value",
        "                edges_of[nid] = 0\n                cycles_of[nid] = 0",
        "                edges_of[nid] = 1\n                cycles_of[nid] = 0",
    ),
    "M7": (
        "CYCLE does not raise the hole count",
        "                        cycles_of[rn] += 1\n                        edges_of[rn] += 1",
        "                        cycles_of[rn] += 0\n                        edges_of[rn] += 1",
    ),
    "M8": (
        "adjacency predicate loses the endpoint on the Capture.NONE scan",
        "                while pj < nprev and prevline[pj][0] <= r.hi + slack:\n"
        "                    pj += 1\n            nadj = pj - pi",
        "                while pj < nprev and prevline[pj][0] < r.hi + slack:\n"
        "                    pj += 1\n            nadj = pj - pi",
    ),
    "M9": (
        "roots_before / adj guarded on the wrong capture level",
        "            if keep_events:\n                adj = []",
        "            if keep_graph:\n                adj = []",
    ),
    "M10": (
        "kids_of not recorded for the first parent (SPLIT events lost)",
        "                p = prevline[pi][2]\n                if keep_events:\n"
        "                    kids_of.setdefault(p, []).append(nid)",
        "                p = prevline[pi][2]\n                if False:\n"
        "                    kids_of.setdefault(p, []).append(nid)",
    ),
    "M11": (
        "attach fast path does not grow the component size",
        "        if self.size[root] > 1:\n            self.parent[new_id] = root\n"
        "            self.size[root] += 1\n            return root\n",
        "        if self.size[root] > 1:\n            self.parent[new_id] = root\n"
        "            return root\n",
    ),
    "M12": (
        "attach fast path returns the new singleton instead of the root",
        "            return root\n        return self.union_roots(new_id, root)",
        "            return new_id\n        return self.union_roots(new_id, root)",
    ),
    # -- CR B1: the moment and extent accumulators --------------------
    # Killed by `assert_moments` (against `aggregate`), not by
    # `assert_same` (against `_sweep_reference`, which has no moments).
    "MM1": (
        "sx and sy swapped in the row branch",
        "                    rsx = rs1\n                    rsy = rn_area * k",
        "                    rsx = rn_area * k\n                    rsy = rs1",
    ),
    "MM2": (
        "sxy uses the run length where the index sum belongs",
        "                    rsxy = k * rs1\n                else:",
        "                    rsxy = k * rn_area\n                else:",
    ),
    "MM3": (
        "_sum_ii used where _sum_i belongs",
        "                rs1 = _sum_i(r.lo, r.hi)",
        "                rs1 = _sum_ii(r.lo, r.hi)",
    ),
    "MM4": (
        "_sum_i used where _sum_ii belongs",
        "                rs2 = _sum_ii(r.lo, r.hi)",
        "                rs2 = _sum_i(r.lo, r.hi)",
    ),
    "MM5": (
        "min/max swapped for x0 on the attach path",
        "                    if rx0 < v[6]:",
        "                    if rx0 > v[6]:",
    ),
    "MM6": (
        "extents not merged on union -- survivor's x0 kept, loser's dropped",
        "                            if w[6] < v[6]:\n"
        "                                v[6] = w[6]",
        "                            if False:\n"
        "                                v[6] = w[6]",
    ),
    "MM7": (
        "extents not merged on union -- y1, which only a COLUMN sweep reaches",
        "                            if w[9] > v[9]:\n"
        "                                v[9] = w[9]",
        "                            if False:\n"
        "                                v[9] = w[9]",
    ),
    "MM8": (
        "the moment vector is not stored back after a union",
        "                        if moms_of is not None:\n"
        "                            moms_of[rn] = v",
        "                        if False:\n"
        "                            moms_of[rn] = v",
    ),
    "MM9": (
        "area accumulated at BIRTH but not on the attach path",
        "                    v[0] += rn_area",
        "                    v[0] += 0",
    ),
    "MM10": (
        "moment sums accumulated at BIRTH but not on the attach path",
        "                    v[3] += rsxx",
        "                    v[3] += 0",
    ),
    "MM11": (
        "the axis branch swapped -- a row sweep gets the column mapping",
        "                    rx0, rx1, ry0, ry1 = r.lo, r.hi, k, k",
        "                    rx0, rx1, ry0, ry1 = k, k, r.lo, r.hi",
    ),
    "MM12": (
        "the column branch reuses the row mapping for sx",
        "                    rsx = rn_area * k\n                    rsy = rs1",
        "                    rsx = rs1\n                    rsy = rs1",
    ),
    "MM13": (
        "the BIRTH vector does not carry the run's own extents",
        "                    moms_of[nid] = [rn_area, rsx, rsy, rsxx, rsyy, rsxy,\n"
        "                                    rx0, ry0, rx1, ry1]",
        "                    moms_of[nid] = [rn_area, rsx, rsy, rsxx, rsyy, rsxy,\n"
        "                                    0, 0, 0, 0]",
    ),
}


def apply_last(text: str, old: str, new: str) -> str:
    i = text.rfind(old)
    if i == -1:
        raise SystemExit(f"mutant anchor not found:\n{old}")
    # `_sweep_reference` is the oracle. Several blocks appear verbatim
    # in both it and the live sweep, so "last occurrence" is necessary
    # but not sufficient. Refuse an anchor landing inside the oracle's
    # BODY -- not merely "before `def sweep`", because M1/M11/M12
    # legitimately mutate `_UF`, which is defined earlier still.
    ref = text.find("\ndef _sweep_reference(")
    if ref != -1:
        end = text.find("\ndef ", ref + 1)
        if end == -1:
            end = len(text)
        if ref < i < end:
            raise SystemExit(
                "mutant anchor landed inside _sweep_reference -- the "
                f"oracle would be mutated:\n{old}")
    return text[:i] + new + text[i + len(old):]


def run_one(name: str) -> bool:
    """True if the mutant was KILLED (the harness failed)."""
    why, old, new = MUTANTS[name]
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        shutil.copytree(ROOT / "inkdrill", work / "inkdrill")
        shutil.copytree(ROOT / "tests", work / "tests")
        p = work / "inkdrill" / "sweep.py"
        p.write_text(apply_last(p.read_text(), old, new))
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", "tests.test_sweep_equiv", "-q"],
            cwd=work, env={"PYTHONPATH": str(work), "PATH": "/usr/bin:/bin"},
            capture_output=True, text=True)
    killed = proc.returncode != 0
    print(f"{name:4s} {'KILLED  ' if killed else 'SURVIVED'} {why}")
    return killed


def main() -> int:
    names = sys.argv[1:] or list(MUTANTS)
    results = [run_one(n) for n in names]
    killed = sum(results)
    print(f"\n{killed}/{len(results)} killed")
    return 0 if killed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
