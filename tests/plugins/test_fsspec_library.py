"""The `folder` and `zip` backends, checked by the contract kit and case by case."""

import os
import zipfile
from pathlib import Path

import pytest

from medleyplay.plugin_api import (
    CheckRoot,
    FetchFile,
    FileRequest,
    LibraryRoot,
    ListFiles,
)
from medleyplay.plugin_api.testing import check_library_backend
from medleyplay.plugins.fsspec_library.backends import FolderBackend, ZipBackend
from tests.support.audio import Song, folder_of, mark_encrypted, wav_bytes, zip_of

AUDIO = frozenset({"wav", "mp3"})


def _folder(tmp_path: Path) -> LibraryRoot:
    """A folder holding `Blue/01 Intro.wav`, `02 Outro.WAV`, and `notes.txt`."""
    root = folder_of(
        tmp_path / "Music",
        {"Blue/01 Intro.wav": Song("Intro"), "02 Outro.WAV": Song("Outro"), "notes.txt": Song()},
    )
    return LibraryRoot(kind="folder", path=str(root))


def _zip(tmp_path: Path) -> LibraryRoot:
    """An archive holding `x/stored.wav`, stored, and `x/deflated.wav`, compressed."""
    archive = zip_of(
        tmp_path / "Old.zip",
        {"x/stored.wav": Song("Stored"), "x/deflated.wav": Song("Deflated")},
        compressed=frozenset({"x/deflated.wav"}),
    )
    return LibraryRoot(kind="zip", path=str(archive))


def test_the_folder_backend_keeps_the_contract(tmp_path: Path) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    listing = check_library_backend(FolderBackend(), _folder(tmp_path), AUDIO, scratch)

    assert [file.path for file in listing.files] == ["02 Outro.WAV", "Blue/01 Intro.wav"]


def test_the_zip_backend_keeps_the_contract(tmp_path: Path) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    listing = check_library_backend(ZipBackend(), _zip(tmp_path), AUDIO, scratch)

    assert [file.path for file in listing.files] == ["x/deflated.wav", "x/stored.wav"]


def test_a_folder_file_is_located_whole(tmp_path: Path) -> None:
    root = _folder(tmp_path)

    location = FolderBackend().locate(FileRequest(root=root, path="Blue/01 Intro.wav"))

    assert location.local_path == str(Path(root.path) / "Blue" / "01 Intro.wav")
    assert (location.offset, location.length) == (0, len(wav_bytes(Song("Intro"))))


def test_a_stored_zip_member_is_located_inside_the_archive(tmp_path: Path) -> None:
    root = _zip(tmp_path)

    location = ZipBackend().locate(FileRequest(root=root, path="x/stored.wav"))

    assert location.local_path == root.path
    with Path(root.path).open("rb") as archive:
        archive.seek(location.offset)
        assert archive.read(location.length) == wav_bytes(Song("Stored"))


def test_a_compressed_zip_member_has_no_location_and_is_fetched(tmp_path: Path) -> None:
    root = _zip(tmp_path)
    request = FileRequest(root=root, path="x/deflated.wav")

    location = ZipBackend().locate(request)
    fetched = ZipBackend().fetch(FetchFile(root=root, path="x/deflated.wav", folder=str(tmp_path)))

    assert (location.local_path, location.compressed) == (None, True)
    assert Path(fetched.local_path).read_bytes() == wav_bytes(Song("Deflated"))


def test_zip_members_take_the_archives_modification_time(tmp_path: Path) -> None:
    root = _zip(tmp_path)

    listing = ZipBackend().list_files(ListFiles(root=root, extensions=AUDIO))

    assert {file.modified_ns for file in listing.files} == {Path(root.path).stat().st_mtime_ns}


