"""The plugin host process: load plugins, then answer calls from the server, one at a time."""

import os
import queue
import resource
import sys
import threading
from collections.abc import Mapping
from typing import IO, Final

from pydantic import BaseModel, JsonValue, ValidationError

from medleyplay.plugin_api import AuthError, NetworkError
from medleyplay.plugin_host.loader import Address, Endpoint, load_plugins
from medleyplay.plugin_host.streams import take_standard_streams
from medleyplay.plugin_host.wire import (
    MAX_LINE,
    TO_HOST,
    Call,
    Failure,
    FailureKind,
    Loaded,
    Loading,
    Quarantined,
    Ready,
    Reply,
    Start,
    encode,
)

# ru_maxrss is in bytes on macOS and in KiB on Linux.
_MAXRSS_UNIT: Final = 1 if sys.platform == "darwin" else 1024
_PROTOCOL_ERROR: Final = 2


def main() -> int:
    """Run the host until the server closes the pipe."""
    protocol_in, protocol_out = take_standard_streams()
    inbox: queue.Queue[str] = queue.Queue()
    threading.Thread(target=_read_inbox, args=(protocol_in, inbox), daemon=True).start()

    def send(message: Loading | Loaded | Quarantined | Ready | Reply) -> None:
        protocol_out.write(encode(message))
        protocol_out.flush()

    start = TO_HOST.validate_json(inbox.get())
    if not isinstance(start, Start):
        return _PROTOCOL_ERROR
    endpoints = load_plugins(start.package, start.plugins, send)
    send(Ready())
    while True:
        call = TO_HOST.validate_json(inbox.get())
        if not isinstance(call, Call):
            return _PROTOCOL_ERROR
        send(answer(call, endpoints))


def _read_inbox(protocol_in: IO[str], inbox: queue.Queue[str]) -> None:
    # The server closing the pipe ends the host at once, even while a plugin call
    # is stuck, so a host never outlives its server.
    while line := protocol_in.readline(MAX_LINE + 1):
        if not line.endswith("\n"):
            break
        inbox.put(line)
    os._exit(0)


def answer(call: Call, endpoints: Mapping[Address, Endpoint]) -> Reply:
    """Call the endpoint `call` addresses and return its reply or failure."""
    endpoint = endpoints.get((call.point, call.key, call.operation))
    if endpoint is None:
        message = f"No provider answers {call.point}.{call.operation} for {call.key!r}."
        return _failed(call, "request", message)
    try:
        request = endpoint.parse(call.request)
    except ValidationError as error:
        return _failed(call, "request", f"The request is invalid: {error}")
    try:
        reply = _reply_json(endpoint.invoke(request))
    except NetworkError as error:
        return _failed(call, "network", str(error) or "The site couldn't be reached.")
    except AuthError as error:
        return _failed(call, "auth", str(error) or "The site refused the login.")
    except (Exception, SystemExit) as error:  # noqa: BLE001 -- any other failure is the plugin's
        return _failed(call, "plugin", f"{type(error).__name__}: {error}")
    return Reply(id=call.id, reply=reply, peak_memory=peak_memory())


def _reply_json(reply: BaseModel) -> JsonValue:
    return reply.model_dump(mode="json")


def _failed(call: Call, kind: FailureKind, message: str) -> Reply:
    return Reply(id=call.id, failure=Failure(kind=kind, message=message), peak_memory=peak_memory())


def peak_memory() -> int:
    """Return this process's peak resident memory, in bytes."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * _MAXRSS_UNIT
