"""Linked accounts: an Account's login on a site, such as its Bilibili cookies.

The login itself lives in the Keychain; the catalog keeps only its state, when it
expires, and a revision that rises each time it is saved. A login is a cookies
file in Netscape's format, one cookie per line:

```text
.bilibili.com	TRUE	/	TRUE	1807142400	SESSDATA	abc%2C123
```
"""

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final
from urllib.parse import unquote

from medleyplay.domain.accounts import AccountId
from medleyplay.domain.errors import InvalidInputError

KEYCHAIN_SERVICE: Final = "medleyplay"
"""The Keychain service every login is kept under."""
REDACTED: Final = "<redacted>"
_SITE: Final = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
_COOKIE_FIELDS: Final = 7
_SHORTEST_SECRET: Final = 4


class LinkState(StrEnum):
    """Whether a login can be used."""

    VALID = "valid"
    NEEDS_SIGN_IN = "needs_sign_in"
    """The site refused it, it expired, or the Keychain no longer holds it."""


@dataclass(frozen=True)
class LinkedAccount:
    """An Account's login on one site, as the catalog knows it."""

    site: str
    state: LinkState
    expires_at: datetime | None
    saved_at: datetime
    revision: int

    def state_at(self, now: datetime) -> LinkState:
        """Return the login's state at `now`: one past its expiry needs sign-in."""
        if self.expires_at is not None and self.expires_at <= now:
            return LinkState.NEEDS_SIGN_IN
        return self.state


def check_site(site: str) -> str:
    """Return `site`, or raise `InvalidInputError` when it isn't a plain key like `bilibili`."""
    if not _SITE.fullmatch(site):
        message = f"{site[:64]!r} isn't a site."
        raise InvalidInputError(message)
    return site


def secret_name(account_id: AccountId, site: str) -> str:
    """Return the name an Account's login on `site` is kept under in the Keychain."""
    return f"{account_id}:{check_site(site)}"


def redact(text: str, login: str | None) -> str:
    """Return `text` with every cookie value of `login` replaced, as written and URL-decoded."""
    if not login:
        return text
    secrets = set()
    for line in login.splitlines():
        fields = line.split("\t")
        if len(fields) == _COOKIE_FIELDS and len(fields[-1]) >= _SHORTEST_SECRET:
            secrets |= {fields[-1], unquote(fields[-1])}
    for secret in sorted(secrets, key=len, reverse=True):
        text = text.replace(secret, REDACTED)
    return text
