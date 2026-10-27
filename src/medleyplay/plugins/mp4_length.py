"""The length of a fragmented MP4 file, read from its boxes when its header says 0."""

import io
import struct
from collections.abc import Iterator
from dataclasses import dataclass
from typing import BinaryIO, Final

MAX_BOXES: Final = 100_000
"""The most boxes read at one level of a file; one with more is treated as malformed."""

_HEADER_SIZE: Final = 8
_LARGE_HEADER_SIZE: Final = 16
_SIDX_REFERENCE_SIZE: Final = 12
_REFERENCE_TO_INDEX: Final = 0x8000_0000


class _MalformedError(Exception):
    """A box that can't be read as the format describes."""


@dataclass(frozen=True)
class _Box:
    """A box of type `kind` whose payload runs from `start` to `end` in the file."""

    kind: bytes
    start: int
    end: int


def read_fragmented_length(file: BinaryIO) -> float | None:
    """Return the length of an MP4 file in seconds from its boxes, or None if they don't say.

    A fragmented file, such as an audio track downloaded over DASH, keeps its media
    in `moof` and `mdat` fragments after a `moov` whose `mvhd` duration is 0:

        ftyp
        moov
          mvhd          timescale; duration 0
          mvex
            mehd        fragment_duration, in the mvhd timescale
            trex
        sidx            timescale and subsegment durations
        moof, mdat      repeated

    The length is the `mehd` fragment duration over the `mvhd` timescale; without it,
    the sum of every top-level `sidx` box's subsegment durations over its timescale.
    Only box headers and the few boxes named above are read, never the media. A
    malformed file has no length rather than raising.
    """
    try:
        return _read_length(file, end=file.seek(0, io.SEEK_END))
    except _MalformedError:
        return None


def _read_length(file: BinaryIO, *, end: int) -> float | None:
    indexed = 0.0
    for box in _boxes(file, start=0, end=end):
        if box.kind == b"moov" and (length := _moov_length(file, box)) is not None:
            return length
        if box.kind == b"sidx":
            indexed += _sidx_length(file, box)
    return indexed if indexed > 0 else None


def _boxes(file: BinaryIO, *, start: int, end: int) -> Iterator[_Box]:
    """Yield the boxes from `start` to `end`, reading only their headers."""
    position = start
    for _ in range(MAX_BOXES):
        if position == end:
            return
        size, kind = struct.unpack(">I4s", _read_at(file, position, _HEADER_SIZE))
        header_size = _HEADER_SIZE
        if size == 1:
            size = int.from_bytes(_read_at(file, position + _HEADER_SIZE, 8))
            header_size = _LARGE_HEADER_SIZE
        elif size == 0:
            size = end - position
        if size < header_size or position + size > end:
            raise _MalformedError
        yield _Box(kind, start=position + header_size, end=position + size)
        position += size
    if position != end:
        raise _MalformedError


def _moov_length(file: BinaryIO, moov: _Box) -> float | None:
    """Return the `mehd` fragment duration over the `mvhd` timescale, if both are given."""
    timescale = 0
    fragment_duration = 0
    for box in _boxes(file, start=moov.start, end=moov.end):
        if box.kind == b"mvhd":
            timescale = _mvhd_timescale(file, box)
        elif box.kind == b"mvex":
            fragment_duration = _mvex_fragment_duration(file, box)
    if timescale == 0 or fragment_duration == 0:
        return None
    return fragment_duration / timescale


def _mvhd_timescale(file: BinaryIO, mvhd: _Box) -> int:
    # Version 0 has 32-bit creation and modification times before the timescale;
    # version 1 has 64-bit ones.
    version = _version(file, mvhd)
    offset = 12 if version == 0 else 20
    return int.from_bytes(_read_payload(file, mvhd, offset, 4))


def _mvex_fragment_duration(file: BinaryIO, mvex: _Box) -> int:
    for box in _boxes(file, start=mvex.start, end=mvex.end):
        if box.kind == b"mehd":
            size = 4 if _version(file, box) == 0 else 8
            return int.from_bytes(_read_payload(file, box, 4, size))
    return 0


def _sidx_length(file: BinaryIO, sidx: _Box) -> float:
    """Return the seconds of media the `sidx` box indexes directly.

    A reference to another `sidx` box is left out, since that box is counted itself.
    """
    version = _version(file, sidx)
    timescale = int.from_bytes(_read_payload(file, sidx, 8, 4))
    if timescale == 0:
        raise _MalformedError
    # Version 0 has 32-bit earliest presentation time and first offset; version 1
    # has 64-bit ones. Two reserved bytes and the reference count follow.
    count_offset = 22 if version == 0 else 30
    count = int.from_bytes(_read_payload(file, sidx, count_offset, 2))
    references = _read_payload(file, sidx, count_offset + 2, count * _SIDX_REFERENCE_SIZE)
    duration: int = sum(
        subsegment_duration
        for kind_and_size, subsegment_duration, _ in struct.iter_unpack(">III", references)
        if not kind_and_size & _REFERENCE_TO_INDEX
    )
    return duration / timescale


def _version(file: BinaryIO, box: _Box) -> int:
    return _read_payload(file, box, 0, 1)[0]


def _read_payload(file: BinaryIO, box: _Box, offset: int, size: int) -> bytes:
    """Read `size` bytes at `offset` into the box's payload, which must hold them."""
    if box.start + offset + size > box.end:
        raise _MalformedError
    return _read_at(file, box.start + offset, size)


def _read_at(file: BinaryIO, position: int, size: int) -> bytes:
    file.seek(position)
    data = file.read(size)
    if len(data) < size:
        raise _MalformedError
    return data
