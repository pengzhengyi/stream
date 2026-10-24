"""The catalog: adding Tracks by their Source, each Account's favorites and ratings, Playlists.

Every command here is idempotent: repeating it leaves the same state as doing it once.
"""

from collections.abc import Sequence

from sqlalchemy import Select, delete, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application import Clock
from medleyplay.domain.accounts import AccountId
from medleyplay.domain.catalog import (
    Playlist,
    PlaylistId,
    SourceKey,
    Track,
    TrackDetails,
    TrackId,
    check_playlist_length,
    check_rating,
    parse_playlist_name,
)
from medleyplay.domain.errors import ConflictError, InvalidInputError, NotFoundError
from medleyplay.persistence.schema import (
    PlaylistEntryRow,
    PlaylistRow,
    SourceRow,
    TrackRow,
    TrackStateRow,
)


class CatalogService:
    """Read and change the catalog as one Account sees it."""

    def __init__(self, units: sessionmaker[Session], clock: Clock) -> None:
        """Create a service over the database `units` open."""
        self._units = units
        self._clock = clock

    def add_track(self, key: SourceKey, details: TrackDetails) -> TrackId:
        """Return the Track for a Source, creating both when the Source is new.

        A Source that already exists returns its Track unchanged, so adding the same
        link or file twice never makes a second Track.
        """
        existing = self._track_of(key)
        if existing is not None:
            return existing
        try:
            with self._units.begin() as db:
                track = TrackRow(
                    title=details.title,
                    artist=details.artist,
                    album=details.album,
                    album_artist=details.album_artist,
                    duration_ms=details.duration_ms,
                    added_at=self._clock(),
                )
                db.add(track)
                db.flush()
                db.add(SourceRow(track_id=track.id, kind=key.kind, locator=key.locator))
                return TrackId(track.id)
        except IntegrityError:
            # Another request added the same Source between the lookup and the insert.
            raced = self._track_of(key)
            if raced is None:
                raise
            return raced

    def list_tracks(self, account_id: AccountId) -> list[Track]:
        """Return every Track, oldest first, with `account_id`'s own state."""
        with self._units() as db:
            rows = db.execute(_tracks_for(account_id).order_by(TrackRow.id))
            return [_to_track(track, state) for track, state in rows]

    def get_track(self, account_id: AccountId, track_id: TrackId) -> Track:
        """Return one Track with `account_id`'s own state."""
        with self._units() as db:
            found = db.execute(_tracks_for(account_id).where(TrackRow.id == track_id)).one_or_none()
        if found is None:
            raise _no_track(track_id)
        return _to_track(*found)

    def set_favorite(self, account_id: AccountId, track_id: TrackId, *, favorite: bool) -> Track:
        """Mark or unmark a Track as one of `account_id`'s favorites."""
        self._upsert_state(account_id, track_id, favorite=favorite)
        return self.get_track(account_id, track_id)

    def set_rating(self, account_id: AccountId, track_id: TrackId, rating: int | None) -> Track:
        """Give a Track 1-5 stars from `account_id`, or clear the rating with `None`."""
        check_rating(rating)
        self._upsert_state(account_id, track_id, rating=rating)
        return self.get_track(account_id, track_id)

    def put_playlist(
        self,
        account_id: AccountId,
        playlist_id: PlaylistId,
        name: str,
        track_ids: Sequence[TrackId],
    ) -> tuple[Playlist, bool]:
        """Create or replace a Playlist under a client-chosen id; return it and whether it is new.

        Sending the same Playlist again changes nothing, not even its update time.
        An id that belongs to another Account is refused.
        """
        clean_name, entries = parse_playlist_name(name), tuple(track_ids)
        check_playlist_length(entries)
        with self._units.begin() as db:
            _check_tracks_exist(db, entries)
            row = db.get(PlaylistRow, playlist_id)
            created = row is None
            if row is None:
                now = self._clock()
                row = PlaylistRow(
                    id=playlist_id, account_id=account_id, name=clean_name, created_at=now
                )
                db.add(row)
            elif row.account_id != account_id:
                message = f"The Playlist id {playlist_id} is already in use."
                raise ConflictError(message)
            if created or (row.name, _entries_of(db, playlist_id)) != (clean_name, entries):
                row.name = clean_name
                row.updated_at = self._clock()
                db.flush()
                db.execute(delete(PlaylistEntryRow).where(PlaylistEntryRow.playlist_id == row.id))
                db.add_all(
                    PlaylistEntryRow(playlist_id=row.id, position=position, track_id=track_id)
                    for position, track_id in enumerate(entries)
                )
            return Playlist(playlist_id, row.name, entries, row.updated_at), created

    def list_playlists(self, account_id: AccountId) -> list[Playlist]:
        """Return `account_id`'s Playlists by name."""
        with self._units() as db:
            rows = db.scalars(
                select(PlaylistRow)
                .where(PlaylistRow.account_id == account_id)
                .order_by(PlaylistRow.name, PlaylistRow.id)
            ).all()
            return [_to_playlist(db, row) for row in rows]

    def get_playlist(self, account_id: AccountId, playlist_id: PlaylistId) -> Playlist:
        """Return one of `account_id`'s Playlists; another Account's is not found."""
        with self._units() as db:
            row = db.get(PlaylistRow, playlist_id)
            if row is None or row.account_id != account_id:
                message = f"No Playlist has the id {playlist_id}."
                raise NotFoundError(message)
            return _to_playlist(db, row)

    def delete_playlist(self, account_id: AccountId, playlist_id: PlaylistId) -> None:
        """Delete one of `account_id`'s Playlists; deleting a missing one does nothing."""
        with self._units.begin() as db:
            db.execute(
                delete(PlaylistRow).where(
                    PlaylistRow.id == playlist_id, PlaylistRow.account_id == account_id
                )
            )

    def _track_of(self, key: SourceKey) -> TrackId | None:
        with self._units() as db:
            found = db.scalar(
                select(SourceRow.track_id).where(
                    SourceRow.kind == key.kind, SourceRow.locator == key.locator
                )
            )
        return None if found is None else TrackId(found)

    def _upsert_state(self, account_id: AccountId, track_id: TrackId, **values: object) -> None:
        with self._units.begin() as db:
            if db.get(TrackRow, track_id) is None:
                raise _no_track(track_id)
            db.execute(
                insert(TrackStateRow)
                .values(account_id=account_id, track_id=track_id, **values)
                .on_conflict_do_update(index_elements=["account_id", "track_id"], set_=values)
            )


