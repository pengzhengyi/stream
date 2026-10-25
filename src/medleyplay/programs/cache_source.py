"""The program that copies a compressed zip member into the cache, so it can be served."""

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from medleyplay.plugin_api import FETCH_FILE, FetchFile, LibraryPath, LibraryRoot
from medleyplay.plugin_host.job import JobContext, JobProgram, PluginCallFailedError


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CacheSource(_Model):
    """Copy the file at `path` in `root`, `length` bytes long, to `destination`."""

    root: LibraryRoot
    path: LibraryPath
    length: int
    destination: str


class CachedSource(_Model):
    """The copy is at its destination."""

    size: int


def run(request: CacheSource, context: JobContext) -> CachedSource:
    """Fetch the file into the working folder, check it, and move it into place at once.

    A copy already at the destination, such as from a Job that finished just
    before this one was submitted, is kept.
    """
    destination = Path(request.destination)
    if destination.is_file() and destination.stat().st_size == request.length:
        return CachedSource(size=request.length)
    folder = context.work_dir / "fetched"
    folder.mkdir(exist_ok=True)
    kind = request.root.kind
    fetched = context.call(
        FETCH_FILE, kind, FetchFile(root=request.root, path=request.path, folder=str(folder))
    )
    copy = Path(fetched.local_path).resolve()
    if not copy.is_relative_to(folder.resolve()) or not copy.is_file():
        message = f"The copy of {request.path!r} isn't a file in the folder it was fetched into."
        raise PluginCallFailedError(kind="plugin", message=message, plugin=None, key=kind)
    size = copy.stat().st_size
    if size != request.length:
        message = f"The copy of {request.path!r} has {size} bytes, not {request.length}."
        raise PluginCallFailedError(kind="plugin", message=message, plugin=None, key=kind)
    with copy.open("rb") as file:
        os.fsync(file.fileno())
    destination.parent.mkdir(parents=True, exist_ok=True)
    copy.replace(destination)
    return CachedSource(size=size)


CACHE_SOURCE: JobProgram[CacheSource, CachedSource] = JobProgram(CacheSource, CachedSource, run)
