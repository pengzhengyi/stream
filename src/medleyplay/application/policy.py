"""The download policy, applied: one evaluation at a time, on a thread of its own.

An evaluation reads a snapshot, plans, and applies the plan: the removals first,
each checked again where it happens, then the Downloads to start.

```text
request ... request ......5 s...... evaluate: snapshot -> plan -> remove -> start
                                    (a change since the snapshot drops the plan)
```

It fails closed: when the snapshot can't be read, nothing is planned, and the
error shows in the storage report until an evaluation succeeds.
"""

import contextlib
import threading
import time
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final

from sqlalchemy import delete, update
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application import Clock
from medleyplay.application.downloads import DownloadService
from medleyplay.application.plugins import PluginService
from medleyplay.application.policy_snapshot import Snapshot, read_snapshot
from medleyplay.application.settings import read_settings
from medleyplay.domain.accounts import Account, AccountId
from medleyplay.domain.catalog import TrackId
from medleyplay.domain.errors import ForbiddenError
from medleyplay.domain.playback import CACHE_FOLDER
from medleyplay.domain.policy import (
    Plan,
    PolicyState,
    Remove,
    RemoveCache,
    Shortfall,
    plan,
    removable,
)
from medleyplay.persistence.schema import DownloadRow
from medleyplay.plugin_api import SOURCE_DOWNLOADER

DELAY: Final = timedelta(seconds=5)
"""How long after the first request an evaluation starts, so a burst of changes is one."""
TICK: Final = timedelta(hours=1)
"""How often an evaluation runs with no request, for rules on time and any request missed."""
REMOVED_PREFIX: Final = ".removed-"


@dataclass(frozen=True)
class Evaluation:
    """What one evaluation did, and what it couldn't do."""

    at: datetime
    removed: int = 0
    started: int = 0
    shortfalls: Mapping[TrackId, Shortfall] = field(default_factory=dict)
    plan_dropped: bool = False
    """What it planned to remove changed since the snapshot, so it did nothing and asked again."""
    error: str | None = None
    """Why the evaluation planned nothing."""
    failed_actions: tuple[str, ...] = ()


@dataclass(frozen=True)
class Storage:
    """The space Downloads and cache copies use, the limit, and what the policy wants.

    The figures are `None` when the snapshot can't be read; `error` says why.
    """

    limit: int | None
    downloads: int | None = None
    cache: int | None = None
    reserved: int | None = None
    free: int | None = None
    disk_size: int | None = None
    min_free: int | None = None
    wanted: int | None = None
    """The space wanted Tracks hold: their Downloads, and estimates for the rest."""
    wanted_by_account: Mapping[AccountId, int] = field(default_factory=dict)
    last: Evaluation | None = None
    error: str | None = None
    preview: Plan | None = None
    """What a plan at the asked limit would do, when an admin asked."""


