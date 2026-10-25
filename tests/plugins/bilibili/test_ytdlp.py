"""yt-dlp's failures are sorted by type, and it never runs on a URL it wasn't meant for."""

import io

import pytest
from yt_dlp.networking import Response  # type: ignore[import-untyped]
from yt_dlp.networking.exceptions import HTTPError, TransportError  # type: ignore[import-untyped]
from yt_dlp.utils import ExtractorError  # type: ignore[import-untyped]

from medleyplay.plugin_api import AuthError, NetworkError
from medleyplay.plugins.bilibili._ytdlp import (
    GoneError,
    NeedsLoginError,
    extract,
    sort_failure,
)


def _http(status: int) -> ExtractorError:
    """An extractor error caused by the site answering `status`."""
    response = Response(io.BytesIO(), "https://www.bilibili.com/video/BV1Xx41117Tz", {}, status)
    return ExtractorError("Unable to download webpage", cause=HTTPError(response))


@pytest.mark.parametrize("status", [429, 500, 503])
def test_a_busy_or_failing_site_is_a_network_failure(status: int) -> None:
    assert isinstance(sort_failure(_http(status), signed_in=False), NetworkError)


def test_a_connection_that_fails_is_a_network_failure() -> None:
    error = ExtractorError("Unable to download webpage", cause=TransportError("timed out"))

    assert isinstance(sort_failure(error, signed_in=False), NetworkError)


def test_a_missing_page_is_gone() -> None:
    assert isinstance(sort_failure(_http(404), signed_in=False), GoneError)


@pytest.mark.parametrize("status", [403, 412])
def test_a_refusal_of_the_client_is_a_fault_not_a_wait(status: int) -> None:
    failure = sort_failure(_http(status), signed_in=True)

    assert type(failure) is RuntimeError
    assert str(status) in str(failure)


@pytest.mark.parametrize(
    "message",
    [
        "This video is only available for registered users",
        "This video is for premium members only",
        "This is a supporter-only video: x",
    ],
)
def test_an_expected_login_refusal_needs_a_login_or_fails_the_one_sent(message: str) -> None:
    error = ExtractorError(message, expected=True)

    assert isinstance(sort_failure(error, signed_in=False), NeedsLoginError)
    assert isinstance(sort_failure(error, signed_in=True), AuthError)


def test_an_expected_rate_limit_is_a_fault() -> None:
    error = ExtractorError("You have exceeded the rate limit. Try again later", expected=True)

    assert type(sort_failure(error, signed_in=True)) is RuntimeError


def test_an_expected_removal_is_gone() -> None:
    error = ExtractorError("This video may be deleted or geo-restricted.", expected=True)

    assert isinstance(sort_failure(error, signed_in=False), GoneError)


def test_an_extractor_that_no_longer_understands_the_page_is_a_fault() -> None:
    failure = sort_failure(ExtractorError("Unable to extract initial state"), signed_in=False)

    assert type(failure) is RuntimeError
    assert "initial state" in str(failure)


def test_yt_dlp_refuses_a_url_bilibilis_extractor_doesnt_handle_without_fetching_it() -> None:
    # example.invalid can't resolve, so a fetch would fail as a network failure.
    with pytest.raises(RuntimeError, match="No suitable extractor"):
        extract("https://example.invalid/video/1", playlist=False)
