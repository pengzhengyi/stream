"""Reading a video's title and description: its details, whether it is an album, its song list."""

import time
from itertools import accumulate

import pytest
from hypothesis import given
from hypothesis import strategies as st

from medleyplay.domain.details import MAX_TEXT, Field, Value, found_value
from medleyplay.domain.errors import InvalidInputError
from medleyplay.domain.video_text import (
    MAX_LINE,
    MAX_SONGS,
    Chapter,
    Song,
    VideoText,
    check_songs,
    read_song_list,
    read_video,
)

THREE_SONGS = """\
Songs:
00:00 アイネクライネ
04:12 ゴーゴー幽霊船 - ハチ
1:02:03 Last
"""
"""A description with three timestamped lines, the second naming its artist."""

THREE_SONGS_READ = (
    Song(0, "アイネクライネ"),
    Song(252_000, "ゴーゴー幽霊船", "ハチ"),
    Song(3_723_000, "Last"),
)

OUT_OF_ORDER = """\
00:00 Intro
07:40 Blue Room
03:12 Night Drive
"""
"""A description whose second song starts after its third."""

TWO_CHAPTERS = (Chapter(0, "Intro"), Chapter(192_000, "Night Drive"))


def titled(title: str) -> VideoText:
    return VideoText(title=title)


def described(description: str) -> VideoText:
    return VideoText(title="Mixtape", description=description)


# --- A video's title ---------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        (
            "【初音ミク】メルト / ryo(supercell)【MV】",
            {Field.TITLE: "メルト", Field.ARTIST: "ryo(supercell)"},
        ),
        (
            "wowaka - アンノウン・マザーグース【Hi-Res】",
            {Field.TITLE: "アンノウン・マザーグース", Field.ARTIST: "wowaka"},
        ),
        ("Night Drive [Hi-Res] 【中字】", {Field.TITLE: "Night Drive"}),
        ("【无损音质】【MV】 Night Drive", {Field.TITLE: "Night Drive"}),
    ],
    ids=[
        "tags around a title and artist",
        "a tag after an artist and title",
        "tags in both kinds of brackets",
        "tags before a lone title",
    ],
)
def test_bracketed_tags_are_dropped_from_the_title(
    title: str, expected: dict[Field, Value]
) -> None:
    assert read_video(titled(title)).values == expected


@pytest.mark.parametrize(
    "title",
    [
        "wowaka - Unknown Mother-Goose",
        "wowaka \u2013 Unknown Mother-Goose",
        "wowaka \u2014 Unknown Mother-Goose",
        "wowaka\uff0dUnknown Mother-Goose",
        "Unknown Mother-Goose / wowaka",
        "Unknown Mother-Goose \uff0f wowaka",
    ],
    ids=["hyphen", "en dash", "em dash", "full-width hyphen", "slash", "full-width slash"],
)
def test_a_title_splits_into_artist_and_title_at_each_separator(title: str) -> None:
    assert read_video(titled(title)).values == {
        Field.TITLE: "Unknown Mother-Goose",
        Field.ARTIST: "wowaka",
    }


def test_a_title_with_no_separator_has_no_artist() -> None:
    assert read_video(titled("Spider-Man Theme")).values == {Field.TITLE: "Spider-Man Theme"}


def test_a_hyphen_with_no_space_around_it_does_not_split() -> None:
    assert read_video(titled("Re-Start")).values == {Field.TITLE: "Re-Start"}


def test_a_dash_splits_before_a_slash_does() -> None:
    values = read_video(titled("wowaka - Rolling Girl / Unknown")).values

    assert values == {Field.ARTIST: "wowaka", Field.TITLE: "Rolling Girl / Unknown"}


def test_a_separator_with_nothing_beside_it_leaves_the_title_whole() -> None:
    assert read_video(titled("wowaka - ")).values == {Field.TITLE: "wowaka"}


def test_whitespace_in_a_title_collapses() -> None:
    values = read_video(titled("  wowaka 　-\n  Rolling\t Girl  ")).values

    assert values == {Field.ARTIST: "wowaka", Field.TITLE: "Rolling Girl"}


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("初音ミク 「メルト」", {Field.TITLE: "メルト", Field.ARTIST: "初音ミク"}),
        ("初音ミク 『メルト』", {Field.TITLE: "メルト", Field.ARTIST: "初音ミク"}),
        ("【MV】「メルト」", {Field.TITLE: "メルト"}),
        ("ryo - 「メルト」", {Field.TITLE: "メルト", Field.ARTIST: "ryo"}),
        ("《メルト》 / ryo", {Field.TITLE: "メルト", Field.ARTIST: "ryo"}),
        ("「メルト」を歌ってみた", {Field.TITLE: "メルト"}),
        ("【洛天依】《霜雪千年》原创", {Field.TITLE: "霜雪千年"}),
    ],
    ids=[
        "corner brackets",
        "double corner brackets",
        "alone",
        "after a dash",
        "before a slash",
        "with words after it",
        "with a note after it",
    ],
)
def test_a_name_in_quoting_marks_is_the_title(title: str, expected: dict[Field, Value]) -> None:
    assert read_video(titled(title)).values == expected


