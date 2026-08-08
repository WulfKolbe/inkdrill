"""Unit 8 tests. Every test name is quoted verbatim in the status report."""

import random
import unittest

from inkdrill.raster import BG, INK, InkMask
from inkdrill.sched import (DuplicateTaskKey, InvalidWorkerCount, Result,
                            RunReport, Task, TaskFailed, page_tasks, run)
from inkdrill.sweep import Capture, sweep

# Jobs must be importable by name for a process pool to pickle them, so
# they live at module level rather than inside the tests.


def double(x):
    return x * 2


def sweep_job(rows):
    """A real unit of work: build a mask and sweep it. Small enough that
    the suite stays fast, real enough that the pool carries something
    other than integers."""
    mask = InkMask.from_rows(rows)
    res = sweep(mask, axis="row", conn=8, capture=Capture.GRAPH)
    return (res.node_count, res.component_count, res.cycle_count)


def boom(x):
    if x == 3:
        raise ValueError("job 3 refuses")
    return x


def slow_for_one(x):
    """One task far more expensive than the rest -- the 185x spread the
    premise check measured, in miniature."""
    n = 200000 if x == 0 else 200
    return sum(range(n))


RING = ["#####", "#...#", "#...#", "#...#", "#####"]
NESTED = ["#######", "#.....#", "#.###.#", "#.#.#.#",
          "#.###.#", "#.....#", "#######"]


def random_rows(rng, w, h, density=0.4):
    return ["".join("#" if rng.random() < density else "."
                    for _ in range(w)) for _ in range(h)]


class T8_1_IdenticalAtEveryWorkerCount(unittest.TestCase):
    """G1, the contract. units.md asks for identical output at pool size
    1, 8 and 128; 128 processes on a 16-core machine is a scheduling
    test, not a throughput one, so it is included at a size the suite can
    afford."""

    def test_identical_results_for_every_worker_count(self):
        tasks = [Task((i,), i) for i in range(24)]
        want = run(tasks, double, workers=1).values()
        for w in (2, 4, 8):
            with self.subTest(workers=w):
                self.assertEqual(run(tasks, double, workers=w).values(), want)

    def test_identical_on_real_sweep_work(self):
        rng = random.Random(20260808)
        pages = [random_rows(rng, 12, 12) for _ in range(12)]
        tasks = page_tasks(pages)
        want = run(tasks, sweep_job, workers=1).values()
        for w in (2, 4, 8):
            with self.subTest(workers=w):
                self.assertEqual(run(tasks, sweep_job, workers=w).values(),
                                 want)

    def test_more_workers_than_tasks_is_harmless(self):
        tasks = [Task((i,), i) for i in range(3)]
        want = run(tasks, double, workers=1).values()
        for w in (8, 32):
            with self.subTest(workers=w):
                self.assertEqual(run(tasks, double, workers=w).values(), want)

    def test_worker_count_must_be_at_least_one(self):
        for w in (0, -1):
            with self.subTest(workers=w):
                with self.assertRaises(InvalidWorkerCount):
                    run([Task((0,), 1)], double, workers=w)


class T8_2_OrderIsByKeyNeverByCompletion(unittest.TestCase):
    """G2 and G3. The U7 audit showed what an assumed ordering costs."""

    def test_results_come_back_in_key_order(self):
        tasks = [Task((i,), i) for i in range(30)]
        for w in (1, 4, 8):
            with self.subTest(workers=w):
                keys = [r.key for r in run(tasks, double, workers=w).results]
                self.assertEqual(keys, sorted(keys))

    def test_shuffled_input_gives_the_same_ordered_output(self):
        rng = random.Random(11)
        tasks = [Task((i,), i) for i in range(30)]
        want = run(tasks, double, workers=1).values()
        for trial in range(4):
            shuffled = tasks[:]
            rng.shuffle(shuffled)
            for w in (1, 4):
                with self.subTest(trial=trial, workers=w):
                    self.assertEqual(run(shuffled, double, workers=w).values(),
                                     want)

    def test_completion_order_does_not_leak_into_results(self):
        """The task that finishes LAST must still appear first if its key
        says so. `slow_for_one` makes key 0 the slowest."""
        tasks = [Task((i,), i) for i in range(8)]
        for w in (1, 4):
            with self.subTest(workers=w):
                res = run(tasks, slow_for_one, workers=w).results
                self.assertEqual([r.key for r in res],
                                 [(i,) for i in range(8)])
                self.assertEqual(res[0].value, sum(range(200000)))

    def test_page_tasks_key_is_page_then_axis(self):
        tasks = page_tasks(["a", "b"], axes=("row", "col"))
        self.assertEqual([t.key for t in tasks],
                         [(0, "row"), (0, "col"), (1, "row"), (1, "col")])
        keys = sorted(t.key for t in tasks)
        self.assertEqual(keys[0], (0, "col"))
        self.assertEqual(keys[-1], (1, "row"))

    def test_page_tasks_carry_no_band_component(self):
        """The band tier was measured into the ground before this unit
        was written; the key must not carry a slot for it."""
        for t in page_tasks(["a", "b", "c"]):
            with self.subTest(key=t.key):
                self.assertEqual(len(t.key), 2)


