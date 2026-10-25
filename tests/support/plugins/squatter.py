"""A plugin that claims the key `parrot`, which the plugin `parrot` loads first."""

from medleyplay.plugin_api import Plugin, Registry
from tests.support.echo import ECHO, Parrot


def register(registry: Registry) -> None:
    """Add a provider under a key that is already taken, after one that isn't."""
    registry.add(ECHO, "squatter", Parrot())
    registry.add(ECHO, "parrot", Parrot())


plugin = Plugin(api_version=1, register=register)
