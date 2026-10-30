"""The details API: a Track's values and where each came from, and the household's own."""

from collections.abc import Mapping
from typing import Annotated

from fastapi import APIRouter
from pydantic import BaseModel, Field, StrictInt, StrictStr

from medleyplay.application.details import DetailsView, VideoRead
from medleyplay.domain.catalog import TrackId
from medleyplay.domain.details import Field as Detail
from medleyplay.domain.details import Origin, Shown
from medleyplay.domain.video_text import VideoText
from medleyplay.web.deps import DetailsDep, SignedInAccount
from medleyplay.web.ids import RowId

router = APIRouter(prefix="/api/tracks", tags=["details"])

# Strict, so JSON `true` or `3.0` is refused rather than taken as a whole number.
type DetailValue = StrictStr | StrictInt


class ShownOut(BaseModel):
    """The value a field shows, and the origin it came from."""

    value: DetailValue
    origin: Origin


class VideoTextIn(BaseModel):
    """A video's title and description, as the site shows them."""

    title: Annotated[StrictStr, Field(max_length=1_000)] = Field(examples=["ハチ 全专《Bremen》"])
    description: Annotated[StrictStr, Field(max_length=20_000)] = Field(
        default="", examples=["00:00 アイネクライネ\n04:12 ゴーゴー幽霊船 - ハチ"]
    )


class VideoTextOut(BaseModel):
    """The video's text the `video` values were read from."""

    title: str
    description: str


class DetailsOut(BaseModel):
    """A Track's shown values, what each origin says, and what would show without the household.

    A field no origin gives is absent from `shown`; `found` is what would show if the
    household's values were dropped. `video_text` is the video's text the `video`
    values were read from, if any was.
    """

    track_id: int
    shown: dict[str, ShownOut]
    found: dict[str, ShownOut]
    origins: dict[Origin, dict[str, DetailValue]]
    video_text: VideoTextOut | None

    @classmethod
    def of(cls, view: DetailsView) -> "DetailsOut":
        """Return the API view of `view`."""
        return cls(
            track_id=view.track_id,
            shown=_shown_out(view.shown),
            found=_shown_out(view.found),
            origins={
                origin: {str(field): value for field, value in values.items()}
                for origin, values in view.values.items()
            },
            video_text=None
            if view.video_text is None
            else VideoTextOut(title=view.video_text.title, description=view.video_text.description),
        )


class SongOut(BaseModel):
    """A song of a song list: where it starts, its title, and its artist, or ""."""

    start_ms: int
    title: str
    artist: str


class VideoReadOut(BaseModel):
    """A Track's details once its video's text is read, and the songs that text lists."""

    details: DetailsOut
    songs: list[SongOut]

    @classmethod
    def of(cls, read: VideoRead) -> "VideoReadOut":
        """Return the API view of `read`."""
        return cls(
            details=DetailsOut.of(read.details),
            songs=[
                SongOut(start_ms=song.start_ms, title=song.title, artist=song.artist)
                for song in read.songs
            ],
        )


def _shown_out(values: Mapping[Detail, Shown]) -> dict[str, ShownOut]:
    return {
        field: ShownOut(value=found.value, origin=found.origin) for field, found in values.items()
    }


class HouseholdIn(BaseModel):
    """The household's values: text, empty to show nothing, or whole numbers."""

    values: dict[str, DetailValue] = Field(
        examples=[{"title": "Night Drive", "artist": "Blue Room", "year": 2016}]
    )


class ManyIn(BaseModel):
    """Household values to set on several Tracks; `null` drops one, so the next origin shows."""

    track_ids: Annotated[list[RowId], Field(min_length=1, max_length=10_000)]
    values: dict[str, DetailValue | None] = Field(
        examples=[{"album": "Re:Start", "album_artist": "wowaka"}]
    )


class ManyOut(BaseModel):
    """How many Tracks changed."""

    changed: int


@router.get("/{track_id}/details")
def details(track_id: RowId, _: SignedInAccount, service: DetailsDep) -> DetailsOut:
    """Return the Track's shown values, and what each origin says."""
    return DetailsOut.of(service.details(TrackId(track_id)))


@router.put("/{track_id}/details")
def put_details(
    track_id: RowId, body: HouseholdIn, _: SignedInAccount, service: DetailsDep
) -> DetailsOut:
    """Make `values` the household's values for the Track, replacing its earlier ones."""
    return DetailsOut.of(service.put_household(TrackId(track_id), body.values))


@router.post("/details")
def set_on_many(body: ManyIn, _: SignedInAccount, service: DetailsDep) -> ManyOut:
    """Set the given household values on every Track named; either all change or none."""
    return ManyOut(changed=service.set_on_many(map(TrackId, body.track_ids), body.values))


@router.post("/{track_id}/video-text")
def read_video_text(
    track_id: RowId, body: VideoTextIn, _: SignedInAccount, service: DetailsDep
) -> VideoReadOut:
    """Read a video's pasted title and description as the Track's `video` values."""
    read = service.read_video_text(TrackId(track_id), VideoText(body.title, body.description))
    return VideoReadOut.of(read)
