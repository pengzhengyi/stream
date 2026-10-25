"""The events API: a stream of Server-Sent Events telling a browser each time a Job changes."""

import asyncio
from collections.abc import AsyncIterable
from typing import Final

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from fastapi.sse import EventSourceResponse, ServerSentEvent

from medleyplay.application.events import SubscriptionEndedError
from medleyplay.domain.errors import NotSignedInError
from medleyplay.web.deps import AccountsDep, EventsDep, JobsDep, SessionToken, SignedInAccount
from medleyplay.web.jobs import JobOut

router = APIRouter(prefix="/api", tags=["events"])

SESSION_CHECK_SECONDS: Final = 15.0
"""How long a quiet stream waits before checking its session is still signed in."""


@router.get("/events", response_class=EventSourceResponse)
async def stream_events(
    me: SignedInAccount,
    events: EventsDep,
    jobs: JobsDep,
    accounts: AccountsDep,
    token: SessionToken = None,
) -> AsyncIterable[ServerSentEvent]:
    """Stream a `job` event, the Job as `GET /api/jobs` shows it, whenever a Job changes.

    The stream starts with a `ready` event once it hears every change, so a
    browser asks `GET /api/jobs` after `ready` and misses nothing. Events carry no
    ids and nothing is replayed: a browser that reconnects waits for `ready` and
    asks again. The stream ends when its session does.
    """
    del me  # Signed in to open the stream; the session is checked again as it runs.
    async with events.subscribe() as subscription:
        yield ServerSentEvent(event="ready", data={})
        while True:
            try:
                job_id = await asyncio.wait_for(subscription.next(), SESSION_CHECK_SECONDS)
            except TimeoutError:
                if not await run_in_threadpool(_still_signed_in, accounts, token):
                    return
                continue
            except SubscriptionEndedError:
                return
            view = await run_in_threadpool(jobs.get_job, job_id)
            yield ServerSentEvent(data=JobOut.of(view), event="job")


def _still_signed_in(accounts: AccountsDep, token: str | None) -> bool:
    if token is None:  # pragma: no cover -- the stream opened signed in
        return False
    try:
        accounts.authenticate(token)
    except NotSignedInError:
        return False
    return True
