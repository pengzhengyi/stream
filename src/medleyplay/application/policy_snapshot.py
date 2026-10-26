"""Reading everything the download policy plans from, in one transaction.

The snapshot fails closed: a *Keep downloaded* Playlist whose rules can't be
read raises `UnreadableRulesError`, so an evaluation that can't tell what is
wanted removes nothing.
"""

import shutil
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from medleyplay.application.downloads import DOWNLOAD_KIND, QUALITY_DETAIL
from medleyplay.application.rule_schema import read_rules
from medleyplay.application.track_facts import track_facts
from medleyplay.domain.accounts import AccountId
from medleyplay.domain.catalog import SourceId, SourceState, TrackId
from medleyplay.domain.downloads import download_target, quality_kbps
from medleyplay.domain.errors import InvalidInputError
from medleyplay.domain.jobs import ACTIVE_STATES, JobState
from medleyplay.domain.libraries import LIBRARY_SOURCE
from medleyplay.domain.linked_accounts import LinkState
from medleyplay.domain.playback import CACHE_FOLDER
from medleyplay.domain.policy import (
    CacheCopy,
    Failure,
    PolicyState,
    Standing,
    StoredDownload,
    Wanted,
    reservation,
)
from medleyplay.domain.rules import TrackFacts, matches
from medleyplay.persistence.schema import (
    DownloadRow,
    JobRow,
    LinkedAccountRow,
    PlaylistEntryRow,
    PlaylistRow,
    SourceRow,
    TrackRow,
    TrackStateRow,
)


class UnreadableRulesError(InvalidInputError):
    """A *Keep downloaded* Playlist's stored rules can't be read, so nothing may be removed."""


@dataclass(frozen=True)
class Snapshot:
    """The policy's state, and what it needs to report and to remove files."""

    state: PolicyState
    wanted_bytes: Mapping[AccountId, int]
    """The space each Account's wants hold: their Downloads, and estimates for the rest."""
    file_names: Mapping[SourceId, str]


@dataclass(frozen=True)
class _Source:
    id: SourceId
    track_id: TrackId
    kind: str
    state: str
    quality: str


def read_snapshot(
    db: Session,
    now: datetime,
    limit: int | None,
    downloadable_sites: Iterable[str],
    data_dir: Path,
) -> Snapshot:
    """Return the policy's state as the database and the data folder hold it now."""
    sites = frozenset(downloadable_sites)
    wanted_by = _wanted_by(db, now)
    sources = [
        _Source(
            SourceId(row.id),
            TrackId(row.track_id),
            row.kind,
            row.state,
            str((row.details or {}).get(QUALITY_DETAIL, "best")),
        )
        for row in db.scalars(select(SourceRow).order_by(SourceRow.id))
    ]
    by_track: defaultdict[TrackId, list[_Source]] = defaultdict(list)
    for source in sources:
        by_track[source.track_id].append(source)
    standings, durations = _standings(db)
    downloads = {SourceId(row.source_id): row for row in db.scalars(select(DownloadRow))}
    active = set(
        db.scalars(
            select(JobRow.target).where(
                JobRow.kind == DOWNLOAD_KIND, JobRow.state.in_(ACTIVE_STATES)
            )
        )
    )
    source_of = {source.id: source for source in sources}

    def estimate(source: _Source) -> int:
        return reservation(durations.get(source.track_id), quality_kbps(source.quality))

    stored = tuple(
        StoredDownload(
            source_id=source_id,
            size=row.size,
            standing=standings[source_of[source_id].track_id],
            downloaded_at=row.downloaded_at,
            last_served_at=row.last_served_at,
            last_wanted_at=row.last_wanted_at,
            wanted=source_of[source_id].track_id in wanted_by,
            replaceable=source_of[source_id].state == SourceState.OK
            and source_of[source_id].kind in sites,
            active_job=download_target(source_id) in active,
        )
        for source_id, row in downloads.items()
        if source_id in source_of
    )
    logins = _valid_logins(db, now)
    wanted: list[Wanted] = []
    held: defaultdict[AccountId, int] = defaultdict(int)
    for track_id, accounts in wanted_by.items():
        own = by_track.get(track_id, [])
        site_sources = [each for each in own if each.kind != LIBRARY_SOURCE]
        downloaded = [each for each in site_sources if each.id in downloads]
        for account_id in accounts:
            held[account_id] += sum(downloads[each.id].size for each in downloaded)
        has_library = any(
            each.kind == LIBRARY_SOURCE and each.state == SourceState.OK for each in own
        )
        if not site_sources or downloaded or has_library:
            continue
        startable = [
            each for each in site_sources if each.kind in sites and each.state == SourceState.OK
        ]
        chosen = (startable or site_sources)[0]
        for account_id in accounts:
            held[account_id] += estimate(chosen)
        wanted.append(
            Wanted(
                track_id=track_id,
                source_id=chosen.id,
                site=chosen.kind,
                estimate=estimate(chosen),
                standing=standings[track_id],
                wanted_by=tuple(sorted(accounts)),
                source_ok=chosen.state == SourceState.OK,
                active_job=download_target(chosen.id) in active,
                failure=_failure(db, chosen, accounts, logins),
            )
        )
    disk = shutil.disk_usage(data_dir)
    state = PolicyState(
        now=now,
        limit=limit,
        free=disk.free,
        disk_size=disk.total,
        downloads=stored,
        cache=_cache_copies(data_dir),
        wanted=tuple(wanted),
        reserved=sum(
            estimate(source_of[_source_of_target(t)])
            for t in active
            if _source_of_target(t) in source_of
        ),
        active_policy_jobs=len(active),
        downloadable_sites=sites,
        valid_logins=frozenset(logins),
    )
    return Snapshot(
        state,
        dict(held),
        {source_id: row.file_name for source_id, row in downloads.items()},
    )


