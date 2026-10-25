"""Jobs run in real Job processes: success, every way they fail, cancelling, and retrying."""

import fcntl
import os
import signal
import subprocess  # nosec B404 -- stand-in Job processes
import time
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application.accounts import AccountService
from medleyplay.application.job_runner import FIRST_RETRY, NETWORK_RETRY, JobProcesses, JobRunner
from medleyplay.application.jobs import JobService
from medleyplay.application.plugins import PluginService
from medleyplay.domain.accounts import Account
from medleyplay.domain.errors import ConflictError, ForbiddenError, NotFoundError
from medleyplay.domain.jobs import JobId, JobState, Progress
from medleyplay.persistence.schema import JobRow
from medleyplay.plugin_host.process import HostCommand
from tests.support.echo import Say
from tests.support.factories import NewAccountFactory
from tests.support.fakes import FakeClock
from tests.support.jobs import running_jobs
from tests.support.programs import EchoJob, echo_kind


@pytest.fixture
def household(accounts: AccountService) -> tuple[Account, Account]:
    """Return Alice, the admin, and Bob, a member."""
    alice = accounts.create_first_admin(NewAccountFactory.admin()).account
    return alice, accounts.create_account(alice, NewAccountFactory.member())


def test_a_job_runs_its_program_and_the_completion_applies_its_result(
    units: sessionmaker[Session], clock: FakeClock, tmp_path: Path
) -> None:
    with running_jobs(units, clock, tmp_path / "jobs") as jobs:
        job = jobs.submit(EchoJob(text="hello", say=Say(text="from the parrot")))
        done = jobs.wait_for(job.id, JobState.SUCCEEDED)

    assert jobs.completed == ["from the parrot"]
    assert (done.job.failure_kind, done.job.attempts, done.progress) == (None, 0, None)
    assert done.job.finished_at == clock()
    assert list((tmp_path / "jobs").iterdir()) == []


def test_a_running_job_shows_its_progress(
    units: sessionmaker[Session], clock: FakeClock, tmp_path: Path
) -> None:
    with running_jobs(units, clock, tmp_path / "jobs") as jobs:
        job = jobs.submit(EchoJob(text="slow", steps=2, step_seconds=1))
        running = jobs.wait_for(
            job.id, JobState.RUNNING, until=lambda view: view.progress is not None
        )

    assert running.progress == Progress(0.5, "Step 1")


def test_submitting_the_same_target_again_returns_the_active_job(
    units: sessionmaker[Session], clock: FakeClock, tmp_path: Path
) -> None:
    with running_jobs(units, clock, tmp_path / "jobs", start=False) as jobs:
        first = jobs.submit(EchoJob(text="a"))
        again = jobs.submit(EchoJob(text="b"))
        other = jobs.submit(EchoJob(text="c"), target="echo:2")

    assert again == first
    assert other.id != first.id


def test_submitting_a_kind_the_service_does_not_run_is_refused(
    units: sessionmaker[Session], clock: FakeClock, tmp_path: Path
) -> None:
    with running_jobs(units, clock, tmp_path / "jobs", start=False) as jobs:
        stranger = echo_kind([])

        with pytest.raises(ValueError, match="isn't one this server runs"):
            jobs.service.submit(stranger, "echo:1", EchoJob(text="a"), None)


def test_a_fault_in_the_program_fails_the_job_without_a_retry(
    units: sessionmaker[Session], clock: FakeClock, tmp_path: Path
) -> None:
    with running_jobs(units, clock, tmp_path / "jobs") as jobs:
        job = jobs.submit(EchoJob(text="boom", fail="raise"))
        failed = jobs.wait_for(job.id, JobState.FAILED)

    assert (failed.job.failure_kind, failed.job.failure_message) == ("program", "ValueError: boom")
    assert failed.job.attempts == 0


def test_a_plugin_fault_retries_with_a_growing_delay_then_fails(
    units: sessionmaker[Session], clock: FakeClock, tmp_path: Path
) -> None:
    request = EchoJob(text="x", say=Say(text="boom", raises="value"))
    with running_jobs(units, clock, tmp_path / "jobs") as jobs:
        job = jobs.submit(request)
        first = jobs.wait_for(job.id, JobState.QUEUED, until=lambda view: view.job.attempts == 1)
        jobs.retry_time_comes(FIRST_RETRY)
        second = jobs.wait_for(job.id, JobState.QUEUED, until=lambda view: view.job.attempts == 2)
        jobs.retry_time_comes(FIRST_RETRY * 2)
        failed = jobs.wait_for(job.id, JobState.FAILED)

    assert (first.job.failure_kind, first.job.failure_message) == ("plugin", "ValueError: boom")
    assert second.job.attempts == 2
    assert failed.job.attempts == 3


