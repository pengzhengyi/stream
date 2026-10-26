"""Picking a Track's Source, opening its audio safely, and preparing compressed members."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application.accounts import AccountService
from medleyplay.application.downloads import DownloadService
from medleyplay.application.jobs import JobService
from medleyplay.application.playback import (
    AudioFile,
    PlaybackService,
    Preparing,
    Ready,
    Unplayable,
    cache_source_kind,
)
from medleyplay.domain.accounts import Account
from medleyplay.domain.catalog import Availability, SourceId, SourceState, TrackId
from medleyplay.domain.errors import ConflictError, NotFoundError, PluginCallError
from medleyplay.domain.jobs import JobState
from medleyplay.domain.libraries import LibraryId, LibraryKind, library_locator
from medleyplay.persistence.schema import LibraryRow, SourceRow, TrackRow
from tests.support.audio import Song, folder_of, wav_bytes, zip_of
from tests.support.factories import NewAccountFactory, SourceKeyFactory, TrackDetailsFactory
from tests.support.fakes import FakeClock
from tests.support.hosts import started_plugins
from tests.support.libraries import Libraries, running_libraries


@pytest.fixture
def running(units: sessionmaker[Session], clock: FakeClock, tmp_path: Path) -> Iterator[Libraries]:
    with running_libraries(units, clock, tmp_path / "data") as libraries:
        yield libraries


@pytest.fixture
def alice(accounts: AccountService) -> Account:
    return accounts.create_first_admin(NewAccountFactory.admin()).account


def _scanned(running: Libraries, alice: Account, kind: LibraryKind, root: Path) -> None:
    registered = running.service.register(alice, "Music", kind, str(root))
    assert registered.scan is not None
    running.wait_for(registered.scan.id, JobState.SUCCEEDED)


def _sources(units: sessionmaker[Session]) -> dict[str, tuple[TrackId, SourceId]]:
    """Each Source's path in its Library, with its Track and its own id."""
    with units() as db:
        return {
            row.locator.partition("/")[2]: (TrackId(row.track_id), SourceId(row.id))
            for row in db.scalars(select(SourceRow))
        }


def _read(audio: AudioFile) -> bytes:
    try:
        return os.pread(audio.descriptor, audio.length, audio.offset)
    finally:
        audio.close()


def _old_mixes(tmp_path: Path) -> Path:
    """An archive holding `stored.wav`, stored, and `deflated.wav`, compressed."""
    return zip_of(
        tmp_path / "Old Mixes.zip",
        {"stored.wav": Song("Stored"), "deflated.wav": Song("Deflated")},
        compressed=frozenset({"deflated.wav"}),
    )


def test_a_folder_file_is_ready_and_opens_whole(
    running: Libraries, alice: Account, units: sessionmaker[Session], tmp_path: Path
) -> None:
    _scanned(running, alice, LibraryKind.FOLDER, folder_of(tmp_path / "M", {"a.wav": Song("A")}))
    track_id, source_id = _sources(units)["a.wav"]

    answer = running.playback.play(alice, track_id)

    assert answer == Ready(source_id, "audio/wav")
    assert _read(running.playback.open_audio(source_id)) == wav_bytes(Song("A"))


def test_a_stored_zip_member_opens_as_its_slice_of_the_archive(
    running: Libraries, alice: Account, units: sessionmaker[Session], tmp_path: Path
) -> None:
    _scanned(running, alice, LibraryKind.ZIP, _old_mixes(tmp_path))
    _, source_id = _sources(units)["stored.wav"]

    audio = running.playback.open_audio(source_id)

    assert audio.media_type == "audio/wav"
    assert _read(audio) == wav_bytes(Song("Stored"))


def test_a_compressed_member_is_prepared_once_then_plays_from_the_cache(
    running: Libraries, alice: Account, units: sessionmaker[Session], tmp_path: Path
) -> None:
    _scanned(running, alice, LibraryKind.ZIP, _old_mixes(tmp_path))
    track_id, source_id = _sources(units)["deflated.wav"]

    first = running.playback.play(alice, track_id)
    second = running.playback.play(alice, track_id)
    assert isinstance(first, Preparing)
    assert isinstance(second, Preparing)
    with pytest.raises(ConflictError, match="must be prepared first"):
        running.playback.open_audio(source_id)
    running.wait_for(first.job.id, JobState.SUCCEEDED)

    assert second.job.id == first.job.id
    assert running.playback.play(alice, track_id) == Ready(source_id, "audio/wav")
    assert _read(running.playback.open_audio(source_id)) == wav_bytes(Song("Deflated"))


