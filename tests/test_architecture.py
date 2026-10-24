"""The core's layers, checked by the import-linter contracts in `pyproject.toml`."""

from importlinter.cli import lint_imports


def test_every_import_respects_the_layer_contracts() -> None:
    assert lint_imports(no_cache=True, no_logo=True) == 0
