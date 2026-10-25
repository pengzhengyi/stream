"""The contract kit catches providers that break their extension point's contract."""

import math

import pytest
from pydantic import BaseModel, field_serializer

from medleyplay.plugin_api import ExtensionPoint
from medleyplay.plugin_api.testing import ContractError, check_operation, check_round_trip
from tests.support.echo import SAY, Parrot, Said, Say


class Measured(BaseModel):
    value: float


class Rounded(BaseModel):
    """A model whose serializer rounds, so it can't come back as it was."""

    value: float

    @field_serializer("value")
    def _rounded(self, value: float) -> float:
        return float(round(value + 0.1))


class Gauge:
    def __init__(self, value: float) -> None:
        self._value = value

    def read(self, request: Say) -> Measured:
        return Measured(value=self._value)


GAUGE = ExtensionPoint[Gauge]("gauge")
READ = GAUGE.operation("read", Say, Measured, lambda gauge: gauge.read)


def test_a_well_behaved_provider_passes_and_its_reply_is_returned() -> None:
    assert check_operation(SAY, Parrot(), Say(text="hi")) == Said(text="hi")


def test_a_provider_whose_reply_changes_between_calls_fails() -> None:
    with pytest.raises(ContractError, match="Calling twice gave different replies"):
        check_operation(SAY, Parrot(), Say(text="hi", count_calls=True))


def test_a_reply_that_does_not_survive_a_json_round_trip_fails() -> None:
    with pytest.raises(ContractError, match="doesn't survive a JSON round trip"):
        check_operation(READ, Gauge(math.nan), Say(text="read"))


def test_a_model_that_survives_a_round_trip_passes() -> None:
    check_round_trip(Measured(value=1.5))


def test_a_model_that_changes_in_a_round_trip_fails() -> None:
    with pytest.raises(ContractError, match=r"became Rounded\(value=2\.0\) in a JSON round trip"):
        check_round_trip(Rounded(value=1.5))
