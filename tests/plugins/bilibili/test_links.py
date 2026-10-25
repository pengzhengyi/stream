"""Every shape of Bilibili link names one video and, perhaps, one of its parts."""

import pytest

from medleyplay.plugins.bilibili.links import (
    VideoLink,
    av_to_bv,
    bv_to_av,
    is_short_link,
    parse_video_link,
)


@pytest.mark.parametrize(
    ("aid", "bvid"),
    [(170001, "BV17x411w7KC"), (2, "BV1xx411c7mD"), (8508035, "BV1Xx41117Tz")],
)
def test_av_and_bv_ids_convert_both_ways(aid: int, bvid: str) -> None:
    assert av_to_bv(aid) == bvid
    assert bv_to_av(bvid) == aid


@pytest.mark.parametrize(
    ("link", "expected"),
    [
        ("https://www.bilibili.com/video/BV1Xx41117Tz/", VideoLink("BV1Xx41117Tz", None)),
        ("https://www.bilibili.com/video/BV1Xx41117Tz?p=3", VideoLink("BV1Xx41117Tz", 3)),
        ("https://m.bilibili.com/video/BV1Xx41117Tz/?p=1&t=30", VideoLink("BV1Xx41117Tz", 1)),
        ("https://www.bilibili.com/video/av170001", VideoLink("BV17x411w7KC", None)),
        ("https://bilibili.com/video/AV170001/?p=2", VideoLink("BV17x411w7KC", 2)),
        ("https://www.bilibili.com/video/bv1Xx41117Tz", VideoLink("BV1Xx41117Tz", None)),
    ],
)
def test_a_video_link_names_its_video_and_part(link: str, expected: VideoLink) -> None:
    assert parse_video_link(link) == expected


@pytest.mark.parametrize(
    "link",
    [
        "https://www.bilibili.com/",
        "https://www.bilibili.com/video/",
        "https://www.bilibili.com/video/BV1Xx41117T",
        "https://www.bilibili.com/video/BV1Xx41117Tz?p=0",
        "https://www.bilibili.com/video/BV1Xx41117Tz?p=two",
        "https://www.bilibili.com/bangumi/play/ep1234",
        "https://www.bilibili.com/video/av0",
    ],
)
def test_a_link_to_anything_but_a_video_names_none(link: str) -> None:
    assert parse_video_link(link) is None


def test_a_b23_link_is_short() -> None:
    assert is_short_link("https://b23.tv/abc123")
    assert not is_short_link("https://www.bilibili.com/video/BV1Xx41117Tz")
