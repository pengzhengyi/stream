"""The plugin's three providers: the resolver, the downloader, and the login check."""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from medleyplay.plugin_api import (
    AuthError,
    Canonical,
    Canonicalize,
    CheckedLogin,
    CheckLogin,
    Downloaded,
    DownloadPart,
    ReadVideo,
    VideoDetails,
    VideoStatus,
    report_progress,
)
from medleyplay.plugins.bilibili import _ytdlp
from medleyplay.plugins.bilibili.cookies import NoSessionError, keep_login
from medleyplay.plugins.bilibili.links import is_short_link, parse_video_link
from medleyplay.plugins.bilibili.short_links import Fetch, follow_short_link, is_allowed
from medleyplay.plugins.bilibili.videos import (
    audio_qualities,
    codecs,
    downloaded_file,
    formats_for,
    video_details,
    video_url,
)

BACKEND: Final = "yt-dlp"

type Extract = Callable[..., _ytdlp.Info]


@dataclass(frozen=True)
class BilibiliResolver:
    """Finds the video a Bilibili link names, and reads its details with yt-dlp."""

    fetch: Fetch | None = None
    extract: Extract = field(default=_ytdlp.extract)

    def canonicalize(self, request: Canonicalize) -> Canonical:
        """Name the video and part the link does, following a short link first."""
        link = (
            follow_short_link(request.link, self.fetch)
            if is_short_link(request.link)
            else request.link
        )
        found = None if is_short_link(link) or not is_allowed(link) else parse_video_link(link)
        if found is None:
            return Canonical(video=None, link=link)
        return Canonical(video=found.video, part=found.part, link=link)

    def read(self, request: ReadVideo) -> VideoDetails:
        """Read the video's title, uploader, parts, and AAC qualities."""
        try:
            top = self.extract(video_url(request.video), playlist=True)
            if top.get("_type") == "playlist":
                first = self.extract(video_url(request.video, 1), playlist=False)
                details = video_details(first, top)
            else:
                first, details = top, video_details(top)
        except _ytdlp.GoneError as error:
            return VideoDetails(status=VideoStatus.GONE, message=str(error)[:512])
        except _ytdlp.NeedsLoginError as error:
            return VideoDetails(status=VideoStatus.NEEDS_LOGIN, message=str(error)[:512])
        if not audio_qualities(first):
            message = f"The video has no AAC audio stream medleyplay can serve ({codecs(first)})."
            return VideoDetails(status=VideoStatus.GONE, message=message)
        return details


@dataclass(frozen=True)
class BilibiliDownloader:
    """Downloads a part's audio with yt-dlp."""

    download_with: Callable[..., _ytdlp.Info] = field(default=_ytdlp.download)

    def download(self, request: DownloadPart) -> Downloaded:
        """Download the part at its quality, or the best below it, into the folder."""

        def on_progress(done: int, total: int | None) -> None:
            report_progress(done / total if total else None, "Downloading")

        try:
            info = self.download_with(
                video_url(request.video, request.part),
                formats=formats_for(request.quality),
                folder=request.folder,
                cookie_file=request.login,
                on_progress=on_progress,
            )
        except _ytdlp.GoneError as error:
            return Downloaded(file=None, gone=True, message=str(error)[:512])
        except _ytdlp.NeedsLoginError as error:
            message = f"This video needs a Bilibili login: {error}"
            raise AuthError(message) from None
        path, quality = downloaded_file(info)
        return Downloaded(file=Path(path).name, quality=quality, backend=BACKEND)


class BilibiliLogin:
    """Keeps the Bilibili cookies the plugin needs from a pasted cookies file."""

    def check(self, request: CheckLogin) -> CheckedLogin:
        """Keep the session and device cookies, or say the file holds no session."""
        try:
            login = keep_login(request.text)
        except NoSessionError as error:
            return CheckedLogin(valid=False, message=str(error))
        return CheckedLogin(valid=True, login=login.cookies, expires_at=login.expires_at)
