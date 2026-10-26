"""Downloading a Bilibili Source in a real Job, through the test plugin `tube`, and playing it."""

import os
import time
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application.accounts import AccountService
from medleyplay.application.job_runner import NETWORK_RETRY
from medleyplay.application.links import Added, PartChoice
from medleyplay.application.playback import Preparing, Ready, Unplayable
from medleyplay.domain.accounts import Account
from medleyplay.domain.catalog import Availability, SourceState
from medleyplay.domain.downloads import DOWNLOAD_EXTENSIONS, MAX_DOWNLOAD_BYTES, download_target
from medleyplay.domain.errors import NotFoundError
from medleyplay.domain.jobs import JobId, JobState, JobView
from medleyplay.domain.linked_accounts import LinkState
from medleyplay.domain.plugins import PluginState
from medleyplay.persistence.schema import DownloadRow, SourceRow
from medleyplay.programs.download_source import DownloadSource
from tests.support.factories import NewAccountFactory
from tests.support.fakes import FakeClock, MemorySecrets
from tests.support.sites import Site, running_site

SESSION = ".bilibili.com\tTRUE\t/\tTRUE\t0\tSESSDATA\tsecret-session"
COOKIES = f"# Netscape HTTP Cookie File\n{SESSION}\n"


@pytest.fixture
def alice(accounts: AccountService) -> Account:
    return accounts.create_first_admin(NewAccountFactory.admin()).account


@pytest.fixture
def site(
    units: sessionmaker[Session], clock: FakeClock, tmp_path: Path, secrets: MemorySecrets
) -> Iterator[Site]:
    with running_site(units, clock, tmp_path / "data", secrets) as running:
        yield running


def _added(site: Site, alice: Account, video: str, quality: str = "best") -> Added:
    """Add the first part of `video`, as the household would from its link."""
    link = f"https://www.bilibili.com/video/{video}"
    return site.links.add(alice, link, quality, [PartChoice(1, "Night Drive", "Blue Room")])[0]


def _finished(site: Site, added: Added) -> JobView:
    assert added.job is not None
    return site.wait_for(added.job.id, JobState.SUCCEEDED)


def _failed(site: Site, added: Added) -> JobView:
    """Wait for the Job's first failure: final, or before its next attempt."""
    assert added.job is not None
    return site.wait_for(
        added.job.id,
        JobState.QUEUED,
        JobState.FAILED,
        until=lambda view: view.job.failure_kind is not None,
    )


def _given_up(site: Site, clock: FakeClock, job_id: JobId) -> JobView:
    """Wait for the Job to fail for good, moving the clock past each retry's delay."""
    while True:
        view = site.wait_for(
            job_id,
            JobState.QUEUED,
            JobState.FAILED,
            until=lambda each: each.job.failure_kind is not None,
        )
        if view.job.state is JobState.FAILED:
            return view
        clock.advance(timedelta(hours=1))
        time.sleep(0.05)


def _job_id(added: Added) -> JobId:
    assert added.job is not None
    return added.job.id


def _wait_until_gone(path: Path) -> None:
    """Wait for the runner to remove a finished Job's working folder, as it does after settling."""
    ends = time.monotonic() + 10
    while path.exists():
        assert time.monotonic() < ends, f"{path} is still there."
        time.sleep(0.05)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_a_download_lands_in_downloads_named_by_its_source_and_plays(
    site: Site, alice: Account, units: sessionmaker[Session], clock: FakeClock
) -> None:
    added = _added(site, alice, "BV1Xx41117Tz")

    _finished(site, added)

    file = site.data_dir / "downloads" / f"{added.source_id}.m4a"
    assert _read(file) == "BV1Xx41117Tz/p1 quality=30280 login=none mode=none"
    with units() as db:
        row = db.get_one(DownloadRow, added.source_id)
        assert (row.file_name, row.quality, row.backend, row.size, row.downloaded_at) == (
            file.name,
            "30280",
            "tube",
            file.stat().st_size,
            clock.now,
        )
    assert site.playback.play(alice, added.track_id) == Ready(added.source_id, "audio/mp4")
    audio = site.playback.open_audio(added.source_id)
    try:
        assert os.pread(audio.descriptor, audio.length, 0) == file.read_bytes()
    finally:
        audio.close()


