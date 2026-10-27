"""An id too large for the database is refused with 422, never a server error."""

import pytest
from fastapi.testclient import TestClient

from tests.support.api import set_up_as_alice

TOO_LARGE = 2**63
"""One past the largest id SQLite can hold."""

PLAY = {"track_id": TOO_LARGE, "played_at": "2026-01-01T00:00:00Z"}
PLAYLIST = {"name": "Morning", "track_ids": [1, TOO_LARGE]}
PLAYLIST_ID = "00000000-0000-4000-8000-000000000001"
PLAY_ID = "00000000-0000-4000-8000-000000000002"


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", f"/api/tracks/{TOO_LARGE}", None),
        ("PUT", f"/api/tracks/{TOO_LARGE}/favorite", {"favorite": True}),
        ("PUT", f"/api/tracks/{TOO_LARGE}/rating", {"rating": 3}),
        ("PUT", f"/api/plays/{PLAY_ID}", PLAY),
        ("PUT", f"/api/playlists/{PLAYLIST_ID}", PLAYLIST),
        ("POST", f"/api/tracks/{TOO_LARGE}/playback", None),
        ("GET", f"/api/sources/{TOO_LARGE}/audio", None),
        ("HEAD", f"/api/sources/{TOO_LARGE}/audio", None),
        ("GET", f"/api/jobs/{TOO_LARGE}", None),
        ("POST", f"/api/jobs/{TOO_LARGE}/cancel", None),
        ("POST", f"/api/jobs/{TOO_LARGE}/retry", None),
        ("PUT", f"/api/accounts/{TOO_LARGE}/role", {"role": "member"}),
        ("DELETE", f"/api/accounts/{TOO_LARGE}", None),
        ("POST", f"/api/libraries/{TOO_LARGE}/scan", None),
        ("DELETE", f"/api/libraries/{TOO_LARGE}", None),
        ("DELETE", f"/api/mode/metered/{TOO_LARGE}", None),
        ("GET", f"/api/tracks/{TOO_LARGE}/details", None),
        ("PUT", f"/api/tracks/{TOO_LARGE}/details", {"values": {}}),
        ("POST", "/api/tracks/details", {"track_ids": [TOO_LARGE], "values": {}}),
    ],
)
def test_an_id_too_large_for_the_database_answers_422(
    client: TestClient, method: str, path: str, body: object
) -> None:
    set_up_as_alice(client)

    response = client.request(method, path, json=body)

    assert response.status_code == 422


@pytest.mark.parametrize("path", ["/api/tracks/0", "/api/tracks/-1", "/api/jobs/0"])
def test_an_id_below_one_answers_422(client: TestClient, path: str) -> None:
    set_up_as_alice(client)

    response = client.get(path)

    assert response.status_code == 422


def test_the_largest_id_the_database_holds_is_merely_unknown(client: TestClient) -> None:
    set_up_as_alice(client)

    response = client.get(f"/api/tracks/{2**63 - 1}")

    assert response.status_code == 404
