"""The messages between the server and a plugin host: one JSON object per line.

```text
server -> host  {"type": "start", "package": "medleyplay.plugins", "plugins": ["parrot"]}
host -> server  {"type": "loading", "name": "parrot"}
host -> server  {"type": "loaded", "name": "parrot", "keys": {"echo": ["parrot"]}}
host -> server  {"type": "ready"}
server -> host  {"type": "call", "id": 1, "point": "echo", "key": "parrot",
                 "operation": "say", "request": {"text": "hi"}}
host -> server  {"type": "reply", "id": 1, "reply": {"text": "hi"}, "peak_memory": 41943040}
```
"""

from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter

MAX_LINE: Final = 16 * 1024 * 1024
"""The longest message, in characters, either side accepts."""

type FailureKind = Literal["network", "auth", "plugin", "request"]
"""Why a call failed: the site's network, its login, the plugin, or a request the host refused."""


class _Message(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Start(_Message):
    """Load these plugins, in name order, from `package`."""

    type: Literal["start"] = "start"
    package: str
    plugins: tuple[str, ...]


class Call(_Message):
    """Call one operation of the provider registered for `key`."""

    type: Literal["call"] = "call"
    id: int
    point: str
    key: str
    operation: str
    request: JsonValue


class Loading(_Message):
    """The host is about to import the plugin `name`."""

    type: Literal["loading"] = "loading"
    name: str


class Loaded(_Message):
    """The plugin `name` loaded; `keys` lists its keys for each extension point."""

    type: Literal["loaded"] = "loaded"
    name: str
    keys: dict[str, tuple[str, ...]]


class Quarantined(_Message):
    """The plugin `name` failed to load and won't be called."""

    type: Literal["quarantined"] = "quarantined"
    name: str
    reason: str


class Ready(_Message):
    """Every plugin has loaded or been quarantined; calls may start."""

    type: Literal["ready"] = "ready"


class Failure(_Message):
    """Why a call failed."""

    kind: FailureKind
    message: str


class Reply(_Message):
    """The outcome of the call `id`, and the host's peak memory in bytes so far."""

    type: Literal["reply"] = "reply"
    id: int
    reply: JsonValue = None
    failure: Failure | None = None
    peak_memory: int


type ToHost = Annotated[Start | Call, Field(discriminator="type")]
type FromHost = Annotated[
    Loading | Loaded | Quarantined | Ready | Reply, Field(discriminator="type")
]

TO_HOST: Final = TypeAdapter[ToHost](ToHost)
FROM_HOST: Final = TypeAdapter[FromHost](FromHost)


def encode(message: _Message) -> str:
    """Return `message` as one line, newline included."""
    return message.model_dump_json() + "\n"
