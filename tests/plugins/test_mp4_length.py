"""The length of a fragmented MP4 file from its boxes, and the malformed files that have none."""

import io
import struct
from typing import override

import pytest
from hypothesis import given
from hypothesis import strategies as st

from medleyplay.plugins.mp4_length import MAX_BOXES, read_fragmented_length
from tests.support.mp4 import (
    FTYP,
    Mp4,
    box,
    box_header,
    full_box,
    large_box,
    mp4_bytes,
    mvhd,
    sidx,
)


def _length(data: bytes) -> float | None:
    return read_fragmented_length(io.BytesIO(data))


@pytest.mark.parametrize("version", [0, 1])
def test_a_fragmented_file_is_as_long_as_its_mehd_fragment_duration(version: int) -> None:
    data = mp4_bytes(Mp4(fragment_seconds=3.5, mehd_version=version))

    assert _length(data) == 3.5


@pytest.mark.parametrize("mvhd_version", [0, 1])
def test_the_mehd_fragment_duration_counts_in_the_mvhd_timescale(mvhd_version: int) -> None:
    mehd = full_box(b"mehd", 0, struct.pack(">I", 88_200))
    moov = box(b"moov", mvhd(0, timescale=44_100, version=mvhd_version) + box(b"mvex", mehd))
    data = FTYP + moov

    assert _length(data) == 2.0


def test_a_fragmented_file_without_mehd_is_as_long_as_its_sidx_subsegments() -> None:
    data = mp4_bytes(Mp4(segment_seconds=(1.5, 2.25)))

    assert _length(data) == 3.75


def test_every_top_level_sidx_adds_its_subsegments_over_its_own_timescale() -> None:
    data = FTYP + sidx([3_000], timescale=1_000) + sidx([88_200], timescale=44_100, version=1)

    assert _length(data) == 5.0


def test_a_sidx_reference_to_another_sidx_is_not_counted_twice() -> None:
    data = FTYP + sidx([], to_index=2) + sidx([1_000]) + sidx([2_000])

    assert _length(data) == 3.0


def test_mehd_takes_precedence_over_sidx() -> None:
    data = mp4_bytes(Mp4(fragment_seconds=3, segment_seconds=(9,)))

    assert _length(data) == 3.0


def test_mehd_without_an_mvhd_timescale_gives_way_to_sidx() -> None:
    mehd = full_box(b"mehd", 0, struct.pack(">I", 5_000))
    moov = box(b"moov", mvhd(0, timescale=0) + box(b"mvex", mehd))

    assert _length(FTYP + moov + sidx([2_000])) == 2.0


def test_a_fragmented_file_with_neither_mehd_nor_sidx_has_no_length() -> None:
    data = mp4_bytes(Mp4())

    assert _length(data) is None


def test_a_large_size_box_is_stepped_over_like_any_other() -> None:
    data = FTYP + large_box(b"free", bytes(10)) + sidx([2_000])

    assert _length(data) == 2.0


def test_a_box_of_size_zero_runs_to_the_end_of_the_file() -> None:
    data = FTYP + sidx([2_000]) + box_header(0, b"mdat") + bytes(100)

    assert _length(data) == 2.0


def test_a_sidx_after_a_box_of_size_zero_is_inside_that_box_and_not_read() -> None:
    data = FTYP + box_header(0, b"mdat") + sidx([2_000])

    assert _length(data) is None


def test_a_file_with_as_many_boxes_as_the_bound_is_read() -> None:
    data = FTYP + sidx([1_000]) + box(b"free", b"") * (MAX_BOXES - 2)

    assert _length(data) == 1.0


def test_a_file_with_more_boxes_than_the_bound_has_no_length() -> None:
    data = FTYP + sidx([1_000]) + box(b"free", b"") * (MAX_BOXES - 1)

    assert _length(data) is None


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(b"", id="an empty file"),
        pytest.param(b"not an mp4 file at all", id="text"),
        # Stepping 4 bytes would read the next header from inside this one, as a
        # valid 8-byte box of type "free".
        pytest.param(
            FTYP + box_header(4, b"\x00\x00\x00\x08") + b"free" + sidx([1_000]),
            id="smaller than a header",
        ),
        pytest.param(
            FTYP + sidx([1_000]) + box_header(100, b"mdat") + bytes(10), id="past the end"
        ),
        pytest.param(FTYP + sidx([1_000]) + b"\x00\x00\x00", id="a header cut short"),
        pytest.param(
            FTYP + sidx([1_000]) + struct.pack(">I4sQ", 1, b"mdat", 2**63),
            id="largesize past the end",
        ),
        pytest.param(
            FTYP + struct.pack(">I4sQ", 1, b"free", 8) + sidx([1_000]),
            id="largesize smaller than its header",
        ),
        pytest.param(FTYP + sidx([1_000], timescale=0), id="a sidx timescale of 0"),
        pytest.param(
            FTYP + sidx([1_000])[:-4], id="a sidx holding fewer references than it counts"
        ),
        pytest.param(
            FTYP
            + box(b"moov", mvhd(0) + box(b"mvex", full_box(b"mehd", 0, b"\x00\x01")))
            + sidx([1_000]),
            id="a mehd shorter than its duration",
        ),
        pytest.param(
            FTYP + box(b"moov", box_header(500, b"mvhd")) + sidx([1_000]) + bytes(1_000),
            id="a box running past the end of its parent",
        ),
    ],
)
def test_a_malformed_file_has_no_length(data: bytes) -> None:
    assert _length(data) is None


class _CountingReader(io.BytesIO):
    """A file in memory that counts the bytes read from it."""

    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.bytes_read = 0

    @override
    def read(self, size: int | None = -1, /) -> bytes:
        data = super().read(size)
        self.bytes_read += len(data)
        return data


def test_only_box_headers_and_length_boxes_are_read_not_the_media() -> None:
    file = _CountingReader(FTYP + sidx([2_000]) + box(b"mdat", bytes(1 << 20)))

    length = read_fragmented_length(file)

    assert length == 2.0
    assert file.bytes_read < 100


_KINDS = st.sampled_from([b"moov", b"mvhd", b"mvex", b"mehd", b"sidx", b"mdat"])


def _box_claiming(kind: bytes, payload: bytes, size: int | None) -> bytes:
    return box(kind, payload) if size is None else box_header(size, kind) + payload


def _any_box(payloads: st.SearchStrategy[bytes]) -> st.SearchStrategy[bytes]:
    """Return boxes around `payloads` whose size is right or any 32-bit number."""
    sizes = st.none() | st.integers(0, 2**32 - 1)
    return st.builds(_box_claiming, _KINDS, payloads, sizes)


_BOX_TREES = st.recursive(
    st.binary(max_size=40),
    lambda children: _any_box(st.lists(children, max_size=4).map(b"".join)),
    max_leaves=12,
)


@given(st.lists(_BOX_TREES, max_size=4).map(b"".join))
def test_any_file_has_a_positive_length_or_none_and_never_raises(boxes: bytes) -> None:
    length = _length(FTYP + boxes)

    assert length is None or length > 0
