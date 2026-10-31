"""The scan program: which files it lists, reads, and skips, and how it reads a sidecar."""

from pathlib import Path

import pytest

from medleyplay.plugin_host.job import JobContext
from medleyplay.plugin_host.loader import BUILT_IN_PLUGINS, load_plugins
from medleyplay.programs.info_json import MAX_BYTES, InfoChapter
from medleyplay.programs.scan_library import (
    KnownFile,
    ScanLibrary,
    ScannedFile,
    Stamp,
    run,
)
from tests.support.audio import Song, folder_of, zip_of
from tests.support.info_json import (
    album_with_odd_chapters,
    info_json_beside,
    melt_video,
    world_is_mine_video,
)
from tests.support.libraries import LIBRARY_PLUGINS

MELT_TITLE = "【初音ミク】メルト / ryo(supercell)【MV】"


def _context(tmp_path: Path) -> JobContext:
    work_dir = tmp_path / "work"
    work_dir.mkdir(exist_ok=True)
    endpoints = load_plugins(BUILT_IN_PLUGINS, LIBRARY_PLUGINS, lambda _: None)
    return JobContext(work_dir, endpoints, lambda _: None)


def _scan(
    tmp_path: Path,
    root: Path,
    kind: str = "folder",
    *,
    known: dict[str, KnownFile] | None = None,
    full: bool = False,
) -> dict[str, ScannedFile]:
    """Scan `root` for `.wav` files, and return what was found by path."""
    request = ScanLibrary.model_validate(
        {
            "root": {"kind": kind, "path": str(root)},
            "extensions": ["wav"],
            "known": known or {},
            "full": full,
        }
    )
    scan = run(request, _context(tmp_path))
    assert scan.readable
    return {file.path: file for file in scan.files}


def _known(found: dict[str, ScannedFile]) -> dict[str, KnownFile]:
    """What a catalog keeps of a scan: each file's stamp and its sidecar's."""
    return {
        path: KnownFile(
            size=file.size,
            modified_ns=file.modified_ns,
            info_json=None
            if file.info_json is None
            else Stamp(size=file.info_json.size, modified_ns=file.info_json.modified_ns),
        )
        for path, file in found.items()
    }


def _read_title(file: ScannedFile) -> str | None:
    """The title the scan read from the file's sidecar, or `None` when it read nothing."""
    if file.info_json is None or file.info_json.text is None:
        return None
    return file.info_json.text.title


def test_a_sidecar_beside_its_audio_is_read_and_is_not_a_file_of_its_own(tmp_path: Path) -> None:
    music = folder_of(tmp_path / "Music", {"Blue/a.wav": Song("A")})
    sidecar = info_json_beside(music / "Blue" / "a.wav", melt_video())

    found = _scan(tmp_path, music)

    info = found["Blue/a.wav"].info_json
    assert list(found) == ["Blue/a.wav"]
    assert info is not None
    assert (info.size, info.modified_ns) == (sidecar.stat().st_size, sidecar.stat().st_mtime_ns)
    assert info.error == ""
    assert info.text is not None
    assert (info.text.title, info.text.description) == (MELT_TITLE, "supercell's first single")
    assert info.text.chapters == ()


def test_a_sidecar_named_in_capitals_is_read(tmp_path: Path) -> None:
    music = folder_of(tmp_path / "Music", {"a.wav": Song("A")})
    (music / "a.INFO.JSON").write_text(melt_video(), encoding="utf-8")

    found = _scan(tmp_path, music)

    assert _read_title(found["a.wav"]) == MELT_TITLE


def test_other_json_files_and_a_sidecar_with_no_audio_are_ignored(tmp_path: Path) -> None:
    music = folder_of(tmp_path / "Music", {"a.wav": Song("A"), "Blue/b.wav": Song("B")})
    (music / "settings.json").write_text(melt_video(), encoding="utf-8")
    (music / "a.json").write_text(melt_video(), encoding="utf-8")
    (music / "orphan.info.json").write_text(melt_video(), encoding="utf-8")
    (music / "Blue" / "a.info.json").write_text(melt_video(), encoding="utf-8")

    found = _scan(tmp_path, music)

    assert list(found) == ["Blue/b.wav", "a.wav"]
    assert [file.info_json for file in found.values()] == [None, None]


def test_a_changed_sidecar_is_read_again_while_the_unchanged_audio_is_not(tmp_path: Path) -> None:
    music = folder_of(tmp_path / "Music", {"a.wav": Song("A")})
    info_json_beside(music / "a.wav", melt_video())
    known = _known(_scan(tmp_path, music))

    info_json_beside(music / "a.wav", world_is_mine_video())
    found = _scan(tmp_path, music, known=known)

    assert found["a.wav"].changed is False
    assert found["a.wav"].tags is None
    assert _read_title(found["a.wav"]) == "【初音ミク】ワールドイズマイン / ryo(supercell)【MV】"