def test_a_plugin_fault_the_program_catches_does_not_fail_the_job(
    units: sessionmaker[Session], clock: FakeClock, tmp_path: Path
) -> None:
    request = EchoJob(text="x", say=Say(text="boom", raises="value"), catch_failure=True)
    with running_jobs(units, clock, tmp_path / "jobs") as jobs:
        job = jobs.submit(request)
        jobs.wait_for(job.id, JobState.SUCCEEDED)

    assert jobs.completed == ["caught"]


def test_a_network_failure_waits_without_counting_an_attempt(
    units: sessionmaker[Session], clock: FakeClock, tmp_path: Path
) -> None:
    request = EchoJob(text="x", say=Say(text="offline", raises="network"))
    with running_jobs(units, clock, tmp_path / "jobs") as jobs:
        job = jobs.submit(request)
        waiting = jobs.wait_for(job.id, JobState.WAITING)
        jobs.retry_time_comes(NETWORK_RETRY)
        again = jobs.wait_for(
            job.id, JobState.WAITING, until=lambda view: view.job.started_at == clock()
        )

    assert (waiting.job.failure_kind, waiting.job.failure_message) == ("network", "offline")
    assert (waiting.job.attempts, again.job.attempts) == (0, 0)


def test_a_login_failure_fails_the_job_at_once(
    units: sessionmaker[Session], clock: FakeClock, tmp_path: Path
) -> None:
    request = EchoJob(text="x", say=Say(text="expired", raises="auth"))
    with running_jobs(units, clock, tmp_path / "jobs") as jobs:
        job = jobs.submit(request)
        failed = jobs.wait_for(job.id, JobState.FAILED)

    assert (failed.job.failure_kind, failed.job.failure_message) == ("auth", "expired")


@pytest.mark.parametrize(
    ("fail", "idle_timeout", "message"),
    [
        ("crash", timedelta(seconds=30), "Its process exited without an outcome."),
        ("hang", timedelta(seconds=2), "It reported nothing for 0:00:02."),
    ],
)
def test_a_job_process_that_crashes_or_hangs_is_a_fault_with_a_retry(
    units: sessionmaker[Session],
    clock: FakeClock,
    tmp_path: Path,
    fail: str,
    idle_timeout: timedelta,
    message: str,
) -> None:
    with running_jobs(units, clock, tmp_path / "jobs", idle_timeout=idle_timeout) as jobs:
        job = jobs.submit(EchoJob.model_validate({"text": "x", "fail": fail}))
        queued = jobs.wait_for(job.id, JobState.QUEUED, until=lambda view: view.job.attempts == 1)

    assert (queued.job.failure_kind, queued.job.failure_message) == ("plugin", message)


def test_a_job_process_past_its_memory_limit_is_a_fault(
    units: sessionmaker[Session], clock: FakeClock, tmp_path: Path
) -> None:
    with running_jobs(units, clock, tmp_path / "jobs", memory_limit=1) as jobs:
        job = jobs.submit(EchoJob(text="x", steps=1))
        queued = jobs.wait_for(job.id, JobState.QUEUED, until=lambda view: view.job.attempts == 1)

    assert queued.job.failure_message.startswith("It used ")


def test_a_completion_that_fails_fails_the_job_and_applies_nothing(
    units: sessionmaker[Session], clock: FakeClock, tmp_path: Path
) -> None:
    def refuse(*_: object) -> None:
        message = "the database said no"
        raise RuntimeError(message)

    with running_jobs(units, clock, tmp_path / "jobs", kind=echo_kind([], complete=refuse)) as jobs:
        job = jobs.submit(EchoJob(text="x"))
        failed = jobs.wait_for(job.id, JobState.FAILED)

    assert failed.job.failure_kind == "program"
    assert failed.job.failure_message == "Its completion failed: RuntimeError: the database said no"


def test_cancelling_a_queued_job_cancels_it(
    units: sessionmaker[Session],
    clock: FakeClock,
    tmp_path: Path,
    household: tuple[Account, Account],
) -> None:
    _admin, member = household
    with running_jobs(units, clock, tmp_path / "jobs", start=False) as jobs:
        job = jobs.submit(EchoJob(text="x"), by=member.id)
        cancelled = jobs.service.cancel(member, job.id)

    assert cancelled.job.state is JobState.CANCELLED


