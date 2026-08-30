"""388 — the streamed reader against the buffered one."""
import io
import subprocess
import pathlib
import pytest

from inkdrill.pnmio import (stream_masks, read_pnm_stream, CorruptPNM,
                            UnsupportedPNM, NoResolution)
from inkdrill.raster import binarize


def _pgm(width, height, fill=0):
    return b"P5\n%d %d\n255\n" % (width, height) + bytes([fill]) * (width * height)


def _mixed(width, height):
    body = bytes((x * 7 + y * 13) % 256 for y in range(height)
                 for x in range(width))
    return b"P5\n%d %d\n255\n" % (width, height) + body


def test_streamed_masks_are_byte_identical_to_buffered():
    """The whole point: a faster path that changes a measurement is not a
    faster path. Same LUT, so the threshold rule cannot drift."""
    raw = _mixed(37, 29) + _mixed(11, 5)
    whole = [binarize(i.gray, i.width, i.height, threshold=128,
                      ink_is_dark=True)
             for i in read_pnm_stream(raw, dpi=300)]
    streamed = list(stream_masks(io.BytesIO(raw), dpi=300, threshold=128))
    assert len(streamed) == len(whole) == 2
    for a, b in zip(whole, streamed):
        assert (a.width, a.height) == (b.width, b.height)
        assert a.data == b.data


@pytest.mark.parametrize("threshold", [1, 64, 128, 200, 255])
def test_identical_at_every_threshold(threshold):
    raw = _mixed(23, 17)
    a = binarize(next(iter(read_pnm_stream(raw, dpi=300))).gray, 23, 17,
                 threshold=threshold, ink_is_dark=True)
    b = next(iter(stream_masks(io.BytesIO(raw), dpi=300, threshold=threshold)))
    assert a.data == b.data


def test_a_ghostscript_comment_in_the_header_is_skipped():
    """gs writes a `# ...` comment after the magic. Read byte at a time:
    a buffered read-ahead would swallow raster bytes, and a pipe cannot
    give them back."""
    raw = b"P5\n# Created by GPL Ghostscript\n4 2\n255\n" + bytes(8)
    m = next(iter(stream_masks(io.BytesIO(raw), dpi=300, threshold=128)))
    assert (m.width, m.height) == (4, 2)


def test_a_short_raster_is_refused_not_padded():
    raw = b"P5\n4 4\n255\n" + bytes(9)          # 9 of 16
    with pytest.raises(CorruptPNM) as e:
        list(stream_masks(io.BytesIO(raw), dpi=300))
    assert "short" in str(e.value)


def test_p2_is_refused_by_name():
    """P2 is ASCII: no fixed row length, so it cannot be read a row at a
    time. Refused loudly rather than mis-read."""
    with pytest.raises(UnsupportedPNM):
        list(stream_masks(io.BytesIO(b"P2\n2 2\n255\n1 2 3 4\n"), dpi=300))


def test_dpi_is_still_required():
    with pytest.raises(NoResolution):
        list(stream_masks(io.BytesIO(_pgm(2, 2))))


def test_end_of_stream_is_not_an_error():
    assert list(stream_masks(io.BytesIO(b""), dpi=300)) == []
    assert list(stream_masks(io.BytesIO(b"\n"), dpi=300)) == []
