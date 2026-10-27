"""The events API: a signed-in browser hears each change of a Job as Server-Sent Events."""

import dataclasses
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application.accounts import AccountService
from medleyplay.application.events import Events
from medleyplay.application.mode import ModeService
from medleyplay.domain.jobs import JobState
from medleyplay.web import events as events_api
from medleyplay.web.app import create_app
from medleyplay.web.deps import SESSION_COOKIE, Services
from tests.conftest import TEST_HOST
from tests.support.api import set_up_as_alice
from tests.support.fakes import FakeClock, FakeInternet, FakeNetwork
from tests.support.jobs import Jobs, running_jobs
from tests.support.programs import EchoJob


@pytest.fixture
def hub() -> Events:
    return Events()


@pytest.fixture
def running(
    units: sessionmaker[Session], clock: FakeClock, tmp_path: Path, hub: Events
) -> Iterator[Jobs]:
    with running_jobs(units, clock, tmp_path / "jobs", events=hub) as jobs:
        yield jobs


@pytest.fixture
def hub_mode(
    units: sessionmaker[Session],
    clock: FakeClock,
    network: FakeNetwork,
    internet: FakeInternet,
    hub: Events,
) -> ModeService:
    """The Mode service, telling the hub of each change as the server's does."""
    return ModeService(units, clock, probe=network, check=internet, on_change=hub.publish_mode)


@pytest.fixture
def events_client(
    running: Jobs, services: Services, hub: Events, hub_mode: ModeService
) -> Iterator[TestClient]:
    plugins = running.runner._plugins  # noqa: SLF001 -- the plugin service the runner uses
    app = create_app(
        dataclasses.replace(
            services, plugins=plugins, jobs=running.service, events=hub, mode=hub_mode
        ),
        allowed_hosts=[TEST_HOST],
    )
    with TestClient(app, base_url=f"http://{TEST_HOST}") as client:
        yield client


def _ready(lines: Iterator[str]) -> None:
    """Read the stream until it says it hears every change."""
    for line in lines:
        if line == "event: ready":
            return
    raise AssertionError


def _job_events(lines: Iterator[str], until_state: str) -> list[dict[str, object]]:
    """Read `job` events from an event stream until one is in `until_state`."""
    heard: list[dict[str, object]] = []
    event = None
    for line in lines:
        if line.startswith("event: "):
            event = line.removeprefix("event: ")
        elif line.startswith("data: ") and event == "job":
            heard.append(json.loads(line.removeprefix("data: ")))
            if heard[-1]["state"] == until_state:
                return heard
    return heard


def _next_mode(lines: Iterator[str]) -> dict[str, object]:
    """Read the stream until a `mode` event, and return the Mode it carries."""
    event = None
    for line in lines:
        if line.startswith("event: "):
            event = line.removeprefix("event: ")
        elif line.startswith("data: ") and event == "mode":
            body: dict[str, object] = json.loads(line.removeprefix("data: "))
            return body
    raise AssertionError


def _progress_heard(lines: Iterator[str]) -> None:
    """Read the stream until a `job` event carries the Job's progress."""
    event = None
    for line in lines:
        if line.startswith("event: "):
            event = line.removeprefix("event: ")
        elif (
            line.startswith("data: ")
            and event == "job"
            and json.loads(line.removeprefix("data: "))["progress"] is not None
        ):
            return
    raise AssertionError


def test_a_browser_hears_a_job_change_until_it_succeeds(
    events_client: TestClient, running: Jobs
) -> None:
    alice = set_up_as_alice(events_client)

    with events_client.stream("GET", "/api/events") as stream:
        assert stream.headers["content-type"].startswith("text/event-stream")
        lines = stream.iter_lines()
        _ready(lines)
        job = running.submit(EchoJob(text="hi", steps=2), by=int(str(alice["id"])))
        heard = _job_events(lines, "succeeded")

    # Each event is the Job as it stands when sent, so a quick Job may skip states.
    assert {each["id"] for each in heard} == {job.id}
    assert heard[-1]["state"] == "succeeded"


def test_a_stream_ends_when_its_session_does(
    events_client: TestClient, accounts: AccountService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(events_api, "SESSION_CHECK_SECONDS", 0.05)
    set_up_as_alice(events_client)

    with events_client.stream("GET", "/api/events") as stream:
        lines = stream.iter_lines()
        _ready(lines)
        accounts.sign_out(events_client.cookies[SESSION_COOKIE])
        remaining = list(lines)

    assert not any(line.startswith("event: job") for line in remaining)


def test_a_busy_stream_ends_when_its_session_does_without_waiting_for_quiet(
    events_client: TestClient,
    running: Jobs,
    accounts: AccountService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Progress arrives four times a second, so the stream is never quiet for half a second.
    monkeypatch.setattr(events_api, "SESSION_CHECK_SECONDS", 0.5)
    alice = set_up_as_alice(events_client)

    with events_client.stream("GET", "/api/events") as stream:
        lines = stream.iter_lines()
        _ready(lines)
        job = running.submit(
            EchoJob(text="hi", steps=40, step_seconds=0.1), by=int(str(alice["id"]))
        )
        _progress_heard(lines)
        accounts.sign_out(events_client.cookies[SESSION_COOKIE])
        remaining = _job_events(lines, "succeeded")

    assert all(each["state"] != "succeeded" for each in remaining)
    assert running.service.get_job(job.id).job.state is JobState.RUNNING


def test_events_need_a_signed_in_account(client: TestClient) -> None:
    assert client.get("/api/events").status_code == 401


def test_a_browser_hears_the_mode_when_the_stream_opens_and_when_it_changes(
    events_client: TestClient, hub_mode: ModeService
) -> None:
    set_up_as_alice(events_client)

    with events_client.stream("GET", "/api/events") as stream:
        lines = stream.iter_lines()
        _ready(lines)
        opened = _next_mode(lines)
        hub_mode.tick()
        changed = _next_mode(lines)

    assert (opened["reason"], changed["reason"]) == ("unreachable", "settling")
