"""What produced a `lines.json`, so "same bytes" is not ambiguous.

CONTRACT (A2)
=============

A consumer that re-runs inkdrill and gets identical output has two very
different situations to tell apart:

  * nothing about the page changed, and the answer is stable;
  * the code changed and the change **could not reach** this path.

Those look the same without a producer version, and the second is not
hypothetical -- `mathstruct.group()` was fixed while unreachable from
the CLI, so a downstream re-run was byte-identical and correctly so.
With a version in the file that becomes a reportable finding, "version
changed, output identical", rather than a puzzle.

The version is the GIT COMMIT when running from a checkout, because it
is the only identifier in this project that changes when the code
changes -- there is no build step, no installer and no release
numbering to hang one on. It is read from `.git` directly rather than
by running `git`: a subprocess in the emit path would be a dependency
on an external tool for a metadata field.

Outside a checkout there is nothing truthful to report, so the version
is `"unknown"`. That is deliberately not a fabricated number: a
consumer comparing two `"unknown"` values learns nothing, which is the
truth, whereas a fake constant would say "same code" and be wrong.

A LINKED WORKTREE IS NOT A SPECIAL CASE, it is the ordinary one. Two
builds compared side by side is what this field exists for, and
`git worktree add` is how that comparison gets set up. But a linked
worktree's git directory holds only its OWN refs -- `HEAD` and the
bisect/rewritten/worktree namespaces -- while branches live in the
shared directory named by its `commondir` file. So a worktree checked
out on a BRANCH has a symbolic `HEAD` pointing at a ref that is not
there, and reading only the worktree's own directory reports
`"unknown"` for a perfectly good checkout. A worktree on a detached
`HEAD` has the hash in `HEAD` itself and hides the bug. `commondir` is
followed for exactly this reason.

Guarantees
----------
G1  pure and read-only -- no subprocess, no network, no writes
G2  the value changes when HEAD changes, which is what makes it usable
    for the "changed but unreachable" question
G3  `"unknown"` outside a git checkout, never a fabricated version
G4  resolved ONCE per process and cached; emitting a document must not
    cost a file read per page
G5  a linked worktree reports what `git rev-parse HEAD` reports IN THAT
    WORKTREE, on a branch as well as detached -- which means resolving
    a ref against `commondir` when the worktree's own directory does
    not hold it, loose or packed
"""

from __future__ import annotations

import pathlib

__all__ = ["UNKNOWN", "resolve"]

UNKNOWN = "unknown"

_cached: str | None = None


def _common_dir(git_dir: pathlib.Path) -> pathlib.Path | None:
    """The shared git directory `git_dir` borrows its refs from, if any.

    Present only in a linked worktree, where it is written by
    `git worktree add` and normally holds the RELATIVE path `../..`.
    Returns `None` for an ordinary `.git` directory, which is what
    keeps the non-worktree path exactly as it was.
    """
    try:
        text = (git_dir / "commondir").read_text(
            encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if not text:
        return None
    common = pathlib.Path(text)
    if not common.is_absolute():
        common = git_dir / common
    try:
        return common.resolve()
    except OSError:
        return None


def _ref_in(git_dir: pathlib.Path, ref: str) -> str | None:
    """`ref` resolved within ONE git directory: loose file, then packed."""
    try:
        return (git_dir / ref).read_text(
            encoding="utf-8", errors="replace").strip() or None
    except OSError:
        pass
    # A packed ref, which is what a fresh clone has before the first
    # write to that branch.
    try:
        packed = (git_dir / "packed-refs").read_text(
            encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in packed.splitlines():
        if line.startswith("#") or " " not in line:
            continue
        sha, name = line.split(" ", 1)
        if name.strip() == ref:
            return sha.strip()
    return None


def _head_of(git_dir: pathlib.Path) -> str | None:
    """The commit `HEAD` names, following one symbolic ref."""
    head = git_dir / "HEAD"
    try:
        text = head.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if not text.startswith("ref:"):
        # Detached HEAD holds the hash directly.
        return text or None
    ref = text[4:].strip()
    # The worktree's own directory first -- refs/bisect and
    # refs/worktree are per-worktree and must not be answered from the
    # shared store -- then the common directory, where branches live
    # (G5). For an ordinary .git there is no second place to look.
    for d in (git_dir, _common_dir(git_dir)):
        if d is None:
            continue
        sha = _ref_in(d, ref)
        if sha:
            return sha
    return None


def resolve() -> str:
    """The producer version, cached for the process (G4).

    Short-form commit, or `UNKNOWN` outside a checkout (G3).
    """
    global _cached
    if _cached is not None:
        return _cached
    here = pathlib.Path(__file__).resolve()
    for parent in here.parents:
        git = parent / ".git"
        if git.is_dir():
            sha = _head_of(git)
            if sha:
                _cached = sha[:12]
                return _cached
            break
        if git.is_file():
            # A worktree or submodule: `.git` is a file naming the real
            # directory. Followed rather than ignored, because a
            # worktree is exactly where a comparison run happens.
            try:
                line = git.read_text(encoding="utf-8",
                                     errors="replace").strip()
            except OSError:
                break
            if line.startswith("gitdir:"):
                sha = _head_of(pathlib.Path(line[7:].strip()))
                if sha:
                    _cached = sha[:12]
                    return _cached
            break
    _cached = UNKNOWN
    return _cached
