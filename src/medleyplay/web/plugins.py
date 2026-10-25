"""The plugins API: what the server can do now, and each plugin's state for admins."""

from collections.abc import Mapping

from fastapi import APIRouter
from pydantic import BaseModel

from medleyplay.domain.plugins import PluginState, PluginStatus
from medleyplay.web.deps import AccountsDep, PluginsDep, SignedInAccount

router = APIRouter(prefix="/api", tags=["plugins"])


class FeaturesOut(BaseModel):
    """What this server can do now, so the client can hide what it can't."""

    multiple_accounts: bool
    providers: Mapping[str, list[str]]
    """The keys that answer calls, for each extension point."""


class PluginOut(BaseModel):
    """One plugin's state, the reason for it, and its keys for each extension point."""

    name: str
    state: PluginState
    reason: str
    keys: Mapping[str, list[str]]

    @classmethod
    def of(cls, status: PluginStatus) -> "PluginOut":
        """Return the API view of `status`."""
        keys = {point: list(point_keys) for point, point_keys in status.keys.items()}
        return cls(name=status.name, state=status.state, reason=status.reason, keys=keys)


@router.get("/features")
def features(_: SignedInAccount, accounts: AccountsDep, plugins: PluginsDep) -> FeaturesOut:
    """Return what this server can do now."""
    return FeaturesOut(
        multiple_accounts=accounts.multiple_accounts, providers=plugins.available_keys()
    )


@router.get("/plugins")
def list_plugins(me: SignedInAccount, plugins: PluginsDep) -> list[PluginOut]:
    """Return every plugin's state; admins only."""
    return [PluginOut.of(status) for status in plugins.statuses(me)]


@router.post("/plugins/{name}/reset")
def reset_plugin(name: str, me: SignedInAccount, plugins: PluginsDep) -> PluginOut:
    """Clear a plugin's fault so it is called again; admins only. Resetting twice is fine."""
    return PluginOut.of(plugins.reset(me, name))
