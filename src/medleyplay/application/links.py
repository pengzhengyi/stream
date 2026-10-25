"""Adding music from a link: looking a video up, then adding the parts the household chose.

The core recognizes the link by its host before any plugin sees it, and checks
the link the plugin ended on again. Adding doesn't trust the client: it reads
the video again, from a short memory of recent lookups, and checks every part and
the quality against it.
"""

import threading
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application import Clock
from medleyplay.application.catalog import CatalogService
from medleyplay.application.downloads import QUALITY_DETAIL, DownloadService
from medleyplay.application.plugins import PluginService
from medleyplay.domain.accounts import Account
from medleyplay.domain.catalog import SourceId, SourceKey, SourceState, TrackDetails, TrackId
from medleyplay.domain.errors import InvalidInputError
from medleyplay.domain.jobs import Job
from medleyplay.domain.links import part_locator, recognize_link
from medleyplay.persistence.schema import DownloadRow, SourceRow
from medleyplay.plugin_api import (
    BEST_QUALITY,
    CANONICALIZE,
    READ_VIDEO,
    AudioQuality,
    Canonicalize,
    ReadVideo,
    VideoDetails,
    VideoStatus,
)

LOOKUP_MEMORY: Final = timedelta(minutes=10)
MAX_PARTS_PER_ADD: Final = 50
MAX_TEXT: Final = 512


@dataclass(frozen=True)
class PartLookup:
    """One part of a looked-up video, and its Track when it is already in the catalog."""

    part: int
    title: str
    duration_ms: int | None
    track_id: TrackId | None


@dataclass(frozen=True)
class Lookup:
    """A video a link names: its details, its parts, and the qualities it can be added at."""

    kind: str
    video: str
    title: str
    uploader: str
    parts: tuple[PartLookup, ...]
    qualities: tuple[AudioQuality, ...]


@dataclass(frozen=True)
class PartChoice:
    """A part the household chose to add, under the title and artist it chose."""

    part: int
    title: str
    artist: str


@dataclass(frozen=True)
class Added:
    """A part's Track and Source, and the Job downloading it when one is needed."""

    part: int
    track_id: TrackId
    source_id: SourceId
    job: Job | None


@dataclass(frozen=True)
class _Remembered:
    details: VideoDetails
    read_at: datetime


