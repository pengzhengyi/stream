"""A linked account's state over time, the Keychain name of its login, and redacting it."""

from datetime import UTC, datetime

import pytest

from medleyplay.domain.accounts import AccountId
from medleyplay.domain.errors import InvalidInputError
from medleyplay.domain.linked_accounts import (
    LinkedAccount,
    LinkState,
    check_site,
    redact,
    secret_name,
)

NOW = datetime(2026, 10, 25, 12, tzinfo=UTC)
LOGIN = (
    "# Netscape HTTP Cookie File\n"
    ".bilibili.com\tTRUE\t/\tTRUE\t1807142400\tSESSDATA\tabc%2C123xyz\n"
    "#HttpOnly_.bilibili.com\tTRUE\t/\tFALSE\t1807142400\tbuvid3\tdevice-0001\n"
)


def _linked(expires_at: datetime | None, state: LinkState = LinkState.VALID) -> LinkedAccount:
    return LinkedAccount("bilibili", state, expires_at, saved_at=NOW, revision=1)


def test_a_valid_login_stays_valid_until_it_expires() -> None:
    assert _linked(datetime(2026, 10, 26, tzinfo=UTC)).state_at(NOW) is LinkState.VALID
    assert _linked(None).state_at(NOW) is LinkState.VALID


def test_an_expired_login_needs_sign_in() -> None:
    assert _linked(datetime(2026, 10, 25, tzinfo=UTC)).state_at(NOW) is LinkState.NEEDS_SIGN_IN


def test_a_refused_login_needs_sign_in_whatever_its_expiry() -> None:
    linked = _linked(None, LinkState.NEEDS_SIGN_IN)

    assert linked.state_at(NOW) is LinkState.NEEDS_SIGN_IN


def test_a_login_is_kept_in_the_keychain_under_its_account_and_site() -> None:
    assert secret_name(AccountId(3), "bilibili") == "3:bilibili"


@pytest.mark.parametrize("site", ["", "Bilibili", "../x", "a" * 65])
def test_a_site_is_a_plain_key(site: str) -> None:
    with pytest.raises(InvalidInputError):
        check_site(site)


def test_every_cookie_value_is_redacted_as_written_and_url_decoded() -> None:
    message = "failed with abc%2C123xyz, abc,123xyz, and device-0001 at .bilibili.com"

    assert redact(message, LOGIN) == (
        "failed with <redacted>, <redacted>, and <redacted> at .bilibili.com"
    )


def test_redacting_without_a_login_changes_nothing() -> None:
    assert redact("failed", None) == "failed"
