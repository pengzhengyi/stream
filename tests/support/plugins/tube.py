"""A plugin that answers for `bilibili` Sources with scripted videos, so no test meets the site.

The video id says how the plugin behaves:

| Video | Reads as | Downloads as |
| --- | --- | --- |
| `BV1Xx41117Tz` | *Night Drive* by *Blue Room*, one part | `audio.m4a` |
| `BV17x411w7KC` | *Mixtape*, three parts | `audio.m4a` |
| `BVgone` | gone | gone |
| `BVmembers` | needs a login | `audio.m4a` with a login, an `AuthError` without |
| `BVrefused` | one part | an `AuthError`: the site refuses the login |
| `BVdown` | a `NetworkError` | a `NetworkError` |
| `BVbroken` | a fault | a fault |
| `BVescape`, `BVtext` | one part | a file outside the folder, or of another type |
| `BVempty`, `BVlink` | one part | an empty file, or a link |

A downloaded file holds what the download was asked, so a test can read back the
quality and the login it got: `BV1Xx41117Tz/p1 quality=30280 login=<text> mode=0o600`.

`https://b23.tv/night` leads to `BV1Xx41117Tz`, `https://b23.tv/away` off the site,
and `https://b23.tv/liar` names a video on a link off the site.
"""

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from medleyplay.plugin_api import (
    CREDENTIAL_SPEC,
    SOURCE_DOWNLOADER,
    SOURCE_RESOLVER,
    AudioQuality,
    AuthError,
    Canonical,
    Canonicalize,
    CheckedLogin,
    CheckLogin,
    Downloaded,
    DownloadPart,
    NetworkError,
    PartDetails,
    Plugin,
    ReadVideo,
    Registry,
    VideoDetails,
    VideoStatus,
    report_progress,
)

NIGHT_DRIVE: Final = "BV1Xx41117Tz"
MIXTAPE: Final = "BV17x411w7KC"
QUALITIES: Final = (
    AudioQuality(id="30280", label="192 kbps", kbps=192),
    AudioQuality(id="30232", label="132 kbps", kbps=132),
    AudioQuality(id="30216", label="64 kbps", kbps=64),
)
_TITLES: Final = {NIGHT_DRIVE: ("Night Drive", 1), MIXTAPE: ("Mixtape", 3)}
_VIDEO: Final = re.compile(r"/video/(?P<video>BV\w+)/?")
_PART: Final = re.compile(r"[?&]p=(?P<part>\d+)")
_SHORT: Final = {
    "night": f"https://www.bilibili.com/video/{NIGHT_DRIVE}",
    "away": "https://evil.example/video/BV1Xx41117Tz",
}


class Resolver:
    """Names scripted videos, and reads them as the table says."""

    def canonicalize(self, request: Canonicalize) -> Canonical:
        link = request.link
        if "b23.tv/liar" in link:
            return Canonical(video=NIGHT_DRIVE, link="https://evil.example/")
        for code, target in _SHORT.items():
            if f"b23.tv/{code}" in link:
                link = target
        video, part = _VIDEO.search(link), _PART.search(link)
        if video is None or "evil.example" in link:
            return Canonical(video=None, link=link)
        return Canonical(video=video["video"], part=int(part["part"]) if part else None, link=link)

    def read(self, request: ReadVideo) -> VideoDetails:
        video = request.video
        _fail_as(video)
        if video == "BVgone":
            return VideoDetails(status=VideoStatus.GONE, message="The video was removed.")
        if video == "BVmembers":
            return VideoDetails(status=VideoStatus.NEEDS_LOGIN, message="Members only.")
        title, parts = _TITLES.get(video, (video, 1))
        return VideoDetails(
            title=f"【MV】{title}",
            uploader="Blue Room",
            parts=tuple(
                PartDetails(part=n, title=title if parts == 1 else f"{title} {n}", duration_ms=1000)
                for n in range(1, parts + 1)
            ),
            qualities=QUALITIES,
        )


class Downloader:
    """Writes a file saying what it was asked, or misbehaves as the video id says."""

    def download(self, request: DownloadPart) -> Downloaded:
        video, folder = request.video, Path(request.folder)
        _fail_as(video)
        if video == "BVgone":
            return Downloaded(file=None, gone=True, message="The video was removed.")
        if video == "BVrefused" or (video == "BVmembers" and request.login is None):
            message = "Bilibili refused the login."
            raise AuthError(message)
        report_progress(0.5, "Downloading")
        quality = "30280" if request.quality == "best" else request.quality
        name = _misbehave(video, folder)
        if name is None:
            name = "audio.m4a"
            (folder / name).write_text(_said(request, quality), encoding="utf-8")
        return Downloaded(file=name, quality=quality, backend="tube")


class Login:
    """Keeps the `SESSDATA` lines of a cookies file, which expires when the first one does."""

    def check(self, request: CheckLogin) -> CheckedLogin:
        kept = [line for line in request.text.splitlines() if "\tSESSDATA\t" in line]
        if not kept:
            return CheckedLogin(valid=False, message="The file holds no session.")
        expiry = int(kept[0].split("\t")[4])
        expires_at = datetime.fromtimestamp(expiry, UTC) if expiry else None
        return CheckedLogin(valid=True, login="\n".join(kept) + "\n", expires_at=expires_at)


def _fail_as(video: str) -> None:
    if video == "BVdown":
        message = "Bilibili couldn't be reached."
        raise NetworkError(message)
    if video == "BVbroken":
        message = "The page changed."
        raise ValueError(message)


def _misbehave(video: str, folder: Path) -> str | None:
    match video:
        case "BVescape":
            return "../escape.m4a"
        case "BVtext":
            (folder / "notes.txt").write_text("not audio", encoding="utf-8")
            return "notes.txt"
        case "BVempty":
            (folder / "audio.m4a").touch()
            return "audio.m4a"
        case "BVlink":
            (folder / "audio.m4a").symlink_to("/etc/hosts")
            return "audio.m4a"
        case _:
            return None


def _said(request: DownloadPart, quality: str) -> str:
    login, mode = "none", "none"
    if request.login is not None:
        path = Path(request.login)
        login = path.read_text(encoding="utf-8").strip()
        mode = oct(path.stat().st_mode & 0o777)
    return f"{request.video}/p{request.part} quality={quality} login={login} mode={mode}"


def register(registry: Registry) -> None:
    """Add the resolver, the downloader, and the login check for `bilibili`."""
    registry.add(SOURCE_RESOLVER, "bilibili", Resolver())
    registry.add(SOURCE_DOWNLOADER, "bilibili", Downloader())
    registry.add(CREDENTIAL_SPEC, "bilibili", Login())


plugin = Plugin(api_version=1, register=register)
