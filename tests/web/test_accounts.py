"""The Accounts API, over HTTP with the session cookie."""

from fastapi.testclient import TestClient

from tests.support.api import ALICE_SETUP, BOB, add_bob, set_up_as_alice, sign_in
from tests.support.factories import PASSWORD


def test_setup_reports_whether_the_first_admin_exists(client: TestClient) -> None:
    before = client.get("/api/setup").json()
    set_up_as_alice(client)

    after = client.get("/api/setup").json()
    assert (before["set_up"], after["set_up"]) == (False, True)
    assert after["multiple_accounts"]


def test_setting_up_creates_an_admin_and_signs_the_browser_in(client: TestClient) -> None:
    created = set_up_as_alice(client)

    me = client.get("/api/me")

    assert created == {"id": 1, "username": "alice", "display_name": "Alice", "role": "admin"}
    assert me.json() == created


def test_the_session_cookie_is_http_only_and_same_site_lax(client: TestClient) -> None:
    response = client.post("/api/setup", json=ALICE_SETUP)

    cookie = response.headers["set-cookie"].lower()
    assert cookie.startswith("medleyplay_session=")
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert PASSWORD not in cookie


def test_setting_up_twice_is_a_conflict(client: TestClient) -> None:
    set_up_as_alice(client)

    response = client.post("/api/setup", json=BOB)

    assert response.status_code == 409
    assert "already set up" in response.json()["detail"]


def test_without_a_session_the_api_answers_401(client: TestClient) -> None:
    response = client.get("/api/me")

    assert (response.status_code, response.json()) == (401, {"detail": "Sign in first."})


def test_a_wrong_password_answers_401_without_saying_which_part_was_wrong(
    client: TestClient,
) -> None:
    set_up_as_alice(client)

    response = client.post("/api/session", json={"username": "alice", "password": "nope-nope"})

    assert response.status_code == 401
    assert response.json() == {"detail": "The username or password is wrong."}


def test_repeated_failed_sign_ins_answer_429_with_retry_after(client: TestClient) -> None:
    set_up_as_alice(client)
    wrong = {"username": "alice", "password": "nope-nope"}
    for _ in range(5):
        client.post("/api/session", json=wrong)

    response = client.post("/api/session", json=ALICE_SETUP)

    assert response.status_code == 429
    assert int(response.headers["retry-after"]) == 15 * 60


def test_signing_out_ends_the_session_and_can_be_repeated(client: TestClient) -> None:
    set_up_as_alice(client)

    first, second = client.delete("/api/session"), client.delete("/api/session")

    assert (first.status_code, second.status_code) == (204, 204)
    assert client.get("/api/me").status_code == 401


def test_signing_out_everywhere_ends_other_browsers_too(client: TestClient) -> None:
    set_up_as_alice(client)
    phone = client.cookies.get("medleyplay_session")
    sign_in(client, "alice")

    response = client.delete("/api/sessions")

    assert response.status_code == 204
    client.cookies.set("medleyplay_session", str(phone))
    assert client.get("/api/me").status_code == 401


def test_an_admin_manages_accounts_end_to_end(client: TestClient) -> None:
    set_up_as_alice(client)
    bob_id = add_bob(client)

    promoted = client.put(f"/api/accounts/{bob_id}/role", json={"role": "admin"})
    listed = client.get("/api/accounts").json()
    deleted = client.delete(f"/api/accounts/{bob_id}")

    assert promoted.json()["role"] == "admin"
    assert [account["username"] for account in listed] == ["alice", "bob"]
    assert deleted.status_code == 204
    assert [a["username"] for a in client.get("/api/accounts").json()] == ["alice"]


def test_a_member_managing_accounts_answers_403(client: TestClient) -> None:
    set_up_as_alice(client)
    add_bob(client)
    sign_in(client, "bob")

    response = client.post("/api/accounts", json={**BOB, "username": "carol"})

    assert response.status_code == 403


def test_demoting_the_last_admin_answers_409(client: TestClient) -> None:
    set_up_as_alice(client)

    response = client.put("/api/accounts/1/role", json={"role": "member"})

    assert response.status_code == 409


def test_an_invalid_username_answers_422_naming_the_rule(client: TestClient) -> None:
    response = client.post("/api/setup", json={**ALICE_SETUP, "username": "has space"})

    assert response.status_code == 422
    assert "1-32 letters" in response.json()["detail"]


def test_an_unknown_account_answers_404(client: TestClient) -> None:
    set_up_as_alice(client)

    assert client.put("/api/accounts/404/role", json={"role": "admin"}).status_code == 404
