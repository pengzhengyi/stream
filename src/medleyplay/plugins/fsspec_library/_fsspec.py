"""Every call this plugin makes to fsspec, which has no type hints, returning typed values."""

from dataclasses import dataclass
from typing import Any

import fsspec  # type: ignore[import-untyped] # fsspec ships no type hints


@dataclass(frozen=True)
class Entry:
    """One file fsspec found: its path as fsspec names it, its size, and its details."""

    name: str
    size: int
    modified: float | None
    details: dict[str, Any]  # Any: fsspec's details differ by filesystem


def find_files(protocol: str, path: str, **options: object) -> list[Entry]:
    """Return every regular file under `path` on the filesystem `protocol` names.

    Symbolic links are left out, so a link can't lead outside the root or into a loop.
    """
    filesystem = fsspec.filesystem(protocol, **options)
    found: dict[str, dict[str, Any]] = filesystem.find(path, detail=True, withdirs=False)
    return [
        Entry(name, int(info["size"]), info.get("mtime"), info)
        for name, info in sorted(found.items())
        if info.get("type") == "file" and not info.get("islink", False)
    ]
