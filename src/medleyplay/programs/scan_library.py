"""The program of a Library scan: list the files, then read what changed since the last scan."""

import shutil
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
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
from medleyplay.programs.info_json import MAX_BYTES, InfoJsonError, InfoText, parse_info_json

REPORT_EVERY: Final = 1.0
"""Seconds between progress reports."""
SIDECAR_SUFFIX: Final = ".info.json"
"""The name's end of the file yt-dlp writes beside `<name>.m4a`: `<name>.info.json`."""


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Stamp(_Model):
    """A file's size and modified time, which tell whether it changed."""

    size: int
    modified_ns: int


class KnownFile(_Model):
    """What the last scan recorded about a file whose tags it read.

    `info_json` is the stamp of the `.info.json` beside it when the last scan found one.
    """

    size: int
    modified_ns: int
    info_json: Stamp | None = None


class ScanLibrary(_Model):
    """Scan `root` for files with `extensions`; skip known files that haven't changed.

    With `full`, every file is read again.
    """

    root: LibraryRoot
    extensions: frozenset[str]
    known: dict[LibraryPath, KnownFile]
    full: bool = False


class InfoJson(_Model):
    """The `.info.json` beside a file: its stamp, and what reading it gave.

    A sidecar the scan skipped as unchanged has neither `text` nor `error`. One it
    read has the `text`, or the `error` when it couldn't be read as a video's details.
    """

    size: int
    modified_ns: int
    text: InfoText | None = None
    error: str = ""


class ScannedFile(_Model):
    """One file the scan found.

    An unchanged file has no fingerprint or tags. A file whose tags couldn't be read
    has the `error` instead. `info_json` is the sidecar beside the file, if there is one.
    """

    path: LibraryPath
    size: int
    modified_ns: int
    changed: bool
    fingerprint: str | None = None
    tags: Tags | None = None
    error: str = ""
    info_json: InfoJson | None = None


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
    extensions = request.extensions | {"json"}
    listing = context.call(LIST_FILES, kind, ListFiles(root=request.root, extensions=extensions))
    audio, sidecars = _split(listing.files, request.extensions)
    scanned: list[ScannedFile] = []
    reported = time.monotonic()
    for done, file in enumerate(audio):
        if time.monotonic() - reported >= REPORT_EVERY:
            context.report(done / len(audio), f"Read {done} of {len(audio)} files")
            reported = time.monotonic()
        known = request.known.get(file.path)
        unchanged = known is not None and _stamp(file) == Stamp(
            size=known.size, modified_ns=known.modified_ns
        )
        if unchanged and not request.full:
            scanned_file = _file(file, changed=False)
        else:
            scanned_file = _read(request.root, file, context)
        sidecar = sidecars.get(_name_of(file.path))
        if sidecar is not None:
            info = _info_json(request, sidecar, known, context)
            scanned_file = scanned_file.model_copy(update={"info_json": info})
        scanned.append(scanned_file)
    return LibraryScan(readable=True, files=tuple(scanned))


def _split(
    listed: Iterable[LibraryFile], extensions: frozenset[str]
) -> tuple[list[LibraryFile], dict[str, LibraryFile]]:
    """Split a listing into the audio files and their sidecars, keyed by the name they share.

    `Blue/a.m4a` and `Blue/a.info.json` share `Blue/a`. A sidecar with no audio file
    beside it, and any other file, is left out.
    """
    files = list({file.path: file for file in listed}.values())
    audio = [file for file in files if _extension(file.path) in extensions]
    names = {_name_of(file.path) for file in audio}
    sidecars = {
        file.path[: -len(SIDECAR_SUFFIX)]: file
        for file in files
        if file.path.lower().endswith(SIDECAR_SUFFIX)
    }
    return audio, {name: sidecar for name, sidecar in sidecars.items() if name in names}


def _extension(path: str) -> str:
    return PurePosixPath(path).suffix.lower().removeprefix(".")


