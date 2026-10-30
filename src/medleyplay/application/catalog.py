"""The catalog: adding Tracks by their Source, each Account's favorites and ratings, Playlists.

Every command here is idempotent: repeating it leaves the same state as doing it once.
"""

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import datetime

from sqlalchemy import Select, case, delete, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application import Clock
from medleyplay.application.builtin_playlists import ensure_builtin_playlists
from medleyplay.application.changes import OnChange
from medleyplay.application.details import record as record_details
from medleyplay.application.rule_schema import read_rules, rules_document
from medleyplay.application.segments import album_file_of
from medleyplay.application.track_facts import track_facts
from medleyplay.domain.accounts import AccountId
from medleyplay.domain.catalog import (
    Availability,
    Builtin,
    Playlist,
    PlaylistId,
    SourceKey,
    SourceState,
    Track,
    TrackDetails,
    TrackId,
    check_playlist_length,
    check_rating,
    parse_playlist_name,
    source_availability,
    track_availability,
)
from medleyplay.domain.details import Field, Origin, Value
from medleyplay.domain.errors import ConflictError, InvalidInputError, NotFoundError
from medleyplay.domain.libraries import LIBRARY_SOURCE, LibraryState, library_of_locator
from medleyplay.domain.playback import PlayId
from medleyplay.domain.rules import Rules, matches
from medleyplay.domain.segments import SEGMENT_SOURCE, parse_segment_locator
from medleyplay.persistence.schema import (
    DownloadRow,
    LibraryRow,
    PlaylistEntryRow,
    PlaylistRow,
    PlayRow,
    SourceRow,
    TrackRow,
    TrackStateRow,
)


