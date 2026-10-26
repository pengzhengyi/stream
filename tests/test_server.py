"""The composition root: settings from the environment, and a working app from them."""

import sqlite3
import time
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from medleyplay.config import ConfigError
from medleyplay.server import (
    AlreadyRunningError,
    PluginSource,
    Settings,
    build_app,
    default_data_dir,
    local_host_names,
)
from tests.support.api import set_up_as_alice, sign_in
from tests.support.hosts import TEST_COMMAND, TEST_PLUGINS


def test_the_data_folder_comes_from_medleyplay_data_dir(tmp_path: Path) -> None:
    settings = Settings.from_environment({"MEDLEYPLAY_DATA_DIR": str(tmp_path)})

    assert settings.data_dir == tmp_path


def test_on_macos_the_data_folder_defaults_to_application_support() -> None:
    folder = default_data_dir({}, platform="darwin")

    assert folder == Path.home() / "Library" / "Application Support" / "medleyplay"


def test_elsewhere_the_data_folder_follows_xdg_data_home() -> None:
    assert default_data_dir({"XDG_DATA_HOME": "/data"}, platform="linux") == Path(
        "/data/medleyplay"
    )
    assert default_data_dir({}, platform="linux") == Path.home() / ".local/share/medleyplay"


def test_extra_allowed_hosts_are_added_to_the_local_names() -> None:
    settings = Settings.from_environment({"MEDLEYPLAY_ALLOWED_HOSTS": "music.home, nas.lan"})

    assert {"music.home", "nas.lan", "localhost", "127.0.0.1"} <= set(settings.allowed_hosts)


def test_the_local_names_include_this_machines_hostname() -> None:
    names = local_host_names()

    assert "localhost" in names
    assert any(name.endswith(".local") for name in names)


def test_the_built_app_creates_its_database_and_answers(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    app = build_app(Settings(data_dir=data_dir, allowed_hosts=("testserver",)))

    with TestClient(app) as client:
        response = client.get("/api/setup")

    assert response.json() == {"set_up": False, "multiple_accounts": False}
    assert (data_dir / "medleyplay.sqlite3").is_file()
    assert data_dir.stat().st_mode & 0o777 == 0o700


def test_the_built_app_evaluates_the_download_policy_as_it_starts(tmp_path: Path) -> None:
    app = build_app(Settings(data_dir=tmp_path, allowed_hosts=("testserver",)))

    with TestClient(app, base_url="http://testserver") as client:
        set_up_as_alice(client)
        ends = time.monotonic() + 10
        while (last := client.get("/api/storage").json()["last_evaluation"]) is None:
            assert time.monotonic() < ends, "The policy never evaluated."
            time.sleep(0.05)

    assert (last["error"], last["started"], last["removed"]) == (None, 0, 0)


def test_the_built_app_gives_an_account_without_favorites_its_favorites_as_it_starts(
    tmp_path: Path,
) -> None:
    settings = Settings(data_dir=tmp_path, allowed_hosts=("testserver",))
    with TestClient(build_app(settings)) as client:
        set_up_as_alice(client)
    with closing(sqlite3.connect(tmp_path / "medleyplay.sqlite3")) as database, database:
        database.execute("DELETE FROM playlist")

    with TestClient(build_app(settings)) as client:
        sign_in(client, "alice")
        playlists = client.get("/api/playlists").json()

    assert [(p["name"], p["builtin"]) for p in playlists] == [("Favorites", "favorites")]


def _data_dir_with_config(tmp_path: Path, config: str) -> Path:
    (tmp_path / "medleyplay.toml").write_text(config, encoding="utf-8")
    return tmp_path


TEST_SOURCE = PluginSource(TEST_PLUGINS, TEST_COMMAND)
# Every test plugin but `parrot` is off, so the server starts quickly.
ONLY_PARROT = "\n".join(
    f"[plugins.{name}]\nenabled = false"
    for name in ("broken-import", "crashes-on-import", "future-version", "hangs-on-import",
                 "liar", "mute", "mynah", "not-a-plugin", "squatter", "stutter", "tube")
)  # fmt: skip


def test_one_account_is_the_default(tmp_path: Path) -> None:
    app = build_app(Settings(data_dir=tmp_path, allowed_hosts=("testserver",)))

    with TestClient(app) as client:
        assert not client.get("/api/setup").json()["multiple_accounts"]


def test_the_config_file_turns_several_accounts_on(tmp_path: Path) -> None:
    data_dir = _data_dir_with_config(tmp_path, "multiple_accounts = true")
    app = build_app(Settings(data_dir=data_dir, allowed_hosts=("testserver",)))

    with TestClient(app) as client:
        assert client.get("/api/setup").json()["multiple_accounts"]


def test_a_config_file_with_an_invalid_setting_stops_the_server(tmp_path: Path) -> None:
    data_dir = _data_dir_with_config(tmp_path, 'multiple_accounts = "maybe"')

    with pytest.raises(ConfigError):
        build_app(Settings(data_dir=data_dir, allowed_hosts=("testserver",)))


def test_the_built_app_starts_the_plugins_the_config_file_leaves_on(tmp_path: Path) -> None:
    data_dir = _data_dir_with_config(tmp_path, ONLY_PARROT)
    app = build_app(Settings(data_dir=data_dir, allowed_hosts=("testserver",)), TEST_SOURCE)

    with TestClient(app, base_url="http://testserver") as client:
        set_up_as_alice(client)
        providers = client.get("/api/features").json()["providers"]
        states = {p["name"]: p["state"] for p in client.get("/api/plugins").json()}

    assert providers == {"echo": ["parrot"]}
    assert states["parrot"] == "on"
    assert states["mynah"] == "off"


def test_in_safe_mode_the_built_app_starts_no_plugins(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, allowed_hosts=("testserver",), safe_mode=True)
    app = build_app(settings, TEST_SOURCE)

    with TestClient(app, base_url="http://testserver") as client:
        set_up_as_alice(client)
        providers = client.get("/api/features").json()["providers"]

    assert providers == {}


def test_a_second_server_on_the_same_data_folder_is_refused(tmp_path: Path) -> None:
    first = build_app(Settings(data_dir=tmp_path, allowed_hosts=("testserver",)))
    second = build_app(Settings(data_dir=tmp_path, allowed_hosts=("testserver",)))

    with TestClient(first), pytest.raises(AlreadyRunningError), TestClient(second):
        pass
