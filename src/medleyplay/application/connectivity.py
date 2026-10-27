"""Whether the internet can be reached: a request must answer exactly what its endpoint promises.

Neither default endpoint is a music site. A redirect, or any other answer, is a
captive portal, which counts as unreachable.
"""

# cspell:ignore miui

import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final
from urllib.error import HTTPError, URLError

TIMEOUT: Final = 5.0
"""Seconds an endpoint may take to answer."""
MAX_BODY: Final = 4096
APPLE_SUCCESS: Final = "<HTML><HEAD><TITLE>Success</TITLE></HEAD><BODY>Success</BODY></HTML>"


@dataclass(frozen=True)
class Check:
    """An endpoint, and what it answers: a status, and a body unless `body` is `None`."""

    url: str
    status: int
    body: str | None = None


DEFAULT_CHECKS: Final = (
    Check("http://captive.apple.com/hotspot-detect.html", 200, APPLE_SUCCESS),
    Check("http://connect.rom.miui.com/generate_204", 204),
)


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_: object) -> None:
        return None


_OPENER: Final = urllib.request.build_opener(_NoRedirects)


def reachable(checks: Sequence[Check], timeout: float = TIMEOUT) -> bool:
    """Return whether an endpoint of `checks` answers as promised, trying each in turn."""
    return any(_answers(check, timeout) for check in checks)


def _answers(check: Check, timeout: float) -> bool:
    request = urllib.request.Request(check.url, headers={"User-Agent": "medleyplay"})  # noqa: S310 -- the config file allows only http and https
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            status, body = response.status, response.read(MAX_BODY)
    except HTTPError as error:
        # A redirect is one, as any status of 400 or more is; each holds its response open.
        error.close()
        return False
    except (URLError, OSError, ValueError):
        return False
    if status != check.status:
        return False
    return check.body is None or body.decode("utf-8", "replace").strip() == check.body
