"""The download policy at work: real download Jobs through `tube`, kept and removed by the rules."""

import os
import time
import uuid
from collections.abc import Callable, Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application import policy as policy_module
from medleyplay.application.accounts import AccountService
from medleyplay.application.downloads import DOWNLOAD_KIND
from medleyplay.application.policy import PolicyService
from medleyplay.application.settings import SettingsService
from medleyplay.domain.accounts import Account
from medleyplay.domain.catalog import PlaylistId, SourceId, SourceState, TrackId
from medleyplay.domain.downloads import download_target
from medleyplay.domain.errors import ForbiddenError
from medleyplay.domain.jobs import JobState
from medleyplay.domain.playback import CACHE_FOLDER
from medleyplay.domain.policy import (
    REST,
    RETRY_AFTER,
    Plan,
    PolicyState,
    Remove,
    Shortfall,
    plan,
    reservation,
)
from medleyplay.domain.rules import Favorite, Match, Rules
from medleyplay.domain.settings import Settings
from medleyplay.persistence.schema import DownloadRow, PlaylistRow, SourceRow
from tests.support.factories import NewAccountFactory, SourceKeyFactory, TrackDetailsFactory
from tests.support.fakes import FakeClock, MemorySecrets
from tests.support.sites import WAIT, Site, running_site

MIXTAPE = "BV17x411w7KC"
CAR = PlaylistId(uuid.UUID("00000000-0000-4000-8000-0000000000c1"))
NEWER = PlaylistId(uuid.UUID("00000000-0000-4000-8000-0000000000c2"))
COOKIES = "# Netscape HTTP Cookie File\n.bilibili.com\tTRUE\t/\tTRUE\t0\tSESSDATA\tsecret\n"
SONG_ESTIMATE = reservation(TrackDetailsFactory.song().duration_ms, 192)
"""What a download of a song from `TrackDetailsFactory` reserves at the best quality."""


@pytest.fixture
def alice(accounts: AccountService) -> Account:
    return accounts.create_first_admin(NewAccountFactory.admin()).account


@pytest.fixture
def bob(accounts: AccountService, alice: Account) -> Account:
    return accounts.create_account(alice, NewAccountFactory.member())


@pytest.fixture
def site(
    units: sessionmaker[Session], clock: FakeClock, tmp_path: Path, secrets: MemorySecrets
) -> Iterator[Site]:
    with running_site(units, clock, tmp_path / "data", secrets) as running:
        yield running


@pytest.fixture
def policy(units: sessionmaker[Session], clock: FakeClock, site: Site) -> PolicyService:
    return PolicyService(units, clock, site.downloads, site.plugins, site.data_dir)


def _tracks(site: Site, count: int, video: str = MIXTAPE) -> list[TrackId]:
    """Add parts 1 to `count` of a Bilibili video as Tracks, with nothing downloaded."""
    return [
        site.catalog.add_track(SourceKeyFactory.bilibili(video, part), TrackDetailsFactory.song())
        for part in range(1, count + 1)
    ]


def _keep(site: Site, owner: Account, tracks: list[TrackId], *, keep: bool = True) -> None:
    """Put the owner's *Car* Playlist of `tracks`, kept downloaded unless `keep` is off."""
    site.catalog.put_playlist(owner.id, CAR, "Car", tracks, keep_downloaded=keep)


def _source(units: sessionmaker[Session], track_id: TrackId) -> SourceId:
    with units() as db:
        return SourceId(
            db.scalars(select(SourceRow.id).where(SourceRow.track_id == track_id)).one()
        )


def _stored(units: sessionmaker[Session]) -> set[SourceId]:
    with units() as db:
        return {SourceId(each) for each in db.scalars(select(DownloadRow.source_id))}


def _settled(site: Site, source_id: SourceId, *states: JobState) -> None:
    """Wait for the Source's latest download Job, if it has one, to end in one of `states`."""
    job = site.jobs.latest(DOWNLOAD_KIND, download_target(source_id))
    if job is not None:
        site.wait_for(job.id, *states)


def _failed(site: Site, source_id: SourceId) -> None:
    job = site.jobs.latest(DOWNLOAD_KIND, download_target(source_id))
    assert job is not None, f"Source {source_id} was never downloaded."
    site.wait_for(job.id, JobState.FAILED)


def _downloaded(
    site: Site, policy: PolicyService, units: sessionmaker[Session], tracks: list[TrackId]
) -> None:
    """Evaluate until every one of `tracks` is downloaded, as the policy's own thread would."""
    wanted = {_source(units, each) for each in tracks}
    ends = time.monotonic() + WAIT
    while not wanted <= _stored(units):
        assert time.monotonic() < ends, f"{wanted - _stored(units)} never downloaded."
        policy.evaluate()
        for source_id in wanted - _stored(units):
            _settled(site, source_id, JobState.SUCCEEDED)


