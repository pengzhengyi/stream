"""Audio files the tests make: small WAV files with tags, in folders and zip archives."""

import io
import struct
import wave
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

RATE = 8000


@dataclass(frozen=True)
class Song:
    """What a test WAV file says about its music, and how long it is."""

    title: str = "Intro"
    artist: str = "The Band"
    album: str = "Blue"
    seconds: float = 1.0


def wav_bytes(song: Song) -> bytes:
    """Return a silent mono WAV file whose RIFF `INFO` chunk carries the song's tags."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(RATE)
        audio.writeframes(b"\0\0" * int(RATE * song.seconds))
    data = bytearray(buffer.getvalue())
    info = b"INFO"
    for key, value in (("INAM", song.title), ("IART", song.artist), ("IPRD", song.album)):
        text = value.encode() + b"\0"
        info += key.encode() + struct.pack("<I", len(text)) + text + (b"\0" * (len(text) % 2))
    data += b"LIST" + struct.pack("<I", len(info)) + info
    struct.pack_into("<I", data, 4, len(data) - 8)
    return bytes(data)


def folder_of(root: Path, songs: Mapping[str, Song]) -> Path:
    """Write each song at its path under `root`, such as `Blue/01 Intro.wav`; return `root`.

    A path with another extension gets the song's WAV bytes all the same.
    """
    for path, song in songs.items():
        file = root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(wav_bytes(song))
    return root


def zip_of(
    archive: Path, songs: Mapping[str, Song], *, compressed: frozenset[str] = frozenset()
) -> Path:
    """Write a zip archive holding each song at its path; return the archive.

    Members in `compressed` are deflated; the rest are stored uncompressed.
    """
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w") as zip_file:
        for path, song in songs.items():
            method = zipfile.ZIP_DEFLATED if path in compressed else zipfile.ZIP_STORED
            zip_file.writestr(zipfile.ZipInfo(path), wav_bytes(song), compress_type=method)
    return archive


def mark_encrypted(archive: Path, member: str) -> None:
    """Set the encrypted flag of `member` in the archive's central directory.

    `zipfile` can't write encrypted members, so this makes one that only claims to be.
    """
    data = bytearray(archive.read_bytes())
    signature = b"PK\x01\x02"
    position = data.find(signature)
    while position != -1:
        name_length = struct.unpack_from("<H", data, position + 28)[0]
        name = bytes(data[position + 46 : position + 46 + name_length]).decode()
        if name == member:
            flags = struct.unpack_from("<H", data, position + 8)[0]
            struct.pack_into("<H", data, position + 8, flags | 0x1)
        position = data.find(signature, position + 1)
    archive.write_bytes(bytes(data))