class CatalogService:
    """Read and change the catalog as one Account sees it."""

    def __init__(
        self,
        units: sessionmaker[Session],
        clock: Clock,
        on_change: OnChange | None = None,
        online: Callable[[], bool] = lambda: True,
    ) -> None:
        """Create a service over the database `units` open, telling `on_change` what it changed.

        `online` says whether the Mode is Online, which a Track to download waits for.
        """
        self._units = units
        self._clock = clock
        self._on_change = on_change
        self._online = online

    def add_track(
        self,
        key: SourceKey,
        details: TrackDetails,
        source_details: Mapping[str, object] | None = None,
        origin: Origin = Origin.VIDEO,
    ) -> TrackId:
        """Return the Track for a Source, creating both when the Source is new.

        A Source that already exists returns its Track unchanged, `source_details`
        included, so adding the same link or file twice never makes a second Track.
        The new Track's details are recorded as `origin`'s: a site Track's are its
        video's.
        """
        existing = self._track_of(key)
        if existing is not None:
            return existing
        try:
            with self._units.begin() as db:
                now = self._clock()
                track = TrackRow(title=details.title, duration_ms=details.duration_ms, added_at=now)
                db.add(track)
                db.flush()
                given: dict[Field, Value | None] = {
                    Field.TITLE: details.title,
                    Field.ARTIST: details.artist,
                    Field.ALBUM: details.album,
                    Field.ALBUM_ARTIST: details.album_artist,
                    Field.TRACK_NUMBER: details.track_number,
                    Field.DISC_NUMBER: details.disc_number,
                    Field.YEAR: details.year,
                    Field.GENRE: details.genre,
                }
                values = {field: value for field, value in given.items() if value is not None}
                record_details(db, TrackId(track.id), origin, values, now)
                db.add(
                    SourceRow(
                        track_id=track.id,
                        kind=key.kind,
                        locator=key.locator,
                        details=dict(source_details or {}),
                    )
                )
                added = TrackId(track.id)
        except IntegrityError:
            # Another request added the same Source between the lookup and the insert.
            raced = self._track_of(key)
            if raced is None:
                raise
            return raced
        self._changed("catalog")
        return added

    def list_tracks(self, account_id: AccountId) -> list[Track]:
        """Return every Track, oldest first, with `account_id`'s own state."""
        with self._units() as db:
            rows = db.execute(_tracks_for(account_id).order_by(TrackRow.id)).all()
            available = _availability(db, select(SourceRow), online=self._online())
            downloaded = _downloaded(db, select(SourceRow.track_id))
            segment_of = album_file_of(db)
            split = set(segment_of.values())
            return [
                _to_track(
                    track,
                    state,
                    available[track.id],
                    downloaded=track.id in downloaded,
                    segment_of=segment_of.get(track.id),
                    split=track.id in split,
                )
                for track, state in rows
            ]

    def get_track(self, account_id: AccountId, track_id: TrackId) -> Track:
        """Return one Track with `account_id`'s own state."""
        with self._units() as db:
            found = db.execute(_tracks_for(account_id).where(TrackRow.id == track_id)).one_or_none()
            if found is None:
                raise _no_track(track_id)
            available = _availability(
                db, select(SourceRow).where(SourceRow.track_id == track_id), online=self._online()
            )
            downloaded = _downloaded(
                db, select(SourceRow.track_id).where(SourceRow.track_id == track_id)
            )
            segment_of = album_file_of(db)
        return _to_track(
            *found,
            available[track_id],
            downloaded=track_id in downloaded,
            segment_of=segment_of.get(track_id),
            split=track_id in segment_of.values(),
        )

    def set_favorite(self, account_id: AccountId, track_id: TrackId, *, favorite: bool) -> Track:
        """Mark or unmark a Track as one of `account_id`'s favorites."""
        self._upsert_state(account_id, track_id, favorite=favorite)
        return self.get_track(account_id, track_id)

    def set_rating(self, account_id: AccountId, track_id: TrackId, rating: int | None) -> Track:
        """Give a Track 1-5 stars from `account_id`, or clear the rating with `None`."""
        check_rating(rating)
        self._upsert_state(account_id, track_id, rating=rating)
        return self.get_track(account_id, track_id)

    def record_play(
        self, account_id: AccountId, play_id: PlayId, track_id: TrackId, played_at: datetime
    ) -> Track:
        """Record that `account_id` played a Track at `played_at`, no later than now.

        The id is the client's own choice, so sending a play again changes nothing;
        sending its id with another Track is refused.
        """
        when = min(played_at, self._clock())
        recorded_now = False
        try:
            with self._units.begin() as db:
                if db.get(TrackRow, track_id) is None:
                    raise _no_track(track_id)
                recorded = db.get(PlayRow, (account_id, play_id))
                if recorded is None:
                    db.add(
                        PlayRow(
                            account_id=account_id, id=play_id, track_id=track_id, played_at=when
                        )
                    )
                    db.flush()
                    _count_play(db, account_id, track_id, when)
                    recorded_now = True
                elif recorded.track_id != track_id:
                    raise _another_track(play_id)
        except IntegrityError:
            # The same play arrived twice at once, and the other request recorded it.
            with self._units() as db:
                raced = db.get(PlayRow, (account_id, play_id))
            if raced is None:
                raise
            if raced.track_id != track_id:
                raise _another_track(play_id) from None
        if recorded_now:
            self._changed("catalog")
        return self.get_track(account_id, track_id)

    def put_playlist(
        self,
        account_id: AccountId,
        playlist_id: PlaylistId,
        name: str,
        track_ids: Sequence[TrackId] | None = None,
        *,
        rules: Rules | None = None,
        keep_downloaded: bool = False,
    ) -> tuple[Playlist, bool]:
        """Create or replace a Playlist under a client-chosen id; return it and whether it is new.

        A plain Playlist has `track_ids`, a smart one `rules`, never both. Sending
        the same Playlist again changes nothing, not even its update time. An id
        that belongs to another Account is refused.
        """
        if track_ids is not None and rules is not None:
            message = "A Playlist has Tracks or rules, not both."
            raise InvalidInputError(message)
        clean_name, entries = parse_playlist_name(name), tuple(track_ids or ())
        check_playlist_length(entries)
        document = None if rules is None else rules_document(rules)
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
            elif row.builtin is not None:
                message = (
                    f"{row.name} is kept by the server; only its Keep downloaded switch changes."
                )
                raise ConflictError(message)
            wanted = (clean_name, entries, document, keep_downloaded)
            changed = created or _stored(db, row) != wanted
            if changed:
                row.name, row.rules, row.keep_downloaded = clean_name, document, keep_downloaded
                row.updated_at = self._clock()
                db.flush()
                db.execute(delete(PlaylistEntryRow).where(PlaylistEntryRow.playlist_id == row.id))
                db.add_all(
                    PlaylistEntryRow(playlist_id=row.id, position=position, track_id=track_id)
                    for position, track_id in enumerate(entries)
                )
            db.flush()
            saved = _to_playlist(db, row, self._clock()), created
        if changed:
            self._changed("catalog")
        return saved

    def ensure_builtin_playlists(self) -> None:
        """Give every Account the built-in Playlists it doesn't have, such as Favorites."""
        with self._units.begin() as db:
            ensure_builtin_playlists(db, self._clock())

    def set_keep_downloaded(
        self, account_id: AccountId, playlist_id: PlaylistId, *, keep: bool
    ) -> Playlist:
        """Switch whether one of `account_id`'s Playlists keeps its Tracks downloaded.

        Any Playlist's switch changes this way, Favorites' included; switching it to
        what it is changes nothing.
        """
        with self._units.begin() as db:
            row = _owned_playlist(db, account_id, playlist_id)
            changed = row.keep_downloaded != keep
            if changed:
                row.keep_downloaded = keep
                row.updated_at = self._clock()
                db.flush()
            saved = _to_playlist(db, row, self._clock())
        if changed:
            self._changed("catalog")
        return saved

    def list_playlists(self, account_id: AccountId) -> list[Playlist]:
        """Return `account_id`'s Playlists: the built-in ones first, then the rest by name."""
        with self._units() as db:
            rows = db.scalars(
                select(PlaylistRow)
                .where(PlaylistRow.account_id == account_id)
                .order_by(PlaylistRow.builtin.is_(None), PlaylistRow.name, PlaylistRow.id)
            ).all()
            return [_to_playlist(db, row, self._clock()) for row in rows]

    def get_playlist(self, account_id: AccountId, playlist_id: PlaylistId) -> Playlist:
        """Return one of `account_id`'s Playlists; another Account's is not found."""
        with self._units() as db:
            return _to_playlist(db, _owned_playlist(db, account_id, playlist_id), self._clock())

    def delete_playlist(self, account_id: AccountId, playlist_id: PlaylistId) -> None:
        """Delete one of `account_id`'s Playlists; deleting a missing one does nothing.

        A built-in Playlist, such as Favorites, can't be deleted.
        """
        with self._units.begin() as db:
            deleted = (
                db.connection()
                .execute(
                    delete(PlaylistRow).where(
                        PlaylistRow.id == playlist_id,
                        PlaylistRow.account_id == account_id,
                        PlaylistRow.builtin.is_(None),
                    )
                )
                .rowcount
            )
            kept = None if deleted else db.get(PlaylistRow, playlist_id)
            if kept is not None and kept.account_id == account_id:
                message = f"{kept.name} is kept by the server and can't be deleted."
                raise ConflictError(message)
        if deleted:
            self._changed("catalog")

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
        self._changed("catalog")

    def _changed(self, what: str) -> None:
        if self._on_change is not None:
            self._on_change(what)


