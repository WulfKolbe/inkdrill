"""Unit 9 (rasterizer half), part 1: Type 1 font programs.

Hermetic. Every font here is BUILT in memory by `build`, using the
module's own `encrypt` -- which is only sound because G5 makes encryption
the exact inverse of decryption, and `T9_1_Crypt` establishes that first.
The alternative was committing a binary .pfb fixture, which would test
this parser against one font forever; the corpus module
`test_type1_corpus.py` tests it against every font on the machine.
"""

import unittest

from inkdrill.type1 import (CHARSTRING_R, EEXEC_R, FontNotType1,
                            STANDARD_ENCODING, decrypt, encrypt, parse)

# hsbw with two arguments: `0 500 hsbw` in Type 1 number encoding, where
# a value v in -107..107 is the single byte v+139.
HSBW = bytes([139, 255, 0, 0, 1, 244, 13])
# A minimal closed path after the hsbw: rlineto, closepath, endchar.
BODY = bytes([139 + 10, 139 + 10, 5, 9, 14])
GLYPH = HSBW + BODY


def build(charstrings=None, *, subrs=(), len_iv=4, declared_len_iv=None,
          rd=b"RD", nd=b"ND",
          encoding=b"/Encoding StandardEncoding def\n",
          matrix=b"/FontMatrix [0.001 0 0 0.001 0 0] readonly def\n",
          header=b"%!PS-AdobeFont-1.0: TestFont 001.001\n",
          charstrings_section=True, cipher=None):
    """A complete Type 1 font program as (clear, encrypted-private)."""
    if charstrings is None:
        charstrings = {"A": GLYPH, "radical": GLYPH}
    clear = (header + b"/FontName /TestFont def\n" + matrix + encoding +
             b"currentdict end\ncurrentfile eexec\n")
    # `declared_len_iv` states a value in the font text that differs from
    # the one used to encrypt, which is how a font claiming something
    # impossible is built without the builder itself failing first.
    priv = (b"dup /Private 8 dict dup begin\n/lenIV %d def\n"
            % (len_iv if declared_len_iv is None else declared_len_iv))
    if subrs:
        priv += b"/Subrs %d array\n" % len(subrs)
        for i, s in enumerate(subrs):
            body = encrypt(s, CHARSTRING_R, len_iv)
            priv += b"dup %d %d %s %s NP\n" % (i, len(body), rd, body)
    if charstrings_section:
        # `cipher` supplies a body VERBATIM rather than encrypting one.
        # A trap has to live in the ciphertext to be reachable: the
        # plaintext of a charstring is encrypted before it is written,
        # so a trap written in plaintext is unreachable and the test
        # that used one passed against a parser with the guard removed.
        bodies = {n: bytes(b) for n, b in (cipher or {}).items()}
        bodies.update({n: encrypt(cs, CHARSTRING_R, len_iv)
                       for n, cs in charstrings.items()})
        priv += b"/CharStrings %d dict dup begin\n" % len(bodies)
        for name, body in bodies.items():
            priv += b"/%s %d %s %s %s\n" % (name.encode(), len(body), rd,
                                            body, nd)
        priv += b"end\nend\nmark currentfile closefile\n"
    return clear, encrypt(priv, EEXEC_R, 4)


def as_pfb(clear, enc, *, trailer=b"0" * 512 + b"\ncleartomark\n"):
    """Wrap in PFB segments, including the ASCII trailer that follows the
    binary -- the shape that catches a parser appending every ASCII
    segment to the header."""
    def seg(kind, body):
        return b"\x80" + bytes([kind]) + len(body).to_bytes(4, "little") + body
    return seg(1, clear) + seg(2, enc) + seg(1, trailer) + b"\x80\x03"


def as_pfa(clear, enc):
    """Wrap as PFA: the eexec portion hex-encoded, wrapped at 64
    columns as real PFA files are."""
    h = enc.hex().encode("ascii")
    lines = b"\n".join(h[i:i + 64] for i in range(0, len(h), 64))
    return clear + lines + b"\n" + b"0" * 512 + b"\ncleartomark\n"


