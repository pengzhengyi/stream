"""The storage API: the space Downloads use, what the policy wants, and a plan at another limit."""

from collections.abc import Mapping
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel

from medleyplay.application.policy import Evaluation, Storage
from medleyplay.domain.catalog import TrackId
from medleyplay.domain.policy import Plan, Remove, Shortfall
from medleyplay.web.deps import PolicyDep, SignedInAccount

router = APIRouter(prefix="/api/storage", tags=["storage"])


class ShortfallOut(BaseModel):
    """A wanted Track with no Download yet, and why."""

    track_id: int
    reason: Shortfall


class AccountUseOut(BaseModel):
    """The space one Account's wanted Tracks hold."""

    account_id: int
    bytes: int


class RemovalOut(BaseModel):
    """A Download, or a cache copy, a plan removes."""

    kind: Literal["download", "cache"]
    source_id: int | None
    size: int


class StartOut(BaseModel):
    """A Download a plan starts, and the space it reserves."""

    track_id: int
    source_id: int
    estimate: int


class PlanOut(BaseModel):
    """What a plan removes and starts, and what it couldn't do."""

    removals: list[RemovalOut]
    starts: list[StartOut]
    shortfalls: list[ShortfallOut]

    @classmethod
    def of(cls, plan: Plan) -> "PlanOut":
        """Return the API view of `plan`."""
        return cls(
            removals=[
                RemovalOut(kind="download", source_id=each.source_id, size=each.size)
                if isinstance(each, Remove)
                else RemovalOut(kind="cache", source_id=None, size=each.size)
                for each in plan.removals
            ],
            starts=[
                StartOut(track_id=each.track_id, source_id=each.source_id, estimate=each.estimate)
                for each in plan.starts
            ],
            shortfalls=_shortfalls(plan.shortfalls),
        )


class EvaluationOut(BaseModel):
    """What the last evaluation did, and what it couldn't do."""

    at: datetime
    removed: int
    started: int
    shortfalls: list[ShortfallOut]
    error: str | None
    failed_actions: list[str]

    @classmethod
    def of(cls, evaluation: Evaluation) -> "EvaluationOut":
        """Return the API view of `evaluation`."""
        return cls(
            at=evaluation.at,
            removed=evaluation.removed,
            started=evaluation.started,
            shortfalls=_shortfalls(evaluation.shortfalls),
            error=evaluation.error,
            failed_actions=list(evaluation.failed_actions),
        )


class StorageOut(BaseModel):
    """The storage the policy governs; the figures are null when `error` says they can't be read."""

    limit: int | None
    downloads: int | None
    cache: int | None
    reserved: int | None
    free: int | None
    disk_size: int | None
    min_free: int | None
    wanted: int | None
    wanted_by_account: list[AccountUseOut]
    last_evaluation: EvaluationOut | None
    error: str | None
    preview: PlanOut | None

    @classmethod
    def of(cls, storage: Storage) -> "StorageOut":
        """Return the API view of `storage`."""
        return cls(
            limit=storage.limit,
            downloads=storage.downloads,
            cache=storage.cache,
            reserved=storage.reserved,
            free=storage.free,
            disk_size=storage.disk_size,
            min_free=storage.min_free,
            wanted=storage.wanted,
            wanted_by_account=[
                AccountUseOut(account_id=account_id, bytes=held)
                for account_id, held in sorted(storage.wanted_by_account.items())
            ],
            last_evaluation=None if storage.last is None else EvaluationOut.of(storage.last),
            error=storage.error,
            preview=None if storage.preview is None else PlanOut.of(storage.preview),
        )


def _shortfalls(shortfalls: Mapping[TrackId, Shortfall]) -> list[ShortfallOut]:
    return [ShortfallOut(track_id=track, reason=why) for track, why in sorted(shortfalls.items())]


@router.get("")
def get_storage(
    me: SignedInAccount,
    policy: PolicyDep,
    limit: Annotated[int | None, Query(ge=0, description="Preview a plan at this limit")] = None,
) -> StorageOut:
    """Return the storage now and the last evaluation; with `limit`, an admin's preview."""
    return StorageOut.of(policy.storage(me, preview_limit=limit))
