"""A Track's details: checking values, and choosing the value each field shows."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from medleyplay.domain.details import (
    ALBUM_FIELDS,
    MAX_TEXT,
    ORIGINS,
    Field,
    Origin,
    Shown,
    Value,
    Values,
    check_value,
    check_values,
    shown,
)
from medleyplay.domain.errors import InvalidInputError


def test_a_field_shows_the_first_origins_value() -> None:
    values = {
        Origin.FILE_NAME: {Field.TITLE: "BV1dm4y1s7ak"},
        Origin.FILES: {Field.TITLE: "Night Drive"},
    }

    assert shown(values)[Field.TITLE] == Shown("Night Drive", Origin.FILES)


def test_the_households_value_wins_over_every_other() -> None:
    values = {
        Origin.FILES: {Field.ARTIST: "GUMI"},
        Origin.HOUSEHOLD: {Field.ARTIST: "GUMI/MAYU"},
    }

    assert shown(values)[Field.ARTIST] == Shown("GUMI/MAYU", Origin.HOUSEHOLD)


def test_empty_text_from_the_household_shows_nothing() -> None:
    values = {Origin.FILES: {Field.GENRE: "Pop"}, Origin.HOUSEHOLD: {Field.GENRE: ""}}

    assert shown(values)[Field.GENRE] == Shown("", Origin.HOUSEHOLD)


def test_a_field_no_origin_has_is_absent() -> None:
    assert Field.YEAR not in shown({Origin.FILES: {Field.TITLE: "Intro"}})


def test_the_album_fields_come_from_the_first_origin_naming_an_album() -> None:
    values = {
        Origin.FILES: {Field.TRACK_NUMBER: 7},
        Origin.VIDEO: {Field.ALBUM: "Re:Start", Field.YEAR: 2016, Field.TRACK_NUMBER: 2},
    }

    found = shown(values)

    assert found[Field.ALBUM] == Shown("Re:Start", Origin.VIDEO)
    assert found[Field.TRACK_NUMBER] == Shown(2, Origin.VIDEO)
    assert found[Field.YEAR] == Shown(2016, Origin.VIDEO)


def test_the_households_album_field_still_wins_on_its_own() -> None:
    values = {
        Origin.VIDEO: {Field.ALBUM: "Re:Start", Field.YEAR: 2016},
        Origin.HOUSEHOLD: {Field.YEAR: 2017},
    }

    found = shown(values)

    assert found[Field.ALBUM] == Shown("Re:Start", Origin.VIDEO)
    assert found[Field.YEAR] == Shown(2017, Origin.HOUSEHOLD)


def test_without_a_named_album_each_album_field_falls_back_on_its_own() -> None:
    values = {Origin.FILES: {Field.TRACK_NUMBER: 3}, Origin.VIDEO: {Field.YEAR: 2014}}

    found = shown(values)

    assert found[Field.TRACK_NUMBER] == Shown(3, Origin.FILES)
    assert found[Field.YEAR] == Shown(2014, Origin.VIDEO)


def test_text_is_trimmed() -> None:
    assert check_value(Field.TITLE, "  Intro \n") == "Intro"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        (Field.TITLE, "x" * (MAX_TEXT + 1)),
        (Field.TITLE, 3),
        (Field.TRACK_NUMBER, 0),
        (Field.TRACK_NUMBER, "3"),
        (Field.TRACK_NUMBER, True),
        (Field.DISC_NUMBER, 1000),
        (Field.YEAR, 999),
        (Field.YEAR, 3000),
    ],
    ids=[
        "text too long",
        "a number for text",
        "a track number of 0",
        "text for a number",
        "a boolean for a number",
        "a disc number over 999",
        "a year of three digits",
        "a year past 2999",
    ],
)
def test_a_value_its_field_cant_keep_is_refused(field: Field, value: object) -> None:
    with pytest.raises(InvalidInputError):
        check_value(field, value)


def test_values_are_checked_by_their_field_names() -> None:
    assert check_values({"title": " Intro ", "year": 2014}) == {
        Field.TITLE: "Intro",
        Field.YEAR: 2014,
    }


def test_a_field_a_track_doesnt_have_is_refused() -> None:
    with pytest.raises(InvalidInputError, match="lyrics"):
        check_values({"lyrics": "la la"})


_VALUE = st.one_of(st.text(max_size=4), st.integers(min_value=1, max_value=9))
_VALUES = st.dictionaries(
    st.sampled_from(Origin),
    st.dictionaries(st.sampled_from(Field), _VALUE, max_size=4),
    max_size=len(ORIGINS),
)


@given(_VALUES)
def test_every_shown_value_is_one_an_origin_holds(values: dict[Origin, Values]) -> None:
    for field, found in shown(values).items():
        assert values[found.origin][field] == found.value


@given(_VALUES)
def test_a_field_outside_the_album_shows_the_first_origin_holding_it(
    values: dict[Origin, Values],
) -> None:
    for field in set(Field) - ALBUM_FIELDS:
        holding = [origin for origin in ORIGINS if field in values.get(origin, {})]

        assert shown(values).get(field) == (
            Shown(values[holding[0]][field], holding[0]) if holding else None
        )


@given(_VALUES, st.sampled_from(Field), _VALUE)
def test_the_households_value_always_shows(
    values: dict[Origin, Values], field: Field, value: Value
) -> None:
    values = {**values, Origin.HOUSEHOLD: {**values.get(Origin.HOUSEHOLD, {}), field: value}}

    assert shown(values)[field] == Shown(value, Origin.HOUSEHOLD)


@given(_VALUES)
def test_the_album_fields_never_mix_two_origins_besides_the_household(
    values: dict[Origin, Values],
) -> None:
    found = shown(values)
    if Field.ALBUM in found and found[Field.ALBUM].value:
        others = {
            found[field].origin
            for field in ALBUM_FIELDS
            if field in found and found[field].origin is not Origin.HOUSEHOLD
        }

        assert len(others) <= 1