@pytest.mark.parametrize("title", ["", "   ", "\n\t", "【MV】", "[Hi-Res] 【中字】"])
def test_a_title_with_no_text_has_no_values(title: str) -> None:
    assert read_video(titled(title)).values == {}


def test_a_long_title_is_cut_to_the_text_limit() -> None:
    values = read_video(titled("x" * (MAX_TEXT + 40))).values

    assert values == {Field.TITLE: "x" * MAX_TEXT}


def test_a_title_is_not_an_album_by_itself() -> None:
    assert not read_video(titled("wowaka - Rolling Girl")).album


# --- An album ----------------------------------------------------------------


def test_a_full_album_in_chinese_names_the_album_in_quoting_marks() -> None:
    reading = read_video(titled("【无损音质】ハチ 全专《Bremen》"))

    assert reading.album
    assert reading.values == {
        Field.ALBUM: "Bremen",
        Field.TITLE: "Bremen",
        Field.ARTIST: "ハチ",
        Field.ALBUM_ARTIST: "ハチ",
    }


def test_an_english_full_album_takes_its_artist_from_before_the_dash() -> None:
    reading = read_video(titled("米津玄師 - 「STRAY SHEEP」Full Album"))

    assert reading.album
    assert reading.values == {
        Field.ALBUM: "STRAY SHEEP",
        Field.TITLE: "STRAY SHEEP",
        Field.ARTIST: "米津玄師",
        Field.ALBUM_ARTIST: "米津玄師",
    }


def test_an_album_with_no_quoting_marks_is_named_by_what_is_left() -> None:
    reading = read_video(titled("ハチ - Bremen 全专"))

    assert reading.values == {
        Field.ALBUM: "Bremen",
        Field.TITLE: "Bremen",
        Field.ARTIST: "ハチ",
        Field.ALBUM_ARTIST: "ハチ",
    }


def test_an_album_with_no_artist_has_no_album_artist() -> None:
    reading = read_video(titled("Bremen 专辑"))

    assert reading.album
    assert reading.values == {Field.ALBUM: "Bremen", Field.TITLE: "Bremen"}


@pytest.mark.parametrize(
    "title",
    [
        "Bremen 专辑",
        "Bremen 全专",
        "Bremen 全专辑",
        "Bremen 合集",
        "Bremen アルバム",
        "Bremen Full Album",
        "Bremen full album",
        "Bremen ALBUM",
        "【Full Album】Bremen",
        "Bremen [album]",
    ],
)
def test_an_album_word_marks_the_video_as_an_album_named_without_it(title: str) -> None:
    reading = read_video(titled(title))

    assert reading.album
    assert reading.values[Field.ALBUM] == "Bremen"


@pytest.mark.parametrize("title", ["Albumin", "Albums"])
def test_a_word_that_only_contains_album_is_not_an_album_word(title: str) -> None:
    assert not read_video(titled(title)).album


def test_three_songs_in_the_description_make_the_video_an_album() -> None:
    reading = read_video(VideoText("ハチ - Bremen", THREE_SONGS))

    assert reading.album
    assert reading.values == {
        Field.ALBUM: "Bremen",
        Field.TITLE: "Bremen",
        Field.ARTIST: "ハチ",
        Field.ALBUM_ARTIST: "ハチ",
    }


def test_two_songs_do_not_make_the_video_an_album() -> None:
    reading = read_video(VideoText("ハチ - Bremen", "00:00 Intro\n03:12 Night Drive"))

    assert not reading.album
    assert reading.values == {Field.TITLE: "Bremen", Field.ARTIST: "ハチ"}


# --- A video's song list -----------------------------------------------------


def test_a_description_lists_songs_by_their_timestamps() -> None:
    assert read_video(described(THREE_SONGS)).songs == THREE_SONGS_READ


def test_a_description_with_no_timestamps_has_no_songs() -> None:
    assert read_video(described("A mixtape of old songs.\nThanks for watching!")).songs == ()


