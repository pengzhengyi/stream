"""Smart-playlist rules, and matching them against one Track as one Account sees it.

A rule is one level of conditions joined by `all` or `any`:

```text
all of: favorite is true, rating at least 4, added within 30 days
```

Text is compared after Unicode compatibility folding and case folding, so a
title in full-width capitals matches the same words typed plainly. A day count
includes its boundary: a Track added exactly 7 days ago is added within 7 days.
"""

import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal

type NumberOp = Literal["is", "at_least", "at_most"]
type AgeOp = Literal["within_days", "not_within_days"]
type TextField = Literal["title", "artist", "album"]
type TextOp = Literal["is", "contains"]


class Match(StrEnum):
    """Whether a Track must meet every condition, or one of them."""

    ALL = "all"
    ANY = "any"


@dataclass(frozen=True)
class TrackFacts:
    """What rules may ask of a Track, with the favorite, rating, and plays of one Account."""

    title: str
    artist: str
    album: str
    added_at: datetime
    favorite: bool
    rating: int | None
    play_count: int
    last_played_at: datetime | None
    source_kinds: frozenset[str]


@dataclass(frozen=True)
class Favorite:
    """The Track is, or isn't, a favorite."""

    value: bool


@dataclass(frozen=True)
class Rating:
    """The Track's rating is a number of stars, at least or at most one, or none."""

    op: NumberOp | Literal["unrated"]
    value: int | None = None


@dataclass(frozen=True)
class PlayCount:
    """The Track was played at least, or at most, a number of times."""

    op: Literal["at_least", "at_most"]
    value: int


@dataclass(frozen=True)
class LastPlayed:
    """The Track was, or wasn't, last played within a number of days."""

    op: AgeOp
    days: int


@dataclass(frozen=True)
class Added:
    """The Track was, or wasn't, added within a number of days."""

    op: AgeOp
    days: int


@dataclass(frozen=True)
class Text:
    """The Track's title, artist, or album is, or contains, some text."""

    field: TextField
    op: TextOp
    value: str


@dataclass(frozen=True)
class Kind:
    """One of the Track's Sources is of a kind, such as `bilibili` or `library`."""

    value: str


type Condition = Favorite | Rating | PlayCount | LastPlayed | Added | Text | Kind


@dataclass(frozen=True)
class Rules:
    """A smart playlist's conditions, and whether a Track must meet all or any of them."""

    match: Match
    conditions: tuple[Condition, ...]


def matches(rules: Rules, facts: TrackFacts, now: datetime) -> bool:
    """Return whether the Track meets the rules at `now`."""
    met = (_meets(condition, facts, now) for condition in rules.conditions)
    return all(met) if rules.match is Match.ALL else any(met)


def fold(text: str) -> str:
    """Return `text` as rules compare it: compatibility-folded, then case-folded."""
    return unicodedata.normalize("NFKC", text).casefold()


def _meets(condition: Condition, facts: TrackFacts, now: datetime) -> bool:  # noqa: PLR0911
    match condition:
        case Favorite(value=value):
            return facts.favorite is value
        case Rating(op="unrated"):
            return facts.rating is None
        case Rating(op=op, value=value):
            return facts.rating is not None and _compare(op, facts.rating, value)
        case PlayCount(op=op, value=value):
            return _compare(op, facts.play_count, value)
        case LastPlayed(op=op, days=days):
            return _within(op, facts.last_played_at, days, now)
        case Added(op=op, days=days):
            return _within(op, facts.added_at, days, now)
        case Text(field=field, op=op, value=value):
            actual, wanted = fold(getattr(facts, field)), fold(value)
            return actual == wanted if op == "is" else wanted in actual
        case Kind(value=value):
            return value in facts.source_kinds


def _compare(op: str, actual: int, value: int | None) -> bool:
    if value is None:  # pragma: no cover -- every number condition but unrated has a value
        return False
    if op == "at_least":
        return actual >= value
    if op == "at_most":
        return actual <= value
    return actual == value


def _within(op: AgeOp, when: datetime | None, days: int, now: datetime) -> bool:
    within = when is not None and now - when <= timedelta(days=days)
    return within if op == "within_days" else not within
