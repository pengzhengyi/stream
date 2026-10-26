"""Secrets the core keeps outside the database: linked accounts' logins, in the Keychain.

macOS can ask for access to the Keychain, or keep it locked, and `keyring` waits
meanwhile, so every call has a time limit and fails as `KeychainUnavailableError`.
"""

import sys
import threading
from collections.abc import Callable
from datetime import timedelta
from typing import Final, Protocol

import keyring
import keyring.errors
from keyring.backend import KeyringBackend

from medleyplay.domain.errors import KeychainUnavailableError
from medleyplay.domain.linked_accounts import KEYCHAIN_SERVICE

KEYCHAIN_TIMEOUT: Final = timedelta(seconds=5)


class Secrets(Protocol):
    """Where secrets are kept, by name."""

    def get(self, name: str) -> str | None:
        """Return the secret, or `None` when there is none."""
        ...

    def set(self, name: str, value: str) -> None:
        """Keep `value`, replacing any secret of that name."""
        ...

    def delete(self, name: str) -> None:
        """Forget the secret; forgetting one that isn't there is fine."""
        ...


class KeychainSecrets:
    """Secrets in the macOS Keychain, under one service, each call bounded in time."""

    def __init__(
        self,
        service: str = KEYCHAIN_SERVICE,
        backend: KeyringBackend | None = None,
        timeout: timedelta = KEYCHAIN_TIMEOUT,
    ) -> None:
        """Keep secrets under `service`, in `backend` or the system's Keychain.

        On macOS the system's Keychain is the Keychain itself, never `keyring`'s
        chain of every backend it finds: a chain asks each backend in turn for a
        secret the Keychain lacks, so any other backend installed, even a stalled
        one, would answer in its place.
        """
        self._service = service
        self._backend = backend
        self._timeout = timeout

    def get(self, name: str) -> str | None:
        """Return the secret, or `None` when there is none."""
        return self._bounded(lambda keys: keys.get_password(self._service, name))

    def set(self, name: str, value: str) -> None:
        """Keep `value`, replacing any secret of that name."""
        self._bounded(lambda keys: keys.set_password(self._service, name, value))

    def delete(self, name: str) -> None:
        """Forget the secret; forgetting one that isn't there is fine."""

        def delete(keys: KeyringBackend) -> None:
            try:
                keys.delete_password(self._service, name)
            except keyring.errors.PasswordDeleteError:
                return

        self._bounded(delete)

    def _bounded[T](self, call: Callable[[KeyringBackend], T]) -> T:
        # A daemon thread per call, so one that never returns can't hold up the next.
        outcome: list[T] = []
        failure: list[BaseException] = []

        def run() -> None:
            try:
                outcome.append(call(self._backend or _system_keychain()))
            except Exception as error:  # noqa: BLE001 -- reported to the caller below
                failure.append(error)

        thread = threading.Thread(target=run, name="keychain", daemon=True)
        thread.start()
        thread.join(self._timeout.total_seconds())
        if thread.is_alive():
            message = f"The Keychain didn't answer within {self._timeout.total_seconds():g} s."
            raise KeychainUnavailableError(message)
        if failure:
            message = f"The Keychain refused: {type(failure[0]).__name__}."
            raise KeychainUnavailableError(message) from failure[0]
        return outcome[0]


def _system_keychain(platform: str = sys.platform) -> KeyringBackend:
    if platform == "darwin":  # pragma: no cover -- CI runs on Linux
        from keyring.backends import macOS  # noqa: PLC0415 -- it exists only on macOS

        return macOS.Keyring()  # type: ignore[no-untyped-call] # keyring's own __init__ is untyped
    return keyring.get_keyring()  # pragma: no cover -- the suites always pass a backend
