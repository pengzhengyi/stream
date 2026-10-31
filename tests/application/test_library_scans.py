"""Applying a completed scan to the catalog: new, changed, moved, missing, and offline."""

from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.application.catalog import CatalogService
from medleyplay.application.details import DetailsService, video_text_of
from medleyplay.application.libraries import apply_scan
from medleyplay.domain.accounts import AccountId
from medleyplay.domain.catalog import Availability, TrackId
from medleyplay.domain.details import Field, Origin, Shown
from medleyplay.domain.libraries import LibraryId, LibraryState
from medleyplay.domain.video_text import Chapter, VideoText
from medleyplay.persistence.schema import (
    LibraryRow,
    SourceRow,
    TrackRow,
    TrackValueRow,
    VideoTextRow,
)
from medleyplay.plugin_api import Tags
from medleyplay.programs.info_json import InfoChapter
from medleyplay.programs.scan_library import LibraryScan, ScannedFile
from tests.support.factories import InfoJsonFactory, ScannedFileFactory
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


def test_a_file_whose_title_tag_is_blank_is_named_after_its_file(
    units: sessionmaker[Session], clock: FakeClock, library: LibraryId
) -> None:
    _scan(units, clock, library, ScannedFileFactory.song("Blue/07 Hidden.wav", "  "))

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


def test_a_rescan_leaves_the_values_of_an_unchanged_file_as_they_were_recorded(
    units: sessionmaker[Session], clock: FakeClock, library: LibraryId
) -> None:
    _scan(units, clock, library, ScannedFileFactory.song("a.wav", "A"))
    first = _recorded(units)
    clock.advance(timedelta(days=1))

    _scan(units, clock, library, ScannedFileFactory.unchanged("a.wav"))

    assert _recorded(units) == first


def _recorded(units: sessionmaker[Session]) -> list[tuple[str, str, datetime]]:
    """Return each value's field, origin, and when it was recorded."""
    with units() as db:
        rows = db.scalars(select(TrackValueRow).order_by(TrackValueRow.field))
        return [(row.field, row.origin, row.recorded_at) for row in rows]


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


# --- The video's text, read from the `.info.json` beside a file --------------

MELT = "【初音ミク】メルト / ryo(supercell)【MV】"
WORLD_IS_MINE = "【初音ミク】ワールドイズマイン / ryo(supercell)【MV】"
VIDEO = "BV1dm4y1s7ak.m4a"
BROKEN = "isn't valid JSON (JSONDecodeError)"


def _shown(units: sessionmaker[Session], clock: FakeClock, path: str) -> dict[Field, Shown]:
    """Return the details the file's Track shows."""
    track_id = TrackId(_catalog(units)[path].track_id)
    return DetailsService(units, clock).details(track_id).shown


def _video_text(units: sessionmaker[Session], path: str) -> VideoText | None:
    with units() as db:
        return video_text_of(db, TrackId(_catalog(units)[path].track_id))


def _came_from(units: sessionmaker[Session]) -> list[str]:
    with units() as db:
        return [row.came_from for row in db.scalars(select(VideoTextRow))]


def _source_details(units: sessionmaker[Session]) -> dict[str, object]:
    with units() as db:
        return dict(db.scalars(select(SourceRow)).one().details or {})


def _paste(units: sessionmaker[Session], clock: FakeClock, path: str, text: VideoText) -> None:
    track_id = TrackId(_catalog(units)[path].track_id)
    DetailsService(units, clock).read_video_text(track_id, text)


@pytest.fixture
def melt_read(units: sessionmaker[Session], clock: FakeClock, library: LibraryId) -> None:
    """A library whose video was scanned with `MELT` read from its sidecar."""
    sidecar = InfoJsonFactory.read(MELT)
    _scan(units, clock, library, ScannedFileFactory.untagged(VIDEO, info_json=sidecar))


def test_a_sidecar_read_gives_the_track_the_videos_title_and_artist(
    units: sessionmaker[Session], clock: FakeClock, library: LibraryId
) -> None:
    sidecar = InfoJsonFactory.read(MELT, "supercell's first single")

    _scan(units, clock, library, ScannedFileFactory.untagged(VIDEO, info_json=sidecar))

    assert _shown(units, clock, VIDEO) == {
        Field.TITLE: Shown("メルト", Origin.VIDEO),
        Field.ARTIST: Shown("ryo(supercell)", Origin.VIDEO),
    }
    assert _video_text(units, VIDEO) == VideoText(MELT, "supercell's first single")
    assert _came_from(units) == ["file"]


def test_a_sidecars_chapters_are_kept_with_the_text(
    units: sessionmaker[Session], clock: FakeClock, library: LibraryId
) -> None:
    chapters = (
        InfoChapter(start_ms=0, title="アイネクライネ"),
        InfoChapter(start_ms=252_400, title="Last"),
    )
    sidecar = InfoJsonFactory.read("ハチ 全专《Bremen》", chapters=chapters)

    _scan(units, clock, library, ScannedFileFactory.untagged(VIDEO, info_json=sidecar))

    assert _video_text(units, VIDEO) == VideoText(
        "ハチ 全专《Bremen》", chapters=(Chapter(0, "アイネクライネ"), Chapter(252_400, "Last"))
    )


