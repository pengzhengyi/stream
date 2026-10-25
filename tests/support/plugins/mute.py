"""A plugin whose echo provider has no `say` method."""

from medleyplay.plugin_api import Plugin, Registry
from tests.support.echo import ECHO


class Mute:
    """A provider that can't say anything."""

    say = None


def register(registry: Registry) -> None:
    """Add a provider that lacks the operation's method."""
    registry.add(ECHO, "mute", Mute())  # type: ignore[misc] # the mistake under test


plugin = Plugin(api_version=1, register=register)
