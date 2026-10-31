"""The playback API: asking to play a Track, and its audio served with Range, as browsers ask."""

import dataclasses
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from medleyplay.domain.jobs import JobId, JobState
from medleyplay.web.app import create_app
from medleyplay.web.deps import Services
from tests.conftest import TEST_HOST
from tests.support.api import set_up_as_alice
from tests.support.audio import Song, folder_of, wav_bytes, zip_of
from tests.support.fakes import FakeClock
from tests.support.libraries import Libraries, running_libraries

INTRO = wav_bytes(Song("Intro"))


@pytest.fixture
def running(units: sessionmaker[Session], clock: FakeClock, tmp_path: Path) -> Iterator[Libraries]:
    with running_libraries(units, clock, tmp_path / "data") as libraries:
        yield libraries


@pytest.fixture
def player(running: Libraries, services: Services) -> Iterator[TestClient]:
    services = dataclasses.replace(
        services,
        catalog=running.catalog,
        plugins=running.plugins,
        jobs=running.jobs,
        libraries=running.service,
        playback=running.playback,
    )
    with TestClient(
        create_app(services, allowed_hosts=[TEST_HOST]), base_url=f"http://{TEST_HOST}"
    ) as client:
        yield client


def _register(client: TestClient, running: Libraries, kind: str, root: Path) -> dict[str, int]:
    """Register and scan a Library as Alice; return each Track's id by its title."""
    response = client.post(
        "/api/libraries", json={"name": "Music", "kind": kind, "path": str(root)}
    )
    running.wait_for(JobId(response.json()["scan"]["id"]), JobState.SUCCEEDED)
    return {track["title"]: track["id"] for track in client.get("/api/tracks").json()}


@pytest.fixture
def intro_url(player: TestClient, running: Libraries, tmp_path: Path) -> str:
    """The audio URL of "Intro", a WAV file in a folder Library."""
    set_up_as_alice(player)
    tracks = _register(
        player, running, "folder", folder_of(tmp_path / "M", {"i.wav": Song("Intro")})
    )
    answer = player.post(f"/api/tracks/{tracks['Intro']}/playback").json()
    assert answer["state"] == "ready", answer
    url: str = answer["audio_url"]
    return url


def test_asking_to_play_a_ready_track_answers_its_audio_url_and_type(
    player: TestClient, running: Libraries, tmp_path: Path
) -> None:
    set_up_as_alice(player)
    tracks = _register(
        player, running, "folder", folder_of(tmp_path / "M", {"i.wav": Song("Intro")})
    )

    answer = player.post(f"/api/tracks/{tracks['Intro']}/playback").json()

    assert answer == {
        "state": "ready",
        "source_id": answer["source_id"],
        "audio_url": f"/api/sources/{answer['source_id']}/audio",
        "media_type": "audio/wav",
        "start_ms": None,
        "end_ms": None,
    }


def test_a_song_answers_its_album_files_audio_and_its_stretch(
    player: TestClient, running: Libraries, tmp_path: Path
) -> None:
    set_up_as_alice(player)
    tracks = _register(
        player,
        running,
        "folder",
        folder_of(tmp_path / "M", {"Bremen.wav": Song("Bremen", seconds=5.0)}),
    )
    rows = [
        {"start_ms": 0, "title": "アイネクライネ"},
        {"start_ms": 2_000, "title": "Last"},
    ]
    split = player.put(f"/api/tracks/{tracks['Bremen']}/songs", json={"rows": rows}).json()

    answer = player.post(f"/api/tracks/{split['songs'][1]['track_id']}/playback").json()
    whole = player.post(f"/api/tracks/{tracks['Bremen']}/playback").json()

    assert (answer["audio_url"], answer["start_ms"], answer["end_ms"]) == (
        whole["audio_url"],
        2_000,
        5_000,
    )


def test_the_whole_file_is_served_with_its_headers(player: TestClient, intro_url: str) -> None:
    response = player.get(intro_url)

    assert response.status_code == 200
    assert response.content == INTRO
    assert response.headers["content-type"] == "audio/wav"
    assert response.headers["content-length"] == str(len(INTRO))
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["cache-control"] == "private, no-cache"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["etag"].startswith('"')


