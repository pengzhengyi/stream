"""The linked accounts API: saving a login, seeing only its state, and removing it."""

import dataclasses
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application.linked_accounts import LinkedAccountService
from medleyplay.web.app import create_app
from medleyplay.web.deps import Services
from tests.conftest import TEST_HOST
from tests.support.api import add_bob, set_up_as_alice, sign_in
from tests.support.fakes import FakeClock, MemorySecrets
from tests.support.hosts import started_plugins

COOKIES = (
    "# Netscape HTTP Cookie File\n"
    ".bilibili.com\tTRUE\t/\tTRUE\t0\tSESSDATA\tabc123\n"
    ".bilibili.com\tTRUE\t/\tFALSE\t0\tbili_jct\ttoken\n"
)


@pytest.fixture
def site_client(
    units: sessionmaker[Session], clock: FakeClock, services: Services, secrets: MemorySecrets
) -> Iterator[TestClient]:
    """A client of a server with the test plugin `tube` answering for `bilibili`."""
    with started_plugins(units, clock, "tube") as plugins:
        linked = LinkedAccountService(units, clock, plugins, secrets)
        app = create_app(
            dataclasses.replace(services, plugins=plugins, linked=linked),
            allowed_hosts=[TEST_HOST],
        )
        with TestClient(app, base_url=f"http://{TEST_HOST}") as client:
            yield client


def test_a_saved_login_shows_only_its_state(site_client: TestClient, clock: FakeClock) -> None:
    set_up_as_alice(site_client)

    saved = site_client.put("/api/me/linked-accounts/bilibili", json={"cookies": COOKIES})
    listed = site_client.get("/api/me/linked-accounts")

    expected = {
        "site": "bilibili",
        "state": "valid",
        "expires_at": None,
        "saved_at": clock.now.isoformat().replace("+00:00", "Z"),
    }
    assert (saved.status_code, saved.json()) == (200, expected)
    assert listed.json() == [expected]
    assert "abc123" not in saved.text + listed.text


def test_a_file_without_a_session_is_refused_with_why(site_client: TestClient) -> None:
    set_up_as_alice(site_client)

    response = site_client.put(
        "/api/me/linked-accounts/bilibili", json={"cookies": "# Netscape HTTP Cookie File\n"}
    )

    assert response.status_code == 422
    assert "no session" in response.json()["detail"]


def test_a_site_no_plugin_reads_logins_for_is_not_found(site_client: TestClient) -> None:
    set_up_as_alice(site_client)

    response = site_client.put("/api/me/linked-accounts/youtube", json={"cookies": COOKIES})

    assert response.status_code == 404


def test_removing_a_login_answers_204_also_when_there_is_none(
    site_client: TestClient, secrets: MemorySecrets
) -> None:
    set_up_as_alice(site_client)
    site_client.put("/api/me/linked-accounts/bilibili", json={"cookies": COOKIES})

    first = site_client.delete("/api/me/linked-accounts/bilibili")
    again = site_client.delete("/api/me/linked-accounts/bilibili")

    assert (first.status_code, again.status_code) == (204, 204)
    assert site_client.get("/api/me/linked-accounts").json() == []
    assert secrets.items == {}


def test_each_account_sees_only_its_own_logins(site_client: TestClient) -> None:
    set_up_as_alice(site_client)
    site_client.put("/api/me/linked-accounts/bilibili", json={"cookies": COOKIES})
    add_bob(site_client)

    sign_in(site_client, "bob")

    assert site_client.get("/api/me/linked-accounts").json() == []


def test_deleting_an_account_forgets_its_logins(
    site_client: TestClient, secrets: MemorySecrets
) -> None:
    set_up_as_alice(site_client)
    bob = add_bob(site_client)
    sign_in(site_client, "bob")
    site_client.put("/api/me/linked-accounts/bilibili", json={"cookies": COOKIES})
    sign_in(site_client, "alice")

    site_client.delete(f"/api/accounts/{bob}")

    assert secrets.items == {}


def test_a_keychain_that_does_not_answer_is_unavailable(
    site_client: TestClient, secrets: MemorySecrets
) -> None:
    set_up_as_alice(site_client)
    secrets.unavailable = True

    response = site_client.put("/api/me/linked-accounts/bilibili", json={"cookies": COOKIES})

    assert response.status_code == 503
    assert "Keychain" in response.json()["detail"]


def test_linked_accounts_need_a_signed_in_account(client: TestClient) -> None:
    assert client.get("/api/me/linked-accounts").status_code == 401
