"""The plugin `tinytag-tags`: tags and durations of audio files, read with tinytag."""

import io
from pathlib import Path
from typing import Final, override

from tinytag import TinyTag, TinyTagException

from medleyplay.plugin_api import TAG_READER, Plugin, ReadTags, Registry, Tags
from medleyplay.plugins.mp4_length import read_fragmented_length

AUDIO_EXTENSIONS: Final = frozenset(
    {"aif", "aifc", "aiff", "flac", "m4a", "m4b", "mp3", "mp4", "oga", "ogg", "opus", "wav", "wma"}
)
"""The extensions this plugin reads: tinytag's audio formats, leaving out video."""
MP4_EXTENSIONS: Final = frozenset({"m4a", "m4b", "mp4"})
"""The extensions of MP4 files, whose length can also be read from their fragments."""
PROTECTED_EXTENSION: Final = "m4p"


class _Slice(io.RawIOBase):
    """A read-only view of `length` bytes of a file from `offset`, such as a zip member."""

    def __init__(self, file: io.BufferedReader, offset: int, length: int) -> None:
        self._file = file
        self._offset = offset
        self._length = length
        self._position = 0

    @override
    def readable(self) -> bool:
        return True

    @override
    def seekable(self) -> bool:
        return True

    @override
    def tell(self) -> int:
        return self._position

    @override
    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self._position, io.SEEK_END: self._length}[whence]
        self._position = min(max(base + offset, 0), self._length)
        return self._position

    @override
    def readinto(self, buffer: memoryview) -> int:  # type: ignore[override] # io.RawIOBase types the buffer loosely
        count = min(len(buffer), self._length - self._position)
        if count <= 0:
            return 0
        self._file.seek(self._offset + self._position)
        data = self._file.read(count)
        buffer[: len(data)] = data
        self._position += len(data)
        return len(data)


class TinytagReader:
    """Reads tags with tinytag; `protected` marks every file it reads as locked."""

    def __init__(self, *, protected: bool = False, mp4: bool = False) -> None:
        """Create a reader for unprotected files, or with `protected`, for locked ones.

        With `mp4`, a file tinytag finds no length for has its length read from its
        fragments instead, as in an MP4 file downloaded over DASH.
        """
        self._protected = protected
        self._mp4 = mp4

    def read_tags(self, request: ReadTags) -> Tags:
        """Read the tags; a file tinytag can't parse has none, rather than failing the call."""
        path = Path(request.local_path)
        with path.open("rb") as file:
            length = request.length if request.length is not None else path.stat().st_size
            view = io.BufferedReader(_Slice(file, request.offset, length))
            try:
                tag = TinyTag.get(file_obj=view)
            except TinyTagException:
                return Tags(protected=self._protected)
            duration = tag.duration
            if self._mp4 and not (duration is not None and duration > 0):
                duration = read_fragmented_length(view) or duration
        return Tags(
            title=tag.title or "",
            artist=tag.artist or "",
            album=tag.album or "",
            album_artist=tag.albumartist or "",
            duration_ms=None if duration is None else round(duration * 1000),
            track_number=tag.track,
            protected=self._protected,
        )


def register(registry: Registry) -> None:
    """Add a reader for each audio extension, and one for protected `.m4p` files."""
    for extension in sorted(AUDIO_EXTENSIONS):
        registry.add(TAG_READER, extension, TinytagReader(mp4=extension in MP4_EXTENSIONS))
    registry.add(TAG_READER, PROTECTED_EXTENSION, TinytagReader(protected=True))


plugin = Plugin(api_version=1, register=register)
