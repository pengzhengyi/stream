"""Fakes for the core's boundaries: the clock, the Keychain, and the network."""

from datetime import UTC, datetime, timedelta

from medleyplay.domain.errors import KeychainUnavailableError
from medleyplay.domain.mode import Network, Unread
from tests.support.factories import NetworkFactory


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


class FakeNetwork:
    """The network the server is on, as a test sets it: the home Wi-Fi unless changed."""

    def __init__(self) -> None:
        self.network: Network | Unread | None = NetworkFactory.home_wifi()

    def __call__(self) -> Network | Unread | None:
        return self.network


class FakeInternet:
    """Whether the connectivity check reaches the internet, as a test sets it; it counts checks."""

    def __init__(self) -> None:
        self.reachable = True
        self.checks = 0

    def __call__(self) -> bool:
        self.checks += 1
        return self.reachable
