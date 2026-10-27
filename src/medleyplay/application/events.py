"""Events: telling every open browser when a Job or the Mode changes, as it happens.

The runner and the services publish a Job's id after they commit, and the Mode
service publishes `MODE` when the Mode changes, from any thread; each
subscriber, one per open event stream, receives it on the event loop and reads
the Job or the Mode as it now stands.

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
from typing import Final, Literal

from medleyplay.domain.jobs import JobId

MODE: Final = "mode"
"""The event that the Mode changed."""
MAX_QUEUED: Final = 64
PROGRESS_INTERVAL: Final = 0.25
"""At most four progress events a second for one Job."""


type Event = JobId | Literal["mode"]
"""A Job that changed, or `MODE`."""


class SubscriptionEndedError(Exception):
    """The subscriber fell too far behind, and missed a change of state."""


@dataclass(eq=False)
class Subscription:
    """One event stream's queue of events, read on the event loop."""

    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue[Event] = field(default_factory=lambda: asyncio.Queue(MAX_QUEUED))
    ended: bool = False

    async def next(self) -> Event:
        """Return the next event; raise `SubscriptionEndedError` once ended."""
        if self.ended:
            raise SubscriptionEndedError
        event = await self.queue.get()
        if self.ended:
            raise SubscriptionEndedError
        return event

    def offer(self, event: Event, *, progress: bool) -> None:
        """Queue the event, on the event loop; a full queue drops progress and ends on state."""
        if self.ended:
            return
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            if not progress:
                self.ended = True
                # Wake a reader waiting on the queue, so it sees the end.
                with contextlib.suppress(asyncio.QueueEmpty):
                    self.queue.get_nowait()
                self.queue.put_nowait(event)


class Events:
    """Where Job and Mode changes are published, and event streams subscribe to them."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        """Create a hub with no subscribers; `clock` paces progress events."""
        self._clock = clock
        self._lock = threading.Lock()
        self._subscriptions: set[Subscription] = set()
        self._listeners: list[Callable[[JobId], None]] = []
        self._last_progress: dict[JobId, float] = {}

    def listen(self, listener: Callable[[JobId], None]) -> None:
        """Call `listener` with each Job whose state changes, on the publishing thread."""
        with self._lock:
            self._listeners.append(listener)

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
            listeners = () if progress else tuple(self._listeners)
        for listener in listeners:
            listener(job_id)
        self._offer(subscriptions, job_id, progress=progress)

    def publish_mode(self) -> None:
        """Tell every subscriber the Mode changed; callable from any thread."""
        with self._lock:
            subscriptions = tuple(self._subscriptions)
        self._offer(subscriptions, MODE, progress=False)

    @contextlib.asynccontextmanager
    async def subscribe(self) -> AsyncIterator[Subscription]:
        """Receive every event published from now until the block ends."""
        subscription = Subscription(asyncio.get_running_loop())
        with self._lock:
            self._subscriptions.add(subscription)
        try:
            yield subscription
        finally:
            with self._lock:
                self._subscriptions.discard(subscription)

    @staticmethod
    def _offer(subscriptions: tuple[Subscription, ...], event: Event, *, progress: bool) -> None:
        for subscription in subscriptions:
            with contextlib.suppress(RuntimeError):  # its loop closed
                subscription.loop.call_soon_threadsafe(
                    functools.partial(subscription.offer, event, progress=progress)
                )