def _tracks_for(account_id: AccountId) -> Select[TrackRow, TrackStateRow]:
    # An outer join: the state is None for a Track this Account has never touched.
    return select(TrackRow, TrackStateRow).outerjoin(
        TrackStateRow,
        (TrackStateRow.track_id == TrackRow.id) & (TrackStateRow.account_id == account_id),
    )


def _to_track(track: TrackRow, state: TrackStateRow | None) -> Track:
    return Track(
        id=TrackId(track.id),
        details=TrackDetails(
            title=track.title,
            artist=track.artist,
            album=track.album,
            album_artist=track.album_artist,
            duration_ms=track.duration_ms,
        ),
        added_at=track.added_at,
        favorite=state is not None and state.favorite,
        rating=None if state is None else state.rating,
        play_count=0 if state is None else state.play_count,
        last_played_at=None if state is None else state.last_played_at,
    )


def _no_track(track_id: TrackId) -> NotFoundError:
    return NotFoundError(f"No Track has the id {track_id}.")


def _check_tracks_exist(db: Session, track_ids: tuple[TrackId, ...]) -> None:
    wanted = set(track_ids)
    found = set(db.scalars(select(TrackRow.id).where(TrackRow.id.in_(wanted))))
    if missing := sorted(wanted - found):
        message = f"No Tracks have the ids {missing}."
        raise InvalidInputError(message)


def _entries_of(db: Session, playlist_id: PlaylistId) -> tuple[TrackId, ...]:
    return tuple(
        TrackId(track_id)
        for track_id in db.scalars(
            select(PlaylistEntryRow.track_id)
            .where(PlaylistEntryRow.playlist_id == playlist_id)
            .order_by(PlaylistEntryRow.position)
        )
    )


def _to_playlist(db: Session, row: PlaylistRow) -> Playlist:
    playlist_id = PlaylistId(row.id)
    return Playlist(playlist_id, row.name, _entries_of(db, playlist_id), row.updated_at)