def _tracks_for(account_id: AccountId) -> Select[TrackRow, TrackStateRow]:
    # An outer join: the state is None for a Track this Account has never touched.
    return select(TrackRow, TrackStateRow).outerjoin(
        TrackStateRow,
        (TrackStateRow.track_id == TrackRow.id) & (TrackStateRow.account_id == account_id),
    )


def _count_play(db: Session, account_id: AccountId, track_id: TrackId, when: datetime) -> None:
    played = insert(TrackStateRow).values(
        account_id=account_id, track_id=track_id, play_count=1, last_played_at=when
    )
    # A play recorded late, such as from a device that was away, keeps a later play the latest.
    latest = case(
        (
            TrackStateRow.last_played_at.is_(None)
            | (TrackStateRow.last_played_at < played.excluded.last_played_at),
            played.excluded.last_played_at,
        ),
        else_=TrackStateRow.last_played_at,
    )
    db.execute(
        played.on_conflict_do_update(
            index_elements=["account_id", "track_id"],
            set_={"play_count": TrackStateRow.play_count + 1, "last_played_at": latest},
        )
    )


def _availability(
    db: Session, sources: Select[SourceRow], *, online: bool
) -> defaultdict[int, Availability]:
    # A Library's Source can play only while its Library is online; another kind must
    # be downloaded, which waits while the Mode is Offline. A Source with a Download
    # plays it, whatever its state. A song plays as its album file's Source does.
    mounted = {row.id: row.state == LibraryState.ONLINE for row in db.scalars(select(LibraryRow))}
    downloaded = set(db.scalars(select(DownloadRow.source_id)))

    def of(source: SourceRow) -> Availability:
        if source.id in downloaded:
            return Availability.OK
        if source.kind != LIBRARY_SOURCE:
            state = source_availability(SourceState(source.state), online=True)
            return Availability.WAITING_ONLINE if state is Availability.OK and not online else state
        reachable = mounted.get(library_of_locator(source.locator), False)
        return source_availability(SourceState(source.state), online=reachable)

    rows = list(db.scalars(sources))
    album_of = {
        row.id: parse_segment_locator(row.locator)[0] for row in rows if row.kind == SEGMENT_SOURCE
    }
    albums = {
        row.id: row
        for row in db.scalars(select(SourceRow).where(SourceRow.id.in_(set(album_of.values()))))
    }
    per_track: defaultdict[int, list[Availability]] = defaultdict(list)
    for source in rows:
        if source.kind == SEGMENT_SOURCE:
            album = albums.get(album_of[source.id])
            per_track[source.track_id].append(Availability.MISSING if album is None else of(album))
        else:
            per_track[source.track_id].append(of(source))
    found: defaultdict[int, Availability] = defaultdict(lambda: Availability.MISSING)
    found.update({track: track_availability(each) for track, each in per_track.items()})
    return found


