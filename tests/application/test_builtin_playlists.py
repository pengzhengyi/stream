"""Favorites: the smart playlist of an Account's favorites, which the server keeps for it."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application.accounts import AccountService
from medleyplay.application.builtin_playlists import ensure_builtin_playlists
from medleyplay.application.catalog import CatalogService
from medleyplay.domain.accounts import Account
from medleyplay.domain.catalog import Builtin, Playlist, PlaylistId, TrackId
from medleyplay.domain.errors import ConflictError, NotFoundError
from medleyplay.domain.rules import Favorite, Match, Rules
from medleyplay.persistence.schema import PlaylistRow
from tests.support.factories import NewAccountFactory, SourceKeyFactory, TrackDetailsFactory
from tests.support.fakes import FakeClock

FAVORITE_RULES = Rules(Match.ALL, (Favorite(value=True),))
ROAD_TRIP = PlaylistId(uuid.UUID("00000000-0000-4000-8000-0000000000a1"))


def _alice_and_bob(accounts: AccountService) -> tuple[Account, Account]:
    """Return Alice, the admin, and Bob, a member."""
    alice = accounts.create_first_admin(NewAccountFactory.admin()).account
    return alice, accounts.create_account(alice, NewAccountFactory.member())


def _favorites_of(catalog: CatalogService, account: Account) -> Playlist:
    """Return `account`'s Favorites, checking it has exactly one."""
    [favorites] = [
        playlist
        for playlist in catalog.list_playlists(account.id)
        if playlist.builtin is Builtin.FAVORITES
    ]
    return favorites


def test_every_account_starts_with_favorites_a_smart_playlist_of_its_favorites_newest_first(
    catalog: CatalogService, accounts: AccountService, clock: FakeClock
) -> None:
    alice, bob = _alice_and_bob(accounts)
    first = catalog.add_track(SourceKeyFactory.bilibili(part=1), TrackDetailsFactory.song())
    clock.advance(timedelta(days=1))
    second = catalog.add_track(SourceKeyFactory.bilibili(part=2), TrackDetailsFactory.song())

    catalog.set_favorite(alice.id, first, favorite=True)
    catalog.set_favorite(alice.id, second, favorite=True)

    favorites = _favorites_of(catalog, alice)
    assert (favorites.name, favorites.rules, favorites.track_ids, favorites.keep_downloaded) == (
        "Favorites",
        FAVORITE_RULES,
        (second, first),
        False,
    )
    assert _favorites_of(catalog, bob).track_ids == ()


def test_favorites_lists_before_the_accounts_own_playlists(
    catalog: CatalogService, accounts: AccountService
) -> None:
    alice, _ = _alice_and_bob(accounts)

    catalog.put_playlist(alice.id, ROAD_TRIP, "A road trip", [])

    assert [playlist.name for playlist in catalog.list_playlists(alice.id)] == [
        "Favorites",
        "A road trip",
    ]


def test_making_sure_again_adds_no_second_favorites(
    catalog: CatalogService,
    accounts: AccountService,
    units: sessionmaker[Session],
    clock: FakeClock,
) -> None:
    alice, _ = _alice_and_bob(accounts)
    kept = _favorites_of(catalog, alice)

    with units.begin() as db:
        ensure_builtin_playlists(db, clock())
    with units.begin() as db:
        ensure_builtin_playlists(db, clock())

    assert _favorites_of(catalog, alice) == kept


def test_an_account_without_favorites_gets_it_back_when_the_server_makes_sure(
    catalog: CatalogService,
    accounts: AccountService,
    units: sessionmaker[Session],
    clock: FakeClock,
) -> None:
    alice, _ = _alice_and_bob(accounts)
    with units.begin() as db:
        db.execute(delete(PlaylistRow).where(PlaylistRow.account_id == alice.id))

    with units.begin() as db:
        ensure_builtin_playlists(db, clock())

    assert _favorites_of(catalog, alice).rules == FAVORITE_RULES


@pytest.mark.parametrize(
    ("name", "track_ids", "rules"),
    [
        ("Loved", None, FAVORITE_RULES),
        ("Favorites", [], None),
        ("Favorites", None, Rules(Match.ALL, (Favorite(value=False),))),
    ],
    ids=["renamed", "given Tracks", "given other rules"],
)
def test_favorites_cant_be_changed_but_for_keep_downloaded(
    catalog: CatalogService,
    accounts: AccountService,
    name: str,
    track_ids: list[TrackId] | None,
    rules: Rules | None,
) -> None:
    alice, _ = _alice_and_bob(accounts)
    favorites = _favorites_of(catalog, alice)

    with pytest.raises(ConflictError, match="Keep downloaded"):
        catalog.put_playlist(alice.id, favorites.id, name, track_ids, rules=rules)

    assert _favorites_of(catalog, alice) == favorites


def test_favorites_cant_be_deleted(catalog: CatalogService, accounts: AccountService) -> None:
    alice, _ = _alice_and_bob(accounts)
    favorites = _favorites_of(catalog, alice)

    with pytest.raises(ConflictError, match="can't be deleted"):
        catalog.delete_playlist(alice.id, favorites.id)

    assert _favorites_of(catalog, alice) == favorites


@pytest.mark.parametrize("own", [True, False], ids=["an own Playlist", "Favorites"])
def test_keep_downloaded_switches_on_and_off_for_any_playlist(
    catalog: CatalogService, accounts: AccountService, changes: list[str], *, own: bool
) -> None:
    alice, _ = _alice_and_bob(accounts)
    if own:
        catalog.put_playlist(alice.id, ROAD_TRIP, "A road trip", [])
    playlist_id = ROAD_TRIP if own else _favorites_of(catalog, alice).id
    changes.clear()

    kept = catalog.set_keep_downloaded(alice.id, playlist_id, keep=True)
    dropped = catalog.set_keep_downloaded(alice.id, playlist_id, keep=False)

    assert (kept.keep_downloaded, dropped.keep_downloaded) == (True, False)
    assert changes == ["catalog", "catalog"]


def test_keep_downloaded_switched_to_what_it_is_changes_nothing(
    catalog: CatalogService, accounts: AccountService, changes: list[str], clock: FakeClock
) -> None:
    alice, _ = _alice_and_bob(accounts)
    favorites = _favorites_of(catalog, alice)
    changes.clear()
    clock.advance(timedelta(minutes=1))

    again = catalog.set_keep_downloaded(alice.id, favorites.id, keep=False)

    assert again == favorites
    assert changes == []


def test_keep_downloaded_of_another_accounts_playlist_is_not_found(
    catalog: CatalogService, accounts: AccountService
) -> None:
    alice, bob = _alice_and_bob(accounts)

    with pytest.raises(NotFoundError):
        catalog.set_keep_downloaded(bob.id, _favorites_of(catalog, alice).id, keep=True)
