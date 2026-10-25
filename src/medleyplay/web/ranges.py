"""Reading a `Range` header against a slice of bytes, as RFC 9110 section 14 defines it.

Only one range is ever served: with several, the first satisfiable one. A header
that doesn't parse is ignored, so the whole slice is served.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Final, Literal

_SPEC: Final = re.compile(r"(?:(?P<first>[0-9]+)-(?P<last>[0-9]*)|-(?P<suffix>[0-9]+))", re.ASCII)


@dataclass(frozen=True)
class ByteRange:
    """The bytes from `start` up to, but not including, `stop`."""

    start: int
    stop: int


class _Unsatisfiable(Enum):
    UNSATISFIABLE = "unsatisfiable"


UNSATISFIABLE: Final = _Unsatisfiable.UNSATISFIABLE
"""No requested range overlaps the slice: the answer is 416."""


def requested_range(
    header: str | None, length: int
) -> ByteRange | Literal[_Unsatisfiable.UNSATISFIABLE] | None:
    """Return the range of a `length`-byte slice that `header` asks for.

    `None` means the whole slice, for a missing header or one that doesn't parse.
    """
    if header is None:
        return None
    unit, equals, range_set = header.partition("=")
    if not equals or unit.lower() != "bytes":
        return None
    ranges: list[ByteRange | None] = []
    for spec in range_set.split(","):
        match = _SPEC.fullmatch(spec.strip())
        if match is None or _reversed(match):
            return None
        ranges.append(_range_of(match, length))
    return next((found for found in ranges if found is not None), UNSATISFIABLE)


def _reversed(match: re.Match[str]) -> bool:
    return bool(match["last"]) and int(match["last"]) < int(match["first"])


def _range_of(match: re.Match[str], length: int) -> ByteRange | None:
    # None: the spec is well formed, but none of its bytes are in the slice.
    if match["suffix"] is not None:
        suffix = int(match["suffix"])
        return ByteRange(max(length - suffix, 0), length) if suffix and length else None
    first = int(match["first"])
    if first >= length:
        return None
    stop = int(match["last"]) + 1 if match["last"] else length
    return ByteRange(first, min(stop, length))
