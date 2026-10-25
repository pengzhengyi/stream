"""Secrets in the Keychain: kept, replaced, forgotten, and bounded when the Keychain stalls."""

import os
import sys
import threading
import uuid
from datetime import timedelta

import pytest
from keyring.backend import KeyringBackend
from keyring.errors import KeyringLocked, PasswordDeleteError

from medleyplay.application.secrets import KeychainSecrets
from medleyplay.domain.errors import KeychainUnavailableError


class MemoryKeyring(KeyringBackend):
    """A keyring backend in memory, standing in for the Keychain."""

    priority = 1

    def __init__(self) -> None:
        super().__init__()  # type: ignore[no-untyped-call] # keyring's own __init__ is untyped
        self.items: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.items.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.items[service, username] = password

    def delete_password(self, service: str, username: str) -> None:
        if self.items.pop((service, username), None) is None:
            raise PasswordDeleteError(username)


class StalledKeyring(MemoryKeyring):
    """A Keychain waiting on an access prompt nobody answers."""

    def __init__(self) -> None:
        super().__init__()
        self.release = threading.Event()

    def get_password(self, service: str, username: str) -> str | None:
        self.release.wait()
        return None


class LockedKeyring(MemoryKeyring):
    def set_password(self, service: str, username: str, password: str) -> None:
        raise KeyringLocked


def test_a_secret_is_kept_replaced_and_forgotten() -> None:
    backend = MemoryKeyring()
    secrets = KeychainSecrets(backend=backend)

    secrets.set("3:bilibili", "first")
    secrets.set("3:bilibili", "second")

    assert secrets.get("3:bilibili") == "second"
    assert backend.items == {("medleyplay", "3:bilibili"): "second"}
    secrets.delete("3:bilibili")
    assert secrets.get("3:bilibili") is None


def test_forgetting_a_secret_that_is_not_there_is_fine() -> None:
    KeychainSecrets(backend=MemoryKeyring()).delete("3:bilibili")


def test_a_keychain_that_does_not_answer_fails_within_the_limit() -> None:
    backend = StalledKeyring()
    secrets = KeychainSecrets(backend=backend, timeout=timedelta(seconds=0.05))

    try:
        with pytest.raises(KeychainUnavailableError, match="didn't answer"):
            secrets.get("3:bilibili")
    finally:
        backend.release.set()


def test_a_locked_keychain_fails_saying_so() -> None:
    with pytest.raises(KeychainUnavailableError, match="KeyringLocked"):
        KeychainSecrets(backend=LockedKeyring()).set("3:bilibili", "x")


@pytest.mark.skipif(
    sys.platform != "darwin" or not os.environ.get("MEDLEYPLAY_KEYCHAIN_TEST"),
    reason="touches the real Keychain; set MEDLEYPLAY_KEYCHAIN_TEST=1 on macOS",
)
def test_the_real_keychain_keeps_and_forgets_a_secret() -> None:
    secrets = KeychainSecrets(service="medleyplay-test")
    name = f"test:{uuid.uuid4()}"

    secrets.set(name, "secret")
    try:
        assert secrets.get(name) == "secret"
    finally:
        secrets.delete(name)
    assert secrets.get(name) is None
