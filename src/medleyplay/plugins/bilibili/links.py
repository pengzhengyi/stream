"""Bilibili's links: which video and part a link names, and its `av` and `BV` ids.

```text
https://www.bilibili.com/video/BV1Xx41117Tz?p=2   BV1Xx41117Tz, part 2
https://www.bilibili.com/video/av8508035          BV1Xx41117Tz, no part named
https://b23.tv/abc123                             a short link, to be followed
```
"""

import re
from dataclasses import dataclass
from typing import Final
from urllib.parse import parse_qs, urlsplit

# The site's published conversion between a video's number and its `BV` id.
_ALPHABET: Final = "FcwAPNKTMug3GV5Lj7EJnHpWsx4tb8haYeviqBz6rkCy12mUSDQX9RdoZf"
_XOR: Final = 23442827791579
_MASK: Final = (1 << 51) - 1
_MAX_AID: Final = 1 << 51
_PREFIX: Final = "BV1"
_DIGIT_POSITIONS: Final = (11, 10, 3, 8, 4, 6, 5, 7, 9)
"""Where each base-58 digit goes, least significant first."""

_VIDEO_PATH: Final = re.compile(r"/video/(?:(?P<bv>[bB][vV]1\w{9})|[aA][vV](?P<av>\d{1,16}))/?")
SHORT_LINK_HOST: Final = "b23.tv"


@dataclass(frozen=True)
class VideoLink:
    """A video's `BV` id, and the part the link names, if it names one."""

    video: str
    part: int | None


def av_to_bv(aid: int) -> str:
    """Return the `BV` id of the video numbered `aid`."""
    if not 0 < aid < _MAX_AID:
        message = f"{aid} isn't a video number."
        raise ValueError(message)
    digits = list(_PREFIX + " " * len(_DIGIT_POSITIONS))
    value = (_MAX_AID | aid) ^ _XOR
    for position in _DIGIT_POSITIONS:
        value, digit = divmod(value, len(_ALPHABET))
        digits[position] = _ALPHABET[digit]
    return "".join(digits)


def bv_to_av(bvid: str) -> int:
    """Return the number of the video whose `BV` id is `bvid`."""
    if not _is_bv(bvid):
        message = f"{bvid!r} isn't a BV id."
        raise ValueError(message)
    value = 0
    for position in reversed(_DIGIT_POSITIONS):
        value = value * len(_ALPHABET) + _ALPHABET.index(bvid[position])
    return (value & _MASK) ^ _XOR


def parse_video_link(link: str) -> VideoLink | None:
    """Return the video and part a full video link names, or `None` for any other link."""
    parts = urlsplit(link)
    found = _VIDEO_PATH.fullmatch(parts.path)
    if found is None:
        return None
    part = _part(parse_qs(parts.query).get("p"))
    if part == 0:
        return None
    if found["av"] is not None:
        aid = int(found["av"])
        return VideoLink(av_to_bv(aid), part) if 0 < aid < _MAX_AID else None
    bvid = _PREFIX + found["bv"][len(_PREFIX) :]
    return VideoLink(bvid, part) if _is_bv(bvid) else None


def is_short_link(link: str) -> bool:
    """Return whether `link` is a short link, which must be followed to find its video."""
    return urlsplit(link).netloc.lower().removesuffix(".") == SHORT_LINK_HOST


def _part(values: list[str] | None) -> int | None:
    # 0 stands for a part that is named but isn't one, such as `?p=two`.
    if not values:
        return None
    return int(values[0]) if values[0].isdecimal() and len(values[0]) <= 4 else 0  # noqa: PLR2004 -- four digits


def _is_bv(bvid: str) -> bool:
    return (
        len(bvid) == len(_PREFIX) + len(_DIGIT_POSITIONS)
        and bvid.startswith(_PREFIX)
        and all(char in _ALPHABET for char in bvid[len(_PREFIX) :])
    )