@pytest.mark.parametrize(
    ("header", "start", "stop"),
    [
        ("bytes=0-1", 0, 2),
        ("bytes=10-", 10, len(INTRO)),
        ("bytes=-8", len(INTRO) - 8, len(INTRO)),
        ("bytes=4-7, 0-1", 4, 8),
    ],
)
def test_a_range_is_served_as_partial_content(
    player: TestClient, intro_url: str, header: str, start: int, stop: int
) -> None:
    response = player.get(intro_url, headers={"Range": header})

    assert response.status_code == 206
    assert response.content == INTRO[start:stop]
    assert response.headers["content-range"] == f"bytes {start}-{stop - 1}/{len(INTRO)}"
    assert response.headers["content-length"] == str(stop - start)


def test_a_range_past_the_end_answers_416(player: TestClient, intro_url: str) -> None:
    response = player.get(intro_url, headers={"Range": f"bytes={len(INTRO)}-"})

    assert response.status_code == 416
    assert response.headers["content-range"] == f"bytes */{len(INTRO)}"


def test_a_malformed_range_serves_the_whole_file(player: TestClient, intro_url: str) -> None:
    response = player.get(intro_url, headers={"Range": "bytes=9-2"})

    assert (response.status_code, response.content) == (200, INTRO)


def test_head_answers_the_headers_alone(player: TestClient, intro_url: str) -> None:
    response = player.head(intro_url, headers={"Range": "bytes=0-1"})

    assert response.status_code == 206
    assert response.content == b""
    assert response.headers["content-length"] == "2"


def test_if_range_with_the_current_etag_serves_the_range(
    player: TestClient, intro_url: str
) -> None:
    etag = player.head(intro_url).headers["etag"]

    response = player.get(intro_url, headers={"Range": "bytes=0-1", "If-Range": etag})

    assert (response.status_code, response.content) == (206, INTRO[:2])


def test_if_range_with_an_old_etag_serves_the_whole_file(
    player: TestClient, intro_url: str
) -> None:
    response = player.get(intro_url, headers={"Range": "bytes=0-1", "If-Range": '"old"'})

    assert (response.status_code, response.content) == (200, INTRO)


def test_if_none_match_with_the_current_etag_answers_304(
    player: TestClient, intro_url: str
) -> None:
    etag = player.head(intro_url).headers["etag"]

    response = player.get(intro_url, headers={"If-None-Match": f'W/"other", {etag}'})

    assert (response.status_code, response.content) == (304, b"")
    assert response.headers["etag"] == etag


def test_a_stored_zip_member_is_served_as_audio_not_as_a_zip(
    player: TestClient, running: Libraries, tmp_path: Path
) -> None:
    set_up_as_alice(player)
    archive = zip_of(tmp_path / "Old.zip", {"x/stored.wav": Song("Stored")})
    tracks = _register(player, running, "zip", archive)
    answer = player.post(f"/api/tracks/{tracks['Stored']}/playback").json()

    response = player.get(answer["audio_url"], headers={"Range": "bytes=0-3"})

    assert response.headers["content-type"] == "audio/wav"
    assert response.content == b"RIFF"


def test_a_compressed_member_answers_preparing_then_plays(
    player: TestClient, running: Libraries, tmp_path: Path
) -> None:
    set_up_as_alice(player)
    archive = zip_of(
        tmp_path / "Old.zip", {"x/d.wav": Song("Deflated")}, compressed=frozenset({"x/d.wav"})
    )
    tracks = _register(player, running, "zip", archive)

    first = player.post(f"/api/tracks/{tracks['Deflated']}/playback").json()
    early = player.get(f"/api/sources/{first['source_id']}/audio")
    running.wait_for(JobId(first["job_id"]), JobState.SUCCEEDED)
    ready = player.post(f"/api/tracks/{tracks['Deflated']}/playback").json()

    assert first["state"] == "preparing"
    assert early.status_code == 409
    assert player.get(ready["audio_url"]).content == wav_bytes(Song("Deflated"))


def test_a_track_whose_file_is_gone_answers_unplayable_and_its_audio_404(
    player: TestClient, running: Libraries, tmp_path: Path
) -> None:
    set_up_as_alice(player)
    root = folder_of(tmp_path / "M", {"i.wav": Song("Intro")})
    tracks = _register(player, running, "folder", root)
    source_id = player.post(f"/api/tracks/{tracks['Intro']}/playback").json()["source_id"]
    (root / "i.wav").unlink()

    answer = player.post(f"/api/tracks/{tracks['Intro']}/playback").json()

    assert answer == {"state": "unplayable", "availability": "missing"}
    assert player.get(f"/api/sources/{source_id}/audio").status_code == 404


def test_audio_needs_a_signed_in_browser(player: TestClient, intro_url: str) -> None:
    player.delete("/api/session")

    assert player.get(intro_url).status_code == 401
