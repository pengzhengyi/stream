"""Accounts: the people in a household, their roles, and the rules for their names."""

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, NewType

from medleyplay.domain.errors import InvalidInputError

AccountId = NewType("AccountId", int)
Username = NewType("Username", str)

MIN_PASSWORD_LENGTH: Final = 8
MAX_PASSWORD_LENGTH: Final = 256
MAX_DISPLAY_NAME_LENGTH: Final = 64

_USERNAME = re.compile(r"[a-z0-9][a-z0-9._-]{0,31}")


class Role(StrEnum):
    """What an Account may do: an admin also manages Accounts."""

    ADMIN = "admin"
    MEMBER = "member"


@dataclass(frozen=True)
class Account:
    """A person in the household."""

    id: AccountId
    username: Username
    display_name: str
    role: Role

    @property
    def is_admin(self) -> bool:
        """Return whether this Account manages the household."""
        return self.role is Role.ADMIN


def parse_username(raw: str) -> Username:
    """Return the canonical form of a username, which is lowercase.

    A username is 1-32 letters, digits, `.`, `_`, or `-`, starting with a letter or
    digit. `Alice` and `alice` are the same username.
    """
    candidate = raw.strip().lower()
    if not _USERNAME.fullmatch(candidate):
        message = (
            f"Username {raw!r} must be 1-32 letters, digits, '.', '_', or '-', "
            "starting with a letter or digit."
        )
        raise InvalidInputError(message)
    return Username(candidate)


def parse_display_name(raw: str) -> str:
    """Return a display name without surrounding spaces."""
    candidate = raw.strip()
    if not 1 <= len(candidate) <= MAX_DISPLAY_NAME_LENGTH:
        message = f"A display name must be 1-{MAX_DISPLAY_NAME_LENGTH} characters."
        raise InvalidInputError(message)
    return candidate


def check_password(password: str) -> None:
    """Refuse a password that is too short or too long to hash sensibly."""
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        message = f"A password must be {MIN_PASSWORD_LENGTH}-{MAX_PASSWORD_LENGTH} characters."
        raise InvalidInputError(message)
