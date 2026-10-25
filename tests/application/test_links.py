"""Looking a link up and adding its parts, through the test plugin `tube`; see its table."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application.accounts import AccountService
from medleyplay.application.links import PartChoice
from medleyplay.domain.accounts import Account
from medleyplay.domain.errors import InvalidInputError, PluginCallError
from medleyplay.persistence.schema import SourceRow, TrackRow
from tests.support.factories import NewAccountFactory
from tests.support.fakes import FakeClock, MemorySecrets
from tests.support.sites import Site, running_site

NIGHT_DRIVE = "https://www.bilibili.com/video/BV1Xx41117Tz"
MIXTAPE = "https://www.bilibili.com/video/BV17x411w7KC"


@pytest.fixture
def alice(accounts: AccountService) -> Account:
    return accounts.create_first_admin(NewAccountFactory.admin()).account


@pytest.fixture
def site(
    units: sessionmaker[Session], clock: FakeClock, tmp_path: Path, secrets: MemorySecrets
) -> Iterator[Site]:
    with running_site(units, clock, tmp_path / "data", secrets) as running:
        yield running


def _night_drive(title: str = "Night Drive") -> list[PartChoice]:
    return [PartChoice(1, title, "Blue Room")]


def test_a_lookup_answers_the_videos_details_parts_and_qualities(
    site: Site, alice: Account
) -> None:
    lookup = site.links.lookup(alice, NIGHT_DRIVE)

    assert (lookup.kind, lookup.video, lookup.title, lookup.uploader) == (
        "bilibili",
        "BV1Xx41117Tz",
        "【MV】Night Drive",
        "Blue Room",
    )
    assert [(p.part, p.title, p.duration_ms, p.track_id) for p in lookup.parts] == [
        (1, "Night Drive", 1000, None)
    ]
    assert [q.id for q in lookup.qualities] == ["30280", "30232", "30216"]


def test_a_short_link_looks_up_the_video_it_leads_to(site: Site, alice: Account) -> None:
    assert site.links.lookup(alice, "https://b23.tv/night").video == "BV1Xx41117Tz"


@pytest.mark.parametrize(
    "link",
    [
        "https://evil.example/video/BV1Xx41117Tz",
        "https://b23.tv/away",
        "https://b23.tv/liar",
        "https://www.bilibili.com/",
    ],
    ids=["another site", "a short link off the site", "a plugin naming another site", "no video"],
)
def test_a_link_that_is_not_a_bilibili_video_is_refused(
    site: Site, alice: Account, link: str
) -> None:
    with pytest.raises(InvalidInputError):
        site.links.lookup(alice, link)


@pytest.mark.parametrize(("video", "why"), [("BVgone", "removed"), ("BVmembers", "Members only")])
def test_a_video_that_cant_be_added_is_refused_saying_why(
    site: Site, alice: Account, video: str, why: str
) -> None:
    with pytest.raises(InvalidInputError, match=why):
        site.links.lookup(alice, f"https://www.bilibili.com/video/{video}")


def test_a_site_that_cant_be_reached_is_a_network_failure(site: Site, alice: Account) -> None:
    with pytest.raises(PluginCallError) as failed:
        site.links.lookup(alice, "https://www.bilibili.com/video/BVdown")

    assert failed.value.kind == "network"


def test_adding_makes_a_track_per_part_and_starts_each_download(
    site: Site, alice: Account, units: sessionmaker[Session]
) -> None:
    added = site.links.add(
        alice,
        MIXTAPE,
        "30232",
        [PartChoice(1, "Side A", "Blue Room"), PartChoice(3, "Side C", "")],
    )

    with units() as db:
        tracks = {row.id: (row.title, row.artist) for row in db.scalars(select(TrackRow))}
        sources = {row.id: (row.locator, row.details) for row in db.scalars(select(SourceRow))}
    assert [tracks[each.track_id] for each in added] == [("Side A", "Blue Room"), ("Side C", "")]
    assert [sources[each.source_id] for each in added] == [
        ("BV17x411w7KC/p1", {"quality": "30232"}),
        ("BV17x411w7KC/p3", {"quality": "30232"}),
    ]
    assert [each.job.target if each.job else None for each in added] == [
        f"source:{added[0].source_id}",
        f"source:{added[1].source_id}",
    ]


def test_adding_again_returns_the_same_tracks_and_jobs(site: Site, alice: Account) -> None:
    first = site.links.add(alice, NIGHT_DRIVE, "best", _night_drive())

    again = site.links.add(alice, "https://b23.tv/night", "30216", _night_drive("Other"))

    assert [(a.track_id, a.source_id) for a in again] == [(f.track_id, f.source_id) for f in first]
    assert again[0].job is not None
    assert first[0].job is not None
    assert again[0].job.id == first[0].job.id


def test_a_lookup_shows_a_part_already_added(site: Site, alice: Account) -> None:
    added = site.links.add(alice, NIGHT_DRIVE, "best", _night_drive())

    lookup = site.links.lookup(alice, NIGHT_DRIVE)

    assert lookup.parts[0].track_id == added[0].track_id


@pytest.mark.parametrize(
    ("quality", "parts"),
    [
        ("best", [PartChoice(4, "Side D", "")]),
        ("99999", [PartChoice(1, "Side A", "")]),
        ("best", [PartChoice(1, "Side A", ""), PartChoice(1, "Again", "")]),
        ("best", []),
        ("best", [PartChoice(1, "  ", "")]),
        ("best", [PartChoice(1, "x" * 513, "")]),
    ],
    ids=["no such part", "no such quality", "a part twice", "no parts", "no title", "long title"],
)
def test_a_choice_the_video_does_not_offer_is_refused_and_adds_nothing(
    site: Site,
    alice: Account,
    units: sessionmaker[Session],
    quality: str,
    parts: list[PartChoice],
) -> None:
    with pytest.raises(InvalidInputError):
        site.links.add(alice, MIXTAPE, quality, parts)

    with units() as db:
        assert db.scalars(select(TrackRow)).all() == []
