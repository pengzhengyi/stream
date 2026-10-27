"""A Track's details, each kept with where it came from, and the value each field shows.

Every value has an *origin*. A field shows the value of the first origin, in
`ORIGINS`, that has one, so the household's word always wins and a source read
again replaces only its own values:

```text
title    household: —           files: "Night Drive"   file_name: "BV1dm4y1s7ak"
         shows "Night Drive", from files
```

The album fields travel together: they show from the first origin that names an
album, so one Track never mixes two releases; the household's own value for any
of them still wins on its own.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from medleyplay.domain.errors import InvalidInputError

MAX_TEXT: Final = 512
MAX_NUMBER: Final = 999
MIN_YEAR: Final = 1000
MAX_YEAR: Final = 2999


class Origin(StrEnum):
    """Where a value came from, in the order the shown value is chosen."""

    HOUSEHOLD = "household"
    """Entered by someone in the household."""
    FILES = "files"
    """The file's tags."""
    MUSICBRAINZ = "musicbrainz"
    """A release matched in MusicBrainz."""
    VIDEO = "video"
    """The video's own text, from the site, a file beside the audio, or a paste."""
    ALBUM_FILE = "album_file"
    """For a song inside a long file, its album file's album fields."""
    FILE_NAME = "file_name"
    """The file's name: the title of last resort."""


ORIGINS: Final = tuple(Origin)


class Field(StrEnum):
    """A detail of a Track."""

    TITLE = "title"
    ARTIST = "artist"
    ALBUM = "album"
    ALBUM_ARTIST = "album_artist"
    TRACK_NUMBER = "track_number"
    DISC_NUMBER = "disc_number"
    YEAR = "year"
    GENRE = "genre"


TEXT_FIELDS: Final = frozenset(
    {Field.TITLE, Field.ARTIST, Field.ALBUM, Field.ALBUM_ARTIST, Field.GENRE}
)
NUMBER_FIELDS: Final = frozenset({Field.TRACK_NUMBER, Field.DISC_NUMBER, Field.YEAR})
ALBUM_FIELDS: Final = frozenset(
    {Field.ALBUM, Field.ALBUM_ARTIST, Field.TRACK_NUMBER, Field.DISC_NUMBER, Field.YEAR}
)
"""The fields that describe the release a Track is on, shown from one origin."""

type Value = str | int
type Values = Mapping[Field, Value]


@dataclass(frozen=True)
class Shown:
    """The value a field shows, and the origin it came from."""

    value: Value
    origin: Origin


def check_value(field: Field, value: object) -> Value:
    """Return `value` as `field` keeps it, or raise `InvalidInputError` saying why.

    Text is trimmed and at most `MAX_TEXT` characters; empty text is a value, which
    shows nothing. Numbers are whole, from 1, and a year has four digits.
    """
    if field in TEXT_FIELDS:
        if not isinstance(value, str):
            message = f"{field} is text."
            raise InvalidInputError(message)
        text = value.strip()
        if len(text) > MAX_TEXT:
            message = f"{field} is at most {MAX_TEXT} characters."
            raise InvalidInputError(message)
        return text
    if not isinstance(value, int) or isinstance(value, bool):
        message = f"{field} is a whole number."
        raise InvalidInputError(message)
    low, high = (MIN_YEAR, MAX_YEAR) if field is Field.YEAR else (1, MAX_NUMBER)
    if not low <= value <= high:
        message = f"{field} is from {low} to {high}."
        raise InvalidInputError(message)
    return value


def check_values(values: Mapping[str, object]) -> dict[Field, Value]:
    """Return every value checked, keyed by its field; an unknown field is refused."""
    return {
        field_named(name): check_value(field_named(name), value) for name, value in values.items()
    }


def field_named(name: str) -> Field:
    """Return the field called `name`, or raise `InvalidInputError` for one a Track lacks."""
    try:
        return Field(name)
    except ValueError:
        message = f"A Track has no detail {name!r}."
        raise InvalidInputError(message) from None


def shown(values: Mapping[Origin, Values]) -> dict[Field, Shown]:
    """Return the value each field shows, from each origin's values.

    A field no origin has is absent.
    """
    found: dict[Field, Shown] = {}
    for field in Field:
        if field in ALBUM_FIELDS:
            continue
        first = _first(values, field, ORIGINS)
        if first is not None:
            found[field] = first
    found |= _album(values)
    return found


def _album(values: Mapping[Origin, Values]) -> dict[Field, Shown]:
    named = next(
        (origin for origin in ORIGINS if values.get(origin, {}).get(Field.ALBUM)),
        None,
    )
    # Without a named album, each album field falls back on its own.
    origins = ORIGINS if named is None else (Origin.HOUSEHOLD, named)
    found: dict[Field, Shown] = {}
    for field in ALBUM_FIELDS:
        first = _first(values, field, origins)
        if first is not None:
            found[field] = first
    return found


def _first(
    values: Mapping[Origin, Values], field: Field, origins: tuple[Origin, ...]
) -> Shown | None:
    for origin in origins:
        value = values.get(origin, {}).get(field)
        if value is not None:
            return Shown(value, origin)
    return None
