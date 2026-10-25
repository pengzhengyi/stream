"""Serving a slice of an open file as audio, with Range, `If-Range`, and `HEAD`.

Starlette's `FileResponse` serves only whole files; a stored zip member is a
slice of its archive, so the core serves every file through this response.
"""

import os
from typing import Final, override

import anyio.to_thread
from fastapi import Request, Response, status
from starlette.types import Receive, Scope, Send

from medleyplay.application.playback import AudioFile
from medleyplay.web.ranges import UNSATISFIABLE, requested_range

CHUNK: Final = 256 * 1024


def audio_response(request: Request, audio: AudioFile) -> Response:
    """Return the response serving `audio` for `request`; the response closes `audio`."""
    etag = f'"{audio.version}"'
    headers = {
        "accept-ranges": "bytes",
        "etag": etag,
        "cache-control": "private, no-cache",
        "x-content-type-options": "nosniff",
    }
    if _matches(request.headers.get("if-none-match"), etag):
        audio.close()
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    if_range = request.headers.get("if-range")
    honored = if_range is None or if_range == etag
    found = requested_range(request.headers.get("range") if honored else None, audio.length)
    if found is UNSATISFIABLE:
        audio.close()
        return Response(
            status_code=status.HTTP_416_RANGE_NOT_SATISFIABLE,
            headers={**headers, "content-range": f"bytes */{audio.length}"},
        )
    start, stop = (0, audio.length) if found is None else (found.start, found.stop)
    if found is not None:
        headers["content-range"] = f"bytes {start}-{stop - 1}/{audio.length}"
    return _SliceResponse(
        audio,
        start,
        stop,
        status.HTTP_200_OK if found is None else status.HTTP_206_PARTIAL_CONTENT,
        headers,
        send_body=request.method != "HEAD",
    )


def _matches(if_none_match: str | None, etag: str) -> bool:
    # A weak comparison, as RFC 9110 asks for `If-None-Match`.
    if if_none_match is None:
        return False
    tags = {tag.strip().removeprefix("W/") for tag in if_none_match.split(",")}
    return "*" in tags or etag in tags


class _SliceResponse(Response):
    def __init__(
        self,
        audio: AudioFile,
        start: int,
        stop: int,
        status_code: int,
        headers: dict[str, str],
        *,
        send_body: bool,
    ) -> None:
        super().__init__(
            status_code=status_code,
            headers={**headers, "content-length": str(stop - start)},
            media_type=audio.media_type,
        )
        self._audio = audio
        self._start = start
        self._stop = stop
        self._send_body = send_body

    @override
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await send(
                {
                    "type": "http.response.start",
                    "status": self.status_code,
                    "headers": self.raw_headers,
                }
            )
            position = self._start
            while self._send_body and position < self._stop:
                chunk = await anyio.to_thread.run_sync(self._read, position)
                if not chunk:
                    break  # The file shrank; the server ends the short response.
                position += len(chunk)
                more = position < self._stop
                await send({"type": "http.response.body", "body": chunk, "more_body": more})
            if not self._send_body or position == self._start:
                await send({"type": "http.response.body", "body": b"", "more_body": False})
        finally:
            self._audio.close()

    def _read(self, position: int) -> bytes:
        size = min(CHUNK, self._stop - position)
        return os.pread(self._audio.descriptor, size, self._audio.offset + position)
