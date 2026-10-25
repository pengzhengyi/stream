"""Sources on a site: turning a link into a video, reading it, downloading it, and logins.

A video has parts, each the audio of one Source; the core names a part's Source
from the video's id and the part's number, so a plugin can't hand the core a path
or a URL as a key:

```text
link     https://b23.tv/abc123
video    BV1Xx41117Tz
part     2              the Source BV1Xx41117Tz/p2
```

An ordinary *no*, such as a link that isn't a video or a video that was removed,
is a reply, not a failure, so it doesn't count against the plugin.
"""

from datetime import timedelta
from enum import StrEnum
from typing import Annotated, Final, Protocol

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

from medleyplay.plugin_api.extension import ExtensionPoint

MAX_TEXT: Final = 512
MAX_LOGIN_TEXT: Final = 64 * 1024
BEST_QUALITY: Final = "best"
"""The quality that asks for the best audio the login allows."""

type VideoId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
"""A video's id on its site: letters, digits, `_`, and `-`."""
type PartNumber = Annotated[int, Field(ge=1, le=9999)]
type QualityId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_-]{1,32}$")]
"""A site's own name for an audio quality, such as Bilibili's `30280`, or `best`."""
type Text = Annotated[str, StringConstraints(max_length=MAX_TEXT)]


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Canonicalize(_Model):
    """Find the video a link names; the core has checked that its host is the site's."""

    link: Annotated[str, StringConstraints(max_length=2048)]


class Canonical(_Model):
    """The video and part a link names, and the link it ended on after any redirects.

    `video` is `None` for a link to something that isn't a video, such as a channel.
    """

    video: VideoId | None
    part: PartNumber | None = None
    link: Annotated[str, StringConstraints(max_length=2048)]


class ReadVideo(_Model):
    """Read a video's details, without a login."""

    video: VideoId


class VideoStatus(StrEnum):
    """Whether a video can be read."""

    OK = "ok"
    GONE = "gone"
    """Removed, region-locked, or with no audio the core can serve."""
    NEEDS_LOGIN = "needs_login"
    """Only a signed-in account can see it."""


class PartDetails(_Model):
    """One part of a video: its number, title, and length when known."""

    part: PartNumber
    title: Text
    duration_ms: Annotated[int, Field(ge=0)] | None = None


class AudioQuality(_Model):
    """An audio quality a part can be downloaded at."""

    id: QualityId
    label: Text
    kbps: Annotated[int, Field(ge=1)] | None = None


class VideoDetails(_Model):
    """A video's title, uploader, parts, and qualities, or why it can't be read."""

    status: VideoStatus = VideoStatus.OK
    message: Text = ""
    title: Text = ""
    uploader: Text = ""
    parts: tuple[PartDetails, ...] = ()
    qualities: tuple[AudioQuality, ...] = ()


class SourceResolver(Protocol):
    """Recognizes a site's links and reads its videos."""

    def canonicalize(self, request: Canonicalize) -> Canonical:
        """Say which video and part the link names, following a short link."""
        ...

    def read(self, request: ReadVideo) -> VideoDetails:
        """Read the video's details."""
        ...


class DownloadPart(_Model):
    """Download one part's audio into `folder`, an empty folder the caller owns.

    `login` is the path of a cookies file in that folder, or `None` to download
    without one.
    """

    video: VideoId
    part: PartNumber
    quality: QualityId
    folder: str
    login: str | None = None


class Downloaded(_Model):
    """The downloaded file's bare name in the folder, or why there is none.

    `gone` says the site no longer has the part, as `VideoStatus.GONE` does.
    """

    file: Annotated[str, StringConstraints(max_length=255)] | None
    gone: bool = False
    message: Text = ""
    quality: QualityId | None = None
    backend: Annotated[str, StringConstraints(max_length=64)] = ""


class SourceDownloader(Protocol):
    """Downloads a site's audio."""

    def download(self, request: DownloadPart) -> Downloaded:
        """Download the part into the folder, reporting progress as it goes."""
        ...


class CheckLogin(_Model):
    """Read a login pasted by the household, such as an exported cookies file."""

    text: Annotated[str, StringConstraints(max_length=MAX_LOGIN_TEXT)]


class CheckedLogin(_Model):
    """The login to keep, and when it expires, or why the pasted text holds none.

    `login` holds only what the site needs, in the form the downloader reads.
    """

    valid: bool
    message: Text = ""
    login: Annotated[str, StringConstraints(max_length=MAX_LOGIN_TEXT)] = ""
    expires_at: AwareDatetime | None = None


class CredentialSpec(Protocol):
    """Describes a site's login."""

    def check(self, request: CheckLogin) -> CheckedLogin:
        """Keep the parts of the pasted login the site needs, without contacting it."""
        ...


SOURCE_RESOLVER = ExtensionPoint[SourceResolver]("source_resolver")
CANONICALIZE = SOURCE_RESOLVER.operation(
    "canonicalize",
    Canonicalize,
    Canonical,
    lambda resolver: resolver.canonicalize,
    deadline=timedelta(seconds=5),
)
READ_VIDEO = SOURCE_RESOLVER.operation(
    "read", ReadVideo, VideoDetails, lambda resolver: resolver.read, deadline=timedelta(seconds=10)
)
SOURCE_DOWNLOADER = ExtensionPoint[SourceDownloader]("source_downloader")
DOWNLOAD_PART = SOURCE_DOWNLOADER.operation(
    "download",
    DownloadPart,
    Downloaded,
    lambda downloader: downloader.download,
    deadline=timedelta(hours=2),
)
CREDENTIAL_SPEC = ExtensionPoint[CredentialSpec]("credential_spec")
CHECK_LOGIN = CREDENTIAL_SPEC.operation(
    "check", CheckLogin, CheckedLogin, lambda spec: spec.check, deadline=timedelta(seconds=5)
)
