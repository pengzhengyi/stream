"""Smart playlists: Playlists whose Tracks are the ones their rules match now."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application.accounts import AccountService
from medleyplay.application.catalog import CatalogService
from medleyplay.application.segments import SongsService
from medleyplay.domain.accounts import Account
from medleyplay.domain.catalog import PlaylistId, TrackId
from medleyplay.domain.errors import InvalidInputError
from medleyplay.domain.rules import Favorite, Kind, Match, Rules
from medleyplay.domain.segments import SongRow
from medleyplay.domain.video_text import Song
from medleyplay.persistence.schema import PlaylistRow
from tests.support.factories import NewAccountFactory, SourceKeyFactory, TrackDetailsFactory
from tests.support.fakes import FakeClock

FAVORITES = PlaylistId(uuid.UUID("00000000-0000-4000-8000-0000000000f1"))
FAVORITE_RULES = Rules(Match.ALL, (Favorite(value=True),))


def _alice_and_bob(accounts: AccountService) -> tuple[Account, Account]:
    """Return Alice, the admin, and Bob, a member."""
    alice = accounts.create_first_admin(NewAccountFactory.admin()).account
    return alice, accounts.create_account(alice, NewAccountFactory.member())


def _added_a_day_apart(catalog: CatalogService, clock: FakeClock, count: int) -> list[TrackId]:
    """Add parts 1 to `count` of one Bilibili video, a day apart, oldest first."""
    tracks = []
    for part in range(1, count + 1):
        tracks.append(
            catalog.add_track(SourceKeyFactory.bilibili(part=part), TrackDetailsFactory.song())
        )
        clock.advance(timedelta(days=1))
    return tracks


def test_a_smart_playlist_lists_the_tracks_its_rules_match_newest_added_first(
    catalog: CatalogService, accounts: AccountService, clock: FakeClock
) -> None:
    alice, _ = _alice_and_bob(accounts)
    first, second, third = _added_a_day_apart(catalog, clock, 3)
    catalog.set_favorite(alice.id, first, favorite=True)
    catalog.set_favorite(alice.id, third, favorite=True)

    catalog.put_playlist(alice.id, FAVORITES, "Favorites", rules=FAVORITE_RULES)
    catalog.set_favorite(alice.id, second, favorite=True)

    smart = catalog.get_playlist(alice.id, FAVORITES)
    assert (smart.rules, smart.track_ids) == (FAVORITE_RULES, (third, second, first))


def test_a_smart_playlist_matches_as_its_owner_sees_the_tracks(
    catalog: CatalogService, accounts: AccountService, clock: FakeClock
) -> None:
    alice, bob = _alice_and_bob(accounts)
    [track] = _added_a_day_apart(catalog, clock, 1)
    catalog.set_favorite(bob.id, track, favorite=True)

    catalog.put_playlist(alice.id, FAVORITES, "Favorites", rules=FAVORITE_RULES)

    assert catalog.get_playlist(alice.id, FAVORITES).track_ids == ()


def test_putting_the_same_smart_playlist_again_changes_nothing(
    catalog: CatalogService, accounts: AccountService, clock: FakeClock
) -> None:
    alice, _ = _alice_and_bob(accounts)
    first, _created = catalog.put_playlist(
        alice.id, FAVORITES, "Favorites", rules=FAVORITE_RULES, keep_downloaded=True
    )
    clock.advance(timedelta(minutes=5))

    again, created = catalog.put_playlist(
        alice.id, FAVORITES, "Favorites", rules=FAVORITE_RULES, keep_downloaded=True
    )

    assert (again.updated_at, created) == (first.updated_at, False)


def test_a_plain_playlist_put_as_smart_drops_its_entries_and_back_drops_its_rules(
    catalog: CatalogService, accounts: AccountService, clock: FakeClock
) -> None:
    alice, _ = _alice_and_bob(accounts)
    [track] = _added_a_day_apart(catalog, clock, 1)
    catalog.put_playlist(alice.id, FAVORITES, "Mix", [track])

    smart, _ = catalog.put_playlist(
        alice.id, FAVORITES, "Mix", rules=Rules(Match.ANY, (Kind("library"),))
    )
    plain, _ = catalog.put_playlist(alice.id, FAVORITES, "Mix", [])

    assert (smart.rules is not None, smart.track_ids) == (True, ())
    assert (plain.rules, plain.track_ids) == (None, ())


def test_any_playlist_can_keep_its_tracks_downloaded(
    catalog: CatalogService, accounts: AccountService, clock: FakeClock
) -> None:
    alice, _ = _alice_and_bob(accounts)
    [track] = _added_a_day_apart(catalog, clock, 1)

    plain, _ = catalog.put_playlist(alice.id, FAVORITES, "Car", [track], keep_downloaded=True)

    assert (
        catalog.get_playlist(alice.id, FAVORITES).keep_downloaded is plain.keep_downloaded is True
    )


def test_a_playlist_with_both_tracks_and_rules_is_refused(
    catalog: CatalogService, accounts: AccountService
) -> None:
    alice, _ = _alice_and_bob(accounts)

    with pytest.raises(InvalidInputError, match="rules"):
        catalog.put_playlist(alice.id, FAVORITES, "Both", [], rules=FAVORITE_RULES)


def test_stored_rules_this_server_cant_read_show_no_tracks_and_say_why(
    catalog: CatalogService, accounts: AccountService, units: sessionmaker[Session]
) -> None:
    alice, _ = _alice_and_bob(accounts)
    catalog.put_playlist(alice.id, FAVORITES, "Favorites", rules=FAVORITE_RULES)
    newer = {"version": 2, "match": "all", "conditions": []}
    with units.begin() as db:
        db.execute(update(PlaylistRow).values(rules=newer))

    unreadable = catalog.get_playlist(alice.id, FAVORITES)

    assert (unreadable.rules, unreadable.track_ids) == (None, ())
    assert "version 2" in unreadable.unreadable


def test_a_smart_playlist_matches_a_split_files_songs_not_the_file(
    catalog: CatalogService, songs: SongsService, accounts: AccountService, clock: FakeClock
) -> None:
    alice, _ = _alice_and_bob(accounts)
    [album] = _added_a_day_apart(catalog, clock, 1)
    split = songs.save(
        album, [SongRow(None, Song(0, "Intro")), SongRow(None, Song(60_000, "Outro"))]
    )

    catalog.put_playlist(
        alice.id, FAVORITES, "From Bilibili", rules=Rules(Match.ALL, (Kind("bilibili"),))
    )

    matched = set(catalog.get_playlist(alice.id, FAVORITES).track_ids)
    assert matched == {song.track_id for song in split.songs}
