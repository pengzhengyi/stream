"""Reads a video's title and description for a song's details and a song list.

A title gives the song's title and artist, or an album's name; the description or
the chapters give the songs inside a long file:

```text
title        【无损音质】ハチ 全专《Bremen》
description  00:00 アイネクライネ
             04:12 ゴーゴー幽霊船 - ハチ
             1:02:03 Last

album Bremen by ハチ, with 3 songs starting at 0 s, 252 s, and 3,723 s
```

The reading is a guess from free text, so it never raises: what it cannot read is
left out.
"""

import itertools
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Final

from medleyplay.domain.details import Field, Value, Values, found_value
from medleyplay.domain.errors import InvalidInputError

MAX_SONGS: Final = 300
MIN_SONGS: Final = 2
MIN_SONG_MS: Final = 1_000
ALBUM_SONGS: Final = 3
"""A song list this long makes the video an album."""

_TAG: Final = re.compile(r"【[^】]*】|\[[^\]]*\]")
_QUOTED: Final = re.compile(r"[《「『]([^》」』]*)[》」』]")
_QUOTING_MARKS: Final = re.compile(r"[《》「」『』]")
_ALBUM_WORD: Final = re.compile(
    r"全专辑|全专|专辑|合集|アルバム|(?:\bfull\s+)?\balbum\b", re.IGNORECASE
)
# Spaced hyphen, en dash, or em dash; or a full-width hyphen with or without spaces.
_DASH: Final = re.compile(r"\s+[-\u2013\u2014]\s+|\s*\uff0d\s*")
# Spaced slash, or a full-width slash with or without spaces.
_SLASH: Final = re.compile(r"\s+/\s+|\s*\uff0f\s*")
# Whitespace, `|`, `/`, hyphens, dashes, and the middle dot, full-width forms included.
_SEPARATORS: Final = r"\s|\uff5c/\uff0f\-\u2013\u2014\uff0d\u00b7"
_EDGE: Final = re.compile(rf"^[{_SEPARATORS}]+|[{_SEPARATORS}]+$")

_TIME: Final = r"(?:(\d{1,2}):)?(\d{1,3}):(\d{2})(?![\d:])"
_OPEN: Final = r"[\[(\uff08\u3010]?"
_CLOSE: Final = r"[\])\uff09\u3011]?"
# A time at the start of a line, after an optional number such as `1.` or `01`.
_TIME_FIRST: Final = re.compile(
    rf"^\s*(?:\d{{1,3}}\s*[.)、]?\s+)?{_OPEN}\s*{_TIME}\s*{_CLOSE}(.*)$"
)
_TIME_LAST: Final = re.compile(rf"^(.*?)\s*{_OPEN}\s*(?<![\d:]){_TIME}\s*{_CLOSE}\s*$")


@dataclass(frozen=True)
class Chapter:
    """A chapter of a video, as yt-dlp's info.json lists them."""

    start_ms: int
    title: str


@dataclass(frozen=True)
class VideoText:
    """What a video says about itself."""

    title: str
    description: str = ""
    chapters: tuple[Chapter, ...] = ()


@dataclass(frozen=True)
class Song:
    """One song of a song list: where it starts, its title, and maybe its artist."""

    start_ms: int
    title: str
    artist: str = ""


@dataclass(frozen=True)
class Reading:
    """What a video's text says."""

    values: Values
    """The title, artist, album, and album artist found, each as `found_value` keeps it."""
    songs: tuple[Song, ...]
    """A checked song list, or `()` when none is found."""
    album: bool
    """Whether the video is an album rather than one song."""


def read_video(text: VideoText) -> Reading:
    """Return what `text` says about its song or album, and its song list.

    "【初音ミク】メルト / ryo(supercell)【MV】" has the title "メルト" and the artist
    "ryo(supercell)". Chapters make the song list when there are two or more;
    otherwise the description's timestamped lines do.
    """
    songs = _songs_of(text)
    name, artist, album_word = _read_title(text.title)
    album = album_word or len(songs) >= ALBUM_SONGS
    return Reading(_values(name, artist, album=album), songs, album)


def read_song_list(text: str) -> tuple[Song, ...]:
    """Return the songs of a pasted list, one a line, or raise `InvalidInputError`.

    ```text
    00:00 Intro
    1. 03:12 Night Drive - Blue Room
    Blue Room 1:07:40
    ```

    The error names the first line with no time or no title, or the check the list fails.
    """
    songs: list[Song] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        timed = _timed(line)
        if timed is None:
            message = f"Line {number} has no time."
            raise InvalidInputError(message)
        song = _song(*timed)
        if song is None:
            message = f"Line {number} has no title."
            raise InvalidInputError(message)
        songs.append(song)
    check_songs(songs)
    return tuple(songs)


