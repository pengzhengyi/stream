"""Start a medleyplay server for the end-to-end tests, over a fresh data folder and music.

The music is silent WAV files named for their Tracks: `Alpha`, `Bravo`, and
`Charlie` in a folder, and `Delta` compressed in a zip archive, so it must be
prepared before it plays. Run from `web/` with `uv run --project .. python e2e/serve.py`.
"""

import os
import shutil
import wave
import zipfile
from pathlib import Path

PORT = "4174"
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent / ".cache" / "e2e"
RATE = 8000


def silence(path: Path, seconds: int) -> None:
    """Write `seconds` of 8 kHz, 8-bit, mono silence to `path`."""
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(1)
        audio.setframerate(RATE)
        audio.writeframes(b"\x80" * RATE * seconds)


def main() -> None:
    """Make the music and the data folder, then become the server."""
    shutil.rmtree(ROOT, ignore_errors=True)
    music = ROOT / "Music"
    music.mkdir(parents=True)
    silence(music / "Alpha.wav", 60)
    silence(music / "Bravo.wav", 60)
    silence(music / "Charlie.wav", 2)
    silence(ROOT / "Delta.wav", 60)
    with zipfile.ZipFile(ROOT / "Old Mixes.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(ROOT / "Delta.wav", "Delta.wav")
    (ROOT / "Delta.wav").unlink()
    env = {**os.environ, "MEDLEYPLAY_DATA_DIR": str(ROOT / "data")}
    command = ["medleyplay", "serve", "--host", "127.0.0.1", "--port", PORT]
    os.execvpe(command[0], command, env)  # noqa: S606 -- the test server, by a fixed command


if __name__ == "__main__":
    main()
