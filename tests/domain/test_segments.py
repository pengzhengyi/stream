"""Segments: the songs inside one long file, where each ends, and what saving the rows does."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from medleyplay.domain.catalog import SourceId
from medleyplay.domain.errors import InvalidInputError
from medleyplay.domain.segments import (
    SegmentId,
    SongRow,
    ends_of,
    needs_check,
    parse_segment_locator,
    plan_split,
    segment_locator,
)
from medleyplay.domain.video_text import Song

ALBUM_MS = 2 * 3_600_000
"""A two-hour album file."""


def _rows(*rows: tuple[int | None, int, str]) -> list[SongRow]:
    """Editor rows, each `(id or None for a new song, start_ms, title)`."""
    return [
        SongRow(None if id_ is None else SegmentId(id_), Song(start, title))
        for id_, start, title in rows
    ]


# --- Where each song ends ----------------------------------------------------


def test_a_song_ends_where_the_next_starts_and_the_last_at_the_end_of_the_file() -> None:
    assert ends_of([0, 192_000, 460_000], ALBUM_MS) == [192_000, 460_000, ALBUM_MS]


def test_a_file_with_no_songs_has_no_ends() -> None:
    assert ends_of([], ALBUM_MS) == []


def test_a_file_now_shorter_than_its_last_songs_start_ends_that_song_where_it_starts() -> None:
    assert ends_of([0, 5_000], 3_000) == [5_000, 5_000]


def test_the_last_song_of_a_file_of_unknown_length_has_no_end() -> None:
    assert ends_of([0, 192_000], None) == [192_000, None]


@given(
    st.lists(st.integers(1_000, 600_000), min_size=2, max_size=40),
    st.integers(1_000, 600_000),
)
def test_the_songs_tile_the_file_without_a_gap_or_an_overlap(lengths: list[int], tail: int) -> None:
    starts = [sum(lengths[:index]) for index in range(len(lengths))]
    length = starts[-1] + tail

    ends = ends_of(starts, length)

    assert ends[:-1] == starts[1:]
    assert ends[-1] == length


# --- Saving the editor's rows ------------------------------------------------


def test_a_first_split_adds_every_row() -> None:
    plan = plan_split([], _rows((None, 0, "Intro"), (None, 192_000, "Night Drive")), ALBUM_MS)

    assert plan.added == ((0, Song(0, "Intro")), (1, Song(192_000, "Night Drive")))
    assert plan.kept == ()
    assert plan.removed == frozenset()


def test_a_row_keeps_its_song_when_moved_renamed_or_retimed() -> None:
    existing = [SegmentId(7), SegmentId(8)]

    plan = plan_split(
        existing,
        _rows((None, 0, "Intro"), (8, 100_000, "Night Drive (Live)"), (7, 300_000, "Blue Room")),
        ALBUM_MS,
    )

    assert plan.kept == (
        (SegmentId(8), 1, Song(100_000, "Night Drive (Live)")),
        (SegmentId(7), 2, Song(300_000, "Blue Room")),
    )
    assert plan.added == ((0, Song(0, "Intro")),)


def test_a_song_left_out_of_the_rows_is_removed() -> None:
    plan = plan_split(
        [SegmentId(7), SegmentId(8), SegmentId(9)],
        _rows((7, 0, "Intro"), (9, 300_000, "Blue Room")),
        ALBUM_MS,
    )

    assert plan.removed == frozenset({SegmentId(8)})


def test_a_row_naming_a_song_of_another_file_is_refused() -> None:
    with pytest.raises(InvalidInputError, match="Row 2"):
        plan_split([SegmentId(7)], _rows((7, 0, "Intro"), (42, 192_000, "Other")), ALBUM_MS)


def test_two_rows_naming_one_song_are_refused() -> None:
    with pytest.raises(InvalidInputError, match="Row 2"):
        plan_split([SegmentId(7)], _rows((7, 0, "Intro"), (7, 192_000, "Again")), ALBUM_MS)


def test_rows_that_are_not_a_song_list_are_refused() -> None:
    with pytest.raises(InvalidInputError, match="at least a second"):
        plan_split([], _rows((None, 0, "Intro"), (None, 500, "Too soon")), ALBUM_MS)


def test_a_song_starting_after_the_file_ends_is_refused() -> None:
    with pytest.raises(InvalidInputError, match="before the file ends"):
        plan_split([], _rows((None, 0, "Intro"), (None, ALBUM_MS, "After")), ALBUM_MS)


def test_the_last_song_lasts_at_least_a_second() -> None:
    with pytest.raises(InvalidInputError, match="before the file ends"):
        plan_split([], _rows((None, 0, "Intro"), (None, ALBUM_MS - 999, "Blip")), ALBUM_MS)


def test_a_file_of_unknown_length_takes_any_rising_starts() -> None:
    plan = plan_split([], _rows((None, 0, "Intro"), (None, 99 * ALBUM_MS, "Late")), None)

    assert len(plan.added) == 2


# --- A segment's Source, and checking after a rescan -------------------------


def test_a_segments_locator_names_its_album_files_source_and_itself() -> None:
    locator = segment_locator(SourceId(3), SegmentId(41))

    assert locator == "3/41"
    assert parse_segment_locator(locator) == (SourceId(3), SegmentId(41))


@pytest.mark.parametrize("locator", ["", "3", "3/", "/41", "a/41", "3/41/5", "-3/41"])
def test_a_locator_that_names_no_segment_is_refused(locator: str) -> None:
    with pytest.raises(InvalidInputError):
        parse_segment_locator(locator)


@pytest.mark.parametrize(
    ("split_at", "now", "expected"),
    [
        (ALBUM_MS, ALBUM_MS, False),
        (ALBUM_MS, ALBUM_MS + 999, False),
        (ALBUM_MS, ALBUM_MS - 1_000, True),
        (ALBUM_MS, None, False),
        (None, ALBUM_MS, False),
    ],
    ids=["same", "within a second", "a second shorter", "length now unknown", "unknown before"],
)
def test_a_split_file_needs_checking_once_its_length_changes_by_a_second(
    split_at: int | None, now: int | None, *, expected: bool
) -> None:
    assert needs_check(split_at, now) is expected
