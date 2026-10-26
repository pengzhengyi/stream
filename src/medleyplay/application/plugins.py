"""Plugins as the core sees them: which are on, calls through the host, and faults.

A plugin is faulted when one of its keys fails `FAULT_AFTER` times in a row with
a fault in the plugin; network and login failures don't count. A fault is stored,
so it survives a restart, until an admin resets the plugin.
"""

import threading
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Protocol

from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application import Clock
from medleyplay.application.changes import OnChange
from medleyplay.domain.accounts import Account
from medleyplay.domain.errors import (
    ForbiddenError,
    NotFoundError,
    PluginCallError,
    PluginUnavailableError,
)
from medleyplay.domain.plugins import PluginState, PluginStatus
from medleyplay.persistence.schema import PluginStateRow
from medleyplay.plugin_api import Operation
from medleyplay.plugin_host.client import (
    CallFailedError,
    HostBusyError,
    HostStartError,
    LoadReport,
)
from medleyplay.plugin_host.job_wire import KeyOutcome

if TYPE_CHECKING:
    from collections.abc import Mapping

FAULT_AFTER: Final = 5


class Host(Protocol):
    """A plugin host process, as `medleyplay.plugin_host.client.PluginHost` provides."""

    @property
    def report(self) -> LoadReport:
        """Return what loaded and what was quarantined, as of the latest start."""
        ...

    def start(self) -> LoadReport:
        """Start the host and load its plugins."""
        ...

    def call[P, I: BaseModel, O: BaseModel](
        self, operation: Operation[P, I, O], key: str, request: I
    ) -> O:
        """Call `operation` on the provider for `key`."""
        ...

    def close(self) -> None:
        """Stop the host."""
        ...


@dataclass(frozen=True)
class Lineup:
    """Which plugins exist, which the config file turns on, and which it names in vain."""

    available: tuple[str, ...] = ()
    enabled: tuple[str, ...] = ()
    unknown: tuple[str, ...] = ()
    safe_mode: bool = False


