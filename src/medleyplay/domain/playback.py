"""Playback: whether a Track can play now, what its audio is, and where its cache copy goes."""

import hashlib
import uuid
from pathlib import PurePosixPath
from typing import Final, NewType

from medleyplay.domain.catalog import SourceId

PlayId = NewType("PlayId", uuid.UUID)

MEDIA_TYPES: Final = {
    "mp3": "audio/mpeg",
    "m4a": "audio/mp4",
    "m4b": "audio/mp4",
    "mp4": "audio/mp4",
    "flac": "audio/flac",
    "ogg": "audio/ogg",
    "oga": "audio/ogg",
    "opus": "audio/ogg",
    "wav": "audio/wav",
    "aif": "audio/aiff",
    "aifc": "audio/aiff",
    "aiff": "audio/aiff",
    "wma": "audio/x-ms-wma",
}
"""The media type of each audio extension the core serves."""
UNKNOWN_MEDIA_TYPE: Final = "application/octet-stream"

CACHE_FOLDER: Final = "cache/sources"
"""Where cache copies live, in the data folder."""


def extension(path: str) -> str:
    """Return the lowercase extension of `path`, without its dot."""
    return PurePosixPath(path).suffix.lower().removeprefix(".")


def media_type(path: str) -> str:
    """Return the media type of the audio file at `path`, by its extension."""
    return MEDIA_TYPES.get(extension(path), UNKNOWN_MEDIA_TYPE)


def source_version(fingerprint: str | None, size: int | None, modified_ns: int | None) -> str:
    """Return a short name for the version of a Source's file that its last scan saw.

    The fingerprint names it; a file whose fingerprint couldn't be taken is named by
    its size and modification time instead.
    """
    seen = fingerprint or f"{size}:{modified_ns}"
    return hashlib.sha256(seen.encode()).hexdigest()[:16]


def cache_name(source_id: SourceId, version: str, path: str) -> str:
    """Return the file name of a Source's cache copy.

    The extension is kept only when it is a known audio one, so a file's name can't
    shape the cache's paths: `7-1a2b3c4d5e6f7a8b.flac`.
    """
    suffix = extension(path) if extension(path) in MEDIA_TYPES else "bin"
    return f"{source_id}-{version}.{suffix}"


def cache_target(source_id: SourceId, version: str) -> str:
    """Return the Job target that prepares one version of a Source."""
    return f"source:{source_id}:{version}"
