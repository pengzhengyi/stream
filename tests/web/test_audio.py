"""The audio response, for what a browser can't arrange: a file that shrinks as it is served."""

import os
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from medleyplay.application.playback import AudioFile
from medleyplay.web.audio import audio_response


def test_a_file_that_shrank_since_it_was_opened_ends_the_body_early(tmp_path: Path) -> None:
    song = tmp_path / "a.wav"
    song.write_bytes(b"RIFF....WAVE")
    app = FastAPI()

    @app.get("/audio")
    def audio(request: Request) -> Response:
        # The slice was located while the file was 20 bytes long.
        return audio_response(request, AudioFile(os.open(song, os.O_RDONLY), 0, 20, "audio/wav"))

    response = TestClient(app).get("/audio")

    assert response.content == b"RIFF....WAVE"
