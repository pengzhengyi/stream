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

__all__ = [
    "API_VERSION",
    "DEFAULT_DEADLINE",
    "AuthError",
    "ExtensionPoint",
    "NetworkError",
    "Operation",
    "Plugin",
    "Registry",
    "check_key",
]
