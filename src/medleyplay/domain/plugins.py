"""What the core knows about each plugin: whether it is on, and if not, why."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum


class PluginState(StrEnum):
    """Whether a plugin answers calls, and if not, why."""

    ON = "on"
    """Loaded; its keys answer calls."""
    OFF = "off"
    """Turned off in the config file or by safe mode; never imported."""
    QUARANTINED = "quarantined"
    """Failed to load; never called until the server restarts."""
    FAULTED = "faulted"
    """Loaded, but failed too often; never called until an admin resets it."""
    UNKNOWN = "unknown"
    """Named in the config file, but no such plugin exists."""


@dataclass(frozen=True)
class PluginStatus:
    """One plugin's state, the reason for it, and its keys for each extension point."""

    name: str
    state: PluginState
    reason: str = ""
    keys: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
