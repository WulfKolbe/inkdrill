"""P18: the one gate every corpus harness runs before it starts.

A harness that sweeps 3,232 documents because it was invoked with no
arguments is a footgun, and this session fired it twice. The gate:

* **`--limit` is required.** Running without it is refused, with the
  flag and the smallest useful sample named in the message. There is
  no implicit corpus default; `--limit all` is the explicit opt-in.
* **The plan is printed before any work** -- how many documents and
  how many pages are about to be processed.
* **Above a stated threshold the run must be confirmed**: more than
  `CONFIRM_DOCS` documents or `CONFIRM_PAGES` pages needs `--yes`, or
  a typed `y` when stdin is a terminal. A non-interactive run is
  REFUSED rather than prompted, because a harness that blocks on a
  prompt in the background reads as a hang.

Page counting is honest about its own cost: exact for a selection up
to `EXACT_PAGES_UPTO` documents, and a labelled estimate from a
`ESTIMATE_SAMPLE`-document sample above that. An estimate is always
printed as `~N`, never as a bare number.
"""

from __future__ import annotations

import sys

DEFAULT_SAMPLE = 3          # the smallest useful sample
CONFIRM_DOCS = 25
CONFIRM_PAGES = 5000
EXACT_PAGES_UPTO = 100
ESTIMATE_SAMPLE = 20


class Refused(SystemExit):
    """Refusal is an exit, not an exception a caller can swallow."""


def add_arguments(ap):
    """Attach the gate's flags to an argparse parser."""
    ap.add_argument("--limit", default=None,
                    help=f"documents to process: an integer, or 'all' "
                         f"for the whole corpus (required; the "
                         f"smallest useful sample is {DEFAULT_SAMPLE})")
    ap.add_argument("--yes", action="store_true",
                    help="confirm a run above the size threshold "
                         "(required when stdin is not a terminal)")
    return ap


def select(items, limit):
    """The documents this run will touch, or refuse."""
    if limit is None:
        raise Refused(
            f"--limit is required: pass --limit {DEFAULT_SAMPLE} for the "
            f"smallest useful sample, --limit N for N documents, or "
            f"--limit all for the whole corpus ({len(items)} documents). "
            f"There is no corpus default -- a sweep is opted into, "
            f"never fallen into.")
    if str(limit).lower() == "all":
        return list(items)
    try:
        n = int(limit)
    except (TypeError, ValueError):
        raise Refused(f"--limit takes an integer or 'all', not {limit!r}")
    if n < 1:
        raise Refused(f"--limit must be >= 1, got {n}")
    return list(items)[:n]


def page_plan(chosen, count_pages):
    """(pages, exact) for the chosen documents.

    `count_pages` maps one item to its page count. Counting every
    document of a large selection costs more than the plan is worth,
    so above `EXACT_PAGES_UPTO` the total is extrapolated from a
    sample and flagged as inexact.
    """
    if count_pages is None or not chosen:
        return None, True
    if len(chosen) <= EXACT_PAGES_UPTO:
        return sum(count_pages(i) for i in chosen), True
    step = max(1, len(chosen) // ESTIMATE_SAMPLE)
    sample = chosen[::step][:ESTIMATE_SAMPLE]
    per = sum(count_pages(i) for i in sample) / len(sample)
    return int(round(per * len(chosen))), False


def plan_line(name, chosen, total, pages, exact):
    p = ("" if pages is None else
         f", {'' if exact else '~'}{pages} pages"
         f"{'' if exact else ' (estimated)'}")
    return (f"{name}: {len(chosen)} of {total} documents{p} "
            f"-- threshold is {CONFIRM_DOCS} documents / "
            f"{CONFIRM_PAGES} pages")


def gate(name, items, limit, yes, count_pages=None, stream=sys.stderr,
         ask=None, interactive=None):
    """Select, print the plan, confirm if large. Returns the items.

    `ask` and `interactive` exist so the confirmation path is
    testable without a terminal; production passes neither.
    """
    total = len(items)
    chosen = select(items, limit)
    pages, exact = page_plan(chosen, count_pages)
    print(plan_line(name, chosen, total, pages, exact), file=stream)
    big = len(chosen) > CONFIRM_DOCS or (pages or 0) > CONFIRM_PAGES
    if not big or yes:
        return chosen
    if interactive is None:
        interactive = sys.stdin.isatty()
    if not interactive:
        raise Refused(
            f"{name}: this run is above the threshold and stdin is not a "
            f"terminal -- re-run with --yes to confirm "
            f"{len(chosen)} documents.")
    answer = (ask or input)(f"{name}: proceed with {len(chosen)} "
                            f"documents? [y/N] ")
    if str(answer).strip().lower() not in ("y", "yes"):
        raise Refused(f"{name}: not confirmed, nothing was processed.")
    return chosen
