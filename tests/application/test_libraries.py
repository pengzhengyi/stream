"""Registering, scanning, and removing Libraries, through the real plugins and Job processes."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application.accounts import AccountService
from medleyplay.domain.accounts import Account
from medleyplay.domain.errors import ForbiddenError, InvalidInputError
from medleyplay.domain.jobs import JobState
from medleyplay.domain.libraries import LibraryKind, LibraryState
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
