"""The two provenance lines every report carries (242).

    2026-08-27T08:56:07Z  /  2026-08-27 10:56:07 +02:00 (Europe/Berlin)  commit ccc61c5 +dirty
       ... the report ...
    2026-08-27T09:14:22Z  /  2026-08-27 11:14:22 +02:00 (Europe/Berlin)  end

FIRST LINE when the report STARTED, LAST LINE when it FINISHED. The
pair is the only durable record of how long a measurement took: the
harness prints "Worked for 6m 55s" and that does not survive being
pasted, so a report that took nine hours and one that took nine
seconds are otherwise indistinguishable once they are quoted.

BOTH CLOCKS, because each answers a different question. UTC orders
two reports against each other without anyone reasoning about a
changeover; local time is what the reader's terminal shows and what
they can check against their own memory of the afternoon. Carrying
one and making the reader derive the other is where the mistake gets
made.

THE OFFSET IS DERIVED, NEVER WRITTEN DOWN. `ZoneInfo("Europe/Berlin")`
gives +02:00 now and +01:00 from late October to late March. A
hard-coded +02:00 is wrong for four months of the year and wrong in
the direction that still looks plausible -- the reader sees an offset,
believes it, and is an hour out.

THE COMMIT IS THE ONE THAT PRODUCED THE NUMBERS -- `HEAD` when the
report was written -- not the commit that later contains the file.
Those differ by one, and the difference is "which code measured this"
against "which code shipped this"; only the first is re-runnable.
`+dirty` when the tree had uncommitted changes, because then the
numbers came from code in no commit at all.
"""
import datetime as _dt
import pathlib as _pl
import subprocess as _sp

try:
    from zoneinfo import ZoneInfo as _ZI
    BERLIN = _ZI("Europe/Berlin")
except Exception:                        # pragma: no cover
    BERLIN = None


def _head():
    root = _pl.Path(__file__).resolve().parent.parent
    try:
        h = _sp.run(["git", "rev-parse", "--short", "HEAD"], cwd=root,
                    capture_output=True, text=True,
                    check=True).stdout.strip()
    except Exception:
        h = "unknown"
    try:
        dirty = bool(_sp.run(["git", "status", "--porcelain"], cwd=root,
                             capture_output=True, text=True,
                             check=True).stdout.strip())
    except Exception:
        dirty = False
    return h, dirty


def _both(t) -> str:
    """`<utc>Z  /  <berlin> +HH:MM (Europe/Berlin)` for one instant."""
    if t.tzinfo is None:
        t = t.replace(tzinfo=_dt.timezone.utc)
    u = t.astimezone(_dt.timezone.utc)
    b = t.astimezone(BERLIN) if BERLIN else u
    iso = b.isoformat(timespec="seconds")
    date, rest = iso.split("T")
    # the offset begins at the LAST sign: a zone west of Greenwich
    # puts a `-` there and splitting from the left would cut the date
    cut = max(rest.rfind("+"), rest.rfind("-"))
    return (f"{u.strftime('%Y-%m-%dT%H:%M:%SZ')}  /  "
            f"{date} {rest[:cut]} {rest[cut:]} (Europe/Berlin)")


def start_line(t=None) -> str:
    h, dirty = _head()
    t = t or _dt.datetime.now(_dt.timezone.utc)
    return f"{_both(t)}  commit {h}" + (" +dirty" if dirty else "")


def end_line(t=None, note="end") -> str:
    t = t or _dt.datetime.now(_dt.timezone.utc)
    return f"{_both(t)}  {note}"


def wrap(path, started=None, note="end") -> None:
    """Put both lines around an existing report body, once."""
    p = _pl.Path(path)
    body = p.read_text()
    lines = body.split("\n")
    if lines and "  /  " in lines[0] and "commit " in lines[0]:
        return                                  # already wrapped
    p.write_text(start_line(started) + "\n" + body.rstrip("\n")
                 + "\n" + end_line(note=note) + "\n")


if __name__ == "__main__":
    print(start_line())
    print(end_line())
