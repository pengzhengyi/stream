"""Reading a yt-dlp `.info.json`: the words a video says, from a file nobody vouches for."""

import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from medleyplay.programs.info_json import (
    MAX_CHAPTERS,
    MAX_DESCRIPTION,
    MAX_TITLE,
    InfoChapter,
    InfoJsonError,
    InfoText,
    parse_info_json,
)


def test_the_title_description_and_chapters_are_read() -> None:
    text = parse_info_json(
        """
        {
          "id": "BV1dm4y1s7ak",
          "title": "ハチ 全专《Bremen》",
          "description": "00:00 アイネクライネ",
          "uploader": "ハチ",
          "chapters": [{"start_time": 0.0, "end_time": 252.0, "title": "アイネクライネ"}]
        }
        """.encode()
    )

    assert text == InfoText(
        title="ハチ 全专《Bremen》",
        description="00:00 アイネクライネ",
        chapters=(InfoChapter(start_ms=0, title="アイネクライネ"),),
    )


@pytest.mark.parametrize(
    "document",
    [
        pytest.param("{}", id="an empty object"),
        pytest.param('{"title": 7, "description": ["a"], "chapters": "none"}', id="odd types"),
        pytest.param('{"title": null, "description": null, "chapters": null}', id="nulls"),
    ],
)
def test_a_title_description_or_chapters_of_the_wrong_kind_is_empty(document: str) -> None:
    assert parse_info_json(document.encode()) == InfoText()


def test_a_long_title_and_description_are_cut_to_the_limits_of_a_paste() -> None:
    document = json.dumps({"title": "t" * 1_500, "description": "d" * 25_000})

    text = parse_info_json(document.encode())

    assert (len(text.title), len(text.description)) == (1_000, 20_000)
    assert (MAX_TITLE, MAX_DESCRIPTION) == (1_000, 20_000)


@pytest.mark.parametrize(
    ("start_time", "kept"),
    [
        pytest.param("1.2346", 1_235, id="rounded to the millisecond"),
        pytest.param("0", 0, id="zero"),
        pytest.param("-0.001", None, id="negative"),
        pytest.param("true", None, id="a boolean"),
        pytest.param('"1"', None, id="text"),
        pytest.param("null", None, id="null"),
        pytest.param("NaN", None, id="NaN"),
        pytest.param("Infinity", None, id="infinity"),
        pytest.param("1e308", None, id="too large to count in milliseconds"),
        pytest.param("1" + "0" * 400, None, id="a whole number too large for a float"),
    ],
)
def test_a_chapter_is_kept_only_for_a_finite_start_of_zero_or_later(
    start_time: str, kept: int | None
) -> None:
    text = parse_info_json(
        f'{{"chapters": [{{"start_time": {start_time}, "title": "A"}}]}}'.encode()
    )

    assert text.chapters == (() if kept is None else (InfoChapter(start_ms=kept, title="A"),))


@pytest.mark.parametrize(
    ("document", "problem"),
    [
        pytest.param(b"", "isn't valid JSON", id="empty"),
        pytest.param(b'{"title": ', "isn't valid JSON", id="cut short"),
        pytest.param(b'{"title": "\xff"}', "isn't valid JSON", id="not UTF-8"),
        pytest.param(b"[" * 100_000, "isn't valid JSON", id="nested too deep"),
        pytest.param(b"[]", "isn't a JSON object", id="a list"),
        pytest.param(b"null", "isn't a JSON object", id="null"),
    ],
)
def test_a_document_that_is_not_a_json_object_is_refused_with_the_reason(
    document: bytes, problem: str
) -> None:
    with pytest.raises(InfoJsonError, match=problem):
        parse_info_json(document)


_JSON = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats() | st.text(),
    lambda inner: (
        st.lists(inner, max_size=4) | st.dictionaries(st.text(max_size=8), inner, max_size=4)
    ),
    max_leaves=12,
)
_FIELDS = st.fixed_dictionaries(
    {"title": _JSON, "description": _JSON, "chapters": st.lists(_JSON, max_size=6) | _JSON},
)


@given(_FIELDS)
def test_any_object_reads_to_text_within_the_limits_and_never_raises(document: object) -> None:
    text = parse_info_json(json.dumps(document).encode())

    assert len(text.title) <= MAX_TITLE
    assert len(text.description) <= MAX_DESCRIPTION
    assert all(chapter.start_ms >= 0 for chapter in text.chapters)


def test_text_that_isnt_valid_unicode_keeps_a_replacement_character() -> None:
    text = parse_info_json(
        rb"""
        {
          "title": "Melt \ud800",
          "chapters": [
            {"start_time": 0, "title": "Intro \udc00"},
            {"start_time": 60, "title": "Night Drive"}
          ]
        }
        """
    )

    assert text.title == "Melt �"
    assert text.chapters[0].title == "Intro �"
    assert "Melt" in text.model_dump_json()


def test_a_long_chapter_title_is_cut_to_the_limit_of_a_title() -> None:
    document = {"chapters": [{"start_time": 0, "title": "x" * (MAX_TITLE + 40)}]}

    text = parse_info_json(json.dumps(document).encode())

    assert text.chapters == (InfoChapter(start_ms=0, title="x" * MAX_TITLE),)


def test_chapters_past_the_limit_are_left_out() -> None:
    document = {
        "chapters": [
            {"start_time": seconds, "title": "Song"} for seconds in range(MAX_CHAPTERS + 5)
        ]
    }

    text = parse_info_json(json.dumps(document).encode())

    assert len(text.chapters) == MAX_CHAPTERS


def test_a_chapter_starting_more_than_a_week_in_is_left_out() -> None:
    document = {
        "chapters": [
            {"start_time": 0, "title": "Intro"},
            {"start_time": 8 * 24 * 3600, "title": "Much later"},
            {"start_time": 1e300, "title": "Never"},
        ]
    }

    text = parse_info_json(json.dumps(document).encode())

    assert text.chapters == (InfoChapter(start_ms=0, title="Intro"),)
