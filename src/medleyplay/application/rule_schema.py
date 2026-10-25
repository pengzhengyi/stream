"""The JSON shape of smart-playlist rules, version 1, read into the domain's rules and back.

The rules are stored as this document and sent as it, so the version says how to
read a stored one after the schema grows; a version newer than the server knows
is refused rather than half-read.
"""

from typing import Annotated, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from medleyplay.domain.errors import InvalidInputError
from medleyplay.domain.rules import (
    Added,
    AgeOp,
    Condition,
    Favorite,
    Kind,
    LastPlayed,
    Match,
    PlayCount,
    Rating,
    Rules,
    Text,
    TextField,
    TextOp,
)

VERSION: Final = 1
MAX_CONDITIONS: Final = 20
MAX_DAYS: Final = 3650
MAX_TEXT: Final = 512

type Days = Annotated[int, Field(ge=1, le=MAX_DAYS)]


class _Condition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FavoriteIn(_Condition):
    """`favorite is true`, or `false`."""

    field: Literal["favorite"]
    op: Literal["is"]
    value: bool


class RatingIn(_Condition):
    """A rating of 1-5 stars, a bound on it, or `unrated`, which takes no value."""

    field: Literal["rating"]
    op: Literal["is", "at_least", "at_most", "unrated"]
    value: Annotated[int, Field(ge=1, le=5)] | None = None

    @model_validator(mode="after")
    def _value_unless_unrated(self) -> Self:
        if (self.op == "unrated") != (self.value is None):
            message = "unrated takes no value, and every other rating operator takes one"
            raise ValueError(message)
        return self


class PlayCountIn(_Condition):
    """A bound on how many times the Track was played."""

    field: Literal["play_count"]
    op: Literal["at_least", "at_most"]
    value: Annotated[int, Field(ge=0)]


class LastPlayedIn(_Condition):
    """Whether the Track was last played within a number of days."""

    field: Literal["last_played"]
    op: AgeOp
    value: Days


class AddedIn(_Condition):
    """Whether the Track was added within a number of days."""

    field: Literal["added"]
    op: AgeOp
    value: Days


class TextIn(_Condition):
    """Whether the Track's title, artist, or album is, or contains, some text."""

    field: TextField
    op: TextOp
    value: Annotated[str, Field(min_length=1, max_length=MAX_TEXT)]


class SourceKindIn(_Condition):
    """Whether one of the Track's Sources is of a kind."""

    field: Literal["source_kind"]
    op: Literal["is"]
    value: Annotated[str, Field(min_length=1, max_length=64)]


type ConditionIn = Annotated[
    FavoriteIn | RatingIn | PlayCountIn | LastPlayedIn | AddedIn | TextIn | SourceKindIn,
    Field(discriminator="field"),
]


class RulesIn(BaseModel):
    """A smart playlist's rules as JSON: a version, `all` or `any`, and 1-20 conditions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    match: Match
    conditions: Annotated[list[ConditionIn], Field(min_length=1, max_length=MAX_CONDITIONS)]


def read_rules(document: object) -> Rules:
    """Return the rules a document spells out; raise `InvalidInputError` saying what is wrong."""
    if isinstance(document, dict):
        version = document.get("version")
        if isinstance(version, int) and version > VERSION:
            message = f"The rules are version {version}, newer than this server reads."
            raise InvalidInputError(message)
    try:
        parsed = RulesIn.model_validate(document)
    except ValidationError as error:
        first = error.errors()[0]
        where = ".".join(str(part) for part in first["loc"])
        message = f"The rules aren't valid at {where}: {first['msg']}"
        raise InvalidInputError(message) from None
    return Rules(parsed.match, tuple(_condition(each) for each in parsed.conditions))


def rules_document(rules: Rules) -> dict[str, object]:
    """Return the document that reads as `rules`."""
    return {
        "version": VERSION,
        "match": rules.match.value,
        "conditions": [_document(each) for each in rules.conditions],
    }


def _condition(condition: ConditionIn) -> Condition:  # noqa: PLR0911 -- one per field
    match condition:
        case FavoriteIn(value=value):
            return Favorite(value=value)
        case RatingIn(op=op, value=value):
            return Rating(op, value)
        case PlayCountIn(op=op, value=value):
            return PlayCount(op, value)
        case LastPlayedIn(op=op, value=value):
            return LastPlayed(op, value)
        case AddedIn(op=op, value=value):
            return Added(op, value)
        case TextIn(field=field, op=op, value=value):
            return Text(field, op, value)
        case SourceKindIn(value=value):
            return Kind(value)


def _document(condition: Condition) -> dict[str, object]:  # noqa: PLR0911 -- one per kind
    match condition:
        case Favorite(value=value):
            return {"field": "favorite", "op": "is", "value": value}
        case Rating(op="unrated"):
            return {"field": "rating", "op": "unrated"}
        case Rating(op=op, value=value):
            return {"field": "rating", "op": op, "value": value}
        case PlayCount(op=op, value=value):
            return {"field": "play_count", "op": op, "value": value}
        case LastPlayed(op=op, days=days):
            return {"field": "last_played", "op": op, "value": days}
        case Added(op=op, days=days):
            return {"field": "added", "op": op, "value": days}
        case Text(field=field, op=op, value=value):
            return {"field": field, "op": op, "value": value}
        case Kind(value=value):
            return {"field": "source_kind", "op": "is", "value": value}
