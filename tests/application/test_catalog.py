"""The catalog: adding Tracks idempotently, favorites and ratings, and Playlists."""

import uuid
from dataclasses import replace
from datetime import timedelta

import pytest

from medleyplay.application.accounts import AccountService
from medleyplay.application.catalog import CatalogService
from medleyplay.domain.accounts import Account
from medleyplay.domain.catalog import Availability, PlaylistId, TrackId
from medleyplay.domain.errors import ConflictError, InvalidInputError, NotFoundError
from medleyplay.domain.playback import PlayId
from tests.support.factories import NewAccountFactory, SourceKeyFactory, TrackDetailsFactory
from tests.support.fakes import FakeClock

MORNING = PlaylistId(uuid.UUID("00000000-0000-4000-8000-000000000001"))


def _alice_and_bob(accounts: AccountService) -> tuple[Account, Account]:
    """Return Alice, the admin, and Bob, a member."""
    alice = accounts.create_first_admin(NewAccountFactory.admin()).account
    return alice, accounts.create_account(alice, NewAccountFactory.member())


def _three_tracks(catalog: CatalogService) -> list[TrackId]:
    """Add three parts of one Bilibili video and return their Tracks."""
    return [
        catalog.add_track(
            SourceKeyFactory.bilibili(part=part), TrackDetailsFactory.song(f"P{part}")
        )
        for part in (1, 2, 3)
    ]


def test_adding_a_source_creates_a_track_with_its_details(
    catalog: CatalogService, accounts: AccountService, clock: FakeClock
) -> None:
    alice, _ = _alice_and_bob(accounts)

    track_id = catalog.add_track(SourceKeyFactory.bilibili(), TrackDetailsFactory.song())

    track = catalog.get_track(alice.id, track_id)
    assert track.details == TrackDetailsFactory.song()
    assert track.added_at == clock.now
    assert (track.favorite, track.rating, track.play_count) == (False, None, 0)


def test_adding_a_known_source_again_returns_its_track_unchanged(
    catalog: CatalogService, accounts: AccountService
) -> None:
    alice, _ = _alice_and_bob(accounts)
    first = catalog.add_track(SourceKeyFactory.bilibili(), TrackDetailsFactory.song("Intro"))

    again = catalog.add_track(SourceKeyFactory.bilibili(), TrackDetailsFactory.song("Renamed"))

    assert again == first
    assert [track.details.title for track in catalog.list_tracks(alice.id)] == ["Intro"]


def test_each_account_has_its_own_favorites_and_ratings(
    catalog: CatalogService, accounts: AccountService
) -> None:
    alice, bob = _alice_and_bob(accounts)
    track_id, *_ = _three_tracks(catalog)

    catalog.set_favorite(alice.id, track_id, favorite=True)
    catalog.set_rating(bob.id, track_id, 4)

    alices, bobs = catalog.get_track(alice.id, track_id), catalog.get_track(bob.id, track_id)
    assert (alices.favorite, alices.rating) == (True, None)
    assert (bobs.favorite, bobs.rating) == (False, 4)


def test_setting_a_favorite_or_rating_twice_leaves_the_same_state(
    catalog: CatalogService, accounts: AccountService
) -> None:
    alice, _ = _alice_and_bob(accounts)
    track_id, *_ = _three_tracks(catalog)

    once = catalog.set_rating(alice.id, track_id, 5)
    catalog.set_favorite(alice.id, track_id, favorite=True)
    twice = catalog.set_favorite(alice.id, track_id, favorite=True)

    assert twice == replace(once, favorite=True)


def test_a_rating_can_be_cleared(catalog: CatalogService, accounts: AccountService) -> None:
    alice, _ = _alice_and_bob(accounts)
    track_id, *_ = _three_tracks(catalog)
    catalog.set_rating(alice.id, track_id, 3)

    assert catalog.set_rating(alice.id, track_id, None).rating is None


def test_a_rating_outside_1_to_5_is_refused(
    catalog: CatalogService, accounts: AccountService
) -> None:
    alice, _ = _alice_and_bob(accounts)
    track_id, *_ = _three_tracks(catalog)

    with pytest.raises(InvalidInputError):
        catalog.set_rating(alice.id, track_id, 6)


