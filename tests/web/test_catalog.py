"""The catalog API: Tracks with your own state, and Playlists under ids you choose."""

import json
import uuid

from fastapi.testclient import TestClient

from medleyplay.application.catalog import CatalogService
from medleyplay.domain.catalog import TrackId
from tests.support.api import add_bob, set_up_as_alice, sign_in
from tests.support.factories import SourceKeyFactory, TrackDetailsFactory

MORNING = uuid.UUID("00000000-0000-4000-8000-000000000001")


def _one_track(catalog: CatalogService) -> TrackId:
    """Add one Bilibili Track, "Intro" by The Band."""
    return catalog.add_track(SourceKeyFactory.bilibili(), TrackDetailsFactory.song("Intro"))


def test_tracks_are_listed_with_your_own_state(client: TestClient, catalog: CatalogService) -> None:
    set_up_as_alice(client)
    track_id = _one_track(catalog)
    client.put(f"/api/tracks/{track_id}/favorite", json={"favorite": True})

    tracks = client.get("/api/tracks").json()

    assert [(t["id"], t["title"], t["artist"], t["favorite"]) for t in tracks] == [
        (track_id, "Intro", "The Band", True)
    ]


def test_a_rating_is_put_as_an_absolute_value_and_can_be_cleared(
    client: TestClient, catalog: CatalogService
) -> None:
    set_up_as_alice(client)
    track_id = _one_track(catalog)

    rated = client.put(f"/api/tracks/{track_id}/rating", json={"rating": 4})
    cleared = client.put(f"/api/tracks/{track_id}/rating", json={"rating": None})

    assert (rated.json()["rating"], cleared.json()["rating"]) == (4, None)
    assert client.get(f"/api/tracks/{track_id}").json()["rating"] is None


def test_a_rating_of_six_stars_answers_422(client: TestClient, catalog: CatalogService) -> None:
    set_up_as_alice(client)
    track_id = _one_track(catalog)

    assert client.put(f"/api/tracks/{track_id}/rating", json={"rating": 6}).status_code == 422


def test_a_missing_track_answers_404(client: TestClient) -> None:
    set_up_as_alice(client)

    assert client.get("/api/tracks/404").status_code == 404


def test_putting_a_playlist_answers_201_then_200_with_the_same_body(
    client: TestClient, catalog: CatalogService
) -> None:
    set_up_as_alice(client)
    track_id = _one_track(catalog)
    playlist = {"name": "Morning", "track_ids": [track_id, track_id]}

    created = client.put(f"/api/playlists/{MORNING}", json=playlist)
    repeated = client.put(f"/api/playlists/{MORNING}", json=playlist)

    assert (created.status_code, repeated.status_code) == (201, 200)
    assert created.json() == repeated.json()
    assert created.json()["track_ids"] == [track_id, track_id]
    favorites, morning = client.get("/api/playlists").json()
    assert (favorites["builtin"], morning) == ("favorites", created.json())


FAVORITES = """
{
  "name": "Favorites",
  "keep_downloaded": true,
  "rules": {
    "version": 1,
    "match": "all",
    "conditions": [{ "field": "favorite", "op": "is", "value": true }]
  }
}
"""


def test_a_smart_playlist_answers_with_its_rules_and_the_tracks_they_match(
    client: TestClient, catalog: CatalogService
) -> None:
    set_up_as_alice(client)
    track_id = _one_track(catalog)
    client.put(f"/api/tracks/{track_id}/favorite", json={"favorite": True})
    body = json.loads(FAVORITES)

    smart = client.put(f"/api/playlists/{MORNING}", json=body).json()

    assert (smart["rules"], smart["keep_downloaded"], smart["track_ids"]) == (
        body["rules"],
        True,
        [track_id],
    )
    assert smart["unreadable"] == ""


def test_a_playlist_with_rules_the_schema_refuses_answers_422(client: TestClient) -> None:
    set_up_as_alice(client)
    body = json.loads(FAVORITES)
    body["rules"]["conditions"][0]["field"] = "mood"

    assert client.put(f"/api/playlists/{MORNING}", json=body).status_code == 422


def test_a_playlist_with_both_tracks_and_rules_answers_422(client: TestClient) -> None:
    set_up_as_alice(client)

    both = client.put(f"/api/playlists/{MORNING}", json={**json.loads(FAVORITES), "track_ids": []})

    assert both.status_code == 422


def test_another_accounts_playlist_id_answers_409_and_its_playlist_404(
    client: TestClient,
) -> None:
    set_up_as_alice(client)
    add_bob(client)
    client.put(f"/api/playlists/{MORNING}", json={"name": "Morning", "track_ids": []})
    sign_in(client, "bob")

    taken = client.put(f"/api/playlists/{MORNING}", json={"name": "Mine", "track_ids": []})

    assert taken.status_code == 409
    assert client.get(f"/api/playlists/{MORNING}").status_code == 404