def test_serving_a_cache_copy_marks_when_it_was_served_and_keeps_its_version(
    running: Libraries, alice: Account, units: sessionmaker[Session], tmp_path: Path
) -> None:
    _scanned(running, alice, LibraryKind.ZIP, _old_mixes(tmp_path))
    track_id, source_id = _sources(units)["deflated.wav"]
    preparing = running.playback.play(alice, track_id)
    assert isinstance(preparing, Preparing)
    running.wait_for(preparing.job.id, JobState.SUCCEEDED)
    [copy] = (tmp_path / "data" / "cache" / "sources").iterdir()
    os.utime(copy, (1_000_000, 1_000_000))
    before = running.playback.open_audio(source_id)
    before.close()

    after = running.playback.open_audio(source_id)
    after.close()

    assert copy.stat().st_atime > 1_000_000
    assert (copy.stat().st_mtime, after.version) == (1_000_000, before.version)


def test_a_ready_source_wins_over_an_older_one_that_must_be_prepared(
    running: Libraries, alice: Account, units: sessionmaker[Session], tmp_path: Path
) -> None:
    _scanned(running, alice, LibraryKind.ZIP, _old_mixes(tmp_path))
    _scanned(running, alice, LibraryKind.FOLDER, folder_of(tmp_path / "M", {"d.wav": Song("D")}))
    sources = _sources(units)
    track_id, _ = sources["deflated.wav"]
    _, folder_source = sources["d.wav"]
    with units.begin() as db:
        row = db.get(SourceRow, folder_source)
        assert row is not None
        row.track_id = track_id

    answer = running.playback.play(alice, track_id)

    assert answer == Ready(folder_source, "audio/wav")


def test_a_file_changed_after_it_was_located_is_located_again(
    running: Libraries, alice: Account, units: sessionmaker[Session], tmp_path: Path
) -> None:
    root = folder_of(tmp_path / "M", {"a.wav": Song("A")})
    _scanned(running, alice, LibraryKind.FOLDER, root)
    _, source_id = _sources(units)["a.wav"]
    running.playback.open_audio(source_id).close()

    (root / "a.wav").write_bytes(wav_bytes(Song("A much longer title")))

    assert _read(running.playback.open_audio(source_id)) == wav_bytes(Song("A much longer title"))


def test_a_file_gone_since_the_scan_is_missing(
    running: Libraries, alice: Account, units: sessionmaker[Session], tmp_path: Path
) -> None:
    root = folder_of(tmp_path / "M", {"a.wav": Song("A")})
    _scanned(running, alice, LibraryKind.FOLDER, root)
    track_id, source_id = _sources(units)["a.wav"]

    (root / "a.wav").unlink()

    assert running.playback.play(alice, track_id) == Unplayable(Availability.MISSING)
    with pytest.raises(NotFoundError, match="it is missing"):
        running.playback.open_audio(source_id)


def test_a_track_of_an_offline_library_is_unplayable_offline(
    running: Libraries, alice: Account, units: sessionmaker[Session], tmp_path: Path
) -> None:
    _scanned(running, alice, LibraryKind.FOLDER, folder_of(tmp_path / "M", {"a.wav": Song("A")}))
    track_id, _ = _sources(units)["a.wav"]
    with units.begin() as db:
        for library in db.scalars(select(LibraryRow)):
            library.state = "offline"

    assert running.playback.play(alice, track_id) == Unplayable(Availability.OFFLINE)


def test_a_source_that_cant_play_is_never_opened(
    running: Libraries, alice: Account, units: sessionmaker[Session], tmp_path: Path
) -> None:
    _scanned(running, alice, LibraryKind.FOLDER, folder_of(tmp_path / "M", {"a.wav": Song("A")}))
    track_id, source_id = _sources(units)["a.wav"]
    with units.begin() as db:
        row = db.get(SourceRow, source_id)
        assert row is not None
        row.state = SourceState.CANT_PLAY

    assert running.playback.play(alice, track_id) == Unplayable(Availability.CANT_PLAY)
    with pytest.raises(NotFoundError, match="can't be played"):
        running.playback.open_audio(source_id)


