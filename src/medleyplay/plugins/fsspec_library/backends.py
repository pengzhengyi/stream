"""The `folder` and `zip` backends: listing, locating, fingerprinting, and fetching files."""

import hashlib
import os
import shutil
import struct
import zipfile
from pathlib import Path, PurePosixPath
from typing import Final

from medleyplay.plugin_api import (
    CheckRoot,
    FetchedFile,
    FetchFile,
    FileFingerprint,
    FileList,
    FileLocation,
    FileRequest,
    LibraryFile,
    ListFiles,
    RootCheck,
    check_library_path,
)
from medleyplay.plugins.fsspec_library._fsspec import find_files

EDGE: Final = 64 * 1024
MISSING: Final = FileLocation(local_path=None, length=0, missing=True)
# A zip member's data starts after a 30-byte local header, its name, and an extra field.
_LOCAL_HEADER: Final = struct.Struct("<4s22xHH")
_LOCAL_HEADER_SIGNATURE: Final = b"PK\x03\x04"


def _extension(path: str) -> str:
    return PurePosixPath(path).suffix.lower().removeprefix(".")


def _fingerprint(size: int, first: bytes, last: bytes) -> FileFingerprint:
    digest = hashlib.sha256(first + last).hexdigest()
    return FileFingerprint(value=f"{size}:{digest}")


class FolderBackend:
    """Files in a folder on this machine."""

    def check(self, request: CheckRoot) -> RootCheck:
        """Say whether the folder exists and can be read."""
        root = Path(request.root.path)
        if not root.is_dir():
            return RootCheck(readable=False, message=f"{root} isn't a folder.")
        if not os.access(root, os.R_OK | os.X_OK):
            return RootCheck(readable=False, message=f"{root} can't be read.")
        return RootCheck(readable=True)

    def list_files(self, request: ListFiles) -> FileList:
        """List the folder's files with the requested extensions, in path order."""
        root = Path(request.root.path).resolve()
        files = []
        for entry in find_files("file", str(root)):
            path = Path(entry.name).relative_to(root).as_posix()
            if _extension(path) in request.extensions:
                stat = Path(entry.name).stat()
                files.append(
                    LibraryFile(path=path, size=stat.st_size, modified_ns=stat.st_mtime_ns)
                )
        return FileList(files=tuple(files))

    def locate(self, request: FileRequest) -> FileLocation:
        """Return the file's path; its bytes are the whole file."""
        try:
            path = self._inside(request)
            return FileLocation(local_path=str(path), length=path.stat().st_size)
        except OSError:
            return MISSING

    def fingerprint(self, request: FileRequest) -> FileFingerprint:
        """Return the file's size and a hash of its first and last 64 KB."""
        path = self._inside(request)
        size = path.stat().st_size
        with path.open("rb") as file:
            first = file.read(EDGE)
            file.seek(max(size - EDGE, 0))
            last = file.read(EDGE)
        return _fingerprint(size, first, last)

    def fetch(self, request: FetchFile) -> FetchedFile:
        """Copy the file into the requested folder."""
        source = self._inside(request)
        destination = Path(request.folder) / source.name
        shutil.copyfile(source, destination)
        return FetchedFile(local_path=str(destination))

    def _inside(self, request: FileRequest | FetchFile) -> Path:
        root = Path(request.root.path).resolve()
        path = (root / check_library_path(request.path)).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            message = f"{request.path!r} isn't a file in {root}."
            raise FileNotFoundError(message)
        return path


class ZipBackend:
    """Members of a zip archive on this machine.

    A member's modification time is the archive's own, since zip times are coarse:
    changing the archive rescans every member.
    """

    def check(self, request: CheckRoot) -> RootCheck:
        """Say whether the archive exists and is a zip archive."""
        archive = Path(request.root.path)
        if not archive.is_file():
            return RootCheck(readable=False, message=f"{archive} isn't a file.")
        if not zipfile.is_zipfile(archive):
            return RootCheck(readable=False, message=f"{archive} isn't a zip archive.")
        return RootCheck(readable=True)

    def list_files(self, request: ListFiles) -> FileList:
        """List the archive's unencrypted members with the requested extensions."""
        archive = Path(request.root.path)
        modified_ns = archive.stat().st_mtime_ns
        with zipfile.ZipFile(archive) as zip_file:
            encrypted = {info.filename for info in zip_file.infolist() if info.flag_bits & 0x1}
        files = []
        for entry in find_files("zip", "", fo=str(archive)):
            if entry.name in encrypted or _extension(entry.name) not in request.extensions:
                continue
            try:
                path = check_library_path(entry.name)
            except ValueError:
                continue  # A member named outside the archive's tree, such as `../x`.
            files.append(LibraryFile(path=path, size=entry.size, modified_ns=modified_ns))
        return FileList(files=tuple(files))

    def locate(self, request: FileRequest) -> FileLocation:
        """Return where a stored member's bytes are; a compressed member must be fetched.

        A member that isn't there, or an archive that can't be read now, perhaps
        because it is being rewritten, is missing.
        """
        archive = Path(request.root.path)
        try:
            with zipfile.ZipFile(archive) as zip_file:
                member = self._member(zip_file, request)
            if member.compress_type != zipfile.ZIP_STORED:
                return FileLocation(local_path=None, length=member.file_size, compressed=True)
            with archive.open("rb") as file:
                file.seek(member.header_offset)
                header = file.read(_LOCAL_HEADER.size)
        except (OSError, zipfile.BadZipFile):
            return MISSING
        if len(header) != _LOCAL_HEADER.size:
            return MISSING
        signature, name_length, extra_length = _LOCAL_HEADER.unpack(header)
        if signature != _LOCAL_HEADER_SIGNATURE:
            return MISSING
        offset = member.header_offset + _LOCAL_HEADER.size + name_length + extra_length
        return FileLocation(local_path=str(archive), offset=offset, length=member.file_size)

    def fingerprint(self, request: FileRequest) -> FileFingerprint:
        """Return the member's size and a hash of its first and last 64 KB."""
        with zipfile.ZipFile(request.root.path) as zip_file:
            member = self._member(zip_file, request)
            with zip_file.open(member) as file:
                first = file.read(EDGE)
                file.seek(max(member.file_size - EDGE, 0))
                last = file.read(EDGE)
        return _fingerprint(member.file_size, first, last)

    def fetch(self, request: FetchFile) -> FetchedFile:
        """Copy the member's uncompressed bytes into the requested folder."""
        destination = Path(request.folder) / PurePosixPath(request.path).name
        with zipfile.ZipFile(request.root.path) as zip_file:
            member = self._member(zip_file, request)
            with zip_file.open(member) as source, destination.open("wb") as target:
                shutil.copyfileobj(source, target)
        return FetchedFile(local_path=str(destination))

    def _member(
        self, zip_file: zipfile.ZipFile, request: FileRequest | FetchFile
    ) -> zipfile.ZipInfo:
        try:
            return zip_file.getinfo(check_library_path(request.path))
        except KeyError:
            message = f"{request.path!r} isn't a member of {request.root.path}."
            raise FileNotFoundError(message) from None
