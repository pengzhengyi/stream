"""Reading a video's details from yt-dlp's info, and naming the formats to download.

yt-dlp answers a video with several parts as a playlist whose entries are only
the parts' URLs, so only the first part is read in full; it names the uploader,
the formats, and its own part's title, as `<video title> p01 <part title>`.

Unverified until yt-dlp can read Bilibili again: the fields follow yt-dlp's
Bilibili extractor, not a recorded answer.
"""

from collections.abc import Mapping, Sequence
from typing import Final

from medleyplay.plugin_api import BEST_QUALITY, AudioQuality, PartDetails, VideoDetails

type Info = Mapping[str, object]

QUALITIES: Final = {"30280": 192, "30232": 132, "30216": 64}
"""Bilibili's AAC audio ids and their bitrates in kbps, best first."""
VIDEO_URL: Final = "https://www.bilibili.com/video/{video}"
MAX_TEXT: Final = 512


def video_url(video: str, part: int | None = None) -> str:
    """Return the URL yt-dlp reads a video, or one of its parts, from."""
    url = VIDEO_URL.format(video=video)
    return url if part is None else f"{url}?p={part}"


def video_details(first: Info, playlist: Info | None = None) -> VideoDetails:
    """Return a video's details from the info of its first part, and of the playlist, if any.

    A video with no AAC audio-only stream, such as an old one with only a muxed
    stream, has no qualities; the caller says why.
    """
    title = _text(playlist or first, "title")
    qualities = audio_qualities(first)
    count = len(_entries(playlist)) if playlist is not None else 1
    first_title = _text(first, "title").removeprefix(f"{title} p01 ") if playlist else title
    parts = [PartDetails(part=1, title=first_title or title, duration_ms=_duration_ms(first))]
    parts += [PartDetails(part=n, title=f"{title} P{n}") for n in range(2, count + 1)]
    return VideoDetails(
        title=title, uploader=_text(first, "uploader"), parts=tuple(parts), qualities=qualities
    )


def audio_qualities(info: Info) -> tuple[AudioQuality, ...]:
    """Return the AAC audio-only qualities among a part's formats, best first."""
    found = {
        str(fmt.get("format_id"))
        for fmt in _list(info.get("formats"))
        if fmt.get("vcodec") == "none" and str(fmt.get("acodec") or "").startswith("mp4a")
    }
    return tuple(
        AudioQuality(id=quality, label=f"{kbps} kbps", kbps=kbps)
        for quality, kbps in QUALITIES.items()
        if quality in found
    )


def codecs(info: Info) -> str:
    """Return the audio codecs among a part's formats, to say why none can be served."""
    found = sorted({str(fmt.get("acodec")) for fmt in _list(info.get("formats"))} - {"none"})
    return ", ".join(found) or "none"


def formats_for(quality: str) -> str:
    """Return yt-dlp's format choice for `quality`: it, or the next best, down to the lowest."""
    ids = list(QUALITIES)
    start = 0 if quality == BEST_QUALITY else ids.index(quality)
    return "/".join(ids[start:])


def downloaded_file(info: Info) -> tuple[str, str | None]:
    """Return the downloaded file's path and the format id yt-dlp chose."""
    downloads = _list(info.get("requested_downloads"))
    path = downloads[0].get("filepath") if downloads else None
    if not isinstance(path, str):
        message = "yt-dlp didn't say where it downloaded the part."
        raise TypeError(message)
    format_id = info.get("format_id")
    return path, str(format_id) if format_id is not None else None


def _entries(playlist: Info) -> Sequence[Mapping[str, object]]:
    return _list(playlist.get("entries"))


def _list(value: object) -> list[Mapping[str, object]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _text(info: Info, key: str) -> str:
    value = info.get(key)
    return value.strip()[:MAX_TEXT] if isinstance(value, str) else ""


def _duration_ms(info: Info) -> int | None:
    seconds = info.get("duration")
    return round(seconds * 1000) if isinstance(seconds, int | float) and seconds >= 0 else None
