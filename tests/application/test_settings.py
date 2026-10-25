"""The household's settings: one document, changed by an admin at the revision they read."""

import pytest

from medleyplay.application.accounts import AccountService
from medleyplay.application.settings import SettingsService
from medleyplay.domain.accounts import Account
from medleyplay.domain.errors import ConflictError, ForbiddenError, InvalidInputError
from medleyplay.domain.settings import RemovalOrder, Settings
from tests.support.factories import NewAccountFactory

FIVE_GB = 5 * 10**9


def _alice_and_bob(accounts: AccountService) -> tuple[Account, Account]:
    """Return Alice, the admin, and Bob, a member."""
    alice = accounts.create_first_admin(NewAccountFactory.admin()).account
    return alice, accounts.create_account(alice, NewAccountFactory.member())


def test_settings_never_saved_have_no_limit_at_revision_zero(settings: SettingsService) -> None:
    assert settings.get() == Settings(
        storage_limit=None, removal_order=RemovalOrder.LEAST_FAVORITE, revision=0
    )


def test_an_admin_saves_settings_at_the_revision_read_and_gets_the_next_one(
    settings: SettingsService, accounts: AccountService
) -> None:
    alice, _ = _alice_and_bob(accounts)

    saved = settings.put(alice, Settings(storage_limit=FIVE_GB, revision=0))

    assert (saved.storage_limit, saved.revision) == (FIVE_GB, 1)
    assert settings.get() == saved


def test_saving_at_a_stale_revision_is_refused(
    settings: SettingsService, accounts: AccountService
) -> None:
    alice, _ = _alice_and_bob(accounts)
    settings.put(alice, Settings(storage_limit=FIVE_GB, revision=0))

    with pytest.raises(ConflictError, match="revision"):
        settings.put(alice, Settings(storage_limit=1, revision=0))

    assert settings.get().storage_limit == FIVE_GB


def test_only_an_admin_saves_settings(settings: SettingsService, accounts: AccountService) -> None:
    _, bob = _alice_and_bob(accounts)

    with pytest.raises(ForbiddenError):
        settings.put(bob, Settings(storage_limit=FIVE_GB, revision=0))


def test_a_negative_limit_is_refused(settings: SettingsService, accounts: AccountService) -> None:
    alice, _ = _alice_and_bob(accounts)

    with pytest.raises(InvalidInputError, match="limit"):
        settings.put(alice, Settings(storage_limit=-1, revision=0))


def test_saving_tells_whoever_listens_that_the_settings_changed(
    settings: SettingsService, accounts: AccountService, changes: list[str]
) -> None:
    alice, _ = _alice_and_bob(accounts)

    settings.put(alice, Settings(storage_limit=FIVE_GB, revision=0))

    assert changes == ["settings"]
