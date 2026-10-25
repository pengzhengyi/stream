"""The server's side of the pipe: start a plugin host, call it with deadlines, restart it."""

import contextlib
import itertools
import os
import queue
import signal
import subprocess  # nosec B404 -- starts only the core's own host module
import sys
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from typing import IO, Final

from pydantic import BaseModel, ValidationError

from medleyplay.plugin_api import Operation
from medleyplay.plugin_host.loader import BUILT_IN_PLUGINS
from medleyplay.plugin_host.wire import (
    FROM_HOST,
    MAX_LINE,
    Call,
    FailureKind,
    FromHost,
    Loaded,
    Loading,
    Quarantined,
    Ready,
    Reply,
    Start,
    encode,
)

LOAD_DEADLINE: Final = timedelta(seconds=30)
MEMORY_LIMIT: Final = 1024**3
_STOP_GRACE: Final = 2.0


class CallFailedError(Exception):
    """A call reached the host and failed; `kind` says why."""

    def __init__(self, kind: FailureKind, message: str) -> None:
        """Record why the call failed."""
        super().__init__(message)
        self.kind: FailureKind = kind


class HostBusyError(Exception):
    """Another call held the host for longer than this call's deadline."""


class HostStartError(Exception):
    """The plugin host itself failed to start, before or between loading plugins."""


@dataclass(frozen=True)
class HostCommand:
    """How to start a plugin host process."""

    argv: tuple[str, ...] = (sys.executable, "-m", "medleyplay.plugin_host")
    env: Mapping[str, str] | None = None


@dataclass
class LoadReport:
    """What happened to each plugin the host was asked to load."""

    loaded: dict[str, dict[str, tuple[str, ...]]] = field(default_factory=dict)
    quarantined: dict[str, str] = field(default_factory=dict)

    def owner(self, point: str, key: str) -> str | None:
        """Return the loaded plugin that registered `key` for `point`, if any."""
        return next(
            (name for name, keys in self.loaded.items() if key in keys.get(point, ())), None
        )


class _Timeout(Exception):  # noqa: N818 -- private control flow, never raised to callers
    pass


class _HostDied(Exception):  # noqa: N818 -- private control flow, never raised to callers
    pass


class _Process:
    """One running host, with a thread reading its replies so reads can time out."""

    def __init__(self, command: HostCommand) -> None:
        env = None if command.env is None else {**os.environ, **command.env}
        # The argv is the server's own interpreter running a module of the core.
        self._popen = subprocess.Popen(  # noqa: S603  # nosec B603
            command.argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env=env,
            start_new_session=True,
        )
        self._lines: queue.Queue[str | None] = queue.Queue()
        threading.Thread(target=self._read, args=(_pipe(self._popen.stdout),), daemon=True).start()

    def _read(self, stdout: IO[str]) -> None:
        with contextlib.suppress(ValueError, OSError):
            while line := stdout.readline(MAX_LINE + 1):
                self._lines.put(line)
        self._lines.put(None)

    def alive(self) -> bool:
        return self._popen.poll() is None

    def send(self, message: Start | Call) -> None:
        stdin = _pipe(self._popen.stdin)
        try:
            stdin.write(encode(message))
            stdin.flush()
        except (BrokenPipeError, ValueError) as error:
            raise _HostDied from error

    def receive(self, timeout: float) -> FromHost:
        try:
            line = self._lines.get(timeout=max(timeout, 0))
        except queue.Empty:
            raise _Timeout from None
        if line is None or not line.endswith("\n"):
            raise _HostDied
        try:
            return FROM_HOST.validate_json(line)
        except ValidationError as error:
            raise _HostDied from error

    def stop(self) -> None:
        # Closing the pipe ends a host at once; the kill is for one that doesn't exit.
        with contextlib.suppress(OSError):
            _pipe(self._popen.stdin).close()
        with contextlib.suppress(subprocess.TimeoutExpired):
            self._popen.wait(timeout=_STOP_GRACE)
        self.kill()

    def kill(self) -> None:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(self._popen.pid, signal.SIGKILL)
        self._popen.wait()
        for pipe in (self._popen.stdin, self._popen.stdout):
            if pipe is not None:
                with contextlib.suppress(OSError):
                    pipe.close()


def _pipe(pipe: IO[str] | None) -> IO[str]:
    if pipe is None:  # pragma: no cover -- Popen opens every pipe it is asked for
        message = "The plugin host was started without its pipes."
        raise RuntimeError(message)
    return pipe


