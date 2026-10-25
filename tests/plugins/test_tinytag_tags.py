"""The tinytag tag reader: tags from whole files and zip members, and what it can't read."""

from pathlib import Path

from medleyplay.plugin_api import FileRequest, LibraryRoot, ReadTags, Tags
from medleyplay.plugin_api.testing import check_tag_reader
from medleyplay.plugins.fsspec_library.backends import ZipBackend
from medleyplay.plugins.tinytag_tags import TinytagReader, register
from tests.support.audio import Song, folder_of, zip_of


def test_the_reader_keeps_the_contract_and_reads_the_tags(tmp_path: Path) -> None:
    folder_of(tmp_path, {"intro.wav": Song("Intro", "The Band", "Blue", seconds=2)})

    tags = check_tag_reader(TinytagReader(), ReadTags(local_path=str(tmp_path / "intro.wav")))

    assert tags == Tags(title="Intro", artist="The Band", album="Blue", duration_ms=2000)


def test_a_stored_zip_member_is_read_in_place(tmp_path: Path) -> None:
    archive = zip_of(tmp_path / "a.zip", {"x/one.wav": Song("One")})
    location = ZipBackend().locate(
        FileRequest(root=LibraryRoot(kind="zip", path=str(archive)), path="x/one.wav")
    )

    tags = TinytagReader().read_tags(
        ReadTags(local_path=str(archive), offset=location.offset, length=location.length)
    )

    assert tags.title == "One"


def test_a_file_tinytag_cant_parse_has_no_tags(tmp_path: Path) -> None:
    broken = tmp_path / "broken.mp3"
    broken.write_bytes(b"not audio at all")

    assert TinytagReader().read_tags(ReadTags(local_path=str(broken))) == Tags()


def test_a_protected_reader_marks_what_it_reads_protected(tmp_path: Path) -> None:
    broken = tmp_path / "song.m4p"
    broken.write_bytes(b"locked")

    assert TinytagReader(protected=True).read_tags(ReadTags(local_path=str(broken))).protected


class _Recorder:
    """Records what a plugin registers, in place of the registry."""

    def __init__(self) -> None:
        self.readers: dict[str, TinytagReader] = {}

    def add(self, point: object, key: str, provider: TinytagReader) -> None:
        self.readers[key] = provider


def test_the_plugin_reads_audio_extensions_and_marks_only_m4p_protected(tmp_path: Path) -> None:
    registry = _Recorder()
    unreadable = tmp_path / "unreadable"
    unreadable.write_bytes(b"x")

    register(registry)  # type: ignore[arg-type] # a recorder in place of the registry
    protected = [
        key
        for key, reader in registry.readers.items()
        if reader.read_tags(ReadTags(local_path=str(unreadable))).protected
    ]

    assert {"mp3", "flac", "m4a", "wav", "m4p"} <= set(registry.readers)
    assert "m4v" not in registry.readers
    assert protected == ["m4p"]
