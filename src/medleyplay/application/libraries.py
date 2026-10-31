"""Libraries: registering them, scanning them, and applying each scan to the catalog."""

from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Final

from sqlalchemy import Select, delete, exists, select
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application import Clock, details
from medleyplay.application.jobs import JobKind, JobService
from medleyplay.application.plugins import PluginService
from medleyplay.application.segments import drop_songs
from medleyplay.domain.accounts import Account
from medleyplay.domain.catalog import SourceState, TrackId
from medleyplay.domain.details import Field, Origin, Value
from medleyplay.domain.errors import ForbiddenError, InvalidInputError, NotFoundError
from medleyplay.domain.jobs import Job
from medleyplay.domain.libraries import (
    LIBRARY_SOURCE,
    Library,
    LibraryId,
    LibraryKind,
    LibraryState,
    library_locator,
    parse_library_name,
    path_of_locator,
    scan_target,
)
from medleyplay.domain.video_text import Chapter, VideoText
from medleyplay.persistence.schema import LibraryRow, SourceRow, TrackRow
from medleyplay.plugin_api import CHECK_ROOT, LIBRARY_BACKEND, TAG_READER, CheckRoot, LibraryRoot
from medleyplay.programs.info_json import InfoText
from medleyplay.programs.scan_library import (
    InfoJson,
    KnownFile,
    LibraryScan,
    ScanLibrary,
    ScannedFile,
    Stamp,
)

SCAN_KIND: Final = "scan_library"
INFO_JSON: Final = "info_json"
INFO_JSON_ERROR: Final = "info_json_error"
_SIDECAR_KEYS: Final = frozenset({INFO_JSON, INFO_JSON_ERROR})
"""The keys of a Source's details for its `.info.json`: its stamp, and why the last read failed."""
READER_VERSION: Final = 2
"""What a scan reads from a file; raised when it reads more, so the next scan reads each again."""

type ScanKind = JobKind[ScanLibrary, LibraryScan]


def scan_library_kind(clock: Clock) -> ScanKind:
    """Return the Job kind that scans a Library and applies the scan to the catalog."""

    def complete(db: Session, job: Job, scan: LibraryScan) -> None:
        apply_scan(db, LibraryId(int(job.target.removeprefix("library:"))), scan, clock)

    return JobKind(
        name=SCAN_KIND,
        program="medleyplay.programs.scan_library:SCAN_LIBRARY",
        request=ScanLibrary,
        result=LibraryScan,
        complete=complete,
        points=(LIBRARY_BACKEND.name, TAG_READER.name),
    )


@dataclass(frozen=True)
class Registered:
    """A Library, whether this request created it, and its scan when it did."""

    library: Library
    created: bool
    scan: Job | None


class LibraryService:
    """Register, list, scan, and remove Libraries."""

    def __init__(
        self,
        units: sessionmaker[Session],
        clock: Clock,
        plugins: PluginService,
        jobs: JobService,
        kind: ScanKind,
        data_dir: Path,
    ) -> None:
        """Create a service; `data_dir` is refused as a Library, with anything inside it."""
        self._units = units
        self._clock = clock
        self._plugins = plugins
        self._jobs = jobs
        self._kind = kind
        self._data_dir = data_dir.resolve()

    def register(self, caller: Account, name: str, kind: LibraryKind, path: str) -> Registered:
        """Register a Library and start its scan; admins only.

        A root already registered returns its Library unchanged, whatever `name` says.
        """
        _require_admin(caller)
        name = parse_library_name(name)
        root = self._canonical(path)
        existing = self._find(kind, root)
        if existing is not None:
            return Registered(existing, created=False, scan=None)
        check = self._plugins.call(
            CHECK_ROOT, kind, CheckRoot(root=LibraryRoot(kind=kind, path=root))
        )
        if not check.readable:
            raise InvalidInputError(check.message)
        with self._units.begin() as db:
            row = LibraryRow(
                name=name,
                kind=kind,
                path=root,
                state=LibraryState.ONLINE,
                message="",
                file_count=0,
                added_at=self._clock(),
            )
            db.add(row)
            db.flush()
            library = _to_library(row)
        return Registered(library, created=True, scan=self.scan(caller, library.id))

    def list_libraries(self) -> list[Library]:
        """Return every Library, in the order they were registered."""
        with self._units() as db:
            return [
                _to_library(row) for row in db.scalars(select(LibraryRow).order_by(LibraryRow.id))
            ]

    def scan(self, caller: Account, library_id: LibraryId, *, full: bool = False) -> Job:
        """Start a scan of the Library, or return the one already active; admins only.

        A full scan reads every file again, even those that look unchanged.
        """
        _require_admin(caller)
        with self._units() as db:
            library = _to_library(_library_row(db, library_id))
            known = _known_files(db, library_id)
        extensions = frozenset(self._plugins.available_keys().get(TAG_READER.name, []))
        request = ScanLibrary(
            root=LibraryRoot(kind=library.kind, path=library.path),
            extensions=extensions,
            known=known,
            full=full,
        )
        return self._jobs.submit(self._kind, scan_target(library_id), request, caller.id)

    def remove(self, caller: Account, library_id: LibraryId) -> None:
        """Remove a Library, its Sources, its files' songs, and Tracks left without one.

        Admins only. Its active scan is cancelled. Removing a Library that is gone changes nothing.
        """
        _require_admin(caller)
        active = self._jobs.active(SCAN_KIND, scan_target(library_id))
        if active is not None:
            self._jobs.cancel(caller, active.id)
        with self._units.begin() as db:
            if db.get(LibraryRow, library_id) is None:
                return
            sources = list(db.scalars(_sources_of(library_id)))
            track_ids = {source.track_id for source in sources}
            drop_songs(db, _sources_of(library_id).with_only_columns(SourceRow.id))
            for source in sources:
                db.delete(source)
            db.flush()
            orphaned = select(TrackRow.id).where(
                TrackRow.id.in_(track_ids),
                ~exists().where(SourceRow.track_id == TrackRow.id),
            )
            db.execute(delete(TrackRow).where(TrackRow.id.in_(orphaned)))
            db.execute(delete(LibraryRow).where(LibraryRow.id == library_id))

    def _canonical(self, path: str) -> str:
        root = Path(path).expanduser().resolve()
        if root == self._data_dir or root.is_relative_to(self._data_dir):
            message = "A Library can't be inside medleyplay's own data folder."
            raise InvalidInputError(message)
        return str(root)

    def _find(self, kind: LibraryKind, root: str) -> Library | None:
        with self._units() as db:
            row = db.scalar(
                select(LibraryRow).where(LibraryRow.kind == kind, LibraryRow.path == root)
            )
            return None if row is None else _to_library(row)


