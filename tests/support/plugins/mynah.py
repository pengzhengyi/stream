"""A second well-behaved plugin, with two keys, which prints while it loads."""

import sys

from medleyplay.plugin_api import Plugin, Registry
from tests.support.echo import ECHO, Parrot

sys.stdout.write("mynah is loading\n")


def register(registry: Registry) -> None:
    """Add two echo providers."""
    registry.add(ECHO, "mynah", Parrot())
    registry.add(ECHO, "myna", Parrot())


plugin = Plugin(api_version=1, register=register)
