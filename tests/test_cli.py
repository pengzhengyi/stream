"""The command line: `python -m medleyplay`."""

import re
import runpy
import sys
from importlib.metadata import version

import pytest

from medleyplay.__main__ import main


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


def test_no_arguments_exits_successfully() -> None:
    assert main([]) == 0