def test_a_track_that_does_not_exist_is_not_found(running: Libraries, alice: Account) -> None:
    with pytest.raises(NotFoundError):
        running.playback.play(alice, TrackId(404))


def test_a_newer_cache_copy_removes_the_older_ones(
    running: Libraries, alice: Account, units: sessionmaker[Session], tmp_path: Path
) -> None:
    _scanned(running, alice, LibraryKind.ZIP, _old_mixes(tmp_path))
    track_id, source_id = _sources(units)["deflated.wav"]
    cache = tmp_path / "data" / "cache" / "sources"
    cache.mkdir(parents=True)
    (cache / f"{source_id}-0000000000000000.wav").write_bytes(b"old")

    first = running.playback.play(alice, track_id)
    assert isinstance(first, Preparing)
    running.wait_for(first.job.id, JobState.SUCCEEDED)

    assert [copy.name.split("-")[0] for copy in cache.iterdir()] == [str(source_id)]
    assert not (cache / f"{source_id}-0000000000000000.wav").exists()


def test_sweeping_the_cache_keeps_only_current_copies(
    running: Libraries, alice: Account, units: sessionmaker[Session], tmp_path: Path
) -> None:
    _scanned(running, alice, LibraryKind.ZIP, _old_mixes(tmp_path))
    track_id, _ = _sources(units)["deflated.wav"]
    first = running.playback.play(alice, track_id)
    assert isinstance(first, Preparing)
    running.wait_for(first.job.id, JobState.SUCCEEDED)
    cache = tmp_path / "data" / "cache" / "sources"
    [current] = cache.iterdir()
    (cache / "999-0000000000000000.wav").write_bytes(b"a Source that is gone")

    running.playback.sweep_cache()

    assert list(cache.iterdir()) == [current]


# The liar plugin locates each file where its name says; see tests.support.plugins.liar.


@pytest.fixture
def liar(
    units: sessionmaker[Session],
    clock: FakeClock,
    tmp_path: Path,
    jobs: JobService,
    downloads: DownloadService,
) -> Iterator[PlaybackService]:
    data_dir = tmp_path / "data"
    with started_plugins(units, clock, "liar") as plugins:
        yield PlaybackService(
            units, plugins, jobs, cache_source_kind(data_dir), data_dir, downloads
        )


def _lied_about(
    units: sessionmaker[Session], clock: FakeClock, kind: LibraryKind, root: Path, path: str
) -> SourceId:
    """Register a Library at `root` and a Source for `path` in it, as a scan would."""
    with units.begin() as db:
        library = LibraryRow(
            name="Music",
            kind=kind,
            path=str(root),
            state="online",
            message="",
            file_count=1,
            added_at=clock(),
        )
        track = TrackRow(title=path, added_at=clock())
        db.add_all([library, track])
        db.flush()
        source = SourceRow(
            track_id=track.id, kind="library", locator=library_locator(LibraryId(library.id), path)
        )
        db.add(source)
        db.flush()
        return SourceId(source.id)


def _music(tmp_path: Path) -> Path:
    """A folder holding `a.wav`, next to `outside.wav`, which is outside it."""
    (tmp_path / "outside.wav").write_bytes(b"not in the Library")
    return folder_of(tmp_path / "Music", {"a.wav": Song("A")})


@pytest.mark.parametrize("path", ["outside.wav", "the-root.wav"])
def test_a_folder_location_outside_the_library_is_refused(
    liar: PlaybackService, units: sessionmaker[Session], clock: FakeClock, tmp_path: Path, path: str
) -> None:
    source_id = _lied_about(units, clock, LibraryKind.FOLDER, _music(tmp_path), path)

    with pytest.raises(PluginCallError, match="is outside its Library"):
        liar.open_audio(source_id)


def test_a_link_out_of_the_library_is_refused(
    liar: PlaybackService, units: sessionmaker[Session], clock: FakeClock, tmp_path: Path
) -> None:
    root = _music(tmp_path)
    (root / "link.wav").symlink_to(tmp_path / "outside.wav")
    source_id = _lied_about(units, clock, LibraryKind.FOLDER, root, "link.wav")

    with pytest.raises(PluginCallError, match="is outside its Library"):
        liar.open_audio(source_id)


