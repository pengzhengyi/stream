"""The linked accounts API: saving, listing, and removing the caller's logins on sites."""

from datetime import datetime

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from medleyplay.domain.linked_accounts import LinkedAccount, LinkState
from medleyplay.plugin_api.sources import MAX_LOGIN_TEXT
from medleyplay.web.deps import LinkedDep, SignedInAccount

router = APIRouter(prefix="/api/me/linked-accounts", tags=["linked accounts"])


class LoginIn(BaseModel):
    """A login to save: the text of a cookies file exported from a signed-in browser."""

    cookies: str = Field(max_length=MAX_LOGIN_TEXT, examples=["# Netscape HTTP Cookie File\n…"])


class LinkedAccountOut(BaseModel):
    """A linked account as the API shows it; the login itself never leaves the server."""

    site: str
    state: LinkState
    expires_at: datetime | None
    saved_at: datetime

    @classmethod
    def of(cls, linked: LinkedAccount) -> "LinkedAccountOut":
        """Return the API view of `linked`."""
        return cls(
            site=linked.site,
            state=linked.state,
            expires_at=linked.expires_at,
            saved_at=linked.saved_at,
        )


@router.get("")
def list_linked_accounts(me: SignedInAccount, linked: LinkedDep) -> list[LinkedAccountOut]:
    """Return the caller's linked accounts."""
    return [LinkedAccountOut.of(each) for each in linked.list_linked(me)]


@router.put("/{site}")
def save_linked_account(
    site: str, body: LoginIn, me: SignedInAccount, linked: LinkedDep
) -> LinkedAccountOut:
    """Save the caller's login on a site from a cookies file; text with no login answers 422."""
    return LinkedAccountOut.of(linked.save(me, site, body.cookies))


@router.delete("/{site}", status_code=status.HTTP_204_NO_CONTENT)
def remove_linked_account(site: str, me: SignedInAccount, linked: LinkedDep) -> None:
    """Forget the caller's login on a site; 204 also when there is none."""
    linked.remove(me, site)
