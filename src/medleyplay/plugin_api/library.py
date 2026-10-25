"""The library backend: reading a Library's files, from a folder or a zip archive.

A root is a storage kind and a path; a file in it is a path relative to the root,
with `/` between folders:

```text
root   LibraryRoot(kind="zip", path="/Users/alice/Music/Old.zip")
file   "Blue/01 Intro.mp3"
```

No operation writes to a Library.
"""

from datetime import timedelta
from typing import Annotated, Protocol

from pydantic import AfterValidator, BaseModel, ConfigDict

from medleyplay.plugin_api.extension import ExtensionPoint


def check_library_path(path: str) -> str:
    """Return `path`, or raise `ValueError` when it isn't a plain path inside a root.

    `Blue/01 Intro.mp3` is fine; `/etc/passwd`, `../x`, `a//b`, and `a/./b` are not.
    """
    parts = path.split("/")
    if not path or path.startswith("/") or any(part in {"", ".", ".."} for part in parts):
        message = f"{path!r} isn't a path inside a Library."
        raise ValueError(message)
    if "\0" in path or "\\" in path:
        message = f"{path!r} has a character a Library path can't hold."
        raise ValueError(message)
    return path


type LibraryPath = Annotated[str, AfterValidator(check_library_path)]
"""A path relative to a root, checked so it can't leave the root."""


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class LibraryRoot(_Model):
    """Where a Library's files are: a storage kind, such as `folder` or `zip`, and a path."""

    kind: str
    path: str


class CheckRoot(_Model):
    """Ask whether a root can be read."""

    root: LibraryRoot


class RootCheck(_Model):
    """Whether the root can be read, and if not, why."""

    readable: bool
    message: str = ""


class ListFiles(_Model):
    """List the root's files whose extension is one of `extensions`, such as `mp3`."""

    root: LibraryRoot
    extensions: frozenset[str]


class LibraryFile(_Model):
    """One file in a Library."""

    path: LibraryPath
    size: int
    modified_ns: int


class FileList(_Model):
    """The files of a root, in path order."""

    files: tuple[LibraryFile, ...]


class FileRequest(_Model):
    """Ask about one file of a root."""

    root: LibraryRoot
    path: LibraryPath


class FileLocation(_Model):
    """Where a file's bytes are.

    A file in a folder, or a member stored uncompressed in a zip archive, has a
    `local_path` with an `offset` and a `length`. A compressed member has none:
    `compressed` is set, and it must be fetched first. A file that isn't there, or
    can't be read now, is `missing`: an ordinary answer, not a failure.
    """

    local_path: str | None
    offset: int = 0
    length: int
    compressed: bool = False
    missing: bool = False


class FileFingerprint(_Model):
    """A file's size plus a hash of its first and last 64 KB, to recognize it after a move."""

    value: str


class FetchFile(_Model):
    """Copy a file into `folder`, an empty folder the caller owns."""

    root: LibraryRoot
    path: LibraryPath
    folder: str


class FetchedFile(_Model):
    """Where the copy is."""

    local_path: str


class LibraryBackend(Protocol):
    """Reads the files of roots of one storage kind."""

    def check(self, request: CheckRoot) -> RootCheck:
        """Say whether the root can be read."""
        ...

    def list_files(self, request: ListFiles) -> FileList:
        """List the root's files with the requested extensions."""
        ...

    def locate(self, request: FileRequest) -> FileLocation:
        """Say where a file's bytes are."""
        ...

    def fingerprint(self, request: FileRequest) -> FileFingerprint:
        """Return the file's fingerprint."""
        ...

    def fetch(self, request: FetchFile) -> FetchedFile:
        """Copy the file into the requested folder."""
        ...


LIBRARY_BACKEND = ExtensionPoint[LibraryBackend]("library_backend")
CHECK_ROOT = LIBRARY_BACKEND.operation(
    "check", CheckRoot, RootCheck, lambda backend: backend.check, deadline=timedelta(seconds=10)
)
LIST_FILES = LIBRARY_BACKEND.operation(
    "list_files",
    ListFiles,
    FileList,
    lambda backend: backend.list_files,
    deadline=timedelta(hours=1),
)
LOCATE_FILE = LIBRARY_BACKEND.operation(
    "locate",
    FileRequest,
    FileLocation,
    lambda backend: backend.locate,
    deadline=timedelta(seconds=5),
)
FINGERPRINT_FILE = LIBRARY_BACKEND.operation(
    "fingerprint",
    FileRequest,
    FileFingerprint,
    lambda backend: backend.fingerprint,
    deadline=timedelta(seconds=30),
)
FETCH_FILE = LIBRARY_BACKEND.operation(
    "fetch", FetchFile, FetchedFile, lambda backend: backend.fetch, deadline=timedelta(minutes=10)
)