class T9_1_Crypt(unittest.TestCase):
    """G5: encryption is the exact inverse of decryption."""

    def test_round_trip_recovers_the_plaintext(self):
        for plain in (b"", b"x", bytes(range(256)), b"\x00" * 100):
            for r, skip in ((EEXEC_R, 4), (CHARSTRING_R, 4),
                            (CHARSTRING_R, 0), (EEXEC_R, 1)):
                with self.subTest(n=len(plain), r=r, skip=skip):
                    self.assertEqual(
                        decrypt(encrypt(plain, r, skip, b"\xde\xad\xbe\xef"),
                                r, skip),
                        plain)

    def test_the_discarded_pad_does_not_change_the_result(self):
        a = decrypt(encrypt(b"payload", EEXEC_R, 4, b"\0\0\0\0"), EEXEC_R, 4)
        b = decrypt(encrypt(b"payload", EEXEC_R, 4, b"\xff\x01\x7f\x40"),
                    EEXEC_R, 4)
        self.assertEqual(a, b)

    def test_a_short_pad_is_refused_rather_than_silently_padded(self):
        with self.assertRaises(ValueError):
            encrypt(b"x", EEXEC_R, 4, b"\0\0")

    def test_decryption_is_not_the_identity(self):
        # Guards against an `encrypt` that returns its input, which would
        # make every round-trip assertion above pass vacuously.
        self.assertNotEqual(encrypt(b"payload", EEXEC_R, 0), b"payload")


class T9_2_Wrapper(unittest.TestCase):
    """G2: PFB and PFA of one font give identical charstrings."""

    def test_pfb_and_pfa_agree(self):
        clear, enc = build()
        a = parse(as_pfb(clear, enc))
        b = parse(as_pfa(clear, enc))
        self.assertEqual(a.charstrings, b.charstrings)
        self.assertEqual(a.charstrings["A"], GLYPH)

    def test_the_pfb_ascii_trailer_is_not_taken_for_header(self):
        """Only ASCII seen BEFORE the binary segment is the header.

        A real trailer is 512 zeros and `cleartomark`, and merging it
        into the header changes nothing -- 60 fonts sampled from the TeX
        tree parse identically either way, so this guard cannot be
        killed by real data. It is asserted here by giving the trailer
        content the header lacks, which is what the rule actually says
        and the only way to state it as a test rather than a comment.
        """
        clear, enc = build(encoding=b"")
        f = parse(as_pfb(clear, enc,
                         trailer=b"/Encoding 256 array\ndup 0 /radical put\n"
                                 + b"0" * 512 + b"\ncleartomark\n"))
        self.assertEqual(f.encoding, {})

    def test_a_truncated_pfb_segment_raises(self):
        clear, enc = build()
        raw = as_pfb(clear, enc)
        with self.assertRaises(FontNotType1):
            parse(raw[:len(raw) - 200])

    def test_a_pfb_with_no_binary_segment_raises(self):
        clear, _ = build()
        body = b"\x80\x01" + len(clear).to_bytes(4, "little") + clear + b"\x80\x03"
        with self.assertRaises(FontNotType1):
            parse(body)

    def test_a_raw_binary_eexec_font_parses(self):
        # PFA is usually hex, but an unsegmented file may hold the eexec
        # section as raw binary. The four-hex-digit test decides.
        clear, enc = build()
        self.assertEqual(parse(clear + enc).charstrings["A"], GLYPH)


