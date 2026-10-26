"""The preferences API: each Account reads and saves its own, at the revision read."""

from fastapi.testclient import TestClient

from tests.support.api import add_bob, set_up_as_alice, sign_in

PLAY_ON_K = {"toggle": ["space", "k"], "mute": ["m"]}


def test_preferences_never_saved_read_as_no_shortcuts_at_revision_0(client: TestClient) -> None:
    set_up_as_alice(client)

    response = client.get("/api/me/preferences")

    assert response.json() == {"shortcuts": None, "revision": 0}


def test_an_account_saves_its_shortcuts_at_the_revision_read(client: TestClient) -> None:
    set_up_as_alice(client)

    saved = client.put("/api/me/preferences", json={"shortcuts": PLAY_ON_K, "revision": 0})

    assert (saved.status_code, saved.json()) == (200, {"shortcuts": PLAY_ON_K, "revision": 1})
    assert client.get("/api/me/preferences").json() == saved.json()


def test_a_member_has_preferences_of_their_own(client: TestClient) -> None:
    set_up_as_alice(client)
    client.put("/api/me/preferences", json={"shortcuts": PLAY_ON_K, "revision": 0})
    add_bob(client)
    sign_in(client, "bob")

    response = client.get("/api/me/preferences")

    assert response.json() == {"shortcuts": None, "revision": 0}


def test_saving_at_a_revision_saved_since_is_a_conflict(client: TestClient) -> None:
    set_up_as_alice(client)
    client.put("/api/me/preferences", json={"shortcuts": PLAY_ON_K, "revision": 0})

    stale = client.put("/api/me/preferences", json={"shortcuts": {}, "revision": 0})

    assert stale.status_code == 409
    assert client.get("/api/me/preferences").json()["shortcuts"] == PLAY_ON_K


def test_keys_not_as_the_page_writes_them_are_refused(client: TestClient) -> None:
    set_up_as_alice(client)

    response = client.put(
        "/api/me/preferences", json={"shortcuts": {"toggle": ["Space Bar"]}, "revision": 0}
    )

    assert response.status_code == 422


def test_reading_preferences_needs_a_signed_in_account(client: TestClient) -> None:
    response = client.get("/api/me/preferences")

    assert response.status_code == 401
