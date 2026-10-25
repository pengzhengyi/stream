"""Extension points and operations: declaring them, invoking them, and provider keys."""

import pytest

from medleyplay.plugin_api import ExtensionPoint, check_key
from tests.support.echo import ECHO, SAY, Echo, Parrot, Said, Say


def test_a_point_lists_the_operations_declared_on_it() -> None:
    assert ECHO.operations["say"] is SAY
    assert SAY.point is ECHO
    assert repr(ECHO) == "ExtensionPoint('echo')"


def test_declaring_an_operation_name_twice_is_refused() -> None:
    point = ExtensionPoint[Echo]("twice")
    point.operation("say", Say, Said, lambda echo: echo.say)

    with pytest.raises(ValueError, match="twice already has an operation 'say'"):
        point.operation("say", Say, Said, lambda echo: echo.say)


def test_invoking_an_operation_calls_the_providers_method() -> None:
    assert SAY.invoke(Parrot(), Say(text="hi")) == Said(text="hi")


def test_invoking_an_operation_refuses_a_reply_of_the_wrong_type() -> None:
    with pytest.raises(TypeError, match=r"echo\.say returned Say, not Said\."):
        SAY.invoke(Parrot(), Say(text="hi", wrong_reply=True))


@pytest.mark.parametrize("key", ["mp3", "file", "bilibili", "a.b_c-d"])
def test_a_lowercase_key_is_valid(key: str) -> None:
    assert check_key(key) == key


@pytest.mark.parametrize("key", ["", "MP3", "-mp3", "has space", "x" * 65])
def test_other_keys_are_refused(key: str) -> None:
    with pytest.raises(ValueError, match="isn't a valid key"):
        check_key(key)
