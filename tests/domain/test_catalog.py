"""The catalog's value rules: Source keys, availability, ratings, and Playlists."""

import pytest

from medleyplay.domain.catalog import (
    Availability,
    SourceKey,
    SourceState,
    TrackId,
    check_playlist_length,
    check_rating,
    parse_playlist_name,
    source_availability,
    track_availability,
)
from medleyplay.domain.errors import InvalidInputError


@pytest.mark.parametrize(("kind", "locator"), [("", "BV1Xx41117Tz/p1"), ("bilibili", "")])
def test_a_source_key_needs_both_a_kind_and_a_locator(kind: str, locator: str) -> None:
    with pytest.raises(InvalidInputError, match="kind and a locator"):
        SourceKey(kind, locator)


@pytest.mark.parametrize("rating", [None, 1, 5])
def test_a_rating_of_1_to_5_stars_or_none_is_accepted(rating: int | None) -> None:
    check_rating(rating)


@pytest.mark.parametrize("rating", [0, 6, -1])
def test_a_rating_outside_1_to_5_stars_is_refused(rating: int) -> None:
    with pytest.raises(InvalidInputError, match="1-5 stars"):
        check_rating(rating)


def test_a_playlist_name_loses_surrounding_spaces() -> None:
    assert parse_playlist_name("  Morning ") == "Morning"


@pytest.mark.parametrize("raw", ["", " ", "x" * 129])
def test_an_empty_or_overlong_playlist_name_is_refused(raw: str) -> None:
    with pytest.raises(InvalidInputError, match="Playlist name"):
        parse_playlist_name(raw)


def test_a_playlist_of_more_than_10000_entries_is_refused() -> None:
    with pytest.raises(InvalidInputError, match="at most 10000"):
        check_playlist_length((TrackId(1),) * 10_001)


def test_an_ok_source_in_an_offline_library_is_offline() -> None:
    assert source_availability(SourceState.OK, online=False) is Availability.OFFLINE


def test_a_missing_source_stays_missing_whether_or_not_its_library_is_online() -> None:
    assert source_availability(SourceState.MISSING, online=False) is Availability.MISSING


def test_a_track_is_as_available_as_its_best_source() -> None:
    sources = [Availability.CANT_PLAY, Availability.OFFLINE, Availability.MISSING]

    assert track_availability(sources) is Availability.OFFLINE


def test_a_track_without_sources_is_missing() -> None:
    assert track_availability([]) is Availability.MISSING


def test_a_track_waiting_for_online_is_less_available_than_one_on_disk() -> None:
    assert track_availability([Availability.WAITING_ONLINE, Availability.OK]) is Availability.OK
    assert (
        track_availability([Availability.WAITING_ONLINE, Availability.MISSING])
        is Availability.WAITING_ONLINE
    )