def test_an_unchanged_sidecar_is_listed_with_its_stamp_but_not_read(tmp_path: Path) -> None:
    music = folder_of(tmp_path / "Music", {"a.wav": Song("A")})
    sidecar = info_json_beside(music / "a.wav", melt_video())
    known = _known(_scan(tmp_path, music))

    info = _scan(tmp_path, music, known=known)["a.wav"].info_json

    assert info is not None
    assert (info.size, info.modified_ns) == (sidecar.stat().st_size, sidecar.stat().st_mtime_ns)
    assert (info.text, info.error) == (None, "")


def test_a_full_scan_reads_an_unchanged_sidecar(tmp_path: Path) -> None:
    music = folder_of(tmp_path / "Music", {"a.wav": Song("A")})
    info_json_beside(music / "a.wav", melt_video())
    known = _known(_scan(tmp_path, music))

    found = _scan(tmp_path, music, known=known, full=True)

    assert _read_title(found["a.wav"]) == MELT_TITLE


def test_a_sidecar_new_beside_a_known_audio_file_is_read(tmp_path: Path) -> None:
    music = folder_of(tmp_path / "Music", {"a.wav": Song("A")})
    known = _known(_scan(tmp_path, music))

    info_json_beside(music / "a.wav", melt_video())
    found = _scan(tmp_path, music, known=known)

    assert found["a.wav"].changed is False
    assert _read_title(found["a.wav"]) == MELT_TITLE


@pytest.mark.parametrize(
    ("content", "error"),
    [
        pytest.param('{"title": "Melt", ', "isn't valid JSON", id="malformed JSON"),
        pytest.param('["Melt"]', "isn't a JSON object", id="a list"),
        pytest.param('"Melt"', "isn't a JSON object", id="a string"),
        pytest.param("[" * 100_000, "isn't valid JSON", id="nesting too deep to parse"),
        pytest.param(" " * (MAX_BYTES + 1), "too large", id="a file over the limit"),
    ],
)
def test_a_sidecar_that_cant_be_read_is_a_noted_error_and_the_scan_goes_on(
    tmp_path: Path, content: str, error: str
) -> None:
    music = folder_of(tmp_path / "Music", {"a.wav": Song("A"), "b.wav": Song("B")})
    info_json_beside(music / "a.wav", content)

    found = _scan(tmp_path, music)

    info = found["a.wav"].info_json
    assert info is not None
    assert info.text is None
    assert error in info.error
    assert found["a.wav"].tags is not None
    assert found["b.wav"].tags is not None


def test_a_sidecar_at_the_limit_is_read(tmp_path: Path) -> None:
    music = folder_of(tmp_path / "Music", {"a.wav": Song("A")})
    padding = " " * (MAX_BYTES - len("{}"))
    info_json_beside(music / "a.wav", "{}" + padding)

    info = _scan(tmp_path, music)["a.wav"].info_json

    assert info is not None
    assert info.error == ""
    assert info.text is not None


def test_a_chapter_that_is_not_a_start_and_a_title_is_skipped_and_the_rest_kept(
    tmp_path: Path,
) -> None:
    music = folder_of(tmp_path / "Music", {"a.wav": Song("A")})
    info_json_beside(music / "a.wav", album_with_odd_chapters())

    info = _scan(tmp_path, music)["a.wav"].info_json

    assert info is not None
    assert info.text is not None
    assert info.text.chapters == (
        InfoChapter(start_ms=0, title="アイネクライネ"),
        InfoChapter(start_ms=252_400, title="ゴーゴー幽霊船"),
        InfoChapter(start_ms=3_723_000, title="Last"),
    )


def test_the_sidecar_of_a_zip_archive_is_read_stored_or_compressed(tmp_path: Path) -> None:
    archive = zip_of(
        tmp_path / "Old.zip",
        {
            "x/stored.wav": Song("Stored"),
            "x/stored.info.json": melt_video().encode(),
            "x/deflated.wav": Song("Deflated"),
            "x/deflated.info.json": world_is_mine_video().encode(),
        },
        compressed=frozenset({"x/deflated.info.json"}),
    )

    found = _scan(tmp_path, archive, "zip")

    assert {path: _read_title(file) for path, file in found.items()} == {
        "x/deflated.wav": "【初音ミク】ワールドイズマイン / ryo(supercell)【MV】",
        "x/stored.wav": MELT_TITLE,
    }


def test_a_sidecar_that_cant_be_opened_is_read_again_next_scan(tmp_path: Path) -> None:
    music = folder_of(tmp_path / "Music", {"a.wav": Song("A")})
    sidecar = info_json_beside(music / "a.wav", melt_video())
    sidecar.chmod(0)

    info = _scan(tmp_path, music)["a.wav"].info_json

    sidecar.chmod(0o644)
    assert info is not None
    assert (info.retry, "can't be read" in info.error) == (True, True)
