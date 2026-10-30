"""Splitting one long file into its songs: each a Track, kept across edits, until unsplit."""

from datetime import timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application.accounts import AccountService
from medleyplay.application.catalog import CatalogService
from medleyplay.application.details import DetailsService
from medleyplay.application.segments import SongsService, SongView
from medleyplay.domain.accounts import Account
from medleyplay.domain.catalog import Availability, SourceState, TrackId
from medleyplay.domain.details import Field, Origin, Shown
from medleyplay.domain.errors import ConflictError, InvalidInputError, NotFoundError
from medleyplay.domain.segments import SongRow
from medleyplay.domain.video_text import Song, VideoText
from medleyplay.persistence.schema import DownloadRow, SourceRow, TrackRow, TrackValueRow
from tests.support.factories import NewAccountFactory, SourceKeyFactory, TrackDetailsFactory
from tests.support.fakes import FakeClock

THREE_SONGS = (
    SongRow(None, Song(0, "アイネクライネ")),
    SongRow(None, Song(252_000, "ゴーゴー幽霊船", "米津玄師")),
    SongRow(None, Song(480_000, "Last")),
)
"""A first split of *Bremen*: three new songs, the second naming its own artist."""


@pytest.fixture
def alice(accounts: AccountService) -> Account:
    return accounts.create_first_admin(NewAccountFactory.admin()).account


@pytest.fixture
def album(catalog: CatalogService) -> TrackId:
    """*Bremen*, a whole album uploaded as one hour-long video."""
    return catalog.add_track(
        SourceKeyFactory.bilibili("BV1dm4y1s7ak"), TrackDetailsFactory.album_file()
    )


def _kept(songs: tuple[SongView, ...], *titles: str) -> list[SongRow]:
    """The rows of `songs` with the titles `titles`, each keeping its song."""
    return [
        SongRow(song.id, Song(song.start_ms, song.title, song.artist))
        for song in songs
        if song.title in titles
    ]


def test_a_first_split_makes_a_track_of_each_song(songs: SongsService, album: TrackId) -> None:
    view = songs.save(album, THREE_SONGS)

    assert [(song.start_ms, song.end_ms, song.title) for song in view.songs] == [
        (0, 252_000, "アイネクライネ"),
        (252_000, 480_000, "ゴーゴー幽霊船"),
        (480_000, 3_600_000, "Last"),
    ]
    assert len({song.track_id for song in view.songs}) == 3


def test_a_song_takes_its_album_fields_from_its_album_file_and_its_place(
    songs: SongsService, details: DetailsService, album: TrackId
) -> None:
    second = songs.save(album, THREE_SONGS).songs[1]

    shown = details.details(second.track_id).shown

    assert shown[Field.TITLE] == Shown("ゴーゴー幽霊船", Origin.ALBUM_FILE)
    assert shown[Field.ARTIST] == Shown("米津玄師", Origin.ALBUM_FILE)
    assert shown[Field.ALBUM] == Shown("Bremen", Origin.ALBUM_FILE)
    assert shown[Field.ALBUM_ARTIST] == Shown("ハチ", Origin.ALBUM_FILE)
    assert shown[Field.TRACK_NUMBER] == Shown(2, Origin.ALBUM_FILE)
    assert shown[Field.YEAR] == Shown(2015, Origin.ALBUM_FILE)


def test_a_song_with_no_artist_of_its_own_is_the_album_artists(
    songs: SongsService, details: DetailsService, album: TrackId
) -> None:
    first = songs.save(album, THREE_SONGS).songs[0]

    assert details.details(first.track_id).shown[Field.ARTIST] == Shown("ハチ", Origin.ALBUM_FILE)


def test_a_change_to_the_album_files_details_reaches_its_songs(
    songs: SongsService, details: DetailsService, album: TrackId
) -> None:
    first = songs.save(album, THREE_SONGS).songs[0]

    details.put_household(album, {"album": "Bremen (Deluxe)"})

    shown = details.details(first.track_id).shown[Field.ALBUM]
    assert shown == Shown("Bremen (Deluxe)", Origin.ALBUM_FILE)


def test_a_songs_length_is_its_stretch_of_the_file(
    songs: SongsService, catalog: CatalogService, album: TrackId, alice: Account
) -> None:
    last = songs.save(album, THREE_SONGS).songs[2]

    assert catalog.get_track(alice.id, last.track_id).details.duration_ms == 3_120_000


def test_a_song_inserted_in_the_middle_keeps_every_other_songs_track(
    songs: SongsService, catalog: CatalogService, album: TrackId, alice: Account
) -> None:
    before = songs.save(album, THREE_SONGS).songs
    catalog.set_rating(alice.id, before[1].track_id, 5)
    rows = [
        SongRow(before[0].id, Song(0, "アイネクライネ")),
        SongRow(None, Song(120_000, "Interlude")),
        SongRow(before[1].id, Song(252_000, "ゴーゴー幽霊船", "米津玄師")),
        SongRow(before[2].id, Song(480_000, "Last")),
    ]

    after = songs.save(album, rows).songs

    assert [song.track_id for song in after[::2]] == [before[0].track_id, before[1].track_id]
    assert catalog.get_track(alice.id, before[1].track_id).rating == 5
    assert catalog.get_track(alice.id, before[1].track_id).details.track_number == 3


def test_a_song_left_out_of_the_rows_is_removed_with_its_track(
    songs: SongsService, catalog: CatalogService, album: TrackId, alice: Account
) -> None:
    before = songs.save(album, THREE_SONGS).songs

    after = songs.save(album, _kept(before, "アイネクライネ", "Last")).songs

    assert [song.title for song in after] == ["アイネクライネ", "Last"]
    with pytest.raises(NotFoundError):
        catalog.get_track(alice.id, before[1].track_id)