def test_a_description_with_one_timestamped_line_has_no_songs() -> None:
    assert read_video(described("Intro\n03:12 Night Drive")).songs == ()


def test_timestamps_out_of_order_give_no_songs() -> None:
    assert read_video(described(OUT_OF_ORDER)).songs == ()


def test_a_line_with_no_title_is_not_a_song() -> None:
    description = """\
00:00 Intro
03:12
07:40 Blue Room
"""

    assert read_video(described(description)).songs == (
        Song(0, "Intro"),
        Song(460_000, "Blue Room"),
    )


def test_a_line_padded_with_spaces_reads_as_its_song() -> None:
    description = "00:00 　  Intro\n03:12" + " " * 40 + "Night Drive\n"

    assert read_video(described(description)).songs == (
        Song(0, "Intro"),
        Song(192_000, "Night Drive"),
    )


def test_a_line_of_long_padding_is_read_at_once() -> None:
    padded = "Intro" + " " * 1_000 + "credits"
    description = f"00:00 Intro\n{padded}\n03:12 Night Drive\n"

    started = time.perf_counter()
    songs = read_video(described(description)).songs

    assert time.perf_counter() - started < 1.0
    assert songs == (Song(0, "Intro"), Song(192_000, "Night Drive"))


def test_a_line_too_long_for_a_song_is_not_one() -> None:
    description = f"00:00 Intro\n03:12 {'x' * MAX_LINE}\n07:40 Blue Room\n"

    assert read_video(described(description)).songs == (
        Song(0, "Intro"),
        Song(460_000, "Blue Room"),
    )


def test_two_chapters_make_the_song_list() -> None:
    reading = read_video(VideoText("Mixtape", chapters=TWO_CHAPTERS))

    assert reading.songs == (Song(0, "Intro"), Song(192_000, "Night Drive"))


def test_a_chapter_title_may_name_its_artist() -> None:
    chapters = (Chapter(0, "Intro"), Chapter(192_000, "Night Drive - Blue Room"))

    songs = read_video(VideoText("Mixtape", chapters=chapters)).songs

    assert songs[1] == Song(192_000, "Night Drive", "Blue Room")


def test_chapters_are_used_in_preference_to_the_description() -> None:
    reading = read_video(VideoText("Mixtape", THREE_SONGS, TWO_CHAPTERS))

    assert [song.title for song in reading.songs] == ["Intro", "Night Drive"]


def test_one_chapter_is_not_a_list_so_the_description_is_read() -> None:
    reading = read_video(VideoText("Mixtape", THREE_SONGS, (Chapter(0, "Full video"),)))

    assert reading.songs == THREE_SONGS_READ


def test_chapters_that_fail_the_checks_give_no_songs_without_reading_the_description() -> None:
    chapters = (Chapter(192_000, "Night Drive"), Chapter(0, "Intro"))

    assert read_video(VideoText("Mixtape", THREE_SONGS, chapters)).songs == ()


def test_chapters_closer_than_a_second_give_no_songs() -> None:
    chapters = (Chapter(0, "Intro"), Chapter(999, "Night Drive"))

    assert read_video(VideoText("Mixtape", chapters=chapters)).songs == ()


def test_a_chapter_with_no_title_is_not_a_song() -> None:
    chapters = (Chapter(0, "Intro"), Chapter(60_000, "  "), Chapter(120_000, "Blue Room"))

    songs = read_video(VideoText("Mixtape", chapters=chapters)).songs

    assert songs == (Song(0, "Intro"), Song(120_000, "Blue Room"))


def test_a_long_song_title_is_cut_to_the_text_limit() -> None:
    chapters = (Chapter(0, "x" * (MAX_TEXT + 10)), Chapter(60_000, "Blue Room"))

    songs = read_video(VideoText("Mixtape", chapters=chapters)).songs

    assert songs[0].title == "x" * MAX_TEXT


def test_a_video_with_no_text_has_no_values_and_no_songs() -> None:
    reading = read_video(VideoText(title=""))

    assert (reading.values, reading.songs, reading.album) == ({}, (), False)


