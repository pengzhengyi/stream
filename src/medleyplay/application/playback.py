"""Playback: picking a Track's Source, opening its audio safely, and preparing cache copies.

The core serves every byte itself, from a file it opened and checked, so a faulty
plugin can't make it serve anything outside a Library.
"""

import contextlib
import hashlib
import os
import stat
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application.downloads import DownloadService
from medleyplay.application.jobs import JobKind, JobService
from medleyplay.application.plugins import PluginService
from medleyplay.domain.accounts import Account
from medleyplay.domain.catalog import (
    Availability,
    SourceId,
    SourceState,
    TrackId,
    source_availability,
    track_availability,
)
from medleyplay.domain.errors import (
    ConflictError,
    NotFoundError,
    PluginCallError,
    PluginUnavailableError,
)
from medleyplay.domain.jobs import Job
from medleyplay.domain.libraries import (
    LIBRARY_SOURCE,
    LibraryKind,
    LibraryState,
    library_of_locator,
    path_of_locator,
)
from medleyplay.domain.links import BILIBILI_SOURCE
from medleyplay.domain.playback import (
    CACHE_FOLDER,
    cache_name,
    cache_target,
    media_type,
    source_version,
)
from medleyplay.persistence.schema import DownloadRow, LibraryRow, SourceRow, TrackRow
from medleyplay.plugin_api import (
    LIBRARY_BACKEND,
    LOCATE_FILE,
    FileLocation,
    FileRequest,
    LibraryRoot,
)
from medleyplay.programs.cache_source import CachedSource, CacheSource

CACHE_KIND: Final = "cache_source"
_OPEN_FLAGS: Final = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK

type CacheKind = JobKind[CacheSource, CachedSource]


class AudioFile:
    """An open, checked file and the slice of it that is a Source's audio.

    The caller owns the file and closes it; closing twice is harmless.
    """

    def __init__(self, descriptor: int, offset: int, length: int, media_type: str) -> None:
        """Take ownership of `descriptor`."""
        info = os.fstat(descriptor)
        self.descriptor = descriptor
        self.offset = offset
        self.length = length
        self.media_type = media_type
        seen = f"{info.st_dev}:{info.st_ino}:{info.st_size}:{info.st_mtime_ns}:{offset}:{length}"
        self.version = hashlib.sha256(seen.encode()).hexdigest()[:32]
        """Names these bytes, for the `ETag`; it never shows the file's path."""
        self._closed = False

    def close(self) -> None:
        """Close the file."""
        if not self._closed:
            self._closed = True
            os.close(self.descriptor)


@dataclass(frozen=True)
class Ready:
    """The Track plays from this Source now."""

    source_id: SourceId
    media_type: str


@dataclass(frozen=True)
class Preparing:
    """The Track plays once `job` makes its Source's cache copy."""

    source_id: SourceId
    job: Job


@dataclass(frozen=True)
class Unplayable:
    """No Source of the Track can play, for the reason its best Source gives."""

    availability: Availability


type Playback = Ready | Preparing | Unplayable


def cache_source_kind(data_dir: Path) -> CacheKind:
    """Return the Job kind that copies a compressed member into the cache in `data_dir`."""
    folder = data_dir / CACHE_FOLDER

    def complete(_: Session, job: Job, __: CachedSource) -> None:
        # Older copies of the same Source can't be served again; their names differ.
        _kind, source_id, version = job.target.split(":")
        for older in folder.glob(f"{source_id}-*"):
            if not older.name.startswith(f"{source_id}-{version}."):
                older.unlink(missing_ok=True)

    return JobKind(
        name=CACHE_KIND,
        program="medleyplay.programs.cache_source:CACHE_SOURCE",
        request=CacheSource,
        result=CachedSource,
        complete=complete,
        points=(LIBRARY_BACKEND.name,),
    )


@dataclass(frozen=True)
class _Source:
    id: SourceId
    path: str
    version: str
    library: LibraryRow | None


