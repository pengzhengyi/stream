"""The download policy: a pure plan of what to download and what to remove.

`plan` reads a snapshot and returns what to do; it never touches a file. It
makes room for each wanted Track in turn, most favored first, by removing what
may be removed in removal order, cache copies first:

```text
limit 100 MB, use 95 MB, a wanted Track of 10 MB
  -> remove a 4 MB cache copy and a 3 MB unwanted Download, start the Track
```

Nothing is removed without a limit, and nothing wanted, irreplaceable, at rest
for less than a day, or with an active Job is ever removed.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final

from medleyplay.domain.accounts import AccountId
from medleyplay.domain.catalog import SourceId, TrackId

REST: Final = timedelta(hours=24)
"""How long a file must go untouched, not downloaded, served, or wanted, before it may go."""
RETRY_AFTER: Final = timedelta(days=1)
MAX_FAILURES: Final = 3
"""A wanted Source the policy has seen fail this many times in a row waits for the household."""
MAX_ACTIVE: Final = 2
"""The most download Jobs active at once that the policy starts more beside."""
MIN_FREE: Final = 2 * 1024**3
MIN_FREE_SHARE: Final = 0.05
BEST_KBPS: Final = 192
UNKNOWN_SIZE: Final = 16 * 1024**2


class Shortfall(StrEnum):
    """Why a wanted Track has no Download yet."""

    DOWNLOADING = "downloading"
    WAITING_TURN = "waiting_turn"
    OVER_LIMIT = "over_limit"
    DISK_FULL = "disk_full"
    FAILING = "failing"
    NO_PLUGIN = "no_plugin"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class Standing:
    """How favored a Track is, across every Account; a smaller one is removed first.

    The order is the removal order, *least favorite*: no Account's favorite first,
    then the best rating, unrated first, then least recently played, never played
    first, then oldest added.
    """

    favorite: bool
    best_rating: int | None
    last_played_at: datetime | None
    added_at: datetime

    def key(self) -> tuple[bool, int, float, float]:
        """Return the sort key: smaller is removed first."""
        played = self.last_played_at.timestamp() if self.last_played_at else float("-inf")
        return (self.favorite, self.best_rating or 0, played, self.added_at.timestamp())


@dataclass(frozen=True)
class Failure:
    """A wanted Source's last download failures in a row, and whether their cause changed since.

    `cleared` says the cause is gone: a login saved again after a login failure.
    """

    failed_at: datetime
    in_a_row: int
    cleared: bool = False


@dataclass(frozen=True)
class Wanted:
    """A wanted Track with no Download, and the site Source the policy would download."""

    track_id: TrackId
    source_id: SourceId
    site: str
    estimate: int
    standing: Standing
    wanted_by: tuple[AccountId, ...]
    source_ok: bool = True
    active_job: bool = False
    failure: Failure | None = None


@dataclass(frozen=True)
class StoredDownload:
    """A Download on disk, and what decides whether it may be removed."""

    source_id: SourceId
    size: int
    standing: Standing
    downloaded_at: datetime
    last_served_at: datetime | None = None
    last_wanted_at: datetime | None = None
    wanted: bool = False
    replaceable: bool = True
    active_job: bool = False

    def touched_at(self) -> datetime:
        """Return when it was last downloaded, served, or wanted."""
        return max(t for t in (self.downloaded_at, self.last_served_at, self.last_wanted_at) if t)


@dataclass(frozen=True)
class CacheCopy:
    """A cache copy on disk, and when it was last written or served."""

    name: str
    size: int
    touched_at: datetime


@dataclass(frozen=True)
class PolicyState:
    """Everything `plan` decides from, read in one transaction."""

    now: datetime
    limit: int | None
    free: int
    """Free bytes on the data folder's disk."""
    disk_size: int
    downloads: tuple[StoredDownload, ...] = ()
    cache: tuple[CacheCopy, ...] = ()
    wanted: tuple[Wanted, ...] = ()
    reserved: int = 0
    """The reservations of every active download Job."""
    active_policy_jobs: int = 0
    downloadable_sites: frozenset[str] = frozenset()
    valid_logins: frozenset[tuple[AccountId, str]] = frozenset()

    def use(self) -> int:
        """Return the bytes the limit counts: Downloads, cache copies, and reservations."""
        stored = sum(each.size for each in self.downloads) + sum(each.size for each in self.cache)
        return stored + self.reserved

    def min_free(self) -> int:
        """Return the free space a Download must leave on the disk."""
        return max(MIN_FREE, int(self.disk_size * MIN_FREE_SHARE))


@dataclass(frozen=True)
class Start:
    """Start downloading a wanted Track's Source, as the Account whose login it uses, if any."""

    track_id: TrackId
    source_id: SourceId
    requester: AccountId
    estimate: int


@dataclass(frozen=True)
class Remove:
    """Remove a Download."""

    source_id: SourceId
    size: int


@dataclass(frozen=True)
class RemoveCache:
    """Remove a cache copy."""

    name: str
    size: int