def test_a_download_asks_for_the_quality_chosen_when_adding(site: Site, alice: Account) -> None:
    added = _added(site, alice, "BV1Xx41117Tz", quality="30216")

    _finished(site, added)

    assert "quality=30216" in _read(site.data_dir / "downloads" / f"{added.source_id}.m4a")


def test_a_download_gets_a_copy_of_the_valid_login_only_its_owner_reads(
    site: Site, alice: Account
) -> None:
    site.linked.save(alice, "bilibili", COOKIES)

    added = _added(site, alice, "BVSignedIn")
    view = _finished(site, added)

    said = _read(site.data_dir / "downloads" / f"{added.source_id}.m4a")
    assert said == f"BVSignedIn/p1 quality=30280 login={SESSION} mode=0o600"
    _wait_until_gone(site.data_dir / "jobs" / str(view.job.id))


def test_a_download_that_needs_a_login_fails_without_one_saying_so(
    site: Site, alice: Account
) -> None:
    view = _failed(site, _added(site, alice, "BVSignedIn"))

    assert (view.job.failure_kind, "refused the login" in view.job.failure_message) == (
        "auth",
        True,
    )


def test_a_login_the_site_refuses_needs_sign_in(site: Site, alice: Account) -> None:
    site.linked.save(alice, "bilibili", COOKIES)

    _failed(site, _added(site, alice, "BVrefused"))

    assert [each.state for each in site.linked.list_linked(alice)] == [LinkState.NEEDS_SIGN_IN]


def test_a_failure_message_never_keeps_the_login(site: Site, alice: Account) -> None:
    site.linked.save(alice, "bilibili", COOKIES)

    view = _failed(site, _added(site, alice, "BVleaky"))

    assert "secret-session" not in view.job.failure_message
    assert "<redacted>" in view.job.failure_message


def test_a_part_the_site_no_longer_has_makes_its_source_unavailable(
    site: Site, alice: Account, units: sessionmaker[Session]
) -> None:
    added = _added(site, alice, "BVremoved")

    _finished(site, added)

    with units() as db:
        assert db.get_one(SourceRow, added.source_id).state == SourceState.UNAVAILABLE
    assert site.playback.play(alice, added.track_id) == Unplayable(Availability.UNAVAILABLE)
    with pytest.raises(NotFoundError):
        site.playback.open_audio(added.source_id)


@pytest.mark.parametrize(
    ("video", "why"),
    [
        ("BVescape", "isn't a file directly in its folder"),
        ("BVtext", "isn't an accepted type"),
        ("BVempty", "0 bytes long"),
        ("BVlink", "can't be opened"),
    ],
)
def test_a_file_the_core_cant_trust_fails_the_download_as_a_plugin_fault(
    site: Site, alice: Account, video: str, why: str
) -> None:
    view = _failed(site, _added(site, alice, video))

    assert view.job.failure_kind == "plugin"
    assert why in view.job.failure_message
    assert not list((site.data_dir / "downloads").glob("*"))


def test_a_download_still_plays_when_its_source_is_unavailable_since(
    site: Site, alice: Account, units: sessionmaker[Session]
) -> None:
    added = _added(site, alice, "BV1Xx41117Tz")
    _finished(site, added)
    with units.begin() as db:
        db.execute(update(SourceRow).values(state=SourceState.UNAVAILABLE))

    assert site.playback.play(alice, added.track_id) == Ready(added.source_id, "audio/mp4")
    site.playback.open_audio(added.source_id).close()
    track = site.catalog.get_track(alice.id, added.track_id)
    assert track.availability is Availability.OK


def test_a_source_without_a_download_answers_preparing_with_its_download(
    site: Site, alice: Account, units: sessionmaker[Session]
) -> None:
    added = _added(site, alice, "BV1Xx41117Tz")
    _finished(site, added)
    (site.data_dir / "downloads" / f"{added.source_id}.m4a").unlink()

    preparing = site.playback.play(alice, added.track_id)

    assert not isinstance(preparing, Ready | Unplayable)
    assert preparing.job.target == f"source:{added.source_id}"


def test_the_sweep_removes_files_no_download_names(
    site: Site, alice: Account, units: sessionmaker[Session]
) -> None:
    added = _added(site, alice, "BV1Xx41117Tz")
    _finished(site, added)
    stray = site.data_dir / "downloads" / "99.m4a"
    stray.write_text("left by a crash", encoding="utf-8")

    site.playback.sweep_downloads()

    with units() as db:
        named = list(db.scalars(select(DownloadRow.file_name)))
    assert sorted(path.name for path in (site.data_dir / "downloads").iterdir()) == named