class PluginHost:
    """A plugin host process the server calls, one call at a time, restarting it as needed."""

    def __init__(
        self,
        plugins: Sequence[str],
        *,
        package: str = BUILT_IN_PLUGINS,
        command: HostCommand = HostCommand(),  # noqa: B008 -- a frozen value
        load_deadline: timedelta = LOAD_DEADLINE,
        memory_limit: int = MEMORY_LIMIT,
    ) -> None:
        """Prepare a host for `plugins`; `start` starts it."""
        self._plugins = tuple(plugins)
        self._package = package
        self._command = command
        self._load_deadline = load_deadline
        self._memory_limit = memory_limit
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self._process: _Process | None = None
        self._peak_memory = 0
        self.report = LoadReport()

    def start(self) -> LoadReport:
        """Start the host and load its plugins; return what loaded and what was quarantined."""
        with self._lock:
            self._boot()
            return self.report

    def call[P, I: BaseModel, O: BaseModel](
        self, operation: Operation[P, I, O], key: str, request: I
    ) -> O:
        """Call `operation` on the provider for `key` and return its reply.

        Raise `CallFailedError` when the call fails, `HostBusyError` when another call
        holds the host past this call's deadline, and `HostStartError` when no host
        can be started.
        """
        deadline = operation.deadline.total_seconds()
        if not self._lock.acquire(timeout=deadline):
            message = f"The plugin host was busy for {deadline:g} s."
            raise HostBusyError(message)
        try:
            process = self._ready_process()
            call = Call(
                id=next(self._ids),
                point=operation.point.name,
                key=key,
                operation=operation.name,
                request=request.model_dump(mode="json"),
            )
            reply = self._exchange(process, call, deadline)
        finally:
            self._lock.release()
        if reply.failure is not None:
            raise CallFailedError(reply.failure.kind, reply.failure.message)
        try:
            return operation.reply.model_validate(reply.reply)
        except ValidationError as error:
            message = f"The reply is invalid: {error}"
            raise CallFailedError(kind="plugin", message=message) from error

    def close(self) -> None:
        """Stop the host."""
        with self._lock:
            if self._process is not None:
                self._process.stop()
                self._process = None

    def _ready_process(self) -> _Process:
        # A host that died between calls, or grew past the memory limit, is replaced
        # before the call is sent, so its end isn't blamed on this call's plugin.
        process = self._process
        if process is None or not process.alive() or self._peak_memory > self._memory_limit:
            if process is not None:
                process.kill()
            process = self._boot()
        return process

    def _exchange(self, process: _Process, call: Call, deadline: float) -> Reply:
        ends_at = time.monotonic() + deadline
        try:
            process.send(call)
            while True:
                message = process.receive(ends_at - time.monotonic())
                if isinstance(message, Reply) and message.id == call.id:
                    self._peak_memory = message.peak_memory
                    return message
        except _Timeout:
            self._discard(process)
            message_text = f"{call.point}.{call.operation} missed its deadline of {deadline:g} s."
            raise CallFailedError(kind="plugin", message=message_text) from None
        except _HostDied:
            self._discard(process)
            message_text = f"The plugin host exited during {call.point}.{call.operation}."
            raise CallFailedError(kind="plugin", message=message_text) from None

    def _discard(self, process: _Process) -> None:
        process.kill()
        self._process = None

    def _boot(self) -> _Process:
        report = LoadReport(quarantined=dict(self.report.quarantined))
        pending = [name for name in self._plugins if name not in report.quarantined]
        while True:
            process = _Process(self._command)
            loading = self._load(process, pending, report)
            if loading is None:
                self.report = report
                self._process = process
                self._peak_memory = 0
                return process
            process.kill()
            if loading not in pending:
                message = f"The plugin host announced {loading!r}, which it wasn't asked to load."
                raise HostStartError(message)
            report.quarantined[loading] = "It hung or crashed the plugin host while loading."
            pending.remove(loading)
            report.loaded.clear()

    def _load(self, process: _Process, plugins: Sequence[str], report: LoadReport) -> str | None:
        """Load `plugins`; return the plugin that was loading when the host failed, if any."""
        loading: str | None = None
        try:
            process.send(Start(package=self._package, plugins=tuple(plugins)))
            while True:
                match process.receive(self._load_deadline.total_seconds()):
                    case Loading(name=name):
                        loading = name
                    case Loaded(name=name, keys=keys):
                        report.loaded[name] = keys
                        loading = None
                    case Quarantined(name=name, reason=reason):
                        report.quarantined[name] = reason
                        loading = None
                    case Ready():
                        return None
                    case Reply():
                        break  # A reply before `Ready`: the host is broken.
        except (_Timeout, _HostDied):
            pass
        if loading is None:
            process.kill()
            message = "The plugin host failed to start."
            raise HostStartError(message)
        return loading
