"""The app's guards: the Host check against DNS rebinding and the Origin check on writes."""

from fastapi.testclient import TestClient

from tests.support.api import ALICE_SETUP


def test_a_request_for_another_host_is_refused(client: TestClient) -> None:
    response = client.get("/api/setup", headers={"host": "attacker.example"})

    assert response.status_code == 400


def test_a_write_from_another_sites_page_is_refused(client: TestClient) -> None:
    response = client.post(
        "/api/setup", json=ALICE_SETUP, headers={"origin": "http://attacker.example"}
    )

    assert response.status_code == 403
    assert not client.get("/api/setup").json()["set_up"]


def test_a_write_from_the_servers_own_page_is_allowed(client: TestClient) -> None:
    response = client.post("/api/setup", json=ALICE_SETUP, headers={"origin": "http://testserver"})

    assert response.status_code == 201


def test_a_read_from_another_origin_is_answered(client: TestClient) -> None:
    response = client.get("/api/setup", headers={"origin": "http://attacker.example"})

    assert response.status_code == 200


def test_the_interactive_api_docs_are_served(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    assert schema["info"]["title"] == "medleyplay"
    assert "/api/playlists/{playlist_id}" in schema["paths"]