def test_deleting_a_playlist_answers_204_every_time(client: TestClient) -> None:
    set_up_as_alice(client)
    client.put(f"/api/playlists/{MORNING}", json={"name": "Morning", "track_ids": []})

    first, second = (
        client.delete(f"/api/playlists/{MORNING}"),
        client.delete(f"/api/playlists/{MORNING}"),
    )

    assert (first.status_code, second.status_code) == (204, 204)
    assert [p["name"] for p in client.get("/api/playlists").json()] == ["Favorites"]


def _favorites(client: TestClient) -> dict[str, object]:
    """Return the signed-in Account's Favorites, which the API lists first."""
    favorites: dict[str, object] = client.get("/api/playlists").json()[0]
    assert favorites["builtin"] == "favorites"
    return favorites


def test_favorites_is_the_smart_playlist_of_your_favorites_the_server_keeps(
    client: TestClient, catalog: CatalogService
) -> None:
    set_up_as_alice(client)
    track_id = _one_track(catalog)

    client.put(f"/api/tracks/{track_id}/favorite", json={"favorite": True})

    favorites = _favorites(client)
    expected = json.loads(FAVORITES)
    assert (favorites["name"], favorites["rules"], favorites["track_ids"]) == (
        "Favorites",
        expected["rules"],
        [track_id],
    )
    assert favorites["keep_downloaded"] is False


def test_keep_downloaded_switches_with_a_put_of_its_own_as_often_as_sent(
    client: TestClient,
) -> None:
    set_up_as_alice(client)
    url = f"/api/playlists/{_favorites(client)['id']}/keep_downloaded"

    first = client.put(url, json={"keep_downloaded": True})
    again = client.put(url, json={"keep_downloaded": True})

    assert (first.status_code, again.status_code) == (200, 200)
    assert first.json() == again.json()
    assert _favorites(client)["keep_downloaded"] is True


def test_favorites_answers_409_to_a_replace_or_a_delete(client: TestClient) -> None:
    set_up_as_alice(client)
    favorites = _favorites(client)
    url = f"/api/playlists/{favorites['id']}"

    replaced = client.put(url, json={"name": "Loved", "track_ids": []})
    deleted = client.delete(url)

    assert (replaced.status_code, deleted.status_code) == (409, 409)
    assert _favorites(client) == favorites


def test_keep_downloaded_of_another_accounts_playlist_answers_404(client: TestClient) -> None:
    set_up_as_alice(client)
    add_bob(client)
    alices = _favorites(client)["id"]
    sign_in(client, "bob")

    switched = client.put(
        f"/api/playlists/{alices}/keep_downloaded", json={"keep_downloaded": True}
    )

    assert switched.status_code == 404


FIRST_PLAY = "00000000-0000-4000-8000-0000000000a1"


def test_a_play_is_put_once_under_your_id_and_answers_the_track(
    client: TestClient, catalog: CatalogService
) -> None:
    set_up_as_alice(client)
    track_id = _one_track(catalog)
    play = {"track_id": track_id, "played_at": "2026-10-25T08:00:00+00:00"}

    first = client.put(f"/api/plays/{FIRST_PLAY}", json=play)
    again = client.put(f"/api/plays/{FIRST_PLAY}", json=play)

    assert (first.status_code, again.status_code) == (200, 200)
    assert again.json()["play_count"] == 1
    assert again.json()["availability"] == "ok"


def test_a_play_id_put_with_another_track_answers_409(
    client: TestClient, catalog: CatalogService
) -> None:
    set_up_as_alice(client)
    first = _one_track(catalog)
    second = catalog.add_track(SourceKeyFactory.bilibili(part=2), TrackDetailsFactory.song("P2"))
    client.put(
        f"/api/plays/{FIRST_PLAY}", json={"track_id": first, "played_at": "2026-10-25T08:00:00Z"}
    )

    response = client.put(
        f"/api/plays/{FIRST_PLAY}", json={"track_id": second, "played_at": "2026-10-25T08:00:00Z"}
    )

    assert response.status_code == 409


def test_a_play_without_a_time_zone_answers_422(
    client: TestClient, catalog: CatalogService
) -> None:
    set_up_as_alice(client)
    track_id = _one_track(catalog)

    response = client.put(
        f"/api/plays/{FIRST_PLAY}", json={"track_id": track_id, "played_at": "2026-10-25T08:00:00"}
    )

    assert response.status_code == 422
