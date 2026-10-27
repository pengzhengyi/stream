"""Applying a completed scan to the catalog: new, changed, moved, missing, and offline."""

from dataclasses import dataclass
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application.catalog import CatalogService
from medleyplay.application.details import DetailsService
from medleyplay.application.libraries import apply_scan
from medleyplay.domain.accounts import AccountId
from medleyplay.domain.catalog import Availability, TrackId
from medleyplay.domain.details import Field, Origin
from medleyplay.domain.libraries import LibraryId, LibraryState
from medleyplay.persistence.schema import LibraryRow, SourceRow, TrackRow
from medleyplay.plugin_api import Tags
from medleyplay.programs.scan_library import LibraryScan, ScannedFile
from tests.support.factories import ScannedFileFactory
from tests.support.fakes import FakeClock


@dataclass(frozen=True)
class Seen:
    """What the catalog holds for one file of the Library."""

    state: str
    title: str
    track_id: int


def _library(units: sessionmaker[Session], clock: FakeClock) -> LibraryId:
    with units.begin() as db:
        row = LibraryRow(
            name="Music",
            kind="folder",
            path="/music",
            state="online",
            message="",
            file_count=0,
            added_at=clock(),
        )
        db.add(row)
        db.flush()
        return LibraryId(row.id)


def _scan(
    units: sessionmaker[Session], clock: FakeClock, library_id: LibraryId, *files: ScannedFile
) -> None:
    with units.begin() as db:
        apply_scan(db, library_id, LibraryScan(readable=True, files=files), clock)


def _catalog(units: sessionmaker[Session]) -> dict[str, Seen]:
    with units() as db:
        rows = db.execute(
            select(SourceRow, TrackRow).join(TrackRow, SourceRow.track_id == TrackRow.id)
        )
        return {
            source.locator.partition("/")[2]: Seen(source.state, track.title, track.id)
            for source, track in rows
        }


def _library_row(units: sessionmaker[Session], library_id: LibraryId) -> LibraryRow:
    with units() as db:
        row = db.get(LibraryRow, library_id)
        assert row is not None
        return row


@pytest.fixture
def library(units: sessionmaker[Session], clock: FakeClock) -> LibraryId:
    return _library(units, clock)


def test_each_new_file_becomes_a_track_with_its_tags(
    units: sessionmaker[Session], clock: FakeClock, library: LibraryId
) -> None:
    _scan(
        units,
        clock,
        library,
        ScannedFileFactory.song("a.wav", "A"),
        ScannedFileFactory.song("b.wav", "B"),
    )

    catalog = _catalog(units)
    row = _library_row(units, library)

    assert {path: (seen.state, seen.title) for path, seen in catalog.items()} == {
        "a.wav": ("ok", "A"),
        "b.wav": ("ok", "B"),
    }
    assert (row.state, row.file_count, row.last_scanned_at) == ("online", 2, clock())


def test_a_file_without_a_title_is_named_after_its_file(
    units: sessionmaker[Session], clock: FakeClock, library: LibraryId
) -> None:
    untitled = ScannedFileFactory.song("Blue/07 Hidden.wav").model_copy(update={"tags": Tags()})

    _scan(units, clock, library, untitled)

    assert _catalog(units)["Blue/07 Hidden.wav"].title == "07 Hidden"


def test_a_changed_file_updates_its_track_and_an_unchanged_one_keeps_it(
    units: sessionmaker[Session], clock: FakeClock, library: LibraryId
) -> None:
    _scan(
        units,
        clock,
        library,
        ScannedFileFactory.song("a.wav", "A"),
        ScannedFileFactory.song("b.wav", "B"),
    )
    before = _catalog(units)

    _scan(
        units,
        clock,
        library,
        ScannedFileFactory.song("a.wav", "A, retagged"),
        ScannedFileFactory.unchanged("b.wav"),
    )
    after = _catalog(units)

    assert after["a.wav"] == Seen("ok", "A, retagged", before["a.wav"].track_id)
    assert after["b.wav"] == before["b.wav"]


def test_a_file_the_scan_did_not_find_is_missing_until_it_returns(
    units: sessionmaker[Session], clock: FakeClock, library: LibraryId
) -> None:
    _scan(units, clock, library, ScannedFileFactory.song("a.wav"), ScannedFileFactory.song("b.wav"))

    _scan(units, clock, library, ScannedFileFactory.unchanged("a.wav"))
    gone = _catalog(units)["b.wav"].state
    _scan(
        units,
        clock,
        library,
        ScannedFileFactory.unchanged("a.wav"),
        ScannedFileFactory.unchanged("b.wav"),
    )
    back = _catalog(units)["b.wav"].state

    assert (gone, back) == ("missing", "ok")


def test_a_moved_file_keeps_its_track(
    units: sessionmaker[Session], clock: FakeClock, library: LibraryId
) -> None:
    _scan(units, clock, library, ScannedFileFactory.song("old/a.wav", fingerprint="f1"))
    track_id = _catalog(units)["old/a.wav"].track_id

    _scan(units, clock, library, ScannedFileFactory.song("new/a.wav", fingerprint="f1"))
    catalog = _catalog(units)

    assert catalog == {"new/a.wav": Seen("ok", "Intro", track_id)}


