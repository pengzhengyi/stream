"""Jobs: background work with progress and an outcome, such as a download or a scan."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Final, NewType

from medleyplay.domain.accounts import AccountId

JobId = NewType("JobId", int)


class JobState(StrEnum):
    """Where a Job is in its life."""

    WAITING = "waiting"
    """Held until the server is Online and its retry time has come."""
    QUEUED = "queued"
    """Ready to start."""
    RUNNING = "running"
    """Has a process."""
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_active(self) -> bool:
        """Return whether the Job can still run."""
        return self in ACTIVE_STATES


ACTIVE_STATES: Final = frozenset({JobState.WAITING, JobState.QUEUED, JobState.RUNNING})


@dataclass(frozen=True)
class Job:
    """A Job as the household sees it.

    `target` names what the Job works on, such as `library:3`; at most one active
    Job of a kind exists per target.
    """

    id: JobId
    kind: str
    target: str
    state: JobState
    requested_by: AccountId | None
    attempts: int
    failure_kind: str | None
    failure_message: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


@dataclass(frozen=True)
class Progress:
    """How far a running Job has got: a fraction from 0 to 1 when known, and what it's doing."""

    fraction: float | None = None
    message: str = ""


@dataclass(frozen=True)
class JobView:
    """A Job with its progress, which only a running Job has."""

    job: Job
    progress: Progress | None = field(default=None)
