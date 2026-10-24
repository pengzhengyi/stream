"""Helpers for driving the HTTP API the way a browser does."""

from fastapi.testclient import TestClient

from tests.support.factories import PASSWORD

ALICE_SETUP = {"username": "alice", "display_name": "Alice", "password": PASSWORD}
BOB = {"username": "bob", "display_name": "Bob", "password": PASSWORD}


def set_up_as_alice(client: TestClient) -> dict[str, object]:
    """Create Alice as the first admin; the client is then signed in as her."""
    response = client.post("/api/setup", json=ALICE_SETUP)
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


def add_bob(client: TestClient) -> int:
    """As the signed-in admin, create Bob as a member; return his id."""
    response = client.post("/api/accounts", json=BOB)
    assert response.status_code == 201, response.text
    account_id: int = response.json()["id"]
    return account_id


def sign_in(client: TestClient, username: str) -> None:
    """Sign the client in as `username`, replacing any session it had."""
    response = client.post("/api/session", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200, response.text
