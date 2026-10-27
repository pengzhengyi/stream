"""The Job runner: a thread in the server that starts Job processes and settles their outcomes.

The server is the only runner, so a Job left running at startup belongs to a
server that stopped; `start` recovers it before anything new starts.
"""

import contextlib
import fcntl
import os
import shutil
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Final, Protocol

from pydantic import ValidationError
from sqlalchemy import ColumnElement, or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application import Clock
from medleyplay.application.events import Events
from medleyplay.application.jobs import AnyJobKind, to_job
from medleyplay.application.plugins import PluginService
from medleyplay.domain.accounts import AccountId
from medleyplay.domain.errors import KeychainUnavailableError
from medleyplay.domain.jobs import JobId, JobState, Progress
from medleyplay.domain.linked_accounts import redact
from medleyplay.persistence.schema import JobRow
from medleyplay.plugin_api.progress import MAX_MESSAGE as MAX_PROGRESS_MESSAGE
from medleyplay.plugin_host.job_wire import (
    FROM_JOB,
    RESULT_FILE,
    FromJob,
    JobFailed,
    JobFinished,
    JobProgress,
    JobStart,
)
from medleyplay.plugin_host.loader import BUILT_IN_PLUGINS
from medleyplay.plugin_host.process import (
    ChildExitedError,
    ChildProcess,
    ChildTimeoutError,
    HostCommand,
    kill_group,
)

MAX_RUNNING: Final = 2
POLL: Final = timedelta(seconds=1)
FIRST_RETRY: Final = timedelta(seconds=30)
NETWORK_RETRY: Final = timedelta(minutes=1)
"""How long a Job waits after a network failure, or a Keychain that didn't answer."""
MAX_INTERRUPTIONS: Final = 3
JOB_MEMORY_LIMIT: Final = 2 * 1024**3
LOCK_FILE: Final = "lock"
LOGIN_FILE: Final = "login.txt"
_NEW_PRIVATE: Final = os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW


class Lent(Protocol):
    """A copy of a login lent to one Job, and the revision it was copied at."""

    @property
    def text(self) -> str: ...  # noqa: D102
    @property
    def revision(self) -> int: ...  # noqa: D102


class Logins(Protocol):
    """Where the runner borrows Accounts' logins for Jobs, as `LinkedAccountService` provides."""

    def lend(self, account_id: AccountId, site: str) -> Lent | None:
        """Return a copy of the Account's valid login on `site`, or `None`."""
        ...

    def refused(self, account_id: AccountId, site: str, revision: int) -> None:
        """Mark the login refused, unless it was saved again since `revision`."""
        ...


@dataclass(frozen=True)
class JobProcesses:
    """How to start Job processes, and where their plugins come from."""

    command: HostCommand = field(default_factory=HostCommand)
    package: str = BUILT_IN_PLUGINS


@dataclass(frozen=True)
class _Fault:
    """The Job process failed without saying why: it hung, grew too large, or exited."""

    message: str


@dataclass(frozen=True)
class _Interrupted:
    """The server is shutting down; the Job goes back in the queue."""


type _Outcome = JobFinished | JobFailed | _Fault | _Interrupted


@dataclass(frozen=True)
class _Login:
    account_id: AccountId
    site: str
    lent: Lent


@dataclass
class _Running:
    job_id: JobId
    kind: AnyJobKind
    work_dir: Path
    process: ChildProcess[FromJob]
    login: _Login | None = None
    thread: threading.Thread | None = None
    held: bool = False
    """Stopped because the Mode went Offline, so it goes back to the queue uncounted."""
    done: bool = False
    """Its process has ended, so nothing is left to stop."""

    def redact(self, message: str) -> str:
        return redact(message, self.login.lent.text if self.login else None)


