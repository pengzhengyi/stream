"""A plugin that answers echo calls for the key `parrot`."""

from medleyplay.plugin_api import Plugin, Registry
from tests.support.echo import ECHO, Parrot


def register(registry: Registry) -> None:
    """Add the parrot."""
    registry.add(ECHO, "parrot", Parrot())


plugin = Plugin(api_version=1, register=register)
