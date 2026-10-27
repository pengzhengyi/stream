"""A Track's details: every origin's values, the household's own, and many Tracks at once."""

import pytest
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application.accounts import AccountService
from medleyplay.application.catalog import CatalogService
from medleyplay.application.details import DetailsService
from medleyplay.domain.accounts import Account
from medleyplay.domain.catalog import TrackId
from medleyplay.domain.details import Field, Origin, Shown
from medleyplay.domain.errors import InvalidInputError, NotFoundError
from tests.support.factories import NewAccountFactory, SourceKeyFactory, TrackDetailsFactory
from tests.support.fakes import FakeClock


@pytest.fixture
def alice(accounts: AccountService) -> Account:
    return accounts.create_first_admin(NewAccountFactory.admin()).account


def _song(catalog: CatalogService, part: int = 1, title: str = "Intro") -> TrackId:
    """Add one part of a Bilibili video, whose details are the video's."""
    return catalog.add_track(SourceKeyFactory.bilibili(part=part), TrackDetailsFactory.song(title))


def test_a_new_site_tracks_details_are_its_videos(
    catalog: CatalogService, details: DetailsService
) -> None:
    track_id = _song(catalog)

    view = details.details(track_id)

    assert view.values == {
        Origin.VIDEO: {Field.TITLE: "Intro", Field.ARTIST: "The Band", Field.ALBUM: "Blue"}
    }
    assert view.shown[Field.TITLE] == Shown("Intro", Origin.VIDEO)


def test_the_households_values_show_on_the_track(
    catalog: CatalogService, details: DetailsService, alice: Account
) -> None:
    track_id = _song(catalog)

    view = details.put_household(track_id, {"title": "Night Drive", "year": 2016})

    assert view.shown[Field.TITLE] == Shown("Night Drive", Origin.HOUSEHOLD)
    track = catalog.get_track(alice.id, track_id).details
    assert (track.title, track.artist, track.year) == ("Night Drive", "The Band", 2016)


def test_putting_the_households_values_drops_the_ones_left_out(
    catalog: CatalogService, details: DetailsService, alice: Account
) -> None:
    track_id = _song(catalog)
    details.put_household(track_id, {"title": "Night Drive", "genre": "Pop"})

    details.put_household(track_id, {"genre": "City pop"})

    track = catalog.get_track(alice.id, track_id).details
    assert (track.title, track.genre) == ("Intro", "City pop")


def test_empty_text_from_the_household_shows_nothing(
    catalog: CatalogService, details: DetailsService, alice: Account
) -> None:
    track_id = _song(catalog)

    details.put_household(track_id, {"artist": ""})

    assert catalog.get_track(alice.id, track_id).details.artist == ""


def test_values_are_set_on_many_tracks_at_once(
    catalog: CatalogService, details: DetailsService, alice: Account
) -> None:
    tracks = [_song(catalog, part, f"P{part}") for part in (1, 2)]

    changed = details.set_on_many(tracks, {"album": "Re:Start", "album_artist": "wowaka"})

    assert changed == 2
    assert [catalog.get_track(alice.id, each).details.album for each in tracks] == [
        "Re:Start",
        "Re:Start",
    ]


def test_setting_none_on_many_tracks_drops_the_households_value(
    catalog: CatalogService, details: DetailsService, alice: Account
) -> None:
    track_id = _song(catalog)
    details.set_on_many([track_id], {"album": "Re:Start"})

    details.set_on_many([track_id], {"album": None})

    assert catalog.get_track(alice.id, track_id).details.album == "Blue"


def test_many_tracks_change_together_or_not_at_all(
    catalog: CatalogService, details: DetailsService, alice: Account
) -> None:
    track_id = _song(catalog)

    with pytest.raises(NotFoundError):
        details.set_on_many([track_id, TrackId(999)], {"album": "Re:Start"})

    assert catalog.get_track(alice.id, track_id).details.album == "Blue"


@pytest.mark.parametrize(
    "values",
    [{"lyrics": "la la"}, {"year": 99}, {"title": 3}],
    ids=["an unknown field", "a year of two digits", "a number for a title"],
)
def test_a_value_a_track_cant_keep_is_refused(
    catalog: CatalogService, details: DetailsService, values: dict[str, object]
) -> None:
    track_id = _song(catalog)

    with pytest.raises(InvalidInputError):
        details.put_household(track_id, values)


def test_the_details_of_a_missing_track_are_not_found(details: DetailsService) -> None:
    with pytest.raises(NotFoundError):
        details.details(TrackId(999))


def test_a_change_tells_the_catalogs_listeners(
    catalog: CatalogService, units: sessionmaker[Session], clock: FakeClock
) -> None:
    told: list[str] = []
    track_id = _song(catalog)
    service = DetailsService(units, clock, told.append)

    service.put_household(track_id, {"genre": "Pop"})

    assert told == ["catalog"]
