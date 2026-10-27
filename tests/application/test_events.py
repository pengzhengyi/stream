"""Events reach every subscriber, Job progress paced, without a slow one holding anyone up."""

import asyncio
import threading

import pytest

from medleyplay.application.events import (
    MAX_QUEUED,
    MODE,
    Event,
    Events,
    Subscription,
    SubscriptionEndedError,
)
from medleyplay.domain.jobs import JobId


class Ticks:
    """A monotonic clock a test moves by hand."""

    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


async def _drained(subscription: Subscription) -> list[Event]:
    """Let published events land, then return what the subscriber has queued."""
    await asyncio.sleep(0.01)
    found = []
    while not subscription.queue.empty():
        found.append(subscription.queue.get_nowait())
    return found


def test_a_change_published_from_another_thread_reaches_every_subscriber() -> None:
    events = Events()

    async def scenario() -> tuple[Event, Event]:
        async with events.subscribe() as first, events.subscribe() as second:
            thread = threading.Thread(target=events.publish, args=(JobId(7),))
            thread.start()
            thread.join()
            return await first.next(), await second.next()

    assert asyncio.run(scenario()) == (7, 7)


def test_progress_is_sent_at_most_four_times_a_second_and_state_always() -> None:
    ticks = Ticks()
    events = Events(ticks)

    async def scenario() -> list[Event]:
        async with events.subscribe() as subscription:
            events.publish(JobId(1), progress=True)
            ticks.now += 0.1
            events.publish(JobId(1), progress=True)
            events.publish(JobId(1))
            ticks.now += 0.3
            events.publish(JobId(1), progress=True)
            return await _drained(subscription)

    assert asyncio.run(scenario()) == [1, 1, 1]


def test_a_full_queue_drops_progress_but_ends_on_a_change_of_state() -> None:
    ticks = Ticks()
    events = Events(ticks)

    async def scenario() -> tuple[int, bool, bool]:
        async with events.subscribe() as subscription:
            for job in range(MAX_QUEUED + 5):
                events.publish(JobId(job), progress=True)
            await asyncio.sleep(0.01)
            queued, ended_by_progress = subscription.queue.qsize(), subscription.ended
            events.publish(JobId(999))
            await asyncio.sleep(0.01)
            return queued, ended_by_progress, subscription.ended

    assert asyncio.run(scenario()) == (MAX_QUEUED, False, True)


def test_a_subscription_that_ended_raises_for_its_reader() -> None:
    events = Events()

    async def scenario() -> None:
        async with events.subscribe() as subscription:
            subscription.ended = True
            await subscription.next()

    with pytest.raises(SubscriptionEndedError):
        asyncio.run(scenario())


def test_a_change_after_the_subscription_closed_reaches_nobody() -> None:
    events = Events()

    async def scenario() -> Subscription:
        async with events.subscribe() as subscription:
            pass
        events.publish(JobId(1))
        return subscription

    assert asyncio.run(scenario()).queue.empty()


def test_a_listener_hears_each_change_of_state_but_not_progress() -> None:
    events = Events()
    heard: list[JobId] = []
    events.listen(heard.append)

    events.publish(JobId(1), progress=True)
    events.publish(JobId(1))
    events.publish(JobId(2))

    assert heard == [1, 2]


def test_a_change_of_mode_reaches_every_subscriber_and_no_job_listener() -> None:
    events = Events()
    heard: list[JobId] = []
    events.listen(heard.append)

    async def scenario() -> list[Event]:
        async with events.subscribe() as subscription:
            events.publish_mode()
            return await _drained(subscription)

    assert (asyncio.run(scenario()), heard) == ([MODE], [])
