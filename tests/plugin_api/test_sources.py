"""The Source models: what a resolver, a downloader, and a login check may say."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from medleyplay.plugin_api import (
    AudioQuality,
    Canonical,
    CheckedLogin,
    Downloaded,
    DownloadPart,
    PartDetails,
    VideoDetails,
    VideoStatus,
)


@pytest.mark.parametrize("video", ["../etc", "BV1Xx41117Tz/p1", "https://b23.tv/x", "", "a b"])
def test_a_video_id_is_never_a_path_or_a_link(video: str) -> None:
    with pytest.raises(ValidationError):
        Canonical(video=video, link="https://www.bilibili.com/")


@pytest.mark.parametrize("part", [0, -1, 10_000])
def test_a_part_is_numbered_from_one(part: int) -> None:
    with pytest.raises(ValidationError):
        PartDetails(part=part, title="Intro")


def test_a_link_to_something_but_a_video_names_no_video() -> None:
    canonical = Canonical(video=None, link="https://space.bilibili.com/1234")

    assert canonical.part is None


def test_a_video_that_cant_be_read_says_why_with_no_details() -> None:
    details = VideoDetails(status=VideoStatus.GONE, message="The video was removed.")

    assert details.parts == ()
    assert details.qualities == ()


@pytest.mark.parametrize("quality", ["Best", "30280 kbps", "../x", ""])
def test_a_quality_is_a_plain_name(quality: str) -> None:
    with pytest.raises(ValidationError):
        AudioQuality(id=quality, label="Best")
    with pytest.raises(ValidationError):
        DownloadPart(video="BV1Xx41117Tz", part=1, quality=quality, folder="/jobs/1")


def test_a_download_names_its_file_or_says_the_part_is_gone() -> None:
    assert Downloaded(file="BV1Xx41117Tz_p1.m4a", quality="30280", backend="yt-dlp").gone is False
    assert Downloaded(file=None, gone=True, message="Removed.").file is None


def test_a_login_expiry_says_its_time_zone() -> None:
    with pytest.raises(ValidationError):
        CheckedLogin(valid=True, login="x", expires_at=datetime(2027, 4, 8))  # noqa: DTZ001 -- the naive time is the point
