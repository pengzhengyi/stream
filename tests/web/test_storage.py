"""The storage API: the space in use, what the policy wants, and an admin's preview of a limit."""

from fastapi.testclient import TestClient

from tests.support.api import add_bob, set_up_as_alice, sign_in


def test_an_empty_household_uses_nothing_and_wants_nothing(client: TestClient) -> None:
    set_up_as_alice(client)

    storage = client.get("/api/storage").json()

    assert (storage["limit"], storage["downloads"], storage["cache"], storage["wanted"]) == (
        None,
        0,
        0,
        0,
    )
    assert (storage["wanted_by_account"], storage["error"], storage["preview"]) == ([], None, None)
    assert storage["free"] > 0
    assert storage["min_free"] >= 2 * 1024**3


def test_an_admin_previews_a_plan_at_another_limit(client: TestClient) -> None:
    set_up_as_alice(client)

    storage = client.get("/api/storage", params={"limit": 0}).json()

    assert storage["preview"] == {"removals": [], "starts": [], "shortfalls": []}


def test_a_member_sees_the_storage_but_cannot_preview(client: TestClient) -> None:
    set_up_as_alice(client)
    add_bob(client)
    sign_in(client, "bob")

    seen = client.get("/api/storage")
    previewed = client.get("/api/storage", params={"limit": 0})

    assert (seen.status_code, previewed.status_code) == (200, 403)


def test_the_storage_is_for_signed_in_accounts(client: TestClient) -> None:
    response = client.get("/api/storage")

    assert response.status_code == 401
