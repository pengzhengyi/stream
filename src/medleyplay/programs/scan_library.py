"""The program of a Library scan: list the files, then read what changed since the last scan."""

import shutil
import time
from pathlib import Path, PurePosixPath
from typing import Final

from pydantic import BaseModel, ConfigDict

from medleyplay.plugin_api import (
    CHECK_ROOT,
    FETCH_FILE,
    FINGERPRINT_FILE,
    LIST_FILES,
    LOCATE_FILE,
    READ_TAGS,
    CheckRoot,
    FetchFile,
    FileRequest,
    LibraryFile,
    LibraryPath,
    LibraryRoot,
    ListFiles,
    ReadTags,
    Tags,
)
from medleyplay.plugin_host.job import JobContext, JobProgram, PluginCallFailedError

REPORT_EVERY: Final = 1.0
"""Seconds between progress reports."""


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class KnownFile(_Model):
    """What the last scan recorded about a file whose tags it read."""

    size: int
    modified_ns: int


class ScanLibrary(_Model):
    """Scan `root` for files with `extensions`; skip known files that haven't changed.

    With `full`, every file is read again.
    """

    root: LibraryRoot
    extensions: frozenset[str]
    known: dict[LibraryPath, KnownFile]
    full: bool = False


class ScannedFile(_Model):
    """One file the scan found.

    An unchanged file has no fingerprint or tags. A file whose tags couldn't be read
    has the `error` instead.
    """

    path: LibraryPath
    size: int
    modified_ns: int
    changed: bool
    fingerprint: str | None = None
    tags: Tags | None = None
    error: str = ""


class LibraryScan(_Model):
    """What the scan found: every file, or why the root couldn't be read."""

    readable: bool
    message: str = ""
    files: tuple[ScannedFile, ...] = ()


def run(request: ScanLibrary, context: JobContext) -> LibraryScan:
    """Scan the root."""
    kind = request.root.kind
    check = context.call(CHECK_ROOT, kind, CheckRoot(root=request.root))
    if not check.readable:
        return LibraryScan(readable=False, message=check.message)
    listing = context.call(
        LIST_FILES, kind, ListFiles(root=request.root, extensions=request.extensions)
    )
    files = list({file.path: file for file in listing.files}.values())
    scanned: list[ScannedFile] = []
    reported = time.monotonic()
    for done, file in enumerate(files):
        if time.monotonic() - reported >= REPORT_EVERY:
            context.report(done / len(files), f"Read {done} of {len(files)} files")
            reported = time.monotonic()
        known = request.known.get(file.path)
        unchanged = known == KnownFile(size=file.size, modified_ns=file.modified_ns)
        if unchanged and not request.full:
            scanned.append(_file(file, changed=False))
        else:
            scanned.append(_read(request.root, file, context))
    return LibraryScan(readable=True, files=tuple(scanned))


def _file(file: LibraryFile, *, changed: bool) -> ScannedFile:
    return ScannedFile(
        path=file.path, size=file.size, modified_ns=file.modified_ns, changed=changed
    )


def _read(root: LibraryRoot, file: LibraryFile, context: JobContext) -> ScannedFile:
    request = FileRequest(root=root, path=file.path)
    extension = PurePosixPath(file.path).suffix.lower().removeprefix(".")
    try:
        fingerprint = context.call(FINGERPRINT_FILE, root.kind, request).value
        location = context.call(LOCATE_FILE, root.kind, request)
        if location.compressed or location.local_path is None:
            tags = _read_fetched(root, file, extension, context)
        else:
            read = ReadTags(
                local_path=location.local_path, offset=location.offset, length=location.length
            )
            tags = context.call(READ_TAGS, extension, read)
    except PluginCallFailedError as error:
        return _file(file, changed=True).model_copy(update={"error": str(error)})
    return _file(file, changed=True).model_copy(update={"fingerprint": fingerprint, "tags": tags})


def _read_fetched(
    root: LibraryRoot, file: LibraryFile, extension: str, context: JobContext
) -> Tags:
    folder = context.work_dir / "fetched"
    folder.mkdir(exist_ok=True)
    try:
        fetched = context.call(
            FETCH_FILE, root.kind, FetchFile(root=root, path=file.path, folder=str(folder))
        )
        copy = Path(fetched.local_path).resolve()
        if not copy.is_relative_to(folder.resolve()):
            message = f"The copy of {file.path!r} is outside the folder it was fetched into."
            raise PluginCallFailedError(kind="plugin", message=message, plugin=None, key=root.kind)
        return context.call(READ_TAGS, extension, ReadTags(local_path=str(copy)))
    finally:
        shutil.rmtree(folder, ignore_errors=True)


SCAN_LIBRARY: JobProgram[ScanLibrary, LibraryScan] = JobProgram(ScanLibrary, LibraryScan, run)
