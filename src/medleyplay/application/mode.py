"""The Mode, applied: reading the network and the internet, deciding, and the Mode's settings.

A tick reads the network, checks the internet when a check is due, and decides
the Mode; a thread of its own ticks every few seconds, and at once when the
settings change, so the Mode follows the network:

```text
tick: read network -> check if due -> decide -> tell if changed -> wake at the next tick
```

A check is due at the first tick, five minutes after one that reached the
internet, 30 seconds after one that didn't, on another network, when asked, and
on leaving the setting Offline. While the setting is Offline, nothing is checked.
"""

import contextlib
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from ipaddress import IPv4Network
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application import Clock
from medleyplay.domain.accounts import Account
from medleyplay.domain.errors import ConflictError, ForbiddenError, InvalidInputError
from medleyplay.domain.mode import (
    Facts,
    MeteredNetwork,
    Mode,
    ModeSetting,
    ModeSettings,
    Network,
    NetworkKey,
    Unread,
    decide,
    starting,
)
from medleyplay.persistence.schema import ModeSettingRow

NETWORK_POLL: Final = timedelta(seconds=5)
"""How often the network is read."""
CHECK_WHILE_ONLINE: Final = timedelta(minutes=5)
CHECK_AFTER_FAILURE: Final = timedelta(seconds=30)
MAX_NAME: Final = 64
MODE_ROW: Final = 1
_SAVE_ATTEMPTS: Final = 3
_HARDWARE_ADDRESS: Final = r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$"


class MeteredDocument(BaseModel):
    """A metered network as stored."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=MAX_NAME)
    router: str = Field(pattern=_HARDWARE_ADDRESS)
    subnet: IPv4Network


class ModeDocument(BaseModel):
    """The Mode's settings as stored, version 1; `next_id` is the next mark's id."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1] = 1
    setting: ModeSetting = ModeSetting.AUTO
    metered: tuple[MeteredDocument, ...] = ()
    next_id: int = Field(default=1, ge=1)


@dataclass(frozen=True)
class ModeView:
    """The Mode now, and when the internet was last checked."""

    mode: Mode
    checked_at: datetime | None


