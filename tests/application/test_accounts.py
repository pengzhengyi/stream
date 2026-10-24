"""Accounts and sessions: the first admin, sign-in, roles, and the last-admin rule."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta

import pytest
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application.accounts import AccountService, NewAccount, SignedIn
from medleyplay.application.throttle import SignInThrottle
from medleyplay.domain.accounts import Account, AccountId, Role
from medleyplay.domain.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    NotSignedInError,
    SignInRefusedError,
    SignInThrottledError,
)
from medleyplay.persistence.schema import AccountRow, SessionRow
from tests.support.factories import PASSWORD, AccountFactory, NewAccountFactory
from tests.support.fakes import FakeClock


def _household(accounts: AccountService) -> tuple[Account, Account]:
    """Return Alice, the first admin, and Bob, a member she created."""
    alice = accounts.create_first_admin(NewAccountFactory.admin()).account
    bob = accounts.create_account(alice, NewAccountFactory.member())
    return alice, bob


def test_before_the_first_admin_exists_the_server_is_not_set_up(
    accounts: AccountService,
) -> None:
    assert not accounts.is_set_up()


def test_the_first_account_becomes_an_admin_and_is_signed_in(accounts: AccountService) -> None:
    signed_in = accounts.create_first_admin(NewAccountFactory.member("Alice"))

    assert signed_in.account.role is Role.ADMIN
    assert signed_in.account.username == "alice"
    assert accounts.authenticate(signed_in.token) == signed_in.account
    assert accounts.is_set_up()


def test_a_second_first_admin_is_refused(accounts: AccountService) -> None:
    accounts.create_first_admin(NewAccountFactory.admin())

    with pytest.raises(ConflictError, match="already set up"):
        accounts.create_first_admin(NewAccountFactory.admin("mallory"))


def test_simultaneous_first_registrations_make_exactly_one_admin(
    accounts: AccountService, units: sessionmaker[Session]
) -> None:
    candidates = [NewAccountFactory.admin(f"user{i}") for i in range(8)]

    def register(candidate: NewAccount) -> SignedIn | ConflictError:
        try:
            return accounts.create_first_admin(candidate)
        except ConflictError as refused:
            return refused

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(register, candidates))

    assert sum(isinstance(outcome, SignedIn) for outcome in outcomes) == 1
    with units() as db:
        assert len(db.scalars(select(AccountRow)).all()) == 1


def test_an_admin_creates_a_member(accounts: AccountService) -> None:
    alice = accounts.create_first_admin(NewAccountFactory.admin()).account

    bob = accounts.create_account(alice, NewAccountFactory.member())

    assert (bob.username, bob.role) == ("bob", Role.MEMBER)
    assert accounts.list_accounts(alice) == [alice, bob]


def test_a_member_may_not_create_or_list_accounts(accounts: AccountService) -> None:
    _, bob = _household(accounts)

    with pytest.raises(ForbiddenError):
        accounts.create_account(bob, NewAccountFactory.member("carol"))
    with pytest.raises(ForbiddenError):
        accounts.list_accounts(bob)


def test_a_username_differing_only_in_case_is_taken(accounts: AccountService) -> None:
    alice, _ = _household(accounts)

    with pytest.raises(ConflictError, match="'bob' is taken"):
        accounts.create_account(alice, NewAccountFactory.member("BOB"))


def test_signing_in_with_the_right_password_starts_a_session(accounts: AccountService) -> None:
    _, bob = _household(accounts)

    signed_in = accounts.sign_in("Bob", PASSWORD)

    assert signed_in.account == bob
    assert accounts.authenticate(signed_in.token) == bob


@pytest.mark.parametrize(
    ("username", "password"), [("bob", "wrong password"), ("nobody", PASSWORD)]
)
def test_a_wrong_password_or_unknown_username_is_refused_alike(
    accounts: AccountService, username: str, password: str
) -> None:
    _household(accounts)

    with pytest.raises(SignInRefusedError):
        accounts.sign_in(username, password)


def test_five_failed_sign_ins_throttle_even_the_right_password(accounts: AccountService) -> None:
    _household(accounts)
    for _ in range(5):
        with pytest.raises(SignInRefusedError):
            accounts.sign_in("bob", "wrong password")

    with pytest.raises(SignInThrottledError):
        accounts.sign_in("bob", PASSWORD)


def test_signing_in_rehashes_a_password_hashed_with_old_parameters(
    units: sessionmaker[Session], hasher: PasswordHash, clock: FakeClock
) -> None:
    old = AccountService(units, hasher, clock, SignInThrottle(clock))
    old.create_first_admin(NewAccountFactory.admin())
    stronger = PasswordHash((Argon2Hasher(time_cost=2, memory_cost=16, parallelism=1),))
    with units() as db:
        before = db.scalars(select(AccountRow.password_hash)).one()

    AccountService(units, stronger, clock, SignInThrottle(clock)).sign_in("alice", PASSWORD)

    with units() as db:
        after = db.scalars(select(AccountRow.password_hash)).one()
    assert after != before
    assert stronger.verify(PASSWORD, after)


def test_an_unknown_token_is_not_signed_in(accounts: AccountService) -> None:
    with pytest.raises(NotSignedInError):
        accounts.authenticate("not-a-token")


def test_a_session_idle_for_more_than_30_days_has_ended(
    accounts: AccountService, clock: FakeClock
) -> None:
    signed_in = accounts.create_first_admin(NewAccountFactory.admin())
    clock.advance(timedelta(days=30, seconds=1))

    with pytest.raises(NotSignedInError):
        accounts.authenticate(signed_in.token)


def test_an_ended_session_is_deleted_so_it_never_comes_back(
    accounts: AccountService, clock: FakeClock, units: sessionmaker[Session]
) -> None:
    signed_in = accounts.create_first_admin(NewAccountFactory.admin())
    clock.advance(timedelta(days=31))
    with pytest.raises(NotSignedInError):
        accounts.authenticate(signed_in.token)

    with units() as db:
        assert db.scalars(select(SessionRow)).all() == []


def test_using_a_session_keeps_it_alive(accounts: AccountService, clock: FakeClock) -> None:
    signed_in = accounts.create_first_admin(NewAccountFactory.admin())
    for _ in range(3):
        clock.advance(timedelta(days=20))
        accounts.authenticate(signed_in.token)

    assert accounts.authenticate(signed_in.token) == signed_in.account


def test_the_database_keeps_only_a_hash_of_the_session_token(
    accounts: AccountService, units: sessionmaker[Session]
) -> None:
    signed_in = accounts.create_first_admin(NewAccountFactory.admin())

    with units() as db:
        stored = db.scalars(select(SessionRow.token_hash)).one()
    assert signed_in.token not in stored
    assert len(stored) == 64


def test_signing_out_ends_only_that_session_and_is_safe_to_repeat(
    accounts: AccountService,
) -> None:
    _household(accounts)
    phone, laptop = accounts.sign_in("bob", PASSWORD), accounts.sign_in("bob", PASSWORD)

    accounts.sign_out(phone.token)
    accounts.sign_out(phone.token)

    with pytest.raises(NotSignedInError):
        accounts.authenticate(phone.token)
    assert accounts.authenticate(laptop.token) == laptop.account


def test_signing_out_everywhere_ends_every_session_of_that_account_only(
    accounts: AccountService,
) -> None:
    alice, bob = _household(accounts)
    phone, laptop = accounts.sign_in("bob", PASSWORD), accounts.sign_in("bob", PASSWORD)
    alices = accounts.sign_in("alice", PASSWORD)

    accounts.sign_out_everywhere(bob)

    for ended in (phone, laptop):
        with pytest.raises(NotSignedInError):
            accounts.authenticate(ended.token)
    assert accounts.authenticate(alices.token) == alice


def test_an_admin_promotes_a_member_and_then_may_be_demoted(accounts: AccountService) -> None:
    alice, bob = _household(accounts)

    accounts.set_role(alice, bob.id, Role.ADMIN)
    demoted = accounts.set_role(alice, alice.id, Role.MEMBER)

    assert demoted == replace(alice, role=Role.MEMBER)


def test_the_last_admin_cannot_be_demoted(accounts: AccountService) -> None:
    alice, _ = _household(accounts)

    with pytest.raises(ConflictError, match="needs an admin"):
        accounts.set_role(alice, alice.id, Role.MEMBER)


def test_setting_a_role_on_a_missing_account_is_not_found(accounts: AccountService) -> None:
    alice, _ = _household(accounts)

    with pytest.raises(NotFoundError):
        accounts.set_role(alice, AccountId(404), Role.ADMIN)


def test_a_member_may_not_change_roles(accounts: AccountService) -> None:
    _, bob = _household(accounts)

    with pytest.raises(ForbiddenError):
        accounts.set_role(bob, bob.id, Role.ADMIN)


def test_deleting_an_account_ends_its_sessions_and_is_safe_to_repeat(
    accounts: AccountService,
) -> None:
    alice, bob = _household(accounts)
    bobs = accounts.sign_in("bob", PASSWORD)

    accounts.delete_account(alice, bob.id)
    accounts.delete_account(alice, bob.id)

    assert accounts.list_accounts(alice) == [alice]
    with pytest.raises(NotSignedInError):
        accounts.authenticate(bobs.token)


def test_the_last_admin_cannot_be_deleted(accounts: AccountService) -> None:
    alice, _ = _household(accounts)

    with pytest.raises(ConflictError, match="needs an admin"):
        accounts.delete_account(alice, alice.id)


def test_a_member_may_not_delete_accounts(accounts: AccountService) -> None:
    alice, _ = _household(accounts)

    with pytest.raises(ForbiddenError):
        accounts.delete_account(AccountFactory.member(), alice.id)


def test_resetting_a_password_replaces_it_and_signs_the_account_out(
    accounts: AccountService,
) -> None:
    _household(accounts)
    old_session = accounts.sign_in("bob", PASSWORD)

    accounts.reset_password("bob", "a brand new password")

    with pytest.raises(NotSignedInError):
        accounts.authenticate(old_session.token)
    with pytest.raises(SignInRefusedError):
        accounts.sign_in("bob", PASSWORD)
    assert accounts.sign_in("bob", "a brand new password").account.username == "bob"


def test_resetting_the_password_of_an_unknown_username_is_not_found(
    accounts: AccountService,
) -> None:
    with pytest.raises(NotFoundError, match="'nobody'"):
        accounts.reset_password("nobody", "a brand new password")


def test_with_one_account_the_first_admin_is_created_but_no_more(
    units: sessionmaker[Session], hasher: PasswordHash, clock: FakeClock
) -> None:
    one_account = AccountService(units, hasher, clock, SignInThrottle(clock))
    alice = one_account.create_first_admin(NewAccountFactory.admin()).account

    with pytest.raises(ForbiddenError, match="one Account"):
        one_account.create_account(alice, NewAccountFactory.member())

    assert not one_account.multiple_accounts
    assert one_account.list_accounts(alice) == [alice]


def test_turning_several_accounts_off_leaves_existing_accounts_working(
    accounts: AccountService, units: sessionmaker[Session], hasher: PasswordHash, clock: FakeClock
) -> None:
    _household(accounts)

    one_account = AccountService(units, hasher, clock, SignInThrottle(clock))

    assert one_account.sign_in("bob", PASSWORD).account.username == "bob"
