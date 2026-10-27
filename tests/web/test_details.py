"""The details API: what each origin says about a Track, and the household's own values."""

from fastapi.testclient import TestClient

from medleyplay.application.catalog import CatalogService
from medleyplay.domain.catalog import TrackId
from tests.support.api import add_bob, set_up_as_alice, sign_in
from tests.support.factories import SourceKeyFactory, TrackDetailsFactory


def _one_track(catalog: CatalogService, part: int = 1) -> TrackId:
    """Add one Bilibili Track, "Intro" by The Band on "Blue", whose details are its video's."""
    return catalog.add_track(SourceKeyFactory.bilibili(part=part), TrackDetailsFactory.song())


def test_a_tracks_details_say_where_each_value_came_from(
    client: TestClient, catalog: CatalogService
) -> None:
    set_up_as_alice(client)
    track_id = _one_track(catalog)

    body = client.get(f"/api/tracks/{track_id}/details").json()

    assert body["shown"]["title"] == {"value": "Intro", "origin": "video"}
    assert body["origins"] == {"video": {"title": "Intro", "artist": "The Band", "album": "Blue"}}


def test_the_households_values_are_put_and_show_on_the_track(
    client: TestClient, catalog: CatalogService
) -> None:
    set_up_as_alice(client)
    track_id = _one_track(catalog)

    put = client.put(
        f"/api/tracks/{track_id}/details",
        json={"values": {"title": "Night Drive", "year": 2016, "genre": ""}},
    )

    assert put.status_code == 200
    assert put.json()["shown"]["title"] == {"value": "Night Drive", "origin": "household"}
    track = client.get(f"/api/tracks/{track_id}").json()
    assert (track["title"], track["year"], track["genre"]) == ("Night Drive", 2016, "")


def test_any_signed_in_account_may_edit_a_tracks_details(
    client: TestClient, catalog: CatalogService
) -> None:
    set_up_as_alice(client)
    add_bob(client)
    track_id = _one_track(catalog)
    sign_in(client, "bob")

    put = client.put(f"/api/tracks/{track_id}/details", json={"values": {"artist": "Blue Room"}})

    assert put.status_code == 200


def test_values_are_set_on_many_tracks_at_once(client: TestClient, catalog: CatalogService) -> None:
    set_up_as_alice(client)
    tracks = [_one_track(catalog, part) for part in (1, 2)]

    response = client.post(
        "/api/tracks/details", json={"track_ids": tracks, "values": {"album": "Re:Start"}}
    )

    assert response.json() == {"changed": 2}
    assert {t["album"] for t in client.get("/api/tracks").json()} == {"Re:Start"}


def test_a_detail_unknown_to_tracks_is_refused(
    client: TestClient, catalog: CatalogService
) -> None:
    set_up_as_alice(client)
    track_id = _one_track(catalog)

    response = client.put(f"/api/tracks/{track_id}/details", json={"values": {"lyrics": "la"}})

    assert response.status_code == 422


def test_the_details_of_a_missing_track_are_not_found(client: TestClient) -> None:
    set_up_as_alice(client)

    assert client.get("/api/tracks/999/details").status_code == 404


def test_details_need_a_signed_in_account(client: TestClient, catalog: CatalogService) -> None:
    track_id = _one_track(catalog)

    assert client.get(f"/api/tracks/{track_id}/details").status_code == 401
