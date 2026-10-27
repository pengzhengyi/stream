"""MP4 files the tests make, box by box: plain and fragmented, with and without a length."""

import struct
from collections.abc import Sequence
from dataclasses import dataclass

TIMESCALE = 1000
"""The units per second of a test file's `mvhd` and `sidx` boxes: milliseconds."""

FTYP = b"\x00\x00\x00\x10ftypM4A \x00\x00\x00\x00"
"""The `ftyp` box that opens every test file and tells tinytag it reads an MP4 file."""


@dataclass(frozen=True)
class Mp4:
    """What a test MP4 file's boxes say about its length.

    `header_seconds` goes in `mvhd`, which is 0 in a fragmented file. `fragment_seconds`
    adds `mvex/mehd`, written in `mehd_version`'s layout. `segment_seconds` adds a
    top-level `sidx` box holding one subsegment duration each.
    """

    header_seconds: float = 0
    fragment_seconds: float | None = None
    mehd_version: int = 0
    segment_seconds: Sequence[float] = ()


def mp4_bytes(mp4: Mp4) -> bytes:
    """Return a silent MP4 file with the boxes `mp4` describes, and one empty fragment.

    A fragmented file with both lengths looks like this:

        ftyp
        moov
          mvhd          timescale 1000; duration 0
          mvex
            mehd        fragment_duration
            trex
        sidx            timescale 1000; one subsegment duration per segment
        moof
        mdat
    """
    mvex = box(b"mvex", _mehd(mp4) + full_box(b"trex", 0, bytes(20)))
    moov = box(b"moov", mvhd(_units(mp4.header_seconds)) + mvex)
    segments = sidx([_units(seconds) for seconds in mp4.segment_seconds])
    return (
        FTYP
        + moov
        + (segments if mp4.segment_seconds else b"")
        + box(b"moof", b"")
        + box(b"mdat", b"")
    )


def box(kind: bytes, payload: bytes) -> bytes:
    """Return a box of type `kind` around `payload`, with a 32-bit size."""
    return struct.pack(">I", 8 + len(payload)) + kind + payload


def box_header(size: int, kind: bytes) -> bytes:
    """Return the header of a box of type `kind` that claims `size` bytes, true or not."""
    return struct.pack(">I", size) + kind


def large_box(kind: bytes, payload: bytes) -> bytes:
    """Return a box of type `kind` around `payload`, with its size in a 64-bit `largesize`."""
    return struct.pack(">I4sQ", 1, kind, 16 + len(payload)) + payload


def full_box(kind: bytes, version: int, payload: bytes) -> bytes:
    """Return a box that opens with a version and three bytes of flags, all 0."""
    return box(kind, bytes([version, 0, 0, 0]) + payload)


def mvhd(duration: int, *, timescale: int = TIMESCALE, version: int = 0) -> bytes:
    """Return an `mvhd` box with this duration and timescale.

    Version 0 has 32-bit times and duration; version 1 has 64-bit ones.
    """
    if version == 0:
        fields = struct.pack(">II", 0, 0) + struct.pack(">II", timescale, duration)
    else:
        fields = struct.pack(">QQ", 0, 0) + struct.pack(">IQ", timescale, duration)
    return full_box(b"mvhd", version, fields + bytes(80))


def sidx(
    durations: Sequence[int], *, timescale: int = TIMESCALE, version: int = 0, to_index: int = 0
) -> bytes:
    """Return a `sidx` box with a media reference for each subsegment duration.

    `to_index` comes first: that many references to other `sidx` boxes, each
    1000 seconds long.
    """
    times = struct.pack(">II", 0, 0) if version == 0 else struct.pack(">QQ", 0, 0)
    references = [(0x8000_0000, 1_000_000)] * to_index + [(0, units) for units in durations]
    return full_box(
        b"sidx",
        version,
        struct.pack(">II", 1, timescale)
        + times
        + struct.pack(">HH", 0, len(references))
        + b"".join(struct.pack(">III", kind, units, 0) for kind, units in references),
    )


def _mehd(mp4: Mp4) -> bytes:
    if mp4.fragment_seconds is None:
        return b""
    units = _units(mp4.fragment_seconds)
    duration = struct.pack(">I", units) if mp4.mehd_version == 0 else struct.pack(">Q", units)
    return full_box(b"mehd", mp4.mehd_version, duration)


def _units(seconds: float) -> int:
    return round(seconds * TIMESCALE)
