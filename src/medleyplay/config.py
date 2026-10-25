"""The config file, `medleyplay.toml` in the data folder: core settings and plugin toggles.

```toml
multiple_accounts = false

[plugins.bilibili]
enabled = false
```
"""

import tomllib
from collections.abc import Iterable
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError

CONFIG_FILE: Final = "medleyplay.toml"


class ConfigError(Exception):
    """The config file can't be read, or a setting in it is invalid."""


class PluginConfig(BaseModel):
    """One plugin's settings."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = True


class Config(BaseModel):
    """Every setting in the config file; a missing setting takes its default."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    multiple_accounts: bool = False
    plugins: dict[str, PluginConfig] = Field(default_factory=dict)

    def enabled_plugins(self, available: Iterable[str]) -> tuple[str, ...]:
        """Return the plugins of `available` that are on; a plugin is on unless turned off."""
        return tuple(name for name in available if self.plugins.get(name, PluginConfig()).enabled)

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
