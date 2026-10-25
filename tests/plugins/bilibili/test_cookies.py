"""A pasted cookies file keeps only the Bilibili cookies the plugin needs."""

from datetime import UTC, datetime

import pytest

from medleyplay.plugins.bilibili.cookies import NoSessionError, keep_login


def _exported(*lines: str) -> str:
    """A cookies file as a browser extension exports it, in Netscape's format."""
    header = "# Netscape HTTP Cookie File\n# https://curl.se/docs/http-cookies.html\n\n"
    return header + "\n".join(lines) + "\n"


SESSION = ".bilibili.com\tTRUE\t/\tTRUE\t1807142400\tSESSDATA\tabc%2C123"
DEVICE = ".bilibili.com\tTRUE\t/\tFALSE\t1838678400\tbuvid3\tdevice-1"
TOKEN = ".bilibili.com\tTRUE\t/\tFALSE\t1807142400\tbili_jct\tsecret-token"
ELSEWHERE = ".example.com\tTRUE\t/\tFALSE\t1807142400\tSESSDATA\tnot-ours"


def test_only_the_session_and_device_cookies_are_kept() -> None:
    login = keep_login(_exported(SESSION, DEVICE, TOKEN, ELSEWHERE))

    assert login.cookies.splitlines()[1:] == [SESSION, DEVICE]
    assert login.cookies.startswith("# Netscape HTTP Cookie File")


def test_the_login_expires_when_its_session_cookie_does() -> None:
    login = keep_login(_exported(DEVICE, SESSION))

    assert login.expires_at == datetime(2027, 4, 8, tzinfo=UTC)


def test_an_http_only_cookie_is_read_too() -> None:
    login = keep_login(_exported(f"#HttpOnly_{SESSION}"))

    assert login.cookies.splitlines()[1:] == [f"#HttpOnly_{SESSION}"]


def test_a_session_cookie_with_no_expiry_lasts_as_long_as_the_site_allows() -> None:
    login = keep_login(_exported(SESSION.replace("1807142400", "0")))

    assert login.expires_at is None


@pytest.mark.parametrize("expiry", ["1807142400000", "1" + "0" * 30])
def test_an_expiry_out_of_range_is_read_as_none(expiry: str) -> None:
    # Some exporters write milliseconds; no date that far off is a real expiry.
    login = keep_login(_exported(SESSION.replace("1807142400", expiry)))

    assert login.expires_at is None


@pytest.mark.parametrize(
    "text",
    [
        _exported(".bilibili.com\tTRUE\t/\tTRUE\t\u0661\u0662\tSESSDATA\tabc"),
        _exported(DEVICE, TOKEN),
        _exported(ELSEWHERE),
        "SESSDATA=abc123",
        "",
        _exported(".bilibili.com\tTRUE\t/\tTRUE\tsoon\tSESSDATA\tabc"),
    ],
)
def test_a_file_without_a_bilibili_session_is_refused(text: str) -> None:
    with pytest.raises(NoSessionError):
        keep_login(text)


def test_the_refusal_never_repeats_a_cookie() -> None:
    with pytest.raises(NoSessionError) as refused:
        keep_login(_exported(TOKEN))

    assert "secret-token" not in str(refused.value)
