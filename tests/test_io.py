"""Unit 0 tests. Every test name is quoted verbatim in the status report."""

import struct
import unittest
import zlib

from inkdrill.io import CorruptPNG, UnsupportedPNG, _chunks, _parse_ihdr, _parse_phys

SIG = b"\x89PNG\r\n\x1a\n"


def _chunk(typ, data):
    """Assemble one PNG chunk with a correct CRC."""
    return (struct.pack(">I", len(data)) + typ + data
            + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))


def ihdr(w, h, depth=8, ctype=2, comp=0, filt=0, inter=0):
    return _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, depth, ctype, comp,
                                       filt, inter))


class T0_1_ChunkLayer(unittest.TestCase):

    def test_bad_signature_rejected(self):
        with self.assertRaises(CorruptPNG):
            list(_chunks(b"not a png at all"))

    def test_chunks_yields_type_and_payload(self):
        raw = SIG + ihdr(3, 2) + _chunk(b"IEND", b"")
        got = [(t, len(d)) for t, d in _chunks(raw)]
        self.assertEqual(got, [(b"IHDR", 13), (b"IEND", 0)])

    def test_crc_mismatch_rejected(self):
        good = SIG + ihdr(3, 2) + _chunk(b"IEND", b"")
        bad = bytearray(good)
        bad[-1] ^= 0xFF                      # corrupt the IEND CRC
        with self.assertRaises(CorruptPNG):
            list(_chunks(bytes(bad)))

    def test_truncated_chunk_rejected(self):
        raw = SIG + ihdr(3, 2)
        with self.assertRaises(CorruptPNG):
            list(_chunks(raw[:-4]))


class T0_2_HeaderValidation(unittest.TestCase):

    def test_supported_ihdr_returns_dimensions(self):
        self.assertEqual(_parse_ihdr(struct.pack(">IIBBBBB", 7, 5, 8, 2, 0, 0, 0)),
                         (7, 5))

    def test_zero_dimension_rejected(self):
        with self.assertRaises(CorruptPNG):
            _parse_ihdr(struct.pack(">IIBBBBB", 0, 5, 8, 2, 0, 0, 0))

    def test_unsupported_variants_rejected_by_name(self):
        cases = {
            "16-bit":     (16, 2, 0, 0, 0),
            "palette":    (8, 3, 0, 0, 0),
            "greyscale":  (8, 0, 0, 0, 0),
            "rgba":       (8, 6, 0, 0, 0),
            "interlaced": (8, 2, 0, 0, 1),
        }
        for label, (d, ct, cm, fm, il) in cases.items():
            with self.subTest(label):
                with self.assertRaises(UnsupportedPNG) as cm_:
                    _parse_ihdr(struct.pack(">IIBBBBB", 4, 4, d, ct, cm, fm, il))
                self.assertIn(str((d, ct, cm, fm, il)), str(cm_.exception))


class T0_3_PhysDpi(unittest.TestCase):

    def test_metre_unit_converts_to_dpi(self):
        # 11811 px/m == 300 dpi
        dpi = _parse_phys(struct.pack(">IIB", 11811, 11811, 1))
        self.assertAlmostEqual(dpi[0], 300.0, places=1)
        self.assertAlmostEqual(dpi[1], 300.0, places=1)

    def test_unit_zero_gives_none(self):
        self.assertIsNone(_parse_phys(struct.pack(">IIB", 100, 100, 0)))
