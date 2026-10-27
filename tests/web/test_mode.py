"""The Mode API: any signed-in Account sees the Mode; an admin changes its settings."""

from datetime import datetime

from fastapi.testclient import TestClient

from medleyplay.application.mode import ModeService
from medleyplay.domain.mode import FIRST_WAIT, UNREAD
from tests.support.api import add_bob, set_up_as_alice, sign_in
from tests.support.factories import NetworkFactory
from tests.support.fakes import FakeClock, FakeNetwork


def _time(text: object) -> datetime:
    assert isinstance(text, str)
    return datetime.fromisoformat(text)


def test_the_mode_is_offline_until_the_server_has_checked(client: TestClient) -> None:
    set_up_as_alice(client)

    body = client.get("/api/mode").json()

    assert (body["setting"], body["online"], body["reason"], body["network"]) == (
        "auto",
        False,
        "unreachable",
        None,
    )


def test_the_mode_says_when_it_goes_online_while_settling(
    client: TestClient, mode: ModeService, clock: FakeClock
) -> None:
    set_up_as_alice(client)
    mode.tick()

    body = client.get("/api/mode").json()

    assert (body["reason"], _time(body["online_at"])) == ("settling", clock() + FIRST_WAIT)


def test_the_mode_online_on_the_home_wifi(
    client: TestClient, mode: ModeService, clock: FakeClock
) -> None:
    set_up_as_alice(client)
    mode.tick()
    clock.advance(FIRST_WAIT)
    mode.tick()

    body = client.get("/api/mode").json()

    assert {**body, "since": _time(body["since"]), "checked_at": _time(body["checked_at"])} == {
        "setting": "auto",
        "online": True,
        "reason": "online",
        "network": {"kind": "wifi", "metered_as": None, "hotspot_like": False},
        "since": clock(),
        "checked_at": clock() - FIRST_WAIT,
        "online_at": None,
    }


def test_the_settings_never_saved_are_auto_with_nothing_marked(client: TestClient) -> None:
    set_up_as_alice(client)

    response = client.get("/api/mode/settings")

    assert response.json() == {"setting": "auto", "metered": [], "revision": 0}


def test_an_admin_sets_the_mode_offline_and_it_is_at_once(client: TestClient) -> None:
    set_up_as_alice(client)

    saved = client.put("/api/mode/settings", json={"setting": "offline", "revision": 0})

    assert (saved.status_code, saved.json()) == (
        200,
        {"setting": "offline", "metered": [], "revision": 1},
    )
    assert client.get("/api/mode").json()["reason"] == "set_offline"


def test_setting_the_mode_at_a_revision_saved_since_is_a_conflict(client: TestClient) -> None:
    set_up_as_alice(client)
    client.put("/api/mode/settings", json={"setting": "offline", "revision": 0})

    response = client.put("/api/mode/settings", json={"setting": "online", "revision": 0})

    assert response.status_code == 409


def test_a_member_sees_the_mode_but_cant_change_it(client: TestClient) -> None:
    set_up_as_alice(client)
    add_bob(client)
    sign_in(client, "bob")

    seen = client.get("/api/mode")
    changed = client.put("/api/mode/settings", json={"setting": "offline", "revision": 0})
    marked = client.post("/api/mode/metered", json={"name": "Hotspot"})

    assert (seen.status_code, changed.status_code, marked.status_code) == (200, 403, 403)


def test_an_admin_marks_the_network_the_server_is_on_metered(
    client: TestClient, network: FakeNetwork
) -> None:
    set_up_as_alice(client)
    network.network = NetworkFactory.iphone_hotspot()

    marked = client.post("/api/mode/metered", json={"name": "iPhone hotspot"})

    assert (marked.status_code, marked.json()) == (
        200,
        {"id": 1, "name": "iPhone hotspot", "subnet": "172.20.10.0/28", "hotspot_like": True},
    )
    mode = client.get("/api/mode").json()
    assert (mode["reason"], mode["network"]["metered_as"]) == ("metered", "iPhone hotspot")
    assert client.get("/api/mode/settings").json()["metered"] == [marked.json()]


def test_a_network_the_server_cant_tell_apart_cant_be_marked(
    client: TestClient, network: FakeNetwork
) -> None:
    set_up_as_alice(client)
    network.network = UNREAD

    response = client.post("/api/mode/metered", json={"name": "Hotspot"})

    assert response.status_code == 409


def test_removing_a_mark_twice_answers_no_content_both_times(client: TestClient) -> None:
    set_up_as_alice(client)
    marked = client.post("/api/mode/metered", json={"name": "Hotspot"}).json()

    first = client.delete(f"/api/mode/metered/{marked['id']}")
    second = client.delete(f"/api/mode/metered/{marked['id']}")

    assert (first.status_code, second.status_code) == (204, 204)
    assert client.get("/api/mode/settings").json()["metered"] == []


def test_the_mode_needs_a_signed_in_account(client: TestClient) -> None:
    assert client.get("/api/mode").status_code == 401
