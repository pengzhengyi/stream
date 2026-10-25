"""A plugin whose `folder` and `zip` backends locate files where a faulty plugin might.

The file's name says where `locate` points:

- `outside.wav`: at `outside.wav` next to the root, outside the Library;
- `past-the-end.wav`: at the root, with a slice running past its end;
- `the-root.wav`: at the root itself;
- any other name: at that file in the root, honestly, as a folder backend would,
  even when it is a link, a FIFO, or not there at all.

`fetch` copies honestly too, except `short.wav`, whose copy is one byte, and
`elsewhere.wav`, which it copies next to the folder it was given.
"""

from pathlib import Path

from medleyplay.plugin_api import (
    LIBRARY_BACKEND,
    FetchedFile,
    FetchFile,
    FileLocation,
    FileRequest,
    Plugin,
    Registry,
)
from medleyplay.plugins.fsspec_library.backends import FolderBackend


class Liar(FolderBackend):
    """Locates files as the file's name asks."""

    def locate(self, request: FileRequest) -> FileLocation:
        """Point where the name says."""
        root = Path(request.root.path)
        match request.path:
            case "outside.wav":
                return FileLocation(local_path=str(root.parent / "outside.wav"), length=4)
            case "past-the-end.wav":
                size = root.stat().st_size
                return FileLocation(local_path=str(root), offset=size - 2, length=4)
            case "the-root.wav":
                return FileLocation(local_path=str(root), length=4)
            case path:
                return FileLocation(local_path=str(root / path), length=4)

    def fetch(self, request: FetchFile) -> FetchedFile:
        """Copy the file, except where its name says otherwise."""
        folder = Path(request.folder)
        match request.path:
            case "short.wav":
                (folder / "short.wav").write_bytes(b"R")
                return FetchedFile(local_path=str(folder / "short.wav"))
            case "elsewhere.wav":
                copy = super().fetch(request.model_copy(update={"path": "a.wav"}))
                moved = Path(copy.local_path).replace(folder.parent / "elsewhere.wav")
                return FetchedFile(local_path=str(moved))
            case _:
                return super().fetch(request)


def register(registry: Registry) -> None:
    """Add the liar for both storage kinds."""
    registry.add(LIBRARY_BACKEND, "folder", Liar())
    registry.add(LIBRARY_BACKEND, "zip", Liar())


plugin = Plugin(api_version=1, register=register)
