"""Each Account's preferences: one versioned document per Account, saved at the revision read.

The revision guards every change, so a page left open on another device can't
put back shortcuts changed since.
"""

from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError
from sqlalchemy import Insert, Update, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application import Clock
from medleyplay.domain.accounts import AccountId
from medleyplay.domain.errors import ConflictError, InvalidInputError
from medleyplay.domain.preferences import Preferences
from medleyplay.persistence.schema import PreferenceRow

MAX_COMMANDS: Final = 64
MAX_KEYS: Final = 8

type _Command = Annotated[str, StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9]{0,31}$")]
# Modifiers and a key, joined by `+`, in lower case, as the page writes them.
type _Keys = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(\+[a-z0-9]+){0,4}$")]


class PreferencesDocument(BaseModel):
    """The preferences as stored, version 1."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1] = 1
    shortcuts: dict[_Command, Annotated[list[_Keys], Field(max_length=MAX_KEYS)]] | None = Field(
        default=None, max_length=MAX_COMMANDS
    )


class PreferencesService:
    """Read an Account's preferences, and let it replace them."""

    def __init__(self, units: sessionmaker[Session], clock: Clock) -> None:
        """Create a service over the database `units` opens."""
        self._units = units
        self._clock = clock

    def get(self, account_id: AccountId) -> Preferences:
        """Return the Account's preferences, or none at revision 0 if it never saved them."""
        with self._units() as db:
            row = db.get(PreferenceRow, account_id)
            if row is None:
                return Preferences()
            return _preferences_of(PreferencesDocument.model_validate(row.document), row.revision)

    def put(self, account_id: AccountId, preferences: Preferences) -> Preferences:
        """Replace the preferences read at `preferences.revision`; return them at the next.

        A revision other than the current one is a `ConflictError`: the Account
        saved them since, perhaps from another device.
        """
        try:
            shortcuts = preferences.shortcuts
            document = PreferencesDocument(
                shortcuts=None
                if shortcuts is None
                else {command: list(keys) for command, keys in shortcuts.items()}
            ).model_dump(mode="json")
        except ValidationError as error:
            where = ".".join(str(part) for part in error.errors()[0]["loc"])
            message = f"The preferences aren't valid at {where}: {error.errors()[0]['msg']}"
            raise InvalidInputError(message) from None
        now = self._clock()
        statement: Insert | Update
        with self._units.begin() as db:
            if preferences.revision == 0:
                statement = (
                    insert(PreferenceRow)
                    .values(account_id=account_id, document=document, revision=1, updated_at=now)
                    .on_conflict_do_nothing()
                )
            else:
                statement = (
                    update(PreferenceRow)
                    .where(
                        PreferenceRow.account_id == account_id,
                        PreferenceRow.revision == preferences.revision,
                    )
                    .values(document=document, revision=preferences.revision + 1, updated_at=now)
                )
            saved = db.connection().execute(statement).rowcount
        if saved != 1:
            message = (
                f"The preferences were saved since revision {preferences.revision}; "
                "read them again."
            )
            raise ConflictError(message)
        return self.get(account_id)


def _preferences_of(document: PreferencesDocument, revision: int) -> Preferences:
    shortcuts = document.shortcuts
    return Preferences(
        shortcuts=None
        if shortcuts is None
        else {command: tuple(keys) for command, keys in shortcuts.items()},
        revision=revision,
    )