def apply_scan(db: Session, library_id: LibraryId, scan: LibraryScan, clock: Clock) -> None:
    """Apply a completed scan to the catalog; a scan of a removed Library changes nothing.

    An unreadable root, or one that lists nothing after holding files, marks the
    Library offline and changes no Source.
    """
    library = db.get(LibraryRow, library_id)
    if library is None:
        return
    if not scan.readable or (not scan.files and library.file_count > 0):
        library.state = LibraryState.OFFLINE
        library.message = scan.message or "The Library lists no files; is its drive connected?"
        return
    now = clock()
    sources = {path_of_locator(row.locator): row for row in db.scalars(_sources_of(library_id))}
    files = {file.path: file for file in scan.files}
    unseen = {path: row for path, row in sources.items() if path not in files}
    new = [file for path, file in files.items() if path not in sources]
    moved = _moves(new, unseen)
    for file in new:
        source = moved.get(file.path)
        if source is None:
            _add(db, library_id, file, now)
        else:
            unseen.pop(path_of_locator(source.locator))
            source.locator = library_locator(library_id, file.path)
            _record_name(db, TrackId(source.track_id), file, now)
            _update(db, source, file, now)
    for path, file in files.items():
        if path in sources and path not in unseen:
            _update(db, sources[path], file, now)
    for source in unseen.values():
        source.state = SourceState.MISSING
    library.state = LibraryState.ONLINE
    library.message = ""
    library.file_count = len(files)
    library.last_scanned_at = now


def _moves(new: Iterable[ScannedFile], unseen: dict[str, SourceRow]) -> dict[str, SourceRow]:
    # Only a one-to-one match is a move: a fingerprint shared by two new files, or by
    # two Sources, could be a copy, and guessing would hand one file's ratings to another.
    new_counts = Counter(file.fingerprint for file in new if file.fingerprint)
    by_fingerprint: defaultdict[str, list[SourceRow]] = defaultdict(list)
    for source in unseen.values():
        if source.fingerprint:
            by_fingerprint[source.fingerprint].append(source)
    return {
        file.path: by_fingerprint[file.fingerprint][0]
        for file in new
        if file.fingerprint
        and new_counts[file.fingerprint] == 1
        and len(by_fingerprint[file.fingerprint]) == 1
    }


def _add(db: Session, library_id: LibraryId, file: ScannedFile, now: datetime) -> None:
    track = TrackRow(title=_title(file), added_at=now)
    db.add(track)
    db.flush()
    source = SourceRow(
        track_id=track.id, kind=LIBRARY_SOURCE, locator=library_locator(library_id, file.path)
    )
    db.add(source)
    _record_name(db, TrackId(track.id), file, now)
    _update(db, source, file, now, added=True)


