"""Accounts: usernames, display names, and passwords."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from medleyplay.domain.accounts import (
    check_password,
    parse_display_name,
    parse_username,
)
from medleyplay.domain.errors import InvalidInputError


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [("alice", "alice"), ("Alice", "alice"), ("  bob.smith ", "bob.smith"), ("a_1-b", "a_1-b")],
)
def test_a_valid_username_is_stored_lowercase_without_spaces(raw: str, canonical: str) -> None:
    assert parse_username(raw) == canonical


@pytest.mark.parametrize("raw", ["", "   ", "has space", "-leading", "é", "x" * 33, "a/b"])
def test_an_invalid_username_is_refused(raw: str) -> None:
    with pytest.raises(InvalidInputError, match="Username"):
        parse_username(raw)


@given(st.from_regex(r"[A-Za-z0-9][A-Za-z0-9._-]{0,31}", fullmatch=True))
def test_parsing_a_canonical_username_again_leaves_it_unchanged(raw: str) -> None:
    canonical = parse_username(raw)

    assert parse_username(canonical) == canonical


def test_a_display_name_keeps_its_case_and_loses_surrounding_spaces() -> None:
    assert parse_display_name("  Alice Smith ") == "Alice Smith"


@pytest.mark.parametrize("raw", ["", "  ", "x" * 65])
def test_an_empty_or_overlong_display_name_is_refused(raw: str) -> None:
    with pytest.raises(InvalidInputError, match="display name"):
        parse_display_name(raw)


@pytest.mark.parametrize("password", ["1234567", "x" * 257])
def test_a_password_outside_8_to_256_characters_is_refused(password: str) -> None:
    with pytest.raises(InvalidInputError, match="password"):
        check_password(password)


def test_an_8_character_password_is_accepted() -> None:
    check_password("12345678")
