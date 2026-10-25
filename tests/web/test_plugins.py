"""The plugins API: features for every signed-in Account, plugin states for admins."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application.accounts import AccountService
from medleyplay.application.catalog import CatalogService
from medleyplay.application.jobs import JobService
from medleyplay.web.app import create_app
from medleyplay.web.deps import Services
from tests.conftest import TEST_HOST
from tests.support.api import add_bob, set_up_as_alice, sign_in
from tests.support.fakes import FakeClock
from tests.support.hosts import started_plugins


@pytest.fixture
def plugin_client(
    units: sessionmaker[Session],
    clock: FakeClock,
    accounts: AccountService,
    catalog: CatalogService,
    jobs: JobService,
) -> Iterator[TestClient]:
    """A client of a server with the test plugins `parrot` and `broken-import` on."""
    with started_plugins(units, clock, "parrot", "broken-import") as plugins:
        app = create_app(Services(accounts, catalog, plugins, jobs), allowed_hosts=[TEST_HOST])
        with TestClient(app, base_url=f"http://{TEST_HOST}") as test_client:
            yield test_client


def test_the_features_list_the_keys_that_answer_calls(plugin_client: TestClient) -> None:
    set_up_as_alice(plugin_client)

    response = plugin_client.get("/api/features")

    assert response.json() == {"multiple_accounts": True, "providers": {"echo": ["parrot"]}}


def test_the_features_need_a_sign_in(plugin_client: TestClient) -> None:
    assert plugin_client.get("/api/features").status_code == 401


def test_without_plugins_no_extension_point_has_keys(client: TestClient) -> None:
    set_up_as_alice(client)

    assert client.get("/api/features").json()["providers"] == {}


def test_an_admin_sees_each_plugins_state(plugin_client: TestClient) -> None:
    set_up_as_alice(plugin_client)

    plugins = {plugin["name"]: plugin for plugin in plugin_client.get("/api/plugins").json()}

    assert plugins["parrot"] == {
        "name": "parrot",
        "state": "on",
        "reason": "",
        "keys": {"echo": ["parrot"]},
    }
    assert plugins["broken-import"]["state"] == "quarantined"
    assert plugins["mynah"]["state"] == "off"


def test_a_member_cannot_see_the_plugins(plugin_client: TestClient) -> None:
    set_up_as_alice(plugin_client)
    add_bob(plugin_client)
    sign_in(plugin_client, "bob")

    assert plugin_client.get("/api/plugins").status_code == 403


def test_resetting_a_plugin_answers_its_state(plugin_client: TestClient) -> None:
    set_up_as_alice(plugin_client)

    response = plugin_client.post("/api/plugins/parrot/reset")

    assert response.status_code == 200
    assert response.json()["state"] == "on"


def test_resetting_a_plugin_that_does_not_exist_is_not_found(plugin_client: TestClient) -> None:
    set_up_as_alice(plugin_client)

    assert plugin_client.post("/api/plugins/bilibili/reset").status_code == 404
