"""Reading a `Range` header against a slice of bytes, as RFC 9110 defines it."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from medleyplay.web.ranges import UNSATISFIABLE, ByteRange, requested_range


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("bytes=0-1", ByteRange(0, 2)),
        ("bytes=10-", ByteRange(10, 100)),
        ("bytes=-30", ByteRange(70, 100)),
        ("bytes=95-500", ByteRange(95, 100)),
        ("bytes=-500", ByteRange(0, 100)),
        ("bytes=99-99", ByteRange(99, 100)),
        ("BYTES=0-1", ByteRange(0, 2)),
        ("bytes= 5-9 ,0-1", ByteRange(5, 10)),
    ],
)
def test_a_satisfiable_range_is_clamped_to_the_slice(header: str, expected: ByteRange) -> None:
    assert requested_range(header, 100) == expected


def test_several_ranges_answer_the_first_satisfiable_one() -> None:
    assert requested_range("bytes=500-600, 5-9, 0-1", 100) == ByteRange(5, 10)


@pytest.mark.parametrize("header", ["bytes=100-", "bytes=100-200", "bytes=-0", "bytes=500-, 600-"])
def test_a_range_past_the_end_is_unsatisfiable(header: str) -> None:
    assert requested_range(header, 100) is UNSATISFIABLE


def test_every_range_of_an_empty_slice_is_unsatisfiable() -> None:
    assert requested_range("bytes=-5", 0) is UNSATISFIABLE


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "bytes",
        "bytes=",
        "bytes=5-1",
        "bytes=a-b",
        "bytes=-",
        "bytes=+1-2",
        "bytes=0-1, x",
        "items=0-1",
        "bytes=0x10-",
        "bytes=１-２",  # noqa: RUF001 -- full-width digits, which `int` would accept
    ],
)
def test_a_header_that_does_not_parse_asks_for_the_whole_slice(header: str | None) -> None:
    assert requested_range(header, 100) is None


@given(st.binary(min_size=1, max_size=300), st.data())
def test_a_range_selects_exactly_its_bytes(content: bytes, data: st.DataObject) -> None:
    start = data.draw(st.integers(0, len(content) - 1))
    end = data.draw(st.integers(start, len(content) + 10))

    found = requested_range(f"bytes={start}-{end}", len(content))

    assert isinstance(found, ByteRange)
    assert content[found.start : found.stop] == content[start : end + 1]


@given(st.integers(0, 300), st.integers(1, 400))
def test_a_suffix_range_selects_the_last_bytes(length: int, suffix: int) -> None:
    found = requested_range(f"bytes=-{suffix}", length)

    if length == 0:
        assert found is UNSATISFIABLE
    else:
        assert found == ByteRange(max(length - suffix, 0), length)


def test_an_open_range_of_an_empty_slice_is_unsatisfiable() -> None:
    assert requested_range("bytes=0-", 0) is UNSATISFIABLE
