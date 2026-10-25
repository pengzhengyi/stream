"""The program that downloads one part of a site's video into the Job's folder, and checks it.

The plugin downloads into `download/`, an empty folder of its own, and names the
file it made; the program trusts the name only once the file proves to be a
plain, non-empty file of an accepted type, directly in that folder.
"""

import os
import stat
from pathlib import Path, PurePosixPath
from typing import Final, NoReturn

from pydantic import BaseModel, ConfigDict

from medleyplay.plugin_api import DOWNLOAD_PART, DownloadPart, PartNumber, QualityId, VideoId
from medleyplay.plugin_host.job import JobContext, JobProgram, PluginCallFailedError

DOWNLOAD_FOLDER: Final = "download"
_OPEN_FLAGS: Final = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DownloadSource(_Model):
    """Download a part of a video on `site` at `quality`, as a file of an accepted type."""

    site: str
    video: VideoId
    part: PartNumber
    quality: QualityId
    extensions: frozenset[str]
    max_bytes: int


class DownloadedSource(_Model):
    """The checked file's name in the download folder, or why there is none."""

    file: str | None
    gone: bool = False
    message: str = ""
    quality: str = ""
    backend: str = ""
    size: int = 0


def run(request: DownloadSource, context: JobContext) -> DownloadedSource:
    """Download the part with the Job's login, if it has one, then check the file."""
    folder = context.work_dir / DOWNLOAD_FOLDER
    folder.mkdir(exist_ok=True)
    downloaded = context.call(
        DOWNLOAD_PART,
        request.site,
        DownloadPart(
            video=request.video,
            part=request.part,
            quality=request.quality,
            folder=str(folder),
            login=str(context.login) if context.login else None,
        ),
    )
    if downloaded.file is None:
        message = downloaded.message or "The site no longer has it."
        return DownloadedSource(file=None, gone=True, message=message)
    size = _check(folder, downloaded.file, request)
    return DownloadedSource(
        file=downloaded.file,
        quality=downloaded.quality or request.quality,
        backend=downloaded.backend,
        size=size,
    )


def _check(folder: Path, name: str, request: DownloadSource) -> int:
    """Return the size of the file the plugin named, synced to disk, or fail as a plugin fault."""
    suffix = PurePosixPath(name).suffix.lower().removeprefix(".")
    if PurePosixPath(name).name != name or name in {".", ".."} or "\\" in name:
        _refuse(request, f"named {name!r}, which isn't a file directly in its folder")
    if suffix not in request.extensions:
        _refuse(request, f"made {name!r}, which isn't an accepted type of audio")
    try:
        descriptor = os.open(folder / name, _OPEN_FLAGS)
    except OSError as error:
        _refuse(request, f"named {name!r}, which can't be opened: {error.strerror}")
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            _refuse(request, f"named {name!r}, which isn't a regular file")
        if not 0 < info.st_size <= request.max_bytes:
            _refuse(request, f"made {name!r}, {info.st_size} bytes long")
        os.fsync(descriptor)
        return info.st_size
    finally:
        os.close(descriptor)


def _refuse(request: DownloadSource, why: str) -> NoReturn:
    message = f"The download of {request.video} part {request.part} {why}."
    raise PluginCallFailedError(kind="plugin", message=message, plugin=None, key=request.site)


DOWNLOAD_SOURCE: JobProgram[DownloadSource, DownloadedSource] = JobProgram(
    DownloadSource, DownloadedSource, run
)
