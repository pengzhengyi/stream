"""Smart-playlist rules matching one Track as one Account sees it."""

import dataclasses
from datetime import UTC, datetime, timedelta

import pytest

from medleyplay.domain.rules import (
    Added,
    Condition,
    Favorite,
    Kind,
    LastPlayed,
    Match,
    Not,
    PlayCount,
    Rating,
    Rules,
    Text,
    TrackFacts,
    matches,
)

NOW = datetime(2026, 10, 26, 12, tzinfo=UTC)


def _night_drive() -> TrackFacts:
    """*Night Drive* by 周杰伦 on *Midnight*: a favorite rated 4, played 3 times, 10 days old."""
    return TrackFacts(
        title="Night Drive",
        artist="周杰伦",
        album="Midnight",
        added_at=NOW - timedelta(days=10),
        favorite=True,
        rating=4,
        play_count=3,
        last_played_at=NOW - timedelta(days=2),
        source_kinds=frozenset({"bilibili"}),
    )


def _full_width(text: str) -> str:
    """`text` with each letter in its full-width form, as CJK text often writes Latin letters."""
    return "".join(chr(ord(each) + 0xFEE0) if each.isalpha() else each for each in text)


def _all(*conditions: Condition) -> Rules:
    return Rules(Match.ALL, conditions)


@pytest.mark.parametrize(
    ("condition", "expected"),
    [
        (Favorite(value=True), True),
        (Favorite(value=False), False),
        (Rating("is", 4), True),
        (Rating("at_least", 5), False),
        (Rating("at_most", 4), True),
        (Rating("unrated"), False),
        (PlayCount("at_least", 3), True),
        (PlayCount("at_most", 2), False),
        (LastPlayed(7), True),
        (LastPlayed(1), False),
        (Added(30), True),
        (Added(9), False),
        (Text("artist", "is", "周杰伦"), True),
        (Text("title", "contains", "night"), True),
        (Text("album", "contains", "noon"), False),
        (Kind("bilibili"), True),
        (Kind("library"), False),
        (Not(Text("artist", "contains", "周")), False),
        (Not(Kind("library")), True),
    ],
)
def test_each_condition_matches_the_track_as_its_field_and_operator_say(
    condition: Condition,
    expected: bool,  # noqa: FBT001 -- a parameter of the test
) -> None:
    assert matches(_all(condition), _night_drive(), NOW) is expected


def test_an_unrated_track_matches_unrated_and_no_rating_bound() -> None:
    unrated = dataclasses.replace(_night_drive(), rating=None)

    assert matches(_all(Rating("unrated")), unrated, NOW)
    assert not matches(_all(Rating("at_most", 5)), unrated, NOW)


def test_a_track_never_played_is_not_within_any_days() -> None:
    never_played = dataclasses.replace(_night_drive(), play_count=0, last_played_at=None)

    assert not matches(_all(LastPlayed(3650)), never_played, NOW)
    assert matches(_all(Not(LastPlayed(1))), never_played, NOW)


def test_text_is_compared_case_folded_and_width_folded() -> None:
    shouting = dataclasses.replace(_night_drive(), title=_full_width("NIGHT DRIVE"))

    assert matches(_all(Text("title", "is", "night drive")), shouting, NOW)


def test_all_needs_every_condition_and_any_needs_one() -> None:
    conditions = (Favorite(value=True), Kind("library"))

    assert not matches(Rules(Match.ALL, conditions), _night_drive(), NOW)
    assert matches(Rules(Match.ANY, conditions), _night_drive(), NOW)


def test_days_count_back_from_now_inclusive_of_the_boundary() -> None:
    added_a_week_ago = dataclasses.replace(_night_drive(), added_at=NOW - timedelta(days=7))

    assert matches(_all(Added(7)), added_a_week_ago, NOW)
    assert not matches(_all(Added(6)), added_a_week_ago, NOW)
