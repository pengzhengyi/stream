"""Downloading a Bilibili Source in a real Job, through the test plugin `tube`, and playing it."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application.accounts import AccountService
from medleyplay.application.links import Added, PartChoice
from medleyplay.application.playback import Ready, Unplayable
from medleyplay.domain.accounts import Account
from medleyplay.domain.catalog import Availability, SourceState
from medleyplay.domain.errors import NotFoundError
from medleyplay.domain.jobs import JobState, JobView
from medleyplay.domain.linked_accounts import LinkState
from medleyplay.persistence.schema import DownloadRow, SourceRow
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
    assert not (site.data_dir / "jobs" / str(view.job.id)).exists()


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
