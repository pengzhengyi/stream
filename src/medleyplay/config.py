"""The config file, `medleyplay.toml` in the data folder: core settings and plugin toggles.

```toml
multiple_accounts = false

[plugins.bilibili]
enabled = false

# The connectivity checks, tried in turn; these are the defaults.
[[mode.checks]]
url = "http://captive.apple.com/hotspot-detect.html"
status = 200
body = "<HTML><HEAD><TITLE>Success</TITLE></HEAD><BODY>Success</BODY></HTML>"

[[mode.checks]]
url = "http://connect.rom.miui.com/generate_204"
status = 204
```
"""

# cspell:ignore miui

import tomllib
from collections.abc import Iterable
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from medleyplay.application.connectivity import DEFAULT_CHECKS, Check

CONFIG_FILE: Final = "medleyplay.toml"
OFF_BY_DEFAULT: Final = frozenset({"bilibili"})
"""Plugins that are on only when the file turns them on: `bilibili` until yt-dlp reads it again."""


class ConfigError(Exception):
    """The config file can't be read, or a setting in it is invalid."""


class PluginConfig(BaseModel):
    """One plugin's settings."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool | None = None
    """`None` leaves the plugin as it is by default."""


class CheckConfig(BaseModel):
    """A connectivity check: an http or https endpoint, its status, and its body if it has one."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    url: str = Field(pattern=r"^https?://")
    status: int = Field(ge=100, le=599)
    body: str | None = None

    def check(self) -> Check:
        """Return the check this setting describes."""
        return Check(self.url, self.status, self.body)


class ModeConfig(BaseModel):
    """The Mode's settings in the file: the connectivity checks, tried in turn."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    checks: tuple[CheckConfig, ...] = Field(
        default=tuple(CheckConfig(url=c.url, status=c.status, body=c.body) for c in DEFAULT_CHECKS),
        min_length=1,
    )


class Config(BaseModel):
    """Every setting in the config file; a missing setting takes its default."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    multiple_accounts: bool = False
    plugins: dict[str, PluginConfig] = Field(default_factory=dict)
    mode: ModeConfig = Field(default_factory=ModeConfig)

    def enabled_plugins(self, available: Iterable[str]) -> tuple[str, ...]:
        """Return the plugins of `available` that are on.

        A plugin is on unless the file turns it off, or, for one in `OFF_BY_DEFAULT`,
        off unless the file turns it on.
        """
        return tuple(name for name in available if self._enabled(name))

    def _enabled(self, name: str) -> bool:
        enabled = self.plugins.get(name, PluginConfig()).enabled
        return name not in OFF_BY_DEFAULT if enabled is None else enabled

    def unknown_plugins(self, available: Iterable[str]) -> tuple[str, ...]:
        """Return the plugins the file names that aren't in `available`."""
        return tuple(sorted(set(self.plugins) - set(available)))


def load_config(path: Path) -> Config:
    """Read the config file at `path`; a missing file means every default."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Config()
    try:
        return Config.model_validate(tomllib.loads(text))
    except tomllib.TOMLDecodeError as error:
        message = f"{path} isn't valid TOML: {error}"
        raise ConfigError(message) from error
    except ValidationError as error:
        message = f"{path} has an invalid setting:\n{error}"
        raise ConfigError(message) from error
