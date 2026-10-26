"""The settings API: the household's settings, replaced by an admin at the revision read."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from medleyplay.domain.settings import RemovalOrder, Settings
from medleyplay.web.deps import SettingsDep, SignedInAccount

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsIn(BaseModel):
    """The settings to save, and the revision they were read at; 0 if never saved."""

    storage_limit: int | None = Field(ge=0, examples=[20 * 1024**3])
    removal_order: RemovalOrder = RemovalOrder.LEAST_FAVORITE
    revision: int = Field(ge=0)


class SettingsOut(BaseModel):
    """The settings, and their revision."""

    storage_limit: int | None
    removal_order: RemovalOrder
    revision: int

    @classmethod
    def of(cls, settings: Settings) -> "SettingsOut":
        """Return the API view of `settings`."""
        return cls(
            storage_limit=settings.storage_limit,
            removal_order=settings.removal_order,
            revision=settings.revision,
        )


@router.get("")
def get_settings(_: SignedInAccount, settings: SettingsDep) -> SettingsOut:
    """Return the household's settings."""
    return SettingsOut.of(settings.get())


@router.put("")
def put_settings(body: SettingsIn, me: SignedInAccount, settings: SettingsDep) -> SettingsOut:
    """Replace the settings read at `revision`; a stale revision answers 409. Admins only."""
    saved = settings.put(me, Settings(body.storage_limit, body.removal_order, body.revision))
    return SettingsOut.of(saved)
