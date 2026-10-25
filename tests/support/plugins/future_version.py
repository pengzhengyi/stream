"""A plugin written for a later plugin API."""

from medleyplay.plugin_api import Plugin, Registry


def register(registry: Registry) -> None:
    """Add nothing."""


plugin = Plugin(api_version=99, register=register)
