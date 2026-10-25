"""The cache program: copying a file into the cache in one rename, and refusing bad copies."""

from pathlib import Path

import pytest

from medleyplay.plugin_api import LibraryRoot
from medleyplay.plugin_host.job import JobContext, PluginCallFailedError
from medleyplay.plugin_host.loader import load_plugins
from medleyplay.programs.cache_source import CachedSource, CacheSource, run
from tests.support.audio import Song, folder_of, wav_bytes
from tests.support.hosts import TEST_PLUGINS

A = wav_bytes(Song("A"))


def _context(tmp_path: Path) -> JobContext:
    """A Job's context in this process, calling the liar plugin; see tests.support.plugins.liar."""
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    return JobContext(
        work_dir, load_plugins(TEST_PLUGINS, ["liar"], lambda _: None), lambda _: None
    )


def _request(tmp_path: Path, path: str, length: int = len(A)) -> CacheSource:
    """Ask to cache `path` from a folder holding `a.wav`, into `cache/7-v.wav`."""
    root = folder_of(tmp_path / "Music", {"a.wav": Song("A")})
    return CacheSource(
        root=LibraryRoot(kind="folder", path=str(root)),
        path=path,
        length=length,
        destination=str(tmp_path / "cache" / "7-v.wav"),
    )


def test_the_copy_lands_at_its_destination(tmp_path: Path) -> None:
    request = _request(tmp_path, "a.wav")

    result = run(request, _context(tmp_path))

    assert result == CachedSource(size=len(A))
    assert Path(request.destination).read_bytes() == A
    assert list((tmp_path / "work" / "fetched").iterdir()) == []


def test_a_copy_already_at_its_destination_is_kept(tmp_path: Path) -> None:
    request = _request(tmp_path, "gone.wav", length=4)
    Path(request.destination).parent.mkdir()
    Path(request.destination).write_bytes(b"RIFF")

    result = run(request, _context(tmp_path))

    assert result == CachedSource(size=4)


def test_a_copy_of_the_wrong_length_is_refused(tmp_path: Path) -> None:
    with pytest.raises(PluginCallFailedError, match="has 1 bytes, not"):
        run(_request(tmp_path, "short.wav"), _context(tmp_path))

    assert not (tmp_path / "cache" / "7-v.wav").exists()


def test_a_copy_outside_the_working_folder_is_refused(tmp_path: Path) -> None:
    with pytest.raises(PluginCallFailedError, match="isn't a file in the folder"):
        run(_request(tmp_path, "elsewhere.wav"), _context(tmp_path))
