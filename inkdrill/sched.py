"""sched.py — the task graph and priority queue.

CONTRACT (written before implementation; see docs/units.md U8)
=============================================================

What the plan said, and what the measurement said back
------------------------------------------------------
The plan specified tasks `(page, axis, band)` with priority
`(page_index, band_index)`, a large band count for page 1 so it
"saturates all cores", and `multiprocessing.shared_memory` for the mask.

Measured before this unit was written (docs/units.md §3, "U8 premise
check"), on real corpus pages:

  * **decode is 85-95% of per-page work; the sweep is 5-15%.** Band
    parallelism only touches the sweep, so its Amdahl ceiling on the
    target workload is **1.17x** even if the sweep were free.
  * page-parallel work reaches 3.26x on 16 cores, and is capped near
    4.2x by the single slowest page in a sample -- not by core count.
  * per-page cost spread is **185x** (0.18 s to 34.17 s), so any
    scheduler that treats pages as equal-cost units will idle.

So the band tier is NOT built. The task key is `(page, axis)`. This is
the U7 stitch finding taken to its conclusion: banding buys at most
1.7-3x of a slice that is itself 5-15% of the work.

What this unit therefore is
---------------------------
A deterministic priority scheduler over independent tasks. It does not
know what a page is. It takes a job callable and a list of `Task`s whose
keys define both dispatch priority and result order, and it guarantees
the answer does not depend on how many workers ran it or in what order
they finished.

That determinism is the whole point. `units.md` requires "results ordered
by `(page, first_line, node)` not by completion", and the U7 audit showed
what happens when order is assumed rather than enforced -- a stitcher
that passed every in-order test and would have failed in production.

Serial is not a special case of parallel
----------------------------------------
`workers=1` runs in this process with no pool, no pickling and no fork.
That is not an optimisation: it is what makes the unit testable and
debuggable, and it is the reference the parallel paths are checked
against (G1). A scheduler whose serial path went through a pool would
have no oracle.

Utilisation is measured, not assumed
------------------------------------
`RunReport` carries the wall time, the summed worker-busy time and the
resulting utilisation, because docs/units.md assumption 6 asks for
exactly that and the idle tail was measured at 33-62% rather than the
assumed near-100%. A scheduler that cannot report its own utilisation
cannot be improved.

Guarantees
----------
G1  the result is IDENTICAL for every worker count, including 1, and 1
    uses no processes at all
G2  results are ordered by task key, never by completion order
G3  tasks are dispatched in ascending key order, so the lowest-priority
    number starts first and first-page latency is not left to chance
G4  every task runs exactly once: none dropped, none duplicated
G5  a job that raises surfaces the exception rather than silently
    yielding a short result list
G6  `RunReport` reports measured wall time, busy time and utilisation
G7  duplicate keys are refused, because they would make G2's ordering
    ambiguous

Non-guarantees (out of scope for U8)
------------------------------------
  * no shared memory. The premise check measured serialization at
    0.08-0.21 MB per page of components against a 2.7-3.7 MB mask, so it
    is not the constraint; adding shared memory would be optimising a
    cost that was measured and found small.
  * no band tier -- see above; it is a measured decision, not an omission
  * no work stealing. With a 185x per-task cost spread the useful fix is
    finer-grained tasks, not redistribution of coarse ones, and that is
    a scheduling policy the caller chooses by how it builds `Task`s.
"""

from __future__ import annotations

import multiprocessing as mp
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

__all__ = ["Task", "Result", "RunReport", "run", "InvalidWorkerCount",
           "DuplicateTaskKey", "TaskFailed"]


class InvalidWorkerCount(ValueError):
    """workers must be at least 1."""


class DuplicateTaskKey(ValueError):
    """two tasks share a key, so the result order would be ambiguous."""


class TaskFailed(RuntimeError):
    """a job raised; the key and the original exception are attached."""

    def __init__(self, key: tuple, original: BaseException) -> None:
        super().__init__(f"task {key!r} failed: {original!r}")
        self.key = key
        self.original = original


@dataclass(frozen=True, slots=True)
class Task:
    """One unit of work.

    `key` is both the dispatch priority and the result order -- one field
    for both, so they cannot drift apart. For the page pipeline it is
    `(page_index, axis)`.
    """
    key: tuple
    payload: Any