def test_cancelling_a_running_job_kills_its_process_and_the_programs_it_started(
    units: sessionmaker[Session],
    clock: FakeClock,
    tmp_path: Path,
    household: tuple[Account, Account],
) -> None:
    admin, _member = household
    with running_jobs(units, clock, tmp_path / "jobs", idle_timeout=timedelta(minutes=1)) as jobs:
        job = jobs.submit(EchoJob(text="x", fail="sleeping-child"))
        running = jobs.wait_for(
            job.id, JobState.RUNNING, until=lambda view: view.progress is not None
        )
        cancelled = jobs.service.cancel(admin, job.id)
        child = int(running.progress.message) if running.progress else 0
        _wait_until_gone(child)
        after = jobs.service.get_job(job.id)

    assert cancelled.job.state is JobState.CANCELLED
    assert after.job.state is JobState.CANCELLED


def test_cancelling_a_finished_job_changes_nothing(
    units: sessionmaker[Session],
    clock: FakeClock,
    tmp_path: Path,
    household: tuple[Account, Account],
) -> None:
    admin, _member = household
    with running_jobs(units, clock, tmp_path / "jobs") as jobs:
        job = jobs.submit(EchoJob(text="x"))
        jobs.wait_for(job.id, JobState.SUCCEEDED)
        after = jobs.service.cancel(admin, job.id)

    assert after.job.state is JobState.SUCCEEDED


def test_only_the_account_that_asked_or_an_admin_cancels_a_job(
    units: sessionmaker[Session],
    clock: FakeClock,
    tmp_path: Path,
    household: tuple[Account, Account],
) -> None:
    admin, member = household
    with running_jobs(units, clock, tmp_path / "jobs", start=False) as jobs:
        job = jobs.submit(EchoJob(text="x"), by=admin.id)

        with pytest.raises(ForbiddenError):
            jobs.service.cancel(member, job.id)


def test_retrying_a_failed_job_submits_it_again(
    units: sessionmaker[Session],
    clock: FakeClock,
    tmp_path: Path,
    household: tuple[Account, Account],
) -> None:
    admin, _member = household
    with running_jobs(units, clock, tmp_path / "jobs") as jobs:
        job = jobs.submit(EchoJob(text="boom", fail="raise"))
        jobs.wait_for(job.id, JobState.FAILED)
        again = jobs.service.retry(admin, job.id)

    assert again.id != job.id
    assert (again.target, again.requested_by) == (job.target, admin.id)


def test_only_a_failed_or_cancelled_job_is_retried(
    units: sessionmaker[Session],
    clock: FakeClock,
    tmp_path: Path,
    household: tuple[Account, Account],
) -> None:
    admin, _member = household
    with running_jobs(units, clock, tmp_path / "jobs", start=False) as jobs:
        job = jobs.submit(EchoJob(text="x"))

        with pytest.raises(ConflictError, match="Only a failed or cancelled Job"):
            jobs.service.retry(admin, job.id)


def test_a_job_that_does_not_exist_is_not_found(
    units: sessionmaker[Session], clock: FakeClock, tmp_path: Path
) -> None:
    with (
        running_jobs(units, clock, tmp_path / "jobs", start=False) as jobs,
        pytest.raises(NotFoundError),
    ):
        jobs.service.get_job(JobId(404))


def test_the_newest_jobs_are_listed_first(
    units: sessionmaker[Session], clock: FakeClock, tmp_path: Path
) -> None:
    with running_jobs(units, clock, tmp_path / "jobs", start=False) as jobs:
        first = jobs.submit(EchoJob(text="a"), target="echo:1")
        second = jobs.submit(EchoJob(text="b"), target="echo:2")
        listed = [view.job.id for view in jobs.service.list_jobs()]

    assert listed == [second.id, first.id]


def test_stopping_the_runner_puts_a_running_job_back_without_counting_an_attempt(
    units: sessionmaker[Session], clock: FakeClock, tmp_path: Path
) -> None:
    with running_jobs(units, clock, tmp_path / "jobs", start=False) as jobs:
        jobs.runner.start()
        job = jobs.submit(EchoJob(text="x", steps=1, fail="hang"))
        jobs.wait_for(job.id, JobState.RUNNING, until=lambda view: view.progress is not None)
        jobs.runner.stop()
        after = jobs.service.get_job(job.id)

    assert (after.job.state, after.job.attempts) == (JobState.QUEUED, 0)


def _wait_until_gone(pid: int) -> None:
    ends = time.monotonic() + 10
    while time.monotonic() < ends:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    message = f"Process {pid} is still alive."
    raise AssertionError(message)


def test_stopping_the_runner_also_ends_the_programs_a_job_started(
    units: sessionmaker[Session], clock: FakeClock, tmp_path: Path
) -> None:
    with running_jobs(units, clock, tmp_path / "jobs", start=False) as jobs:
        jobs.runner.start()
        job = jobs.submit(EchoJob(text="x", fail="sleeping-child"))
        running = jobs.wait_for(
            job.id, JobState.RUNNING, until=lambda view: view.progress is not None
        )
        jobs.runner.stop()

    _wait_until_gone(int(running.progress.message) if running.progress else 0)


