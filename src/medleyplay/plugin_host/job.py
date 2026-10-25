"""The Job process: load plugins, run one Job's program, and report its progress and outcome.

A program is core code that runs here, never in the server:

```python
def run(request: EchoJob, context: JobContext) -> Echoed:
    context.report(0.5, "Halfway")
    said = context.call(SAY, "parrot", Say(text=request.text))
    return Echoed(text=said.text)


ECHO = JobProgram(EchoJob, Echoed, run)
```
"""

import importlib
import os
import signal
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Generic, Literal, TypeVar

from pydantic import BaseModel

from medleyplay.plugin_api import AuthError, NetworkError, Operation
from medleyplay.plugin_api.progress import reporting_to
from medleyplay.plugin_host.host import peak_memory
from medleyplay.plugin_host.job_wire import (
    RESULT_FILE,
    JobFailed,
    JobFinished,
    JobProgress,
    JobStart,
    KeyOutcome,
)
from medleyplay.plugin_host.loader import Address, Endpoint, load_plugins
from medleyplay.plugin_host.streams import take_standard_streams

I = TypeVar("I", bound=BaseModel)  # noqa: E741 -- the conventional name for an input
R = TypeVar("R", bound=BaseModel)


class PluginCallFailedError(Exception):
    """A plugin call in a Job failed; a program may catch it and carry on."""

    def __init__(
        self, kind: Literal["network", "auth", "plugin"], message: str, plugin: str | None, key: str
    ) -> None:
        """Record why the call failed, and which provider failed it."""
        super().__init__(message)
        self.kind: Literal["network", "auth", "plugin"] = kind
        self.plugin = plugin
        self.key = key


@dataclass
class _KeyRecord:
    plugin: str
    trailing_failures: int = 0
    succeeded: bool = False
    last_failure: str = ""


@dataclass
class JobContext:
    """What a program gets besides its request: plugins, progress, and its working folder."""

    work_dir: Path
    _endpoints: Mapping[Address, Endpoint]
    _send: Callable[[JobProgress], None]
    _keys: dict[str, _KeyRecord] = field(default_factory=dict)

    def report(self, fraction: float | None = None, message: str = "") -> None:
        """Tell the server how far the Job has got.

        A Job that reports nothing for its kind's idle timeout is killed, so a long
        step reports as it goes.
        """
        self._send(JobProgress(fraction=fraction, message=message, peak_memory=peak_memory()))

    def call[P, In: BaseModel, Out: BaseModel](
        self, operation: Operation[P, In, Out], key: str, request: In
    ) -> Out:
        """Call `operation` on the provider for `key`; raise `PluginCallFailedError` on failure."""
        endpoint = self._endpoints.get((operation.point.name, key, operation.name))
        if endpoint is None:
            message = f"No plugin that is on answers {operation.point.name} for {key!r}."
            raise PluginCallFailedError(kind="plugin", message=message, plugin=None, key=key)
        record = self._keys.setdefault(key, _KeyRecord(endpoint.plugin))
        try:
            with reporting_to(self.report):
                reply = endpoint.invoke(request)
        except NetworkError as error:
            raise PluginCallFailedError(
                kind="network", message=str(error), plugin=endpoint.plugin, key=key
            ) from error
        except AuthError as error:
            raise PluginCallFailedError(
                kind="auth", message=str(error), plugin=endpoint.plugin, key=key
            ) from error
        except (Exception, SystemExit) as error:
            message = f"{type(error).__name__}: {error}"
            record.trailing_failures += 1
            record.last_failure = message
            raise PluginCallFailedError(
                kind="plugin", message=message, plugin=endpoint.plugin, key=key
            ) from error
        record.trailing_failures = 0
        record.succeeded = True
        if not isinstance(reply, operation.reply):  # pragma: no cover -- invoke checks the type
            raise TypeError(reply)
        return reply

    def outcomes(self) -> tuple[KeyOutcome, ...]:
        """Return how each key's calls went, for the plugins' circuit breakers."""
        return tuple(
            KeyOutcome(
                plugin=record.plugin,
                key=key,
                trailing_failures=record.trailing_failures,
                succeeded=record.succeeded,
                last_failure=record.last_failure,
            )
            for key, record in sorted(self._keys.items())
        )


@dataclass(frozen=True)
class JobProgram(Generic[I, R]):  # noqa: UP046 -- invariant, as Operation is
    """A Job kind's program: its request and result models, and the function to run."""

    request: type[I]
    result: type[R]
    run: Callable[[I, JobContext], R]


def main() -> int:
    """Run the one Job the server sends, then exit."""
    protocol_in, protocol_out = take_standard_streams()

    def send(message: JobProgress | JobFinished | JobFailed) -> None:
        protocol_out.write(message.model_dump_json() + "\n")
        protocol_out.flush()

    start = JobStart.model_validate_json(protocol_in.readline())
    threading.Thread(target=_end_with_the_server, args=(protocol_in,), daemon=True).start()
    send(run_job(start, send))
    return 0


def run_job(start: JobStart, send: Callable[[JobProgress], None]) -> JobFinished | JobFailed:
    """Run `start`'s program and return its outcome, writing its result to the working folder."""
    work_dir = Path(start.work_dir)
    endpoints = load_plugins(start.package, start.plugins, lambda _: None)
    context = JobContext(work_dir, endpoints, send)
    try:
        program = _program(start.program)
        result = program.run(program.request.model_validate(start.request), context)
        (work_dir / RESULT_FILE).write_text(result.model_dump_json(), encoding="utf-8")
    except PluginCallFailedError as error:
        return JobFailed(
            kind=error.kind,
            message=str(error),
            plugin=error.plugin,
            key=error.key,
            outcomes=context.outcomes(),
            peak_memory=peak_memory(),
        )
    except (Exception, SystemExit) as error:  # noqa: BLE001 -- the program's own fault
        return JobFailed(
            kind="program",
            message=f"{type(error).__name__}: {error}",
            outcomes=context.outcomes(),
            peak_memory=peak_memory(),
        )
    return JobFinished(outcomes=context.outcomes(), peak_memory=peak_memory())


def _program(path: str) -> JobProgram[BaseModel, BaseModel]:
    module_name, _, attribute = path.partition(":")
    program = getattr(importlib.import_module(module_name), attribute, None)
    if not isinstance(program, JobProgram):
        message = f"{path} isn't a JobProgram."
        raise TypeError(message)
    return program


def _end_with_the_server(protocol_in: IO[str]) -> None:
    # The server sends nothing after the start, so end of file means it has gone.
    # Killing the whole group also ends any program the Job started, such as a
    # downloader.
    protocol_in.read()
    os.killpg(os.getpgrp(), signal.SIGKILL)
