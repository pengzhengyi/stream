"""A plugin that registers the same key twice."""

from medleyplay.plugin_api import Plugin, Registry
from tests.support.echo import ECHO, Parrot


def register(registry: Registry) -> None:
    """Add `stutter`, then `stutter` again."""
    registry.add(ECHO, "stutter", Parrot())
    registry.add(ECHO, "stutter", Parrot())


plugin = Plugin(api_version=1, register=register)