def _limit(settings: SettingsService, admin: Account, limit: int | None) -> None:
    settings.put(admin, Settings(storage_limit=limit, revision=settings.get().revision))


def _file(site: Site, source_id: SourceId) -> Path:
    return site.data_dir / "downloads" / f"{source_id}.m4a"


def test_a_kept_playlist_downloads_its_tracks_two_at_a_time(
    site: Site, policy: PolicyService, units: sessionmaker[Session], alice: Account
) -> None:
    tracks = _tracks(site, 3)
    _keep(site, alice, tracks)

    first = policy.evaluate()

    assert (first.started, list(first.shortfalls.values())) == (2, [Shortfall.WAITING_TURN])
    _downloaded(site, policy, units, tracks)
    assert policy.evaluate().started == 0


def test_a_lowered_limit_removes_what_no_one_keeps_least_favorite_first(
    site: Site,
    policy: PolicyService,
    units: sessionmaker[Session],
    clock: FakeClock,
    settings: SettingsService,
    alice: Account,
) -> None:
    loved, other = _tracks(site, 2)
    _keep(site, alice, [loved, other])
    _downloaded(site, policy, units, [loved, other])
    _keep(site, alice, [loved, other], keep=False)
    site.catalog.set_favorite(alice.id, loved, favorite=True)
    clock.advance(REST + timedelta(hours=1))
    one_file = _file(site, _source(units, loved)).stat().st_size

    _limit(settings, alice, one_file)
    evaluation = policy.evaluate()

    assert (evaluation.removed, _stored(units)) == (1, {_source(units, loved)})
    assert sorted(path.name for path in (site.data_dir / "downloads").iterdir()) == [
        f"{_source(units, loved)}.m4a"
    ]


def test_nothing_is_removed_within_a_day_of_being_downloaded_or_wanted(
    site: Site,
    policy: PolicyService,
    units: sessionmaker[Session],
    clock: FakeClock,
    settings: SettingsService,
    alice: Account,
) -> None:
    [track] = _tracks(site, 1)
    _keep(site, alice, [track])
    _downloaded(site, policy, units, [track])
    _keep(site, alice, [track], keep=False)
    clock.advance(REST - timedelta(minutes=1))

    _limit(settings, alice, 0)
    evaluation = policy.evaluate()

    assert (evaluation.removed, _stored(units)) == (0, {_source(units, track)})


def test_a_download_served_within_the_day_stays_though_it_is_the_least_favorite(
    site: Site,
    policy: PolicyService,
    units: sessionmaker[Session],
    clock: FakeClock,
    settings: SettingsService,
    alice: Account,
) -> None:
    played, loved = _tracks(site, 2)
    _keep(site, alice, [played, loved])
    _downloaded(site, policy, units, [played, loved])
    _keep(site, alice, [played, loved], keep=False)
    site.catalog.set_favorite(alice.id, loved, favorite=True)
    clock.advance(REST + timedelta(hours=1))
    site.playback.open_audio(_source(units, played)).close()

    _limit(settings, alice, _file(site, _source(units, played)).stat().st_size)
    policy.evaluate()

    assert _stored(units) == {_source(units, played)}


def test_the_download_of_a_video_gone_from_the_site_is_never_removed(
    site: Site,
    policy: PolicyService,
    units: sessionmaker[Session],
    clock: FakeClock,
    settings: SettingsService,
    alice: Account,
) -> None:
    [track] = _tracks(site, 1)
    _keep(site, alice, [track])
    _downloaded(site, policy, units, [track])
    _keep(site, alice, [track], keep=False)
    with units.begin() as db:
        db.execute(update(SourceRow).values(state=SourceState.UNAVAILABLE))
    clock.advance(REST + timedelta(hours=1))

    _limit(settings, alice, 0)
    evaluation = policy.evaluate()

    assert (evaluation.removed, _stored(units)) == (0, {_source(units, track)})


def test_rules_this_server_cant_read_on_a_kept_playlist_stop_every_removal(
    site: Site,
    policy: PolicyService,
    units: sessionmaker[Session],
    clock: FakeClock,
    settings: SettingsService,
    alice: Account,
) -> None:
    [track] = _tracks(site, 1)
    _keep(site, alice, [track])
    _downloaded(site, policy, units, [track])
    _keep(site, alice, [track], keep=False)
    favorites = Rules(Match.ALL, (Favorite(value=True),))
    site.catalog.put_playlist(alice.id, NEWER, "Newer", rules=favorites, keep_downloaded=True)
    with units.begin() as db:
        newer = {"version": 2, "match": "all", "conditions": []}
        db.execute(update(PlaylistRow).where(PlaylistRow.id == NEWER).values(rules=newer))
    clock.advance(REST + timedelta(hours=1))

    _limit(settings, alice, 0)
    evaluation = policy.evaluate()

    assert (evaluation.removed, _stored(units)) == (0, {_source(units, track)})
    assert evaluation.error is not None
    assert "'Newer'" in evaluation.error
    assert policy.storage(alice).error == evaluation.error


