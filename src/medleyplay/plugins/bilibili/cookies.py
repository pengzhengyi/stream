"""The Bilibili login: the few cookies the plugin needs, kept from a pasted cookies file.

A browser extension exports cookies in Netscape's format, one per line:

```text
.bilibili.com	TRUE	/	TRUE	1807142400	SESSDATA	abc%2C123
```

`SESSDATA` is the session and `buvid3` the device id. `bili_jct`, which authorizes
changes to the site account, is dropped, so a leaked copy can't change it.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

SESSION_COOKIE: Final = "SESSDATA"
KEPT_COOKIES: Final = frozenset({SESSION_COOKIE, "buvid3"})
DOMAINS: Final = frozenset({".bilibili.com", "bilibili.com", "www.bilibili.com"})
HEADER: Final = "# Netscape HTTP Cookie File"
_HTTP_ONLY: Final = "#HttpOnly_"
_FIELDS: Final = 7


class NoSessionError(ValueError):
    """The file holds no Bilibili session cookie."""


@dataclass(frozen=True)
class Login:
    """The kept cookies, as a cookies file, and when the session expires, if it says."""

    cookies: str
    expires_at: datetime | None


def keep_login(text: str) -> Login:
    """Return the Bilibili login in a cookies file; raise `NoSessionError` without a session."""
    kept: list[str] = []
    expires_at: datetime | None = None
    has_session = False
    for line in text.splitlines():
        fields = line.removeprefix(_HTTP_ONLY).split("\t")
        if len(fields) != _FIELDS or (line.startswith("#") and not line.startswith(_HTTP_ONLY)):
            continue
        domain, _, _, _, expiry, name, _ = fields
        if domain.lower() not in DOMAINS or name not in KEPT_COOKIES or not _is_number(expiry):
            continue
        kept.append(line)
        if name == SESSION_COOKIE:
            has_session = True
            expires_at = _expiry(int(expiry))
    if not has_session:
        message = "The file holds no Bilibili session; export the cookies while signed in."
        raise NoSessionError(message)
    return Login("\n".join([HEADER, *kept]) + "\n", expires_at)


def _is_number(text: str) -> bool:
    return text.isascii() and text.isdigit()


def _expiry(seconds: int) -> datetime | None:
    """Return when a cookie expires; `0`, or a time too far off to be real, says nothing."""
    if not seconds:
        return None
    try:
        return datetime.fromtimestamp(seconds, UTC)
    except (ValueError, OverflowError, OSError):
        return None
