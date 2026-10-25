"""The Jobs API: every signed-in Account sees the Jobs; owners and admins change them."""

import dataclasses
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.domain.accounts import AccountId
from medleyplay.domain.jobs import JobState
from medleyplay.web.app import create_app
from medleyplay.web.deps import Services
from tests.conftest import TEST_HOST
from tests.support.api import add_bob, set_up_as_alice, sign_in
from tests.support.fakes import FakeClock
from tests.support.jobs import Jobs, running_jobs
from tests.support.programs import EchoJob


@pytest.fixture
def running(units: sessionmaker[Session], clock: FakeClock, tmp_path: Path) -> Iterator[Jobs]:
    with running_jobs(units, clock, tmp_path / "jobs") as jobs:
        yield jobs


@pytest.fixture
def jobs_client(running: Jobs, services: Services) -> Iterator[TestClient]:
    plugins = running.runner._plugins  # noqa: SLF001 -- the plugin service the runner uses
    app = create_app(
        dataclasses.replace(services, plugins=plugins, jobs=running.service),
        allowed_hosts=[TEST_HOST],
    )
    with TestClient(app, base_url=f"http://{TEST_HOST}") as test_client:
        yield test_client


def test_a_finished_job_is_listed_with_its_outcome(jobs_client: TestClient, running: Jobs) -> None:
    alice = set_up_as_alice(jobs_client)
    job = running.submit(EchoJob(text="hi"), by=int(str(alice["id"])))
    running.wait_for(job.id, JobState.SUCCEEDED)

    listed = jobs_client.get("/api/jobs").json()

    assert [(j["id"], j["kind"], j["state"], j["progress"]) for j in listed] == [
        (job.id, "echo", "succeeded", None)
    ]
    assert jobs_client.get(f"/api/jobs/{job.id}").json()["requested_by"] == alice["id"]


def test_a_running_job_shows_its_progress(jobs_client: TestClient, running: Jobs) -> None:
    set_up_as_alice(jobs_client)
    job = running.submit(EchoJob(text="slow", steps=2, step_seconds=1))
    running.wait_for(job.id, JobState.RUNNING, until=lambda view: view.progress is not None)

    progress = jobs_client.get(f"/api/jobs/{job.id}").json()["progress"]

    assert progress == {"fraction": 0.5, "message": "Step 1"}


def test_the_jobs_need_a_sign_in(jobs_client: TestClient) -> None:
    assert jobs_client.get("/api/jobs").status_code == 401


def test_a_member_cancels_their_own_job_but_not_another_accounts(
    jobs_client: TestClient, running: Jobs
) -> None:
    alice = set_up_as_alice(jobs_client)
    bob = add_bob(jobs_client)
    alices = running.submit(
        EchoJob(text="x", steps=1, fail="hang"), target="echo:1", by=int(str(alice["id"]))
    )
    bobs = running.submit(EchoJob(text="x", steps=1, fail="hang"), target="echo:2", by=bob)
    sign_in(jobs_client, "bob")

    refused = jobs_client.post(f"/api/jobs/{alices.id}/cancel")
    cancelled = jobs_client.post(f"/api/jobs/{bobs.id}/cancel")

    assert refused.status_code == 403
    assert cancelled.json()["state"] == "cancelled"


def test_retrying_answers_the_new_job(jobs_client: TestClient, running: Jobs) -> None:
    set_up_as_alice(jobs_client)
    job = running.submit(EchoJob(text="boom", fail="raise"))
    running.wait_for(job.id, JobState.FAILED)

    retried = jobs_client.post(f"/api/jobs/{job.id}/retry").json()

    assert retried["id"] != job.id
    assert retried["target"] == job.target


def test_a_job_that_does_not_exist_is_not_found(jobs_client: TestClient) -> None:
    set_up_as_alice(jobs_client)

    assert jobs_client.get("/api/jobs/404").status_code == 404


def test_retrying_a_job_that_has_not_failed_is_a_conflict(
    jobs_client: TestClient, running: Jobs
) -> None:
    alice = set_up_as_alice(jobs_client)
    job = running.submit(EchoJob(text="x", steps=1, fail="hang"), by=int(str(alice["id"])))

    assert jobs_client.post(f"/api/jobs/{job.id}/retry").status_code == 409
    assert AccountId(int(str(alice["id"]))) == job.requested_by
