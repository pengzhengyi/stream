"""Following a `b23.tv` short link to the video link it stands for.

The pasted text is never fetched: the first request is rebuilt from the link's
code, and each redirect is checked before it is followed, so a short link can
only ever lead the plugin to Bilibili's own hosts:

```text
https://b23.tv/abc123  ->  https://www.bilibili.com/video/BV1Xx41117Tz?p=2
```
"""

import re
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Final
from urllib.parse import urljoin, urlsplit

from medleyplay.plugin_api import NetworkError
from medleyplay.plugins.bilibili.links import SHORT_LINK_HOST

type Fetch = Callable[[str], str | None]
"""Fetch a URL and return where it redirects to, or `None` when it doesn't."""

HOSTS: Final = frozenset({"bilibili.com", "www.bilibili.com", "m.bilibili.com", SHORT_LINK_HOST})
MAX_HOPS: Final = 3
TIMEOUT_SECONDS: Final = 1
"""Each hop's wait, so every hop together stays well inside the call's deadline."""
USER_AGENT: Final = "medleyplay"
_CODE: Final = re.compile(r"/(?P<code>[A-Za-z0-9]{1,32})/?")
_REDIRECTS: Final = frozenset({301, 302, 303, 307, 308})


def follow_short_link(link: str, fetch: Fetch | None = None) -> str:
    """Return the link a short link leads to, or the first one off Bilibili's hosts.

    The link returned is never fetched unless it is on Bilibili's hosts, so the
    core can refuse it. A short link with no code, or one that leads nowhere, is
    returned as it is, naming no video.
    """
    fetch = fetch or fetch_redirect
    found = _CODE.fullmatch(urlsplit(link).path)
    if found is None:
        return link
    current = f"https://{SHORT_LINK_HOST}/{found['code']}"
    for _ in range(MAX_HOPS):
        target = fetch(current)
        if target is None:
            return current
        current = urljoin(current, target)
        if not is_allowed(current) or _host(current) != SHORT_LINK_HOST:
            return current
    return current


def is_allowed(link: str) -> bool:
    """Return whether `link` may be fetched: `https` or `http`, a Bilibili host, nothing else."""
    parts = urlsplit(link)
    return (
        parts.scheme in {"https", "http"}
        and "@" not in parts.netloc
        and ":" not in parts.netloc
        and _host(link) in HOSTS
    )


def fetch_redirect(url: str) -> str | None:
    """Ask for `url` without following redirects, proxies, or cookies; return its redirect."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirects())
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310 -- callers check the URL
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS):
            return None
    except urllib.error.HTTPError as error:
        with error:
            if error.code in _REDIRECTS:
                return error.headers.get("Location")
        message = f"{SHORT_LINK_HOST} answered {error.code}."
        raise NetworkError(message) from None
    except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
        message = f"{SHORT_LINK_HOST} couldn't be reached: {error}"
        raise NetworkError(message) from None


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_: object, **__: object) -> None:
        return None


def _host(link: str) -> str:
    return urlsplit(link).netloc.lower().removesuffix(".")
