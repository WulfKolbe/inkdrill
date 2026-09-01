#!/usr/bin/env python3
"""453 — is a 449 near-pair genuinely similar, or only the same rectangle?

449 matched on geometry and said so: similar aspect and size is a reason to
look, not a finding. This measures the INK on both crops — the five-tuple
inkdrill uses everywhere else — and reports the L1 difference.

Two crops close in ink and far apart in classification is the finding. Two
crops distant in ink means the rectangle matched and the content did not, and
the pair proves nothing.

Expiry is per pdf_id (401), and several of these documents are unpublished, so
a dead crop is reported as dead rather than counted as a zero.
"""
import argparse, json, pathlib, subprocess, sys, tempfile, urllib.error, urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from inkdrill.pngio import read_png, auto_mask                 # noqa: E402
from inkdrill.mathstruct import pair_stats                     # noqa: E402

KEYS = ("components", "holes", "stacked", "centred", "offset")


def fetch(url, dst):
    """(status, path|None). A dead crop is a status, never an exception."""
    if not url:
        return "no url", None
    try:
        with urllib.request.urlopen(url.replace("\\&", "&"), timeout=30) as r:
            b = r.read()
            dst.write_bytes(b)
            return r.status, dst
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:                       # noqa: BLE001
        return type(e).__name__, None


def five(jpg, work, tag):
    png = work / ("%s.png" % tag)
    subprocess.run(["magick", str(jpg), "-background", "white",
                    "-alpha", "remove", "-alpha", "off", "PNG24:" + str(png)],
                   capture_output=True)
    if not png.is_file():
        return None
    img = read_png(png)
    m, _ = auto_mask(img.gray, img.width, img.height, 200)
    d = pair_stats(m)
    return [d[k] for k in KEYS]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default="/tmp/claude-1000/-home-wkolbe-MX-PDFDRILL/"
                                       "ae99387a-8fcf-4b96-b9d9-5dc00cc6f8da/"
                                       "scratchpad/449_final.json")
    ap.add_argument("--out", default=str(pathlib.Path.home() /
                                         "inkdrill" / "out" / "453.json"))
    a = ap.parse_args()
    pairs = json.loads(pathlib.Path(a.pairs).read_text())
    w = pathlib.Path(tempfile.mkdtemp(prefix="pairink453-"))
    out = []
    for i, p in enumerate(pairs, 1):
        rec = {"n": i, "doc": p["doc"],
               "math_page": p["eq"]["page"], "gfx_page": p["gfx"]["page"],
               "conf": p["eq"]["conf"]}
        sm, fm = fetch(p["eq"]["cdn"], w / ("%02d_m.jpg" % i))
        sg, fg = fetch(p["gfx"]["cdn"], w / ("%02d_g.jpg" % i))
        rec["math_http"], rec["gfx_http"] = sm, sg
        lm = five(fm, w, "%02d_m" % i) if fm else None
        lg = five(fg, w, "%02d_g" % i) if fg else None
        rec["math_five"], rec["gfx_five"] = lm, lg
        if lm and lg:
            rec["distance"] = sum(abs(x - y) for x, y in zip(lm, lg))
            rec["comp_delta"] = abs(lm[0] - lg[0])
        out.append(rec)
        print("  %2d %-34s math %-5s gfx %-5s  %s"
              % (i, p["doc"][:34], sm, sg,
                 ("d=%-5d  %s vs %s" % (rec["distance"], lm, lg))
                 if lm and lg else "NOT MEASURABLE"), flush=True)
        pathlib.Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(a.out).write_text(json.dumps(out, indent=1))
    print("wrote %s" % a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
