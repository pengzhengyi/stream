"""Segments: the songs inside one long file, each a Track playing a stretch of its audio.

```text
BV1dm4y1s7ak.m4a   2:28:46   the album file
  1  00:00  Intro              a segment
  2  03:12  Night Drive        a segment
  3  07:40  Blue Room          a segment
```

A song ends where the next starts, and the last at the end of the file. Each song
keeps its id across edits, so a song moved, renamed, or retimed stays the same Track.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Final, NewType

from medleyplay.domain.catalog import SourceId
from medleyplay.domain.errors import InvalidInputError
from medleyplay.domain.video_text import MIN_SONG_MS, Song, check_songs

SegmentId = NewType("SegmentId", int)

SEGMENT_SOURCE: Final = "segment"
"""The kind of a segment's Source; its locator is `<album file's Source id>/<segment id>`."""


@dataclass(frozen=True)
class SongRow:
    """A row of the songs editor: the song it keeps, or `None` for a new one, and its song."""

    id: SegmentId | None
    song: Song


@dataclass(frozen=True)
class SplitPlan:
    """What saving the editor's rows does: each kept and added song with its place."""

    kept: tuple[tuple[SegmentId, int, Song], ...]
    added: tuple[tuple[int, Song], ...]
    removed: frozenset[SegmentId]


def plan_split(
    existing: Iterable[SegmentId], rows: Sequence[SongRow], length_ms: int | None
) -> SplitPlan:
    """Return what saving `rows` over a file's `existing` songs does, or raise.

    The rows must be a song list, each song starting at least a second before the
    file ends when its length is known; each id must name one of `existing`, once.
    An `InvalidInputError` says which row or rule fails.
    """
    have = set(existing)
    seen: set[SegmentId] = set()
    for number, row in enumerate(rows, start=1):
        if row.id is not None and (row.id not in have or row.id in seen):
            message = f"Row {number} names no other song of this file."
            raise InvalidInputError(message)
        if row.id is not None:
            seen.add(row.id)
    check_songs([row.song for row in rows])
    if length_ms is not None and rows[-1].song.start_ms > length_ms - MIN_SONG_MS:
        message = "Each song starts at least a second before the file ends."
        raise InvalidInputError(message)
    kept = tuple((row.id, place, row.song) for place, row in enumerate(rows) if row.id is not None)
    added = tuple((place, row.song) for place, row in enumerate(rows) if row.id is None)
    return SplitPlan(kept, added, frozenset(have - seen))


def ends_of(starts: Sequence[int], length_ms: int | None) -> list[int | None]:
    """Return where each song starting at `starts` ends: the next start, or the file's end.

    A file now shorter than its last song's start ends that song where it starts.
    """
    if not starts:
        return []
    last = length_ms if length_ms is None else max(length_ms, starts[-1])
    return [*starts[1:], last]


def segment_locator(album_source: SourceId, segment: SegmentId) -> str:
    """Return a segment's Source locator."""
    return f"{album_source}/{segment}"


def parse_segment_locator(locator: str) -> tuple[SourceId, SegmentId]:
    """Return the album file's Source and the segment a locator names, or raise."""
    album, _, segment = locator.partition("/")
    if not (album.isdecimal() and segment.isdecimal()):
        message = f"{locator!r} names no segment."
        raise InvalidInputError(message)
    return SourceId(int(album)), SegmentId(int(segment))


def needs_check(split_length_ms: int | None, length_ms: int | None) -> bool:
    """Return whether a file split at one length has since changed by a second or more."""
    if split_length_ms is None or length_ms is None:
        return False
    return abs(length_ms - split_length_ms) >= MIN_SONG_MS
