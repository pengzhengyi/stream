"""The links API: looking a pasted link up, and adding the parts the household chose."""

from typing import Annotated

from fastapi import APIRouter
from pydantic import BaseModel, Field

from medleyplay.application.links import Added, Lookup, PartChoice
from medleyplay.domain.jobs import JobView
from medleyplay.plugin_api import BEST_QUALITY
from medleyplay.web.deps import LinksDep, SignedInAccount
from medleyplay.web.jobs import JobOut

router = APIRouter(prefix="/api/links", tags=["links"])

type Link = Annotated[str, Field(max_length=2048, examples=["https://b23.tv/abc123"])]


class LinkIn(BaseModel):
    """A link to look up, as pasted."""

    link: Link


class PartOut(BaseModel):
    """One part of the video, and its Track when it is already in the catalog."""

    part: int
    title: str
    duration_ms: int | None
    track_id: int | None


class QualityOut(BaseModel):
    """A quality the video can be added at."""

    id: str
    label: str
    kbps: int | None


class LookupOut(BaseModel):
    """The video a link names."""

    kind: str
    video: str
    title: str
    uploader: str
    parts: list[PartOut]
    qualities: list[QualityOut]

    @classmethod
    def of(cls, lookup: Lookup) -> "LookupOut":
        """Return the API view of `lookup`."""
        return cls(
            kind=lookup.kind,
            video=lookup.video,
            title=lookup.title,
            uploader=lookup.uploader,
            parts=[PartOut(**vars(part)) for part in lookup.parts],
            qualities=[QualityOut(**quality.model_dump()) for quality in lookup.qualities],
        )


class PartIn(BaseModel):
    """A part to add, under the title and artist the household chose."""

    part: int = Field(ge=1)
    title: str = Field(max_length=512, examples=["Night Drive"])
    artist: str = Field(default="", max_length=512, examples=["Blue Room"])


class AddIn(BaseModel):
    """The parts of a link's video to add, at a quality: one the lookup listed, or `best`."""

    link: Link
    quality: str = Field(default=BEST_QUALITY, max_length=32)
    parts: list[PartIn] = Field(max_length=50)


class AddedOut(BaseModel):
    """A part's Track and Source, and the Job downloading it, if one is needed."""

    part: int
    track_id: int
    source_id: int
    job: JobOut | None


@router.post("/lookup")
def look_up(body: LinkIn, me: SignedInAccount, links: LinksDep) -> LookupOut:
    """Return the video a link names; a link that isn't one, or can't be added, answers 422."""
    return LookupOut.of(links.lookup(me, body.link))


@router.post("")
def add(body: AddIn, me: SignedInAccount, links: LinksDep) -> list[AddedOut]:
    """Add the chosen parts as Tracks and start downloading them; adding again adds nothing new."""
    choices = [PartChoice(part.part, part.title, part.artist) for part in body.parts]
    return [_added(each) for each in links.add(me, body.link, body.quality, choices)]


def _added(added: Added) -> AddedOut:
    job = None if added.job is None else JobOut.of(JobView(added.job))
    return AddedOut(part=added.part, track_id=added.track_id, source_id=added.source_id, job=job)