def test_a_plugin_fault_never_keeps_the_login(site: Site, alice: Account, clock: FakeClock) -> None:
    site.linked.save(alice, "bilibili", COOKIES)
    first = _given_up(site, clock, _job_id(_added(site, alice, "BVleaky")))

    _given_up(site, clock, site.jobs.retry(alice, first.job.id).id)

    [tube] = [each for each in site.plugins.statuses(alice) if each.name == "tube"]
    assert tube.state is PluginState.FAULTED
    assert "secret-session" not in tube.reason
    assert "<redacted>" in tube.reason


def test_retrying_a_download_uses_the_login_saved_since_it_failed(
    site: Site, alice: Account
) -> None:
    failed = _failed(site, _added(site, alice, "BVSignedIn"))
    site.linked.save(alice, "bilibili", COOKIES)

    retried = site.jobs.retry(alice, failed.job.id)

    site.wait_for(retried.id, JobState.SUCCEEDED)


def test_a_job_whose_account_is_gone_borrows_no_login(site: Site, alice: Account) -> None:
    added = _added(site, alice, "BV1Xx41117Tz")
    _finished(site, added)
    site.linked.save(alice, "bilibili", COOKIES)
    request = DownloadSource(
        site="bilibili",
        video="BV1Xx41117Tz",
        part=1,
        quality="best",
        extensions=DOWNLOAD_EXTENSIONS,
        max_bytes=MAX_DOWNLOAD_BYTES,
    )

    # A Job outlives the Account that asked for it, whose id a new Account may take.
    job = site.jobs.submit(
        site.download_kind, download_target(added.source_id), request, None, login_account=alice.id
    )
    site.wait_for(job.id, JobState.SUCCEEDED)

    said = _read(site.data_dir / "downloads" / f"{added.source_id}.m4a")
    assert said == "BV1Xx41117Tz/p1 quality=30280 login=none mode=none"


def test_a_download_waits_while_the_keychain_does_not_answer(
    site: Site, alice: Account, clock: FakeClock
) -> None:
    site.linked.save(alice, "bilibili", COOKIES)
    site.secrets.unavailable = True
    added = _added(site, alice, "BVSignedIn")
    waiting = site.wait_for(_job_id(added), JobState.WAITING)

    site.secrets.unavailable = False
    clock.advance(NETWORK_RETRY)

    site.wait_for(_job_id(added), JobState.SUCCEEDED)
    assert (waiting.job.failure_kind, waiting.job.attempts) == ("keychain", 0)
    assert "Keychain" in waiting.job.failure_message


def test_playing_a_track_whose_download_failed_answers_that_job_rather_than_a_new_one(
    site: Site, alice: Account
) -> None:
    added = _added(site, alice, "BVSignedIn")
    failed = _failed(site, added)

    preparing = site.playback.play(alice, added.track_id)

    assert preparing == Preparing(added.source_id, failed.job)


def test_serving_a_download_records_when_at_most_once_a_minute(
    site: Site, alice: Account, units: sessionmaker[Session], clock: FakeClock
) -> None:
    added = _added(site, alice, "BV1Xx41117Tz")
    _finished(site, added)
    first_served = clock.now

    site.playback.open_audio(added.source_id).close()
    clock.advance(timedelta(seconds=30))
    site.playback.open_audio(added.source_id).close()

    with units() as db:
        assert db.get_one(DownloadRow, added.source_id).last_served_at == first_served
    clock.advance(timedelta(minutes=1))
    site.playback.open_audio(added.source_id).close()
    with units() as db:
        assert db.get_one(DownloadRow, added.source_id).last_served_at == clock.now


def test_the_policy_starts_a_download_again_after_one_failed(site: Site, alice: Account) -> None:
    added = _added(site, alice, "BVSignedIn")
    failed = _failed(site, added)

    again = site.downloads.start_for(alice.id, added.source_id)

    assert again is not None
    assert again.id != failed.job.id


def test_the_policy_never_downloads_a_source_already_downloaded(site: Site, alice: Account) -> None:
    added = _added(site, alice, "BV1Xx41117Tz")
    _finished(site, added)

    assert site.downloads.start_for(alice.id, added.source_id) is None
