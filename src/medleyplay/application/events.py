"""Job events: telling every open browser when a Job changes, as it happens.

The runner and the services publish a Job's id after they commit, from any
thread; each subscriber, one per open event stream, receives it on the event
loop and reads the Job as it now stands.

A subscriber has a bounded queue, so a slow browser can't hold the server back:
a progress event that doesn't fit is dropped, since the next one replaces it,
and a change of state that doesn't fit ends the subscription, so the browser
reconnects and asks for every Job again.
"""

import asyncio
import contextlib
import functools
import threading
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Final

from medleyplay.domain.jobs import JobId

MAX_QUEUED: Final = 64
PROGRESS_INTERVAL: Final = 0.25
"""At most four progress events a second for one Job."""


class SubscriptionEndedError(Exception):
    """The subscriber fell too far behind, and missed a change of state."""


@dataclass(eq=False)
class Subscription:
    """One event stream's queue of Job ids, read on the event loop."""

    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue[JobId] = field(default_factory=lambda: asyncio.Queue(MAX_QUEUED))
    ended: bool = False

    async def next(self) -> JobId:
        """Return the next Job that changed; raise `SubscriptionEndedError` once ended."""
        if self.ended:
            raise SubscriptionEndedError
        job_id = await self.queue.get()
        if self.ended:
            raise SubscriptionEndedError
        return job_id

    def offer(self, job_id: JobId, *, progress: bool) -> None:
        """Queue the Job, on the event loop; a full queue drops progress and ends on state."""
        if self.ended:
            return
        try:
            self.queue.put_nowait(job_id)
        except asyncio.QueueFull:
            if not progress:
                self.ended = True
                # Wake a reader waiting on the queue, so it sees the end.
                with contextlib.suppress(asyncio.QueueEmpty):
                    self.queue.get_nowait()
                self.queue.put_nowait(job_id)


class JobEvents:
    """Where Job changes are published, and event streams subscribe to them."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        """Create a hub with no subscribers; `clock` paces progress events."""
        self._clock = clock
        self._lock = threading.Lock()
        self._subscriptions: set[Subscription] = set()
        self._last_progress: dict[JobId, float] = {}

    def publish(self, job_id: JobId, *, progress: bool = False) -> None:
        """Tell every subscriber the Job changed; callable from any thread.

        Progress is sent at most four times a second per Job; a change of state
        is always sent.
        """
        now = self._clock()
        with self._lock:
            if progress:
                last = self._last_progress.get(job_id)
                if last is not None and now - last < PROGRESS_INTERVAL:
                    return
                self._last_progress[job_id] = now
            else:
                self._last_progress.pop(job_id, None)
            subscriptions = tuple(self._subscriptions)
        for subscription in subscriptions:
            with contextlib.suppress(RuntimeError):  # its loop closed
                subscription.loop.call_soon_threadsafe(
                    functools.partial(subscription.offer, job_id, progress=progress)
                )

    @contextlib.asynccontextmanager
    async def subscribe(self) -> AsyncIterator[Subscription]:
        """Receive every Job change published from now until the block ends."""
        subscription = Subscription(asyncio.get_running_loop())
        with self._lock:
            self._subscriptions.add(subscription)
        try:
            yield subscription
        finally:
            with self._lock:
                self._subscriptions.discard(subscription)
