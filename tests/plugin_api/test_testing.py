"""The contract kit catches providers that break their extension point's contract."""

import math
from pathlib import Path

import pytest
from pydantic import BaseModel, field_serializer

from medleyplay.plugin_api import (
    CheckRoot,
    ExtensionPoint,
    FetchedFile,
    FetchFile,
    FileList,
    FileLocation,
    FileRequest,
    LibraryRoot,
    ListFiles,
    ReadTags,
    RootCheck,
    Tags,
)
from medleyplay.plugin_api.testing import (
    ContractError,
    check_library_backend,
    check_operation,
    check_round_trip,
    check_tag_reader,
)
from medleyplay.plugins.fsspec_library.backends import FolderBackend
from tests.support.audio import Song, folder_of
from tests.support.echo import SAY, Parrot, Said, Say


class Measured(BaseModel):
    value: float


class Rounded(BaseModel):
    """A model whose serializer rounds, so it can't come back as it was."""

    value: float

    @field_serializer("value")
    def _rounded(self, value: float) -> float:
        return float(round(value + 0.1))


class Gauge:
    def __init__(self, value: float) -> None:
        self._value = value

    def read(self, request: Say) -> Measured:
        return Measured(value=self._value)


GAUGE = ExtensionPoint[Gauge]("gauge")
READ = GAUGE.operation("read", Say, Measured, lambda gauge: gauge.read)


def test_a_well_behaved_provider_passes_and_its_reply_is_returned() -> None:
    assert check_operation(SAY, Parrot(), Say(text="hi")) == Said(text="hi")


def test_a_provider_whose_reply_changes_between_calls_fails() -> None:
    with pytest.raises(ContractError, match="Calling twice gave different replies"):
        check_operation(SAY, Parrot(), Say(text="hi", count_calls=True))


def test_a_reply_that_does_not_survive_a_json_round_trip_fails() -> None:
    with pytest.raises(ContractError, match="doesn't survive a JSON round trip"):
        check_operation(READ, Gauge(math.nan), Say(text="read"))


def test_a_model_that_survives_a_round_trip_passes() -> None:
    check_round_trip(Measured(value=1.5))


def test_a_model_that_changes_in_a_round_trip_fails() -> None:
    with pytest.raises(ContractError, match=r"became Rounded\(value=2\.0\) in a JSON round trip"):
        check_round_trip(Rounded(value=1.5))


def _library(tmp_path: Path) -> LibraryRoot:
    """A folder holding `a.wav`."""
    return LibraryRoot(kind="folder", path=str(folder_of(tmp_path / "Music", {"a.wav": Song()})))


class _Unreadable(FolderBackend):
    def check(self, request: CheckRoot) -> RootCheck:
        return RootCheck(readable=False, message="unplugged")


class _ListsEverything(FolderBackend):
    def list_files(self, request: ListFiles) -> FileList:
        return super().list_files(
            request.model_copy(update={"extensions": frozenset({"wav", "txt"})})
        )


class _LocatesPastTheEnd(FolderBackend):
    def locate(self, request: FileRequest) -> FileLocation:
        return super().locate(request).model_copy(update={"offset": 10})


class _FetchesElsewhere(FolderBackend):
    def locate(self, request: FileRequest) -> FileLocation:
        return FileLocation(local_path=None, length=1, compressed=True)

    def fetch(self, request: FetchFile) -> FetchedFile:
        return FetchedFile(local_path=str(Path(request.root.path) / request.path))


class _LosesListedFiles(FolderBackend):
    def locate(self, request: FileRequest) -> FileLocation:
        return FileLocation(local_path=None, length=0, missing=True)


class _FindsUnlistedFiles(FolderBackend):
    """A backend that answers any file it doesn't have with the location of `a.wav`."""

    def locate(self, request: FileRequest) -> FileLocation:
        found = super().locate(request)
        if found.missing:
            return super().locate(request.model_copy(update={"path": "a.wav"}))
        return found


class _LocatesAnything(FolderBackend):
    """A backend that locates a path leading out of its root instead of refusing it."""

    def locate(self, request: FileRequest) -> FileLocation:
        if request.path.startswith("../"):
            return FileLocation(local_path=request.path, length=0)
        return super().locate(request)


@pytest.mark.parametrize(
    ("backend", "message"),
    [
        (_Unreadable(), "can't read"),
        (_LocatesPastTheEnd(), "runs past the end"),
        (_FetchesElsewhere(), "was fetched outside"),
        (_LosesListedFiles(), "was located as missing"),
        (_FindsUnlistedFiles(), "wasn't located as missing"),
        (_LocatesAnything(), "located a path outside its root"),
    ],
)
def test_the_library_kit_catches_a_backend_that_breaks_the_contract(
    tmp_path: Path, backend: FolderBackend, message: str
) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    with pytest.raises(ContractError, match=message):
        check_library_backend(backend, _library(tmp_path), frozenset({"wav"}), scratch)


def test_the_library_kit_catches_a_file_with_an_extension_not_asked_for(tmp_path: Path) -> None:
    root = _library(tmp_path)
    (Path(root.path) / "notes.txt").write_text("hi")

    with pytest.raises(ContractError, match="doesn't have a requested extension"):
        check_library_backend(_ListsEverything(), root, frozenset({"wav"}), tmp_path)


class _NegativeReader:
    def read_tags(self, request: ReadTags) -> Tags:
        return Tags(duration_ms=-1)


def test_the_tag_kit_catches_a_negative_duration(tmp_path: Path) -> None:
    with pytest.raises(ContractError, match="A negative duration"):
        check_tag_reader(_NegativeReader(), ReadTags(local_path=str(tmp_path)))
