"""Libraries: storage roots of your own music that medleyplay reads but never writes."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final, NewType

from medleyplay.domain.errors import InvalidInputError

LibraryId = NewType("LibraryId", int)

LIBRARY_SOURCE: Final = "library"
"""The Source kind of a file in a Library; its locator is `<library id>/<path>`."""
MAX_NAME_LENGTH: Final = 128


class LibraryKind(StrEnum):
    """How a Library stores its files."""

    FOLDER = "folder"
    ZIP = "zip"


class LibraryState(StrEnum):
    """Whether the last scan could read the Library."""

    ONLINE = "online"
    OFFLINE = "offline"
    """Unreadable, or empty after holding files, such as an unplugged drive."""


@dataclass(frozen=True)
class Library:
    """A registered Library and what its last scan found.

    `last_scanned_at` is `None` until the first scan completes.
    """

    id: LibraryId
    name: str
    kind: LibraryKind
    path: str
    state: LibraryState
    message: str
    file_count: int
    added_at: datetime
    last_scanned_at: datetime | None


def parse_library_name(name: str) -> str:
    """Return `name` trimmed, or raise `InvalidInputError` when empty or too long."""
    trimmed = name.strip()
    if not trimmed or len(trimmed) > MAX_NAME_LENGTH:
        message = f"A Library's name has 1 to {MAX_NAME_LENGTH} characters."
        raise InvalidInputError(message)
    return trimmed


def library_locator(library_id: LibraryId, path: str) -> str:
    """Return the locator of the Source for `path` in the Library."""
    return f"{library_id}/{path}"


def path_of_locator(locator: str) -> str:
    """Return the path in its Library of the Source with `locator`."""
    return locator.partition("/")[2]


def scan_target(library_id: LibraryId) -> str:
    """Return the Job target of the Library's scans."""
    return f"library:{library_id}"


def library_of_locator(locator: str) -> LibraryId:
    """Return the id of the Library holding the Source with `locator`."""
    return LibraryId(int(locator.partition("/")[0]))