def test_favoriting_or_reading_a_missing_track_is_not_found(
    catalog: CatalogService, accounts: AccountService
) -> None:
    alice, _ = _alice_and_bob(accounts)

    with pytest.raises(NotFoundError, match="404"):
        catalog.set_favorite(alice.id, TrackId(404), favorite=True)
    with pytest.raises(NotFoundError, match="404"):
        catalog.get_track(alice.id, TrackId(404))


def test_putting_a_new_playlist_creates_it_in_order_with_repeats(
    catalog: CatalogService, accounts: AccountService, clock: FakeClock
) -> None:
    alice, _ = _alice_and_bob(accounts)
    first, second, _ = _three_tracks(catalog)

    playlist, created = catalog.put_playlist(
        alice.id, MORNING, " Morning ", [second, first, second]
    )

    assert created
    assert (playlist.name, playlist.track_ids) == ("Morning", (second, first, second))
    assert catalog.get_playlist(alice.id, MORNING) == playlist
    assert playlist.updated_at == clock.now


def test_putting_the_same_playlist_again_changes_nothing(
    catalog: CatalogService, accounts: AccountService, clock: FakeClock
) -> None:
    alice, _ = _alice_and_bob(accounts)
    tracks = _three_tracks(catalog)
    original, _ = catalog.put_playlist(alice.id, MORNING, "Morning", tracks)
    clock.advance(timedelta(hours=1))

    repeated, created = catalog.put_playlist(alice.id, MORNING, "Morning", tracks)

    assert not created
    assert repeated == original


def test_putting_a_changed_playlist_replaces_it(
    catalog: CatalogService, accounts: AccountService, clock: FakeClock
) -> None:
    alice, _ = _alice_and_bob(accounts)
    first, second, third = _three_tracks(catalog)
    catalog.put_playlist(alice.id, MORNING, "Morning", [first, second])
    clock.advance(timedelta(hours=1))

    replaced, created = catalog.put_playlist(alice.id, MORNING, "Evening", [third])

    assert not created
    assert (replaced.name, replaced.track_ids, replaced.updated_at) == (
        "Evening",
        (third,),
        clock.now,
    )
    assert catalog.get_playlist(alice.id, MORNING) == replaced


def test_another_accounts_playlist_id_is_refused_and_hidden(
    catalog: CatalogService, accounts: AccountService
) -> None:
    alice, bob = _alice_and_bob(accounts)
    catalog.put_playlist(alice.id, MORNING, "Morning", [])

    with pytest.raises(ConflictError, match="already in use"):
        catalog.put_playlist(bob.id, MORNING, "Mine now", [])
    with pytest.raises(NotFoundError):
        catalog.get_playlist(bob.id, MORNING)
    assert catalog.list_playlists(bob.id) == []
    catalog.delete_playlist(bob.id, MORNING)
    assert catalog.get_playlist(alice.id, MORNING).name == "Morning"


def test_a_playlist_with_unknown_tracks_is_refused(
    catalog: CatalogService, accounts: AccountService
) -> None:
    alice, _ = _alice_and_bob(accounts)

    with pytest.raises(InvalidInputError, match=r"\[404, 405\]"):
        catalog.put_playlist(alice.id, MORNING, "Morning", [TrackId(405), TrackId(404)])


def test_playlists_are_listed_by_name(catalog: CatalogService, accounts: AccountService) -> None:
    alice, _ = _alice_and_bob(accounts)
    for name in ("Zen", "Afternoon"):
        catalog.put_playlist(alice.id, PlaylistId(uuid.uuid4()), name, [])

    assert [p.name for p in catalog.list_playlists(alice.id)] == ["Afternoon", "Zen"]


def test_deleting_a_playlist_is_safe_to_repeat(
    catalog: CatalogService, accounts: AccountService
) -> None:
    alice, _ = _alice_and_bob(accounts)
    catalog.put_playlist(alice.id, MORNING, "Morning", _three_tracks(catalog))

    catalog.delete_playlist(alice.id, MORNING)
    catalog.delete_playlist(alice.id, MORNING)

    assert catalog.list_playlists(alice.id) == []


