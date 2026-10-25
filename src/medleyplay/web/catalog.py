"""The catalog API: Tracks with your favorites, ratings, and plays, and your Playlists."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Response, status
from pydantic import AwareDatetime, BaseModel, Field

from medleyplay.domain.catalog import (
    MAX_PLAYLIST_LENGTH,
    MAX_RATING,
    MIN_RATING,
    Availability,
    Playlist,
    PlaylistId,
    Track,
    TrackId,
)
from medleyplay.domain.playback import PlayId
from medleyplay.web.deps import CatalogDep, SignedInAccount

router = APIRouter(prefix="/api", tags=["catalog"])


class TrackOut(BaseModel):
    """A Track with the signed-in Account's own state."""

    id: int
    title: str
    artist: str
    album: str
    album_artist: str
    duration_ms: int | None
    added_at: datetime
    favorite: bool
    rating: int | None
    play_count: int
    last_played_at: datetime | None
    availability: Availability

    @classmethod
    def of(cls, track: Track) -> "TrackOut":
        """Return the API view of `track`."""
        details = track.details
        return cls(
            id=track.id,
            title=details.title,
            artist=details.artist,
            album=details.album,
            album_artist=details.album_artist,
            duration_ms=details.duration_ms,
            added_at=track.added_at,
            favorite=track.favorite,
            rating=track.rating,
            play_count=track.play_count,
            last_played_at=track.last_played_at,
            availability=track.availability,
        )


class FavoriteIn(BaseModel):
    """Whether a Track is a favorite: an absolute value, so a retry is harmless."""

    favorite: bool


class RatingIn(BaseModel):
    """A rating in stars, or `null` to clear it."""

    rating: int | None = Field(ge=MIN_RATING, le=MAX_RATING)


class PlayIn(BaseModel):
    """A play of a Track, and when it started; a time in the future is taken as now."""

    track_id: int
    played_at: AwareDatetime


class PlaylistIn(BaseModel):
    """A whole Playlist: its name and its Tracks in order."""

    name: str = Field(examples=["Morning"])
    track_ids: list[int] = Field(max_length=MAX_PLAYLIST_LENGTH)


class PlaylistOut(BaseModel):
    """A Playlist."""

    id: uuid.UUID
    name: str
    track_ids: list[int]
    updated_at: datetime

    @classmethod
    def of(cls, playlist: Playlist) -> "PlaylistOut":
        """Return the API view of `playlist`."""
        return cls(
            id=playlist.id,
            name=playlist.name,
            track_ids=list(playlist.track_ids),
            updated_at=playlist.updated_at,
        )


@router.get("/tracks")
def list_tracks(me: SignedInAccount, catalog: CatalogDep) -> list[TrackOut]:
    """Return every Track in the catalog."""
    return [TrackOut.of(track) for track in catalog.list_tracks(me.id)]


@router.get("/tracks/{track_id}")
def get_track(track_id: int, me: SignedInAccount, catalog: CatalogDep) -> TrackOut:
    """Return one Track."""
    return TrackOut.of(catalog.get_track(me.id, TrackId(track_id)))


@router.put("/tracks/{track_id}/favorite")
def set_favorite(
    track_id: int, body: FavoriteIn, me: SignedInAccount, catalog: CatalogDep
) -> TrackOut:
    """Mark or unmark a Track as your favorite."""
    track = catalog.set_favorite(me.id, TrackId(track_id), favorite=body.favorite)
    return TrackOut.of(track)


@router.put("/tracks/{track_id}/rating")
def set_rating(track_id: int, body: RatingIn, me: SignedInAccount, catalog: CatalogDep) -> TrackOut:
    """Rate a Track 1-5 stars, or clear your rating."""
    return TrackOut.of(catalog.set_rating(me.id, TrackId(track_id), body.rating))


@router.put("/plays/{play_id}")
def record_play(
    play_id: uuid.UUID, body: PlayIn, me: SignedInAccount, catalog: CatalogDep
) -> TrackOut:
    """Record a play under an id you choose; sending it again changes nothing."""
    track = catalog.record_play(me.id, PlayId(play_id), TrackId(body.track_id), body.played_at)
    return TrackOut.of(track)


@router.get("/playlists")
def list_playlists(me: SignedInAccount, catalog: CatalogDep) -> list[PlaylistOut]:
    """Return your Playlists."""
    return [PlaylistOut.of(playlist) for playlist in catalog.list_playlists(me.id)]


@router.get("/playlists/{playlist_id}")
def get_playlist(playlist_id: uuid.UUID, me: SignedInAccount, catalog: CatalogDep) -> PlaylistOut:
    """Return one of your Playlists."""
    return PlaylistOut.of(catalog.get_playlist(me.id, PlaylistId(playlist_id)))


@router.put("/playlists/{playlist_id}")
def put_playlist(
    playlist_id: uuid.UUID,
    body: PlaylistIn,
    response: Response,
    me: SignedInAccount,
    catalog: CatalogDep,
) -> PlaylistOut:
    """Create or replace a Playlist under an id you choose; 201 when new, 200 when replaced."""
    playlist, created = catalog.put_playlist(
        me.id, PlaylistId(playlist_id), body.name, [TrackId(i) for i in body.track_ids]
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return PlaylistOut.of(playlist)


@router.delete("/playlists/{playlist_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_playlist(playlist_id: uuid.UUID, me: SignedInAccount, catalog: CatalogDep) -> None:
    """Delete one of your Playlists; deleting it twice is fine."""
    catalog.delete_playlist(me.id, PlaylistId(playlist_id))
