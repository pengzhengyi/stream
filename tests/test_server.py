"""The composition root: settings from the environment, and a working app from them."""

from pathlib import Path

from fastapi.testclient import TestClient

from medleyplay.server import Settings, build_app, default_data_dir, local_host_names


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

    assert response.json() == {"set_up": False}
    assert (data_dir / "medleyplay.sqlite3").is_file()
    assert data_dir.stat().st_mode & 0o777 == 0o700