# --- A pasted song list ------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("00:00 Intro", Song(0, "Intro")),
        ("0:05 Intro", Song(5_000, "Intro")),
        ("1. 03:12 Night Drive - Blue Room", Song(192_000, "Night Drive", "Blue Room")),
        ("01 03:12 Night Drive", Song(192_000, "Night Drive")),
        ("2) 3:12 Night Drive", Song(192_000, "Night Drive")),
        ("[03:12] Night Drive", Song(192_000, "Night Drive")),
        ("(03:12) Night Drive", Song(192_000, "Night Drive")),
        ("03:12 - Night Drive", Song(192_000, "Night Drive")),
        ("03:12 | Night Drive · Blue Room", Song(192_000, "Night Drive · Blue Room")),
        ("Blue Room 1:07:40", Song(4_060_000, "Blue Room")),
        ("Blue Room - 1:07:40", Song(4_060_000, "Blue Room")),
        ("Blue Room (07:40)", Song(460_000, "Blue Room")),
        ("Night Drive - Blue Room 03:12", Song(192_000, "Night Drive", "Blue Room")),
        ("125:30 Late", Song(7_530_000, "Late")),
        ("  00:00    Intro  ", Song(0, "Intro")),
        ("3 Doors Down 02:10", Song(130_000, "3 Doors Down")),
    ],
    ids=[
        "time then title",
        "a one digit minute",
        "number, time, title and artist",
        "number with no dot",
        "number with a parenthesis",
        "time in square brackets",
        "time in parentheses",
        "separator after the time",
        "other separators stay inside",
        "title then hours",
        "separator before the time",
        "time in parentheses at the end",
        "title and artist before the time",
        "minutes past an hour",
        "spaces around",
        "a title starting with a number",
    ],
)
def test_a_pasted_line_reads_as_a_song(line: str, expected: Song) -> None:
    other = "9:00:00 Closing"

    songs = read_song_list(f"{line}\n{other}")

    assert songs == (expected, Song(32_400_000, "Closing"))


def test_a_pasted_list_reads_one_song_a_line_skipping_blank_lines() -> None:
    text = """\
00:00 Intro

1. 03:12 Night Drive - Blue Room
Blue Room 1:07:40
"""

    assert read_song_list(text) == (
        Song(0, "Intro"),
        Song(192_000, "Night Drive", "Blue Room"),
        Song(4_060_000, "Blue Room"),
    )


def test_a_pasted_line_with_no_time_is_refused_naming_the_line() -> None:
    text = "00:00 Intro\nNight Drive\n07:40 Blue Room"

    with pytest.raises(InvalidInputError, match=r"Line 2.*no time"):
        read_song_list(text)


def test_a_pasted_line_too_long_for_a_song_is_refused_naming_the_line() -> None:
    with pytest.raises(InvalidInputError, match=r"Line 2.*too long"):
        read_song_list(f"00:00 Intro\n03:12 {'x' * MAX_LINE}")


def test_a_pasted_line_with_a_time_out_of_range_has_no_time() -> None:
    with pytest.raises(InvalidInputError, match=r"Line 2.*no time"):
        read_song_list("00:00 Intro\n03:75 Night Drive")


def test_a_pasted_line_with_no_title_is_refused_naming_the_line() -> None:
    with pytest.raises(InvalidInputError, match=r"Line 2.*no title"):
        read_song_list("00:00 Intro\n03:12\n07:40 Blue Room")


def test_a_pasted_list_out_of_order_is_refused() -> None:
    with pytest.raises(InvalidInputError, match="rise"):
        read_song_list(OUT_OF_ORDER)


@pytest.mark.parametrize("text", ["", "  \n\n", "00:00 Intro"])
def test_a_pasted_list_of_fewer_than_two_songs_is_refused(text: str) -> None:
    with pytest.raises(InvalidInputError, match="at least 2 songs"):
        read_song_list(text)


def test_a_pasted_list_of_too_many_songs_is_refused() -> None:
    text = "\n".join(f"{n // 60}:{n % 60:02} Song {n}" for n in range(MAX_SONGS + 1))

    with pytest.raises(InvalidInputError, match=f"at most {MAX_SONGS} songs"):
        read_song_list(text)


def test_a_pasted_list_of_the_most_songs_is_accepted() -> None:
    text = "\n".join(f"{n // 60}:{n % 60:02} Song {n}" for n in range(MAX_SONGS))

    assert len(read_song_list(text)) == MAX_SONGS


# --- Checking a song list ----------------------------------------------------


def test_a_song_list_that_starts_at_zero_and_rises_passes() -> None:
    check_songs([Song(0, "Intro"), Song(1_000, "Night Drive")])


