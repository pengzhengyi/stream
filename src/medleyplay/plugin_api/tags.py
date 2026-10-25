"""The tag reader: a file's title, artists, album, and duration, by file extension."""

from datetime import timedelta
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from medleyplay.plugin_api.extension import ExtensionPoint


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ReadTags(_Model):
    """Read the tags of the bytes at `local_path`, from `offset`, for `length` when given.

    The offset and length pick a member stored inside a zip archive.
    """

    local_path: str
    offset: int = 0
    length: int | None = None


class Tags(_Model):
    """What a file says about its music; an empty string means the tag is absent.

    `protected` is set for a file whose audio is locked to another player, such as
    an `.m4p` from the iTunes Store.
    """

    title: str = ""
    artist: str = ""
    album: str = ""
    album_artist: str = ""
    duration_ms: int | None = None
    track_number: int | None = None
    protected: bool = False


class TagReader(Protocol):
    """Reads the tags of files of one type."""

    def read_tags(self, request: ReadTags) -> Tags:
        """Read the file's tags."""
        ...


TAG_READER = ExtensionPoint[TagReader]("tag_reader")
READ_TAGS = TAG_READER.operation(
    "read_tags", ReadTags, Tags, lambda reader: reader.read_tags, deadline=timedelta(seconds=30)
)
