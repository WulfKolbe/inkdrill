"""The provenance line every report opens with (240).

    2026-08-27T10:48:12Z  commit 9559437  (+dirty)

ONE LINE, FIRST LINE, before any prose. A report arriving after a
newer one is otherwise indistinguishable from a current one, and that
happened twice in one session: a three-builds-stale figure was quoted
for three exchanges, and a peer's audit attributed a displacement to
the wrong defect because the artifact it read had been superseded.

THE COMMIT IS THE ONE THAT PRODUCED THE NUMBERS -- `HEAD` when the
report was written -- not the commit that later contains the file.
Those differ by exactly one commit and the difference matters: the
question a reader asks is "which code measured this", and the
containing commit answers "which code shipped this", which is a
different thing and one they cannot re-run.

`+dirty` when the working tree has uncommitted changes, because then
the numbers came from code that is in no commit at all and the hash
alone would overstate what is reproducible.
"""
import datetime as _dt
import pathlib as _pl
import subprocess as _sp


def stamp(when=None) -> str:
    """The line. `when` is for tests; default is now, UTC."""
    root = _pl.Path(__file__).resolve().parent.parent
    try:
        h = _sp.run(["git", "rev-parse", "--short", "HEAD"], cwd=root,
                    capture_output=True, text=True, check=True
                    ).stdout.strip()
    except Exception:
        h = "unknown"
    try:
        dirty = bool(_sp.run(["git", "status", "--porcelain"], cwd=root,
                             capture_output=True, text=True,
                             check=True).stdout.strip())
    except Exception:
        dirty = False
    t = when or _dt.datetime.now(_dt.timezone.utc)
    return (f"{t.strftime('%Y-%m-%dT%H:%M:%SZ')}  commit {h}"
            + ("  +dirty" if dirty else ""))


def prepend(path) -> str:
    """Put the line at the top of an existing report, once."""
    p = _pl.Path(path)
    body = p.read_text()
    first = body.split("\n", 1)[0]
    if first.startswith("20") and "commit " in first:
        return first                       # already stamped
    line = stamp()
    p.write_text(line + "\n" + body)
    return line


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        for a in sys.argv[1:]:
            print(f"{a}: {prepend(a)}")
    else:
        print(stamp())