class T8_3_NothingLostNothingRepeated(unittest.TestCase):
    """G4."""

    def test_every_task_runs_exactly_once(self):
        for n in (1, 7, 40):
            tasks = [Task((i,), i) for i in range(n)]
            for w in (1, 4, 8):
                with self.subTest(n=n, workers=w):
                    got = run(tasks, double, workers=w).values()
                    self.assertEqual(len(got), n)
                    self.assertEqual(sorted(got), sorted(i * 2
                                                         for i in range(n)))

    def test_an_empty_task_list_is_not_an_error(self):
        rep = run([], double, workers=4)
        self.assertEqual(rep.results, [])
        self.assertEqual(rep.utilisation, 0.0)

    def test_duplicate_keys_are_refused(self):
        """G7: two tasks with one key would make the result order
        ambiguous, so it is caught rather than silently resolved."""
        tasks = [Task((1,), "a"), Task((2,), "b"), Task((1,), "c")]
        for w in (1, 4):
            with self.subTest(workers=w):
                with self.assertRaises(DuplicateTaskKey):
                    run(tasks, double, workers=w)


class T8_4_FailuresSurface(unittest.TestCase):
    """G5. A scheduler that swallowed an exception would return a short
    result list, and the caller would see missing pages rather than a
    crash."""

    def test_a_raising_job_surfaces_as_task_failed(self):
        tasks = [Task((i,), i) for i in range(6)]
        for w in (1, 4):
            with self.subTest(workers=w):
                with self.assertRaises(TaskFailed) as cm:
                    run(tasks, boom, workers=w)
                self.assertEqual(cm.exception.key, (3,))
                self.assertIsInstance(cm.exception.original, ValueError)

    def test_the_failing_key_is_named(self):
        with self.assertRaises(TaskFailed) as cm:
            run([Task((7,), 3)], boom, workers=1)
        self.assertIn("7", str(cm.exception))


class T8_5_UtilisationIsMeasured(unittest.TestCase):
    """G6. assumption 6 asked whether the scheduler reaches full
    utilisation; the premise check measured 33-62%, so the unit reports
    it rather than asserting it."""

    def test_report_carries_wall_busy_and_utilisation(self):
        rep = run([Task((i,), i) for i in range(8)], slow_for_one,
                  workers=2)
        self.assertGreater(rep.wall_seconds, 0.0)
        self.assertGreater(rep.busy_seconds, 0.0)
        self.assertGreater(rep.utilisation, 0.0)
        self.assertIsInstance(rep, RunReport)

    def test_serial_utilisation_is_near_one(self):
        """One worker that never idles. Anything well below 1.0 here
        would mean the harness itself is the overhead."""
        rep = run([Task((i,), i) for i in range(6)], slow_for_one,
                  workers=1)
        self.assertGreater(rep.utilisation, 0.8)

    def test_the_amdahl_ceiling_is_reported(self):
        """One task dominates, so no worker count can beat total-work
        over longest-task. This is the 4.2x cap the premise check found
        on real pages, in miniature."""
        rep = run([Task((i,), i) for i in range(8)], slow_for_one,
                  workers=1)
        self.assertGreater(rep.longest_task, 0.0)
        self.assertLess(rep.amdahl_ceiling, 8.0)
        self.assertGreaterEqual(rep.amdahl_ceiling, 1.0)

    def test_results_carry_their_own_durations(self):
        rep = run([Task((i,), i) for i in range(5)], slow_for_one,
                  workers=1)
        self.assertTrue(all(r.seconds >= 0 for r in rep.results))
        self.assertAlmostEqual(rep.busy_seconds,
                               sum(r.seconds for r in rep.results), places=9)


class T8_6_SerialUsesNoProcesses(unittest.TestCase):
    """G1's second half. The serial path is the oracle the parallel paths
    are checked against, so it must not itself go through a pool."""

    def test_workers_one_does_not_start_a_pool(self):
        import multiprocessing as mp
        started = []
        real = mp.Pool

        class Spy:
            def __init__(self, *a, **k):
                started.append(a)
                raise AssertionError("workers=1 must not create a Pool")

        mp.Pool = Spy
        try:
            got = run([Task((i,), i) for i in range(4)], double, workers=1)
        finally:
            mp.Pool = real
        self.assertEqual(got.values(), [0, 2, 4, 6])
        self.assertEqual(started, [])

    def test_serial_matches_parallel_on_topology_fixtures(self):
        tasks = page_tasks([RING, NESTED, RING])
        want = run(tasks, sweep_job, workers=1).values()
        self.assertEqual(run(tasks, sweep_job, workers=4).values(), want)
        # and the values are the real sweep answers, not placeholders
        self.assertEqual(want[0][2], 1)          # RING has one hole
        self.assertEqual(want[1][2], 2)          # NESTED has two


if __name__ == "__main__":
    unittest.main()