@dataclass(frozen=True)
class _Gone:
    availability: Availability


@dataclass(frozen=True)
class _NeedsCopy:
    source: _Source
    location: FileLocation


@dataclass(frozen=True)
class _NeedsDownload:
    source_id: SourceId


@dataclass(frozen=True)
class _Remembered:
    path: str
    offset: int
    length: int
    identity: tuple[int, int, int, int]


@dataclass
class _Locations:
    lock: threading.Lock = field(default_factory=threading.Lock)
    known: dict[SourceId, _Remembered] = field(default_factory=dict)


class PlaybackService:
    """Pick the Source a Track plays from, open its audio, and prepare cache copies."""

    def __init__(
        self,
        units: sessionmaker[Session],
        plugins: PluginService,
        jobs: JobService,
        kind: CacheKind,
        data_dir: Path,
        downloads: DownloadService,
    ) -> None:
        """Create a service keeping cache copies in `data_dir`, and starting `downloads`."""
        self._units = units
        self._plugins = plugins
        self._jobs = jobs
        self._kind = kind
        self._downloads = downloads
        self._cache = data_dir / CACHE_FOLDER
        self._locations = _Locations()

    def play(self, caller: Account, track_id: TrackId) -> Playback:
        """Answer how the Track can play: ready, preparing, or unplayable.

        A Source that is ready wins over one that must be prepared first, and a
        Library file to copy wins over a Source to download.
        """
        with self._units() as db:
            if db.get(TrackRow, track_id) is None:
                message = f"No Track has the id {track_id}."
                raise NotFoundError(message)
            sources = db.scalars(
                select(SourceRow).where(SourceRow.track_id == track_id).order_by(SourceRow.id)
            ).all()
            libraries = {row.id: row for row in db.scalars(select(LibraryRow))}
        found: list[Availability] = []
        to_prepare: _NeedsCopy | None = None
        to_download: _NeedsDownload | None = None
        for row in sources:
            match self._consider(row, libraries):
                case AudioFile() as audio:
                    audio.close()
                    return Ready(SourceId(row.id), audio.media_type)
                case _NeedsCopy() as needed:
                    to_prepare = to_prepare or needed
                case _NeedsDownload() as needed:
                    to_download = to_download or needed
                case _Gone(availability=availability):
                    found.append(availability)
        return self._prepared(caller, to_prepare, to_download, found)

    def open_audio(self, source_id: SourceId) -> AudioFile:
        """Open a Source's audio for serving; the caller closes it.

        Raise `NotFoundError` when the Source can't play now, and `ConflictError`
        when its cache copy must be prepared first.
        """
        with self._units() as db:
            row = db.get(SourceRow, source_id)
            if row is not None and row.kind == BILIBILI_SOURCE:
                return self._downloaded_audio(source_id, SourceState(row.state))
            if row is None or row.state != SourceState.OK:
                message = f"The Source {source_id} can't be played."
                raise NotFoundError(message)
            source = _source(row, {lib.id: lib for lib in db.scalars(select(LibraryRow))})
        opened = self._open(source)
        if isinstance(opened, _NeedsCopy):
            message = f"The Source {source_id} must be prepared first."
            raise ConflictError(message)
        if isinstance(opened, _Gone):
            message = f"The Source {source_id} can't be played: it is {opened.availability}."
            raise NotFoundError(message)
        return opened

    def sweep_cache(self) -> None:
        """Remove cache copies of Sources that are gone, or of versions no longer current."""
        if not self._cache.is_dir():
            return
        with self._units() as db:
            current = {
                cache_name(SourceId(row.id), _version(row), path_of_locator(row.locator))
                for row in db.scalars(select(SourceRow).where(SourceRow.kind == LIBRARY_SOURCE))
            }
        for copy in self._cache.iterdir():
            if copy.name not in current:
                copy.unlink(missing_ok=True)

    def _consider(
        self, row: SourceRow, libraries: dict[int, LibraryRow]
    ) -> "AudioFile | _NeedsCopy | _NeedsDownload | _Gone":
        if row.kind == BILIBILI_SOURCE:
            download = self._open_download(SourceId(row.id))
            if download is not None:
                return download
            if row.state == SourceState.UNAVAILABLE:
                return _Gone(Availability.UNAVAILABLE)
            return _NeedsDownload(SourceId(row.id))
        if row.state != SourceState.OK:
            return _Gone(source_availability(SourceState(row.state), online=True))
        return self._try_open(_source(row, libraries))

    def _prepared(
        self,
        caller: Account,
        to_prepare: "_NeedsCopy | None",
        to_download: "_NeedsDownload | None",
        found: list[Availability],
    ) -> Playback:
        if to_prepare is not None:
            return Preparing(to_prepare.source.id, self._prepare(caller, to_prepare))
        if to_download is not None:
            job = self._downloads.start(caller, to_download.source_id)
            if job is not None:
                return Preparing(to_download.source_id, job)
            found.append(Availability.UNAVAILABLE)
        return Unplayable(track_availability(found))

    def _downloaded_audio(self, source_id: SourceId, state: SourceState) -> AudioFile:
        download = self._open_download(source_id)
        if download is not None:
            return download
        if state == SourceState.UNAVAILABLE:
            message = f"The Source {source_id} can't be played: it is unavailable."
            raise NotFoundError(message)
        message = f"The Source {source_id} must be downloaded first."
        raise ConflictError(message)

    def _open_download(self, source_id: SourceId) -> AudioFile | None:
        # The name comes from the catalog, never a plugin, and the file must still
        # be a regular file there, not a link.
        with self._units() as db:
            row = db.get(DownloadRow, source_id)
            name = None if row is None else row.file_name
        if name is None:
            return None
        try:
            descriptor = os.open(self._downloads.folder / name, _OPEN_FLAGS)
        except OSError:
            return None
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            os.close(descriptor)
            return None
        return AudioFile(descriptor, 0, info.st_size, media_type(name))

    def sweep_downloads(self) -> None:
        """Remove files in `downloads/` that no Download names, as a crash can leave."""
        self._downloads.sweep()

    def _try_open(self, source: _Source) -> AudioFile | _NeedsCopy | _Gone:
        # While picking a Source, one whose plugin is off or failing is unavailable,
        # so another Source of the Track can still play.
        try:
            return self._open(source)
        except (PluginUnavailableError, PluginCallError):
            return _Gone(Availability.UNAVAILABLE)

    def _open(self, source: _Source) -> AudioFile | _NeedsCopy | _Gone:
        library = source.library
        if library is None:
            return _Gone(Availability.UNAVAILABLE)
        if library.state != LibraryState.ONLINE:
            return _Gone(Availability.OFFLINE)
        reopened = self._reopen(source)
        return reopened if reopened is not None else self._locate(source, library)

    def _locate(self, source: _Source, library: LibraryRow) -> AudioFile | _NeedsCopy | _Gone:
        location = self._plugins.call(
            LOCATE_FILE,
            library.kind,
            FileRequest(root=LibraryRoot(kind=library.kind, path=library.path), path=source.path),
        )
        if location.missing:
            return _Gone(Availability.MISSING)
        if location.compressed or location.local_path is None:
            return self._cached(source, location)
        opened = _open_checked(location, library, media_type(source.path))
        if opened is None:
            return _Gone(Availability.MISSING)
        real, audio = opened
        remembered = _Remembered(real, audio.offset, audio.length, _identity(audio.descriptor))
        with self._locations.lock:
            self._locations.known[source.id] = remembered
        return audio

    def _reopen(self, source: _Source) -> AudioFile | None:
        with self._locations.lock:
            remembered = self._locations.known.get(source.id)
        if remembered is None:
            return None
        try:
            descriptor = os.open(remembered.path, _OPEN_FLAGS)
        except OSError:
            return None
        if _identity(descriptor) != remembered.identity:
            # The file changed since it was located, so its slice may have moved.
            os.close(descriptor)
            return None
        return AudioFile(descriptor, remembered.offset, remembered.length, media_type(source.path))

    def _cached(self, source: _Source, location: FileLocation) -> AudioFile | _NeedsCopy:
        copy = self._cache / cache_name(source.id, source.version, source.path)
        try:
            descriptor = os.open(copy, _OPEN_FLAGS)
        except OSError:
            return _NeedsCopy(source, location)
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size != location.length:
            os.close(descriptor)
            return _NeedsCopy(source, location)
        return AudioFile(descriptor, 0, info.st_size, media_type(source.path))

    def _prepare(self, caller: Account, needed: _NeedsCopy) -> Job:
        source, library = needed.source, needed.source.library
        if library is None:  # pragma: no cover -- a Source with no Library is never prepared
            raise TypeError(source)
        destination = self._cache / cache_name(source.id, source.version, source.path)
        request = CacheSource(
            root=LibraryRoot(kind=library.kind, path=library.path),
            path=source.path,
            length=needed.location.length,
            destination=str(destination),
        )
        return self._jobs.submit(
            self._kind, cache_target(source.id, source.version), request, caller.id
        )