def check_songs(songs: Sequence[Song]) -> None:
    """Raise `InvalidInputError` unless `songs` is a song list.

    A list has 2 to `MAX_SONGS` songs. Starts rise from 0 or later, each at least a
    second after the one before. Titles and artists are text as `found_value` keeps
    it, and a title is not blank.
    """
    problem = _problem_with(songs)
    if problem is not None:
        raise InvalidInputError(problem)


def _problem_with(songs: Sequence[Song]) -> str | None:
    if len(songs) < MIN_SONGS:
        return f"A song list has at least {MIN_SONGS} songs."
    if len(songs) > MAX_SONGS:
        return f"A song list has at most {MAX_SONGS} songs."
    for number, song in enumerate(songs, start=1):
        if found_value(Field.TITLE, song.title) != song.title:
            return f"The title of song {number} is blank, untrimmed, or too long."
        if (found_value(Field.ARTIST, song.artist) or "") != song.artist:
            return f"The artist of song {number} is untrimmed or too long."
    return _problem_with_starts(songs)


def _problem_with_starts(songs: Sequence[Song]) -> str | None:
    if songs[0].start_ms < 0:
        return "The first song starts from 0 or later."
    for number, (before, after) in enumerate(itertools.pairwise(songs), start=2):
        if after.start_ms - before.start_ms < MIN_SONG_MS:
            return f"Starts rise at least a second a song; song {number} breaks that."
    return None


def _songs_of(text: VideoText) -> tuple[Song, ...]:
    if len(text.chapters) >= MIN_SONGS:
        timed: Iterable[tuple[int, str] | None] = (
            (chapter.start_ms, chapter.title) for chapter in text.chapters
        )
    else:
        timed = (_timed(line) for line in text.description.splitlines())
    songs = tuple(song for item in timed if item is not None and (song := _song(*item)) is not None)
    return songs if _problem_with(songs) is None else ()


def _timed(line: str) -> tuple[int, str] | None:
    """Return a line's start in milliseconds and the rest of it, or `None` with no time."""
    first = _TIME_FIRST.match(line)
    if first is not None and (start := _milliseconds(*first.group(1, 2, 3))) is not None:
        return start, first.group(4)
    last = _TIME_LAST.match(line)
    if last is not None and (start := _milliseconds(*last.group(2, 3, 4))) is not None:
        return start, last.group(1)
    return None


def _milliseconds(hours: str | None, minutes: str, seconds: str) -> int | None:
    if int(seconds) >= 60 or (hours is not None and int(minutes) >= 60):  # noqa: PLR2004
        return None
    return ((int(hours or 0) * 60 + int(minutes)) * 60 + int(seconds)) * 1_000


def _song(start_ms: int, text: str) -> Song | None:
    """Return the song a `title - artist` text names, or `None` when it has no title."""
    title, artist = _split_at(_DASH, _tidy(text))
    kept_title = found_value(Field.TITLE, title)
    if not isinstance(kept_title, str):
        return None
    kept_artist = found_value(Field.ARTIST, artist)
    return Song(start_ms, kept_title, kept_artist if isinstance(kept_artist, str) else "")


def _read_title(raw: str) -> tuple[str, str, bool]:
    """Return a title's name, its artist, and whether it says it is an album."""
    album_word = _ALBUM_WORD.search(raw) is not None
    text = _tidy(_TAG.sub(" ", raw))
    quoted = _QUOTED.search(text)
    if quoted is not None:
        rest = _ALBUM_WORD.sub(" ", text[: quoted.start()] + " " + text[quoted.end() :])
        artist = _tidy(_QUOTING_MARKS.sub(" ", rest))
        return _tidy(quoted.group(1)), artist, album_word
    text = _tidy(_ALBUM_WORD.sub(" ", text))
    artist, title = _split_at(_DASH, text)
    if not title:
        title, artist = _split_at(_SLASH, text)
    return title, artist, album_word


def _split_at(separator: re.Pattern[str], text: str) -> tuple[str, str]:
    """Return the text before and after the first `separator`; the whole text and "" if none."""
    found = separator.search(text)
    if found is None:
        return text, ""
    before, after = _tidy(text[: found.start()]), _tidy(text[found.end() :])
    return (before, after) if before and after else (_tidy(text), "")


def _tidy(text: str) -> str:
    """Return `text` with whitespace collapsed and separators removed from its ends."""
    return _EDGE.sub("", " ".join(text.split()))


def _values(name: str, artist: str, *, album: bool) -> Values:
    wanted: dict[Field, str] = {Field.TITLE: name, Field.ARTIST: artist}
    if album:
        wanted |= {Field.ALBUM: name, Field.ALBUM_ARTIST: artist}
    values: dict[Field, Value] = {}
    for field, text in wanted.items():
        kept = found_value(field, text)
        if kept is not None:
            values[field] = kept
    return values