class T9_3_Private(unittest.TestCase):
    """G3, G4: the read operator and lenIV come from the font."""

    def test_a_dash_bar_font_parses_like_an_RD_font(self):
        a = parse(as_pfb(*build(rd=b"RD", nd=b"ND")))
        b = parse(as_pfb(*build(rd=b"-|", nd=b"|-")))
        self.assertEqual(a.charstrings, b.charstrings)

    def test_lenIV_is_read_rather_than_assumed(self):
        for n in (0, 1, 4, 8):
            with self.subTest(len_iv=n):
                f = parse(as_pfb(*build(len_iv=n)))
                self.assertEqual(f.len_iv, n)
                self.assertEqual(f.charstrings["A"], GLYPH)

    def test_a_lenIV_0_font_keeps_its_hsbw(self):
        # The specific failure hardcoding 4 produces: every charstring
        # silently loses its first four bytes, which is its hsbw.
        f = parse(as_pfb(*build(len_iv=0)))
        self.assertEqual(f.first_ops(), {"hsbw": 2})

    def test_a_negative_lenIV_raises(self):
        with self.assertRaises(FontNotType1):
            parse(as_pfb(*build(declared_len_iv=-1)))

    def test_subrs_are_decrypted_and_indexed(self):
        subrs = [bytes([139, 139, 21, 11]), bytes([11]), bytes([139, 4, 11])]
        f = parse(as_pfb(*build(subrs=subrs)))
        self.assertEqual(f.subrs, subrs)

    def test_a_font_without_subrs_gets_an_empty_list(self):
        self.assertEqual(parse(as_pfb(*build())).subrs, [])

    def test_binary_that_looks_like_a_header_makes_no_phantom_entry(self):
        """Scanning resumes past each body, not at its start.

        The trap must be CIPHERTEXT -- an earlier version of this test
        put it in the plaintext, where encryption hides it, and passed
        against a parser with the guard removed.

        No font in 400 sampled from the TeX tree distinguishes the two,
        so this is pinning a property that real data does not currently
        exercise; that is the reason to assert it here rather than to
        assume it holds.
        """
        trap = b"xx/Z 4 RD wxyz ND\n" + bytes(8)
        f = parse(as_pfb(*build({"A": GLYPH}, cipher={"T": trap})))
        self.assertEqual(set(f.charstrings), {"A", "T"})


class T9_4_Reject(unittest.TestCase):
    """G6: a file that is not a Type 1 program raises."""

    def test_empty(self):
        with self.assertRaises(FontNotType1):
            parse(b"")

    def test_no_eexec(self):
        with self.assertRaises(FontNotType1):
            parse(b"%!PS-AdobeFont-1.0\n/FontName /X def\n")

    def test_an_opentype_file_is_refused(self):
        with self.assertRaises(FontNotType1):
            parse(b"OTTO" + bytes(200))

    def test_no_postscript_header(self):
        clear, enc = build(header=b"not postscript at all\n")
        with self.assertRaises(FontNotType1):
            parse(as_pfb(clear, enc))

    def test_no_charstrings_section(self):
        with self.assertRaises(FontNotType1):
            parse(as_pfb(*build(charstrings_section=False)))

    def test_an_empty_charstrings_section_raises_rather_than_returning(self):
        with self.assertRaises(FontNotType1):
            parse(as_pfb(*build({})))


class T9_5_Encoding(unittest.TestCase):
    """G7: code -> glyph name, with StandardEncoding recognised."""

    def test_standard_encoding_is_recognised_by_name(self):
        f = parse(as_pfb(*build()))
        self.assertEqual(f.encoding[65], "A")
        self.assertEqual(f.encoding[43], "plus")
        self.assertEqual(f.encoding, STANDARD_ENCODING)

    def test_a_builtin_encoding_array_is_read(self):
        enc = (b"/Encoding 256 array\n0 1 255 {1 index exch /.notdef put} for\n"
               b"dup 0 /radical put\ndup 112 /summation put\nreadonly def\n")
        f = parse(as_pfb(*build(encoding=enc)))
        self.assertEqual(f.encoding, {0: "radical", 112: "summation"})

    def test_a_font_with_no_encoding_gets_an_empty_map(self):
        f = parse(as_pfb(*build(encoding=b"")))
        self.assertEqual(f.encoding, {})

    def test_standard_encoding_is_not_shared_between_fonts(self):
        a = parse(as_pfb(*build()))
        a.encoding[65] = "MUTATED"
        self.assertEqual(parse(as_pfb(*build())).encoding[65], "A")


