"""A Source's media type, its version, and the name of its cache copy."""

import pytest

from medleyplay.domain.catalog import SourceId
from medleyplay.domain.playback import cache_name, media_type, source_version


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("Blue/01 Intro.mp3", "audio/mpeg"),
        ("Night Drive.M4A", "audio/mp4"),
        ("x/song.flac", "audio/flac"),
        ("voice.opus", "audio/ogg"),
        ("old.aif", "audio/aiff"),
        ("notes.txt", "application/octet-stream"),
        ("no extension", "application/octet-stream"),
    ],
)
def test_the_media_type_comes_from_the_extension(path: str, expected: str) -> None:
    assert media_type(path) == expected


def test_a_source_version_follows_its_fingerprint() -> None:
    assert source_version("10:abc", 10, 1) != source_version("10:abd", 10, 1)
    assert source_version("10:abc", 10, 1) == source_version("10:abc", 99, 2)


def test_a_source_without_a_fingerprint_is_versioned_by_its_size_and_time() -> None:
    assert source_version(None, 10, 1) != source_version(None, 10, 2)


def test_a_cache_name_keeps_only_a_known_audio_extension() -> None:
    assert cache_name(SourceId(7), "1a2b", "x/Deflated.FLAC") == "7-1a2b.flac"
    assert cache_name(SourceId(7), "1a2b", "x/odd.sh") == "7-1a2b.bin"
