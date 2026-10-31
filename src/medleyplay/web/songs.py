"""The songs API: splitting an album file into songs, editing them by id, and unsplitting."""

from typing import Annotated

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from medleyplay.application.segments import SongsView
from medleyplay.domain.catalog import TrackId
from medleyplay.domain.segments import SegmentId, SongRow
from medleyplay.domain.video_text import MAX_SONGS, Song
from medleyplay.web.deps import SignedInAccount, SongsDep
from medleyplay.web.ids import RowId

router = APIRouter(prefix="/api/tracks", tags=["songs"])


class SongIn(BaseModel):
    """A row of the songs editor: the song it keeps by id, or `null` for a new one."""

    model_config = ConfigDict(extra="forbid")

    id: Annotated[StrictInt, Field(ge=1, le=2**63 - 1)] | None = None
    start_ms: Annotated[StrictInt, Field(ge=0, le=2**63 - 1)]
    title: StrictStr
    artist: StrictStr = ""


class RowsIn(BaseModel):
    """The file's songs, in order; a song left out is removed with its Track."""

    model_config = ConfigDict(extra="forbid")

    rows: Annotated[list[SongIn], Field(max_length=MAX_SONGS)] = Field(
        examples=[
            [
                {"id": None, "start_ms": 0, "title": "Intro"},
                {"id": 7, "start_ms": 192_000, "title": "Night Drive", "artist": "Blue Room"},
            ]
        ]
    )


class ListedSongOut(BaseModel):
    """A song of a list found: where it starts, its title, and its artist, or ""."""

    start_ms: int
    title: str
    artist: str


class SongOut(ListedSongOut):
    """A song of a split file: its id, its Track, and where it ends, if known."""

    id: int
    track_id: int
    end_ms: int | None


class SongsOut(BaseModel):
    """A file's songs, whether its length changed since it was split, and the lists found."""

    track_id: int
    length_ms: int | None
    needs_check: bool
    songs: list[SongOut]
    found: list[list[ListedSongOut]]

    @classmethod
    def of(cls, view: SongsView) -> "SongsOut":
        """Return the API view of `view`."""
        return cls(
            track_id=view.track_id,
            length_ms=view.length_ms,
            needs_check=view.needs_check,
            songs=[
                SongOut(
                    id=song.id,
                    track_id=song.track_id,
                    start_ms=song.start_ms,
                    end_ms=song.end_ms,
                    title=song.title,
                    artist=song.artist,
                )
                for song in view.songs
            ],
            found=[[_listed(song) for song in listed] for listed in view.found],
        )


class ListIn(BaseModel):
    """A pasted song list: one song a line, its time first or last."""

    text: Annotated[StrictStr, Field(max_length=100_000)] = Field(
        examples=["00:00 Intro\n1. 03:12 Night Drive - Blue Room\nBlue Room 1:07:40"]
    )


class ListOut(BaseModel):
    """The songs a pasted list names."""

    songs: list[ListedSongOut]


class RemovedOut(BaseModel):
    """How many songs were removed."""

    removed: int


def _listed(song: Song) -> ListedSongOut:
    return ListedSongOut(start_ms=song.start_ms, title=song.title, artist=song.artist)


@router.get("/{track_id}/songs")
def songs(track_id: RowId, _: SignedInAccount, service: SongsDep) -> SongsOut:
    """Return the file's songs, none when it isn't split, and the song lists found for it."""
    return SongsOut.of(service.songs(TrackId(track_id)))


@router.put("/{track_id}/songs")
def save_songs(track_id: RowId, body: RowsIn, _: SignedInAccount, service: SongsDep) -> SongsOut:
    """Make `rows` the file's songs: keep each by its id, add new ones, remove the rest."""
    rows = [
        SongRow(
            None if row.id is None else SegmentId(row.id),
            Song(row.start_ms, row.title, row.artist),
        )
        for row in body.rows
    ]
    return SongsOut.of(service.save(TrackId(track_id), rows))


@router.post("/{track_id}/songs/read")
def read_list(track_id: RowId, body: ListIn, _: SignedInAccount, service: SongsDep) -> ListOut:
    """Read a song list pasted for the file; 422 names the first line that isn't a song."""
    return ListOut(
        songs=[_listed(song) for song in service.read_list(TrackId(track_id), body.text)]
    )


@router.delete("/{track_id}/songs")
def unsplit(track_id: RowId, _: SignedInAccount, service: SongsDep) -> RemovedOut:
    """Remove every song of the file, with its Track."""
    return RemovedOut(removed=service.unsplit(TrackId(track_id)))
