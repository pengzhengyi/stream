"""A Job runner and service over the test plugins, for tests that run real Job processes."""

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application.events import Events
from medleyplay.application.job_runner import JOB_MEMORY_LIMIT, JobProcesses, JobRunner
from medleyplay.application.jobs import JobKind, JobService
from medleyplay.domain.accounts import AccountId
from medleyplay.domain.jobs import Job, JobId, JobState, JobView
from tests.support.fakes import FakeClock
from tests.support.hosts import TEST_COMMAND, TEST_PLUGINS, started_plugins
from tests.support.programs import Echoed, EchoJob, echo_kind

WAIT: float = 20


@dataclass
class Jobs:
    """A running Job runner, its service, and what the `echo` kind's completions recorded."""

    service: JobService
    runner: JobRunner
    kind: JobKind[EchoJob, Echoed]
    clock: FakeClock
    completed: list[str] = field(default_factory=list)

    def submit(self, request: EchoJob, target: str = "echo:1", by: int | None = None) -> Job:
        """Submit an `echo` Job."""
        return self.service.submit(
            self.kind, target, request, None if by is None else AccountId(by)
        )

    def wait_for(
        self, job_id: JobId, *states: JobState, until: Callable[[JobView], bool] | None = None
    ) -> JobView:
        """Wait until the Job is in one of `states`, and `until` holds, then return it."""
        ends = time.monotonic() + WAIT
        while time.monotonic() < ends:
            view = self.service.get_job(job_id)
            if view.job.state in states and (until is None or until(view)):
                return view
            time.sleep(0.05)
        message = f"Job {job_id} is {self.service.get_job(job_id).job.state}, not in {states}."
        raise AssertionError(message)

    def retry_time_comes(self, after: timedelta) -> None:
        """Move the clock past a retry delay and wake the runner."""
        self.clock.advance(after)
        self.runner.wake()


@contextmanager
def running_jobs(  # noqa: PLR0913 -- the database and clock, then settings with defaults
    units: sessionmaker[Session],
    clock: FakeClock,
    jobs_dir: Path,
    *,
    start: bool = True,
    memory_limit: int = JOB_MEMORY_LIMIT,
    idle_timeout: timedelta = timedelta(seconds=20),
    kind: JobKind[EchoJob, Echoed] | None = None,
    events: Events | None = None,
) -> Iterator[Jobs]:
    """Run Jobs of the `echo` kind with the test plugin `parrot` on, and stop them afterwards."""
    completed: list[str] = []
    echo = kind or echo_kind(completed, idle_timeout=idle_timeout)
    with started_plugins(units, clock, "parrot") as plugins:
        runner = JobRunner(
            units,
            clock,
            {"echo": echo},
            plugins,
            jobs_dir,
            processes=JobProcesses(TEST_COMMAND, TEST_PLUGINS),
            poll=timedelta(seconds=0.1),
            memory_limit=memory_limit,
            events=events,
        )
        service = JobService(units, clock, {"echo": echo}, runner, events)
        if start:
            runner.start()
        try:
            yield Jobs(service, runner, echo, clock, completed)
        finally:
            if start:
                runner.stop()
