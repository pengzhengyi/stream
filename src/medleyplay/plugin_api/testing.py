"""The contract kit: checks every provider of an operation must pass, for plugins' tests."""

from pydantic import BaseModel, ValidationError

from medleyplay.plugin_api.extension import Operation


class ContractError(AssertionError):
    """A provider broke its extension point's contract."""


def check_operation[P, I: BaseModel, O: BaseModel](
    operation: Operation[P, I, O], provider: P, request: I
) -> O:
    """Call `operation` on `provider` twice and return the reply.

    The reply must be the operation's reply model, survive a JSON round trip
    unchanged, as it must to cross the pipe, and be the same both times.
    """
    first = operation.invoke(provider, request)
    check_round_trip(first)
    second = operation.invoke(provider, request)
    if second != first:
        message = f"Calling twice gave different replies: {first!r}, then {second!r}."
        raise ContractError(message)
    return first


def check_round_trip(model: BaseModel) -> None:
    """Check that `model` survives a JSON round trip unchanged."""
    try:
        again = type(model).model_validate_json(model.model_dump_json())
    except ValidationError as error:
        message = f"{model!r} doesn't survive a JSON round trip: {error}"
        raise ContractError(message) from error
    if again != model:
        message = f"{model!r} became {again!r} in a JSON round trip."
        raise ContractError(message)
