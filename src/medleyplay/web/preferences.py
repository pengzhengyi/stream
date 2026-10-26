"""The preferences API: the signed-in Account's own, replaced at the revision read."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from medleyplay.domain.preferences import Preferences
from medleyplay.web.deps import PreferencesDep, SignedInAccount

router = APIRouter(prefix="/api/me/preferences", tags=["accounts"])


class PreferencesIn(BaseModel):
    """The preferences to save, and the revision they were read at; 0 if never saved."""

    shortcuts: dict[str, list[str]] | None = Field(
        examples=[{"toggle": ["space", "k"], "next": ["shift+right"]}]
    )
    revision: int = Field(ge=0)


class PreferencesOut(BaseModel):
    """The preferences, and their revision."""

    shortcuts: dict[str, list[str]] | None
    revision: int

    @classmethod
    def of(cls, preferences: Preferences) -> "PreferencesOut":
        """Return the API view of `preferences`."""
        shortcuts = preferences.shortcuts
        return cls(
            shortcuts=None
            if shortcuts is None
            else {command: list(keys) for command, keys in shortcuts.items()},
            revision=preferences.revision,
        )


@router.get("")
def get_preferences(me: SignedInAccount, preferences: PreferencesDep) -> PreferencesOut:
    """Return the signed-in Account's preferences."""
    return PreferencesOut.of(preferences.get(me.id))


@router.put("")
def put_preferences(
    body: PreferencesIn, me: SignedInAccount, preferences: PreferencesDep
) -> PreferencesOut:
    """Replace the preferences read at `revision`; a stale revision answers 409."""
    shortcuts = body.shortcuts
    saved = preferences.put(
        me.id,
        Preferences(
            shortcuts=None
            if shortcuts is None
            else {command: tuple(keys) for command, keys in shortcuts.items()},
            revision=body.revision,
        ),
    )
    return PreferencesOut.of(saved)
