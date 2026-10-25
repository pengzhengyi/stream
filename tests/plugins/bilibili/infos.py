"""yt-dlp's info for Bilibili videos, as the plugin's tests need it.

Made from yt-dlp's Bilibili extractor source, not recorded from the site: yt-dlp
can't read Bilibili today. Step 5b replaces these with a recorded answer.
"""

from collections.abc import Mapping
from typing import Final

VIDEO: Final = "BV1Xx41117Tz"
TITLE: Final = "【MV】Night Drive"
UPLOADER: Final = "Blue Room"


def _format(format_id: str, acodec: str, vcodec: str = "none") -> dict[str, object]:
    return {"format_id": format_id, "acodec": acodec, "vcodec": vcodec, "ext": "m4a"}


AAC_FORMATS: Final = [
    _format("30216", "mp4a.40.2"),
    _format("30232", "mp4a.40.2"),
    _format("30280", "mp4a.40.2"),
    _format("30250", "ec-3"),
    _format("100026", "none", vcodec="hev1.1.6.L120.90"),
]


class YtDlpInfoFactory:
    """Builds the info yt-dlp extracts from Bilibili."""

    @staticmethod
    def single(formats: list[dict[str, object]] | None = None) -> Mapping[str, object]:
        """A video with one part, three AAC qualities, Dolby audio, and a video stream.

        ```text
        title     【MV】Night Drive, by Blue Room, 3 min 20.5 s
        formats   30216 30232 30280 (AAC), 30250 (E-AC-3), 100026 (video)
        ```
        """
        return {
            "id": VIDEO,
            "title": TITLE,
            "uploader": UPLOADER,
            "duration": 200.5,
            "formats": AAC_FORMATS if formats is None else formats,
        }

    @staticmethod
    def anthology(parts: int) -> Mapping[str, object]:
        """A video with several parts, as a playlist of the parts' URLs and nothing else."""
        return {
            "_type": "playlist",
            "id": VIDEO,
            "title": TITLE,
            "entries": [
                {"_type": "url", "url": f"https://www.bilibili.com/video/{VIDEO}?p={n}"}
                for n in range(1, parts + 1)
            ],
        }

    @staticmethod
    def anthology_first_part() -> Mapping[str, object]:
        """The first part of a video with several parts, titled as yt-dlp titles it."""
        return {**YtDlpInfoFactory.single(), "id": f"{VIDEO}_p1", "title": f"{TITLE} p01 Intro"}

    @staticmethod
    def downloaded(path: str, format_id: str = "30280") -> Mapping[str, object]:
        """A part yt-dlp downloaded to `path` in the format `format_id`."""
        return {
            **YtDlpInfoFactory.single(),
            "format_id": format_id,
            "requested_downloads": [{"filepath": path, "format_id": format_id}],
        }
