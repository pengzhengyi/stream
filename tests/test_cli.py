"""The command line: `python -m medleyplay`."""

import re
import runpy
import sys
from collections.abc import Iterator
from importlib.metadata import version
from pathlib import Path

import pytest

from medleyplay.__main__ import main
from medleyplay.server import Settings, build_app, build_services, open_database
from tests.support.factories import PASSWORD, NewAccountFactory


def test_version_flag_prints_the_installed_package_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])

    assert exit_info.value.code == 0
    output = capsys.readouterr().out
    assert output == f"medleyplay {version('medleyplay')}\n"
    assert re.fullmatch(r"medleyplay \d+\.\d+\.\d+\S*\n", output)


def test_running_the_module_with_version_exits_successfully(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["medleyplay", "--version"])
    # runpy warns when the module it is about to execute is already imported.
    monkeypatch.delitem(sys.modules, "medleyplay.__main__")

    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("medleyplay", run_name="__main__")

    assert exit_info.value.code == 0
    assert capsys.readouterr().out.startswith("medleyplay ")


@pytest.mark.usefixtures("data_dir")
def test_no_arguments_exits_successfully() -> None:
    assert main([]) == 0


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("MEDLEYPLAY_DATA_DIR", str(tmp_path))
    return tmp_path


def _answers(*answers: str) -> Iterator[str]:
    return iter(answers)


def _household_with_alice(data_dir: Path) -> None:
    """Create Alice, the first admin, in the database in `data_dir`."""
    engine = open_database(data_dir)
    build_services(engine, data_dir).accounts.create_first_admin(NewAccountFactory.admin())
    engine.dispose()


def test_serve_starts_the_server_on_the_requested_address(data_dir: Path) -> None:
    started: list[tuple[Settings, str, int]] = []

    exit_code = main(
        ["serve", "--host", "127.0.0.1", "--port", "8123"],
        serve=lambda settings, host, port: started.append((settings, host, port)),
    )

    assert exit_code == 0
    [(settings, host, port)] = started
    assert (settings.data_dir, host, port) == (data_dir, "127.0.0.1", 8123)


@pytest.mark.usefixtures("data_dir")
def test_serve_listens_on_every_interface_at_port_8000_by_default() -> None:
    started: list[tuple[str, int]] = []

    main(["serve"], serve=lambda _, host, port: started.append((host, port)))

    assert started == [("0.0.0.0", 8000)]  # noqa: S104 -- the default under test


@pytest.mark.parametrize(("arguments", "safe_mode"), [([], False), (["--safe-mode"], True)])
@pytest.mark.usefixtures("data_dir")
def test_serve_starts_in_safe_mode_only_when_asked(
    arguments: list[str], *, safe_mode: bool
) -> None:
    started: list[Settings] = []

    main(["serve", *arguments], serve=lambda settings, _, __: started.append(settings))

    assert [settings.safe_mode for settings in started] == [safe_mode]


def _build_only(settings: Settings, host: str, port: int) -> None:
    """Build the app as `serve` does, without listening."""
    build_app(settings)


def test_serve_with_an_invalid_config_file_fails_with_the_reason(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (data_dir / "medleyplay.toml").write_text("multiple_accounts = = 1", encoding="utf-8")

    exit_code = main(["serve"], serve=_build_only)

    assert exit_code == 1
    assert "isn't valid TOML" in capsys.readouterr().err


def test_reset_password_sets_the_new_password(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _household_with_alice(data_dir)
    answers = _answers("a brand new password", "a brand new password")

    exit_code = main(["reset-password", "alice"], read_password=lambda _: next(answers))

    assert exit_code == 0
    assert "signed it out everywhere" in capsys.readouterr().out
    engine = open_database(data_dir)
    signed_in = build_services(engine, data_dir).accounts.sign_in("alice", "a brand new password")
    engine.dispose()
    assert signed_in.account.username == "alice"


def test_reset_password_changes_nothing_when_the_repeat_differs(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _household_with_alice(data_dir)
    answers = _answers("a brand new password", "a different password")

    exit_code = main(["reset-password", "alice"], read_password=lambda _: next(answers))

    assert exit_code == 1
    assert "don't match" in capsys.readouterr().err
    engine = open_database(data_dir)
    assert (
        build_services(engine, data_dir).accounts.sign_in("alice", PASSWORD).account.username
        == "alice"
    )
    engine.dispose()


@pytest.mark.usefixtures("data_dir")
def test_reset_password_for_an_unknown_username_fails_with_the_reason(
    capsys: pytest.CaptureFixture[str],
) -> None:
    answers = _answers("a brand new password", "a brand new password")

    exit_code = main(["reset-password", "nobody"], read_password=lambda _: next(answers))

    assert exit_code == 1
    assert "'nobody'" in capsys.readouterr().err
