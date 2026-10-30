"""Registering, scanning, and removing Libraries, through the real plugins and Job processes."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application.accounts import AccountService
from medleyplay.application.libraries import READER_VERSION
from medleyplay.application.segments import SongsService
from medleyplay.domain import video_text
from medleyplay.domain.accounts import Account
from medleyplay.domain.errors import ForbiddenError, InvalidInputError
from medleyplay.domain.jobs import JobState
from medleyplay.domain.libraries import LibraryKind, LibraryState
from medleyplay.domain.segments import SongRow
from medleyplay.persistence.schema import SegmentRow, SourceRow
from tests.support.audio import Song, folder_of, zip_of
from tests.support.factories import NewAccountFactory
from tests.support.fakes import FakeClock
from tests.support.libraries import Libraries, running_libraries


@pytest.fixture
def household(accounts: AccountService) -> tuple[Account, Account]:
    """Return Alice, the admin, and Bob, a member."""
    alice = accounts.create_first_admin(NewAccountFactory.admin()).account
    return alice, accounts.create_account(alice, NewAccountFactory.member())


@pytest.fixture
def libraries(
    units: sessionmaker[Session], clock: FakeClock, tmp_path: Path
) -> Iterator[Libraries]:
    with running_libraries(units, clock, tmp_path / "data") as running:
        yield running


def _music(tmp_path: Path) -> Path:
    """A folder holding two songs in `Blue/` and a text file."""
    return folder_of(
        tmp_path / "Music",
        {
            "Blue/01 Intro.wav": Song("Intro"),
            "Blue/02 Outro.wav": Song("Outro"),
            "notes.txt": Song(),
        },
    )


def _titles(libraries: Libraries, account: Account) -> list[str]:
    return sorted(track.details.title for track in libraries.catalog.list_tracks(account.id))


def test_registering_a_folder_scans_its_songs_into_the_catalog(
    libraries: Libraries, household: tuple[Account, Account], tmp_path: Path
) -> None:
    alice, _ = household

    registered = libraries.service.register(
        alice, "Music", LibraryKind.FOLDER, str(_music(tmp_path))
    )
    assert registered.scan is not None
    libraries.wait_for(registered.scan.id, JobState.SUCCEEDED)
    [library] = libraries.service.list_libraries()

    assert registered.created
    assert _titles(libraries, alice) == ["Intro", "Outro"]
    assert (library.state, library.file_count) == (LibraryState.ONLINE, 2)


def test_a_zip_archive_scans_its_stored_and_compressed_members(
    libraries: Libraries, household: tuple[Account, Account], tmp_path: Path
) -> None:
    alice, _ = household
    archive = zip_of(
        tmp_path / "Old.zip",
        {"x/stored.wav": Song("Stored"), "x/deflated.wav": Song("Deflated")},
        compressed=frozenset({"x/deflated.wav"}),
    )

    registered = libraries.service.register(alice, "Old", LibraryKind.ZIP, str(archive))
    assert registered.scan is not None
    libraries.wait_for(registered.scan.id, JobState.SUCCEEDED)

    assert _titles(libraries, alice) == ["Deflated", "Stored"]


def test_registering_a_root_again_returns_its_library_without_another_scan(
    libraries: Libraries, household: tuple[Account, Account], tmp_path: Path
) -> None:
    alice, _ = household
    music = _music(tmp_path)
    first = libraries.service.register(alice, "Music", LibraryKind.FOLDER, str(music))

    again = libraries.service.register(alice, "Other name", LibraryKind.FOLDER, f"{music}/Blue/..")

    assert (again.created, again.scan, again.library) == (False, None, first.library)


def test_a_root_that_cant_be_read_is_refused(
    libraries: Libraries, household: tuple[Account, Account], tmp_path: Path
) -> None:
    alice, _ = household

    with pytest.raises(InvalidInputError, match="isn't a folder"):
        libraries.service.register(alice, "Music", LibraryKind.FOLDER, str(tmp_path / "absent"))


def test_the_data_folder_cant_be_a_library(
    libraries: Libraries, household: tuple[Account, Account], tmp_path: Path
) -> None:
    alice, _ = household

    with pytest.raises(InvalidInputError, match="data folder"):
        libraries.service.register(alice, "Me", LibraryKind.FOLDER, str(tmp_path / "data" / "jobs"))


def test_only_an_admin_manages_libraries(
    libraries: Libraries, household: tuple[Account, Account], tmp_path: Path
) -> None:
    _, bob = household

    with pytest.raises(ForbiddenError):
        libraries.service.register(bob, "Music", LibraryKind.FOLDER, str(_music(tmp_path)))


def test_a_rescan_finds_new_and_changed_files_and_skips_the_rest(
    libraries: Libraries, household: tuple[Account, Account], tmp_path: Path
) -> None:
    alice, _ = household
    music = _music(tmp_path)
    registered = libraries.service.register(alice, "Music", LibraryKind.FOLDER, str(music))
    assert registered.scan is not None
    libraries.wait_for(registered.scan.id, JobState.SUCCEEDED)
    folder_of(
        music, {"Blue/02 Outro.wav": Song("Outro, remastered"), "03 Bonus.wav": Song("Bonus")}
    )
    os.utime(music / "Blue" / "02 Outro.wav", ns=(1, 1))

    rescan = libraries.service.scan(alice, registered.library.id)
    libraries.wait_for(rescan.id, JobState.SUCCEEDED)

    assert _titles(libraries, alice) == ["Bonus", "Intro", "Outro, remastered"]


def test_a_full_rescan_reads_files_that_look_unchanged(
    libraries: Libraries, household: tuple[Account, Account], tmp_path: Path
) -> None:
    alice, _ = household
    music = _music(tmp_path)
    registered = libraries.service.register(alice, "Music", LibraryKind.FOLDER, str(music))
    assert registered.scan is not None
    libraries.wait_for(registered.scan.id, JobState.SUCCEEDED)
    intro = music / "Blue" / "01 Intro.wav"
    stat = intro.stat()  # "Intra" has as many letters as "Intro", so the size stays
    folder_of(music, {"Blue/01 Intro.wav": Song("Intra")})
    os.utime(intro, ns=(stat.st_atime_ns, stat.st_mtime_ns))

    quick = libraries.service.scan(alice, registered.library.id)
    libraries.wait_for(quick.id, JobState.SUCCEEDED)
    after_quick = _titles(libraries, alice)
    full = libraries.service.scan(alice, registered.library.id, full=True)
    libraries.wait_for(full.id, JobState.SUCCEEDED)

    assert after_quick == ["Intro", "Outro"]
    assert _titles(libraries, alice) == ["Intra", "Outro"]


def test_a_rescan_reads_again_the_files_an_older_medleyplay_read(
    libraries: Libraries,
    household: tuple[Account, Account],
    tmp_path: Path,
    units: sessionmaker[Session],
) -> None:
    alice, _ = household
    music = _music(tmp_path)
    registered = libraries.service.register(alice, "Music", LibraryKind.FOLDER, str(music))
    assert registered.scan is not None
    libraries.wait_for(registered.scan.id, JobState.SUCCEEDED)
    intro = music / "Blue" / "01 Intro.wav"
    stat = intro.stat()  # "Intra" has as many letters as "Intro", so the size stays
    folder_of(music, {"Blue/01 Intro.wav": Song("Intra")})
    os.utime(intro, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    with units.begin() as db:
        for source in db.scalars(select(SourceRow)):
            # What a medleyplay whose tag reader read less wrote for each file.
            source.details = {**(source.details or {}), "reader": READER_VERSION - 1}

    rescan = libraries.service.scan(alice, registered.library.id)
    libraries.wait_for(rescan.id, JobState.SUCCEEDED)

    assert _titles(libraries, alice) == ["Intra", "Outro"]


def test_removing_a_library_removes_its_tracks(
    libraries: Libraries, household: tuple[Account, Account], tmp_path: Path
) -> None:
    alice, _ = household
    registered = libraries.service.register(
        alice, "Music", LibraryKind.FOLDER, str(_music(tmp_path))
    )
    assert registered.scan is not None
    libraries.wait_for(registered.scan.id, JobState.SUCCEEDED)

    libraries.service.remove(alice, registered.library.id)
    libraries.service.remove(alice, registered.library.id)

    assert libraries.service.list_libraries() == []
    assert _titles(libraries, alice) == []


_TWO_SONGS = (
    SongRow(None, video_text.Song(0, "アイネクライネ")),
    SongRow(None, video_text.Song(2_000, "Last")),
)
"""A split of a five-second file into songs at 0 s and 2 s."""


def test_removing_a_library_removes_the_songs_split_from_its_files(
    libraries: Libraries,
    songs: SongsService,
    household: tuple[Account, Account],
    tmp_path: Path,
    units: sessionmaker[Session],
) -> None:
    alice, _ = household
    music = folder_of(tmp_path / "Music", {"Bremen.wav": Song("Bremen", seconds=5.0)})
    registered = libraries.service.register(alice, "Music", LibraryKind.FOLDER, str(music))
    assert registered.scan is not None
    libraries.wait_for(registered.scan.id, JobState.SUCCEEDED)
    (album,) = libraries.catalog.list_tracks(alice.id)
    songs.save(album.id, _TWO_SONGS)

    libraries.service.remove(alice, registered.library.id)

    assert _titles(libraries, alice) == []
    with units() as db:
        assert db.scalars(select(SegmentRow.id)).all() == []
        assert db.scalars(select(SourceRow.id)).all() == []


def test_an_album_files_source_cant_go_while_its_songs_remain(
    libraries: Libraries,
    songs: SongsService,
    household: tuple[Account, Account],
    tmp_path: Path,
    units: sessionmaker[Session],
) -> None:
    alice, _ = household
    music = folder_of(tmp_path / "Music", {"Bremen.wav": Song("Bremen", seconds=5.0)})
    registered = libraries.service.register(alice, "Music", LibraryKind.FOLDER, str(music))
    assert registered.scan is not None
    libraries.wait_for(registered.scan.id, JobState.SUCCEEDED)
    (album,) = libraries.catalog.list_tracks(alice.id)
    songs.save(album.id, _TWO_SONGS)

    with pytest.raises(IntegrityError), units.begin() as db:
        db.execute(delete(SourceRow).where(SourceRow.track_id == album.id))


def test_a_rescan_of_a_split_file_whose_length_changed_reaches_its_last_song(
    libraries: Libraries, songs: SongsService, household: tuple[Account, Account], tmp_path: Path
) -> None:
    alice, _ = household
    music = folder_of(tmp_path / "Music", {"Bremen.wav": Song("Bremen", seconds=5.0)})
    registered = libraries.service.register(alice, "Music", LibraryKind.FOLDER, str(music))
    assert registered.scan is not None
    libraries.wait_for(registered.scan.id, JobState.SUCCEEDED)
    (album,) = libraries.catalog.list_tracks(alice.id)
    last = songs.save(album.id, _TWO_SONGS).songs[1]
    folder_of(music, {"Bremen.wav": Song("Bremen", seconds=8.0)})

    libraries.wait_for(libraries.service.scan(alice, registered.library.id).id, JobState.SUCCEEDED)

    assert libraries.catalog.get_track(alice.id, last.track_id).details.duration_ms == 6_000
    assert songs.songs(album.id).needs_check


def test_removing_a_library_cancels_its_scan(
    libraries: Libraries, household: tuple[Account, Account], tmp_path: Path
) -> None:
    alice, _ = household
    registered = libraries.service.register(
        alice, "Music", LibraryKind.FOLDER, str(_music(tmp_path))
    )
    assert registered.scan is not None

    libraries.service.remove(alice, registered.library.id)
    scan = libraries.jobs.get_job(registered.scan.id).job

    assert scan.state in {JobState.CANCELLED, JobState.SUCCEEDED}
    assert _titles(libraries, alice) == []


def test_a_library_whose_folder_disappears_goes_offline_and_keeps_its_tracks(
    libraries: Libraries, household: tuple[Account, Account], tmp_path: Path
) -> None:
    alice, _ = household
    music = _music(tmp_path)
    registered = libraries.service.register(alice, "Music", LibraryKind.FOLDER, str(music))
    assert registered.scan is not None
    libraries.wait_for(registered.scan.id, JobState.SUCCEEDED)
    music.rename(tmp_path / "Unplugged")

    rescan = libraries.service.scan(alice, registered.library.id)
    libraries.wait_for(rescan.id, JobState.SUCCEEDED)
    [library] = libraries.service.list_libraries()

    assert (library.state, library.message) == (LibraryState.OFFLINE, f"{music} isn't a folder.")
    assert _titles(libraries, alice) == ["Intro", "Outro"]