def _wanted_by(db: Session, now: datetime) -> dict[TrackId, set[AccountId]]:
    wanted: defaultdict[TrackId, set[AccountId]] = defaultdict(set)
    facts: dict[AccountId, dict[TrackId, TrackFacts]] = {}
    for playlist in db.scalars(select(PlaylistRow).where(PlaylistRow.keep_downloaded)):
        owner = AccountId(playlist.account_id)
        if playlist.rules is None:
            entries = db.scalars(
                select(PlaylistEntryRow.track_id).where(PlaylistEntryRow.playlist_id == playlist.id)
            )
            for track_id in entries:
                wanted[TrackId(track_id)].add(owner)
            continue
        try:
            rules = read_rules(playlist.rules)
        except InvalidInputError as error:
            message = f"The Playlist {playlist.name!r} keeps rules this server can't read: {error}"
            raise UnreadableRulesError(message) from None
        seen = facts.setdefault(owner, track_facts(db, owner))
        for track_id, each in seen.items():
            if matches(rules, each, now):
                wanted[track_id].add(owner)
    return dict(wanted)


def _standings(db: Session) -> tuple[defaultdict[TrackId, Standing], dict[TrackId, int | None]]:
    """Return how favored each Track is across every Account, and each Track's duration."""
    states: defaultdict[int, list[TrackStateRow]] = defaultdict(list)
    for row in db.scalars(select(TrackStateRow)):
        states[row.track_id].append(row)
    standings: dict[TrackId, Standing] = {}
    durations: dict[TrackId, int | None] = {}
    for track in db.scalars(select(TrackRow)):
        own = states.get(track.id, [])
        ratings = [each.rating for each in own if each.rating is not None]
        played = [each.last_played_at for each in own if each.last_played_at is not None]
        standings[TrackId(track.id)] = Standing(
            favorite=any(each.favorite for each in own),
            best_rating=max(ratings, default=None),
            last_played_at=max(played, default=None),
            added_at=track.added_at,
        )
        durations[TrackId(track.id)] = track.duration_ms
    epoch = datetime.fromtimestamp(0, UTC)
    fallback = Standing(favorite=False, best_rating=None, last_played_at=None, added_at=epoch)
    return defaultdict(lambda: fallback, standings), durations


def _valid_logins(db: Session, now: datetime) -> set[tuple[AccountId, str]]:
    return {
        (AccountId(row.account_id), row.site)
        for row in db.scalars(select(LinkedAccountRow))
        if row.state == LinkState.VALID and (row.expires_at is None or row.expires_at > now)
    }


def _failure(
    db: Session,
    source: _Source,
    accounts: set[AccountId],
    logins: set[tuple[AccountId, str]],
) -> Failure | None:
    """Return the Source's last download failures in a row, if its last Job failed."""
    jobs = db.execute(
        select(JobRow.state, JobRow.failure_kind, JobRow.finished_at)
        .where(JobRow.kind == DOWNLOAD_KIND, JobRow.target == download_target(source.id))
        .order_by(JobRow.id.desc())
        .limit(10)
    ).all()
    in_a_row = 0
    for state, _kind, _finished in jobs:
        if state != JobState.FAILED:
            break
        in_a_row += 1
    if not in_a_row:
        return None
    _state, kind, finished_at = jobs[0]
    failed_at = finished_at or datetime.fromtimestamp(0, UTC)
    # A login failure is cleared once an Account that wants the Track saves a valid login again.
    saved = db.execute(
        select(LinkedAccountRow.account_id, LinkedAccountRow.saved_at).where(
            LinkedAccountRow.site == source.kind, LinkedAccountRow.account_id.in_(accounts)
        )
    )
    cleared = kind == "auth" and any(
        when > failed_at and (AccountId(account_id), source.kind) in logins
        for account_id, when in saved
    )
    return Failure(failed_at, in_a_row, cleared=cleared)


def _cache_copies(data_dir: Path) -> tuple[CacheCopy, ...]:
    folder = data_dir / CACHE_FOLDER
    if not folder.is_dir():
        return ()
    copies = []
    for path in folder.iterdir():
        info = path.lstat()
        if path.is_file() and not path.is_symlink():
            copies.append(
                CacheCopy(path.name, info.st_size, _touched_at(info.st_atime, info.st_mtime))
            )
    return tuple(copies)


def _touched_at(accessed: float, modified: float) -> datetime:
    """Return when a cache copy was last written or served, which sets its access time."""
    return datetime.fromtimestamp(max(accessed, modified), UTC)


def _source_of_target(target: str) -> SourceId:
    return SourceId(int(target.removeprefix("source:")))
