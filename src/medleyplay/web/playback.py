"""The playback API: asking to play a Track, and serving a Source's audio with Range."""

from typing import Any, Final, Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from medleyplay.application.playback import Preparing, Ready
from medleyplay.domain.catalog import Availability, SourceId, TrackId
from medleyplay.web.audio import audio_response
from medleyplay.web.deps import PlaybackDep, SignedInAccount
from medleyplay.web.ids import RowId

router = APIRouter(prefix="/api", tags=["playback"])


class ReadyOut(BaseModel):
    """The Track plays from `audio_url` now."""

    state: Literal["ready"] = "ready"
    source_id: int
    audio_url: str
    media_type: str


class PreparingOut(BaseModel):
    """The Track plays once the Job `job_id` succeeds; ask again then."""

    state: Literal["preparing"] = "preparing"
    source_id: int
    job_id: int


class UnplayableOut(BaseModel):
    """No Source of the Track can play now; `availability` says why."""

    state: Literal["unplayable"] = "unplayable"
    availability: Availability


@router.post("/tracks/{track_id}/playback")
def play(
    track_id: RowId, me: SignedInAccount, playback: PlaybackDep
) -> ReadyOut | PreparingOut | UnplayableOut:
    """Pick the Source a Track plays from, preparing it first when it must be."""
    found = playback.play(me, TrackId(track_id))
    if isinstance(found, Ready):
        return ReadyOut(
            source_id=found.source_id,
            audio_url=f"/api/sources/{found.source_id}/audio",
            media_type=found.media_type,
        )
    if isinstance(found, Preparing):
        return PreparingOut(source_id=found.source_id, job_id=found.job.id)
    return UnplayableOut(availability=found.availability)


_AUDIO: Final = "/sources/{source_id}/audio"
_AUDIO_RESPONSES: Final[dict[int | str, dict[str, Any]]] = {
    200: {"content": {"audio/*": {}}},
    206: {"description": "Part of the audio"},
}


@router.get(_AUDIO, response_class=Response, responses=_AUDIO_RESPONSES)
@router.head(_AUDIO, response_class=Response, operation_id="audio_headers")
def audio(
    source_id: RowId, request: Request, _: SignedInAccount, playback: PlaybackDep
) -> Response:
    """Serve a Source's audio, with Range; 409 when it must be prepared first."""
    return audio_response(request, playback.open_audio(SourceId(source_id)))
