"""Accounts and sessions: creating Accounts, signing in and out, and managing roles."""

import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Final

from pwdlib import PasswordHash
from sqlalchemy import ColumnElement, delete, exists, func, insert, literal, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application import Clock
from medleyplay.application.throttle import SignInThrottle
from medleyplay.domain.accounts import (
    Account,
    AccountId,
    Role,
    Username,
    check_password,
    parse_display_name,
    parse_username,
)
from medleyplay.domain.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    NotSignedInError,
    SignInRefusedError,
)
from medleyplay.persistence.schema import AccountRow, SessionRow

SESSION_IDLE_TIMEOUT: Final = timedelta(days=30)
# A session's last-seen time is written at most this often, so reads stay reads.
LAST_SEEN_RESOLUTION: Final = timedelta(minutes=1)


@dataclass(frozen=True)
class NewAccount:
    """What an admin enters to create an Account; parsed when the service uses it."""

    username: str
    display_name: str
    password: str
    role: Role = Role.MEMBER


@dataclass(frozen=True)
class SignedIn:
    """A new session: its Account, and the token the browser keeps in a cookie."""

    account: Account
    token: str


class AccountService:
    """Create and manage Accounts, and turn passwords into sessions."""

    def __init__(
        self,
        units: sessionmaker[Session],
        hasher: PasswordHash,
        clock: Clock,
        throttle: SignInThrottle,
        *,
        idle_timeout: timedelta = SESSION_IDLE_TIMEOUT,
        new_token: Callable[[], str] = lambda: secrets.token_urlsafe(32),
        multiple_accounts: bool = False,
    ) -> None:
        """Create a service over the database `units` open.

        With `multiple_accounts` off, the household uses its first Account and no
        more can be created; Accounts that already exist keep working.
        """
        self._units = units
        self._hasher = hasher
        self._clock = clock
        self._throttle = throttle
        self._idle_timeout = idle_timeout
        self._new_token = new_token
        self._multiple_accounts = multiple_accounts

    @property
    def multiple_accounts(self) -> bool:
        """Return whether an admin may create more Accounts."""
        return self._multiple_accounts

    def is_set_up(self) -> bool:
        """Return whether the first admin exists."""
        with self._units() as db:
            return bool(db.scalar(select(exists().select_from(AccountRow))))

    def create_first_admin(self, new: NewAccount) -> SignedIn:
        """Create the household's first Account as an admin, and sign it in.

        Only one caller can ever succeed: the insert itself checks that no Account
        exists, so two simultaneous first registrations can't both become admin.
        """
        username, display_name = parse_username(new.username), parse_display_name(new.display_name)
        check_password(new.password)
        password_hash = self._hasher.hash(new.password)
        with self._units.begin() as db:
            first_only = select(
                literal(username),
                literal(display_name),
                literal(password_hash),
                literal(Role.ADMIN.value),
                literal(self._clock(), AccountRow.created_at.type),
            ).where(~exists().select_from(AccountRow))
            columns = ["username", "display_name", "password_hash", "role", "created_at"]
            inserted = db.connection().execute(insert(AccountRow).from_select(columns, first_only))
            if inserted.rowcount != 1:
                message = "medleyplay is already set up; an admin creates new Accounts."
                raise ConflictError(message)
            row = db.scalars(select(AccountRow).where(AccountRow.username == username)).one()
            return self._start_session(db, row)

    def create_account(self, caller: Account, new: NewAccount) -> Account:
        """Create an Account; only an admin may, and only with several Accounts turned on."""
        _require_admin(caller)
        if not self._multiple_accounts:
            message = "This server has one Account; turn on several Accounts to add more."
            raise ForbiddenError(message)
        username, display_name = parse_username(new.username), parse_display_name(new.display_name)
        check_password(new.password)
        row = AccountRow(
            username=username,
            display_name=display_name,
            password_hash=self._hasher.hash(new.password),
            role=new.role.value,
            created_at=self._clock(),
        )
        try:
            with self._units.begin() as db:
                db.add(row)
        except IntegrityError as error:
            message = f"The username {username!r} is taken."
            raise ConflictError(message) from error
        return _to_account(row)

    def list_accounts(self, caller: Account) -> list[Account]:
        """Return every Account, by username; only an admin may."""
        _require_admin(caller)
        with self._units() as db:
            rows = db.scalars(select(AccountRow).order_by(AccountRow.username))
            return [_to_account(row) for row in rows]

    def set_role(self, caller: Account, account_id: AccountId, role: Role) -> Account:
        """Make an Account an admin or a member; the last admin can't become a member."""
        _require_admin(caller)
        with self._units.begin() as db:
            change = update(AccountRow).where(AccountRow.id == account_id).values(role=role.value)
            if role is Role.MEMBER:
                change = change.where(_not_the_last_admin())
            if db.connection().execute(change).rowcount != 1:
                _raise_missing_or_last_admin(db, account_id)
            return _to_account(db.get_one(AccountRow, account_id))

    def delete_account(self, caller: Account, account_id: AccountId) -> None:
        """Delete an Account with its sessions, state, and Playlists; never the last admin.

        Deleting an Account that no longer exists does nothing, so a retry is safe.
        """
        _require_admin(caller)
        with self._units.begin() as db:
            removal = delete(AccountRow).where(AccountRow.id == account_id, _not_the_last_admin())
            removed = db.connection().execute(removal).rowcount
            if removed != 1 and db.get(AccountRow, account_id) is not None:
                _raise_missing_or_last_admin(db, account_id)

    def sign_in(self, username: str, password: str) -> SignedIn:
        """Check a username and password and start a session.

        Unknown usernames take as long as wrong passwords, so a response's timing
        doesn't reveal which usernames exist.
        """
        name = parse_username(username)
        self._throttle.check(name)
        with self._units.begin() as db:
            row = db.scalars(select(AccountRow).where(AccountRow.username == name)).one_or_none()
            if row is None:
                self._hasher.hash(password)
                valid, updated_hash = False, None
            else:
                valid, updated_hash = self._hasher.verify_and_update(password, row.password_hash)
            if row is None or not valid:
                self._throttle.record_failure(name)
                raise SignInRefusedError
            if updated_hash is not None:
                row.password_hash = updated_hash
            self._throttle.record_success(name)
            return self._start_session(db, row)

    def authenticate(self, token: str) -> Account:
        """Return the Account a session token belongs to, keeping the session alive."""
        now = self._clock()
        with self._units.begin() as db:
            found = db.scalars(
                select(SessionRow).where(SessionRow.token_hash == _hash_token(token))
            ).one_or_none()
            if found is None:
                raise NotSignedInError
            expired = now - found.last_seen_at > self._idle_timeout
            if expired:
                db.delete(found)
            elif now - found.last_seen_at >= LAST_SEEN_RESOLUTION:
                found.last_seen_at = now
            account = None if expired else _to_account(db.get_one(AccountRow, found.account_id))
        if account is None:
            raise NotSignedInError
        return account

    def sign_out(self, token: str) -> None:
        """End one session; ending one that has already ended does nothing."""
        with self._units.begin() as db:
            db.execute(delete(SessionRow).where(SessionRow.token_hash == _hash_token(token)))

    def sign_out_everywhere(self, account: Account) -> None:
        """End every session of `account`."""
        with self._units.begin() as db:
            db.execute(delete(SessionRow).where(SessionRow.account_id == account.id))

    def reset_password(self, username: str, password: str) -> None:
        """Set a new password and end the Account's sessions; for the command line."""
        name = parse_username(username)
        check_password(password)
        with self._units.begin() as db:
            row = db.scalars(select(AccountRow).where(AccountRow.username == name)).one_or_none()
            if row is None:
                message = f"No Account has the username {name!r}."
                raise NotFoundError(message)
            row.password_hash = self._hasher.hash(password)
            db.execute(delete(SessionRow).where(SessionRow.account_id == row.id))

    def _start_session(self, db: Session, row: AccountRow) -> SignedIn:
        token = self._new_token()
        now = self._clock()
        db.add(
            SessionRow(
                account_id=row.id, token_hash=_hash_token(token), created_at=now, last_seen_at=now
            )
        )
        return SignedIn(_to_account(row), token)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _to_account(row: AccountRow) -> Account:
    return Account(
        id=AccountId(row.id),
        username=Username(row.username),
        display_name=row.display_name,
        role=Role(row.role),
    )


def _require_admin(caller: Account) -> None:
    if not caller.is_admin:
        message = "Only an admin manages Accounts."
        raise ForbiddenError(message)


def _not_the_last_admin() -> ColumnElement[bool]:
    # Evaluated inside the same statement as the change, so two admins demoting
    # each other at once can't leave the household without one.
    admins = select(func.count()).select_from(AccountRow).where(AccountRow.role == "admin")
    return (AccountRow.role != Role.ADMIN.value) | (admins.scalar_subquery() > 1)


def _raise_missing_or_last_admin(db: Session, account_id: AccountId) -> None:
    if db.get(AccountRow, account_id) is None:
        message = f"No Account has the id {account_id}."
        raise NotFoundError(message)
    message = "The household needs an admin; make another Account an admin first."
    raise ConflictError(message)