class LinkService:
    """Look links up, and add the parts the household chose as Tracks."""

    def __init__(
        self,
        units: sessionmaker[Session],
        clock: Clock,
        plugins: PluginService,
        catalog: CatalogService,
        downloads: DownloadService,
    ) -> None:
        """Create a service that adds Tracks to `catalog` and downloads them with `downloads`."""
        self._units = units
        self._clock = clock
        self._plugins = plugins
        self._catalog = catalog
        self._downloads = downloads
        # One lookup at a time: the plugin host answers one call at a time anyway,
        # and a burst of lookups shouldn't reach the site at once.
        self._reading = threading.Lock()
        self._remembered: dict[tuple[str, str], _Remembered] = {}

    def lookup(self, caller: Account, link: str) -> Lookup:
        """Return the video `link` names, with each part's Track if it is already added.

        A link that isn't a video, or a video that is gone or needs a login,
        raises `InvalidInputError` saying why.
        """
        del caller  # Any signed-in Account may look a link up.
        kind, video, details = self._resolve(link)
        tracks = self._tracks(kind, [part_locator(video, part.part) for part in details.parts])
        return Lookup(
            kind=kind,
            video=video,
            title=details.title,
            uploader=details.uploader,
            parts=tuple(
                PartLookup(
                    part.part,
                    part.title,
                    part.duration_ms,
                    tracks.get(part_locator(video, part.part)),
                )
                for part in details.parts
            ),
            qualities=details.qualities,
        )

    def add(
        self, caller: Account, link: str, quality: str, parts: Sequence[PartChoice]
    ) -> list[Added]:
        """Add the chosen parts as Tracks, and start downloading each one without a Download.

        A part already in the catalog keeps its Track and quality, and adding again
        returns the same Tracks and Jobs.
        """
        kind, video, details = self._resolve(link)
        _check_choice(details, quality, parts)
        durations = {part.part: part.duration_ms for part in details.parts}
        added = []
        for choice in parts:
            key = SourceKey(kind, part_locator(video, choice.part))
            track_id = self._catalog.add_track(
                key,
                TrackDetails(
                    title=choice.title.strip(),
                    artist=choice.artist.strip(),
                    duration_ms=durations[choice.part],
                ),
                {QUALITY_DETAIL: quality},
            )
            source_id, needs_download = self._source(key)
            job = self._downloads.start(caller, source_id) if needs_download else None
            added.append(Added(choice.part, track_id, source_id, job))
        return added

    def _resolve(self, link: str) -> tuple[str, str, VideoDetails]:
        kind = recognize_link(link)
        canonical = self._plugins.call(CANONICALIZE, kind, Canonicalize(link=link.strip()))
        # The plugin may have followed a short link; where it ended must be the site too.
        if recognize_link(canonical.link) != kind:  # pragma: no cover -- one kind per host
            raise InvalidInputError(canonical.link)
        if canonical.video is None:
            message = "The link doesn't name a video."
            raise InvalidInputError(message)
        details = self._read(kind, canonical.video)
        if details.status is not VideoStatus.OK:
            raise InvalidInputError(details.message or f"The video is {details.status}.")
        return kind, canonical.video, details

    def _read(self, kind: str, video: str) -> VideoDetails:
        with self._reading:
            now = self._clock()
            remembered = self._remembered.get((kind, video))
            if remembered is not None and now - remembered.read_at < LOOKUP_MEMORY:
                return remembered.details
            details = self._plugins.call(READ_VIDEO, kind, ReadVideo(video=video))
            self._remembered = {
                key: kept
                for key, kept in self._remembered.items()
                if now - kept.read_at < LOOKUP_MEMORY
            }
            self._remembered[kind, video] = _Remembered(details, now)
            return details

    def _tracks(self, kind: str, locators: list[str]) -> dict[str, TrackId]:
        with self._units() as db:
            rows = db.execute(
                select(SourceRow.locator, SourceRow.track_id).where(
                    SourceRow.kind == kind, SourceRow.locator.in_(locators)
                )
            ).all()
        return {locator: TrackId(track_id) for locator, track_id in rows}

    def _source(self, key: SourceKey) -> tuple[SourceId, bool]:
        """Return the Source's id, and whether it needs downloading."""
        with self._units() as db:
            row = db.scalars(
                select(SourceRow).where(
                    SourceRow.kind == key.kind, SourceRow.locator == key.locator
                )
            ).one()
            downloaded = db.get(DownloadRow, row.id) is not None
            return SourceId(row.id), not downloaded and row.state != SourceState.UNAVAILABLE


def _check_choice(details: VideoDetails, quality: str, parts: Sequence[PartChoice]) -> None:
    numbers = [choice.part for choice in parts]
    if not 1 <= len(numbers) <= MAX_PARTS_PER_ADD or len(set(numbers)) != len(numbers):
        message = f"Choose 1 to {MAX_PARTS_PER_ADD} different parts."
        raise InvalidInputError(message)
    known = {part.part for part in details.parts}
    if unknown := sorted(set(numbers) - known):
        message = f"The video has no part {unknown[0]}."
        raise InvalidInputError(message)
    if quality != BEST_QUALITY and quality not in {each.id for each in details.qualities}:
        message = f"The video can't be added at the quality {quality!r}."
        raise InvalidInputError(message)
    for choice in parts:
        if not 1 <= len(choice.title.strip()) <= MAX_TEXT or len(choice.artist) > MAX_TEXT:
            message = f"A title is 1 to {MAX_TEXT} characters, and an artist at most {MAX_TEXT}."
            raise InvalidInputError(message)