def test_deleting_an_account_deletes_its_playlists_and_track_state(
    catalog: CatalogService, accounts: AccountService
) -> None:
    alice, bob = _alice_and_bob(accounts)
    track_id, *_ = _three_tracks(catalog)
    catalog.set_favorite(bob.id, track_id, favorite=True)
    catalog.put_playlist(bob.id, MORNING, "Morning", [track_id])

    accounts.delete_account(alice, bob.id)

    assert catalog.list_playlists(bob.id) == []
    assert not catalog.get_track(bob.id, track_id).favorite
    catalog.put_playlist(alice.id, MORNING, "Reused id", [])


FIRST_PLAY = PlayId(uuid.UUID("00000000-0000-4000-8000-0000000000a1"))


def test_a_play_raises_the_play_count_and_sets_the_last_played_time(
    catalog: CatalogService, accounts: AccountService, clock: FakeClock
) -> None:
    alice, _ = _alice_and_bob(accounts)
    [track_id, *_] = _three_tracks(catalog)

    track = catalog.record_play(alice.id, FIRST_PLAY, track_id, clock.now)

    assert (track.play_count, track.last_played_at) == (1, clock.now)


def test_sending_a_play_again_counts_it_once(
    catalog: CatalogService, accounts: AccountService, clock: FakeClock
) -> None:
    alice, _ = _alice_and_bob(accounts)
    [track_id, *_] = _three_tracks(catalog)
    catalog.record_play(alice.id, FIRST_PLAY, track_id, clock.now)

    again = catalog.record_play(alice.id, FIRST_PLAY, track_id, clock.now)

    assert again.play_count == 1


def test_a_play_id_sent_with_another_track_is_refused(
    catalog: CatalogService, accounts: AccountService, clock: FakeClock
) -> None:
    alice, _ = _alice_and_bob(accounts)
    first, second, _ = _three_tracks(catalog)
    catalog.record_play(alice.id, FIRST_PLAY, first, clock.now)

    with pytest.raises(ConflictError, match="was of another Track"):
        catalog.record_play(alice.id, FIRST_PLAY, second, clock.now)


def test_each_account_has_its_own_play_ids_and_counts(
    catalog: CatalogService, accounts: AccountService, clock: FakeClock
) -> None:
    alice, bob = _alice_and_bob(accounts)
    first, second, _ = _three_tracks(catalog)
    catalog.record_play(alice.id, FIRST_PLAY, first, clock.now)

    bobs = catalog.record_play(bob.id, FIRST_PLAY, second, clock.now)

    assert bobs.play_count == 1
    assert catalog.get_track(bob.id, first).play_count == 0


def test_a_play_from_the_future_is_recorded_as_now(
    catalog: CatalogService, accounts: AccountService, clock: FakeClock
) -> None:
    alice, _ = _alice_and_bob(accounts)
    [track_id, *_] = _three_tracks(catalog)

    track = catalog.record_play(alice.id, FIRST_PLAY, track_id, clock.now + timedelta(days=1))

    assert track.last_played_at == clock.now


def test_a_play_recorded_late_keeps_the_later_play_the_latest(
    catalog: CatalogService, accounts: AccountService, clock: FakeClock
) -> None:
    alice, _ = _alice_and_bob(accounts)
    [track_id, *_] = _three_tracks(catalog)
    catalog.record_play(alice.id, FIRST_PLAY, track_id, clock.now)
    earlier = PlayId(uuid.UUID("00000000-0000-4000-8000-0000000000a2"))

    track = catalog.record_play(alice.id, earlier, track_id, clock.now - timedelta(hours=2))

    assert (track.play_count, track.last_played_at) == (2, clock.now)


def test_a_play_of_a_track_that_does_not_exist_is_not_found(
    catalog: CatalogService, accounts: AccountService, clock: FakeClock
) -> None:
    alice, _ = _alice_and_bob(accounts)

    with pytest.raises(NotFoundError):
        catalog.record_play(alice.id, FIRST_PLAY, TrackId(404), clock.now)


def test_a_track_from_a_site_is_available(
    catalog: CatalogService, accounts: AccountService
) -> None:
    alice, _ = _alice_and_bob(accounts)
    [track_id, *_] = _three_tracks(catalog)

    assert catalog.get_track(alice.id, track_id).availability is Availability.OK
