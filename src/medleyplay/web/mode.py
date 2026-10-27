"""The Mode API: what the Mode is now, and its settings, changed by an admin."""

from datetime import datetime

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

from medleyplay.application.mode import MAX_NAME, ModeView
from medleyplay.domain.mode import MeteredNetwork, ModeSetting, ModeSettings, NetworkKind, Reason
from medleyplay.web.deps import JobsDep, ModeDep, SignedInAccount

router = APIRouter(prefix="/api/mode", tags=["mode"])


class NetworkOut(BaseModel):
    """The network the server is on: how it connects, its mark, and whether it looks a hotspot."""

    kind: NetworkKind
    metered_as: str | None
    hotspot_like: bool


class ModeOut(BaseModel):
    """What the Mode is now, and why.

    `since` is when it last went Online or Offline; `online_at`, while settling,
    is when it goes Online if nothing changes. `held_jobs` counts the Jobs waiting
    for Online.
    """

    setting: ModeSetting
    online: bool
    reason: Reason
    network: NetworkOut | None
    since: datetime
    checked_at: datetime | None
    online_at: datetime | None
    held_jobs: int

    @classmethod
    def of(cls, view: ModeView, held_jobs: int) -> "ModeOut":
        """Return the API view of the Mode now, with how many Jobs wait for Online."""
        mode = view.mode
        network = (
            None
            if mode.network is None
            else NetworkOut(
                kind=mode.network.kind,
                metered_as=mode.metered_as,
                hotspot_like=mode.network.hotspot_like,
            )
        )
        return cls(
            setting=mode.setting,
            online=mode.online,
            reason=mode.reason,
            network=network,
            since=mode.since,
            checked_at=view.checked_at,
            online_at=mode.online_at,
            held_jobs=held_jobs,
        )


class MeteredOut(BaseModel):
    """A network marked metered: its name, its subnet, and whether it looks a hotspot."""

    id: int
    name: str
    subnet: str
    hotspot_like: bool

    @classmethod
    def of(cls, network: MeteredNetwork) -> "MeteredOut":
        """Return the API view of a metered network."""
        return cls(
            id=network.id,
            name=network.name,
            subnet=str(network.key.subnet),
            hotspot_like=network.hotspot_like,
        )


class ModeSettingsOut(BaseModel):
    """The Mode's setting, the metered networks, and their revision."""

    setting: ModeSetting
    metered: list[MeteredOut]
    revision: int

    @classmethod
    def of(cls, settings: ModeSettings) -> "ModeSettingsOut":
        """Return the API view of the Mode's settings."""
        return cls(
            setting=settings.setting,
            metered=[MeteredOut.of(network) for network in settings.metered],
            revision=settings.revision,
        )


class ModeSettingIn(BaseModel):
    """The setting to save, and the revision the settings were read at; 0 if never saved."""

    setting: ModeSetting
    revision: int = Field(ge=0)


class MeteredIn(BaseModel):
    """The name to give the network the server is on now."""

    name: str = Field(max_length=4 * MAX_NAME, examples=["iPhone hotspot"])


@router.get("")
def get_mode(_: SignedInAccount, mode: ModeDep, jobs: JobsDep) -> ModeOut:
    """Return what the Mode is now."""
    return ModeOut.of(mode.now(), jobs.held_count())


@router.get("/settings")
def get_mode_settings(_: SignedInAccount, mode: ModeDep) -> ModeSettingsOut:
    """Return the Mode's setting and the metered networks."""
    return ModeSettingsOut.of(mode.settings())


@router.put("/settings")
def put_mode_settings(body: ModeSettingIn, me: SignedInAccount, mode: ModeDep) -> ModeSettingsOut:
    """Change the setting read at `revision`; a stale revision answers 409. Admins only."""
    return ModeSettingsOut.of(mode.put_setting(me, body.setting, body.revision))


@router.post("/metered")
def mark_metered(body: MeteredIn, me: SignedInAccount, mode: ModeDep) -> MeteredOut:
    """Mark the network the server is on now metered; a marked one is renamed. Admins only.

    A network the server can't tell apart, such as one whose router doesn't
    answer, answers 409.
    """
    return MeteredOut.of(mode.mark_metered(me, body.name))


@router.delete("/metered/{network_id}", status_code=status.HTTP_204_NO_CONTENT)
def unmark(network_id: int, me: SignedInAccount, mode: ModeDep) -> Response:
    """Remove a metered network's mark; one already gone answers 204 too. Admins only."""
    mode.unmark(me, network_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
