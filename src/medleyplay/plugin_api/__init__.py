"""The plugin API: the only part of medleyplay a plugin may import.

A plugin is a module under `medleyplay.plugins` that defines `plugin`:

```python
def register(registry: Registry) -> None:
    registry.add(ECHO, "parrot", Parrot())


plugin = Plugin(api_version=1, register=register)
```
"""

from medleyplay.plugin_api.errors import AuthError, NetworkError
from medleyplay.plugin_api.extension import (
    API_VERSION,
    DEFAULT_DEADLINE,
    ExtensionPoint,
    Operation,
    Plugin,
    Registry,
    check_key,
)
from medleyplay.plugin_api.library import (
    CHECK_ROOT,
    FETCH_FILE,
    FINGERPRINT_FILE,
    LIBRARY_BACKEND,
    LIST_FILES,
    LOCATE_FILE,
    CheckRoot,
    FetchedFile,
    FetchFile,
    FileFingerprint,
    FileList,
    FileLocation,
    FileRequest,
    LibraryBackend,
    LibraryFile,
    LibraryPath,
    LibraryRoot,
    ListFiles,
    RootCheck,
    check_library_path,
)
from medleyplay.plugin_api.tags import READ_TAGS, TAG_READER, ReadTags, TagReader, Tags

__all__ = [
    "API_VERSION",
    "CHECK_ROOT",
    "DEFAULT_DEADLINE",
    "FETCH_FILE",
    "FINGERPRINT_FILE",
    "LIBRARY_BACKEND",
    "LIST_FILES",
    "LOCATE_FILE",
    "READ_TAGS",
    "TAG_READER",
    "AuthError",
    "CheckRoot",
    "ExtensionPoint",
    "FetchFile",
    "FetchedFile",
    "FileFingerprint",
    "FileList",
    "FileLocation",
    "FileRequest",
    "LibraryBackend",
    "LibraryFile",
    "LibraryPath",
    "LibraryRoot",
    "ListFiles",
    "NetworkError",
    "Operation",
    "Plugin",
    "ReadTags",
    "Registry",
    "RootCheck",
    "TagReader",
    "Tags",
    "check_key",
    "check_library_path",
]
