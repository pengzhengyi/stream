"""The `.info.json` files yt-dlp writes beside a download, as the tests need them."""

from pathlib import Path


def info_json_beside(audio: Path, text: str) -> Path:
    """Write `text` as the `.info.json` beside `audio` and return it.

    `Music/BV1dm4y1s7ak.m4a` gets `Music/BV1dm4y1s7ak.info.json`.
    """
    sidecar = audio.with_name(f"{audio.stem}.info.json")
    sidecar.write_text(text, encoding="utf-8")
    return sidecar


def melt_video() -> str:
    """The details of a one-song video: a title that names its artist, no chapters.

    ```json
    {
      "id": "BV1dm4y1s7ak",
      "title": "【初音ミク】メルト / ryo(supercell)【MV】",
      "description": "supercell's first single",
      "uploader": "ryo",
      "chapters": null
    }
    ```

    Read as a Track's details, the title is "メルト" and the artist "ryo(supercell)".
    """
    return """
    {
      "id": "BV1dm4y1s7ak",
      "title": "【初音ミク】メルト / ryo(supercell)【MV】",
      "description": "supercell's first single",
      "uploader": "ryo",
      "chapters": null
    }
    """


def world_is_mine_video() -> str:
    """The details of another one-song video, to replace `melt_video` after the file changes.

    ```json
    {
      "title": "【初音ミク】ワールドイズマイン / ryo(supercell)【MV】",
      "description": "from the album Supercell"
    }
    ```
    """
    return """
    {
      "title": "【初音ミク】ワールドイズマイン / ryo(supercell)【MV】",
      "description": "from the album Supercell"
    }
    """


def wordless_video() -> str:
    """The details of a video that says nothing: a blank title and description, no chapters.

    ```json
    {"id": "BV1dm4y1s7ak", "title": "  ", "description": "", "chapters": []}
    ```
    """
    return """{"id": "BV1dm4y1s7ak", "title": "  ", "description": "", "chapters": []}"""


def album_with_odd_chapters() -> str:
    """An album video whose chapters list holds three good entries among six odd ones.

    ```json
    {
      "title": "ハチ 全专《Bremen》",
      "chapters": [
        {"start_time": 0.0, "end_time": 252.0, "title": "アイネクライネ"},
        {"start_time": -5.0, "title": "Before the start"},
        {"start_time": "252", "title": "Time as text"},
        {"start_time": 252.4, "title": "ゴーゴー幽霊船"},
        {"start_time": NaN, "title": "Not a number"},
        {"start_time": 3723, "title": 7},
        {"title": "No start"},
        "Last",
        {"start_time": 3723.0, "title": "Last"}
      ]
    }
    ```

    `NaN` is not JSON, but Python's parser reads it, so the reading must refuse it.
    Only the entries with a start of 0 or later and a text title are kept, at 0 ms,
    252,400 ms, and 3,723,000 ms.
    """
    return """
    {
      "title": "ハチ 全专《Bremen》",
      "chapters": [
        {"start_time": 0.0, "end_time": 252.0, "title": "アイネクライネ"},
        {"start_time": -5.0, "title": "Before the start"},
        {"start_time": "252", "title": "Time as text"},
        {"start_time": 252.4, "title": "ゴーゴー幽霊船"},
        {"start_time": NaN, "title": "Not a number"},
        {"start_time": 3723, "title": 7},
        {"title": "No start"},
        "Last",
        {"start_time": 3723.0, "title": "Last"}
      ]
    }
    """
