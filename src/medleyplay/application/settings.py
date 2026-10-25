"""The household's settings: one versioned document, saved at the revision it was read.

The revision guards every change, so a form left open in a forgotten tab can't
lower the limit over a newer change.
"""

from collections.abc import Callable
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application import Clock
from medleyplay.domain.accounts import Account
from medleyplay.domain.errors import ConflictError, ForbiddenError, InvalidInputError
from medleyplay.domain.settings import RemovalOrder, Settings
from medleyplay.persistence.schema import SettingRow

SETTINGS_ROW: Final = 1

type OnChange = Callable[[str], None]
"""Told what changed, such as `settings`, after the change is committed."""


class SettingsDocument(BaseModel):
    """The settings as stored, version 1."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1] = 1
    storage_limit: int | None = Field(default=None, ge=0)
    removal_order: RemovalOrder = RemovalOrder.LEAST_FAVORITE


class SettingsService:
    """Read the settings, and let an admin replace them."""

    def __init__(
        self, units: sessionmaker[Session], clock: Clock, on_change: OnChange | None = None
    ) -> None:
        """Create a service that tells `on_change` after the settings change."""
        self._units = units
        self._clock = clock
        self._on_change = on_change

    def get(self) -> Settings:
        """Return the settings, or the defaults at revision 0 if they were never saved."""
        with self._units() as db:
            row = db.get(SettingRow, SETTINGS_ROW)
            if row is None:
                return Settings()
            document = SettingsDocument.model_validate(row.document)
            return Settings(document.storage_limit, document.removal_order, row.revision)

    def put(self, caller: Account, settings: Settings) -> Settings:
        """Replace the settings read at `settings.revision`; return them at their new revision.

        A revision other than the current one is a `ConflictError`: someone saved
        since it was read.
        """
        if not caller.is_admin:
            message = "Only an admin can change the settings."
            raise ForbiddenError(message)
        try:
            document = SettingsDocument(
                storage_limit=settings.storage_limit, removal_order=settings.removal_order
            ).model_dump(mode="json")
        except ValidationError as error:
            where = ".".join(str(part) for part in error.errors()[0]["loc"])
            message = f"The settings aren't valid at {where}: {error.errors()[0]['msg']}"
            raise InvalidInputError(message) from None
        revision = settings.revision + 1
        with self._units.begin() as db:
            if settings.revision == 0:
                saved = (
                    db.connection()
                    .execute(
                        insert(SettingRow)
                        .values(
                            id=SETTINGS_ROW, document=document, revision=1, updated_at=self._clock()
                        )
                        .on_conflict_do_nothing()
                    )
                    .rowcount
                )
            else:
                saved = (
                    db.connection()
                    .execute(
                        update(SettingRow)
                        .where(
                            SettingRow.id == SETTINGS_ROW, SettingRow.revision == settings.revision
                        )
                        .values(document=document, revision=revision, updated_at=self._clock())
                    )
                    .rowcount
                )
        if saved != 1:
            message = (
                f"The settings were saved since revision {settings.revision}; read them again."
            )
            raise ConflictError(message)
        if self._on_change is not None:
            self._on_change("settings")
        return self.get()
