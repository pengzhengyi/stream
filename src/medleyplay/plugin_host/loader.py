"""Finding plugins by name without importing them, and loading them inside a host."""

import importlib
import importlib.util
import pkgutil
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Final

from pydantic import BaseModel, JsonValue

from medleyplay.plugin_api import API_VERSION, ExtensionPoint, Operation, Plugin, check_key
from medleyplay.plugin_host.wire import Loaded, Loading, Quarantined

BUILT_IN_PLUGINS: Final = "medleyplay.plugins"

type Address = tuple[str, str, str]
"""Where a call goes: extension point, key, and operation."""


def plugin_names(package: str = BUILT_IN_PLUGINS) -> tuple[str, ...]:
    """Return the names of the plugins in `package`, importing none of them.

    A module `tinytag_tags` is the plugin `tinytag-tags`.
    """
    spec = importlib.util.find_spec(package)
    folders = spec.submodule_search_locations if spec else None
    if not folders:
        message = f"{package!r} isn't a package of plugins."
        raise ValueError(message)
    return tuple(sorted(module.name.replace("_", "-") for module in pkgutil.iter_modules(folders)))


@dataclass(frozen=True)
class Endpoint:
    """One operation of one provider, ready to call with a request from the pipe."""

    plugin: str
    parse: Callable[[JsonValue], BaseModel]
    invoke: Callable[[BaseModel], BaseModel]


class _PluginRegistry:
    """The registry one plugin registers into; it checks every key as it is added."""

    def __init__(self, plugin: str, taken: Mapping[tuple[str, str], str]) -> None:
        self._plugin = plugin
        self._taken = taken
        self.endpoints: dict[Address, Endpoint] = {}
        self.keys: dict[str, list[str]] = {}

    def add[P](self, point: ExtensionPoint[P], key: str, provider: P) -> None:
        check_key(key)
        holder = self._taken.get((point.name, key))
        if holder is not None or key in self.keys.get(point.name, []):
            message = f"{point.name} key {key!r} is already taken by {holder or 'this plugin'}."
            raise ValueError(message)
        for name, operation in point.operations.items():
            self.endpoints[point.name, key, name] = _endpoint(self._plugin, operation, provider)
        self.keys.setdefault(point.name, []).append(key)


def _endpoint[P](
    plugin: str,
    operation: Operation[P, Any, Any],  # Any: each operation has its own models
    provider: P,
) -> Endpoint:
    # Picking the method now fails registration, rather than the first call, when the
    # provider lacks it.
    if not callable(operation.method(provider)):
        message = f"The provider has no method for {operation.point.name}.{operation.name}."
        raise TypeError(message)
    return Endpoint(
        plugin=plugin,
        parse=operation.request.model_validate,
        invoke=lambda request: operation.invoke(provider, request),
    )


def load_plugins(
    package: str, names: Iterable[str], report: Callable[[Loading | Loaded | Quarantined], None]
) -> dict[Address, Endpoint]:
    """Import and register each plugin in name order, and return every endpoint.

    `report` hears `Loading` before each import, then `Loaded` or `Quarantined`. A
    plugin that claims a key an earlier plugin holds is quarantined as a whole.
    """
    endpoints: dict[Address, Endpoint] = {}
    taken: dict[tuple[str, str], str] = {}
    for name in sorted(names):
        report(Loading(name=name))
        try:
            registry = _register(package, name, taken)
        except (Exception, SystemExit) as error:  # noqa: BLE001 -- any failure quarantines it
            report(Quarantined(name=name, reason=_describe(error)))
            continue
        endpoints.update(registry.endpoints)
        taken.update({(point, key): name for point, keys in registry.keys.items() for key in keys})
        report(
            Loaded(name=name, keys={point: tuple(keys) for point, keys in registry.keys.items()})
        )
    return endpoints


def _register(package: str, name: str, taken: Mapping[tuple[str, str], str]) -> _PluginRegistry:
    module = importlib.import_module(f"{package}.{name.replace('-', '_')}")
    plugin = getattr(module, "plugin", None)
    if not isinstance(plugin, Plugin):
        message = "The module defines no `plugin = Plugin(...)`."
        raise TypeError(message)
    if plugin.api_version != API_VERSION:
        message = f"Written for plugin API {plugin.api_version}; this server has {API_VERSION}."
        raise ValueError(message)
    registry = _PluginRegistry(name, taken)
    plugin.register(registry)
    return registry


def _describe(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}"
