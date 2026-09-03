"""580 stage 1 -- what survives a PDF pass, and where the channel can be written.

The question is whether a side channel attached to `report.pdf` reaches
a later reader. Two candidate carriers, and they are stripped by
different things:

  EMBEDDED FILE   a /Filespec in the catalog's /Names /EmbeddedFiles
                  name tree, with the payload in an /EmbeddedFile
                  stream. The standard attachment; `pdfdetach` reads it
                  and pdfdrill's `pdf_reading.py` already has that
                  reader.
  /PieceInfo      the PDF private-application-data dictionary, at the
                  catalog AND on each page. Designed for exactly this
                  and read by nothing that is not looking for it.

This builds ONE pdf carrying both, at both levels, with a distinctive
marker in each so a survivor can be told from a coincidence, then runs
it through every tool that could sit in a chain and reports what is
left. Pure stdlib for the writer -- the same constraint as the rest of
the package, and it keeps the fixture readable.

WHAT IT DOES NOT DO. It does not decide where the channel goes; it
reports which passes destroy which carrier. The chain's own shape --
which of these passes actually run -- is a separate question answered
by reading the chain, and the report states it beside these numbers,
because a carrier that survives every pass the chain performs is safe
whatever ghostscript does to it in general.
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import zlib

#: distinctive per carrier, so a survivor is identified not merely counted
MARK_ATTACH = b"INKDRILL-CHANNEL-ATTACHMENT-8f3a2c"
MARK_CAT = b"INKDRILL-CHANNEL-CATALOG-PIECEINFO-1d7b40"
MARK_PAGE = b"INKDRILL-CHANNEL-PAGE-PIECEINFO-6e91ca"
ATTACH_NAME = b"pdfdrill-rows.json"


def build(path: pathlib.Path, payload: bytes) -> None:
    """A one-page PDF carrying an embedded file and two /PieceInfo dicts."""
    objs: dict[int, bytes] = {}
    stream = b"BT /F1 24 Tf 72 700 Td (inkdrill 580 marker) Tj ET"
    objs[1] = (b"<< /Type /Catalog /Pages 2 0 R "
               b"/Names << /EmbeddedFiles << /Names [ ("
               + ATTACH_NAME + b") 6 0 R ] >> >> "
               b"/PieceInfo << /InkDrill << /LastModified (D:20260903000000Z) "
               b"/Private (" + MARK_CAT + b") >> >> >>")
    objs[2] = b"<< /Type /Pages /Kids [ 3 0 R ] /Count 1 >>"
    objs[3] = (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
               b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R "
               b"/PieceInfo << /InkDrill << /LastModified (D:20260903000000Z) "
               b"/Private (" + MARK_PAGE + b") >> >> >>")
    objs[4] = (b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
               + stream + b"\nendstream")
    objs[5] = (b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    objs[6] = (b"<< /Type /Filespec /F (" + ATTACH_NAME + b") /UF ("
               + ATTACH_NAME + b") /Desc (580 channel) "
               b"/EF << /F 7 0 R >> >>")
    objs[7] = (b"<< /Type /EmbeddedFile /Subtype /application#2Fjson "
               b"/Length " + str(len(payload)).encode() + b" >>\nstream\n"
               + payload + b"\nendstream")

    out = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offs = {}
    for n in sorted(objs):
        offs[n] = len(out)
        out += str(n).encode() + b" 0 obj\n" + objs[n] + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 " + str(len(objs) + 1).encode() + b"\n"
    out += b"0000000000 65535 f \n"
    for n in sorted(objs):
        out += f"{offs[n]:010d} 00000 n \n".encode()
    out += (b"trailer\n<< /Size " + str(len(objs) + 1).encode()
            + b" /Root 1 0 R >>\nstartxref\n"
            + str(xref).encode() + b"\n%%EOF\n")
    path.write_bytes(bytes(out))


def probe(path: pathlib.Path, payload: bytes) -> dict:
    """What of the three markers survives, tested STRUCTURALLY.

    THE FIRST VERSION OF THIS SCANNED BYTES and reported that
    ghostscript strips the attachment, in the same row as `pdfdetach`
    saying the file still has one. A marker inside a recompressed
    stream is present and unfindable by `in`, so a byte scan reports a
    false strip -- and it did, on three of seven passes. The scan is
    kept only as a separate `*_raw` column, never as the answer.

    The attachment is extracted with `pdfdetach -saveall` and its bytes
    compared -- which is what a consumer does, and what pdfdrill's own
    `pdf_reading.py` already calls. /PieceInfo is read out of `qpdf
    --json`'s object model, so a compressed object stream cannot hide
    it either.
    """
    import json
    import shutil
    import tempfile
    out = {"bytes": path.stat().st_size if path.is_file() else 0}
    raw = path.read_bytes() if path.is_file() else b""
    for key, mark in (("attach", MARK_ATTACH), ("cat_piece", MARK_CAT),
                      ("page_piece", MARK_PAGE)):
        out[key + "_raw"] = mark in raw

    # ATTACHMENT: extract and compare, byte for byte
    out["attach"] = False
    out["attach_note"] = ""
    d = pathlib.Path(tempfile.mkdtemp(prefix="pdfchan-"))
    try:
        subprocess.run(["pdfdetach", "-saveall", "-o", str(d), str(path)],
                       capture_output=True, timeout=120)
        got = [f for f in d.iterdir() if f.is_file()]
        if not got:
            out["attach_note"] = "no file extracted"
        else:
            b = got[0].read_bytes()
            out["attach"] = (b == payload)
            out["attach_note"] = (f"{got[0].name} {len(b)}B"
                                  + ("" if b == payload else " CONTENT DIFFERS"))
    finally:
        shutil.rmtree(d, ignore_errors=True)

    # /PieceInfo: out of qpdf's object model, not out of the bytes
    out["cat_piece"] = out["page_piece"] = False
    out["piece_note"] = ""
    try:
        r = subprocess.run(["qpdf", "--json=latest", str(path)],
                           capture_output=True, text=True, timeout=120)
        j = json.loads(r.stdout)
        objs = j.get("qpdf", [{}, {}])[1]
        blob = json.dumps(objs)
        out["cat_piece"] = MARK_CAT.decode() in blob
        out["page_piece"] = MARK_PAGE.decode() in blob
        out["piece_note"] = f"{blob.count('/PieceInfo')} PieceInfo dict(s)"
    except Exception as e:
        out["piece_note"] = f"qpdf json failed: {type(e).__name__}"
    return out


PASSES = {
    "gs pdfwrite": ["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=pdfwrite",
                    "-sOutputFile={out}", "{in}"],
    "gs pdfwrite -dPDFA": ["gs", "-q", "-dNOPAUSE", "-dBATCH",
                           "-sDEVICE=pdfwrite", "-dPDFA=2",
                           "-sOutputFile={out}", "{in}"],
    "qpdf (copy)": ["qpdf", "{in}", "{out}"],
    "qpdf --linearize": ["qpdf", "--linearize", "{in}", "{out}"],
    "qpdf --object-streams=generate": ["qpdf", "--object-streams=generate",
                                       "{in}", "{out}"],
    "mutool clean": ["mutool", "clean", "{in}", "{out}"],
    "mutool clean -gggg": ["mutool", "clean", "-gggg", "{in}", "{out}"],
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", type=pathlib.Path, required=True)
    ap.add_argument("--payload", type=int, default=400,
                    help="attachment payload size in bytes")
    args = ap.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    payload = (b'{"marker":"' + MARK_ATTACH + b'","rows":['
               + b",".join(b'{"id":%d}' % i for i in range(args.payload // 12))
               + b"]}")
    src = args.work / "marker.pdf"
    build(src, payload)

    rows = [("(no pass)", probe(src, payload), 0)]
    for name, cmd in PASSES.items():
        dst = args.work / ("out_" + name.replace(" ", "_")
                           .replace("/", "_") + ".pdf")
        real = [c.replace("{in}", str(src)).replace("{out}", str(dst))
                for c in cmd]
        r = subprocess.run(real, capture_output=True, text=True, timeout=300)
        if not dst.is_file():
            rows.append((name, {"error": (r.stderr or r.stdout
                                          or f"rc={r.returncode}")[:60]}, 1))
            continue
        rows.append((name, probe(dst, payload), r.returncode))

    print(f"{'pass':<32} {'attach':>7} {'cat/PI':>7} {'page/PI':>8} "
          f"{'bytes':>8}   how it was read")
    for name, p, _rc in rows:
        if "error" in p:
            print(f"{name:<32} FAILED: {p['error']}")
            continue
        def m(k):
            return "KEPT" if p[k] else "gone"
        print(f"{name:<32} {m('attach'):>7} {m('cat_piece'):>7} "
              f"{m('page_piece'):>8} {p['bytes']:>8}   "
              f"{p['attach_note']}; {p['piece_note']}")
    print("\nRAW BYTE SCAN, which is NOT the answer -- shown only so the")
    print("gap against the structural columns above is visible:")
    for name, p, _ in rows:
        if "error" in p:
            continue
        print(f"   {name:<32} attach {str(p['attach_raw']):<5} "
              f"cat {str(p['cat_piece_raw']):<5} page {p['page_piece_raw']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