class T9_6_Matrix(unittest.TestCase):
    """The FontMatrix is read, not assumed."""

    def test_the_usual_matrix_gives_1000_units_per_em(self):
        self.assertEqual(parse(as_pfb(*build())).units_per_em, 1000.0)

    def test_a_non_standard_matrix_is_honoured(self):
        m = b"/FontMatrix [0.0005 0 0 0.0005 0 0] readonly def\n"
        self.assertEqual(parse(as_pfb(*build(matrix=m))).units_per_em, 2000.0)

    def test_a_missing_matrix_falls_back_to_the_type1_default(self):
        f = parse(as_pfb(*build(matrix=b"")))
        self.assertEqual(f.font_matrix, (0.001, 0.0, 0.0, 0.001, 0.0, 0.0))

    def test_a_malformed_matrix_falls_back_rather_than_raising(self):
        m = b"/FontMatrix [0.001 0 0] readonly def\n"
        self.assertEqual(parse(as_pfb(*build(matrix=m))).units_per_em, 1000.0)

    def test_a_zero_scale_matrix_raises_on_use(self):
        m = b"/FontMatrix [0 0 0 0.001 0 0] readonly def\n"
        f = parse(as_pfb(*build(matrix=m)))
        with self.assertRaises(FontNotType1):
            f.units_per_em


class T9_7_Oracle(unittest.TestCase):
    """first_ops is the parser's own check; it must be able to fail, and
    it must separate `callsubr` (deferred) from `cmd<n>` (wrong)."""

    def test_a_subroutinized_charstring_is_its_own_class(self):
        # Verbatim shape from Roboto-Black's `hyphen`: `10 callsubr
        # closepath endchar`, with the hsbw inside subr 10. Counting
        # this as a failure condemns 436 of that font's 1250 correct
        # glyphs; counting it as a pass asserts something unverified.
        f = parse(as_pfb(*build({"A": bytes([149, 10, 9, 14])})))
        self.assertEqual(f.first_ops(), {"callsubr": 1})

    def test_well_formed_charstrings_all_pass(self):
        self.assertEqual(parse(as_pfb(*build())).first_ops(), {"hsbw": 2})

    def test_sbw_counts_as_well_as_hsbw(self):
        sbw = bytes([139, 139, 255, 0, 0, 1, 244, 139, 12, 7]) + bytes([14])
        f = parse(as_pfb(*build({"A": sbw})))
        self.assertEqual(f.first_ops(), {"sbw": 1})

    def test_a_charstring_missing_its_hsbw_is_counted_as_a_failure(self):
        f = parse(as_pfb(*build({"A": GLYPH, "B": bytes([139, 139, 21, 14])})))
        self.assertEqual(f.first_ops(), {"hsbw": 1, "cmd21": 1})

    def test_a_charstring_of_only_numbers_does_not_count(self):
        f = parse(as_pfb(*build({"A": bytes([139, 200, 255, 0, 0, 0, 1])})))
        self.assertEqual(f.first_ops(), {"truncated": 1})

    def test_a_width_computed_with_div_still_counts(self):
        # `0 18153 53 div hsbw endchar`, verbatim from cm-super's
        # sfrm0900. div is 12 12, below 32 like a command, and every
        # charstring of that family begins this way.
        cs = bytes([139, 255, 0, 0, 70, 233, 192, 12, 12, 13, 14])
        f = parse(as_pfb(*build({"A": cs})))
        self.assertEqual(f.first_ops(), {"hsbw": 1})

    def test_div_does_not_excuse_a_missing_hsbw(self):
        cs = bytes([139, 192, 12, 12, 21, 14])       # ... div rmoveto
        f = parse(as_pfb(*build({"A": cs})))
        self.assertEqual(f.first_ops(), {"cmd21": 1})

    def test_the_five_byte_number_encoding_is_stepped_over(self):
        # 255 introduces a 32-bit integer whose bytes may themselves be
        # below 32; a decoder that steps one byte at a time reads one of
        # them as a command and reports the wrong answer here.
        cs = bytes([255, 0, 0, 0, 13, 255, 0, 0, 0, 13, 13, 14])
        f = parse(as_pfb(*build({"A": cs})))
        self.assertEqual(f.first_ops(), {"hsbw": 1})


if __name__ == "__main__":
    unittest.main()
