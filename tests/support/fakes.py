"""Fakes for the core's boundaries: the clock and the Keychain."""

from datetime import UTC, datetime, timedelta

from medleyplay.domain.errors import KeychainUnavailableError


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


class MemorySecrets:
    """A Keychain in memory; `unavailable` makes every call fail as a locked Keychain does."""

    def __init__(self) -> None:
        self.items: dict[str, str] = {}
        self.unavailable = False

    def get(self, name: str) -> str | None:
        self._check()
        return self.items.get(name)

    def set(self, name: str, value: str) -> None:
        self._check()
        self.items[name] = value

    def delete(self, name: str) -> None:
        self._check()
        self.items.pop(name, None)

    def _check(self) -> None:
        if self.unavailable:
            message = "The Keychain didn't answer within 5 s."
            raise KeychainUnavailableError(message)
