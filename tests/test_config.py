"""The config file: core settings and plugin toggles, and refusing a file that's wrong."""

from pathlib import Path

import pytest

from medleyplay.config import Config, ConfigError, PluginConfig, load_config


def _written(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "medleyplay.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_a_missing_file_means_every_default(tmp_path: Path) -> None:
    assert load_config(tmp_path / "medleyplay.toml") == Config()


def test_the_file_sets_the_core_settings_and_plugin_toggles(tmp_path: Path) -> None:
    path = _written(
        tmp_path,
        """
        multiple_accounts = true

        [plugins.bilibili]
        enabled = false
        """,
    )

    config = load_config(path)

    assert config == Config(
        multiple_accounts=True, plugins={"bilibili": PluginConfig(enabled=False)}
    )


def test_every_plugin_is_on_unless_the_file_turns_it_off() -> None:
    config = Config(plugins={"fsspec-library": PluginConfig(enabled=False)})

    assert config.enabled_plugins(["fsspec-library", "tinytag-tags"]) == ("tinytag-tags",)


def test_a_plugin_that_is_off_by_default_is_on_only_when_the_file_turns_it_on() -> None:
    assert Config().enabled_plugins(["bilibili", "tinytag-tags"]) == ("tinytag-tags",)
    assert Config(plugins={"bilibili": PluginConfig(enabled=True)}).enabled_plugins(
        ["bilibili"]
    ) == ("bilibili",)


def test_plugins_the_file_names_but_that_dont_exist_are_unknown() -> None:
    config = Config(plugins={"radio": PluginConfig(enabled=False), "zz": PluginConfig()})

    assert config.unknown_plugins(["bilibili"]) == ("radio", "zz")


def test_a_file_that_is_not_toml_is_refused_with_its_path(tmp_path: Path) -> None:
    path = _written(tmp_path, "multiple_accounts = = true")

    with pytest.raises(ConfigError, match=r"medleyplay\.toml isn't valid TOML"):
        load_config(path)


@pytest.mark.parametrize(
    "text",
    [
        'multiple_accounts = "maybe"',
        "unknown_setting = 1",
        "[plugins.bilibili]\nenable = false",
    ],
)
def test_a_setting_with_the_wrong_name_or_type_is_refused(tmp_path: Path, text: str) -> None:
    path = _written(tmp_path, text)

    with pytest.raises(ConfigError, match="has an invalid setting"):
        load_config(path)
