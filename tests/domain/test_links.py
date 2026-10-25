"""Recognizing a pasted link by its host, and naming the Source of one part of a video."""

import pytest

from medleyplay.domain.errors import InvalidInputError
from medleyplay.domain.links import (
    MAX_LINK_LENGTH,
    parse_part_locator,
    part_locator,
    recognize_link,
)


@pytest.mark.parametrize(
    "link",
    [
        "https://www.bilibili.com/video/BV1Xx41117Tz/",
        "http://bilibili.com/video/av170001?p=2",
        "https://m.bilibili.com/video/BV1Xx41117Tz",
        "https://b23.tv/abc123",
        "  https://WWW.Bilibili.COM/video/BV1Xx41117Tz  ",
        "https://www.bilibili.com./video/BV1Xx41117Tz",
    ],
)
def test_a_bilibili_link_is_recognized_by_its_host(link: str) -> None:
    assert recognize_link(link) == "bilibili"


@pytest.mark.parametrize(
    "link",
    [
        "https://evil.example/video/BV1Xx41117Tz",
        "https://bilibili.com.evil.example/video/BV1Xx41117Tz",
        "https://evilbilibili.com/video/BV1Xx41117Tz",
        "https://space.bilibili.com/1234",
        "ftp://www.bilibili.com/video/BV1Xx41117Tz",
        "file:///etc/passwd",
        "https://user:secret@www.bilibili.com/video/BV1Xx41117Tz",
        "https://www.bilibili.com:8443/video/BV1Xx41117Tz",
        "https://127.0.0.1/video/BV1Xx41117Tz",
        "www.bilibili.com/video/BV1Xx41117Tz",
        "",
        "not a link",
    ],
)
def test_any_other_link_is_refused(link: str) -> None:
    with pytest.raises(InvalidInputError):
        recognize_link(link)


def test_a_link_longer_than_the_limit_is_refused() -> None:
    link = "https://www.bilibili.com/video/BV1Xx41117Tz?x=" + "a" * MAX_LINK_LENGTH

    with pytest.raises(InvalidInputError, match="long"):
        recognize_link(link)


def test_a_part_locator_names_the_video_and_its_part() -> None:
    assert part_locator("BV1Xx41117Tz", 3) == "BV1Xx41117Tz/p3"


@pytest.mark.parametrize(("video", "part"), [("BV1Xx41117Tz", 0), ("../etc", 1), ("", 1)])
def test_a_part_locator_refuses_what_isnt_a_video_and_a_part(video: str, part: int) -> None:
    with pytest.raises(InvalidInputError):
        part_locator(video, part)


def test_a_part_locator_reads_back_as_its_video_and_part() -> None:
    assert parse_part_locator("BV1Xx41117Tz/p12") == ("BV1Xx41117Tz", 12)


@pytest.mark.parametrize(
    "locator", ["BV1Xx41117Tz", "BV1Xx41117Tz/p0", "BV1Xx41117Tz/p01", "x/y/p1"]
)
def test_anything_but_a_part_locator_is_refused(locator: str) -> None:
    with pytest.raises(InvalidInputError):
        parse_part_locator(locator)
