"""Jobs as the household sees them: submitting, listing, cancelling, and retrying.

Every change to a Job's state is a compare-and-set on its row, so the database
decides between a cancel and a completion that arrive together.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Final, Generic, Protocol, TypeVar

from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application import Clock
from medleyplay.domain.accounts import Account, AccountId
from medleyplay.domain.errors import ConflictError, ForbiddenError, NotFoundError
from medleyplay.domain.jobs import ACTIVE_STATES, Job, JobId, JobState, JobView, Progress
from medleyplay.persistence.schema import JobRow

I = TypeVar("I", bound=BaseModel)  # noqa: E741 -- the conventional name for an input
R = TypeVar("R", bound=BaseModel)

IDLE_TIMEOUT: Final = timedelta(minutes=10)
MAX_ATTEMPTS: Final = 3
LIST_LIMIT: Final = 100


@dataclass(frozen=True)
class JobKind(Generic[I, R]):  # noqa: UP046 -- invariant, so `submit` checks its request
    """A kind of Job: the program a Job process runs, and the completion the server runs.

    `program` names a `JobProgram` as `module:attribute`. `complete` applies the
    result to the database in the transaction that marks the Job succeeded, and
    must tolerate finding its work already applied. `points` are the extension
    points the program calls; its Job process loads only their plugins.
    """

    name: str
    program: str
    request: type[I]
    result: type[R]
    complete: Callable[[Session, Job, R], None]
    points: tuple[str, ...] = ()
    idle_timeout: timedelta = IDLE_TIMEOUT
    max_attempts: int = MAX_ATTEMPTS


# Any: each kind has its own request and result models.
type AnyJobKind = JobKind[Any, Any]


class Runner(Protocol):
    """What the service asks of the runner, as `JobRunner` provides."""

    def start(self) -> None:
        """Recover Jobs a stopped server left running, then start running Jobs."""
        ...

    def stop(self) -> None:
        """Stop running Jobs, putting the running ones back in the queue."""
        ...

    def wake(self) -> None:
        """Look for a Job to start now."""
        ...

    def kill(self, job_id: JobId) -> None:
        """Kill the running Job's process, if it has one."""
        ...

    def progress(self, job_id: JobId) -> Progress | None:
        """Return a running Job's latest progress."""
        ...


class JobService:
    """Submit, list, cancel, and retry Jobs."""

    def __init__(
        self,
        units: sessionmaker[Session],
        clock: Clock,
        kinds: Mapping[str, AnyJobKind],
        runner: Runner,
    ) -> None:
        """Create a service over the database `units` open, for Jobs of `kinds`."""
        self._units = units
        self._clock = clock
        self._kinds = kinds
        self._runner = runner

    def start(self) -> None:
        """Start running Jobs, after recovering those a stopped server left running."""
        self._runner.start()

    def stop(self) -> None:
        """Stop running Jobs; the running ones go back in the queue."""
        self._runner.stop()

    def submit(
        self, kind: JobKind[I, R], target: str, request: I, requested_by: AccountId | None
    ) -> Job:
        """Queue a Job of `kind` for `target`, or return the active one that already exists."""
        if self._kinds.get(kind.name) is not kind:
            message = f"The Job kind {kind.name!r} isn't one this server runs."
            raise ValueError(message)
        existing = self.active(kind.name, target)
        if existing is not None:
            return existing
        try:
            with self._units.begin() as db:
                row = JobRow(
                    kind=kind.name,
                    target=target,
                    state=JobState.QUEUED,
                    request=request.model_dump(mode="json"),
                    requested_by=requested_by,
                    attempts=0,
                    interruptions=0,
                    failure_message="",
                    created_at=self._clock(),
                )
                db.add(row)
                db.flush()
                job = to_job(row)
        except IntegrityError:
            # Another request queued the same Job between the lookup and the insert.
            raced = self.active(kind.name, target)
            if raced is None:
                raise
            return raced
        self._runner.wake()
        return job

    def list_jobs(self, limit: int = LIST_LIMIT) -> list[JobView]:
        """Return the newest Jobs first."""
        with self._units() as db:
            rows = db.scalars(select(JobRow).order_by(JobRow.id.desc()).limit(limit))
            return [self._view(to_job(row)) for row in rows]

    def get_job(self, job_id: JobId) -> JobView:
        """Return one Job."""
        with self._units() as db:
            return self._view(to_job(_row(db, job_id)))

    def cancel(self, caller: Account, job_id: JobId) -> JobView:
        """Cancel a Job that hasn't finished; cancelling a finished Job changes nothing.

        Only the Account that asked for the Job, or an admin, may cancel it.
        """
        with self._units.begin() as db:
            row = _row(db, job_id)
            _require_owner_or_admin(caller, row)
            was_running = row.state == JobState.RUNNING
            cancelled = db.connection().execute(
                update(JobRow)
                .where(JobRow.id == job_id, JobRow.state.in_(ACTIVE_STATES))
                .values(state=JobState.CANCELLED, finished_at=self._clock(), pid=None)
            )
        if was_running and cancelled.rowcount == 1:
            self._runner.kill(job_id)
        return self.get_job(job_id)

    def retry(self, caller: Account, job_id: JobId) -> Job:
        """Submit a failed or cancelled Job again, as a new Job; return it.

        When a Job for the same target is already active, return that one instead.
        """
        with self._units() as db:
            row = _row(db, job_id)
            _require_owner_or_admin(caller, row)
            if JobState(row.state) not in {JobState.FAILED, JobState.CANCELLED}:
                message = "Only a failed or cancelled Job can be retried."
                raise ConflictError(message)
            kind = self._kinds.get(row.kind)
            if kind is None:
                message = f"This server no longer runs Jobs of the kind {row.kind!r}."
                raise ConflictError(message)
            target, request = row.target, kind.request.model_validate(row.request)
        return self.submit(kind, target, request, caller.id)

    def active(self, kind: str, target: str) -> Job | None:
        """Return the waiting, queued, or running Job of `kind` for `target`, if any."""
        with self._units() as db:
            row = db.scalar(
                select(JobRow).where(
                    JobRow.kind == kind,
                    JobRow.target == target,
                    JobRow.state.in_(ACTIVE_STATES),
                )
            )
            return None if row is None else to_job(row)

    def _view(self, job: Job) -> JobView:
        progress = self._runner.progress(job.id) if job.state == JobState.RUNNING else None
        return JobView(job, progress)


def to_job(row: JobRow) -> Job:
    """Return the domain view of a `job` row."""
    return Job(
        id=JobId(row.id),
        kind=row.kind,
        target=row.target,
        state=JobState(row.state),
        requested_by=None if row.requested_by is None else AccountId(row.requested_by),
        attempts=row.attempts,
        failure_kind=row.failure_kind,
        failure_message=row.failure_message,
        created_at=row.created_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


def _row(db: Session, job_id: JobId) -> JobRow:
    row = db.get(JobRow, job_id)
    if row is None:
        message = f"There is no Job {job_id}."
        raise NotFoundError(message)
    return row


def _require_owner_or_admin(caller: Account, row: JobRow) -> None:
    if not caller.is_admin and row.requested_by != caller.id:
        message = "Only the Account that asked for a Job, or an admin, can change it."
        raise ForbiddenError(message)
