"""The details API: a Track's values and where each came from, and the household's own."""

from collections.abc import Mapping
from typing import Annotated

from fastapi import APIRouter
from pydantic import BaseModel, Field

from medleyplay.application.details import DetailsView
from medleyplay.domain.catalog import TrackId
from medleyplay.domain.details import Field as Detail
from medleyplay.domain.details import Origin, Shown
from medleyplay.web.deps import DetailsDep, SignedInAccount

router = APIRouter(prefix="/api/tracks", tags=["details"])

type DetailValue = str | int


class ShownOut(BaseModel):
    """The value a field shows, and the origin it came from."""

    value: DetailValue
    origin: Origin


class DetailsOut(BaseModel):
    """A Track's shown values, what each origin says, and what would show without the household.

    A field no origin gives is absent from `shown`; `found` is what would show if the
    household's values were dropped.
    """

    track_id: int
    shown: dict[str, ShownOut]
    found: dict[str, ShownOut]
    origins: dict[Origin, dict[str, DetailValue]]

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

    track_ids: Annotated[list[int], Field(min_length=1, max_length=10_000)]
    values: dict[str, DetailValue | None] = Field(
        examples=[{"album": "Re:Start", "album_artist": "wowaka"}]
    )


class ManyOut(BaseModel):
    """How many Tracks changed."""

    changed: int


@router.get("/{track_id}/details")
def details(track_id: int, _: SignedInAccount, service: DetailsDep) -> DetailsOut:
    """Return the Track's shown values, and what each origin says."""
    return DetailsOut.of(service.details(TrackId(track_id)))


@router.put("/{track_id}/details")
def put_details(
    track_id: int, body: HouseholdIn, _: SignedInAccount, service: DetailsDep
) -> DetailsOut:
    """Make `values` the household's values for the Track, replacing its earlier ones."""
    return DetailsOut.of(service.put_household(TrackId(track_id), body.values))


@router.post("/details")
def set_on_many(body: ManyIn, _: SignedInAccount, service: DetailsDep) -> ManyOut:
    """Set the given household values on every Track named; either all change or none."""
    return ManyOut(changed=service.set_on_many(map(TrackId, body.track_ids), body.values))
