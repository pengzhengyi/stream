"""The Accounts API: first-time setup, signing in and out, and managing Accounts."""

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

from medleyplay.application.accounts import SESSION_IDLE_TIMEOUT, NewAccount, SignedIn
from medleyplay.domain.accounts import MAX_PASSWORD_LENGTH, Account, AccountId, Role
from medleyplay.web.deps import (
    SESSION_COOKIE,
    AccountsDep,
    LinkedDep,
    SessionToken,
    SignedInAccount,
)
from medleyplay.web.ids import RowId

router = APIRouter(prefix="/api", tags=["accounts"])


class AccountOut(BaseModel):
    """An Account as the API shows it; never its password."""

    id: int
    username: str
    display_name: str
    role: Role

    @classmethod
    def of(cls, account: Account) -> "AccountOut":
        """Return the API view of `account`."""
        return cls(
            id=account.id,
            username=account.username,
            display_name=account.display_name,
            role=account.role,
        )


class SetupStatus(BaseModel):
    """Whether the first admin has been created, and whether more Accounts may be."""

    set_up: bool
    multiple_accounts: bool


class AccountIn(BaseModel):
    """A new Account."""

    username: str = Field(examples=["alice"])
    display_name: str = Field(examples=["Alice"])
    password: str = Field(max_length=MAX_PASSWORD_LENGTH, examples=["correct horse battery"])
    role: Role = Role.MEMBER

    def to_new_account(self) -> NewAccount:
        """Return the application's form of this request."""
        return NewAccount(self.username, self.display_name, self.password, self.role)


class Credentials(BaseModel):
    """A username and password."""

    username: str = Field(examples=["alice"])
    password: str = Field(max_length=MAX_PASSWORD_LENGTH, examples=["correct horse battery"])


class RoleIn(BaseModel):
    """A role to give an Account."""

    role: Role


@router.get("/setup")
def setup_status(accounts: AccountsDep) -> SetupStatus:
    """Return whether the first admin exists yet."""
    return SetupStatus(set_up=accounts.is_set_up(), multiple_accounts=accounts.multiple_accounts)


@router.post("/setup", status_code=status.HTTP_201_CREATED)
def set_up(body: AccountIn, response: Response, accounts: AccountsDep) -> AccountOut:
    """Create the first Account, as an admin, and sign it in; refused once set up."""
    signed_in = accounts.create_first_admin(body.to_new_account())
    return _with_cookie(response, signed_in)


@router.post("/session")
def sign_in(body: Credentials, response: Response, accounts: AccountsDep) -> AccountOut:
    """Sign in, setting the session cookie."""
    return _with_cookie(response, accounts.sign_in(body.username, body.password))


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
def sign_out(response: Response, accounts: AccountsDep, token: SessionToken = None) -> None:
    """Sign out this browser; signing out twice is fine."""
    if token is not None:
        accounts.sign_out(token)
    response.delete_cookie(SESSION_COOKIE)


@router.delete("/sessions", status_code=status.HTTP_204_NO_CONTENT)
def sign_out_everywhere(response: Response, me: SignedInAccount, accounts: AccountsDep) -> None:
    """Sign out every browser signed in as you, this one included."""
    accounts.sign_out_everywhere(me)
    response.delete_cookie(SESSION_COOKIE)


@router.get("/me")
def who_am_i(me: SignedInAccount) -> AccountOut:
    """Return the signed-in Account."""
    return AccountOut.of(me)


@router.get("/accounts")
def list_accounts(me: SignedInAccount, accounts: AccountsDep) -> list[AccountOut]:
    """Return every Account; admins only."""
    return [AccountOut.of(account) for account in accounts.list_accounts(me)]


@router.post("/accounts", status_code=status.HTTP_201_CREATED)
def create_account(body: AccountIn, me: SignedInAccount, accounts: AccountsDep) -> AccountOut:
    """Create an Account; admins only, with several Accounts on. A taken username is refused."""
    return AccountOut.of(accounts.create_account(me, body.to_new_account()))


@router.put("/accounts/{account_id}/role")
def set_role(
    account_id: RowId, body: RoleIn, me: SignedInAccount, accounts: AccountsDep
) -> AccountOut:
    """Make an Account an admin or a member; admins only. The last admin stays an admin."""
    return AccountOut.of(accounts.set_role(me, AccountId(account_id), body.role))


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    account_id: RowId, me: SignedInAccount, accounts: AccountsDep, linked: LinkedDep
) -> None:
    """Delete an Account and everything that is its own; admins only. Never the last admin.

    Its logins on sites are forgotten too, from the Keychain as well as the catalog.
    """
    accounts.delete_account(me, AccountId(account_id))
    linked.forget(AccountId(account_id))


def _with_cookie(response: Response, signed_in: SignedIn) -> AccountOut:
    # Plain HTTP on the LAN in the MVP, so the cookie can't be `Secure`.
    response.set_cookie(
        SESSION_COOKIE,
        signed_in.token,
        max_age=int(SESSION_IDLE_TIMEOUT.total_seconds()),
        httponly=True,
        samesite="lax",
    )
    return AccountOut.of(signed_in.account)