def _hearing_a_change_while_planning(
    site: Site, policy: PolicyService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Make every snapshot hear a change as it is read, as a concurrent edit would."""
    available_keys = site.plugins.available_keys

    def heard_a_change() -> dict[str, list[str]]:
        policy.request("catalog")
        return available_keys()

    monkeypatch.setattr(site.plugins, "available_keys", heard_a_change)


def test_a_change_heard_while_planning_drops_the_plan_and_asks_again(
    site: Site,
    policy: PolicyService,
    units: sessionmaker[Session],
    clock: FakeClock,
    settings: SettingsService,
    alice: Account,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old, new = _tracks(site, 2)
    _keep(site, alice, [old])
    _downloaded(site, policy, units, [old])
    clock.advance(REST + timedelta(hours=1))
    _keep(site, alice, [new])
    _limit(settings, alice, SONG_ESTIMATE)
    _hearing_a_change_while_planning(site, policy, monkeypatch)

    dropped = policy.evaluate()
    monkeypatch.undo()
    again = policy.evaluate()

    assert (dropped.plan_dropped, dropped.removed, dropped.started) == (True, 0, 0)
    assert (again.removed, again.started) == (1, 1)


def test_a_change_heard_while_planning_keeps_cache_copies_too(
    site: Site,
    policy: PolicyService,
    clock: FakeClock,
    settings: SettingsService,
    alice: Account,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    copy = _old_cache_copy(site, clock)
    _limit(settings, alice, 0)
    _hearing_a_change_while_planning(site, policy, monkeypatch)

    evaluation = policy.evaluate()

    assert (evaluation.plan_dropped, copy.exists()) == (True, True)


def test_a_download_served_after_the_snapshot_is_judged_again_and_stays(
    site: Site,
    policy: PolicyService,
    units: sessionmaker[Session],
    clock: FakeClock,
    settings: SettingsService,
    alice: Account,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    [track] = _tracks(site, 1)
    _keep(site, alice, [track])
    _downloaded(site, policy, units, [track])
    _keep(site, alice, [track], keep=False)
    clock.advance(REST + timedelta(hours=1))
    _limit(settings, alice, 0)

    def served_while_planning(state: PolicyState) -> Plan:
        planned = plan(state)
        site.downloads.served(_source(units, track))
        return planned

    monkeypatch.setattr(policy_module, "plan", served_while_planning)
    evaluation = policy.evaluate()

    assert (evaluation.removed, _stored(units)) == (0, {_source(units, track)})


def test_a_download_that_failed_is_tried_again_a_day_later_not_sooner(
    site: Site,
    policy: PolicyService,
    units: sessionmaker[Session],
    clock: FakeClock,
    alice: Account,
) -> None:
    [track] = _tracks(site, 1, video="BVrefused")
    _keep(site, alice, [track])
    policy.evaluate()
    _failed(site, _source(units, track))

    soon = policy.evaluate()
    clock.advance(RETRY_AFTER)
    later = policy.evaluate()

    assert (soon.shortfalls, soon.started) == ({track: Shortfall.FAILING}, 0)
    assert later.started == 1


def test_a_login_saved_after_it_failed_on_one_tries_again_at_once(
    site: Site,
    policy: PolicyService,
    units: sessionmaker[Session],
    clock: FakeClock,
    alice: Account,
) -> None:
    [track] = _tracks(site, 1, video="BVSignedIn")
    _keep(site, alice, [track])
    policy.evaluate()
    _failed(site, _source(units, track))
    clock.advance(timedelta(minutes=1))

    site.linked.save(alice, "bilibili", COOKIES)

    _downloaded(site, policy, units, [track])


def _old_cache_copy(site: Site, clock: FakeClock) -> Path:
    """Write a 5-byte cache copy last served more than a day ago."""
    copy = site.data_dir / CACHE_FOLDER / "7-v1.flac"
    copy.parent.mkdir(parents=True, exist_ok=True)
    copy.write_bytes(b"audio")
    old = (clock.now - REST - timedelta(hours=1)).timestamp()
    os.utime(copy, (old, old))
    return copy


def test_a_cache_copy_untouched_for_a_day_goes_before_any_download(
    site: Site,
    policy: PolicyService,
    units: sessionmaker[Session],
    clock: FakeClock,
    settings: SettingsService,
    alice: Account,
) -> None:
    [track] = _tracks(site, 1)
    _keep(site, alice, [track])
    _downloaded(site, policy, units, [track])
    _keep(site, alice, [track], keep=False)
    clock.advance(REST + timedelta(hours=1))
    copy = _old_cache_copy(site, clock)
    one_file = _file(site, _source(units, track)).stat().st_size

    _limit(settings, alice, one_file)
    evaluation = policy.evaluate()

    assert (evaluation.removed, copy.exists(), _stored(units)) == (
        1,
        False,
        {_source(units, track)},
    )


def test_a_download_kept_until_yesterday_stays_a_day_after_it_was_last_wanted(
    site: Site,
    policy: PolicyService,
    units: sessionmaker[Session],
    clock: FakeClock,
    settings: SettingsService,
    alice: Account,
) -> None:
    [track] = _tracks(site, 1)
    _keep(site, alice, [track])
    _downloaded(site, policy, units, [track])
    clock.advance(timedelta(hours=30))
    policy.evaluate()
    _keep(site, alice, [track], keep=False)
    clock.advance(timedelta(hours=23))

    _limit(settings, alice, 0)
    evaluation = policy.evaluate()

    assert (evaluation.removed, _stored(units)) == (0, {_source(units, track)})


def test_a_kept_smart_playlist_downloads_what_its_rules_match_for_its_owner(
    site: Site, policy: PolicyService, units: sessionmaker[Session], alice: Account, bob: Account
) -> None:
    alices, bobs = _tracks(site, 2)
    site.catalog.set_favorite(alice.id, alices, favorite=True)
    site.catalog.set_favorite(bob.id, bobs, favorite=True)
    favorites = Rules(Match.ALL, (Favorite(value=True),))

    site.catalog.put_playlist(alice.id, NEWER, "Favorites", rules=favorites, keep_downloaded=True)
    evaluation = policy.evaluate()

    assert evaluation.started == 1
    _downloaded(site, policy, units, [alices])
    assert _stored(units) == {_source(units, alices)}


def test_the_storage_report_counts_what_each_account_keeps(
    site: Site, policy: PolicyService, units: sessionmaker[Session], alice: Account, bob: Account
) -> None:
    shared, bobs = _tracks(site, 2)
    _keep(site, alice, [shared])
    _downloaded(site, policy, units, [shared])
    site.catalog.put_playlist(bob.id, NEWER, "Bob's", [shared, bobs], keep_downloaded=True)
    size = _file(site, _source(units, shared)).stat().st_size

    storage = policy.storage(bob)

    assert (storage.limit, storage.downloads, storage.wanted) == (None, size, size + SONG_ESTIMATE)
    assert storage.wanted_by_account == {alice.id: size, bob.id: size + SONG_ESTIMATE}


def test_an_admin_previews_another_limit_without_anything_removed(
    site: Site,
    policy: PolicyService,
    units: sessionmaker[Session],
    clock: FakeClock,
    alice: Account,
    bob: Account,
) -> None:
    [track] = _tracks(site, 1)
    _keep(site, alice, [track])
    _downloaded(site, policy, units, [track])
    _keep(site, alice, [track], keep=False)
    clock.advance(REST + timedelta(hours=1))
    size = _file(site, _source(units, track)).stat().st_size

    preview = policy.storage(alice, preview_limit=0).preview

    assert preview is not None
    assert preview.removals == (Remove(_source(units, track), size),)
    assert _stored(units) == {_source(units, track)}
    with pytest.raises(ForbiddenError):
        policy.storage(bob, preview_limit=0)


def test_a_request_is_evaluated_on_a_thread_of_the_policy_service(
    site: Site, units: sessionmaker[Session], clock: FakeClock, alice: Account
) -> None:
    policy = PolicyService(
        units, clock, site.downloads, site.plugins, site.data_dir, delay=timedelta(0)
    )
    [track] = _tracks(site, 1)
    policy.start()
    try:
        _until(lambda: policy.storage(alice).last is not None, "never evaluated at start")
        _keep(site, alice, [track])

        policy.request("catalog")

        source_id = _source(units, track)
        _until(
            lambda: site.jobs.latest(DOWNLOAD_KIND, download_target(source_id)) is not None,
            "never evaluated the request",
        )
    finally:
        policy.stop()


def _until(holds: Callable[[], bool], what: str) -> None:
    ends = time.monotonic() + WAIT
    while not holds():
        assert time.monotonic() < ends, f"The policy {what}."
        time.sleep(0.05)
