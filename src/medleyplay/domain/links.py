"""Links a household pastes to add music, and which Source kind each one belongs to.

The core recognizes a link by its host before any plugin sees it, so a plugin is
only ever handed a link to its own site:

```text
https://www.bilibili.com/video/BV1Xx41117Tz?p=2   bilibili
https://b23.tv/abc123                             bilibili
https://evil.example/video/BV1Xx41117Tz           refused
```

A bare video code stands for its link:

```text
BV1Xx41117Tz   https://www.bilibili.com/video/BV1Xx41117Tz
av170001       https://www.bilibili.com/video/av170001
```
"""

import re
from typing import Final
from urllib.parse import urlsplit

from medleyplay.domain.errors import InvalidInputError

BILIBILI_SOURCE: Final = "bilibili"
"""The Source kind of one part of a Bilibili video; its locator is `<BV id>/p<part>`."""

MAX_LINK_LENGTH: Final = 2048
LINK_HOSTS: Final = {
    "bilibili.com": BILIBILI_SOURCE,
    "www.bilibili.com": BILIBILI_SOURCE,
    "m.bilibili.com": BILIBILI_SOURCE,
    "b23.tv": BILIBILI_SOURCE,
}
"""Each host a link may name, and the Source kind it belongs to; any other is refused."""

CODE_LINK: Final = "https://www.bilibili.com/video/{code}"
_BV_CODE: Final = re.compile(r"bv([0-9A-Za-z]{10})", re.IGNORECASE)
_AV_CODE: Final = re.compile(r"av([0-9]{1,19})", re.IGNORECASE)

VIDEO_ID: Final = re.compile(r"[A-Za-z0-9_-]{1,64}")
"""What a video id looks like to the core: letters, digits, `_`, and `-`, never a path."""


def link_of(text: str) -> str:
    """Return the link a bare `BV` or `av` code stands for, or `text` as it is.

    Only a whole code becomes a link, its prefix in the site's own case; anything
    else is left for `recognize_link` to check as a link.
    """
    code = text.strip()
    if found := _BV_CODE.fullmatch(code):
        return CODE_LINK.format(code=f"BV{found[1]}")
    if found := _AV_CODE.fullmatch(code):
        return CODE_LINK.format(code=f"av{found[1]}")
    return text


def recognize_link(link: str) -> str:
    """Return the Source kind of `link`, or raise `InvalidInputError` for any other link.

    A link must be `http` or `https`, name no user, password, or port, and name a
    host in `LINK_HOSTS`.
    """
    link = link.strip()
    if len(link) > MAX_LINK_LENGTH:
        message = f"A link is at most {MAX_LINK_LENGTH} characters long."
        raise InvalidInputError(message)
    parts = urlsplit(link)
    if parts.scheme.lower() not in {"http", "https"} or "@" in parts.netloc:
        raise _refused(link)
    if ":" in parts.netloc:
        raise _refused(link)
    kind = LINK_HOSTS.get(parts.netloc.lower().removesuffix("."))
    if kind is None:
        raise _refused(link)
    return kind


def part_locator(video: str, part: int) -> str:
    """Return the locator of one part of a video, such as `BV1Xx41117Tz/p2`."""
    if not VIDEO_ID.fullmatch(video) or part < 1:
        message = f"{video!r} part {part} isn't a part of a video."
        raise InvalidInputError(message)
    return f"{video}/p{part}"


def parse_part_locator(locator: str) -> tuple[str, int]:
    """Return the video and part a locator such as `BV1Xx41117Tz/p2` names."""
    video, _, part = locator.rpartition("/p")
    if not part.isdecimal() or part_locator(video, int(part)) != locator:
        message = f"{locator!r} isn't the locator of a part of a video."
        raise InvalidInputError(message)
    return video, int(part)


def _refused(link: str) -> InvalidInputError:
    return InvalidInputError(f"medleyplay can't add music from {link[:100]!r}.")