class PluginService:
    """Call plugins through a host, and track each plugin's state."""

    def __init__(
        self,
        units: sessionmaker[Session],
        clock: Clock,
        lineup: Lineup,
        host: Host | None,
        on_change: OnChange | None = None,
    ) -> None:
        """Create a service; `host` is `None` when no plugin is on. A reset tells `on_change`."""
        self._on_change = on_change
        self._units = units
        self._clock = clock
        self._lineup = lineup
        self._host = host
        self._lock = threading.Lock()
        self._failures: dict[tuple[str, str], int] = {}
        self._faults: dict[str, str] = {}
        self._start_failure: str | None = None

    def start(self) -> None:
        """Read the stored faults and start the host, if any plugin is on."""
        with self._units() as db:
            rows = db.scalars(select(PluginStateRow).where(PluginStateRow.faulted_at.is_not(None)))
            self._faults = {row.name: row.fault_reason for row in rows}
        if self._host is not None:
            try:
                self._host.start()
            except HostStartError as error:
                self._start_failure = str(error)

    def close(self) -> None:
        """Stop the host."""
        if self._host is not None:
            self._host.close()

    def statuses(self, caller: Account) -> list[PluginStatus]:
        """Return every plugin's status, by name; admins only."""
        _require_admin(caller)
        names = sorted({*self._lineup.available, *self._lineup.unknown})
        return [self._status(name) for name in names]

    def available_keys(self) -> dict[str, list[str]]:
        """Return the keys that answer calls now, for each extension point."""
        keys: dict[str, list[str]] = {}
        for name, points in self._report().loaded.items():
            if name not in self._faults:
                for point, point_keys in points.items():
                    keys.setdefault(point, []).extend(point_keys)
        return {point: sorted(point_keys) for point, point_keys in sorted(keys.items())}

    def reset(self, caller: Account, name: str) -> PluginStatus:
        """Clear a plugin's fault, so it is called again; admins only. Idempotent."""
        _require_admin(caller)
        if name not in self._lineup.available:
            message = f"There is no plugin {name!r}."
            raise NotFoundError(message)
        with self._units.begin() as db:
            db.execute(
                update(PluginStateRow)
                .where(PluginStateRow.name == name)
                .values(faulted_at=None, fault_reason="")
            )
        with self._lock:
            self._faults.pop(name, None)
            self._failures = {k: n for k, n in self._failures.items() if k[0] != name}
        if self._on_change is not None:
            self._on_change("plugins")
        return self._status(name)

    def call[P, I: BaseModel, O: BaseModel](
        self, operation: Operation[P, I, O], key: str, request: I
    ) -> O:
        """Call `operation` on the plugin that holds `key`, and return its reply.

        Raise `PluginUnavailableError` when no plugin that is on holds the key, and
        `PluginCallError` when the call fails.
        """
        host = self._host
        owner = self._report().owner(operation.point.name, key)
        if host is None or owner is None or owner in self._faults:
            message = self._start_failure or (
                f"No plugin that is on answers {operation.point.name} for {key!r}."
            )
            raise PluginUnavailableError(message)
        try:
            reply = host.call(operation, key, request)
        except (HostBusyError, HostStartError) as error:
            raise PluginUnavailableError(str(error)) from error
        except CallFailedError as error:
            raise self._failed(owner, key, error) from error
        with self._lock:
            self._failures.pop((owner, key), None)
        return reply

    def _failed(self, owner: str, key: str, error: CallFailedError) -> Exception:
        match error.kind:
            case "request":
                # The core sent a request its own models refuse: a bug in the core.
                return RuntimeError(f"The plugin host refused a request: {error}")
            case "network" | "auth":
                return PluginCallError(error.kind, f"{owner}: {error}")
            case "plugin":
                self._count_faults(owner, key, 1, str(error))
                return PluginCallError("plugin", f"{owner}: {error}")

    def plugins_for(self, points: Iterable[str]) -> tuple[str, ...]:
        """Return the plugins that are on and hold a key for any of `points`, by name."""
        wanted = set(points)
        return tuple(
            sorted(
                name
                for name, keys in self._report().loaded.items()
                if name not in self._faults and wanted & set(keys)
            )
        )

    def record_outcomes(self, outcomes: Iterable[KeyOutcome]) -> None:
        """Count a Job's plugin faults, key by key, as if its calls were made here."""
        for outcome in outcomes:
            if outcome.succeeded or outcome.trailing_failures == 0:
                with self._lock:
                    self._failures.pop((outcome.plugin, outcome.key), None)
            if outcome.trailing_failures:
                self._count_faults(
                    outcome.plugin, outcome.key, outcome.trailing_failures, outcome.last_failure
                )

    def _count_faults(self, owner: str, key: str, count: int, reason: str) -> None:
        with self._lock:
            failures = self._failures.get((owner, key), 0) + count
            self._failures[owner, key] = failures
            if failures < FAULT_AFTER or owner in self._faults:
                return
            self._faults[owner] = reason
        values = {"faulted_at": self._clock(), "fault_reason": reason[:2048]}
        with self._units.begin() as db:
            db.execute(
                insert(PluginStateRow)
                .values(name=owner, **values)
                .on_conflict_do_update(index_elements=["name"], set_=values)
            )

    def _report(self) -> LoadReport:
        return self._host.report if self._host is not None else LoadReport()

    def _status(self, name: str) -> PluginStatus:
        report = self._report()
        if name in self._lineup.unknown:
            return PluginStatus(name, PluginState.UNKNOWN, "The config file names no such plugin.")
        if name not in self._lineup.enabled:
            reason = (
                "Safe mode is on." if self._lineup.safe_mode else "The config file turns it off."
            )
            return PluginStatus(name, PluginState.OFF, reason)
        if name in report.quarantined:
            return PluginStatus(name, PluginState.QUARANTINED, report.quarantined[name])
        keys: Mapping[str, tuple[str, ...]] = report.loaded.get(name, {})
        if name in self._faults:
            return PluginStatus(name, PluginState.FAULTED, self._faults[name], keys)
        if name not in report.loaded:
            reason = self._start_failure or "The plugin host hasn't loaded it."
            return PluginStatus(name, PluginState.QUARANTINED, reason)
        return PluginStatus(name, PluginState.ON, keys=keys)


def _require_admin(caller: Account) -> None:
    if not caller.is_admin:
        message = "Only an admin can manage plugins."
        raise ForbiddenError(message)
