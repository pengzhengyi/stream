"""Fakes for the core's boundaries: the clock."""

from datetime import UTC, datetime, timedelta


class FakeClock:
    """A clock that stands still until a test moves it.

    It starts at 2026-01-01 00:00 UTC.
    """

    def __init__(self, start: datetime = datetime(2026, 1, 1, tzinfo=UTC)) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, by: timedelta) -> None:
        """Move the clock forward."""
        self.now += by