def _downloaded(db: Session, track_ids: Select[int]) -> set[int]:
    # A Track is downloaded while a Download row holds one of its Sources; a cache copy
    # of a zip member doesn't count.
    held = track_ids.join(DownloadRow, DownloadRow.source_id == SourceRow.id)
    return set(db.scalars(held))


def _to_track(
    track: TrackRow,
    state: TrackStateRow | None,
    availability: Availability,
    *,
    downloaded: bool,
    segment_of: int | None = None,
    split: bool = False,
) -> Track:
    return Track(
        id=TrackId(track.id),
        details=TrackDetails(
            title=track.title,
            artist=track.artist,
            album=track.album,
            album_artist=track.album_artist,
            duration_ms=track.duration_ms,
            track_number=track.track_number,
            disc_number=track.disc_number,
            year=track.year,
            genre=track.genre,
        ),
        added_at=track.added_at,
        favorite=state is not None and state.favorite,
        rating=None if state is None else state.rating,
        play_count=0 if state is None else state.play_count,
        last_played_at=None if state is None else state.last_played_at,
        availability=availability,
        downloaded=downloaded,
        segment_of=None if segment_of is None else TrackId(segment_of),
        split=split,
    )


def _another_track(play_id: PlayId) -> ConflictError:
    return ConflictError(f"The play {play_id} was of another Track.")


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


def _stored(db: Session, row: PlaylistRow) -> tuple[object, ...]:
    return (row.name, _entries_of(db, PlaylistId(row.id)), row.rules, row.keep_downloaded)


def _owned_playlist(db: Session, account_id: AccountId, playlist_id: PlaylistId) -> PlaylistRow:
    """Return one of `account_id`'s Playlists; another Account's is not found."""
    row = db.get(PlaylistRow, playlist_id)
    if row is None or row.account_id != account_id:
        message = f"No Playlist has the id {playlist_id}."
        raise NotFoundError(message)
    return row


def _to_playlist(db: Session, row: PlaylistRow, now: datetime) -> Playlist:
    playlist_id = PlaylistId(row.id)
    playlist = Playlist(
        playlist_id,
        row.name,
        _entries_of(db, playlist_id),
        row.updated_at,
        keep_downloaded=row.keep_downloaded,
        builtin=None if row.builtin is None else Builtin(row.builtin),
    )
    if row.rules is None:
        return playlist
    try:
        rules = read_rules(row.rules)
    except InvalidInputError as error:
        return replace(playlist, unreadable=str(error))
    matched = _matching(db, AccountId(row.account_id), rules, now)
    return replace(playlist, rules=rules, track_ids=matched)


def _matching(
    db: Session, account_id: AccountId, rules: Rules, now: datetime
) -> tuple[TrackId, ...]:
    """Return the Tracks `rules` match as `account_id` sees them, newest added first."""
    facts = track_facts(db, account_id)
    matched = [track_id for track_id, each in facts.items() if matches(rules, each, now)]
    return tuple(
        sorted(matched, key=lambda track_id: (facts[track_id].added_at, track_id), reverse=True)
    )