@dataclass(frozen=True, slots=True)
class Result:
    key: tuple
    value: Any
    seconds: float


@dataclass(slots=True)
class RunReport:
    """What actually happened, measured (G6)."""
    results: list[Result] = field(default_factory=list)
    workers: int = 1
    wall_seconds: float = 0.0
    busy_seconds: float = 0.0

    @property
    def utilisation(self) -> float:
        """Summed worker-busy time over wall time times workers.

        1.0 means every worker was busy for the whole run. The idle tail
        shows up here as a number well below 1.0, which is the point.
        """
        denom = self.wall_seconds * self.workers
        return self.busy_seconds / denom if denom > 0 else 0.0

    @property
    def speedup(self) -> float:
        """Against the summed work, i.e. what one worker would have
        taken. Bounded above by `workers`, and by the longest single
        task -- which on real pages is the binding constraint."""
        return self.busy_seconds / self.wall_seconds if self.wall_seconds else 0.0

    @property
    def longest_task(self) -> float:
        return max((r.seconds for r in self.results), default=0.0)

    @property
    def amdahl_ceiling(self) -> float:
        """The best any scheduler could do with these tasks: the total
        work divided by the longest single task, which cannot be split.
        Measured at ~4.2x on a real 16-page sample."""
        longest = self.longest_task
        return self.busy_seconds / longest if longest > 0 else 0.0

    def values(self) -> list[Any]:
        return [r.value for r in self.results]


# Module level so the pool can pickle it.
_JOB: Callable[[Any], Any] | None = None


def _init(job: Callable[[Any], Any]) -> None:
    global _JOB
    _JOB = job


def _call(item: tuple[tuple, Any]) -> tuple[tuple, Any, float, Any]:
    key, payload = item
    t = time.perf_counter()
    try:
        value = _JOB(payload)          # type: ignore[misc]
    except BaseException as exc:       # noqa: BLE001 -- re-raised by run()
        return (key, None, time.perf_counter() - t, exc)
    return (key, value, time.perf_counter() - t, None)


def run(tasks: Iterable[Task], job: Callable[[Any], Any], *,
        workers: int = 1) -> RunReport:
    """Run every task and return results in KEY order.

    `workers=1` runs here, in this process, with no pool (G1). Higher
    counts use a process pool, and the answer is the same either way --
    that equality is what the tests check, and it is why the serial path
    exists.
    """
    if workers < 1:
        raise InvalidWorkerCount(f"workers={workers}, must be >= 1")

    ordered = sorted(tasks, key=lambda t: t.key)      # G3
    keys = [t.key for t in ordered]
    if len(set(keys)) != len(keys):
        seen: set = set()
        for k in keys:
            if k in seen:
                raise DuplicateTaskKey(f"duplicate task key {k!r}")
            seen.add(k)

    report = RunReport(workers=workers)
    if not ordered:
        return report

    items = [(t.key, t.payload) for t in ordered]
    t0 = time.perf_counter()
    if workers == 1:
        _init(job)
        raw = [_call(it) for it in items]
    else:
        with mp.Pool(workers, initializer=_init, initargs=(job,)) as pool:
            raw = list(pool.imap_unordered(_call, items))
    report.wall_seconds = time.perf_counter() - t0

    for key, _value, _secs, exc in raw:
        if exc is not None:
            raise TaskFailed(key, exc)                # G5

    if len(raw) != len(items):                        # G4
        raise RuntimeError(
            f"scheduler lost work: {len(raw)} results for "
            f"{len(items)} tasks")

    raw.sort(key=lambda r: r[0])                      # G2
    report.results = [Result(k, v, s) for k, v, s, _ in raw]
    report.busy_seconds = sum(r.seconds for r in report.results)
    return report


def page_tasks(pages: Sequence[Any], axes: Sequence[str] = ("row",)) -> list[Task]:
    """Build `(page_index, axis)` tasks.

    The key is `(page_index, axis)` and NOT `(page, axis, band)`: the
    band tier was measured into the ground before this unit was written.
    Low page index first, so page 1 completes first.
    """
    return [Task((i, ax), p)
            for i, p in enumerate(pages)
            for ax in axes]
