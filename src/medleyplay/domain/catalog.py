"""The catalog: Tracks, the Sources their audio comes from, and each Account's view of them."""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final, NewType

from medleyplay.domain.errors import InvalidInputError
from medleyplay.domain.rules import Favorite, Match, Rules

TrackId = NewType("TrackId", int)
SourceId = NewType("SourceId", int)
PlaylistId = NewType("PlaylistId", uuid.UUID)

MIN_RATING: Final = 1
MAX_RATING: Final = 5
MAX_PLAYLIST_NAME_LENGTH: Final = 128
MAX_PLAYLIST_LENGTH: Final = 10_000


class Builtin(StrEnum):
    """A Playlist the server keeps for every Account, which can't be edited or deleted."""

    FAVORITES = "favorites"


FAVORITES_NAME: Final = "Favorites"
FAVORITES_RULES: Final = Rules(Match.ALL, (Favorite(value=True),))
"""The rules of Favorites: the Tracks the Account marked as a favorite."""


class SourceState(StrEnum):
    """Whether a Source's audio can be played now."""

    OK = "ok"
    MISSING = "missing"
    UNAVAILABLE = "unavailable"
    CANT_PLAY = "cant_play"


class Availability(StrEnum):
    """Whether a Track can play now, best first."""

    OK = "ok"
    OFFLINE = "offline"
    """Its file is in a Library whose drive is unplugged."""
    UNAVAILABLE = "unavailable"
    MISSING = "missing"
    CANT_PLAY = "cant_play"


_RANK: Final = {availability: rank for rank, availability in enumerate(Availability)}
_OF_STATE: Final = {
    SourceState.OK: Availability.OK,
    SourceState.UNAVAILABLE: Availability.UNAVAILABLE,
    SourceState.MISSING: Availability.MISSING,
    SourceState.CANT_PLAY: Availability.CANT_PLAY,
}


def source_availability(state: SourceState, *, online: bool) -> Availability:
    """Return whether a Source can play, given whether the place holding it is online."""
    found = _OF_STATE[state]
    return Availability.OFFLINE if found is Availability.OK and not online else found


def track_availability(sources: Iterable[Availability]) -> Availability:
    """Return the best availability of a Track's Sources; a Track without any is missing."""
    return min(sources, key=_RANK.__getitem__, default=Availability.MISSING)


@dataclass(frozen=True)
class SourceKey:
    """The natural key of a Source: its kind and its canonical locator for that kind.

    Two links to the same audio canonicalize to one key, so adding either one finds
    the same Source:

    ```text
    kind="bilibili"  locator="BV1Xx41117Tz/p1"
    kind="library"   locator="3/Albums/Blue/01 Intro.flac"
    ```
    """

    kind: str
    locator: str

    def __post_init__(self) -> None:
        """Refuse an empty kind or locator."""
        if not self.kind or not self.locator:
            message = f"A Source key needs a kind and a locator, got {self!r}."
            raise InvalidInputError(message)


@dataclass(frozen=True)
class TrackDetails:
    """What a Source says about the music in it."""

    title: str
    artist: str = ""
    album: str = ""
    album_artist: str = ""
    duration_ms: int | None = None


@dataclass(frozen=True)
class Track:
    """A piece of music, with the signed-in Account's own favorite, rating, and plays."""

    id: TrackId
    details: TrackDetails
    added_at: datetime
    favorite: bool
    rating: int | None
    play_count: int
    last_played_at: datetime | None
    availability: Availability
    downloaded: bool = False
    """Whether a Source of the Track has a Download kept on the server."""


@dataclass(frozen=True)
class Playlist:
    """An Account's named, ordered list of Tracks; a Track may appear more than once.

    A smart playlist has `rules`, and its Tracks are the ones they match now,
    newest added first. Stored rules the server can't read leave it with no
    rules and no Tracks, and `unreadable` saying why. A `builtin` Playlist is one
    the server keeps, such as Favorites.
    """

    id: PlaylistId
    name: str
    track_ids: tuple[TrackId, ...]
    updated_at: datetime
    rules: Rules | None = None
    keep_downloaded: bool = False
    unreadable: str = ""
    builtin: Builtin | None = None


def check_rating(rating: int | None) -> None:
    """Refuse a rating outside 1-5 stars; `None` clears the rating."""
    if rating is not None and not MIN_RATING <= rating <= MAX_RATING:
        message = f"A rating is {MIN_RATING}-{MAX_RATING} stars, got {rating}."
        raise InvalidInputError(message)


def parse_playlist_name(raw: str) -> str:
    """Return a Playlist name without surrounding spaces."""
    candidate = raw.strip()
    if not 1 <= len(candidate) <= MAX_PLAYLIST_NAME_LENGTH:
        message = f"A Playlist name must be 1-{MAX_PLAYLIST_NAME_LENGTH} characters."
        raise InvalidInputError(message)
    return candidate


def check_playlist_length(track_ids: tuple[TrackId, ...]) -> None:
    """Refuse a Playlist longer than the household could plausibly build."""
    if len(track_ids) > MAX_PLAYLIST_LENGTH:
        message = f"A Playlist holds at most {MAX_PLAYLIST_LENGTH} entries."
        raise InvalidInputError(message)