@dataclass(frozen=True)
class Plan:
    """What to remove, then start, and what the plan couldn't do."""

    removals: tuple[Remove | RemoveCache, ...] = ()
    starts: tuple[Start, ...] = ()
    shortfalls: dict[TrackId, Shortfall] = field(default_factory=dict)
    wanted_downloads: frozenset[SourceId] = frozenset()
    """The Downloads that are wanted now, whose last wanted time the plan's applying sets."""

    def is_empty(self) -> bool:
        """Return whether the plan removes and starts nothing."""
        return not self.removals and not self.starts


def reservation(duration_ms: int | None, kbps: int) -> int:
    """Return the bytes a download of this length and bitrate reserves: its size, plus a tenth.

    A length that isn't known, or isn't positive, counts as `UNKNOWN_SIZE`.
    """
    if duration_ms is None or duration_ms <= 0:
        return UNKNOWN_SIZE
    return int(duration_ms / 1000 * kbps * 1000 / 8 * 1.1)


def removable(state: PolicyState) -> list[Remove | RemoveCache]:
    """Return what may be removed, in the order it goes: cache copies, then Downloads."""
    if state.limit is None:
        return []
    cache = sorted(
        (each for each in state.cache if state.now - each.touched_at >= REST),
        key=lambda each: (each.touched_at, each.name),
    )
    downloads = sorted(
        (each for each in state.downloads if _may_remove(each, state.now)),
        key=lambda each: (each.standing.key(), each.source_id),
    )
    return [
        *(RemoveCache(each.name, each.size) for each in cache),
        *(Remove(each.source_id, each.size) for each in downloads),
    ]


def plan(state: PolicyState) -> Plan:
    """Return what to remove and start so wanted Tracks have Downloads, within the limit."""
    pool = removable(state)
    taken = 0
    use, free = state.use(), state.free - state.reserved
    slots = MAX_ACTIVE - state.active_policy_jobs
    starts: list[Start] = []
    shortfalls: dict[TrackId, Shortfall] = {}
    for wanted in _favored_first(state.wanted):
        why = _unstartable(wanted, state)
        if why is None and slots <= 0:
            why = Shortfall.WAITING_TURN
        if why is not None:
            shortfalls[wanted.track_id] = why
            continue
        need = _room_needed(state, use, free, wanted.estimate)
        count = _prefix_freeing(pool[taken:], need)
        if count is None:
            limited = state.limit is not None and use + wanted.estimate > state.limit
            shortfalls[wanted.track_id] = Shortfall.OVER_LIMIT if limited else Shortfall.DISK_FULL
            continue
        freed = sum(each.size for each in pool[taken : taken + count])
        taken += count
        use, free = use - freed + wanted.estimate, free + freed - wanted.estimate
        slots -= 1
        requester = _requester(wanted, state)
        starts.append(Start(wanted.track_id, wanted.source_id, requester, wanted.estimate))
    # A lowered limit is met by removing; a limit nothing removable can meet leaves all in place.
    if state.limit is not None and use > state.limit:
        taken += _prefix_freeing(pool[taken:], use - state.limit) or 0
    return Plan(
        removals=tuple(pool[:taken]),
        starts=tuple(starts),
        shortfalls=shortfalls,
        wanted_downloads=frozenset(each.source_id for each in state.downloads if each.wanted),
    )


def _may_remove(download: StoredDownload, now: datetime) -> bool:
    return (
        not download.wanted
        and download.replaceable
        and not download.active_job
        and now - download.touched_at() >= REST
    )


def _favored_first(wanted: Iterable[Wanted]) -> list[Wanted]:
    return sorted(wanted, key=lambda each: (each.standing.key(), each.source_id), reverse=True)


def _unstartable(wanted: Wanted, state: PolicyState) -> Shortfall | None:
    if wanted.active_job:
        return Shortfall.DOWNLOADING
    if not wanted.source_ok:
        return Shortfall.UNAVAILABLE
    if wanted.site not in state.downloadable_sites:
        return Shortfall.NO_PLUGIN
    if wanted.failure is not None and not _due(wanted.failure, state.now):
        return Shortfall.FAILING
    return None


def _due(failure: Failure, now: datetime) -> bool:
    if failure.cleared:
        return True
    return failure.in_a_row <= MAX_FAILURES and now - failure.failed_at >= RETRY_AFTER


def _room_needed(state: PolicyState, use: int, free: int, estimate: int) -> int:
    """Return the bytes to remove before a Download of `estimate` fits the limit and the disk."""
    over_disk = state.min_free() + estimate - free
    over_limit = 0 if state.limit is None else use + estimate - state.limit
    return max(0, over_disk, over_limit)


def _prefix_freeing(pool: Sequence[Remove | RemoveCache], need: int) -> int | None:
    """Return how many of `pool`, from the start, free at least `need` bytes, or `None`."""
    freed = 0
    for count, each in enumerate(pool):
        if freed >= need:
            return count
        freed += each.size
    return len(pool) if freed >= need else None


def _requester(wanted: Wanted, state: PolicyState) -> AccountId:
    signed_in = [each for each in wanted.wanted_by if (each, wanted.site) in state.valid_logins]
    return min(signed_in or wanted.wanted_by)
