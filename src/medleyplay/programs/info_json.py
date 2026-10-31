"""Reads the video details of a yt-dlp `.info.json`, a file nobody vouches for.

```json
{
  "title": "ハチ 全专《Bremen》",
  "description": "00:00 アイネクライネ",
  "chapters": [{"start_time": 0.0, "title": "アイネクライネ"}]
}
```

Only the title, the description, and each chapter's start and title are read; the
file is parsed as data and nothing in it is followed or run.
"""

import json
import math
from typing import Final

from pydantic import BaseModel, ConfigDict

MAX_BYTES: Final = 5 * 1024 * 1024
"""A file longer than this is not read."""
MAX_TITLE: Final = 1_000
MAX_DESCRIPTION: Final = 20_000
"""Text is cut to the limits of a pasted title and description; a chapter's to a title's."""
MAX_CHAPTERS: Final = 1_000
"""Chapters past this many are left out; a song list holds far fewer."""
MAX_START_MS: Final = 7 * 24 * 3600 * 1000
"""A chapter starting later than a week in is left out."""


class InfoJsonError(ValueError):
    """The file can't be read as a video's details; the message says why."""


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class InfoChapter(_Model):
    """A chapter: where it starts, in milliseconds, and its title."""

    start_ms: int
    title: str


class InfoText(_Model):
    """What a video's details say: its title, description, and chapters."""

    title: str = ""
    description: str = ""
    chapters: tuple[InfoChapter, ...] = ()


def parse_info_json(data: bytes) -> InfoText:
    """Return the words in the document `data`, or raise `InfoJsonError`.

    A title or description that isn't text is empty. A chapter is kept when its
    `start_time` is a finite number of seconds from 0 and its `title` is text.
    """
    try:
        document = json.loads(data)
    except (ValueError, RecursionError) as error:  # ValueError covers bad UTF-8 and syntax.
        message = f"isn't valid JSON ({type(error).__name__})"
        raise InfoJsonError(message) from error
    if not isinstance(document, dict):
        message = "isn't a JSON object"
        raise InfoJsonError(message)
    chapters = document.get("chapters")
    return InfoText(
        title=_text(document.get("title"))[:MAX_TITLE],
        description=_text(document.get("description"))[:MAX_DESCRIPTION],
        chapters=_chapters(chapters) if isinstance(chapters, list) else (),
    )


def _text(value: object) -> str:
    # JSON can name half of a UTF-16 pair, which no UTF-8 text holds; it reads as U+FFFD.
    if not isinstance(value, str):
        return ""
    return value.encode("utf-16", "surrogatepass").decode("utf-16", "replace")


def _chapters(entries: list[object]) -> tuple[InfoChapter, ...]:
    chapters = (_chapter(entry) for entry in entries)
    return tuple(chapter for chapter in chapters if chapter is not None)[:MAX_CHAPTERS]


def _chapter(entry: object) -> InfoChapter | None:
    if not isinstance(entry, dict):
        return None
    start, title = entry.get("start_time"), entry.get("title")
    if isinstance(start, bool) or not isinstance(start, int | float) or not isinstance(title, str):
        return None
    try:
        milliseconds = start * 1000
        if not math.isfinite(milliseconds) or not 0 <= milliseconds <= MAX_START_MS:
            return None
        return InfoChapter(start_ms=round(milliseconds), title=_text(title)[:MAX_TITLE])
    except OverflowError:  # A whole number too large for a float.
        return None
