"""Throttling repeated failed sign-ins for one username."""

import math
import threading
from collections import deque
from datetime import timedelta
from typing import Final

from medleyplay.application import Clock
from medleyplay.domain.accounts import Username
from medleyplay.domain.errors import SignInThrottledError

MAX_FAILURES: Final = 5
WINDOW: Final = timedelta(minutes=15)


class SignInThrottle:
    """Refuse sign-ins for a username after too many recent failures.

    After `max_failures` failures within `window`, sign-ins for that username are
    refused until the oldest of them is older than `window`. A success clears the
    username's failures. State lives in memory, so a restart clears it.
    """

    def __init__(
        self, clock: Clock, *, max_failures: int = MAX_FAILURES, window: timedelta = WINDOW
    ) -> None:
        """Create a throttle that reads the time from `clock`."""
        self._clock = clock
        self._max_failures = max_failures
        self._window = window
        self._failures: dict[Username, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, username: Username) -> None:
        """Raise `SignInThrottledError` when `username` has failed too often recently."""
        now = self._clock().timestamp()
        with self._lock:
            failures = self._recent(username, now)
            if len(failures) < self._max_failures:
                return
            retry_after = failures[0] + self._window.total_seconds() - now
        raise SignInThrottledError(max(1, math.ceil(retry_after)))

    def record_failure(self, username: Username) -> None:
        """Count a failed sign-in for `username`."""
        now = self._clock().timestamp()
        with self._lock:
            self._recent(username, now).append(now)

    def record_success(self, username: Username) -> None:
        """Forget `username`'s failures."""
        with self._lock:
            self._failures.pop(username, None)

    def _recent(self, username: Username, now: float) -> deque[float]:
        failures = self._failures.setdefault(username, deque())
        while failures and failures[0] <= now - self._window.total_seconds():
            failures.popleft()
        return failures