def test_the_stamp_of_a_sidecar_read_is_kept_with_the_source(
    units: sessionmaker[Session], clock: FakeClock, library: LibraryId
) -> None:
    sidecar = InfoJsonFactory.read(MELT, modified_ns=7)

    _scan(units, clock, library, ScannedFileFactory.untagged(VIDEO, info_json=sidecar))

    details = _source_details(units)
    assert details["info_json"] == {"size": 200, "modified_ns": 7}
    assert "info_json_error" not in details


@pytest.mark.usefixtures("melt_read")
def test_a_changed_sidecar_replaces_the_text_read_before(
    units: sessionmaker[Session], clock: FakeClock, library: LibraryId
) -> None:
    changed = InfoJsonFactory.read(WORLD_IS_MINE, modified_ns=2)

    _scan(units, clock, library, ScannedFileFactory.unchanged(VIDEO, info_json=changed))

    assert _shown(units, clock, VIDEO)[Field.TITLE] == Shown("ワールドイズマイン", Origin.VIDEO)
    assert _source_details(units)["info_json"] == {"size": 200, "modified_ns": 2}


@pytest.mark.usefixtures("melt_read")
def test_a_sidecar_not_read_again_leaves_the_text_and_the_stamp(
    units: sessionmaker[Session], clock: FakeClock, library: LibraryId
) -> None:
    skipped = InfoJsonFactory.unchanged()

    _scan(units, clock, library, ScannedFileFactory.unchanged(VIDEO, info_json=skipped))

    assert _video_text(units, VIDEO) == VideoText(MELT)
    assert _source_details(units)["info_json"] == {"size": 200, "modified_ns": 1}


@pytest.mark.usefixtures("melt_read")
def test_a_changed_audio_file_keeps_the_text_of_the_sidecar_beside_it(
    units: sessionmaker[Session], clock: FakeClock, library: LibraryId
) -> None:
    retagged = ScannedFileFactory.untagged(VIDEO, info_json=InfoJsonFactory.unchanged())

    _scan(units, clock, library, retagged)

    assert _video_text(units, VIDEO) == VideoText(MELT)
    assert _source_details(units)["info_json"] == {"size": 200, "modified_ns": 1}


def test_a_sidecar_with_no_words_records_nothing_but_keeps_its_stamp(
    units: sessionmaker[Session], clock: FakeClock, library: LibraryId
) -> None:
    wordless = InfoJsonFactory.wordless()

    _scan(units, clock, library, ScannedFileFactory.untagged(VIDEO, info_json=wordless))

    assert _video_text(units, VIDEO) is None
    assert _source_details(units)["info_json"] == {"size": 200, "modified_ns": 1}
    assert _shown(units, clock, VIDEO) == {Field.TITLE: Shown("BV1dm4y1s7ak", Origin.FILE_NAME)}


@pytest.mark.usefixtures("melt_read")
def test_a_removed_sidecar_takes_the_text_read_from_it_and_its_values(
    units: sessionmaker[Session], clock: FakeClock, library: LibraryId
) -> None:
    _scan(units, clock, library, ScannedFileFactory.unchanged(VIDEO))

    assert _video_text(units, VIDEO) is None
    assert _shown(units, clock, VIDEO) == {Field.TITLE: Shown("BV1dm4y1s7ak", Origin.FILE_NAME)}
    assert "info_json" not in _source_details(units)


@pytest.mark.usefixtures("melt_read")
def test_a_removed_sidecar_leaves_the_text_the_household_pasted(
    units: sessionmaker[Session], clock: FakeClock, library: LibraryId
) -> None:
    _paste(units, clock, VIDEO, VideoText(WORLD_IS_MINE))

    _scan(units, clock, library, ScannedFileFactory.unchanged(VIDEO))

    assert _video_text(units, VIDEO) == VideoText(WORLD_IS_MINE)
    assert _shown(units, clock, VIDEO)[Field.TITLE] == Shown("ワールドイズマイン", Origin.VIDEO)
    assert "info_json" not in _source_details(units)


@pytest.mark.usefixtures("melt_read")
def test_a_paste_after_a_sidecar_read_survives_a_rescan_that_finds_the_sidecar_unchanged(
    units: sessionmaker[Session], clock: FakeClock, library: LibraryId
) -> None:
    _paste(units, clock, VIDEO, VideoText(WORLD_IS_MINE))
    skipped = InfoJsonFactory.unchanged()

    _scan(units, clock, library, ScannedFileFactory.unchanged(VIDEO, info_json=skipped))

    assert _video_text(units, VIDEO) == VideoText(WORLD_IS_MINE)
    assert _came_from(units) == ["household"]


@pytest.mark.usefixtures("melt_read")
def test_a_paste_survives_a_rescan_that_reads_the_unchanged_sidecar_again(
    units: sessionmaker[Session], clock: FakeClock, library: LibraryId
) -> None:
    _paste(units, clock, VIDEO, VideoText(WORLD_IS_MINE))
    reread = InfoJsonFactory.read(MELT)

    _scan(units, clock, library, ScannedFileFactory.untagged(VIDEO, info_json=reread))

    assert _video_text(units, VIDEO) == VideoText(WORLD_IS_MINE)
    assert _came_from(units) == ["household"]