def test_unsplitting_removes_every_song(
    songs: SongsService, catalog: CatalogService, album: TrackId, alice: Account
) -> None:
    split = songs.save(album, THREE_SONGS).songs

    removed = songs.unsplit(album)

    assert removed == 3
    assert songs.songs(album).songs == ()
    assert [track.id for track in catalog.list_tracks(alice.id)] == [album]
    assert all(song.track_id != album for song in split)


def test_track_lists_say_which_file_is_split_and_which_file_a_song_is_of(
    songs: SongsService, catalog: CatalogService, album: TrackId, alice: Account
) -> None:
    first = songs.save(album, THREE_SONGS).songs[0]

    tracks = {track.id: track for track in catalog.list_tracks(alice.id)}

    assert tracks[album].split
    assert tracks[album].segment_of is None
    assert tracks[first.track_id].segment_of == album
    assert not tracks[first.track_id].split
    assert catalog.get_track(alice.id, first.track_id).segment_of == album


def test_a_song_can_play_while_its_album_file_can(
    songs: SongsService,
    catalog: CatalogService,
    album: TrackId,
    alice: Account,
    units: sessionmaker[Session],
) -> None:
    first = songs.save(album, THREE_SONGS).songs[0]
    assert catalog.get_track(alice.id, first.track_id).availability is Availability.OK

    with units.begin() as db:
        db.execute(
            update(SourceRow)
            .where(SourceRow.track_id == album)
            .values(state=SourceState.UNAVAILABLE)
        )

    assert catalog.get_track(alice.id, first.track_id).availability is Availability.UNAVAILABLE
    listed = {track.id: track for track in catalog.list_tracks(alice.id)}
    assert listed[first.track_id].availability is Availability.UNAVAILABLE


def test_the_songs_listed_in_the_videos_text_are_found(
    songs: SongsService, details: DetailsService, album: TrackId
) -> None:
    details.read_video_text(
        album,
        VideoText(
            "ハチ 全专《Bremen》",
            """\
00:00 アイネクライネ
04:12 ゴーゴー幽霊船
08:00 Last
""",
        ),
    )

    found = songs.songs(album).found

    assert found == (
        (Song(0, "アイネクライネ"), Song(252_000, "ゴーゴー幽霊船"), Song(480_000, "Last")),
    )


def test_a_split_file_needs_checking_once_its_length_changes(
    songs: SongsService, album: TrackId, units: sessionmaker[Session]
) -> None:
    songs.save(album, THREE_SONGS)

    with units.begin() as db:
        db.execute(update(TrackRow).where(TrackRow.id == album).values(duration_ms=3_000_000))

    assert songs.songs(album).needs_check


def test_rows_naming_a_song_of_another_file_are_refused(
    songs: SongsService, catalog: CatalogService, album: TrackId
) -> None:
    other = catalog.add_track(
        SourceKeyFactory.bilibili("BV1Other"), TrackDetailsFactory.album_file()
    )
    theirs = songs.save(other, THREE_SONGS).songs[0]

    with pytest.raises(InvalidInputError):
        songs.save(album, [SongRow(theirs.id, Song(0, "A")), *THREE_SONGS[1:]])


def test_a_song_is_not_split_itself(songs: SongsService, album: TrackId) -> None:
    first = songs.save(album, THREE_SONGS).songs[0]

    with pytest.raises(ConflictError, match="song of"):
        songs.save(first.track_id, [SongRow(None, Song(0, "A")), SongRow(None, Song(5_000, "B"))])


def test_the_songs_of_a_missing_track_are_not_found(songs: SongsService) -> None:
    with pytest.raises(NotFoundError):
        songs.songs(TrackId(999))


def test_a_song_added_as_the_last_is_removed_gets_an_id_of_its_own(
    songs: SongsService, album: TrackId
) -> None:
    before = songs.save(album, THREE_SONGS).songs
    rows = [
        *_kept(before, "アイネクライネ", "ゴーゴー幽霊船"),
        SongRow(None, Song(600_000, "Encore")),
    ]

    added = songs.save(album, rows).songs[2]

    assert added.id not in {song.id for song in before}


def test_an_album_file_change_its_songs_dont_take_leaves_their_values_as_they_were(
    songs: SongsService,
    details: DetailsService,
    album: TrackId,
    clock: FakeClock,
    units: sessionmaker[Session],
) -> None:
    first = songs.save(album, THREE_SONGS).songs[0]
    clock.advance(timedelta(days=1))

    details.put_household(album, {"title": "Bremen (Live)"})

    with units() as db:
        recorded = set(
            db.scalars(
                select(TrackValueRow.recorded_at).where(TrackValueRow.track_id == first.track_id)
            )
        )
    assert recorded == {clock() - timedelta(days=1)}


def test_a_song_is_downloaded_while_its_album_file_is(
    songs: SongsService,
    catalog: CatalogService,
    album: TrackId,
    alice: Account,
    units: sessionmaker[Session],
    clock: FakeClock,
) -> None:
    first = songs.save(album, THREE_SONGS).songs[0]
    with units.begin() as db:
        source = db.scalars(select(SourceRow.id).where(SourceRow.track_id == album)).one()
        db.add(
            DownloadRow(
                source_id=source,
                file_name=f"{source}.m4a",
                quality="best",
                backend="yt-dlp",
                size=1_000,
                downloaded_at=clock(),
            )
        )

    assert catalog.get_track(alice.id, first.track_id).downloaded
    assert {track.id for track in catalog.list_tracks(alice.id) if track.downloaded} == {
        album,
        *(song.track_id for song in songs.songs(album).songs),
    }
