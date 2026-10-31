"""The songs API: splitting an album file into songs, editing them by id, and unsplitting."""

import pytest
from fastapi.testclient import TestClient

from medleyplay.application.catalog import CatalogService
from medleyplay.domain.catalog import TrackId
from tests.support.api import set_up_as_alice
from tests.support.factories import SourceKeyFactory, TrackDetailsFactory

TWO_SONGS = [
    {"id": None, "start_ms": 0, "title": "アイネクライネ", "artist": ""},
    {"id": None, "start_ms": 252_000, "title": "ゴーゴー幽霊船", "artist": "米津玄師"},
]
"""A first split of *Bremen* into two new songs."""


def _album(catalog: CatalogService) -> TrackId:
    """Add *Bremen*, a whole album uploaded as one hour-long video."""
    return catalog.add_track(
        SourceKeyFactory.bilibili("BV1dm4y1s7ak"), TrackDetailsFactory.album_file()
    )


def test_splitting_a_file_answers_its_songs(client: TestClient, catalog: CatalogService) -> None:
    set_up_as_alice(client)
    album = _album(catalog)

    response = client.put(f"/api/tracks/{album}/songs", json={"rows": TWO_SONGS})

    assert response.status_code == 200
    body = response.json()
    assert [(song["start_ms"], song["end_ms"], song["title"]) for song in body["songs"]] == [
        (0, 252_000, "アイネクライネ"),
        (252_000, 3_600_000, "ゴーゴー幽霊船"),
    ]
    assert (body["length_ms"], body["needs_check"], body["found"]) == (3_600_000, False, [])


def test_track_lists_say_which_file_is_split_and_which_file_a_song_is_of(
    client: TestClient, catalog: CatalogService
) -> None:
    set_up_as_alice(client)
    album = _album(catalog)
    first = client.put(f"/api/tracks/{album}/songs", json={"rows": TWO_SONGS}).json()["songs"][0]

    tracks = {track["id"]: track for track in client.get("/api/tracks").json()}

    assert (tracks[album]["split"], tracks[album]["segment_of"]) == (True, None)
    song = tracks[first["track_id"]]
    assert (song["split"], song["segment_of"], song["title"]) == (False, album, "アイネクライネ")


def test_a_song_named_by_its_id_keeps_its_track(
    client: TestClient, catalog: CatalogService
) -> None:
    set_up_as_alice(client)
    album = _album(catalog)
    first, second = client.put(f"/api/tracks/{album}/songs", json={"rows": TWO_SONGS}).json()[
        "songs"
    ]
    rows = [
        {"id": first["id"], "start_ms": 0, "title": "Little Night", "artist": ""},
        {"id": second["id"], "start_ms": 252_000, "title": "ゴーゴー幽霊船", "artist": ""},
    ]

    songs = client.put(f"/api/tracks/{album}/songs", json={"rows": rows}).json()["songs"]

    assert [song["track_id"] for song in songs] == [first["track_id"], second["track_id"]]
    assert client.get(f"/api/tracks/{first['track_id']}").json()["title"] == "Little Night"


def test_unsplitting_a_file_says_how_many_songs_it_removed(
    client: TestClient, catalog: CatalogService
) -> None:
    set_up_as_alice(client)
    album = _album(catalog)
    client.put(f"/api/tracks/{album}/songs", json={"rows": TWO_SONGS})

    response = client.delete(f"/api/tracks/{album}/songs")

    assert response.json() == {"removed": 2}
    assert client.get(f"/api/tracks/{album}/songs").json()["songs"] == []


def test_rows_that_are_not_a_song_list_are_refused(
    client: TestClient, catalog: CatalogService
) -> None:
    set_up_as_alice(client)
    album = _album(catalog)
    rows = [{**TWO_SONGS[0], "start_ms": 5_000}, {**TWO_SONGS[1], "start_ms": 1_000}]

    response = client.put(f"/api/tracks/{album}/songs", json={"rows": rows})

    assert response.status_code == 422


def test_a_start_before_the_file_begins_is_refused(
    client: TestClient, catalog: CatalogService
) -> None:
    set_up_as_alice(client)
    album = _album(catalog)
    rows = [{**TWO_SONGS[0], "start_ms": -1}, TWO_SONGS[1]]

    assert client.put(f"/api/tracks/{album}/songs", json={"rows": rows}).status_code == 422


def test_the_songs_of_a_missing_track_are_not_found(client: TestClient) -> None:
    set_up_as_alice(client)

    assert client.get("/api/tracks/999/songs").status_code == 404


def test_songs_need_a_signed_in_account(client: TestClient, catalog: CatalogService) -> None:
    album = _album(catalog)

    assert client.get(f"/api/tracks/{album}/songs").status_code == 401


@pytest.mark.parametrize(
    "row",
    [
        {"id": "1", "start_ms": 0, "title": "A"},
        {"id": True, "start_ms": 0, "title": "A"},
        {"id": None, "start_ms": 0, "title": "A", "end_ms": 5_000},
    ],
    ids=["id as text", "id as true", "an unknown field"],
)
def test_a_row_of_the_wrong_shape_is_refused(
    client: TestClient, catalog: CatalogService, row: dict[str, object]
) -> None:
    set_up_as_alice(client)
    album = _album(catalog)

    response = client.put(f"/api/tracks/{album}/songs", json={"rows": [row, TWO_SONGS[1]]})

    assert response.status_code == 422


def test_the_songs_of_a_song_conflict(client: TestClient, catalog: CatalogService) -> None:
    set_up_as_alice(client)
    album = _album(catalog)
    song = client.put(f"/api/tracks/{album}/songs", json={"rows": TWO_SONGS}).json()["songs"][0]

    assert client.get(f"/api/tracks/{song['track_id']}/songs").status_code == 409


def test_a_pasted_list_answers_its_songs(client: TestClient, catalog: CatalogService) -> None:
    set_up_as_alice(client)
    album = _album(catalog)

    response = client.post(
        f"/api/tracks/{album}/songs/read",
        json={"text": "00:00 Intro\n03:12 Night Drive - Blue Room"},
    )

    assert response.json() == {
        "songs": [
            {"start_ms": 0, "title": "Intro", "artist": ""},
            {"start_ms": 192_000, "title": "Night Drive", "artist": "Blue Room"},
        ]
    }


def test_a_pasted_list_that_isnt_one_answers_why(
    client: TestClient, catalog: CatalogService
) -> None:
    set_up_as_alice(client)
    album = _album(catalog)

    response = client.post(f"/api/tracks/{album}/songs/read", json={"text": "Intro\n03:12 B"})

    assert response.status_code == 422
    assert "Line 1" in response.text