def _name_of(path: str) -> str:
    """Return the path without its extension: `Blue/a.m4a` is `Blue/a`."""
    suffix = PurePosixPath(path).suffix
    return path.removesuffix(suffix) if suffix else path


def _stamp(file: LibraryFile) -> Stamp:
    return Stamp(size=file.size, modified_ns=file.modified_ns)


def _file(file: LibraryFile, *, changed: bool) -> ScannedFile:
    return ScannedFile(
        path=file.path, size=file.size, modified_ns=file.modified_ns, changed=changed
    )


def _read(root: LibraryRoot, file: LibraryFile, context: JobContext) -> ScannedFile:
    request = FileRequest(root=root, path=file.path)
    extension = _extension(file.path)
    try:
        location = context.call(LOCATE_FILE, root.kind, request)
        if location.missing:  # pragma: no cover -- a file removed between listing and reading
            return _file(file, changed=True).model_copy(update={"error": "The file is gone."})
        fingerprint = context.call(FINGERPRINT_FILE, root.kind, request).value
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
    with _fetched(root, file.path, context) as copy:
        return context.call(READ_TAGS, extension, ReadTags(local_path=str(copy)))


@contextmanager
def _fetched(root: LibraryRoot, path: LibraryPath, context: JobContext) -> Iterator[Path]:
    """Copy the file into a folder of the Job's, yield the copy, and remove it afterwards."""
    folder = context.work_dir / "fetched"
    folder.mkdir(exist_ok=True)
    try:
        fetched = context.call(
            FETCH_FILE, root.kind, FetchFile(root=root, path=path, folder=str(folder))
        )
        copy = Path(fetched.local_path).resolve()
        if not copy.is_relative_to(folder.resolve()):
            message = f"The copy of {path!r} is outside the folder it was fetched into."
            raise PluginCallFailedError(kind="plugin", message=message, plugin=None, key=root.kind)
        yield copy
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def _info_json(
    request: ScanLibrary, sidecar: LibraryFile, known: KnownFile | None, context: JobContext
) -> InfoJson:
    """Report the sidecar, reading it when it is new, changed, or the scan is full."""
    stamp = _stamp(sidecar)
    unchanged = known is not None and known.info_json == stamp
    listed = InfoJson(size=sidecar.size, modified_ns=sidecar.modified_ns)
    if unchanged and not request.full:
        return listed
    try:
        text = parse_info_json(_contents(request.root, sidecar, context))
    except InfoJsonError as error:
        return listed.model_copy(update={"error": str(error)})
    except PluginCallFailedError as error:
        return listed.model_copy(update={"error": f"can't be read ({error})"})
    except OSError as error:
        return listed.model_copy(update={"error": f"can't be read ({type(error).__name__})"})
    return listed.model_copy(update={"text": text})


def _contents(root: LibraryRoot, sidecar: LibraryFile, context: JobContext) -> bytes:
    """Return the sidecar's bytes, or raise `InfoJsonError` when it is gone or too large."""
    _require_small(sidecar.size)
    location = context.call(LOCATE_FILE, root.kind, FileRequest(root=root, path=sidecar.path))
    if location.missing:
        message = "is gone"
        raise InfoJsonError(message)
    _require_small(location.length)
    if location.compressed or location.local_path is None:
        with _fetched(root, sidecar.path, context) as copy, copy.open("rb") as file:
            data = file.read(MAX_BYTES + 1)
    else:
        with Path(location.local_path).open("rb") as file:
            file.seek(location.offset)
            data = file.read(location.length)
    _require_small(len(data))
    return data


def _require_small(size: int) -> None:
    if size > MAX_BYTES:
        message = f"is too large ({size:,} bytes; at most {MAX_BYTES:,} are read)"
        raise InfoJsonError(message)


SCAN_LIBRARY: JobProgram[ScanLibrary, LibraryScan] = JobProgram(ScanLibrary, LibraryScan, run)