@pytest.mark.usefixtures("melt_read")
def test_a_sidecar_that_couldnt_be_read_for_now_is_read_again_next_scan(
    units: sessionmaker[Session], clock: FakeClock, library: LibraryId
) -> None:
    late = InfoJsonFactory.unreadable_for_now(modified_ns=2)

    _scan(units, clock, library, ScannedFileFactory.unchanged(VIDEO, info_json=late))

    details = _source_details(units)
    assert details["info_json"] == {"size": 200, "modified_ns": 1}
    assert "can't be read" in str(details["info_json_error"])
    assert _video_text(units, VIDEO) == VideoText(MELT)


@pytest.mark.usefixtures("melt_read")
def test_a_changed_sidecar_replaces_a_paste(
    units: sessionmaker[Session], clock: FakeClock, library: LibraryId
) -> None:
    _paste(units, clock, VIDEO, VideoText(WORLD_IS_MINE))
    rewritten = InfoJsonFactory.read(MELT, "Rewritten", modified_ns=2)

    _scan(units, clock, library, ScannedFileFactory.unchanged(VIDEO, info_json=rewritten))

    assert _video_text(units, VIDEO) == VideoText(MELT, "Rewritten")
    assert _came_from(units) == ["file"]


@pytest.mark.usefixtures("melt_read")
def test_a_malformed_sidecar_keeps_the_earlier_text_and_notes_the_error(
    units: sessionmaker[Session], clock: FakeClock, library: LibraryId
) -> None:
    broken = InfoJsonFactory.malformed(modified_ns=2)

    _scan(units, clock, library, ScannedFileFactory.unchanged(VIDEO, info_json=broken))

    details = _source_details(units)
    assert _video_text(units, VIDEO) == VideoText(MELT)
    assert _shown(units, clock, VIDEO)[Field.TITLE] == Shown("メルト", Origin.VIDEO)
    assert details["info_json"] == {"size": 200, "modified_ns": 2}
    assert details["info_json_error"] == BROKEN


def test_a_noted_error_stays_noted_until_the_sidecar_is_read_well(
    units: sessionmaker[Session], clock: FakeClock, library: LibraryId
) -> None:
    broken = InfoJsonFactory.malformed()
    _scan(units, clock, library, ScannedFileFactory.untagged(VIDEO, info_json=broken))

    skipped = InfoJsonFactory.unchanged()
    _scan(units, clock, library, ScannedFileFactory.unchanged(VIDEO, info_json=skipped))
    still_noted = _source_details(units).get("info_json_error")
    mended = InfoJsonFactory.read(MELT, modified_ns=2)
    _scan(units, clock, library, ScannedFileFactory.unchanged(VIDEO, info_json=mended))

    assert still_noted == BROKEN
    assert "info_json_error" not in _source_details(units)
    assert _video_text(units, VIDEO) == VideoText(MELT)


def test_a_removed_sidecar_clears_the_error_noted_for_it(
    units: sessionmaker[Session], clock: FakeClock, library: LibraryId
) -> None:
    broken = InfoJsonFactory.malformed()
    _scan(units, clock, library, ScannedFileFactory.untagged(VIDEO, info_json=broken))

    _scan(units, clock, library, ScannedFileFactory.unchanged(VIDEO))

    assert _source_details(units).keys() == {"size", "modified_ns", "error", "reader"}


def test_a_moved_file_keeps_its_track_and_reads_the_sidecar_at_its_new_path(
    units: sessionmaker[Session], clock: FakeClock, library: LibraryId
) -> None:
    before = ScannedFileFactory.untagged(
        f"old/{VIDEO}", fingerprint="f1", info_json=InfoJsonFactory.read(MELT)
    )
    _scan(units, clock, library, before)
    track_id = _catalog(units)[f"old/{VIDEO}"].track_id
    other = InfoJsonFactory.read(WORLD_IS_MINE, modified_ns=2)
    after = ScannedFileFactory.untagged(f"new/{VIDEO}", fingerprint="f1", info_json=other)

    _scan(units, clock, library, after)

    assert [seen.track_id for seen in _catalog(units).values()] == [track_id]
    assert _video_text(units, f"new/{VIDEO}") == VideoText(WORLD_IS_MINE)


def test_a_moved_file_whose_sidecar_stayed_behind_loses_the_text_read_from_it(
    units: sessionmaker[Session], clock: FakeClock, library: LibraryId
) -> None:
    before = ScannedFileFactory.untagged(
        f"old/{VIDEO}", fingerprint="f1", info_json=InfoJsonFactory.read(MELT)
    )
    _scan(units, clock, library, before)

    _scan(units, clock, library, ScannedFileFactory.untagged(f"new/{VIDEO}", fingerprint="f1"))

    assert _video_text(units, f"new/{VIDEO}") is None
    assert "info_json" not in _source_details(units)