def test_a_symbolic_link_in_a_folder_is_left_out(tmp_path: Path) -> None:
    root = _folder(tmp_path)
    outside = folder_of(tmp_path / "Elsewhere", {"secret.wav": Song()})
    (Path(root.path) / "link.wav").symlink_to(outside / "secret.wav")
    (Path(root.path) / "loop").symlink_to(root.path)

    listing = FolderBackend().list_files(ListFiles(root=root, extensions=AUDIO))

    assert "link.wav" not in [file.path for file in listing.files]
    assert not any(file.path.startswith("loop/") for file in listing.files)


@pytest.mark.parametrize("path", ["../Elsewhere/secret.wav", "link.wav"])
def test_a_folder_path_that_leads_outside_the_root_is_refused(tmp_path: Path, path: str) -> None:
    root = _folder(tmp_path)
    outside = folder_of(tmp_path / "Elsewhere", {"secret.wav": Song()})
    (Path(root.path) / "link.wav").symlink_to(outside / "secret.wav")

    with pytest.raises((ValueError, FileNotFoundError)):
        FolderBackend().locate(FileRequest.model_construct(root=root, path=path))


def test_zip_members_named_outside_the_archive_or_encrypted_are_left_out(tmp_path: Path) -> None:
    archive = tmp_path / "odd.zip"
    with zipfile.ZipFile(archive, "w") as zip_file:
        zip_file.writestr("../escape.wav", wav_bytes(Song()))
        zip_file.writestr("locked.wav", wav_bytes(Song()))
        zip_file.writestr("fine.wav", wav_bytes(Song()))
    mark_encrypted(archive, "locked.wav")
    root = LibraryRoot(kind="zip", path=str(archive))

    listing = ZipBackend().list_files(ListFiles(root=root, extensions=AUDIO))

    assert [file.path for file in listing.files] == ["fine.wav"]


@pytest.mark.parametrize(
    ("backend", "make", "message"),
    [
        (FolderBackend(), lambda p: p / "absent", "isn't a folder"),
        (ZipBackend(), lambda p: p / "absent.zip", "isn't a file"),
        (ZipBackend(), lambda p: folder_of(p, {"a.zip": Song()}) / "a.zip", "isn't a zip archive"),
    ],
)
def test_a_root_that_cant_be_read_says_why(
    tmp_path: Path, backend: FolderBackend | ZipBackend, make: object, message: str
) -> None:
    path = make(tmp_path)  # type: ignore[operator] # each case's maker
    kind = "folder" if isinstance(backend, FolderBackend) else "zip"

    check = backend.check(CheckRoot(root=LibraryRoot(kind=kind, path=str(path))))

    assert not check.readable
    assert message in check.message


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads every folder")
def test_a_folder_without_read_permission_cant_be_read(tmp_path: Path) -> None:
    root = _folder(tmp_path)
    Path(root.path).chmod(0o000)
    try:
        check = FolderBackend().check(CheckRoot(root=root))
    finally:
        Path(root.path).chmod(0o755)

    assert (check.readable, check.message.endswith("can't be read.")) == (False, True)


def test_a_folder_file_fetches_as_a_copy(tmp_path: Path) -> None:
    root = _folder(tmp_path)
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    fetched = FolderBackend().fetch(
        FetchFile(root=root, path="Blue/01 Intro.wav", folder=str(scratch))
    )

    assert Path(fetched.local_path).read_bytes() == wav_bytes(Song("Intro"))


def test_a_zip_member_that_does_not_exist_is_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="isn't a member"):
        ZipBackend().locate(FileRequest(root=_zip(tmp_path), path="x/absent.wav"))


def test_a_stored_member_with_a_damaged_header_is_refused(tmp_path: Path) -> None:
    root = _zip(tmp_path)
    data = bytearray(Path(root.path).read_bytes())
    data[0:4] = b"XXXX"
    Path(root.path).write_bytes(bytes(data))

    with pytest.raises(ValueError, match="damaged header"):
        ZipBackend().locate(FileRequest(root=root, path="x/stored.wav"))