def test_a_fifo_is_refused_without_waiting_for_a_writer(
    liar: PlaybackService, units: sessionmaker[Session], clock: FakeClock, tmp_path: Path
) -> None:
    root = _music(tmp_path)
    os.mkfifo(root / "fifo.wav")
    source_id = _lied_about(units, clock, LibraryKind.FOLDER, root, "fifo.wav")

    with pytest.raises(PluginCallError, match="isn't a regular file"):
        liar.open_audio(source_id)


def test_a_zip_location_past_the_end_of_the_archive_is_refused(
    liar: PlaybackService, units: sessionmaker[Session], clock: FakeClock, tmp_path: Path
) -> None:
    source_id = _lied_about(units, clock, LibraryKind.ZIP, _old_mixes(tmp_path), "past-the-end.wav")

    with pytest.raises(PluginCallError, match="shorter than the slice"):
        liar.open_audio(source_id)


def test_a_zip_location_outside_the_archive_is_refused(
    liar: PlaybackService, units: sessionmaker[Session], clock: FakeClock, tmp_path: Path
) -> None:
    (tmp_path / "outside.wav").write_bytes(b"not in the archive")
    source_id = _lied_about(units, clock, LibraryKind.ZIP, _old_mixes(tmp_path), "outside.wav")

    with pytest.raises(PluginCallError, match="is outside its Library"):
        liar.open_audio(source_id)


def test_a_refused_location_leaves_the_track_unavailable(
    liar: PlaybackService,
    units: sessionmaker[Session],
    clock: FakeClock,
    tmp_path: Path,
    alice: Account,
) -> None:
    source_id = _lied_about(units, clock, LibraryKind.FOLDER, _music(tmp_path), "outside.wav")
    with units() as db:
        row = db.get(SourceRow, source_id)
        assert row is not None
        track_id = TrackId(row.track_id)

    assert liar.play(alice, track_id) == Unplayable(Availability.UNAVAILABLE)


def test_a_file_deleted_after_it_was_located_is_missing(
    liar: PlaybackService, units: sessionmaker[Session], clock: FakeClock, tmp_path: Path
) -> None:
    source_id = _lied_about(units, clock, LibraryKind.FOLDER, _music(tmp_path), "absent.wav")

    with pytest.raises(NotFoundError, match="it is missing"):
        liar.open_audio(source_id)


def test_a_file_that_cant_be_opened_is_refused(
    liar: PlaybackService, units: sessionmaker[Session], clock: FakeClock, tmp_path: Path
) -> None:
    root = _music(tmp_path)
    (root / "a.wav").chmod(0)
    source_id = _lied_about(units, clock, LibraryKind.FOLDER, root, "a.wav")

    with pytest.raises(PluginCallError, match="can't be opened"):
        liar.open_audio(source_id)


def test_a_damaged_cache_copy_is_prepared_again(
    running: Libraries, alice: Account, units: sessionmaker[Session], tmp_path: Path
) -> None:
    _scanned(running, alice, LibraryKind.ZIP, _old_mixes(tmp_path))
    track_id, source_id = _sources(units)["deflated.wav"]
    first = running.playback.play(alice, track_id)
    assert isinstance(first, Preparing)
    running.wait_for(first.job.id, JobState.SUCCEEDED)
    [copy] = (tmp_path / "data" / "cache" / "sources").iterdir()
    copy.write_bytes(b"cut short")

    again = running.playback.play(alice, track_id)
    assert isinstance(again, Preparing)
    running.wait_for(again.job.id, JobState.SUCCEEDED)

    assert _read(running.playback.open_audio(source_id)) == wav_bytes(Song("Deflated"))


def test_a_source_no_plugin_plays_yet_is_unavailable(running: Libraries, alice: Account) -> None:
    track_id = running.catalog.add_track(SourceKeyFactory.bilibili(), TrackDetailsFactory.song())

    assert running.playback.play(alice, track_id) == Unplayable(Availability.UNAVAILABLE)


def test_closing_audio_twice_is_harmless(
    running: Libraries, alice: Account, units: sessionmaker[Session], tmp_path: Path
) -> None:
    _scanned(running, alice, LibraryKind.FOLDER, folder_of(tmp_path / "M", {"a.wav": Song("A")}))
    audio = running.playback.open_audio(_sources(units)["a.wav"][1])
    audio.close()

    audio.close()
