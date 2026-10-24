"""Throttling failed sign-ins."""

from datetime import timedelta

import pytest

from medleyplay.application.throttle import SignInThrottle
from medleyplay.domain.accounts import Username
from medleyplay.domain.errors import SignInThrottledError
from tests.support.fakes import FakeClock

ALICE = Username("alice")


def _throttle_after_failures(clock: FakeClock, failures: int) -> SignInThrottle:
    """Return a throttle (5 failures in 15 minutes) that has seen `failures` for Alice."""
    throttle = SignInThrottle(clock)
    for _ in range(failures):
        throttle.record_failure(ALICE)
    return throttle


def test_four_recent_failures_still_allow_a_sign_in(clock: FakeClock) -> None:
    throttle = _throttle_after_failures(clock, 4)

    throttle.check(ALICE)


def test_the_fifth_recent_failure_refuses_sign_ins_for_the_rest_of_the_window(
    clock: FakeClock,
) -> None:
    throttle = _throttle_after_failures(clock, 5)
    clock.advance(timedelta(minutes=5))

    with pytest.raises(SignInThrottledError) as refused:
        throttle.check(ALICE)

    assert refused.value.retry_after_seconds == 10 * 60


def test_failures_older_than_the_window_no_longer_count(clock: FakeClock) -> None:
    throttle = _throttle_after_failures(clock, 5)
    clock.advance(timedelta(minutes=15))

    throttle.check(ALICE)


def test_a_success_clears_the_failures(clock: FakeClock) -> None:
    throttle = _throttle_after_failures(clock, 4)

    throttle.record_success(ALICE)
    throttle.record_failure(ALICE)

    throttle.check(ALICE)


def test_one_usernames_failures_do_not_throttle_another(clock: FakeClock) -> None:
    throttle = _throttle_after_failures(clock, 5)

    throttle.check(Username("bob"))
