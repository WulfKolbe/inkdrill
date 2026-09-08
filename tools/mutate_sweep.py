"""mutate_sweep.py -- the mutation gate for the sweep case dispatch.

Each mutant is a single textual edit applied to the LIVE `sweep` in a
throwaway copy of the package; `_sweep_reference` is never touched, so
the equivalence harness still has its oracle. A mutant that SURVIVES
means tests/test_sweep_equiv.py does not reach that line, and it is the
fixture set that needs fixing, not the mutant.

    python3 tools/mutate_sweep.py            # run every mutant
    python3 tools/mutate_sweep.py M3         # run one

Edits are applied to the last occurrence in the file, which is the live
sweep -- _sweep_reference is the earlier copy.
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
}


def apply_last(text: str, old: str, new: str) -> str:
    i = text.rfind(old)
    if i == -1:
        raise SystemExit(f"mutant anchor not found:\n{old}")
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
