"""Writing a Track's details: each origin's values, and the shown values on the Track's row.

Everything that changes a Track's details writes through `record`,
`record_video_text`, or `set_household`, in the caller's transaction, and each
rewrites the Track's row from its values, so the row always holds what `shown`
chooses.
"""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application import Clock
from medleyplay.domain.catalog import TrackId
from medleyplay.domain.details import (
    TEXT_FIELDS,
    Field,
    Origin,
    Shown,
    Value,
    check_values,
    field_named,
    found_value,
    shown,
)
from medleyplay.domain.errors import InvalidInputError, NotFoundError
from medleyplay.domain.video_text import Chapter, Reading, Song, VideoText, read_video
from medleyplay.persistence.schema import TrackRow, TrackValueRow, VideoTextRow

type OriginValues = dict[Origin, dict[Field, Value]]


@dataclass(frozen=True)
class DetailsView:
    """A Track's shown values, what would show without the household's, and every origin's."""

    track_id: TrackId
    shown: dict[Field, Shown]
    found: dict[Field, Shown]
    values: OriginValues
    video_text: VideoText | None
    """The video's text the `video` values were read from, if any was."""


@dataclass(frozen=True)
class VideoRead:
    """A Track's details once its video's text is read, and the songs that text lists."""

    details: DetailsView
    songs: tuple[Song, ...]


def record(
    db: Session, track_id: TrackId, origin: Origin, values: Mapping[Field, Value], now: datetime
) -> None:
    """Replace `origin`'s values for the Track with `values`, and rewrite its shown values.

    Each is kept as `found_value` keeps a value read from a file or a site, so
    blank text and numbers out of range are dropped.
    """
    if origin is Origin.HOUSEHOLD:
        message = "The household's values are set with set_household."
        raise ValueError(message)
    _require(db, track_id)
    found = {field: found_value(field, value) for field, value in values.items()}
    kept = {field: value for field, value in found.items() if value is not None}
    db.execute(
        delete(TrackValueRow).where(
            TrackValueRow.track_id == track_id, TrackValueRow.origin == origin
        )
    )
    db.add_all(_rows(track_id, origin, kept, now))
    db.flush()
    refresh(db, track_id)


def record_video_text(
    db: Session,
    track_id: TrackId,
    text: VideoText,
    came_from: Literal["household", "file"],
    now: datetime,
) -> Reading:
    """Keep `text` as the Track's video's text, and make what it says the `video` values."""
    _require(db, track_id)
    row = db.get(VideoTextRow, track_id) or VideoTextRow(track_id=track_id)
    row.title = text.title
    row.description = text.description
    row.chapters = [
        {"start_ms": chapter.start_ms, "title": chapter.title} for chapter in text.chapters
    ]
    row.came_from = came_from
    row.recorded_at = now
    db.add(row)
    reading = read_video(text)
    record(db, track_id, Origin.VIDEO, reading.values, now)
    return reading


def video_text_of(db: Session, track_id: TrackId) -> VideoText | None:
    """Return the Track's video's text, or `None` when none was read."""
    row = db.get(VideoTextRow, track_id)
    if row is None:
        return None
    chapters = tuple(
        Chapter(int(chapter["start_ms"]), str(chapter["title"])) for chapter in row.chapters
    )
    return VideoText(row.title, row.description, chapters)


def set_household(
    db: Session,
    track_id: TrackId,
    values: Mapping[Field, Value | None],
    now: datetime,
    *,
    replace: bool = False,
) -> None:
    """Set the household's values for the Track; `None` drops one, so the next origin shows.

    With `replace`, every household value not in `values` is dropped too.
    """
    _require(db, track_id)
    mine = (TrackValueRow.track_id == track_id) & (TrackValueRow.origin == Origin.HOUSEHOLD)
    dropped = mine if replace else mine & TrackValueRow.field.in_([str(field) for field in values])
    db.execute(delete(TrackValueRow).where(dropped))
    given = {field: value for field, value in values.items() if value is not None}
    db.add_all(_rows(track_id, Origin.HOUSEHOLD, given, now))
    db.flush()
    refresh(db, track_id)


