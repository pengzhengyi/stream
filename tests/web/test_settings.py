"""The settings API: everyone reads the settings; an admin replaces them at the revision read."""

from fastapi.testclient import TestClient

from tests.support.api import add_bob, set_up_as_alice, sign_in

TWENTY_GIB = 20 * 1024**3


def test_settings_never_saved_read_as_no_limit_at_revision_0(client: TestClient) -> None:
    set_up_as_alice(client)

    response = client.get("/api/settings")

    assert response.json() == {
        "storage_limit": None,
        "removal_order": "least_favorite",
        "revision": 0,
    }


def test_an_admin_saves_a_limit_at_the_revision_read(client: TestClient) -> None:
    set_up_as_alice(client)

    saved = client.put("/api/settings", json={"storage_limit": TWENTY_GIB, "revision": 0})

    assert (saved.status_code, saved.json()["storage_limit"], saved.json()["revision"]) == (
        200,
        TWENTY_GIB,
        1,
    )
    assert client.get("/api/settings").json() == saved.json()


def test_saving_at_a_revision_someone_saved_since_is_a_conflict(client: TestClient) -> None:
    set_up_as_alice(client)
    client.put("/api/settings", json={"storage_limit": TWENTY_GIB, "revision": 0})

    stale = client.put("/api/settings", json={"storage_limit": 0, "revision": 0})

    assert stale.status_code == 409
    assert "revision 0" in stale.json()["detail"]
    assert client.get("/api/settings").json()["storage_limit"] == TWENTY_GIB


def test_a_member_reads_the_settings_but_cannot_change_them(client: TestClient) -> None:
    set_up_as_alice(client)
    add_bob(client)
    sign_in(client, "bob")

    read = client.get("/api/settings")
    changed = client.put("/api/settings", json={"storage_limit": 0, "revision": 0})

    assert (read.status_code, changed.status_code) == (200, 403)


def test_a_negative_limit_is_refused(client: TestClient) -> None:
    set_up_as_alice(client)

    response = client.put("/api/settings", json={"storage_limit": -1, "revision": 0})

    assert response.status_code == 422
