"""Extension points, their operations, and the registry a plugin adds providers to."""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from types import MappingProxyType
from typing import Any, Final, Generic, Protocol, TypeVar

from pydantic import BaseModel

API_VERSION: Final = 1
"""The version of this API; a plugin written against another version isn't loaded."""

DEFAULT_DEADLINE: Final = timedelta(seconds=5)

KEY_PATTERN: Final = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
"""What a provider's key looks like: `mp3`, `file`, `bilibili`."""

# Old-style type variables, because these must be invariant: inferred variance would
# make an extension point covariant in its Protocol, and then `Registry.add` would
# accept any provider by widening the Protocol to `object`.
P = TypeVar("P")
I = TypeVar("I", bound=BaseModel)  # noqa: E741 -- the conventional name for an input
O = TypeVar("O", bound=BaseModel)  # noqa: E741 -- the conventional name for an output


@dataclass(frozen=True, eq=False)
class Operation(Generic[P, I, O]):  # noqa: UP046 -- invariant on purpose; see the type variables
    """One method of an extension point's Protocol, as it crosses the pipe.

    `method` picks the method from a provider, so the operation stays tied to the
    Protocol: renaming the method or changing its types fails type checking.
    """

    point: "ExtensionPoint[P]"
    name: str
    request: type[I]
    reply: type[O]
    method: Callable[[P], Callable[[I], O]]
    deadline: timedelta

    def invoke(self, provider: P, request: I) -> O:
        """Call the operation on `provider`; raise `TypeError` when it returns the wrong type."""
        reply = self.method(provider)(request)
        if not isinstance(reply, self.reply):
            message = (
                f"{self.point.name}.{self.name} returned {type(reply).__name__}, "
                f"not {self.reply.__name__}."
            )
            raise TypeError(message)
        return reply


class ExtensionPoint(Generic[P]):  # noqa: UP046 -- invariant on purpose; see the type variables
    """A kind of provider the core calls, defined by the Protocol `P`.

    ```python
    ECHO = ExtensionPoint[Echo]("echo")
    SAY = ECHO.operation("say", Say, Said, lambda echo: echo.say)
    ```
    """

    def __init__(self, name: str) -> None:
        """Create a point with no operations yet."""
        self.name = name
        # Any: each operation has its own request and reply models.
        self._operations: dict[str, Operation[P, Any, Any]] = {}

    @property
    def operations(self) -> Mapping[str, "Operation[P, Any, Any]"]:
        """Return the point's operations by name."""
        return MappingProxyType(self._operations)

    def operation(
        self,
        name: str,
        request: type[I],
        reply: type[O],
        method: Callable[[P], Callable[[I], O]],
        *,
        deadline: timedelta = DEFAULT_DEADLINE,
    ) -> Operation[P, I, O]:
        """Declare an operation of this point and return it."""
        if name in self._operations:
            message = f"{self.name} already has an operation {name!r}."
            raise ValueError(message)
        operation = Operation(self, name, request, reply, method, deadline)
        self._operations[name] = operation
        return operation

    def __repr__(self) -> str:
        """Return the point's name, as the code declares it."""
        return f"ExtensionPoint({self.name!r})"


class Registry(Protocol):
    """Where a plugin adds its providers while it registers."""

    def add(self, point: ExtensionPoint[P], key: str, provider: P) -> None:
        """Make `provider` answer `point`'s operations for `key`, such as `"mp3"`."""
        ...


@dataclass(frozen=True)
class Plugin:
    """What a plugin module defines as `plugin`.

    `api_version` is the version the plugin was written against, as a literal
    number, so a change to this API can't silently break the plugin.
    """

    api_version: int
    register: Callable[[Registry], None]


def check_key(key: str) -> str:
    """Return `key`, or raise `ValueError` when it isn't a valid provider key."""
    if not KEY_PATTERN.fullmatch(key):
        message = f"{key!r} isn't a valid key; use lowercase letters, digits, '.', '_', '-'."
        raise ValueError(message)
    return key