def test_a_moved_file_without_a_title_is_named_after_its_new_name(
    units: sessionmaker[Session], clock: FakeClock, library: LibraryId
) -> None:
    untitled = ScannedFileFactory.song("old/BV1dm4y1s7ak.m4a", fingerprint="f1")
    _scan(units, clock, library, untitled.model_copy(update={"tags": Tags()}))

    _scan(units, clock, library, ScannedFileFactory.unchanged("new/Re-Start.m4a"))

    assert _catalog(units)["new/Re-Start.m4a"].title == "Re-Start"


def test_the_households_values_outlast_a_rescan_of_a_changed_file(
    units: sessionmaker[Session], clock: FakeClock, library: LibraryId
) -> None:
    _scan(units, clock, library, ScannedFileFactory.song("a.wav", "Intro"))
    track_id = TrackId(_catalog(units)["a.wav"].track_id)
    DetailsService(units, clock).put_household(track_id, {"title": "Night Drive"})

    _scan(units, clock, library, ScannedFileFactory.song("a.wav", "Intro (Remaster)"))

    details = DetailsService(units, clock).details(track_id)
    assert _catalog(units)["a.wav"].title == "Night Drive"
    assert details.values[Origin.FILES][Field.TITLE] == "Intro (Remaster)"


def test_a_move_matched_by_two_new_files_is_no_move(
    units: sessionmaker[Session], clock: FakeClock, library: LibraryId
) -> None:
    _scan(units, clock, library, ScannedFileFactory.song("a.wav", fingerprint="f1"))

    _scan(
        units,
        clock,
        library,
        ScannedFileFactory.song("b.wav", fingerprint="f1"),
        ScannedFileFactory.song("c.wav", fingerprint="f1"),
    )
    catalog = _catalog(units)

    assert {path: seen.state for path, seen in catalog.items()} == {
        "a.wav": "missing",
        "b.wav": "ok",
        "c.wav": "ok",
    }


def test_a_protected_file_cant_be_played(
    units: sessionmaker[Session], clock: FakeClock, library: LibraryId
) -> None:
    locked = ScannedFileFactory.song("a.m4p").model_copy(
        update={"tags": Tags(title="Locked", protected=True)}
    )

    _scan(units, clock, library, locked)

    assert _catalog(units)["a.m4p"].state == "cant_play"


def test_an_unreadable_root_marks_the_library_offline_and_no_file_missing(
    units: sessionmaker[Session], clock: FakeClock, library: LibraryId
) -> None:
    _scan(units, clock, library, ScannedFileFactory.song("a.wav"))

    with units.begin() as db:
        apply_scan(
            db, library, LibraryScan(readable=False, message="/music isn't a folder."), clock
        )
    row = _library_row(units, library)

    assert (row.state, row.message) == (LibraryState.OFFLINE, "/music isn't a folder.")
    assert _catalog(units)["a.wav"].state == "ok"


def test_a_library_that_held_files_and_now_lists_none_is_offline(
    units: sessionmaker[Session], clock: FakeClock, library: LibraryId
) -> None:
    _scan(units, clock, library, ScannedFileFactory.song("a.wav"))
    clock.advance(timedelta(days=1))

    _scan(units, clock, library)
    row = _library_row(units, library)

    assert row.state == LibraryState.OFFLINE
    assert row.last_scanned_at != clock()
    assert _catalog(units)["a.wav"].state == "ok"


def test_an_empty_library_scanned_for_the_first_time_is_online(
    units: sessionmaker[Session], clock: FakeClock, library: LibraryId
) -> None:
    _scan(units, clock, library)

    assert _library_row(units, library).state == LibraryState.ONLINE


def test_a_scan_of_a_removed_library_changes_nothing(
    units: sessionmaker[Session], clock: FakeClock
) -> None:
    _scan(units, clock, LibraryId(404), ScannedFileFactory.song("a.wav"))

    assert _catalog(units) == {}


def test_a_file_whose_tags_failed_is_listed_by_its_name_with_the_error(
    units: sessionmaker[Session], clock: FakeClock, library: LibraryId
) -> None:
    failed = ScannedFile(
        path="odd.wav", size=5, modified_ns=1, changed=True, error="ValueError: odd"
    )

    _scan(units, clock, library, failed)

    with units() as db:
        source = db.scalars(select(SourceRow)).one()
    assert (source.state, source.details["error"]) == ("ok", "ValueError: odd")
    assert _catalog(units)["odd.wav"].title == "odd"


def _availability(catalog: CatalogService) -> dict[str, Availability]:
    # Availability is the same for every Account; any id reads it.
    return {track.details.title: track.availability for track in catalog.list_tracks(AccountId(1))}


def test_tracks_of_an_offline_library_are_listed_offline(
    units: sessionmaker[Session], clock: FakeClock, library: LibraryId, catalog: CatalogService
) -> None:
    _scan(units, clock, library, ScannedFileFactory.song("a.wav", "A"))

    with units.begin() as db:
        apply_scan(db, library, LibraryScan(readable=False, message="unplugged"), clock)

    assert _availability(catalog) == {"A": Availability.OFFLINE}


def test_tracks_of_missing_and_protected_files_are_listed_as_such(
    units: sessionmaker[Session], clock: FakeClock, library: LibraryId, catalog: CatalogService
) -> None:
    protected = ScannedFileFactory.song("b.m4p").model_copy(
        update={"tags": Tags(title="B", protected=True)}
    )
    _scan(units, clock, library, ScannedFileFactory.song("a.wav", "A"), protected)

    _scan(units, clock, library, protected)

    assert _availability(catalog) == {"A": Availability.MISSING, "B": Availability.CANT_PLAY}