@pytest.mark.parametrize(
    ("songs", "message"),
    [
        ([Song(-1, "Intro"), Song(5_000, "Night Drive")], "from 0"),
        ([Song(5_000, "Intro"), Song(5_000, "Night Drive")], "rise"),
        ([Song(5_000, "Intro"), Song(4_000, "Night Drive")], "rise"),
        ([Song(0, "Intro"), Song(999, "Night Drive")], "rise"),
        ([Song(0, "Intro")], "at least 2 songs"),
        ([Song(0, " Intro"), Song(5_000, "Night Drive")], "title"),
        ([Song(0, ""), Song(5_000, "Night Drive")], "title"),
        ([Song(0, "x" * (MAX_TEXT + 1)), Song(5_000, "Night Drive")], "title"),
        ([Song(0, "Intro", " wowaka"), Song(5_000, "Night Drive")], "artist"),
        ([Song(0, "Intro", "x" * (MAX_TEXT + 1)), Song(5_000, "Night Drive")], "artist"),
    ],
    ids=[
        "a negative start",
        "two songs starting together",
        "a start before the one before it",
        "a song shorter than a second",
        "one song",
        "an untrimmed title",
        "a blank title",
        "a title too long",
        "an untrimmed artist",
        "an artist too long",
    ],
)
def test_a_song_list_breaking_a_rule_is_refused(songs: list[Song], message: str) -> None:
    with pytest.raises(InvalidInputError, match=message):
        check_songs(songs)


# --- Properties --------------------------------------------------------------

fragments = st.sampled_from(
    [
        "00:00",
        "1:02:03",
        "03:12",
        "7:40",
        "99:99",
        " ",
        "\n",
        "\r\n",
        " - ",
        "【MV】",
        "[",
        "]",
        "「",
        "」",
        "《",
        "》",
        " / ",
        "\uff0f",
        "\uff0d",
        "|",
        "1.",
        "Intro",
        "ハチ",
        "全专",
        "Full Album",
        "album",
    ]
)
video_texts = st.one_of(
    st.text(),
    st.lists(fragments, max_size=40).map("".join),
)
chapters = st.lists(
    st.builds(Chapter, start_ms=st.integers(-10_000, 400_000), title=video_texts), max_size=6
)


@given(title=video_texts, description=video_texts, listed=chapters)
def test_reading_never_raises_on_any_text(
    title: str, description: str, listed: list[Chapter]
) -> None:
    read_video(VideoText(title, description, tuple(listed)))


@given(title=video_texts, description=video_texts, listed=chapters)
def test_a_song_list_read_from_a_video_passes_the_checks(
    title: str, description: str, listed: list[Chapter]
) -> None:
    songs = read_video(VideoText(title, description, tuple(listed))).songs

    if songs:
        check_songs(songs)


@given(title=video_texts, description=video_texts, listed=chapters)
def test_every_value_read_is_kept_as_found_text_is(
    title: str, description: str, listed: list[Chapter]
) -> None:
    values = read_video(VideoText(title, description, tuple(listed))).values

    for field, value in values.items():
        assert value == found_value(field, value)


@given(title=video_texts, description=video_texts)
def test_a_video_with_three_or_more_songs_is_an_album(title: str, description: str) -> None:
    reading = read_video(VideoText(title, description))

    if len(reading.songs) >= 3:
        assert reading.album


@given(text=video_texts)
def test_a_pasted_list_is_accepted_or_refused_never_something_else(text: str) -> None:
    try:
        songs = read_song_list(text)
    except InvalidInputError:
        return

    check_songs(songs)


words = st.text(st.characters(categories=["L"]), min_size=1, max_size=12)
names = st.lists(words, min_size=1, max_size=3).map(" ".join)


@st.composite
def song_lists(draw: st.DrawFn) -> tuple[Song, ...]:
    first = draw(st.integers(0, 600))
    gaps = draw(st.lists(st.integers(1, 3_600), min_size=1, max_size=19))
    starts = accumulate(gaps, initial=first)
    return tuple(
        Song(start_ms=second * 1_000, title=draw(names), artist=draw(st.one_of(st.just(""), names)))
        for second in starts
    )


def format_song(song: Song) -> str:
    hours, rest = divmod(song.start_ms // 1_000, 3_600)
    minutes, seconds = divmod(rest, 60)
    clock = f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes:02}:{seconds:02}"
    return f"{clock} {song.title} - {song.artist}" if song.artist else f"{clock} {song.title}"


@given(songs=song_lists())
def test_a_song_list_formatted_as_lines_reads_back_the_same(songs: tuple[Song, ...]) -> None:
    text = "\n".join(format_song(song) for song in songs)

    assert read_song_list(text) == songs


@given(title=video_texts, songs=song_lists())
def test_a_description_of_song_lines_gives_the_songs_whatever_the_title(
    title: str, songs: tuple[Song, ...]
) -> None:
    description = "\n".join(format_song(song) for song in songs)

    assert read_video(VideoText(title, description)).songs == songs