def _left_running(
    units: sessionmaker[Session], job_id: JobId, pid: int, interruptions: int = 0
) -> None:
    """Mark a Job running with `pid`, as a server that stopped mid-Job leaves it."""
    with units.begin() as db:
        db.execute(
            update(JobRow)
            .where(JobRow.id == job_id)
            .values(state=JobState.RUNNING, pid=pid, interruptions=interruptions)
        )


def _sleeper(work_dir: Path | None) -> subprocess.Popen[bytes]:
    """Start `sleep` in its own group, holding the lock in `work_dir` as a Job process does."""
    if work_dir is None:
        return subprocess.Popen(["sleep", "60"], start_new_session=True)  # noqa: S607 -- a stand-in Job process
    work_dir.mkdir(parents=True)
    lock = os.open(work_dir / "lock", os.O_CREAT | os.O_RDWR)
    fcntl.flock(lock, fcntl.LOCK_EX)
    try:
        return subprocess.Popen(["sleep", "60"], start_new_session=True, pass_fds=(lock,))  # noqa: S607 -- a stand-in Job process
    finally:
        os.close(lock)


def test_recovery_kills_a_job_process_still_alive_and_requeues_its_job(
    units: sessionmaker[Session], clock: FakeClock, tmp_path: Path
) -> None:
    jobs_dir = tmp_path / "jobs"
    with running_jobs(units, clock, jobs_dir, start=False) as jobs:
        job = jobs.submit(EchoJob(text="x"))
        sleeper = _sleeper(jobs_dir / str(job.id))
        _left_running(units, job.id, sleeper.pid)

        jobs.runner.recover()
        after = jobs.service.get_job(job.id)

    assert sleeper.wait(timeout=10) == -signal.SIGKILL
    assert (after.job.state, after.job.attempts) == (JobState.QUEUED, 0)
    assert list(jobs_dir.iterdir()) == []


def test_recovery_never_kills_a_process_that_does_not_hold_the_jobs_lock(
    units: sessionmaker[Session], clock: FakeClock, tmp_path: Path
) -> None:
    # The Job process is gone, and its process id now belongs to another program.
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    stranger = _sleeper(None)
    try:
        with running_jobs(units, clock, jobs_dir, start=False) as jobs:
            job = jobs.submit(EchoJob(text="x"))
            _left_running(units, job.id, stranger.pid)

            jobs.runner.recover()

        assert stranger.poll() is None
    finally:
        stranger.kill()
        stranger.wait()


def test_a_job_interrupted_by_three_restarts_fails(
    units: sessionmaker[Session], clock: FakeClock, tmp_path: Path
) -> None:
    with running_jobs(units, clock, tmp_path / "jobs", start=False) as jobs:
        job = jobs.submit(EchoJob(text="x"))
        _left_running(units, job.id, pid=0, interruptions=2)
        (tmp_path / "jobs").mkdir()

        jobs.runner.recover()
        after = jobs.service.get_job(job.id)

    assert (after.job.state, after.job.failure_message) == (
        JobState.FAILED,
        "A server restart interrupted it 3 times.",
    )


def test_a_queued_job_of_a_kind_the_server_no_longer_runs_fails(
    units: sessionmaker[Session], clock: FakeClock, tmp_path: Path
) -> None:
    with running_jobs(units, clock, tmp_path / "jobs", start=False) as jobs:
        job = jobs.submit(EchoJob(text="x"))
        with units.begin() as db:
            db.execute(update(JobRow).where(JobRow.id == job.id).values(kind="retired"))
        jobs.runner.start()
        failed = jobs.wait_for(job.id, JobState.FAILED)

    assert failed.job.failure_message == "This server no longer runs Jobs of the kind 'retired'."


def test_a_job_whose_process_cannot_start_fails(
    units: sessionmaker[Session], clock: FakeClock, plugins: PluginService, tmp_path: Path
) -> None:
    kind = echo_kind([])
    runner = JobRunner(
        units,
        clock,
        {"echo": kind},
        plugins,
        tmp_path / "jobs",
        processes=JobProcesses(HostCommand(argv=(str(tmp_path / "no-python"),))),
        poll=timedelta(seconds=0.1),
    )
    service = JobService(units, clock, {"echo": kind}, runner)
    job = service.submit(kind, "echo:1", EchoJob(text="x"), None)
    runner.start()
    try:
        ends = time.monotonic() + 10
        while service.get_job(job.id).job.state is not JobState.FAILED and time.monotonic() < ends:
            time.sleep(0.05)
    finally:
        runner.stop()

    assert service.get_job(job.id).job.failure_message.startswith("Its process didn't start:")