def values_of(db: Session, track_id: TrackId) -> OriginValues:
    """Return every origin's values for the Track."""
    found: OriginValues = {}
    for row in db.scalars(select(TrackValueRow).where(TrackValueRow.track_id == track_id)):
        found.setdefault(Origin(row.origin), {})[Field(row.field)] = row.value
    return found


def refresh(db: Session, track_id: TrackId) -> dict[Field, Shown]:
    """Rewrite the Track's row with its shown values, and return them."""
    track = db.get(TrackRow, track_id)
    if track is None:
        raise _no_track(track_id)
    found = shown(values_of(db, track_id))
    for field in Field:
        value = found[field].value if field in found else None
        setattr(track, field.value, "" if value is None and field in TEXT_FIELDS else value)
    return found


class DetailsService:
    """Read a Track's details, set the household's own, and read a video's pasted text."""

    def __init__(
        self,
        units: sessionmaker[Session],
        clock: Clock,
        on_change: Callable[[str], None] | None = None,
    ) -> None:
        """Create a service over the database `units` open, telling `on_change` of each change."""
        self._units = units
        self._clock = clock
        self._on_change = on_change

    def details(self, track_id: TrackId) -> DetailsView:
        """Return the Track's shown values and every origin's values."""
        with self._units() as db:
            values = values_of(db, track_id)
            if db.get(TrackRow, track_id) is None:
                raise _no_track(track_id)
            video_text = video_text_of(db, track_id)
        found = shown(
            {origin: kept for origin, kept in values.items() if origin is not Origin.HOUSEHOLD}
        )
        return DetailsView(track_id, shown(values), found, values, video_text)

    def read_video_text(self, track_id: TrackId, text: VideoText) -> VideoRead:
        """Read the video's text the household pasted as the Track's `video` values."""
        with self._units.begin() as db:
            reading = record_video_text(db, track_id, text, "household", self._clock())
        self._changed()
        return VideoRead(self.details(track_id), reading.songs)

    def put_household(self, track_id: TrackId, values: Mapping[str, object]) -> DetailsView:
        """Make `values` the household's values for the Track, replacing its earlier ones."""
        checked = check_values(values)
        with self._units.begin() as db:
            set_household(db, track_id, checked, self._clock(), replace=True)
        self._changed()
        return self.details(track_id)

    def set_on_many(self, track_ids: Iterable[TrackId], values: Mapping[str, object | None]) -> int:
        """Set the given household values on every Track; `None` drops one. Return the count.

        Either every Track changes or none does.
        """
        given = {name: value for name, value in values.items() if value is not None}
        checked: dict[Field, Value | None] = dict(check_values(given))
        for name in set(values) - set(given):
            checked[field_named(name)] = None
        ids = list(dict.fromkeys(track_ids))
        if not ids or not checked:
            message = "Choose at least one Track and one detail."
            raise InvalidInputError(message)
        now = self._clock()
        with self._units.begin() as db:
            for track_id in ids:
                set_household(db, track_id, checked, now)
        self._changed()
        return len(ids)

    def _changed(self) -> None:
        if self._on_change is not None:
            self._on_change("catalog")


def _rows(
    track_id: TrackId, origin: Origin, values: Mapping[Field, Value], now: datetime
) -> list[TrackValueRow]:
    return [
        TrackValueRow(track_id=track_id, field=field, origin=origin, value=value, recorded_at=now)
        for field, value in values.items()
    ]


def _require(db: Session, track_id: TrackId) -> None:
    if db.get(TrackRow, track_id) is None:
        raise _no_track(track_id)


def _no_track(track_id: TrackId) -> NotFoundError:
    return NotFoundError(f"No Track has the id {track_id}.")