def _source(row: SourceRow, libraries: dict[int, LibraryRow]) -> _Source:
    library = libraries.get(library_of_locator(row.locator)) if row.kind == LIBRARY_SOURCE else None
    return _Source(SourceId(row.id), path_of_locator(row.locator), _version(row), library)


def _version(row: SourceRow) -> str:
    details = row.details or {}
    size, modified_ns = details.get("size"), details.get("modified_ns")
    return source_version(
        row.fingerprint,
        None if size is None else int(str(size)),
        None if modified_ns is None else int(str(modified_ns)),
    )


def _identity(descriptor: int) -> tuple[int, int, int, int]:
    info = os.fstat(descriptor)
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def _open_checked(
    location: FileLocation, library: LibraryRow, kind_of_media: str
) -> tuple[str, AudioFile] | None:
    """Open the file a plugin located, and return its real path and the open audio.

    A file deleted since it was located is `None`; anything but a regular file in
    the Library is refused.

    For a folder the file must be inside the root, and its length is the file's own;
    for a zip archive it must be the root, and the slice must lie inside it.
    """
    local_path = location.local_path
    if local_path is None:  # pragma: no cover -- the caller handles a location without a path
        raise TypeError(location)
    root = Path(library.path).resolve()
    try:
        real = Path(local_path).resolve(strict=True)
    except OSError:
        return None
    inside = real == root if library.kind == LibraryKind.ZIP else real.is_relative_to(root)
    if not inside or (real == root and library.kind == LibraryKind.FOLDER):
        raise _refused(local_path, "is outside its Library")
    try:
        descriptor = os.open(real, _OPEN_FLAGS)
    except OSError as error:
        raise _refused(local_path, f"can't be opened: {error.strerror}") from None
    with _closing_on_error(descriptor):
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise _refused(local_path, "isn't a regular file")
        if library.kind == LibraryKind.FOLDER:
            return str(real), AudioFile(descriptor, 0, info.st_size, kind_of_media)
        if location.offset + location.length > info.st_size:
            raise _refused(local_path, "is shorter than the slice located in it")
        return str(real), AudioFile(descriptor, location.offset, location.length, kind_of_media)


@contextlib.contextmanager
def _closing_on_error(descriptor: int) -> Iterator[None]:
    try:
        yield
    except BaseException:
        os.close(descriptor)
        raise


def _refused(path: str, why: str) -> PluginCallError:
    return PluginCallError("plugin", f"The plugin located {path!r}, which {why}.")
