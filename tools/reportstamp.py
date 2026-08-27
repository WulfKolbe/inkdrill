"""The provenance line every report opens with (240).

    2026-08-27 10:56:07 +02:00  commit ccc61c5 +dirty

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

LOCAL TIME WITH THE OFFSET SHOWN, not UTC. The reader works in
Europe/Berlin and a report timed 08:56Z next to a terminal showing
10:56 costs a mental subtraction every time. The offset is what keeps
that unambiguous, and it is DERIVED FROM THE SYSTEM ZONE via
`astimezone()` -- never written as a constant, because Berlin is
+01:00 from late October to late March and +02:00 the rest of the
year. A hard-coded `+02:00` would be wrong for four months and wrong
in the direction that still looks plausible.
"""
import datetime as _dt
import pathlib as _pl
import subprocess as _sp


def stamp(when=None) -> str:
    """The line. `when` is for tests; default is now, local."""
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
    t = when or _dt.datetime.now().astimezone()
    if t.tzinfo is None:                   # a naive `when` is local
        t = t.astimezone()
    # isoformat carries the offset as +HH:MM; strftime's %z gives
    # +HHMM and %:z is 3.12+, and this package targets 3.7 syntax.
    iso = t.isoformat(timespec="seconds")
    date, rest = iso.split("T")
    # split the offset off the clock time: it begins at the last sign,
    # and it can be negative, so scanning from the right is what makes
    # this work for a zone west of Greenwich as well as east of it.
    cut = max(rest.rfind("+"), rest.rfind("-"))
    clock, offset = rest[:cut], rest[cut:]
    return (f"{date} {clock} {offset}  commit {h}"
            + (" +dirty" if dirty else ""))


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