class ModeService:
    """Decide the Mode as the network changes, and keep its settings."""

    def __init__(
        self,
        units: sessionmaker[Session],
        clock: Clock,
        *,
        probe: Callable[[], Network | Unread | None],
        check: Callable[[], bool],
        on_change: Callable[[], None] | None = None,
    ) -> None:
        """Create a service reading the network with `probe` and the internet with `check`.

        `on_change` is told, on the ticking thread, each time the Mode changes.
        """
        self._units = units
        self._clock = clock
        self._probe = probe
        self._check = check
        self._on_change = on_change
        self._ticking = threading.Lock()
        self._state = threading.Lock()
        self._mode = starting(ModeSetting.AUTO, clock())
        self._network: Network | Unread | None = None
        self._reachable = False
        self._checked_at: datetime | None = None
        self._next_check: datetime | None = None
        self._check_asked = False
        self._wake = threading.Event()
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None

    def now(self) -> ModeView:
        """Return the Mode now."""
        with self._state:
            return ModeView(self._mode, self._checked_at)

    def settings(self) -> ModeSettings:
        """Return the Mode's settings, or Auto with nothing marked at revision 0."""
        with self._units() as db:
            document, revision = _read(db)
        return _settings_of(document, revision)

    def put_setting(self, caller: Account, setting: ModeSetting, revision: int) -> ModeSettings:
        """Change the setting read at `revision`; it takes effect at once.

        A revision other than the current one is a `ConflictError`: someone saved
        since it was read.
        """
        _require_admin(caller)
        with self._units.begin() as db:
            document, current = _read(db)
            if revision != current:
                message = (
                    f"The Mode's settings were saved since revision {revision}; read them again."
                )
                raise ConflictError(message)
            _save(db, document.model_copy(update={"setting": setting}), current, self._clock())
        self.tick()
        return self.settings()

    def mark_metered(self, caller: Account, name: str) -> MeteredNetwork:
        """Mark the network the server is on now metered, as `name`; a marked one is renamed."""
        _require_admin(caller)
        name = name.strip()
        if not 1 <= len(name) <= MAX_NAME:
            message = f"A metered network needs a name of 1 to {MAX_NAME} characters."
            raise InvalidInputError(message)
        network = self._probe()
        key = network.key if isinstance(network, Network) else None
        if key is None:
            message = "The server can't tell which network it is on now, so it can't mark it."
            raise ConflictError(message)
        marked = self._change(lambda document: _marked(document, key, name))
        self.tick()
        return next(network for network in marked.metered if network.key == key)

    def unmark(self, caller: Account, network_id: int) -> None:
        """Remove a metered network's mark; one already gone changes nothing."""
        _require_admin(caller)
        self._change(
            lambda document: document.model_copy(
                update={"metered": tuple(m for m in document.metered if m.id != network_id)}
            )
        )
        self.tick()

    def check_soon(self) -> None:
        """Check the internet at the next tick, which comes at once."""
        with self._state:
            self._check_asked = True
        self._wake.set()

    def tick(self) -> datetime:
        """Read the network, check the internet if due, and decide; return when to tick next."""
        with self._ticking:
            now = self._clock()
            setting = self.settings()
            network = self._probe()
            with self._state:
                previous = self._mode
                due = setting.setting is not ModeSetting.OFFLINE and (
                    self._check_asked
                    or self._next_check is None
                    or now >= self._next_check
                    or network != self._network
                    or previous.setting is ModeSetting.OFFLINE
                )
                self._check_asked = False
            if due:
                reachable = self._check()
                interval = CHECK_WHILE_ONLINE if reachable else CHECK_AFTER_FAILURE
                with self._state:
                    self._reachable, self._checked_at = reachable, now
                    self._next_check = now + interval
            with self._state:
                self._network = network
                facts = Facts(network, self._reachable)
                self._mode = decide(previous, setting.setting, facts, setting.names(), now)
                mode, next_check = self._mode, self._next_check
            if _shown(mode) != _shown(previous) and self._on_change is not None:
                self._on_change()
            wakes = [now + NETWORK_POLL, mode.online_at]
            if setting.setting is not ModeSetting.OFFLINE:
                wakes.append(next_check)
            return min(wake for wake in wakes if wake is not None)

    def start(self) -> None:
        """Tick on a thread of its own, at once and then as each tick asks."""
        self._stopping.clear()
        self._thread = threading.Thread(target=self._run, name="mode", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop ticking."""
        self._stopping.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None

    def _run(self) -> None:
        while not self._stopping.is_set():
            wait = NETWORK_POLL
            # A tick that fails, as when the database is busy, leaves the Mode as it was.
            with contextlib.suppress(Exception):
                wait = min(max(self.tick() - self._clock(), timedelta(0)), NETWORK_POLL)
            self._wake.wait(wait.total_seconds())
            self._wake.clear()

    def _change(self, change: Callable[[ModeDocument], ModeDocument]) -> ModeSettings:
        for _ in range(_SAVE_ATTEMPTS):
            with self._units.begin() as db:
                document, revision = _read(db)
                changed = change(document)
                if changed == document:
                    return _settings_of(document, revision)
                if _save(db, changed, revision, self._clock()):
                    return _settings_of(changed, revision + 1)
        message = "The Mode's settings kept changing while saving; try again."
        raise ConflictError(message)


def _require_admin(caller: Account) -> None:
    if not caller.is_admin:
        message = "Only an admin can change the Mode's settings."
        raise ForbiddenError(message)


def _shown(mode: Mode) -> tuple[object, ...]:
    """Return what the API shows of a Mode, so a tick that changes none of it tells nothing."""
    return (
        mode.setting,
        mode.online,
        mode.reason,
        mode.since,
        mode.network,
        mode.metered_as,
        mode.online_at,
    )


def _marked(document: ModeDocument, key: NetworkKey, name: str) -> ModeDocument:
    for found in document.metered:
        if (found.router, found.subnet) == (key.router, key.subnet):
            renamed = found.model_copy(update={"name": name})
            metered = tuple(renamed if m.id == found.id else m for m in document.metered)
            return document.model_copy(update={"metered": metered})
    mark = MeteredDocument(id=document.next_id, name=name, router=key.router, subnet=key.subnet)
    return document.model_copy(
        update={"metered": (*document.metered, mark), "next_id": document.next_id + 1}
    )


def _read(db: Session) -> tuple[ModeDocument, int]:
    row = db.get(ModeSettingRow, MODE_ROW)
    if row is None:
        return ModeDocument(), 0
    return ModeDocument.model_validate(row.document), row.revision


def _save(db: Session, document: ModeDocument, revision: int, now: datetime) -> bool:
    """Save `document` over the one read at `revision`; return whether it was still current."""
    values = {"document": document.model_dump(mode="json"), "updated_at": now}
    statement = (
        insert(ModeSettingRow).values(id=MODE_ROW, revision=1, **values).on_conflict_do_nothing()
        if revision == 0
        else update(ModeSettingRow)
        .where(ModeSettingRow.id == MODE_ROW, ModeSettingRow.revision == revision)
        .values(revision=revision + 1, **values)
    )
    return db.connection().execute(statement).rowcount == 1


def _settings_of(document: ModeDocument, revision: int) -> ModeSettings:
    return ModeSettings(
        setting=document.setting,
        metered=tuple(
            MeteredNetwork(m.id, m.name, NetworkKey(m.router, m.subnet)) for m in document.metered
        ),
        revision=revision,
    )
