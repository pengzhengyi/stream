"""A Download's name comes from its Source, and only AAC audio is accepted."""

import pytest

from medleyplay.domain.catalog import SourceId
from medleyplay.domain.downloads import download_name, download_target
from medleyplay.domain.errors import InvalidInputError


def test_a_download_is_named_by_its_source_and_the_type_of_its_file() -> None:
    assert download_name(SourceId(7), "audio.M4A") == "7.m4a"


@pytest.mark.parametrize("file", ["audio.flac", "audio", "notes.txt", "audio.m4a.sh"])
def test_a_file_that_is_not_aac_audio_is_refused(file: str) -> None:
    with pytest.raises(InvalidInputError):
        download_name(SourceId(7), file)


def test_a_download_job_works_on_its_source() -> None:
    assert download_target(SourceId(7)) == "source:7"
