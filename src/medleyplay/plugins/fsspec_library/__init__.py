"""The plugin `fsspec-library`: Libraries in local folders and zip archives, read with fsspec."""

from medleyplay.plugin_api import LIBRARY_BACKEND, Plugin, Registry
from medleyplay.plugins.fsspec_library.backends import FolderBackend, ZipBackend


def register(registry: Registry) -> None:
    """Add the `folder` and `zip` backends."""
    registry.add(LIBRARY_BACKEND, "folder", FolderBackend())
    registry.add(LIBRARY_BACKEND, "zip", ZipBackend())


plugin = Plugin(api_version=1, register=register)