class JobRunner:
    """Start queued Jobs in their own processes, at most `max_running` at once."""

    def __init__(  # noqa: PLR0913 -- the collaborators, then settings with defaults
        self,
        units: sessionmaker[Session],
        clock: Clock,
        kinds: Mapping[str, AnyJobKind],
        plugins: PluginService,
        jobs_dir: Path,
        *,
        processes: JobProcesses = JobProcesses(),  # noqa: B008 -- a frozen value
        max_running: int = MAX_RUNNING,
        poll: timedelta = POLL,
        online: Callable[[], bool] = lambda: True,
        memory_limit: int = JOB_MEMORY_LIMIT,
        logins: Logins | None = None,
        events: Events | None = None,
        network_failed: Callable[[], None] | None = None,
    ) -> None:
        """Create a runner keeping Jobs' working folders in `jobs_dir`."""
        self._units = units
        self._clock = clock
        self._kinds = kinds
        self._plugins = plugins
        self._jobs_dir = jobs_dir
        self._processes = processes
        self._max_running = max_running
        self._poll = poll
        self._online = online
        self._memory_limit = memory_limit
        self._logins = logins
        self._events = events
        self._network_failed = network_failed
        self._network_kinds = tuple(name for name, kind in kinds.items() if kind.needs_network)
        self._lock = threading.Lock()
        self._running: dict[JobId, _Running] = {}
        self._progress: dict[JobId, Progress] = {}
        self._wake = threading.Event()
        self._stopping = threading.Event()
        self._loop_thread: threading.Thread | None = None

    def start(self) -> None:
        """Recover Jobs a stopped server left running, then start running Jobs."""
        self._jobs_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.recover()
        self._loop_thread = threading.Thread(target=self._loop, name="job-runner", daemon=True)
        self._loop_thread.start()

    def stop(self) -> None:
        """Stop starting Jobs, end the running ones, and put them back in the queue."""
        self._stopping.set()
        self._wake.set()
        if self._loop_thread is not None:
            self._loop_thread.join()
        with self._lock:
            running = list(self._running.values())
        for job in running:
            job.process.stop()
        for job in running:
            if job.thread is not None:
                job.thread.join()

    def wake(self) -> None:
        """Look for a Job to start now, rather than at the next poll."""
        self._wake.set()

    def follow_mode(self) -> None:
        """Follow a change of the Mode: Offline, stop the Jobs that need the network.

        A stopped Job goes back to the queue without counting an attempt or an
        interruption, since its process would otherwise keep contacting the site.
        Online, the queued ones start, oldest first.
        """
        if not self._online():
            with self._lock:
                held = [
                    job for job in self._running.values() if job.kind.needs_network and not job.done
                ]
                for job in held:
                    job.held = True
            for job in held:
                job.process.kill()
        self._wake.set()

    def kill(self, job_id: JobId) -> None:
        """Kill a running Job's process group."""
        with self._lock:
            job = self._running.get(job_id)
        if job is not None:
            job.process.kill()

    def progress(self, job_id: JobId) -> Progress | None:
        """Return a running Job's latest progress."""
        with self._lock:
            return self._progress.get(job_id)

    def recover(self) -> None:
        """Requeue Jobs left running, killing any process still alive, and clear working folders.

        A Job interrupted `MAX_INTERRUPTIONS` times fails, so a Job that keeps
        bringing the server down can't loop forever.
        """
        with self._units() as db:
            running = db.scalars(select(JobRow).where(JobRow.state == JobState.RUNNING))
            stale = [(row.id, row.pid, row.interruptions) for row in running]
        for job_id, pid, interruptions in stale:
            if pid is not None and lock_is_held(self._jobs_dir / str(job_id) / LOCK_FILE):
                kill_group(pid)
            if interruptions + 1 >= MAX_INTERRUPTIONS:
                message = f"A server restart interrupted it {interruptions + 1} times."
                self._set(JobId(job_id), JobState.FAILED, failure=("program", message))
            else:
                self._set(JobId(job_id), JobState.QUEUED, interruptions=interruptions + 1)
        for entry in self._jobs_dir.iterdir():
            shutil.rmtree(entry, ignore_errors=True)

    def _loop(self) -> None:
        while not self._stopping.is_set():
            self._promote_waiting()
            while self._has_room() and not self._stopping.is_set():
                if not self._start_next():
                    break
            self._wake.wait(self._poll.total_seconds())
            self._wake.clear()

    def _has_room(self) -> bool:
        with self._lock:
            return len(self._running) < self._max_running

    def _promote_waiting(self) -> None:
        if not self._online():
            return
        with self._units.begin() as db:
            due = (JobRow.state == JobState.WAITING) & _due(self._clock())
            promoted = list(db.scalars(select(JobRow.id).where(due)))
            db.execute(
                update(JobRow).where(JobRow.id.in_(promoted), due).values(state=JobState.QUEUED)
            )
        for job_id in promoted:
            self._publish(JobId(job_id))

    def _start_next(self) -> bool:
        with self._units.begin() as db:
            now = self._clock()
            ready = (JobRow.state == JobState.QUEUED) & _due(now)
            if not self._online():
                ready &= JobRow.kind.not_in(self._network_kinds)
            row = db.scalar(select(JobRow).where(ready).order_by(JobRow.id).limit(1))
            if row is None:
                return False
            claimed = db.connection().execute(
                update(JobRow)
                .where(JobRow.id == row.id, JobRow.state == JobState.QUEUED)
                .values(state=JobState.RUNNING, started_at=now, finished_at=None)
            )
            job_id, kind_name, request = JobId(row.id), row.kind, row.request
            # Only the Account that asked lends its login: once it is deleted, its id
            # may be taken by a new Account, whose login the Job was never meant to have.
            login_account = (
                row.login_account_id if row.login_account_id == row.requested_by else None
            )
        if claimed.rowcount != 1:
            return True
        self._publish(job_id)
        kind = self._kinds.get(kind_name)
        if kind is None:
            message = f"This server no longer runs Jobs of the kind {kind_name!r}."
            self._settle_failure(job_id, "program", message)
            return True
        self._launch(
            job_id, kind, request, None if login_account is None else AccountId(login_account)
        )
        return True

    def _launch(
        self, job_id: JobId, kind: AnyJobKind, request: object, login_account: AccountId | None
    ) -> None:
        work_dir = self._jobs_dir / str(job_id)
        work_dir.mkdir(mode=0o700, exist_ok=True)
        try:
            login = self._lend(kind, login_account, work_dir)
            process = self._spawn(work_dir)
        except KeychainUnavailableError as error:
            # The Keychain can be locked or prompting; it usually answers again soon.
            shutil.rmtree(work_dir, ignore_errors=True)
            failure = ("keychain", f"Its login couldn't be read: {error}")
            self._set(
                job_id,
                JobState.WAITING,
                failure=failure,
                not_before=self._clock() + NETWORK_RETRY,
            )
            return
        except OSError as error:
            self._settle_failure(job_id, "program", f"Its process didn't start: {error}")
            shutil.rmtree(work_dir, ignore_errors=True)
            return
        running = _Running(job_id, kind, work_dir, process, login)
        with self._lock:
            self._running[job_id] = running
        # The Mode may have gone Offline since the claim, before `follow_mode` could
        # see this Job: checked after registering, one of the two stops it.
        if kind.needs_network and not self._online():
            with self._lock:
                running.held = True
        # A cancel that landed while the process was starting found nothing to kill.
        if running.held or not self._set_pid(job_id, process.pid):
            process.kill()
        with contextlib.suppress(ChildExitedError):
            process.send(
                JobStart(
                    package=self._processes.package,
                    plugins=self._plugins.plugins_for(kind.points),
                    program=kind.program,
                    request=request,  # type: ignore[arg-type] # a JSON column holds JSON
                    work_dir=str(work_dir),
                    login=str(work_dir / LOGIN_FILE) if login else None,
                )
            )
        running.thread = threading.Thread(target=self._supervise, args=(running,), daemon=True)
        running.thread.start()

    def _lend(
        self, kind: AnyJobKind, account_id: AccountId | None, work_dir: Path
    ) -> _Login | None:
        # The copy is readable by its owner alone, and goes with the working folder.
        if kind.login_site is None or account_id is None or self._logins is None:
            return None
        lent = self._logins.lend(account_id, kind.login_site)
        if lent is None:
            return None
        descriptor = os.open(work_dir / LOGIN_FILE, _NEW_PRIVATE, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(lent.text)
        return _Login(account_id, kind.login_site, lent)

    def _spawn(self, work_dir: Path) -> ChildProcess[FromJob]:
        # The lock is taken before the process starts and handed to it, so it is
        # held from the first instant the process exists until its last copy closes.
        lock = os.open(work_dir / LOCK_FILE, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX)
            return ChildProcess(self._processes.command, FROM_JOB, args=("job",), pass_fds=(lock,))
        finally:
            os.close(lock)

    def _supervise(self, running: _Running) -> None:
        outcome = self._watch(running)
        with self._lock:
            running.done = True
        if isinstance(outcome, JobFinished | JobFailed):
            running.process.finish()
        else:
            running.process.kill()
        try:
            self._settle(running, outcome)
        finally:
            shutil.rmtree(running.work_dir, ignore_errors=True)
            with self._lock:
                self._running.pop(running.job_id, None)
                self._progress.pop(running.job_id, None)
            self._wake.set()

    def _watch(self, running: _Running) -> _Outcome:
        idle = running.kind.idle_timeout
        while True:
            try:
                message = running.process.receive(idle.total_seconds())
            except ChildTimeoutError:
                return _Fault(f"It reported nothing for {idle}.")
            except ChildExitedError:
                if self._stopping.is_set():
                    return _Interrupted()
                return _Fault("Its process exited without an outcome.")
            match message:
                case JobProgress(fraction=fraction, message=text, peak_memory=peak):
                    if peak > self._memory_limit:
                        return _Fault(f"It used {peak // 1024**2} MiB of memory.")
                    shown = running.redact(text)[:MAX_PROGRESS_MESSAGE]
                    with self._lock:
                        self._progress[running.job_id] = Progress(fraction, shown)
                    self._publish(running.job_id, progress=True)
                case JobFinished() | JobFailed():
                    return message

    def _settle(self, running: _Running, outcome: _Outcome) -> None:
        outcome = _redacted(running, outcome)
        if running.held and not isinstance(outcome, JobFinished):
            self._set(running.job_id, JobState.QUEUED)
            return
        login, refused = running.login, isinstance(outcome, JobFailed) and outcome.kind == "auth"
        if refused and login is not None and self._logins is not None:
            self._logins.refused(login.account_id, login.site, login.lent.revision)
        match outcome:
            case JobFinished(outcomes=outcomes):
                self._plugins.record_outcomes(outcomes)
                self._complete(running)
            case JobFailed(kind="network", message=message, outcomes=outcomes):
                self._plugins.record_outcomes(outcomes)
                not_before = self._clock() + NETWORK_RETRY
                self._set(
                    running.job_id,
                    JobState.WAITING,
                    failure=("network", message),
                    not_before=not_before,
                )
                if self._network_failed is not None:
                    self._network_failed()
            case JobFailed(kind="plugin", message=message, outcomes=outcomes):
                self._plugins.record_outcomes(outcomes)
                self._retry_or_fail(running, message)
            case JobFailed(kind=kind, message=message, outcomes=outcomes):
                self._plugins.record_outcomes(outcomes)
                self._settle_failure(running.job_id, kind, message)
            case _Fault(message=message):
                self._retry_or_fail(running, message)
            case _Interrupted():
                self._set(running.job_id, JobState.QUEUED)

    def _complete(self, running: _Running) -> None:
        kind = running.kind
        try:
            text = (running.work_dir / RESULT_FILE).read_text(encoding="utf-8")
            result = kind.result.model_validate_json(text)
        except (OSError, ValidationError) as error:
            self._settle_failure(running.job_id, "program", f"Its result is unreadable: {error}")
            return
        try:
            with self._units.begin() as db:
                if self._set_in(db, running.job_id, JobState.SUCCEEDED):
                    kind.complete(db, to_job(_get(db, running.job_id)), result)
        except Exception as error:  # noqa: BLE001 -- a failed completion fails its Job
            message = f"Its completion failed: {type(error).__name__}: {error}"
            self._settle_failure(running.job_id, "program", message)
            return
        self._publish(running.job_id)

    def _retry_or_fail(self, running: _Running, message: str) -> None:
        with self._units() as db:
            attempts = _get(db, running.job_id).attempts + 1
        if attempts >= running.kind.max_attempts:
            self._set(
                running.job_id, JobState.FAILED, failure=("plugin", message), attempts=attempts
            )
            return
        delay = FIRST_RETRY * 2 ** (attempts - 1)
        self._set(
            running.job_id,
            JobState.QUEUED,
            failure=("plugin", message),
            attempts=attempts,
            not_before=self._clock() + delay,
        )

    def _settle_failure(self, job_id: JobId, kind: str, message: str) -> None:
        self._set(job_id, JobState.FAILED, failure=(kind, message))

    def _set_pid(self, job_id: JobId, pid: int) -> bool:
        """Record the Job's process; return whether the Job is still running."""
        with self._units.begin() as db:
            recorded = db.connection().execute(
                update(JobRow)
                .where(JobRow.id == job_id, JobRow.state == JobState.RUNNING)
                .values(pid=pid)
            )
        return recorded.rowcount == 1

    def _set(self, job_id: JobId, state: JobState, **changes: Any) -> bool:  # noqa: ANN401 -- column values
        with self._units.begin() as db:
            changed = self._set_in(db, job_id, state, **changes)
        if changed:
            self._publish(job_id)
        return changed

    def _publish(self, job_id: JobId, *, progress: bool = False) -> None:
        if self._events is not None:
            self._events.publish(job_id, progress=progress)

    def _set_in(
        self,
        db: Session,
        job_id: JobId,
        state: JobState,
        *,
        failure: tuple[str, str] | None = None,
        **changes: Any,  # noqa: ANN401 -- column values
    ) -> bool:
        # Only a running Job moves on; a cancel that got there first wins.
        values: dict[str, Any] = {"state": state, "pid": None, **changes}
        if failure is not None:
            values["failure_kind"], values["failure_message"] = failure[0], failure[1][:2048]
        elif state is JobState.SUCCEEDED:
            values["failure_kind"], values["failure_message"] = None, ""
        if not state.is_active:
            values["finished_at"] = self._clock()
        changed = db.connection().execute(
            update(JobRow)
            .where(JobRow.id == job_id, JobRow.state == JobState.RUNNING)
            .values(**values)
        )
        return changed.rowcount == 1


def lock_is_held(path: Path) -> bool:
    """Return whether some process holds the lock on `path`; a missing file is not held."""
    try:
        lock = os.open(path, os.O_RDWR)
    except FileNotFoundError:
        return False
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    finally:
        os.close(lock)
    return False


def _redacted(running: _Running, outcome: _Outcome) -> _Outcome:
    """Return the outcome with the login taken out of every message, whatever printed it."""
    if isinstance(outcome, _Fault):
        return _Fault(running.redact(outcome.message))
    if not isinstance(outcome, JobFinished | JobFailed):
        return outcome
    outcomes = [
        each.model_copy(update={"last_failure": running.redact(each.last_failure)})
        for each in outcome.outcomes
    ]
    if isinstance(outcome, JobFailed):
        return outcome.model_copy(
            update={"outcomes": outcomes, "message": running.redact(outcome.message)}
        )
    return outcome.model_copy(update={"outcomes": outcomes})


def _due(now: datetime) -> ColumnElement[bool]:
    return or_(JobRow.not_before.is_(None), JobRow.not_before <= now)


def _get(db: Session, job_id: JobId) -> JobRow:
    row = db.get(JobRow, job_id)
    if row is None:  # pragma: no cover -- a Job row is never deleted
        message = f"There is no Job {job_id}."
        raise LookupError(message)
    return row