class PolicyService:
    """Evaluate the download policy when asked, and report the storage it governs."""

    def __init__(  # noqa: PLR0913 -- the collaborators, then settings with defaults
        self,
        units: sessionmaker[Session],
        clock: Clock,
        downloads: DownloadService,
        plugins: PluginService,
        data_dir: Path,
        *,
        delay: timedelta = DELAY,
        tick: timedelta = TICK,
        online: Callable[[], bool] = lambda: True,
    ) -> None:
        """Create a service over the Downloads and cache copies in `data_dir`.

        `online` says whether the Mode is Online; while it isn't, no Download is removed.
        """
        self._units = units
        self._clock = clock
        self._downloads = downloads
        self._plugins = plugins
        self._data_dir = data_dir
        self._online = online
        self._delay = delay.total_seconds()
        self._tick = tick.total_seconds()
        self._wake = threading.Condition()
        self._requests = 0
        self._due_at: float | None = None
        self._stopping = False
        self._thread: threading.Thread | None = None
        self._evaluating = threading.Lock()
        self._last: Evaluation | None = None

    def request(self, *_: object) -> None:
        """Ask for an evaluation; callable from any thread, with whatever a notice passes."""
        with self._wake:
            self._requests += 1
            if self._due_at is None:
                self._due_at = time.monotonic() + self._delay
            self._wake.notify()

    def start(self) -> None:
        """Start evaluating on a thread of its own, once now, then when asked or an hour on."""
        with self._wake:
            self._stopping = False
            self._due_at = time.monotonic()
        self._thread = threading.Thread(target=self._run, name="download-policy", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop evaluating, after the evaluation running now, if any, finishes."""
        with self._wake:
            self._stopping = True
            self._wake.notify()
        if self._thread is not None:
            self._thread.join()
            self._thread = None

    def evaluate(self) -> Evaluation:
        """Read a snapshot, plan, and apply the plan now; return what it did."""
        with self._evaluating:
            with self._wake:
                heard = self._requests
            now = self._clock()
            try:
                with self._reading() as db:
                    snapshot = self._snapshot(db, now, read_settings(db).storage_limit)
                evaluation = self._apply(plan(snapshot.state), now, heard)
            except Exception as error:  # noqa: BLE001 -- any failure fails closed, and is shown
                evaluation = Evaluation(now, error=_said(error))
            self._last = evaluation
            return evaluation

    def storage(self, caller: Account, preview_limit: int | None = None) -> Storage:
        """Return the storage as it stands now, and the last evaluation.

        With `preview_limit`, an admin also sees what a plan at that limit would
        remove and start, without doing it.
        """
        if preview_limit is not None and not caller.is_admin:
            message = "Only an admin can preview another storage limit."
            raise ForbiddenError(message)
        now = self._clock()
        limit = None
        try:
            with self._reading() as db:
                limit = read_settings(db).storage_limit
                snapshot = self._snapshot(db, now, limit)
        except Exception as error:  # noqa: BLE001 -- the report says why, as evaluating does
            return Storage(limit, last=self._last, error=_said(error))
        state = snapshot.state
        preview = None
        if preview_limit is not None:
            preview = plan(replace(state, limit=preview_limit))
        return Storage(
            limit,
            downloads=sum(each.size for each in state.downloads),
            cache=sum(each.size for each in state.cache),
            reserved=state.reserved,
            free=state.free,
            disk_size=state.disk_size,
            min_free=state.min_free(),
            wanted=_wanted_bytes(state),
            wanted_by_account=snapshot.wanted_bytes,
            last=self._last,
            error=None if self._last is None else self._last.error,
            preview=preview,
        )

    @contextlib.contextmanager
    def _reading(self) -> Iterator[Session]:
        """Open a session whose reads all see one moment of the database.

        The driver begins a transaction only before a write, so a session that
        only reads would see each commit as it lands; beginning one by hand keeps
        the snapshot whole.
        """
        with self._units() as db:
            db.connection().exec_driver_sql("BEGIN")
            yield db

    def _snapshot(self, db: Session, now: datetime, limit: int | None) -> Snapshot:
        sites = self._plugins.available_keys().get(SOURCE_DOWNLOADER.name, [])
        snapshot = read_snapshot(db, now, limit, sites, self._data_dir)
        return replace(snapshot, state=replace(snapshot.state, online=self._online()))

    def _apply(self, planned: Plan, now: datetime, heard: int) -> Evaluation:
        removed = self._remove(planned.removals, now, heard) if planned.removals else 0
        if removed is None:
            # The next evaluation plans from what changed.
            self.request()
            return Evaluation(now, shortfalls=planned.shortfalls, plan_dropped=True)
        if planned.wanted_downloads:
            with self._units.begin() as db:
                db.execute(
                    update(DownloadRow)
                    .where(DownloadRow.source_id.in_(planned.wanted_downloads))
                    .values(last_wanted_at=now)
                )
        failed: list[str] = []
        started = 0
        for start in planned.starts:
            try:
                job = self._downloads.start_for(start.requester, start.source_id)
            except Exception as error:  # noqa: BLE001 -- one failed action leaves the others
                failed.append(f"Starting the Download of Source {start.source_id}: {error}")
                continue
            started += job is not None
        return Evaluation(
            now,
            removed=removed,
            started=started,
            shortfalls=planned.shortfalls,
            failed_actions=tuple(failed),
        )

    def _remove(
        self, removals: Sequence[Remove | RemoveCache], now: datetime, heard: int
    ) -> int | None:
        """Remove every planned file, or none of them; return how many, or `None` if none.

        The plan's Downloads were sized to fit once its removals happen, so its
        removals happen together or not at all. They are judged again inside the
        transaction that deletes the rows: its first statement writes, so it holds
        the write lock before it reads, and nothing it checks can change until it
        commits. A request heard since the snapshot also drops them.
        """
        folder, cache = self._downloads.folder, self._data_dir / CACHE_FOLDER
        downloads = [each.source_id for each in removals if isinstance(each, Remove)]
        copies = [each.name for each in removals if isinstance(each, RemoveCache)]
        renamed: list[tuple[Path, Path]] = []
        with self._units.begin() as db:
            db.execute(
                update(DownloadRow)
                .where(DownloadRow.source_id.in_(downloads))
                .values(size=DownloadRow.size)
            )
            with self._wake:
                if self._requests != heard:
                    return None
            fresh = self._snapshot(db, now, read_settings(db).storage_limit)
            if not set(removals) <= set(removable(fresh.state)):
                return None
            db.execute(delete(DownloadRow).where(DownloadRow.source_id.in_(downloads)))
            try:
                for source_id in downloads:
                    original = folder / fresh.file_names[source_id]
                    target = folder / f"{REMOVED_PREFIX}{source_id}-{uuid.uuid4().hex}"
                    with contextlib.suppress(FileNotFoundError):
                        original.rename(target)
                        renamed.append((original, target))
            except OSError:
                # The rows stay; so must their files.
                for original, target in renamed:
                    target.rename(original)
                raise
        for _, target in renamed:
            target.unlink(missing_ok=True)
        for name in copies:
            (cache / name).unlink(missing_ok=True)
        return len(removals)

    def _run(self) -> None:
        next_tick = time.monotonic() + self._tick
        while True:
            with self._wake:
                while not self._stopping:
                    deadline = next_tick if self._due_at is None else min(self._due_at, next_tick)
                    if time.monotonic() >= deadline:
                        break
                    self._wake.wait(deadline - time.monotonic())
                if self._stopping:
                    return
                self._due_at = None
                next_tick = time.monotonic() + self._tick
            self.evaluate()


def _said(error: Exception) -> str:
    return str(error) or type(error).__name__


def _wanted_bytes(state: PolicyState) -> int:
    held = sum(each.size for each in state.downloads if each.wanted)
    return held + sum(each.estimate for each in state.wanted)
