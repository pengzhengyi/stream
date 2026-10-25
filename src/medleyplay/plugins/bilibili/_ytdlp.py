"""Every call to yt-dlp, which has no type hints, returning plain values and sorted failures.

yt-dlp only ever sees a URL this plugin built, and only its Bilibili extractor
may run, so its generic extractor never fetches anything else. It reads no proxy
from the environment, keeps no cache, and writes nothing but the download.

Unverified until yt-dlp can read Bilibili again: the options and the errors
follow yt-dlp's documentation and source, not a run against the site.
"""

import re
from collections.abc import Callable, Mapping
from typing import Any, Final

import yt_dlp  # type: ignore[import-untyped] # yt-dlp ships no type hints
from yt_dlp.networking.exceptions import (  # type: ignore[import-untyped]
    HTTPError,
    TransportError,
)
from yt_dlp.utils import DownloadError, ExtractorError  # type: ignore[import-untyped]

from medleyplay.plugin_api import AuthError, NetworkError

type Info = Mapping[str, object]
type OnProgress = Callable[[int, int | None], None]
"""Bytes downloaded so far, and the total when known."""

SOCKET_TIMEOUT_SECONDS: Final = 4
"""Below the plugin API's deadlines, so a stalled read fails as a network failure first."""
OUTPUT_NAME: Final = "audio.%(ext)s"

_LOGIN: Final = re.compile(
    r"registered users|log ?in|premium members|supporter-only|purchase", re.IGNORECASE
)
_REFUSED: Final = re.compile(r"rate limit|blocked by server|rejected by server", re.IGNORECASE)
_RETRY_LATER: Final = frozenset({429, 500, 502, 503, 504})
_GONE: Final = frozenset({404, 410})


class GoneError(Exception):
    """The site says the video isn't there for anyone: removed or region-locked."""


class NeedsLoginError(Exception):
    """The site shows the video only to a signed-in account, and none was sent."""


def extract(url: str, *, playlist: bool, cookie_file: str | None = None) -> Info:
    """Read the info yt-dlp extracts from `url`, without downloading.

    With `playlist`, a video with several parts comes back as a playlist whose
    entries are only the parts' URLs.
    """
    options = {
        **_base(cookie_file),
        "skip_download": True,
        "noplaylist": not playlist,
        "extract_flat": "in_playlist",
    }
    return _run(options, lambda ydl: ydl.extract_info(url, download=False), cookie_file)


def download(
    url: str, *, formats: str, folder: str, cookie_file: str | None, on_progress: OnProgress
) -> Info:
    """Download the first of `formats` the site offers into `folder`, as `audio.<ext>`."""

    def hook(status: Mapping[str, Any]) -> None:
        if status.get("status") == "downloading":
            total = status.get("total_bytes") or status.get("total_bytes_estimate")
            on_progress(int(status.get("downloaded_bytes") or 0), int(total) if total else None)

    options = {
        **_base(cookie_file),
        "noplaylist": True,
        "format": formats,
        "paths": {"home": folder, "temp": folder},
        "outtmpl": {"default": OUTPUT_NAME},
        "overwrites": True,
        "progress_hooks": [hook],
        "postprocessors": [],
    }
    return _run(options, lambda ydl: ydl.extract_info(url, download=True), cookie_file)


def _base(cookie_file: str | None) -> dict[str, object]:
    return {
        "allowed_extractors": ["bilibili"],
        "socket_timeout": SOCKET_TIMEOUT_SECONDS,
        "proxy": "",
        "cachedir": False,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "color": "never",
        "logger": _Quiet(),
        "retries": 1,
        "cookiefile": cookie_file,
    }


def _run(options: dict[str, object], call: Callable[[Any], Any], cookie_file: str | None) -> Info:
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = call(ydl)
    except DownloadError as error:
        cause = (error.exc_info[1] if error.exc_info else None) or error
        raise sort_failure(cause, signed_in=cookie_file is not None) from None
    if not isinstance(info, Mapping):  # pragma: no cover -- yt-dlp returns a dict or raises
        message = f"yt-dlp returned {type(info).__name__}, not its info."
        raise TypeError(message)
    return info


def sort_failure(error: BaseException, *, signed_in: bool) -> Exception:
    """Return the failure the plugin raises for one of yt-dlp's errors.

    By type first: a connection failure or a timeout, a 429, or a 5xx is a
    `NetworkError`; a 404 is gone; a 403 or a 412 is Bilibili refusing the client,
    a fault, so it isn't retried every minute. An error yt-dlp marks *expected*
    is a refused login, a rate limit, or gone, by yt-dlp's own fixed messages.
    Anything else, such as an extractor that no longer understands the page, is
    a fault.
    """
    cause = getattr(error, "cause", None) or error
    if isinstance(cause, HTTPError):
        return _sort_status(cause.status)
    if isinstance(cause, TransportError):
        return NetworkError(f"Bilibili couldn't be reached: {cause}")
    if isinstance(error, ExtractorError) and error.expected:
        return _sort_expected(str(getattr(error, "orig_msg", None) or error), signed_in=signed_in)
    return RuntimeError(f"yt-dlp failed: {error}")


def _sort_status(status: int) -> Exception:
    if status in _RETRY_LATER:
        return NetworkError(f"Bilibili answered {status}; trying again later.")
    if status in _GONE:
        return GoneError("Bilibili has no such video.")
    return RuntimeError(f"Bilibili refused the request ({status}).")


def _sort_expected(text: str, *, signed_in: bool) -> Exception:
    if _REFUSED.search(text):
        return RuntimeError(f"Bilibili refused the request: {text}")
    if _LOGIN.search(text):
        return AuthError(text) if signed_in else NeedsLoginError(text)
    return GoneError(text)


class _Quiet:
    """A logger that keeps yt-dlp silent; its failures arrive as exceptions instead."""

    def debug(self, _: str) -> None: ...
    def info(self, _: str) -> None: ...
    def warning(self, _: str) -> None: ...
    def error(self, _: str) -> None: ...
