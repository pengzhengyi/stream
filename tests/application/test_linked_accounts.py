"""Linked accounts: saving a login from pasted cookies, its state, and lending it to Jobs."""

from collections.abc import Iterator
from datetime import timedelta

import pytest
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application.accounts import AccountService
from medleyplay.application.linked_accounts import LentLogin, LinkedAccountService
from medleyplay.domain.accounts import Account
from medleyplay.domain.errors import InvalidInputError, KeychainUnavailableError, NotFoundError
from medleyplay.domain.linked_accounts import LinkState
from tests.support.factories import NewAccountFactory
from tests.support.fakes import FakeClock, MemorySecrets
from tests.support.hosts import started_plugins


def _cookies(session: str = "abc123") -> str:
    """A cookies file holding a Bilibili session and a token the plugin drops."""
    return (
        "# Netscape HTTP Cookie File\n"
        f".bilibili.com\tTRUE\t/\tTRUE\t0\tSESSDATA\t{session}\n"
        ".bilibili.com\tTRUE\t/\tFALSE\t0\tbili_jct\ttoken\n"
    )


def _kept(session: str = "abc123") -> str:
    return f".bilibili.com\tTRUE\t/\tTRUE\t0\tSESSDATA\t{session}\n"


@pytest.fixture
def alice(accounts: AccountService) -> Account:
    return accounts.create_first_admin(NewAccountFactory.admin()).account


@pytest.fixture
def secrets() -> MemorySecrets:
    return MemorySecrets()


@pytest.fixture
def linked(
    units: sessionmaker[Session], clock: FakeClock, secrets: MemorySecrets
) -> Iterator[LinkedAccountService]:
    with started_plugins(units, clock, "tube") as plugins:
        yield LinkedAccountService(units, clock, plugins, secrets)


def test_saving_keeps_only_what_the_plugin_keeps_in_the_keychain(
    linked: LinkedAccountService, secrets: MemorySecrets, alice: Account, clock: FakeClock
) -> None:
    saved = linked.save(alice, "bilibili", _cookies())

    assert (saved.site, saved.state, saved.saved_at, saved.revision) == (
        "bilibili",
        LinkState.VALID,
        clock.now,
        1,
    )
    assert secrets.items == {f"{alice.id}:bilibili": _kept()}
    assert linked.list_linked(alice) == [saved]


def test_saving_again_replaces_the_login_and_raises_its_revision(
    linked: LinkedAccountService, secrets: MemorySecrets, alice: Account
) -> None:
    linked.save(alice, "bilibili", _cookies("first"))

    saved = linked.save(alice, "bilibili", _cookies("second"))

    assert saved.revision == 2
    assert secrets.items == {f"{alice.id}:bilibili": _kept("second")}


def test_text_without_a_session_is_refused_and_nothing_is_kept(
    linked: LinkedAccountService, secrets: MemorySecrets, alice: Account
) -> None:
    with pytest.raises(InvalidInputError, match="no session"):
        linked.save(alice, "bilibili", "# Netscape HTTP Cookie File\n")

    assert secrets.items == {}
    assert linked.list_linked(alice) == []


def test_a_login_too_long_to_be_one_is_refused(
    linked: LinkedAccountService, alice: Account
) -> None:
    with pytest.raises(InvalidInputError, match="too long"):
        linked.save(alice, "bilibili", "x" * (64 * 1024 + 1))


def test_a_site_no_plugin_reads_logins_for_is_not_found(
    linked: LinkedAccountService, alice: Account
) -> None:
    with pytest.raises(NotFoundError):
        linked.save(alice, "youtube", _cookies())


def test_a_keychain_that_doesnt_answer_fails_the_save_and_keeps_no_row(
    linked: LinkedAccountService, secrets: MemorySecrets, alice: Account
) -> None:
    secrets.unavailable = True

    with pytest.raises(KeychainUnavailableError):
        linked.save(alice, "bilibili", _cookies())

    secrets.unavailable = False
    assert linked.list_linked(alice) == []


def test_removing_forgets_the_login_and_removing_again_is_fine(
    linked: LinkedAccountService, secrets: MemorySecrets, alice: Account
) -> None:
    linked.save(alice, "bilibili", _cookies())

    linked.remove(alice, "bilibili")
    linked.remove(alice, "bilibili")

    assert secrets.items == {}
    assert linked.list_linked(alice) == []


def test_a_login_past_its_expiry_needs_sign_in(
    linked: LinkedAccountService, alice: Account, clock: FakeClock
) -> None:
    expiring = _cookies().replace(
        "TRUE\t0\tSESSDATA", f"TRUE\t{int(clock.now.timestamp()) + 60}\tSESSDATA"
    )
    linked.save(alice, "bilibili", expiring)

    clock.advance(timedelta(minutes=2))

    assert [each.state for each in linked.list_linked(alice)] == [LinkState.NEEDS_SIGN_IN]
    assert linked.lend(alice.id, "bilibili") is None


def test_a_valid_login_is_lent_with_its_revision(
    linked: LinkedAccountService, alice: Account
) -> None:
    linked.save(alice, "bilibili", _cookies())

    assert linked.lend(alice.id, "bilibili") == LentLogin(_kept(), 1)
    assert linked.has_valid(alice.id, "bilibili")


def test_a_refused_login_needs_sign_in_and_isnt_lent(
    linked: LinkedAccountService, alice: Account
) -> None:
    linked.save(alice, "bilibili", _cookies())

    linked.refused(alice.id, "bilibili", 1)

    assert [each.state for each in linked.list_linked(alice)] == [LinkState.NEEDS_SIGN_IN]
    assert linked.lend(alice.id, "bilibili") is None
    assert not linked.has_valid(alice.id, "bilibili")


def test_a_late_refusal_of_an_older_login_leaves_the_newer_one_valid(
    linked: LinkedAccountService, alice: Account
) -> None:
    linked.save(alice, "bilibili", _cookies("old"))
    linked.save(alice, "bilibili", _cookies("new"))

    linked.refused(alice.id, "bilibili", 1)

    assert [each.state for each in linked.list_linked(alice)] == [LinkState.VALID]


def test_a_login_the_keychain_lost_needs_sign_in(
    linked: LinkedAccountService, secrets: MemorySecrets, alice: Account
) -> None:
    linked.save(alice, "bilibili", _cookies())
    secrets.items.clear()

    assert linked.lend(alice.id, "bilibili") is None
    assert [each.state for each in linked.list_linked(alice)] == [LinkState.NEEDS_SIGN_IN]


def test_forgetting_an_account_forgets_its_logins_on_every_site(
    linked: LinkedAccountService, secrets: MemorySecrets, alice: Account
) -> None:
    linked.save(alice, "bilibili", _cookies())

    linked.forget(alice.id)

    assert secrets.items == {}
    assert linked.list_linked(alice) == []