def _update(
    db: Session, source: SourceRow, file: ScannedFile, now: datetime, *, added: bool = False
) -> None:
    previous = dict(source.details or {})
    track_id = TrackId(source.track_id)
    sidecar = _apply_info_json(db, track_id, file.info_json, previous, now)
    if file.changed:
        source.fingerprint = file.fingerprint
        source.details = {
            "size": file.size,
            "modified_ns": file.modified_ns,
            "error": file.error,
            "reader": READER_VERSION,
            **sidecar,
        }
        if file.tags is not None or added:
            _set_details(db, track_id, file, now)
    else:
        kept = {key: value for key, value in previous.items() if key not in _SIDECAR_KEYS}
        source.details = {**kept, "size": file.size, "modified_ns": file.modified_ns, **sidecar}
    protected = file.tags is not None and file.tags.protected
    if file.changed:
        source.state = SourceState.CANT_PLAY if protected else SourceState.OK
    elif source.state == SourceState.MISSING:
        source.state = SourceState.OK


def _apply_info_json(
    db: Session,
    track_id: TrackId,
    info: InfoJson | None,
    previous: dict[str, object],
    now: datetime,
) -> dict[str, object]:
    """Apply the `.info.json` the scan found beside the file; return what the Source keeps of it.

    Text read replaces the Track's video's text. A sidecar that couldn't be read
    leaves the earlier text and notes the error until a later read succeeds, and
    one the scan didn't read leaves both as they were. A sidecar that was there
    last scan and isn't now takes with it the text read from a file, never a paste.
    """
    if info is None:
        if INFO_JSON in previous:
            details.forget_video_text_read_from_a_file(db, track_id, now)
        return {}
    kept: dict[str, object] = {INFO_JSON: {"size": info.size, "modified_ns": info.modified_ns}}
    if info.error:
        kept[INFO_JSON_ERROR] = info.error
    elif info.text is None and INFO_JSON_ERROR in previous:
        kept[INFO_JSON_ERROR] = previous[INFO_JSON_ERROR]
    elif info.text is not None and (text := _video_text(info.text)) is not None:
        details.record_video_text(db, track_id, text, "file", now)
    return kept


def _video_text(text: InfoText) -> VideoText | None:
    """Return the sidecar's text, or `None` when it has no words."""
    if not (text.title.strip() or text.description.strip() or text.chapters):
        return None
    chapters = tuple(Chapter(chapter.start_ms, chapter.title) for chapter in text.chapters)
    return VideoText(text.title, text.description, chapters)


def _set_details(db: Session, track_id: TrackId, file: ScannedFile, now: datetime) -> None:
    tags = file.tags
    values: dict[Field, Value] = {}
    if tags is not None:
        values = {
            Field.TITLE: tags.title,
            Field.ARTIST: tags.artist,
            Field.ALBUM: tags.album,
            Field.ALBUM_ARTIST: tags.album_artist,
        }
        if tags.track_number is not None:
            values[Field.TRACK_NUMBER] = tags.track_number
    # The length first, so recording the values settles a split file's songs to it.
    track = db.get(TrackRow, track_id)
    if track is not None:
        track.duration_ms = tags.duration_ms if tags else None
    details.record(db, track_id, Origin.FILES, values, now)


def _record_name(db: Session, track_id: TrackId, file: ScannedFile, now: datetime) -> None:
    # Recorded when a file is added or moved: a file keeps its name otherwise.
    details.record(db, track_id, Origin.FILE_NAME, {Field.TITLE: _title(file)}, now)


def _title(file: ScannedFile) -> str:
    return PurePosixPath(file.path).stem


def _known_files(db: Session, library_id: LibraryId) -> dict[str, KnownFile]:
    # A file whose tags couldn't be read, or that an older reader read, isn't known,
    # so the next scan reads it again.
    known = {}
    for source in db.scalars(_sources_of(library_id)):
        details = source.details or {}
        if not details.get("error") and details.get("reader") == READER_VERSION:
            known[path_of_locator(source.locator)] = KnownFile(
                size=int(str(details["size"])),
                modified_ns=int(str(details["modified_ns"])),
                info_json=_stamp_of(details.get(INFO_JSON)),
            )
    return known


def _stamp_of(kept: object) -> Stamp | None:
    if not isinstance(kept, dict):
        return None
    return Stamp(size=int(str(kept["size"])), modified_ns=int(str(kept["modified_ns"])))


def _sources_of(library_id: LibraryId) -> Select[SourceRow]:
    return select(SourceRow).where(
        SourceRow.kind == LIBRARY_SOURCE,
        SourceRow.locator.startswith(f"{library_id}/", autoescape=True),
    )


def _library_row(db: Session, library_id: LibraryId) -> LibraryRow:
    row = db.get(LibraryRow, library_id)
    if row is None:
        message = f"There is no Library {library_id}."
        raise NotFoundError(message)
    return row


def _to_library(row: LibraryRow) -> Library:
    return Library(
        id=LibraryId(row.id),
        name=row.name,
        kind=LibraryKind(row.kind),
        path=row.path,
        state=LibraryState(row.state),
        message=row.message,
        file_count=row.file_count,
        added_at=row.added_at,
        last_scanned_at=row.last_scanned_at,
    )


def _require_admin(caller: Account) -> None:
    if not caller.is_admin:
        message = "Only an admin can manage Libraries."
        raise ForbiddenError(message)
