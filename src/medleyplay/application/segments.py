"""Splitting a long file into its songs, each a Track playing a stretch of the file.

Saving the editor's rows keeps each song's Track by its id, so a song moved,
renamed, or retimed keeps its ratings, plays, and place in Playlists; a row left
out removes its song's Track. A song's Source has the kind `segment` and names its
album file's Source, so a song plays, and is available, as its file is.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from sqlalchemy import Select, delete, select
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application import Clock
from medleyplay.application.details import refresh, songs_of, video_text_of
from medleyplay.domain.catalog import SourceId, TrackId
from medleyplay.domain.errors import ConflictError, InvalidInputError, NotFoundError
from medleyplay.domain.segments import (
    SEGMENT_SOURCE,
    SegmentId,
    SongRow,
    ends_of,
    needs_check,
    plan_split,
    segment_locator,
)
from medleyplay.domain.video_text import Song, read_video
from medleyplay.persistence.schema import SegmentRow, SourceRow, TrackRow


@dataclass(frozen=True)
class SongView:
    """A song of a split file: its id, its Track, its stretch of the file, and its row."""

    id: SegmentId
    track_id: TrackId
    start_ms: int
    end_ms: int | None
    """Where it ends, or `None` for the last song of a file of unknown length."""
    title: str
    artist: str


@dataclass(frozen=True)
class SongsView:
    """A file's songs, whether its length changed since it was split, and the lists found."""

    track_id: TrackId
    length_ms: int | None
    needs_check: bool
    songs: tuple[SongView, ...]
    found: tuple[tuple[Song, ...], ...]
    """Song lists read from the file's video text, to start from."""


class SongsService:
    """Read, save, and remove the songs a Track's file is split into."""

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

    def songs(self, track_id: TrackId) -> SongsView:
        """Return the file's songs, none when it isn't split, and the lists found for it."""
        with self._units() as db:
            album = _album_file(db, track_id)
            current = songs_of(db, track_id)
            text = video_text_of(db, track_id)
            ends = ends_of([song.start_ms for song in current], album.duration_ms)
            songs = tuple(
                SongView(
                    SegmentId(song.id),
                    TrackId(song.track_id),
                    song.start_ms,
                    end,
                    song.title,
                    song.artist,
                )
                for song, end in zip(current, ends, strict=True)
            )
            split_at = current[0].split_length_ms if current else None
            length = album.duration_ms
        listed = read_video(text).songs if text is not None else ()
        return SongsView(
            track_id, length, needs_check(split_at, length), songs, (listed,) if listed else ()
        )

    def save(self, track_id: TrackId, rows: Sequence[SongRow]) -> SongsView:
        """Make `rows` the file's songs: keep each by its id, add new ones, remove the rest."""
        with self._units.begin() as db:
            album = _album_file(db, track_id)
            existing = {SegmentId(song.id): song for song in songs_of(db, track_id)}
            plan = plan_split(existing, rows, album.duration_ms)
            if plan.removed:
                removed = [existing[gone].track_id for gone in plan.removed]
                for gone in plan.removed:
                    # Gone from the session too, so a new song can't meet its stale row.
                    db.expunge(existing[gone])
                db.execute(delete(TrackRow).where(TrackRow.id.in_(removed)))
            for song_id, place, song in plan.kept:
                _set_row(existing[song_id], place, song)
            source_id = (
                next(iter(existing.values())).album_source_id
                if existing
                else _first_source(db, track_id)
            )
            for place, song in plan.added:
                _add_song(db, album, SourceId(source_id), place, song)
            db.flush()
            self._settle(db, album)
        self._changed()
        return self.songs(track_id)

    def unsplit(self, track_id: TrackId) -> int:
        """Remove every song of the file, with its Track; return how many there were."""
        with self._units.begin() as db:
            _album_file(db, track_id)
            removed = [song.track_id for song in songs_of(db, track_id)]
            db.execute(delete(TrackRow).where(TrackRow.id.in_(removed)))
        if removed:
            self._changed()
        return len(removed)

    def _settle(self, db: Session, album: TrackRow) -> None:
        # The file's length now, and each song's length and details from its row and place.
        for song in songs_of(db, TrackId(album.id)):
            song.split_length_ms = album.duration_ms
        refresh(db, TrackId(album.id), self._clock())

    def _changed(self) -> None:
        if self._on_change is not None:
            self._on_change("catalog")


def album_file_of(db: Session) -> dict[TrackId, TrackId]:
    """Return the album file of every song, each song's Track to its file's."""
    rows = db.execute(
        select(SegmentRow.track_id, SourceRow.track_id).join(
            SourceRow, SourceRow.id == SegmentRow.album_source_id
        )
    )
    return {TrackId(song): TrackId(album) for song, album in rows.all()}


def drop_songs(db: Session, source_ids: Select[tuple[int]]) -> None:
    """Remove the songs split from the Sources `source_ids` selects, with their Tracks."""
    songs = select(SegmentRow.track_id).where(SegmentRow.album_source_id.in_(source_ids))
    db.execute(delete(TrackRow).where(TrackRow.id.in_(songs)))


def _album_file(db: Session, track_id: TrackId) -> TrackRow:
    track = db.get(TrackRow, track_id)
    if track is None:
        message = f"No Track has the id {track_id}."
        raise NotFoundError(message)
    if db.scalar(select(SegmentRow.id).where(SegmentRow.track_id == track_id)) is not None:
        message = f"Track {track_id} is a song of another file; split that file instead."
        raise ConflictError(message)
    return track


def _first_source(db: Session, track_id: TrackId) -> int:
    found = db.scalar(
        select(SourceRow.id).where(SourceRow.track_id == track_id).order_by(SourceRow.id)
    )
    if found is None:
        message = f"Track {track_id} has no file to split."
        raise InvalidInputError(message)
    return found


def _set_row(row: SegmentRow, place: int, song: Song) -> None:
    row.position = place
    row.start_ms = song.start_ms
    row.title = song.title
    row.artist = song.artist


def _add_song(db: Session, album: TrackRow, source_id: SourceId, place: int, song: Song) -> None:
    # A song was added when its album file was.
    track = TrackRow(title=song.title, added_at=album.added_at)
    db.add(track)
    db.flush()
    row = SegmentRow(album_source_id=source_id, track_id=track.id)
    _set_row(row, place, song)
    db.add(row)
    db.flush()
    locator = segment_locator(source_id, SegmentId(row.id))
    db.add(SourceRow(track_id=track.id, kind=SEGMENT_SOURCE, locator=locator))
