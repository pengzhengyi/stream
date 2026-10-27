"""The Jobs API: the household's Jobs, with progress, cancelling, and retrying."""

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from medleyplay.domain.jobs import JobId, JobState, JobView
from medleyplay.web.deps import JobsDep, SignedInAccount

router = APIRouter(prefix="/api", tags=["jobs"])


class ProgressOut(BaseModel):
    """How far a running Job has got."""

    fraction: float | None
    message: str


class JobOut(BaseModel):
    """A Job as the API shows it."""

    id: int
    kind: str
    target: str
    state: JobState
    requested_by: int | None
    attempts: int
    failure_kind: str | None
    failure_message: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    progress: ProgressOut | None
    waits_for_online: bool
    """It needs the network, and waits while the Mode is Offline."""

    @classmethod
    def of(cls, view: JobView) -> "JobOut":
        """Return the API view of `view`."""
        job, progress = view.job, view.progress
        return cls(
            id=job.id,
            kind=job.kind,
            target=job.target,
            state=job.state,
            requested_by=job.requested_by,
            attempts=job.attempts,
            failure_kind=job.failure_kind,
            failure_message=job.failure_message,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            progress=None if progress is None else ProgressOut(**vars(progress)),
            waits_for_online=view.waits_for_online,
        )


@router.get("/jobs")
def list_jobs(_: SignedInAccount, jobs: JobsDep) -> list[JobOut]:
    """Return the household's newest Jobs first."""
    return [JobOut.of(view) for view in jobs.list_jobs()]


@router.get("/jobs/{job_id}")
def get_job(job_id: int, _: SignedInAccount, jobs: JobsDep) -> JobOut:
    """Return one Job."""
    return JobOut.of(jobs.get_job(JobId(job_id)))


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: int, me: SignedInAccount, jobs: JobsDep) -> JobOut:
    """Cancel a Job; the Account that asked for it, or an admin. Cancelling twice is fine."""
    return JobOut.of(jobs.cancel(me, JobId(job_id)))


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: int, me: SignedInAccount, jobs: JobsDep) -> JobOut:
    """Submit a failed or cancelled Job again, and return the new Job."""
    retried = jobs.retry(me, JobId(job_id))
    return JobOut.of(jobs.get_job(retried.id))
