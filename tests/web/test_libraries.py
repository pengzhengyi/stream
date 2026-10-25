"""The Libraries API: admins register, scan, and remove Libraries; everyone sees them."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application.accounts import AccountService
from medleyplay.domain.jobs import JobId, JobState
from medleyplay.web.app import create_app
from medleyplay.web.deps import Services
from tests.conftest import TEST_HOST
from tests.support.api import add_bob, set_up_as_alice, sign_in
from tests.support.audio import Song, folder_of
from tests.support.fakes import FakeClock
from tests.support.libraries import Libraries, running_libraries


@pytest.fixture
def running(units: sessionmaker[Session], clock: FakeClock, tmp_path: Path) -> Iterator[Libraries]:
    with running_libraries(units, clock, tmp_path / "data") as libraries:
        yield libraries


@pytest.fixture
def library_client(running: Libraries, accounts: AccountService) -> Iterator[TestClient]:
    services = Services(
        accounts, running.catalog, running.plugins, running.jobs, running.service, running.playback
    )
    with TestClient(
        create_app(services, allowed_hosts=[TEST_HOST]), base_url=f"http://{TEST_HOST}"
    ) as client:
        yield client


def _music(tmp_path: Path) -> str:
    return str(folder_of(tmp_path / "Music", {"a.wav": Song("A"), "b.wav": Song("B")}))


def test_registering_a_library_answers_it_with_its_scan(
    library_client: TestClient, running: Libraries, tmp_path: Path
) -> None:
    set_up_as_alice(library_client)

    response = library_client.post(
        "/api/libraries", json={"name": "Music", "kind": "folder", "path": _music(tmp_path)}
    )
    body = response.json()
    running.wait_for(JobId(body["scan"]["id"]), JobState.SUCCEEDED)
    [library] = library_client.get("/api/libraries").json()
    titles = sorted(track["title"] for track in library_client.get("/api/tracks").json())

    assert response.status_code == 201
    assert (body["library"]["name"], body["scan"]["kind"]) == ("Music", "scan_library")
    assert (library["state"], library["file_count"]) == ("online", 2)
    assert titles == ["A", "B"]


def test_registering_a_root_again_answers_200_without_a_scan(
    library_client: TestClient, tmp_path: Path
) -> None:
    set_up_as_alice(library_client)
    body = {"name": "Music", "kind": "folder", "path": _music(tmp_path)}
    library_client.post("/api/libraries", json=body)

    again = library_client.post("/api/libraries", json=body)

    assert (again.status_code, again.json()["scan"]) == (200, None)


def test_an_unreadable_root_is_refused(library_client: TestClient, tmp_path: Path) -> None:
    set_up_as_alice(library_client)

    response = library_client.post(
        "/api/libraries", json={"name": "Music", "kind": "folder", "path": str(tmp_path / "absent")}
    )

    assert response.status_code == 422


def test_scanning_answers_the_scan_and_a_full_scan_is_asked_for_with_a_flag(
    library_client: TestClient, running: Libraries, tmp_path: Path
) -> None:
    set_up_as_alice(library_client)
    body = library_client.post(
        "/api/libraries", json={"name": "Music", "kind": "folder", "path": _music(tmp_path)}
    ).json()
    running.wait_for(JobId(body["scan"]["id"]), JobState.SUCCEEDED)

    scan = library_client.post(f"/api/libraries/{body['library']['id']}/scan?full=true").json()

    assert scan["kind"] == "scan_library"
    assert scan["id"] != body["scan"]["id"]


def test_removing_a_library_answers_204_twice(library_client: TestClient, tmp_path: Path) -> None:
    set_up_as_alice(library_client)
    body = library_client.post(
        "/api/libraries", json={"name": "Music", "kind": "folder", "path": _music(tmp_path)}
    ).json()
    library_id = body["library"]["id"]

    first = library_client.delete(f"/api/libraries/{library_id}")
    second = library_client.delete(f"/api/libraries/{library_id}")

    assert (first.status_code, second.status_code) == (204, 204)
    assert library_client.get("/api/libraries").json() == []


def test_a_member_sees_libraries_but_cannot_register_one(
    library_client: TestClient, tmp_path: Path
) -> None:
    set_up_as_alice(library_client)
    add_bob(library_client)
    sign_in(library_client, "bob")

    refused = library_client.post(
        "/api/libraries", json={"name": "Music", "kind": "folder", "path": _music(tmp_path)}
    )

    assert refused.status_code == 403
    assert library_client.get("/api/libraries").status_code == 200


def test_scanning_a_library_that_does_not_exist_is_not_found(library_client: TestClient) -> None:
    set_up_as_alice(library_client)

    assert library_client.post("/api/libraries/404/scan").status_code == 404
